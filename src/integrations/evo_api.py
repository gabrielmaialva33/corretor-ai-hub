"""
EVO API Integration for WhatsApp Business
"""
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx
import structlog

from src.core.config import get_settings
from src.core.exceptions import ExternalAPIError

logger = structlog.get_logger()
settings = get_settings()


class EvoAPIClient:
    """
    Client for interacting with EVO API
    """

    def __init__(self, instance_key: Optional[str] = None):
        self.base_url = settings.EVO_API_BASE_URL
        self.api_key = settings.EVO_API_KEY
        self.instance_key = instance_key
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "apikey": self.api_key,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_instance_url(self, endpoint: str) -> str:
        """Get URL with instance key"""
        if not self.instance_key:
            raise ValueError("Instance key is required for this operation")
        return f"/instance/{self.instance_key}/{endpoint}"

    async def _request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to EVO API"""
        try:
            response = await self.client.request(
                method=method,
                url=endpoint,
                json=data,
                params=params
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "EVO API HTTP error",
                status_code=e.response.status_code,
                response_text=e.response.text,
                endpoint=endpoint
            )
            raise ExternalAPIError(
                f"EVO API error: {e.response.status_code}",
                details={"response": e.response.text}
            )
        except Exception as e:
            logger.error("EVO API request failed", error=str(e), endpoint=endpoint)
            raise ExternalAPIError(f"EVO API request failed: {str(e)}")

    # Instance Management
    async def create_instance(
            self,
            instance_name: str,
            phone_number: str,
            webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new WhatsApp instance"""
        data = {
            "instanceName": instance_name,
            "phoneNumber": phone_number,
            "webhook": {
                "url": webhook_url or settings.EVO_WEBHOOK_URL,
                "enabled": True,
                "events": [
                    "messages.upsert",
                    "messages.update",
                    "connection.update",
                    "chats.update",
                    "presence.update"
                ]
            }
        }
        return await self._request("POST", "/instance/create", data)

    async def get_instance_info(self) -> Dict[str, Any]:
        """Get instance information"""
        return await self._request("GET", self._get_instance_url("info"))

    async def delete_instance(self) -> Dict[str, Any]:
        """Delete WhatsApp instance"""
        return await self._request("DELETE", self._get_instance_url("delete"))

    async def restart_instance(self) -> Dict[str, Any]:
        """Restart WhatsApp instance"""
        return await self._request("POST", self._get_instance_url("restart"))

    # Connection Management
    async def get_qr_code(self) -> Dict[str, Any]:
        """Get QR code for connecting WhatsApp"""
        return await self._request("GET", self._get_instance_url("qrcode"))

    async def get_connection_status(self) -> Dict[str, Any]:
        """Get WhatsApp connection status"""
        return await self._request("GET", self._get_instance_url("status"))

    async def logout(self) -> Dict[str, Any]:
        """Logout from WhatsApp"""
        return await self._request("POST", self._get_instance_url("logout"))

    # Messaging
    async def send_text_message(
            self,
            to: str,
            message: str,
            quoted_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send text message"""
        data = {
            "to": to,
            "message": message
        }
        if quoted_message_id:
            data["quotedMessageId"] = quoted_message_id

        return await self._request(
            "POST",
            self._get_instance_url("messages/sendText"),
            data
        )

    async def send_media_message(
            self,
            to: str,
            media_type: str,  # image, video, audio, document
            media_url: str,
            caption: Optional[str] = None,
            filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send media message"""
        data = {
            "to": to,
            "mediaUrl": media_url
        }
        if caption:
            data["caption"] = caption
        if filename and media_type == "document":
            data["filename"] = filename

        endpoint_map = {
            "image": "messages/sendImage",
            "video": "messages/sendVideo",
            "audio": "messages/sendAudio",
            "document": "messages/sendDocument"
        }

        endpoint = endpoint_map.get(media_type)
        if not endpoint:
            raise ValueError(f"Invalid media type: {media_type}")

        return await self._request("POST", self._get_instance_url(endpoint), data)

    async def send_location(
            self,
            to: str,
            latitude: float,
            longitude: float,
            name: Optional[str] = None,
            address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send location message"""
        data = {
            "to": to,
            "latitude": latitude,
            "longitude": longitude
        }
        if name:
            data["name"] = name
        if address:
            data["address"] = address

        return await self._request(
            "POST",
            self._get_instance_url("messages/sendLocation"),
            data
        )

    async def send_contact(
            self,
            to: str,
            contact_name: str,
            contact_phone: str
    ) -> Dict[str, Any]:
        """Send contact message"""
        data = {
            "to": to,
            "contact": {
                "name": contact_name,
                "phone": contact_phone
            }
        }
        return await self._request(
            "POST",
            self._get_instance_url("messages/sendContact"),
            data
        )

    async def send_buttons(
            self,
            to: str,
            title: str,
            buttons: List[Dict[str, str]],
            description: Optional[str] = None,
            footer: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send button message"""
        data = {
            "to": to,
            "title": title,
            "buttons": buttons
        }
        if description:
            data["description"] = description
        if footer:
            data["footer"] = footer

        return await self._request(
            "POST",
            self._get_instance_url("messages/sendButtons"),
            data
        )

    async def send_list(
            self,
            to: str,
            title: str,
            button_text: str,
            sections: List[Dict[str, Any]],
            description: Optional[str] = None,
            footer: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send list message"""
        data = {
            "to": to,
            "title": title,
            "buttonText": button_text,
            "sections": sections
        }
        if description:
            data["description"] = description
        if footer:
            data["footer"] = footer

        return await self._request(
            "POST",
            self._get_instance_url("messages/sendList"),
            data
        )

    # Message Status
    async def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark message as read"""
        data = {"messageId": message_id}
        return await self._request(
            "POST",
            self._get_instance_url("messages/markAsRead"),
            data
        )

    async def send_typing(self, to: str, duration: int = 3000) -> Dict[str, Any]:
        """Send typing indicator"""
        data = {
            "to": to,
            "duration": duration
        }
        return await self._request(
            "POST",
            self._get_instance_url("messages/sendTyping"),
            data
        )

    # Chat Management
    async def get_chats(self, limit: int = 100) -> Dict[str, Any]:
        """Get chat list"""
        params = {"limit": limit}
        return await self._request(
            "GET",
            self._get_instance_url("chats"),
            params=params
        )

    async def get_messages(
            self,
            chat_id: str,
            limit: int = 50,
            offset: int = 0
    ) -> Dict[str, Any]:
        """Get messages from a chat"""
        params = {
            "chatId": chat_id,
            "limit": limit,
            "offset": offset
        }
        return await self._request(
            "GET",
            self._get_instance_url("messages"),
            params=params
        )

    async def delete_message(
            self,
            message_id: str,
            for_everyone: bool = False
    ) -> Dict[str, Any]:
        """Delete a message"""
        data = {
            "messageId": message_id,
            "forEveryone": for_everyone
        }
        return await self._request(
            "DELETE",
            self._get_instance_url("messages/delete"),
            data
        )

    # Webhook Management
    async def set_webhook(
            self,
            webhook_url: str,
            events: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Set webhook URL and events"""
        data = {
            "url": webhook_url,
            "enabled": True,
            "events": events or [
                "messages.upsert",
                "messages.update",
                "connection.update",
                "chats.update"
            ]
        }
        return await self._request(
            "POST",
            self._get_instance_url("webhook/set"),
            data
        )

    async def get_webhook_info(self) -> Dict[str, Any]:
        """Get webhook configuration"""
        return await self._request(
            "GET",
            self._get_instance_url("webhook/info")
        )

    # Profile Management
    async def get_profile_info(self, phone_number: str) -> Dict[str, Any]:
        """Get WhatsApp profile information"""
        params = {"phoneNumber": phone_number}
        return await self._request(
            "GET",
            self._get_instance_url("profile/info"),
            params=params
        )

    async def get_profile_picture(self, phone_number: str) -> Dict[str, Any]:
        """Get profile picture URL"""
        params = {"phoneNumber": phone_number}
        return await self._request(
            "GET",
            self._get_instance_url("profile/picture"),
            params=params
        )

    async def set_profile_name(self, name: str) -> Dict[str, Any]:
        """Set profile display name"""
        data = {"name": name}
        return await self._request(
            "POST",
            self._get_instance_url("profile/setName"),
            data
        )

    async def set_profile_status(self, status: str) -> Dict[str, Any]:
        """Set profile status"""
        data = {"status": status}
        return await self._request(
            "POST",
            self._get_instance_url("profile/setStatus"),
            data
        )


# Utility functions
def format_phone_number(phone: str) -> str:
    """
    Format phone number for WhatsApp
    Ensures it has country code and @s.whatsapp.net suffix
    """
    # Remove any non-numeric characters
    phone = "".join(filter(str.isdigit, phone))

    # Add Brazil country code if not present
    if not phone.startswith("55"):
        phone = "55" + phone

    # Add WhatsApp suffix
    if not phone.endswith("@s.whatsapp.net"):
        phone = phone + "@s.whatsapp.net"

    return phone


def parse_webhook_message(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse EVO API webhook message payload
    """
    try:
        message = payload.get("data", {}).get("message", {})

        return {
            "message_id": message.get("id"),
            "chat_id": message.get("from") or message.get("to"),
            "sender": message.get("from"),
            "timestamp": datetime.fromtimestamp(message.get("timestamp", 0)),
            "content": message.get("body") or message.get("caption"),
            "type": message.get("type", "text"),
            "media_url": message.get("mediaUrl"),
            "quoted_message": message.get("quotedMessage"),
            "is_from_me": message.get("fromMe", False),
            "raw_data": message
        }
    except Exception as e:
        logger.error("Failed to parse webhook message", error=str(e), payload=payload)
        return {}
