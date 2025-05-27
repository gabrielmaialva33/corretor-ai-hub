"""
Tests for REMAX Argentina scraper
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.scrapers.remax_scraper import RemaxArgentinaScraper
from src.database.models import PropertyType, PropertyStatus


class TestRemaxScraper:
    """Test REMAX scraper functionality"""
    
    @pytest.fixture
    def scraper(self):
        """Create scraper instance"""
        return RemaxArgentinaScraper("test_tenant_id")
    
    @pytest.fixture
    def mock_html_response(self):
        """Mock HTML response for property page"""
        return """
        <html>
            <head>
                <title>Casa en venta en Palermo - REMAX</title>
                <meta property="og:title" content="Hermosa casa en Palermo">
            </head>
            <body>
                <h1 class="property-title">Casa moderna en Palermo</h1>
                <div class="property-price">USD 350,000</div>
                <div class="property-address">Av. Santa Fe 1234, Palermo</div>
                <div class="property-type">Casa</div>
                <div class="detail-specs">
                    <div class="bedrooms">3 dormitorios</div>
                    <div class="bathrooms">2 baños</div>
                    <div class="area">150 m²</div>
                </div>
                <div class="property-description">
                    Hermosa casa de 3 dormitorios en el corazón de Palermo.
                    Amplios espacios, excelente ubicación.
                </div>
                <div class="property-features">
                    <li>Jardín</li>
                    <li>Cochera</li>
                    <li>Parrilla</li>
                </div>
                <div class="gallery">
                    <img src="/images/property1.jpg" />
                    <img src="/images/property2.jpg" />
                </div>
            </body>
        </html>
        """
    
    @pytest.fixture
    def mock_search_response(self):
        """Mock HTML response for search results"""
        return """
        <html>
            <body>
                <div class="property-card">
                    <a href="/propiedades/casa-palermo-123">
                        <h3 class="property-title">Casa en Palermo</h3>
                        <div class="property-price">USD 350,000</div>
                        <div class="property-location">Palermo, Buenos Aires</div>
                    </a>
                </div>
                <div class="property-card">
                    <a href="/propiedades/depto-recoleta-456">
                        <h3 class="property-title">Departamento en Recoleta</h3>
                        <div class="property-price">USD 200,000</div>
                        <div class="property-location">Recoleta, Buenos Aires</div>
                    </a>
                </div>
            </body>
        </html>
        """
    
    def test_property_type_mapping(self, scraper):
        """Test property type mapping"""
        assert scraper.PROPERTY_TYPE_MAP["casa"] == PropertyType.HOUSE
        assert scraper.PROPERTY_TYPE_MAP["departamento"] == PropertyType.APARTMENT
        assert scraper.PROPERTY_TYPE_MAP["terreno"] == PropertyType.LAND
    
    def test_extract_property_id(self, scraper):
        """Test property ID extraction from URL"""
        # Test different URL patterns
        assert scraper._extract_property_id("https://remax.com.ar/listing/12345") == "remax_12345"
        assert scraper._extract_property_id("https://remax.com.ar/propiedades/casa-123") == "remax_casa-123"
        assert "remax_" in scraper._extract_property_id("https://remax.com.ar/unknown-pattern")
    
    @pytest.mark.asyncio
    async def test_scrape_property(self, scraper, mock_html_response):
        """Test scraping a single property"""
        with patch('httpx.AsyncClient') as mock_client_class:
            # Mock HTTP response
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.text = mock_html_response
            mock_response.raise_for_status = MagicMock()
            
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock save_property
            with patch.object(scraper, 'save_property', return_value={"id": "123"}):
                # Scrape property
                result = await scraper.scrape_property("https://remax.com.ar/propiedades/casa-123")
                
                assert result is not None
                assert result["title"] == "Casa moderna en Palermo"
                assert result["price"] == 350000.0
                assert result["bedrooms"] == 3
                assert result["bathrooms"] == 2
                assert result["area"] == 150.0
                assert result["property_type"] == PropertyType.HOUSE
                assert "Palermo" in result["address"]
                assert len(result["features"]) == 3
                assert "Jardín" in result["features"]
    
    @pytest.mark.asyncio
    async def test_search_properties(self, scraper, mock_search_response, mock_html_response):
        """Test searching properties"""
        with patch('httpx.AsyncClient') as mock_client_class:
            # Mock HTTP client
            mock_client = AsyncMock()
            
            # Mock search response
            search_response = AsyncMock()
            search_response.text = mock_search_response
            search_response.raise_for_status = MagicMock()
            
            # Mock property detail response
            detail_response = AsyncMock()
            detail_response.text = mock_html_response
            detail_response.raise_for_status = MagicMock()
            
            # Configure mock to return different responses
            mock_client.get.side_effect = [search_response, detail_response, detail_response]
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Search properties
            filters = {
                "operation": "venta",
                "property_type": "casa",
                "location": "Palermo",
                "bedrooms": 3,
                "min_price": 200000,
                "max_price": 500000
            }
            
            results = await scraper.search_properties(filters, limit=2)
            
            # Verify search was called with correct params
            mock_client.get.assert_any_call(
                scraper.SEARCH_URL,
                params={
                    "operacion": "venta",
                    "tipo": "casa",
                    "ubicacion": "Palermo",
                    "dormitorios": 3,
                    "precio_desde": 200000,
                    "precio_hasta": 500000,
                    "pagina": 1
                },
                headers=scraper._get_headers(),
                timeout=30.0
            )
    
    def test_build_search_params(self, scraper):
        """Test building search parameters"""
        filters = {
            "operation": "alquiler",
            "property_type": "departamento",
            "location": "Recoleta",
            "bedrooms": 2,
            "min_price": 1000,
            "max_price": 2000,
            "min_area": 50,
            "max_area": 100
        }
        
        params = scraper._build_search_params(filters)
        
        assert params["operacion"] == "alquiler"
        assert params["tipo"] == "departamento"
        assert params["ubicacion"] == "Recoleta"
        assert params["dormitorios"] == 2
        assert params["precio_desde"] == 1000
        assert params["precio_hasta"] == 2000
        assert params["superficie_desde"] == 50
        assert params["superficie_hasta"] == 100
    
    def test_extract_bedrooms(self, scraper):
        """Test bedroom extraction"""
        from bs4 import BeautifulSoup
        
        # Test different formats
        html1 = '<div class="bedrooms">3 dormitorios</div>'
        soup1 = BeautifulSoup(html1, 'html.parser')
        assert scraper._extract_bedrooms(soup1) == 3
        
        html2 = '<div>4 habitaciones</div>'
        soup2 = BeautifulSoup(html2, 'html.parser')
        assert scraper._extract_bedrooms(soup2) == 4
        
        html3 = '<div>2 amb.</div>'
        soup3 = BeautifulSoup(html3, 'html.parser')
        assert scraper._extract_bedrooms(soup3) == 1  # 2 ambientes = 1 dormitorio
    
    def test_extract_price(self, scraper):
        """Test price extraction"""
        from bs4 import BeautifulSoup
        
        # Test different formats
        html1 = '<div class="price">USD 250,000</div>'
        soup1 = BeautifulSoup(html1, 'html.parser')
        assert scraper._extract_price(soup1) == 250000.0
        
        html2 = '<div class="price">$ 1.500.000</div>'
        soup2 = BeautifulSoup(html2, 'html.parser')
        assert scraper._extract_price(soup2) == 1500000.0
        
        html3 = '<div data-price="300000">Precio: consultar</div>'
        soup3 = BeautifulSoup(html3, 'html.parser')
        assert scraper._extract_price(soup3) == 300000.0
    
    def test_extract_features(self, scraper):
        """Test feature extraction"""
        from bs4 import BeautifulSoup
        
        html = """
        <div class="property-features">
            <li>Piscina</li>
            <li>Gimnasio</li>
            <li>Seguridad 24hs</li>
            <li>Cochera doble</li>
        </div>
        """
        soup = BeautifulSoup(html, 'html.parser')
        features = scraper._extract_features(soup)
        
        assert len(features) == 4
        assert "Piscina" in features
        assert "Gimnasio" in features
        assert "Seguridad 24hs" in features
        assert "Cochera doble" in features
    
    def test_format_price(self, scraper):
        """Test price formatting"""
        from src.services.property_matcher import PropertyMatcher
        matcher = PropertyMatcher()
        
        assert matcher._format_price(1500000) == "R$ 1.5M"
        assert matcher._format_price(250000) == "R$ 250K"
        assert matcher._format_price(999) == "R$ 999"