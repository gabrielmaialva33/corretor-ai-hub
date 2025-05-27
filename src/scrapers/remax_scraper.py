"""
REMAX Argentina property scraper
"""
import asyncio
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import urljoin

import httpx
import structlog
from bs4 import BeautifulSoup

from src.database.models import PropertyType, PropertyStatus
from src.scrapers.base_scraper import BaseScraper

logger = structlog.get_logger()


class RemaxArgentinaScraper(BaseScraper):
    """
    Scraper for REMAX Argentina properties
    """

    BASE_URL = "https://www.remax.com.ar"
    SEARCH_URL = "https://www.remax.com.ar/buscar"

    # Property type mappings
    PROPERTY_TYPE_MAP = {
        "casa": PropertyType.HOUSE,
        "departamento": PropertyType.APARTMENT,
        "ph": PropertyType.HOUSE,
        "local": PropertyType.COMMERCIAL,
        "oficina": PropertyType.COMMERCIAL,
        "terreno": PropertyType.LAND,
        "campo": PropertyType.LAND,
        "cochera": PropertyType.OTHER,
        "deposito": PropertyType.OTHER
    }

    # Operation type mappings
    OPERATION_MAP = {
        "venta": "sale",
        "alquiler": "rent",
        "alquiler temporario": "temporary_rent"
    }

    async def search_properties(
            self,
            filters: Dict[str, Any],
            limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search properties based on filters
        
        Args:
            filters: Search filters including:
                - operation: venta/alquiler
                - property_type: casa/departamento/etc
                - location: city or neighborhood
                - bedrooms: number of bedrooms
                - min_price: minimum price
                - max_price: maximum price
                - min_area: minimum area in m2
                - max_area: maximum area in m2
            limit: Maximum number of results
            
        Returns:
            List of property dictionaries
        """
        try:
            # Build search parameters
            params = self._build_search_params(filters)

            # Perform search
            properties = []
            page = 1

            while len(properties) < limit:
                params["pagina"] = page

                # Make request
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self.SEARCH_URL,
                        params=params,
                        headers=self._get_headers(),
                        timeout=30.0
                    )
                    response.raise_for_status()

                # Parse results
                soup = BeautifulSoup(response.text, 'html.parser')
                page_properties = self._parse_search_results(soup)

                if not page_properties:
                    break

                properties.extend(page_properties)

                if len(properties) >= limit:
                    properties = properties[:limit]
                    break

                page += 1

                # Avoid too many requests
                await asyncio.sleep(1)

            # Fetch details for each property
            detailed_properties = []
            for prop in properties:
                try:
                    details = await self.scrape_property(prop["url"])
                    if details:
                        detailed_properties.append(details)
                except Exception as e:
                    logger.error(f"Error fetching property details", url=prop["url"], error=str(e))

                # Rate limiting
                await asyncio.sleep(0.5)

            return detailed_properties

        except Exception as e:
            logger.error("Error searching properties", error=str(e), filters=filters)
            return []

    async def scrape_property(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape a single property from its detail page
        
        Args:
            url: Property URL
            
        Returns:
            Property data dictionary or None if failed
        """
        try:
            # Ensure full URL
            if not url.startswith("http"):
                url = urljoin(self.BASE_URL, url)

            # Fetch page
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers=self._get_headers(),
                    timeout=30.0
                )
                response.raise_for_status()

            # Parse page
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract property data
            property_data = {
                "source_url": url,
                "source_id": self._extract_property_id(url),
                "scraped_at": datetime.utcnow(),

                # Basic info
                "title": self._extract_title(soup),
                "description": self._extract_description(soup),
                "property_type": self._extract_property_type(soup),

                # Location
                "address": self._extract_address(soup),
                "neighborhood": self._extract_neighborhood(soup),
                "city": self._extract_city(soup),
                "state": "Buenos Aires",  # Default for Argentina
                "country": "Argentina",
                "latitude": self._extract_latitude(soup),
                "longitude": self._extract_longitude(soup),

                # Details
                "bedrooms": self._extract_bedrooms(soup),
                "bathrooms": self._extract_bathrooms(soup),
                "area": self._extract_area(soup),
                "built_area": self._extract_built_area(soup),

                # Financial
                "price": self._extract_price(soup),
                "currency": "ARS",
                "price_per_m2": None,  # Calculate later

                # Features
                "features": self._extract_features(soup),
                "amenities": self._extract_amenities(soup),

                # Media
                "images": self._extract_images(soup),
                "video_url": self._extract_video_url(soup),

                # Status
                "status": PropertyStatus.AVAILABLE,
                "listing_type": self._extract_listing_type(soup)
            }

            # Calculate price per m2
            if property_data["price"] and property_data["area"]:
                property_data["price_per_m2"] = property_data["price"] / property_data["area"]

            # Validate required fields
            if not all([property_data["title"], property_data["price"], property_data["address"]]):
                logger.warning("Missing required fields", url=url, data=property_data)
                return None

            return property_data

        except Exception as e:
            logger.error("Error scraping property", url=url, error=str(e))
            return None

    def _build_search_params(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Build search parameters for REMAX API"""
        params = {}

        # Operation type
        if "operation" in filters:
            params["operacion"] = filters["operation"]

        # Property type
        if "property_type" in filters:
            params["tipo"] = filters["property_type"]

        # Location
        if "location" in filters:
            params["ubicacion"] = filters["location"]
        elif "city" in filters:
            params["ubicacion"] = filters["city"]

        # Bedrooms
        if "bedrooms" in filters:
            params["dormitorios"] = filters["bedrooms"]

        # Price range
        if "min_price" in filters:
            params["precio_desde"] = filters["min_price"]
        if "max_price" in filters:
            params["precio_hasta"] = filters["max_price"]

        # Area range
        if "min_area" in filters:
            params["superficie_desde"] = filters["min_area"]
        if "max_area" in filters:
            params["superficie_hasta"] = filters["max_area"]

        return params

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers"""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }

    def _parse_search_results(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Parse search results page"""
        properties = []

        # Find property cards (adjust selector based on actual HTML)
        property_cards = soup.select(".property-card, .listing-item, [data-property-id]")

        for card in property_cards:
            try:
                # Extract URL
                link = card.select_one("a[href*='/propiedades/'], a[href*='/listing/']")
                if not link:
                    continue

                url = link.get("href", "")
                if not url.startswith("http"):
                    url = urljoin(self.BASE_URL, url)

                # Extract basic info
                title = card.select_one(".property-title, .listing-title, h3, h4")
                price = card.select_one(".property-price, .listing-price, .price")
                location = card.select_one(".property-location, .listing-location, .location")

                properties.append({
                    "url": url,
                    "title": title.get_text(strip=True) if title else "",
                    "price": price.get_text(strip=True) if price else "",
                    "location": location.get_text(strip=True) if location else ""
                })

            except Exception as e:
                logger.error("Error parsing property card", error=str(e))
                continue

        return properties

    def _extract_property_id(self, url: str) -> str:
        """Extract property ID from URL"""
        # Try different patterns
        patterns = [
            r"/listing/(\d+)",
            r"/propiedades/([^/]+)",
            r"id=(\d+)",
            r"-(\d+)\.html"
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return f"remax_{match.group(1)}"

        # Fallback to URL hash
        return f"remax_{hash(url)}"

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract property title"""
        selectors = [
            "h1.property-title",
            "h1.listing-title",
            ".detail-title h1",
            "h1",
            "meta[property='og:title']"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == "meta":
                    return element.get("content", "")
                return element.get_text(strip=True)

        return ""

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract property description"""
        selectors = [
            ".property-description",
            ".listing-description",
            ".description-content",
            ".detail-description",
            "[itemprop='description']"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        return ""

    def _extract_property_type(self, soup: BeautifulSoup) -> PropertyType:
        """Extract and map property type"""
        # Try to find property type in various places
        type_text = ""

        selectors = [
            ".property-type",
            ".listing-type",
            "[data-property-type]",
            ".detail-specs .type"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.get("data-property-type"):
                    type_text = element.get("data-property-type")
                else:
                    type_text = element.get_text(strip=True)
                break

        # Map to our property types
        type_lower = type_text.lower()
        for key, value in self.PROPERTY_TYPE_MAP.items():
            if key in type_lower:
                return value

        return PropertyType.OTHER

    def _extract_address(self, soup: BeautifulSoup) -> str:
        """Extract property address"""
        selectors = [
            ".property-address",
            ".listing-address",
            ".detail-address",
            "[itemprop='address']",
            ".location-info .address"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        return ""

    def _extract_neighborhood(self, soup: BeautifulSoup) -> str:
        """Extract neighborhood"""
        selectors = [
            ".property-neighborhood",
            ".listing-neighborhood",
            ".location-neighborhood",
            "[itemprop='neighborhood']"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        # Try to extract from address
        address = self._extract_address(soup)
        if "," in address:
            parts = address.split(",")
            if len(parts) > 1:
                return parts[0].strip()

        return ""

    def _extract_city(self, soup: BeautifulSoup) -> str:
        """Extract city"""
        selectors = [
            ".property-city",
            ".listing-city",
            ".location-city",
            "[itemprop='addressLocality']"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                return element.get_text(strip=True)

        # Default to Buenos Aires for now
        return "Buenos Aires"

    def _extract_bedrooms(self, soup: BeautifulSoup) -> int:
        """Extract number of bedrooms"""
        patterns = [
            (r"(\d+)\s*(?:dormitorio|habitaci[oó]n|ambiente)", 1),
            (r"(\d+)\s*dorm", 1),
            (r"(\d+)\s*amb", -1)  # Ambientes includes living room
        ]

        # Look in specific elements first
        selectors = [
            ".property-bedrooms",
            ".listing-bedrooms",
            ".bedrooms",
            "[data-bedrooms]",
            ".detail-specs .bedrooms"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                for pattern, adjustment in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        bedrooms = int(match.group(1)) + adjustment
                        return max(0, bedrooms)

        # Search in full text
        full_text = soup.get_text()
        for pattern, adjustment in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                bedrooms = int(match.group(1)) + adjustment
                return max(0, bedrooms)

        return 0

    def _extract_bathrooms(self, soup: BeautifulSoup) -> int:
        """Extract number of bathrooms"""
        patterns = [
            r"(\d+)\s*(?:ba[ñn]o|toilette)",
            r"(\d+)\s*bath"
        ]

        selectors = [
            ".property-bathrooms",
            ".listing-bathrooms",
            ".bathrooms",
            "[data-bathrooms]",
            ".detail-specs .bathrooms"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return int(match.group(1))

        return 0

    def _extract_area(self, soup: BeautifulSoup) -> float:
        """Extract property area in m2"""
        patterns = [
            r"(\d+(?:\.\d+)?)\s*m[²2]",
            r"(\d+(?:\.\d+)?)\s*metros",
            r"superficie\s*:?\s*(\d+(?:\.\d+)?)"
        ]

        selectors = [
            ".property-area",
            ".listing-area",
            ".area",
            "[data-area]",
            ".detail-specs .area",
            ".surface"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True)
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        return float(match.group(1))

        return 0.0

    def _extract_built_area(self, soup: BeautifulSoup) -> float:
        """Extract built area"""
        patterns = [
            r"construido[s]?\s*:?\s*(\d+(?:\.\d+)?)",
            r"cubierto[s]?\s*:?\s*(\d+(?:\.\d+)?)",
            r"edificado[s]?\s*:?\s*(\d+(?:\.\d+)?)"
        ]

        full_text = soup.get_text()
        for pattern in patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                return float(match.group(1))

        # Default to total area
        return self._extract_area(soup)

    def _extract_price(self, soup: BeautifulSoup) -> float:
        """Extract property price"""
        selectors = [
            ".property-price",
            ".listing-price",
            ".price",
            "[data-price]",
            ".detail-price",
            "[itemprop='price']"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Get price text
                if element.get("data-price"):
                    price_text = element.get("data-price")
                elif element.get("content"):
                    price_text = element.get("content")
                else:
                    price_text = element.get_text(strip=True)

                # Extract numeric value
                # Remove currency symbols and thousands separators
                price_text = re.sub(r"[^\d.,]", "", price_text)
                price_text = price_text.replace(".", "").replace(",", ".")

                try:
                    return float(price_text)
                except ValueError:
                    continue

        return 0.0

    def _extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract property features"""
        features = []

        # Look for feature lists
        selectors = [
            ".property-features li",
            ".listing-features li",
            ".features-list li",
            ".amenities li",
            "[data-features] li"
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                for element in elements:
                    feature = element.get_text(strip=True)
                    if feature and feature not in features:
                        features.append(feature)

        return features

    def _extract_amenities(self, soup: BeautifulSoup) -> List[str]:
        """Extract building amenities"""
        amenities = []

        # Common amenities to look for
        amenity_keywords = [
            "piscina", "pileta", "gym", "gimnasio", "seguridad",
            "portero", "cochera", "garage", "parrilla", "quincho",
            "sum", "lavadero", "balcón", "terraza", "jardín"
        ]

        # Get all features and filter amenities
        all_features = self._extract_features(soup)

        for feature in all_features:
            feature_lower = feature.lower()
            for keyword in amenity_keywords:
                if keyword in feature_lower:
                    amenities.append(feature)
                    break

        return amenities

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract property images"""
        images = []

        # Look for image galleries
        selectors = [
            ".property-images img",
            ".listing-images img",
            ".gallery img",
            ".carousel img",
            "[data-gallery] img",
            ".detail-images img"
        ]

        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                for element in elements:
                    src = element.get("src") or element.get("data-src")
                    if src:
                        # Make URL absolute
                        if not src.startswith("http"):
                            src = urljoin(self.BASE_URL, src)

                        # Skip placeholder images
                        if "placeholder" not in src.lower():
                            images.append(src)

        # Remove duplicates while preserving order
        seen = set()
        unique_images = []
        for img in images:
            if img not in seen:
                seen.add(img)
                unique_images.append(img)

        return unique_images[:20]  # Limit to 20 images

    def _extract_video_url(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract property video URL if available"""
        # Look for video elements
        video_selectors = [
            "iframe[src*='youtube']",
            "iframe[src*='vimeo']",
            "video source",
            ".property-video iframe"
        ]

        for selector in video_selectors:
            element = soup.select_one(selector)
            if element:
                return element.get("src", "")

        return None

    def _extract_listing_type(self, soup: BeautifulSoup) -> str:
        """Extract listing type (sale/rent)"""
        # Look for operation type
        patterns = [
            r"(venta|alquiler|rent|sale)",
        ]

        selectors = [
            ".operation-type",
            ".listing-operation",
            ".transaction-type"
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(strip=True).lower()
                if "alquiler" in text or "rent" in text:
                    return "rent"
                elif "venta" in text or "sale" in text:
                    return "sale"

        # Check in title or URL
        title = self._extract_title(soup).lower()
        if "alquiler" in title:
            return "rent"
        elif "venta" in title:
            return "sale"

        return "sale"  # Default

    def _extract_latitude(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract latitude if available"""
        # Look for map data
        patterns = [
            r"lat[itude]*['\"]?\s*[:=]\s*(-?\d+\.\d+)",
            r"data-lat[itude]*=['\"](-?\d+\.\d+)",
        ]

        html_str = str(soup)
        for pattern in patterns:
            match = re.search(pattern, html_str, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None

    def _extract_longitude(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract longitude if available"""
        patterns = [
            r"lng|lon[gitude]*['\"]?\s*[:=]\s*(-?\d+\.\d+)",
            r"data-(?:lng|lon)[gitude]*=['\"](-?\d+\.\d+)",
        ]

        html_str = str(soup)
        for pattern in patterns:
            match = re.search(pattern, html_str, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    pass

        return None
