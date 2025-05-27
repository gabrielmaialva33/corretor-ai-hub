"""
Chatwoot Integration for conversation management
"""
from typing import Optional, Dict, Any, List

import httpx
import structlog

from src.core.config import get_settings
from src.core.exceptions import ExternalAPIError

logger = structlog.get_logger()
settings = get_settings()


class ChatwootClient:
    """
    Client for interacting with Chatwoot API
    """

    def __init__(self, account_id: Optional[int] = None):
        self.base_url = settings.CHATWOOT_BASE_URL
        self.api_token = settings.CHATWOOT_API_ACCESS_TOKEN
        self.account_id = account_id or int(settings.CHATWOOT_ACCOUNT_ID)
        self.client = httpx.AsyncClient(
            base_url=f"{self.base_url}/api/v1",
            headers={
                "api_access_token": self.api_token,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def _request(
            self,
            method: str,
            endpoint: str,
            data: Optional[Dict[str, Any]] = None,
            params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Chatwoot API"""
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
                "Chatwoot API HTTP error",
                status_code=e.response.status_code,
                response_text=e.response.text,
                endpoint=endpoint
            )
            raise ExternalAPIError(
                f"Chatwoot API error: {e.response.status_code}",
                details={"response": e.response.text}
            )
        except Exception as e:
            logger.error("Chatwoot API request failed", error=str(e), endpoint=endpoint)
            raise ExternalAPIError(f"Chatwoot API request failed: {str(e)}")

    # Account Management
    async def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        return await self._request("GET", f"/accounts/{self.account_id}")

    # Inbox Management
    async def create_inbox(
            self,
            name: str,
            channel_type: str = "api",
            webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new inbox"""
        data = {
            "name": name,
            "channel": {
                "type": channel_type,
                "webhook_url": webhook_url or settings.CHATWOOT_WEBHOOK_URL
            }
        }
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/inboxes",
            data
        )

    async def get_inbox(self, inbox_id: int) -> Dict[str, Any]:
        """Get inbox details"""
        return await self._request(
            "GET",
            f"/accounts/{self.account_id}/inboxes/{inbox_id}"
        )

    async def list_inboxes(self) -> List[Dict[str, Any]]:
        """List all inboxes"""
        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/inboxes"
        )
        return response.get("payload", [])

    async def update_inbox(
            self,
            inbox_id: int,
            name: Optional[str] = None,
            enable_auto_assignment: Optional[bool] = None,
            greeting_enabled: Optional[bool] = None,
            greeting_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update inbox settings"""
        data = {}
        if name is not None:
            data["name"] = name
        if enable_auto_assignment is not None:
            data["enable_auto_assignment"] = enable_auto_assignment
        if greeting_enabled is not None:
            data["greeting_enabled"] = greeting_enabled
        if greeting_message is not None:
            data["greeting_message"] = greeting_message

        return await self._request(
            "PATCH",
            f"/accounts/{self.account_id}/inboxes/{inbox_id}",
            data
        )

    # Contact Management
    async def create_contact(
            self,
            name: Optional[str] = None,
            email: Optional[str] = None,
            phone_number: Optional[str] = None,
            identifier: Optional[str] = None,
            custom_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new contact"""
        data = {}
        if name:
            data["name"] = name
        if email:
            data["email"] = email
        if phone_number:
            data["phone_number"] = phone_number
        if identifier:
            data["identifier"] = identifier
        if custom_attributes:
            data["custom_attributes"] = custom_attributes

        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/contacts",
            data
        )

    async def get_contact(self, contact_id: int) -> Dict[str, Any]:
        """Get contact details"""
        return await self._request(
            "GET",
            f"/accounts/{self.account_id}/contacts/{contact_id}"
        )

    async def search_contacts(
            self,
            query: str,
            page: int = 1,
            sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """Search contacts"""
        params = {
            "q": query,
            "page": page,
            "sort_order": sort_order
        }
        return await self._request(
            "GET",
            f"/accounts/{self.account_id}/contacts/search",
            params=params
        )

    async def update_contact(
            self,
            contact_id: int,
            name: Optional[str] = None,
            email: Optional[str] = None,
            phone_number: Optional[str] = None,
            custom_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Update contact information"""
        data = {}
        if name is not None:
            data["name"] = name
        if email is not None:
            data["email"] = email
        if phone_number is not None:
            data["phone_number"] = phone_number
        if custom_attributes is not None:
            data["custom_attributes"] = custom_attributes

        return await self._request(
            "PUT",
            f"/accounts/{self.account_id}/contacts/{contact_id}",
            data
        )

    # Conversation Management
    async def create_conversation(
            self,
            contact_id: int,
            inbox_id: int,
            status: str = "open",
            assignee_id: Optional[int] = None,
            custom_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a new conversation"""
        data = {
            "contact_id": contact_id,
            "inbox_id": inbox_id,
            "status": status
        }
        if assignee_id:
            data["assignee_id"] = assignee_id
        if custom_attributes:
            data["custom_attributes"] = custom_attributes

        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations",
            data
        )

    async def get_conversation(self, conversation_id: int) -> Dict[str, Any]:
        """Get conversation details"""
        return await self._request(
            "GET",
            f"/accounts/{self.account_id}/conversations/{conversation_id}"
        )

    async def list_conversations(
            self,
            inbox_id: Optional[int] = None,
            status: Optional[str] = None,
            assignee_id: Optional[int] = None,
            page: int = 1,
            labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """List conversations with filters"""
        params = {"page": page}
        if inbox_id:
            params["inbox_id"] = inbox_id
        if status:
            params["status"] = status
        if assignee_id:
            params["assignee_id"] = assignee_id
        if labels:
            params["labels"] = labels

        return await self._request(
            "GET",
            f"/accounts/{self.account_id}/conversations",
            params=params
        )

    async def update_conversation(
            self,
            conversation_id: int,
            status: Optional[str] = None,
            assignee_id: Optional[int] = None,
            team_id: Optional[int] = None,
            labels: Optional[List[str]] = None,
            custom_attributes: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Update conversation"""
        data = {}
        if status is not None:
            data["status"] = status
        if assignee_id is not None:
            data["assignee_id"] = assignee_id
        if team_id is not None:
            data["team_id"] = team_id
        if labels is not None:
            data["labels"] = labels
        if custom_attributes is not None:
            data["custom_attributes"] = custom_attributes

        return await self._request(
            "PUT",
            f"/accounts/{self.account_id}/conversations/{conversation_id}",
            data
        )

    async def toggle_conversation_status(
            self,
            conversation_id: int,
            status: str  # "open", "resolved", "pending"
    ) -> Dict[str, Any]:
        """Toggle conversation status"""
        data = {"status": status}
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/toggle_status",
            data
        )

    # Message Management
    async def send_message(
            self,
            conversation_id: int,
            content: str,
            message_type: str = "outgoing",
            private: bool = False,
            content_attributes: Optional[Dict[str, Any]] = None,
            attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Send a message in a conversation"""
        data = {
            "content": content,
            "message_type": message_type,
            "private": private
        }
        if content_attributes:
            data["content_attributes"] = content_attributes
        if attachments:
            data["attachments"] = attachments

        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/messages",
            data
        )

    async def get_messages(
            self,
            conversation_id: int,
            before: Optional[int] = None,
            after: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get messages from a conversation"""
        params = {}
        if before:
            params["before"] = before
        if after:
            params["after"] = after

        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/messages",
            params=params
        )
        return response.get("payload", [])

    # Label Management
    async def add_labels_to_conversation(
            self,
            conversation_id: int,
            labels: List[str]
    ) -> Dict[str, Any]:
        """Add labels to a conversation"""
        data = {"labels": labels}
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/labels",
            data
        )

    async def list_labels(self) -> List[Dict[str, Any]]:
        """List all available labels"""
        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/labels"
        )
        return response.get("payload", [])

    # Team Management
    async def list_teams(self) -> List[Dict[str, Any]]:
        """List all teams"""
        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/teams"
        )
        return response.get("payload", [])

    async def assign_team(
            self,
            conversation_id: int,
            team_id: int
    ) -> Dict[str, Any]:
        """Assign conversation to a team"""
        data = {"team_id": team_id}
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/assignments",
            data
        )

    # Agent Management
    async def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents"""
        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/agents"
        )
        return response.get("payload", [])

    async def assign_agent(
            self,
            conversation_id: int,
            assignee_id: int
    ) -> Dict[str, Any]:
        """Assign conversation to an agent"""
        data = {"assignee_id": assignee_id}
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/conversations/{conversation_id}/assignments",
            data
        )

    # Automation Rules
    async def create_automation_rule(
            self,
            name: str,
            description: str,
            event_name: str,
            conditions: List[Dict[str, Any]],
            actions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create an automation rule"""
        data = {
            "name": name,
            "description": description,
            "event_name": event_name,
            "conditions": conditions,
            "actions": actions
        }
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/automation_rules",
            data
        )

    # Webhook Management
    async def create_webhook(
            self,
            url: str,
            subscriptions: List[str]
    ) -> Dict[str, Any]:
        """Create a webhook"""
        data = {
            "url": url,
            "subscriptions": subscriptions
        }
        return await self._request(
            "POST",
            f"/accounts/{self.account_id}/webhooks",
            data
        )

    async def list_webhooks(self) -> List[Dict[str, Any]]:
        """List all webhooks"""
        response = await self._request(
            "GET",
            f"/accounts/{self.account_id}/webhooks"
        )
        return response.get("payload", [])


# Utility functions
def parse_chatwoot_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse Chatwoot webhook payload
    """
    try:
        event_type = payload.get("event")
        data = {}

        if event_type == "conversation_created":
            data = {
                "type": "conversation_created",
                "conversation_id": payload.get("id"),
                "inbox_id": payload.get("inbox_id"),
                "contact_id": payload.get("contact", {}).get("id"),
                "status": payload.get("status")
            }
        elif event_type == "conversation_updated":
            data = {
                "type": "conversation_updated",
                "conversation_id": payload.get("id"),
                "status": payload.get("status"),
                "assignee_id": payload.get("assignee_id")
            }
        elif event_type == "message_created":
            data = {
                "type": "message_created",
                "conversation_id": payload.get("conversation_id"),
                "message_id": payload.get("id"),
                "content": payload.get("content"),
                "message_type": payload.get("message_type"),
                "sender_type": payload.get("sender", {}).get("type"),
                "sender_id": payload.get("sender", {}).get("id")
            }

        return data
    except Exception as e:
        logger.error("Failed to parse Chatwoot webhook", error=str(e), payload=payload)
        return {}


def format_label_name(label: str) -> str:
    """
    Format label name for Chatwoot
    """
    return label.lower().replace(" ", "_").strip()
