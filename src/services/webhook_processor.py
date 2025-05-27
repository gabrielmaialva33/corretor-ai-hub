"""
Webhook processor service
"""
from datetime import datetime
from typing import Dict, Any, Optional

import structlog
from sqlalchemy import select, and_

from src.agents.property_agent import PropertyAgent
from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import (
    Tenant, Lead, Conversation, Message, WebhookLog,
    ConversationStatus, LeadStatus
)
from src.integrations.chatwoot import ChatwootClient, parse_chatwoot_webhook
from src.integrations.evo_api import EvoAPIClient, format_phone_number, parse_webhook_message
from src.services.media_processor import MediaProcessor
from src.services.notification_service import NotificationService
from src.utils.message_filters import MessageFilter

logger = structlog.get_logger()
settings = get_settings()


class WebhookProcessor:
    """
    Process webhooks from various sources
    """

    def __init__(self):
        self.notification_service = NotificationService()
        self.media_processor = MediaProcessor()

    async def process_evo_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process EVO API webhook"""
        try:
            # Log webhook
            await self._log_webhook("evo", payload)

            # Extract event type
            event_type = payload.get("event")

            if event_type == "messages.upsert":
                return await self._handle_evo_message(payload)
            elif event_type == "connection.update":
                return await self._handle_evo_connection_update(payload)
            elif event_type == "messages.update":
                return await self._handle_evo_message_update(payload)
            else:
                logger.info(f"Unhandled EVO event type: {event_type}")
                return {"status": "ignored", "event_type": event_type}

        except Exception as e:
            logger.error("Error processing EVO webhook", error=str(e), payload=payload)
            raise

    async def process_chatwoot_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Chatwoot webhook"""
        try:
            # Log webhook
            await self._log_webhook("chatwoot", payload)

            # Extract event type
            event_type = payload.get("event")

            if event_type == "conversation_created":
                return await self._handle_chatwoot_conversation_created(payload)
            elif event_type == "conversation_updated":
                return await self._handle_chatwoot_conversation_updated(payload)
            elif event_type == "message_created":
                return await self._handle_chatwoot_message_created(payload)
            else:
                logger.info(f"Unhandled Chatwoot event type: {event_type}")
                return {"status": "ignored", "event_type": event_type}

        except Exception as e:
            logger.error("Error processing Chatwoot webhook", error=str(e), payload=payload)
            raise

    async def process_calendar_webhook(
            self,
            payload: Dict[str, Any],
            channel_token: str
    ) -> Dict[str, Any]:
        """Process Google Calendar webhook"""
        try:
            # Log webhook
            await self._log_webhook("google_calendar", payload)

            # Google Calendar webhooks are notifications about changes
            # We need to fetch the actual changes using the Calendar API
            # This is typically handled by a separate sync process

            return {"status": "received", "action": "sync_required"}

        except Exception as e:
            logger.error("Error processing Calendar webhook", error=str(e))
            raise

    async def _handle_evo_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle new message from EVO"""
        try:
            # Parse message
            message_data = parse_webhook_message(payload)

            if not message_data.get("message_id"):
                return {"status": "error", "reason": "invalid_message"}

            # Skip if message is from bot
            if message_data.get("is_from_me"):
                return {"status": "ignored", "reason": "own_message"}

            # Get tenant from instance
            instance_key = payload.get("instance", {}).get("instanceName")
            tenant = await self._get_tenant_by_instance(instance_key)

            if not tenant:
                logger.error(f"Tenant not found for instance: {instance_key}")
                return {"status": "error", "reason": "tenant_not_found"}

            # Get or create lead
            phone = message_data.get("sender")
            lead = await self._get_or_create_lead(tenant.id, phone)

            # Get or create conversation
            conversation = await self._get_or_create_conversation(
                tenant.id,
                lead.id,
                message_data.get("chat_id")
            )

            # Process media if present
            processed_content = message_data.get("content", "")
            media_metadata = {}

            # Handle audio messages
            if message_data.get("type") == "audio" and message_data.get("media_url"):
                audio_result = await self.media_processor.process_audio(
                    message_data["media_url"],
                    message_data.get("media_format", "ogg")
                )
                if audio_result["success"]:
                    processed_content = audio_result["transcription"]
                    media_metadata["audio_transcription"] = audio_result
                    message_data["content"] = processed_content

            # Handle image messages
            elif message_data.get("type") == "image" and message_data.get("media_url"):
                image_result = await self.media_processor.process_image(
                    message_data["media_url"],
                    extract_text=True,
                    analyze_content=True
                )
                if image_result["success"]:
                    # Combine extracted text and analysis
                    parts = []
                    if image_result.get("extracted_text"):
                        parts.append(f"[Texto na imagem: {image_result['extracted_text']}]")
                    if image_result.get("content_analysis"):
                        parts.append(f"[Descrição: {image_result['content_analysis']}]")
                    if parts:
                        processed_content = " ".join(parts)
                    media_metadata["image_analysis"] = image_result
                    message_data["content"] = processed_content

            # Check if automation should be activated
            activation_check = await MessageFilter.should_activate_automation(
                tenant.id,
                phone,
                processed_content,
                tenant.automation_config
            )

            # Save message with activation metadata
            message = await self._save_message(
                conversation.id,
                processed_content,
                message_data.get("type"),
                "customer",
                phone,
                {
                    **message_data,
                    "automation_check": activation_check,
                    "media_metadata": media_metadata
                }
            )

            # Update conversation last message time
            async with get_session() as session:
                conversation.last_message_at = datetime.utcnow()
                session.add(conversation)
                await session.commit()

            # Process with AI agent if conversation is active AND automation should be activated
            if conversation.status == ConversationStatus.ACTIVE and activation_check["activate"]:
                # Initialize AI agent
                agent = PropertyAgent(tenant.id, str(conversation.id))

                # Process message with processed content
                response_text, agent_state = await agent.process_message(
                    processed_content,
                    metadata={
                        "message_id": message_data.get("message_id"),
                        "sender": phone,
                        "timestamp": message_data.get("timestamp"),
                        "message_type": message_data.get("type"),
                        "media_metadata": media_metadata
                    }
                )

                # Send response
                async with EvoAPIClient(instance_key) as evo_client:
                    await evo_client.send_text_message(
                        to=phone,
                        message=response_text
                    )

                # Save AI response
                await self._save_message(
                    conversation.id,
                    response_text,
                    "text",
                    "bot",
                    "ai_agent",
                    {
                        "agent_state": agent_state,
                        "ai_processed": True
                    }
                )

                # Update conversation state
                if agent_state.get("handoff_requested"):
                    conversation.handoff_requested = True
                    conversation.handoff_reason = agent_state.get("handoff_reason")

                    # Notify human agents
                    await self.notification_service.notify_handoff_required(
                        tenant.id,
                        conversation.id,
                        lead.id
                    )

                # Update lead information if captured
                if agent_state.get("lead_info_captured"):
                    await self._update_lead_from_agent(lead.id, agent_state["lead_info_captured"])

                # Sync with Chatwoot
                await self._sync_message_to_chatwoot(tenant, conversation, message, response_text)

            else:
                # Automation not activated - log reason
                logger.info(
                    "Automation not activated",
                    tenant_id=tenant.id,
                    phone=phone,
                    reason=activation_check["reason"],
                    details=activation_check
                )

                # Still sync to Chatwoot for visibility
                await self._sync_message_to_chatwoot(tenant, conversation, message)

            return {
                "status": "processed",
                "conversation_id": str(conversation.id),
                "message_id": str(message.id),
                "automation_activated": activation_check["activate"]
            }

        except Exception as e:
            logger.error("Error handling EVO message", error=str(e))
            raise

    async def _handle_chatwoot_conversation_updated(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Chatwoot conversation update"""
        try:
            # Parse webhook data
            data = parse_chatwoot_webhook(payload)

            # Get conversation
            chatwoot_id = data.get("conversation_id")
            if not chatwoot_id:
                return {"status": "error", "reason": "missing_conversation_id"}

            async with get_session() as session:
                stmt = select(Conversation).where(
                    Conversation.chatwoot_conversation_id == chatwoot_id
                )
                result = await session.execute(stmt)
                conversation = result.scalar_one_or_none()

                if not conversation:
                    return {"status": "error", "reason": "conversation_not_found"}

                # Update status if changed
                new_status = data.get("status")
                if new_status:
                    status_mapping = {
                        "open": ConversationStatus.ACTIVE,
                        "resolved": ConversationStatus.ENDED,
                        "pending": ConversationStatus.HANDED_OFF
                    }

                    if new_status in status_mapping:
                        conversation.status = status_mapping[new_status]

                        if new_status == "resolved":
                            conversation.ended_at = datetime.utcnow()

                await session.commit()

            return {"status": "processed", "conversation_id": str(conversation.id)}

        except Exception as e:
            logger.error("Error handling Chatwoot conversation update", error=str(e))
            raise

    async def _get_tenant_by_instance(self, instance_key: str) -> Optional[Tenant]:
        """Get tenant by EVO instance key"""
        async with get_session() as session:
            stmt = select(Tenant).where(
                and_(
                    Tenant.evo_instance_key == instance_key,
                    Tenant.is_active == True
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _get_or_create_lead(self, tenant_id: str, phone: str) -> Lead:
        """Get or create lead by phone number"""
        async with get_session() as session:
            # Format phone number
            formatted_phone = format_phone_number(phone).replace("@s.whatsapp.net", "")

            stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == formatted_phone
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                lead = Lead(
                    tenant_id=tenant_id,
                    phone=formatted_phone,
                    whatsapp_id=phone,
                    source="whatsapp",
                    source_details={"auto_created": True},
                    status=LeadStatus.NEW
                )
                session.add(lead)
                await session.commit()

            return lead

    async def _get_or_create_conversation(
            self,
            tenant_id: str,
            lead_id: str,
            evo_chat_id: str
    ) -> Conversation:
        """Get or create conversation"""
        async with get_session() as session:
            stmt = select(Conversation).where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.evo_chat_id == evo_chat_id,
                    Conversation.status != ConversationStatus.ENDED
                )
            )
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                conversation = Conversation(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    evo_chat_id=evo_chat_id,
                    status=ConversationStatus.ACTIVE,
                    started_at=datetime.utcnow()
                )
                session.add(conversation)
                await session.commit()

            return conversation

    async def _save_message(
            self,
            conversation_id: str,
            content: str,
            message_type: str,
            sender_type: str,
            sender_id: str,
            metadata: Dict[str, Any]
    ) -> Message:
        """Save message to database"""
        async with get_session() as session:
            message = Message(
                conversation_id=conversation_id,
                content=content or "",
                message_type=message_type,
                sender_type=sender_type,
                sender_id=sender_id,
                sender_name=metadata.get("sender_name"),
                media_url=metadata.get("media_url"),
                ai_processed=metadata.get("ai_processed", False),
                ai_response=metadata.get("ai_response"),
                ai_confidence=metadata.get("ai_confidence"),
                intent=metadata.get("intent"),
                entities=metadata.get("entities", {}),
                created_at=datetime.utcnow()
            )

            session.add(message)
            await session.commit()

            return message

    async def _update_lead_from_agent(self, lead_id: str, captured_info: Dict[str, Any]):
        """Update lead with information captured by AI agent"""
        async with get_session() as session:
            stmt = select(Lead).where(Lead.id == lead_id)
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if lead:
                if "name" in captured_info:
                    lead.name = captured_info["name"]
                if "email" in captured_info:
                    lead.email = captured_info["email"]
                if "preferences" in captured_info:
                    lead.preferences = {**lead.preferences, **captured_info["preferences"]}
                if "budget_min" in captured_info:
                    lead.budget_min = captured_info["budget_min"]
                if "budget_max" in captured_info:
                    lead.budget_max = captured_info["budget_max"]

                lead.last_contact_at = datetime.utcnow()
                await session.commit()

    async def _sync_message_to_chatwoot(
            self,
            tenant: Tenant,
            conversation: Conversation,
            message: Message,
            ai_response: Optional[str] = None
    ):
        """Sync message to Chatwoot"""
        try:
            if not tenant.chatwoot_inbox_id:
                return

            async with ChatwootClient(tenant.id) as chatwoot:
                # Create or update conversation in Chatwoot
                if not conversation.chatwoot_conversation_id:
                    # Create conversation
                    # First, create/get contact
                    lead = await self._get_lead_by_id(conversation.lead_id)

                    contact_data = await chatwoot.create_contact(
                        name=lead.name,
                        phone_number=lead.phone,
                        email=lead.email,
                        identifier=lead.whatsapp_id
                    )

                    # Create conversation
                    conv_data = await chatwoot.create_conversation(
                        contact_id=contact_data["id"],
                        inbox_id=tenant.chatwoot_inbox_id,
                        status="open"
                    )

                    # Update conversation with Chatwoot ID
                    async with get_session() as session:
                        conversation.chatwoot_conversation_id = conv_data["id"]
                        session.add(conversation)
                        await session.commit()

                # Send customer message
                await chatwoot.send_message(
                    conversation_id=conversation.chatwoot_conversation_id,
                    content=message.content,
                    message_type="incoming",
                    private=False
                )

                # Send AI response if provided
                if ai_response:
                    await chatwoot.send_message(
                        conversation_id=conversation.chatwoot_conversation_id,
                        content=ai_response,
                        message_type="outgoing",
                        private=False,
                        content_attributes={"from_ai": True}
                    )

        except Exception as e:
            logger.error("Error syncing to Chatwoot", error=str(e))

    async def _get_lead_by_id(self, lead_id: str) -> Optional[Lead]:
        """Get lead by ID"""
        async with get_session() as session:
            stmt = select(Lead).where(Lead.id == lead_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def _log_webhook(self, source: str, payload: Dict[str, Any]):
        """Log webhook for debugging"""
        async with get_session() as session:
            log = WebhookLog(
                source=source,
                endpoint=f"/webhooks/{source}",
                method="POST",
                headers={},  # Can add headers if needed
                body=payload,
                received_at=datetime.utcnow()
            )
            session.add(log)
            await session.commit()

    async def _handle_evo_connection_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle EVO connection status update"""
        try:
            instance = payload.get("instance", {})
            status = instance.get("status")
            instance_name = instance.get("instanceName")

            logger.info(
                f"EVO connection update",
                instance=instance_name,
                status=status
            )

            # You can implement logic here to handle connection status changes
            # For example, notify admins if connection is lost

            return {"status": "processed", "connection_status": status}

        except Exception as e:
            logger.error("Error handling connection update", error=str(e))
            raise

    async def _handle_evo_message_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle EVO message status update"""
        try:
            # This typically includes read receipts, delivery status, etc.
            message_data = payload.get("data", {})

            # You can implement logic here to update message status in database

            return {"status": "processed", "update_type": "message_status"}

        except Exception as e:
            logger.error("Error handling message update", error=str(e))
            raise

    async def _handle_chatwoot_conversation_created(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Chatwoot conversation creation"""
        try:
            # This is typically triggered when an agent creates a conversation manually
            # We might want to sync this back to our system

            return {"status": "processed", "action": "conversation_created"}

        except Exception as e:
            logger.error("Error handling Chatwoot conversation creation", error=str(e))
            raise

    async def _handle_chatwoot_message_created(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Chatwoot message creation"""
        try:
            # Parse message data
            data = parse_chatwoot_webhook(payload)

            # Only process agent messages (not customer or bot messages)
            if data.get("sender_type") != "agent":
                return {"status": "ignored", "reason": "not_agent_message"}

            # This would be a message from human agent
            # We might want to send it via WhatsApp

            return {"status": "processed", "action": "agent_message"}

        except Exception as e:
            logger.error("Error handling Chatwoot message", error=str(e))
            raise
