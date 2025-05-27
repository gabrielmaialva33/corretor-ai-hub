"""
Tests for media processing functionality
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.media_processor import MediaProcessor


class TestMediaProcessor:
    """Test media processing functionality"""
    
    @pytest.fixture
    def media_processor(self):
        """Create media processor instance"""
        with patch('src.services.media_processor.openai.AsyncOpenAI'):
            processor = MediaProcessor()
            processor.openai_client = AsyncMock()
            return processor
    
    @pytest.mark.asyncio
    async def test_process_audio_success(self, media_processor):
        """Test successful audio processing"""
        # Mock download
        with patch.object(media_processor, '_download_media') as mock_download:
            mock_download.return_value = b"fake_audio_data"
            
            # Mock OpenAI transcription
            mock_transcription = MagicMock()
            mock_transcription.text = "Olá, gostaria de saber sobre o apartamento"
            mock_transcription.language = "portuguese"
            mock_transcription.duration = 5.2
            
            media_processor.openai_client.audio.transcriptions.create.return_value = mock_transcription
            
            # Process audio
            result = await media_processor.process_audio(
                "https://example.com/audio.ogg",
                "ogg"
            )
            
            assert result["success"] is True
            assert result["transcription"] == "Olá, gostaria de saber sobre o apartamento"
            assert result["language"] == "portuguese"
            assert result["duration"] == 5.2
    
    @pytest.mark.asyncio
    async def test_process_audio_error(self, media_processor):
        """Test audio processing with error"""
        # Mock download failure
        with patch.object(media_processor, '_download_media') as mock_download:
            mock_download.side_effect = Exception("Download failed")
            
            result = await media_processor.process_audio(
                "https://example.com/audio.ogg",
                "ogg"
            )
            
            assert result["success"] is False
            assert "Download failed" in result["error"]
            assert result["transcription"] is None
    
    @pytest.mark.asyncio
    async def test_process_image_success(self, media_processor):
        """Test successful image processing"""
        # Mock download
        with patch.object(media_processor, '_download_media') as mock_download:
            mock_download.return_value = b"fake_image_data"
            
            # Mock Vision API response
            with patch.object(media_processor, '_analyze_image_with_vision') as mock_analyze:
                mock_analyze.return_value = {
                    "extracted_text": "Casa en venta - $200,000",
                    "content_analysis": "Una casa de dos pisos con jardín",
                    "property_details": {
                        "price": 200000,
                        "rooms": 3
                    }
                }
                
                # Mock PIL Image
                with patch('src.services.media_processor.Image.open') as mock_image:
                    mock_img = MagicMock()
                    mock_img.format = "JPEG"
                    mock_img.size = (1024, 768)
                    mock_img.mode = "RGB"
                    mock_image.return_value = mock_img
                    
                    # Process image
                    result = await media_processor.process_image(
                        "https://example.com/property.jpg",
                        extract_text=True,
                        analyze_content=True
                    )
                    
                    assert result["success"] is True
                    assert result["extracted_text"] == "Casa en venta - $200,000"
                    assert result["content_analysis"] == "Una casa de dos pisos con jardín"
                    assert result["property_details"]["price"] == 200000
                    assert result["metadata"]["format"] == "JPEG"
    
    @pytest.mark.asyncio
    async def test_analyze_image_with_vision(self, media_processor):
        """Test Vision API analysis"""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        Extracted text: Casa en venta $150,000. 3 dormitorios, 2 baños.
        
        Description: This is a modern two-story house with a garden.
        """
        
        media_processor.openai_client.chat.completions.create.return_value = mock_response
        
        result = await media_processor._analyze_image_with_vision(
            "base64_image_data",
            extract_text=True,
            analyze_content=True
        )
        
        assert "Casa en venta" in result.get("extracted_text", "")
        assert "modern two-story house" in result.get("content_analysis", "")
    
    def test_extract_property_details(self, media_processor):
        """Test property details extraction"""
        content = """
        Beautiful house for sale!
        Price: $250,000
        3 dormitorios, 2 baños
        Surface: 150 m²
        Located on Avenida Libertador 1234
        """
        
        details = media_processor._extract_property_details(content)
        
        assert details is not None
        assert details.get("price") == 250000
        assert details.get("rooms") == 3
        assert details.get("area") == 150
        assert "Avenida Libertador" in details.get("address", "")
    
    @pytest.mark.asyncio
    async def test_download_media(self, media_processor):
        """Test media download"""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.content = b"media_content"
            mock_response.raise_for_status = MagicMock()
            
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            content = await media_processor._download_media("https://example.com/media.jpg")
            
            assert content == b"media_content"
            mock_client.get.assert_called_once()
    
    def test_extract_section(self, media_processor):
        """Test section extraction from text"""
        content = """
        Text extraction:
        This is the extracted text from the image.
        
        Description:
        This is the description of the image content.
        """
        
        text_section = media_processor._extract_section(content, "text", "extraction")
        assert "extracted text from the image" in text_section
        
        desc_section = media_processor._extract_section(content, "description")
        assert "description of the image content" in desc_section