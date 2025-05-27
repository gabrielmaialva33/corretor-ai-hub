"""
Base scraper class for real estate websites
"""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx
import structlog
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
from sqlalchemy import select, and_

from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import Property, PropertyStatus

logger = structlog.get_logger()
settings = get_settings()


class BaseScraper(ABC):
    """
    Abstract base class for property scrapers
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.browser: Optional[Browser] = None
        self.playwright = None
        self.client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.SCRAPER_USER_AGENT
            },
            timeout=settings.SCRAPER_TIMEOUT,
            follow_redirects=True
        )

    @abstractmethod
    def get_base_url(self) -> str:
        """Get the base URL for the scraper"""
        pass

    @abstractmethod
    async def get_listing_urls(self, page: int = 1) -> List[str]:
        """Get property listing URLs from a page"""
        pass

    @abstractmethod
    async def scrape_property(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single property"""
        pass

    @abstractmethod
    def parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text"""
        pass

    async def __aenter__(self):
        """Initialize browser for scraping"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup browser and connections"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        await self.client.aclose()

    async def create_page(self) -> Page:
        """Create a new browser page with default settings"""
        if not self.browser:
            raise RuntimeError("Browser not initialized")

        page = await self.browser.new_page(
            viewport={"width": 1920, "height": 1080},
            user_agent=settings.SCRAPER_USER_AGENT
        )

        # Set default timeout
        page.set_default_timeout(settings.SCRAPER_TIMEOUT * 1000)

        return page

    async def fetch_with_retry(
            self,
            url: str,
            use_browser: bool = False,
            retry_count: int = None
    ) -> Optional[str]:
        """
        Fetch URL content with retry logic
        
        Args:
            url: URL to fetch
            use_browser: Use Playwright browser instead of httpx
            retry_count: Number of retries (default from settings)
        
        Returns:
            HTML content or None if failed
        """
        retry_count = retry_count or settings.SCRAPER_RETRY_ATTEMPTS

        for attempt in range(retry_count):
            try:
                if use_browser:
                    page = await self.create_page()
                    try:
                        await page.goto(url, wait_until="domcontentloaded")
                        await page.wait_for_timeout(2000)  # Wait for dynamic content
                        content = await page.content()
                        return content
                    finally:
                        await page.close()
                else:
                    response = await self.client.get(url)
                    response.raise_for_status()
                    return response.text

            except Exception as e:
                logger.warning(
                    f"Fetch attempt {attempt + 1} failed",
                    url=url,
                    error=str(e)
                )

                if attempt < retry_count - 1:
                    await asyncio.sleep(settings.SCRAPER_RATE_LIMIT_DELAY * (attempt + 1))
                else:
                    logger.error(f"All fetch attempts failed for {url}")
                    return None

        return None

    def extract_text(self, element, default: str = "") -> str:
        """Safely extract text from BeautifulSoup element"""
        if element:
            return element.get_text(strip=True)
        return default

    def extract_number(self, text: str) -> Optional[float]:
        """Extract number from text"""
        if not text:
            return None

        # Remove common non-numeric characters
        cleaned = text.replace(".", "").replace(",", ".").strip()

        # Extract numeric part
        import re
        match = re.search(r'[\d.]+', cleaned)

        if match:
            try:
                return float(match.group())
            except ValueError:
                return None

        return None

    async def save_property(self, property_data: Dict[str, Any]) -> bool:
        """
        Save or update property in database
        
        Args:
            property_data: Property data dictionary
        
        Returns:
            True if saved successfully
        """
        try:
            async with get_session() as session:
                # Check if property already exists
                stmt = select(Property).where(
                    and_(
                        Property.tenant_id == self.tenant_id,
                        Property.source_id == property_data.get("source_id")
                    )
                )

                result = await session.execute(stmt)
                existing_property = result.scalar_one_or_none()

                if existing_property:
                    # Update existing property
                    for key, value in property_data.items():
                        if hasattr(existing_property, key) and value is not None:
                            setattr(existing_property, key, value)

                    existing_property.updated_at = datetime.utcnow()
                    existing_property.scraped_at = datetime.utcnow()

                else:
                    # Create new property
                    property_data["tenant_id"] = self.tenant_id
                    property_data["scraped_at"] = datetime.utcnow()
                    property_data["status"] = PropertyStatus.AVAILABLE
                    property_data["is_active"] = True

                    new_property = Property(**property_data)
                    session.add(new_property)

                await session.commit()
                return True

        except Exception as e:
            logger.error(
                "Failed to save property",
                error=str(e),
                source_id=property_data.get("source_id")
            )
            return False

    async def scrape_all(
            self,
            max_pages: int = 10,
            max_properties_per_page: int = 20
    ) -> Dict[str, Any]:
        """
        Scrape all properties from the website
        
        Args:
            max_pages: Maximum number of pages to scrape
            max_properties_per_page: Maximum properties per page
        
        Returns:
            Scraping results summary
        """
        results = {
            "total_scraped": 0,
            "total_saved": 0,
            "total_failed": 0,
            "errors": []
        }

        try:
            for page in range(1, max_pages + 1):
                logger.info(f"Scraping page {page}")

                # Get listing URLs
                listing_urls = await self.get_listing_urls(page)

                if not listing_urls:
                    logger.info(f"No listings found on page {page}, stopping")
                    break

                # Limit properties per page
                listing_urls = listing_urls[:max_properties_per_page]

                # Scrape each property
                for url in listing_urls:
                    try:
                        # Rate limiting
                        await asyncio.sleep(settings.SCRAPER_RATE_LIMIT_DELAY)

                        # Scrape property
                        property_data = await self.scrape_property(url)

                        if property_data:
                            results["total_scraped"] += 1

                            # Save to database
                            if await self.save_property(property_data):
                                results["total_saved"] += 1
                            else:
                                results["total_failed"] += 1
                        else:
                            results["total_failed"] += 1

                    except Exception as e:
                        logger.error(f"Failed to scrape property: {url}", error=str(e))
                        results["total_failed"] += 1
                        results["errors"].append({
                            "url": url,
                            "error": str(e)
                        })

                # Check if we should continue
                if len(listing_urls) < max_properties_per_page / 2:
                    logger.info("Few listings found, likely near the end")
                    break

        except Exception as e:
            logger.error("Scraping failed", error=str(e))
            results["errors"].append({
                "type": "general",
                "error": str(e)
            })

        return results

    def normalize_property_type(self, type_text: str) -> str:
        """Normalize property type text"""
        type_text = type_text.lower().strip()

        type_mapping = {
            "apartamento": "apartment",
            "casa": "house",
            "cobertura": "penthouse",
            "kitnet": "studio",
            "studio": "studio",
            "loft": "loft",
            "terreno": "land",
            "lote": "land",
            "comercial": "commercial",
            "sala comercial": "commercial",
            "loja": "commercial",
            "galpão": "warehouse",
            "fazenda": "farm",
            "sítio": "farm",
            "chácara": "farm"
        }

        for key, value in type_mapping.items():
            if key in type_text:
                return value

        return "other"

    def normalize_transaction_type(self, text: str) -> str:
        """Normalize transaction type"""
        text = text.lower().strip()

        if "venda" in text or "compra" in text:
            return "sale"
        elif "aluguel" in text or "locação" in text:
            return "rent"

        return "sale"  # Default

    def extract_features(self, features_text: str) -> List[str]:
        """Extract and normalize property features"""
        if not features_text:
            return []

        # Common features to look for
        feature_keywords = {
            "piscina": "pool",
            "churrasqueira": "barbecue",
            "academia": "gym",
            "playground": "playground",
            "salão de festas": "party_room",
            "portaria 24h": "24h_security",
            "varanda": "balcony",
            "sacada": "balcony",
            "ar condicionado": "air_conditioning",
            "closet": "closet",
            "suite": "suite",
            "elevador": "elevator",
            "jardim": "garden",
            "quintal": "backyard",
            "garagem": "garage",
            "lareira": "fireplace",
            "vista mar": "sea_view",
            "vista montanha": "mountain_view"
        }

        features = []
        features_lower = features_text.lower()

        for pt_feature, en_feature in feature_keywords.items():
            if pt_feature in features_lower:
                features.append(en_feature)

        return features
