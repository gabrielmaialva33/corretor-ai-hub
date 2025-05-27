"""
Media processing service for audio and image messages
"""
import base64
import io
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
import openai
import structlog
from PIL import Image

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class MediaProcessor:
    """
    Process media files from WhatsApp messages
    """

    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def process_audio(
            self,
            audio_url: str,
            audio_format: str = "ogg"
    ) -> Dict[str, Any]:
        """
        Process audio message and return transcription
        
        Args:
            audio_url: URL of the audio file
            audio_format: Audio format (ogg, mp3, etc)
            
        Returns:
            Dict with transcription and metadata
        """
        try:
            # Download audio file
            audio_data = await self._download_media(audio_url)

            # Convert audio if needed (WhatsApp uses opus codec in ogg container)
            if audio_format == "ogg" or audio_format == "opus":
                # OpenAI Whisper supports ogg/opus directly
                audio_file = io.BytesIO(audio_data)
                audio_file.name = "audio.ogg"
            else:
                audio_file = io.BytesIO(audio_data)
                audio_file.name = f"audio.{audio_format}"

            # Transcribe using Whisper
            transcription = await self.openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="pt",  # Portuguese for Brazil/Argentina
                response_format="verbose_json"
            )

            return {
                "success": True,
                "transcription": transcription.text,
                "language": transcription.language,
                "duration": transcription.duration,
                "segments": transcription.segments if hasattr(transcription, 'segments') else [],
                "processed_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error("Error processing audio", error=str(e), audio_url=audio_url)
            return {
                "success": False,
                "error": str(e),
                "transcription": None
            }

    async def process_image(
            self,
            image_url: str,
            extract_text: bool = True,
            analyze_content: bool = True
    ) -> Dict[str, Any]:
        """
        Process image message and extract information
        
        Args:
            image_url: URL of the image file
            extract_text: Whether to extract text from image (OCR)
            analyze_content: Whether to analyze image content
            
        Returns:
            Dict with extracted information
        """
        try:
            # Download image
            image_data = await self._download_media(image_url)

            # Convert to base64 for Vision API
            base64_image = base64.b64encode(image_data).decode('utf-8')

            results = {
                "success": True,
                "image_url": image_url,
                "processed_at": datetime.utcnow().isoformat()
            }

            # Analyze image content using GPT-4 Vision
            if analyze_content or extract_text:
                analysis = await self._analyze_image_with_vision(
                    base64_image,
                    extract_text=extract_text,
                    analyze_content=analyze_content
                )
                results.update(analysis)

            # Extract image metadata
            try:
                image = Image.open(io.BytesIO(image_data))
                results["metadata"] = {
                    "format": image.format,
                    "size": image.size,
                    "mode": image.mode
                }
            except Exception as e:
                logger.warning("Could not extract image metadata", error=str(e))

            return results

        except Exception as e:
            logger.error("Error processing image", error=str(e), image_url=image_url)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": None,
                "content_analysis": None
            }

    async def _download_media(self, media_url: str) -> bytes:
        """
        Download media file from URL
        
        Args:
            media_url: URL of the media file
            
        Returns:
            Media file content as bytes
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                media_url,
                headers={
                    "User-Agent": "WhatsApp/2.0",
                    "Accept": "*/*"
                },
                timeout=60.0
            )
            response.raise_for_status()
            return response.content

    async def _analyze_image_with_vision(
            self,
            base64_image: str,
            extract_text: bool = True,
            analyze_content: bool = True
    ) -> Dict[str, Any]:
        """
        Analyze image using GPT-4 Vision API
        
        Args:
            base64_image: Base64 encoded image
            extract_text: Whether to extract text
            analyze_content: Whether to analyze content
            
        Returns:
            Analysis results
        """
        try:
            # Build prompt based on requirements
            prompts = []

            if extract_text:
                prompts.append(
                    "Extract any text visible in this image, including property details, "
                    "addresses, prices, or contact information."
                )

            if analyze_content:
                prompts.append(
                    "Describe what you see in this image. If it's a property photo, "
                    "describe the property type, features, condition, and any notable details."
                )

            # Combine prompts
            full_prompt = " ".join(prompts)

            # Call Vision API
            response = await self.openai_client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": full_prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000
            )

            content = response.choices[0].message.content

            # Parse response to separate text extraction and content analysis
            results = {}

            if extract_text:
                # Extract text portion from response
                text_section = self._extract_section(content, "text", "extracted text")
                results["extracted_text"] = text_section

            if analyze_content:
                # Extract analysis portion
                analysis_section = self._extract_section(content, "description", "analysis")
                results["content_analysis"] = analysis_section

            # Try to extract specific property details if detected
            property_details = self._extract_property_details(content)
            if property_details:
                results["property_details"] = property_details

            return results

        except Exception as e:
            logger.error("Error analyzing image with Vision API", error=str(e))
            return {
                "extracted_text": None,
                "content_analysis": None,
                "error": str(e)
            }

    def _extract_section(self, content: str, *keywords: str) -> Optional[str]:
        """
        Extract a section from the response based on keywords
        
        Args:
            content: Full response content
            keywords: Keywords to search for
            
        Returns:
            Extracted section or full content if not found
        """
        content_lower = content.lower()

        # Try to find section markers
        for keyword in keywords:
            if keyword in content_lower:
                # Find the section after the keyword
                start_idx = content_lower.find(keyword)
                # Look for next section or end
                end_markers = ["\n\n", "description:", "analysis:", "property details:"]
                end_idx = len(content)

                for marker in end_markers:
                    marker_idx = content_lower.find(marker, start_idx + len(keyword))
                    if marker_idx > 0 and marker_idx < end_idx:
                        end_idx = marker_idx

                return content[start_idx:end_idx].strip()

        # If no sections found, return full content
        return content

    def _extract_property_details(self, content: str) -> Optional[Dict[str, Any]]:
        """
        Extract specific property details from content
        
        Args:
            content: Text content to analyze
            
        Returns:
            Property details if found
        """
        details = {}

        # Price patterns
        price_patterns = [
            r"\$\s*([\d,]+)",
            r"USD\s*([\d,]+)",
            r"ARS\s*([\d,]+)",
            r"precio:?\s*\$?\s*([\d,]+)"
        ]

        for pattern in price_patterns:
            import re
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(",", "")
                try:
                    details["price"] = float(price_str)
                    break
                except ValueError:
                    pass

        # Room patterns
        room_patterns = [
            r"(\d+)\s*(?:dormitorio|habitaci[oó]n|cuarto|bedroom)",
            r"(\d+)\s*(?:ambiente|amb\.?)"
        ]

        for pattern in room_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                details["rooms"] = int(match.group(1))
                break

        # Area patterns
        area_patterns = [
            r"(\d+)\s*m[²2]",
            r"(\d+)\s*metros"
        ]

        for pattern in area_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                details["area"] = int(match.group(1))
                break

        # Address pattern - look for street names
        address_pattern = r"(?:calle|av\.|avenida|boulevard)\s+[\w\s]+"
        match = re.search(address_pattern, content, re.IGNORECASE)
        if match:
            details["address"] = match.group(0).strip()

        return details if details else None

    async def process_document(
            self,
            document_url: str,
            document_type: str = "pdf"
    ) -> Dict[str, Any]:
        """
        Process document (PDF, DOC, etc)
        
        Args:
            document_url: URL of the document
            document_type: Type of document
            
        Returns:
            Processed document information
        """
        # For now, just return basic info
        # Could be extended to extract text from PDFs, etc.
        return {
            "success": True,
            "document_url": document_url,
            "document_type": document_type,
            "processed_at": datetime.utcnow().isoformat(),
            "message": "Document processing not fully implemented yet"
        }
