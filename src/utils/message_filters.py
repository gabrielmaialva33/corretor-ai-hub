"""
Message filtering utilities for conditional automation activation
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import structlog
from sqlalchemy import select, and_, func

from src.database.connection import get_session
from src.database.models import Lead, Message, Conversation

logger = structlog.get_logger()

# Real estate portal patterns
REAL_ESTATE_PORTALS = {
    "zonaprop": r"(?:https?://)?(?:www\.)?zonaprop\.com\.ar",
    "argenprop": r"(?:https?://)?(?:www\.)?argenprop\.com",
    "mercadolibre": r"(?:https?://)?(?:www\.)?(?:inmuebles\.)?mercadolibre\.com\.ar",
    "properati": r"(?:https?://)?(?:www\.)?properati\.com\.ar",
    "remax": r"(?:https?://)?(?:www\.)?remax\.com\.ar"
}


class MessageFilter:
    """Filter messages based on various criteria"""

    @staticmethod
    def extract_portal_links(message: str) -> List[Dict[str, str]]:
        """
        Extract real estate portal links from message
        
        Returns:
            List of dicts with portal name and URL
        """
        found_links = []

        for portal_name, pattern in REAL_ESTATE_PORTALS.items():
            # Find all URLs matching the portal pattern
            urls = re.findall(
                pattern + r'/[^\s\)]+',
                message,
                re.IGNORECASE
            )

            for url in urls:
                # Clean up the URL
                if not url.startswith('http'):
                    url = 'https://' + url

                found_links.append({
                    "portal": portal_name,
                    "url": url
                })

        return found_links

    @staticmethod
    async def is_new_contact(tenant_id: str, phone: str, hours: int = 24) -> bool:
        """
        Check if this is a new contact or hasn't messaged in X hours
        
        Args:
            tenant_id: Tenant ID
            phone: Phone number
            hours: Hours to consider as "new" conversation
            
        Returns:
            True if new contact or no recent messages
        """
        async with get_session() as session:
            # Check if lead exists
            stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == phone
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                return True

            # Check last conversation
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)

            stmt = select(Conversation).where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.lead_id == lead.id,
                    Conversation.last_message_at > cutoff_time
                )
            ).order_by(Conversation.last_message_at.desc())

            result = await session.execute(stmt)
            recent_conversation = result.scalar_one_or_none()

            return recent_conversation is None

    @staticmethod
    async def should_activate_automation(
            tenant_id: str,
            phone: str,
            message: str,
            config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Determine if automation should be activated based on criteria
        
        Args:
            tenant_id: Tenant ID
            phone: Phone number
            message: Message content
            config: Tenant-specific configuration
            
        Returns:
            Dict with activation decision and reason
        """
        config = config or {}

        # Default configuration
        activation_config = {
            "require_new_contact": config.get("require_new_contact", True),
            "require_portal_link": config.get("require_portal_link", False),
            "new_contact_hours": config.get("new_contact_hours", 24),
            "allowed_portals": config.get("allowed_portals", list(REAL_ESTATE_PORTALS.keys()))
        }

        # Check for portal links
        portal_links = MessageFilter.extract_portal_links(message)
        has_portal_link = len(portal_links) > 0

        # Filter by allowed portals
        if portal_links and activation_config["allowed_portals"]:
            portal_links = [
                link for link in portal_links
                if link["portal"] in activation_config["allowed_portals"]
            ]
            has_portal_link = len(portal_links) > 0

        # Check if new contact
        is_new = await MessageFilter.is_new_contact(
            tenant_id,
            phone,
            activation_config["new_contact_hours"]
        )

        # Determine activation
        should_activate = False
        reason = ""

        if activation_config["require_new_contact"] and activation_config["require_portal_link"]:
            # Both conditions required
            should_activate = is_new and has_portal_link
            if not should_activate:
                if not is_new:
                    reason = "not_new_contact"
                elif not has_portal_link:
                    reason = "no_portal_link"
        elif activation_config["require_new_contact"]:
            # Only new contact required
            should_activate = is_new
            if not should_activate:
                reason = "not_new_contact"
        elif activation_config["require_portal_link"]:
            # Only portal link required
            should_activate = has_portal_link
            if not should_activate:
                reason = "no_portal_link"
        else:
            # No restrictions
            should_activate = True
            reason = "no_restrictions"

        return {
            "activate": should_activate,
            "reason": reason if not should_activate else "criteria_met",
            "is_new_contact": is_new,
            "has_portal_link": has_portal_link,
            "portal_links": portal_links,
            "config": activation_config
        }

    @staticmethod
    def extract_property_id_from_url(url: str) -> Optional[str]:
        """
        Extract property ID from portal URL
        
        Args:
            url: Portal URL
            
        Returns:
            Property ID if found
        """
        # Patterns for different portals
        patterns = {
            "zonaprop": r"/(\d+)-",
            "argenprop": r"/(\d+)$",
            "mercadolibre": r"MLA-(\d+)",
            "properati": r"/(\d+)$",
            "remax": r"listing/(\d+)"
        }

        for portal, pattern in patterns.items():
            if portal in url.lower():
                match = re.search(pattern, url)
                if match:
                    return f"{portal}_{match.group(1)}"

        return None

    @staticmethod
    async def get_message_context(
            tenant_id: str,
            phone: str,
            limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get recent message context for the contact
        
        Args:
            tenant_id: Tenant ID
            phone: Phone number
            limit: Number of recent messages to retrieve
            
        Returns:
            List of recent messages
        """
        async with get_session() as session:
            # Get lead
            stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == phone
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                return []

            # Get recent messages
            stmt = (
                select(Message, Conversation)
                .join(Conversation, Message.conversation_id == Conversation.id)
                .where(
                    and_(
                        Conversation.tenant_id == tenant_id,
                        Conversation.lead_id == lead.id
                    )
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
            )

            result = await session.execute(stmt)
            messages = []

            for message, conversation in result:
                messages.append({
                    "content": message.content,
                    "sender_type": message.sender_type,
                    "created_at": message.created_at.isoformat(),
                    "conversation_id": str(conversation.id),
                    "message_type": message.message_type
                })

            return messages
