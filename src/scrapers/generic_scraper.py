"""
Generic scraper implementation for real estate websites
This can be customized for specific real estate websites
"""
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse

import structlog
from bs4 import BeautifulSoup

from src.scrapers.base_scraper import BaseScraper

logger = structlog.get_logger()


class GenericRealEstateScraper(BaseScraper):
    """
    Generic scraper that can be configured for different real estate websites
    """

    def __init__(self, tenant_id: str, config: Dict[str, Any]):
        super().__init__(tenant_id)
        self.config = config
        self.base_url = config.get("base_url", "")
        self.selectors = config.get("selectors", {})

    def get_base_url(self) -> str:
        """Get the base URL for the scraper"""
        return self.base_url

    async def get_listing_urls(self, page: int = 1) -> List[str]:
        """Get property listing URLs from a page"""
        listing_urls = []

        try:
            # Build listing page URL
            listing_url = self.config.get("listing_url_pattern", "").format(page=page)
            if not listing_url.startswith("http"):
                listing_url = urljoin(self.base_url, listing_url)

            # Fetch page content
            content = await self.fetch_with_retry(
                listing_url,
                use_browser=self.config.get("use_browser", False)
            )

            if not content:
                return listing_urls

            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')

            # Find property links
            link_selector = self.selectors.get("listing_links")
            if link_selector:
                links = soup.select(link_selector)

                for link in links:
                    href = link.get('href')
                    if href:
                        # Make absolute URL
                        absolute_url = urljoin(self.base_url, href)
                        listing_urls.append(absolute_url)

            logger.info(f"Found {len(listing_urls)} properties on page {page}")

        except Exception as e:
            logger.error(f"Error getting listing URLs from page {page}", error=str(e))

        return listing_urls

    async def scrape_property(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single property"""
        try:
            # Fetch property page
            content = await self.fetch_with_retry(
                url,
                use_browser=self.config.get("use_browser", False)
            )

            if not content:
                return None

            # Parse HTML
            soup = BeautifulSoup(content, 'html.parser')

            # Extract data using selectors
            property_data = {
                "source_url": url,
                "source_id": self._extract_source_id(url)
            }

            # Title
            title_elem = soup.select_one(self.selectors.get("title", ""))
            if title_elem:
                property_data["title"] = self.extract_text(title_elem)

            # Description
            desc_elem = soup.select_one(self.selectors.get("description", ""))
            if desc_elem:
                property_data["description"] = self.extract_text(desc_elem)

            # Price
            price_elem = soup.select_one(self.selectors.get("price", ""))
            if price_elem:
                price_text = self.extract_text(price_elem)
                property_data["price"] = self.parse_price(price_text)

            # Property type
            type_elem = soup.select_one(self.selectors.get("property_type", ""))
            if type_elem:
                type_text = self.extract_text(type_elem)
                property_data["property_type"] = self.normalize_property_type(type_text)

            # Transaction type
            trans_elem = soup.select_one(self.selectors.get("transaction_type", ""))
            if trans_elem:
                trans_text = self.extract_text(trans_elem)
                property_data["transaction_type"] = self.normalize_transaction_type(trans_text)
            else:
                # Try to infer from URL or title
                if "venda" in url.lower() or "sale" in url.lower():
                    property_data["transaction_type"] = "sale"
                elif "aluguel" in url.lower() or "rent" in url.lower():
                    property_data["transaction_type"] = "rent"

            # Location
            location_data = self._extract_location(soup)
            property_data.update(location_data)

            # Characteristics
            characteristics = self._extract_characteristics(soup)
            property_data.update(characteristics)

            # Features
            features = self._extract_features(soup)
            property_data["features"] = features

            # Images
            images = self._extract_images(soup)
            property_data["images"] = images

            # Additional fees
            fees = self._extract_fees(soup)
            property_data.update(fees)

            # Validate required fields
            if not property_data.get("title") or not property_data.get("price"):
                logger.warning(f"Missing required fields for property: {url}")
                return None

            return property_data

        except Exception as e:
            logger.error(f"Error scraping property: {url}", error=str(e))
            return None

    def parse_price(self, price_text: str) -> Optional[float]:
        """Parse price from text"""
        if not price_text:
            return None

        # Remove currency symbols and text
        price_text = re.sub(r'[R$\s]', '', price_text)
        price_text = price_text.replace(".", "").replace(",", ".")

        # Extract numeric value
        match = re.search(r'[\d.]+', price_text)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass

        return None

    def _extract_source_id(self, url: str) -> str:
        """Extract unique ID from URL"""
        # Try to extract ID from URL patterns
        patterns = [
            r'/imovel/(\d+)',
            r'/id/(\d+)',
            r'/codigo/(\w+)',
            r'/ref/(\w+)',
            r'[?&]id=(\w+)',
            r'/(\d+)/?$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # Fallback: use last part of URL path
        path = urlparse(url).path.rstrip('/')
        parts = path.split('/')
        return parts[-1] if parts else url

    def _extract_location(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract location information"""
        location_data = {}

        # Address
        addr_elem = soup.select_one(self.selectors.get("address", ""))
        if addr_elem:
            location_data["address"] = self.extract_text(addr_elem)

        # Neighborhood
        neigh_elem = soup.select_one(self.selectors.get("neighborhood", ""))
        if neigh_elem:
            location_data["neighborhood"] = self.extract_text(neigh_elem)

        # City
        city_elem = soup.select_one(self.selectors.get("city", ""))
        if city_elem:
            location_data["city"] = self.extract_text(city_elem)

        # State
        state_elem = soup.select_one(self.selectors.get("state", ""))
        if state_elem:
            location_data["state"] = self.extract_text(state_elem)

        # Try to parse from a combined location string
        if not location_data.get("city") and self.selectors.get("location"):
            loc_elem = soup.select_one(self.selectors["location"])
            if loc_elem:
                location_text = self.extract_text(loc_elem)
                # Try to parse "Neighborhood, City - State" format
                parts = re.split(r'[,\-]', location_text)
                if len(parts) >= 2:
                    location_data["neighborhood"] = parts[0].strip()
                    location_data["city"] = parts[1].strip()
                    if len(parts) >= 3:
                        location_data["state"] = parts[2].strip()

        return location_data

    def _extract_characteristics(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract property characteristics"""
        characteristics = {}

        # Bedrooms
        bed_elem = soup.select_one(self.selectors.get("bedrooms", ""))
        if bed_elem:
            bed_text = self.extract_text(bed_elem)
            characteristics["bedrooms"] = int(self.extract_number(bed_text) or 0)

        # Bathrooms
        bath_elem = soup.select_one(self.selectors.get("bathrooms", ""))
        if bath_elem:
            bath_text = self.extract_text(bath_elem)
            characteristics["bathrooms"] = int(self.extract_number(bath_text) or 0)

        # Parking spaces
        park_elem = soup.select_one(self.selectors.get("parking", ""))
        if park_elem:
            park_text = self.extract_text(park_elem)
            characteristics["parking_spaces"] = int(self.extract_number(park_text) or 0)

        # Area
        area_elem = soup.select_one(self.selectors.get("area", ""))
        if area_elem:
            area_text = self.extract_text(area_elem)
            characteristics["total_area"] = self.extract_number(area_text)

        # Built area
        built_elem = soup.select_one(self.selectors.get("built_area", ""))
        if built_elem:
            built_text = self.extract_text(built_elem)
            characteristics["built_area"] = self.extract_number(built_text)

        # Try to extract from a characteristics list
        if self.selectors.get("characteristics_list"):
            char_elems = soup.select(self.selectors["characteristics_list"])
            for elem in char_elems:
                text = self.extract_text(elem).lower()

                # Pattern matching for characteristics
                patterns = {
                    "bedrooms": r'(\d+)\s*(?:quarto|dormit|suite)',
                    "bathrooms": r'(\d+)\s*(?:banheir|wc|lavabo)',
                    "parking_spaces": r'(\d+)\s*(?:vaga|garagem)',
                    "total_area": r'(\d+(?:\.\d+)?)\s*m[²2]?\s*(?:total|área)?',
                    "built_area": r'(\d+(?:\.\d+)?)\s*m[²2]?\s*(?:construíd|útil)'
                }

                for key, pattern in patterns.items():
                    if key not in characteristics:
                        match = re.search(pattern, text)
                        if match:
                            value = float(match.group(1))
                            characteristics[key] = int(value) if key != "total_area" and key != "built_area" else value

        return characteristics

    def _extract_features(self, soup: BeautifulSoup) -> List[str]:
        """Extract property features"""
        features = []

        # Features list
        if self.selectors.get("features_list"):
            feature_elems = soup.select(self.selectors["features_list"])
            for elem in feature_elems:
                feature_text = self.extract_text(elem)
                if feature_text:
                    features.append(feature_text.lower())

        # Features container
        if self.selectors.get("features_container"):
            container = soup.select_one(self.selectors["features_container"])
            if container:
                feature_text = self.extract_text(container)
                extracted = self.extract_features(feature_text)
                features.extend(extracted)

        # Deduplicate and normalize
        normalized_features = []
        seen = set()

        for feature in features:
            normalized = self._normalize_feature(feature)
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_features.append(normalized)

        return normalized_features

    def _normalize_feature(self, feature: str) -> Optional[str]:
        """Normalize a feature string"""
        feature = feature.lower().strip()

        # Skip empty or very short features
        if len(feature) < 3:
            return None

        # Remove common words
        skip_words = ["com", "de", "para", "em", "e", "ou", "área"]
        words = feature.split()
        if len(words) == 1 and words[0] in skip_words:
            return None

        return feature

    def _extract_images(self, soup: BeautifulSoup) -> List[str]:
        """Extract property images"""
        images = []

        # Image gallery
        if self.selectors.get("images"):
            img_elems = soup.select(self.selectors["images"])
            for elem in img_elems:
                # Check for different image attributes
                img_url = elem.get('src') or elem.get('data-src') or elem.get('data-lazy')
                if img_url:
                    # Make absolute URL
                    absolute_url = urljoin(self.base_url, img_url)
                    images.append(absolute_url)

        # Limit number of images
        return images[:20]

    def _extract_fees(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract additional fees"""
        fees = {}

        # Condo fee
        if self.selectors.get("condo_fee"):
            fee_elem = soup.select_one(self.selectors["condo_fee"])
            if fee_elem:
                fee_text = self.extract_text(fee_elem)
                fees["condo_fee"] = self.parse_price(fee_text)

        # Property tax (IPTU)
        if self.selectors.get("property_tax"):
            tax_elem = soup.select_one(self.selectors["property_tax"])
            if tax_elem:
                tax_text = self.extract_text(tax_elem)
                fees["property_tax"] = self.parse_price(tax_text)

        return fees


# Example configuration for a generic real estate website
EXAMPLE_CONFIG = {
    "base_url": "https://www.example-imoveis.com.br",
    "listing_url_pattern": "/imoveis/venda?page={page}",
    "use_browser": True,  # Use browser for JavaScript-heavy sites
    "selectors": {
        "listing_links": "a.property-card-link",
        "title": "h1.property-title",
        "description": "div.property-description",
        "price": "span.property-price",
        "property_type": "span.property-type",
        "transaction_type": "span.transaction-type",
        "address": "span.property-address",
        "neighborhood": "span.property-neighborhood",
        "city": "span.property-city",
        "state": "span.property-state",
        "location": "div.property-location",
        "bedrooms": "span.bedrooms-count",
        "bathrooms": "span.bathrooms-count",
        "parking": "span.parking-count",
        "area": "span.property-area",
        "built_area": "span.built-area",
        "characteristics_list": "li.property-feature",
        "features_list": "ul.amenities li",
        "features_container": "div.property-amenities",
        "images": "img.property-image",
        "condo_fee": "span.condo-fee",
        "property_tax": "span.property-tax"
    }
}
