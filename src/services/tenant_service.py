"""
Tenant service for business logic
"""
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import structlog
from sqlalchemy import select, func, and_

from src.api.routes.auth import get_password_hash
from src.core.exceptions import NotFoundError, BusinessLogicError
from src.database.connection import get_session
from src.database.models import (
    Tenant, TenantStatus, Property, Lead, Conversation,
    Appointment, PropertyStatus, LeadStatus, ConversationStatus
)
from src.database.schemas import TenantCreate, TenantUpdate
from src.integrations.chatwoot import ChatwootClient
from src.integrations.evo_api import EvoAPIClient
from src.integrations.qdrant import QdrantManager

logger = structlog.get_logger()


class TenantService:
    """
    Service for managing tenants and their integrations
    """

    async def create_tenant(self, tenant_data: TenantCreate) -> Tenant:
        """Create a new tenant"""
        async with get_session() as session:
            # Create tenant
            tenant = Tenant(
                name=tenant_data.name,
                email=tenant_data.email,
                phone=tenant_data.phone,
                company_name=tenant_data.company_name,
                settings=tenant_data.settings,
                features=tenant_data.features,
                status=TenantStatus.TRIAL,
                qdrant_namespace=f"tenant_{uuid.uuid4().hex[:8]}",
                password_hash=get_password_hash("changeme123")  # Default password
            )

            session.add(tenant)
            await session.commit()
            await session.refresh(tenant)

            logger.info(f"Created tenant: {tenant.id}")
            return tenant

    async def update_tenant(
            self,
            tenant_id: str,
            tenant_update: TenantUpdate
    ) -> Tenant:
        """Update tenant information"""
        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            # Update fields
            update_data = tenant_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(tenant, field, value)

            await session.commit()
            await session.refresh(tenant)

            logger.info(f"Updated tenant: {tenant_id}")
            return tenant

    async def activate_tenant(self, tenant_id: str):
        """Activate a tenant"""
        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            if tenant.status == TenantStatus.ACTIVE:
                raise BusinessLogicError("Tenant is already active")

            tenant.status = TenantStatus.ACTIVE
            tenant.is_active = True
            tenant.activated_at = datetime.utcnow()

            await session.commit()

            logger.info(f"Activated tenant: {tenant_id}")

    async def suspend_tenant(self, tenant_id: str, reason: Optional[str] = None):
        """Suspend a tenant"""
        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            if tenant.status == TenantStatus.SUSPENDED:
                raise BusinessLogicError("Tenant is already suspended")

            tenant.status = TenantStatus.SUSPENDED
            tenant.is_active = False
            tenant.suspended_at = datetime.utcnow()

            if reason:
                tenant.settings["suspension_reason"] = reason

            await session.commit()

            logger.info(f"Suspended tenant: {tenant_id}")

    async def delete_tenant(self, tenant_id: str):
        """Soft delete a tenant"""
        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            tenant.is_active = False
            tenant.status = TenantStatus.INACTIVE

            await session.commit()

            logger.info(f"Deleted tenant: {tenant_id}")

    async def setup_tenant_integrations(self, tenant_id: str):
        """Setup all integrations for a tenant"""
        try:
            async with get_session() as session:
                tenant = await session.get(Tenant, tenant_id)

                if not tenant:
                    raise NotFoundError("Tenant", tenant_id)

            # Setup EVO API instance
            await self._setup_evo_instance(tenant)

            # Setup Chatwoot inbox
            await self._setup_chatwoot_inbox(tenant)

            # Setup Qdrant collections
            await self._setup_qdrant_collections(tenant)

            # Setup Google Calendar (requires manual OAuth)
            # This would typically be done through a web interface

            logger.info(f"Completed integration setup for tenant: {tenant_id}")

        except Exception as e:
            logger.error(f"Failed to setup integrations for tenant {tenant_id}", error=str(e))
            raise

    async def _setup_evo_instance(self, tenant: Tenant):
        """Setup EVO API instance for WhatsApp"""
        try:
            if tenant.evo_instance_key:
                logger.info(f"EVO instance already exists for tenant: {tenant.id}")
                return

            async with EvoAPIClient() as client:
                # Create instance
                instance_name = f"corretor_{tenant.id.hex[:8]}"
                result = await client.create_instance(
                    instance_name=instance_name,
                    phone_number=tenant.phone
                )

                # Update tenant
                async with get_session() as session:
                    tenant.evo_instance_key = instance_name
                    session.add(tenant)
                    await session.commit()

                logger.info(f"Created EVO instance for tenant: {tenant.id}")

        except Exception as e:
            logger.error(f"Failed to setup EVO instance", error=str(e))
            # Don't raise - continue with other integrations

    async def _setup_chatwoot_inbox(self, tenant: Tenant):
        """Setup Chatwoot inbox"""
        try:
            if tenant.chatwoot_inbox_id:
                logger.info(f"Chatwoot inbox already exists for tenant: {tenant.id}")
                return

            async with ChatwootClient() as client:
                # Create inbox
                inbox_result = await client.create_inbox(
                    name=f"{tenant.name} - WhatsApp",
                    channel_type="api"
                )

                # Update tenant
                async with get_session() as session:
                    tenant.chatwoot_inbox_id = inbox_result["id"]
                    session.add(tenant)
                    await session.commit()

                logger.info(f"Created Chatwoot inbox for tenant: {tenant.id}")

        except Exception as e:
            logger.error(f"Failed to setup Chatwoot inbox", error=str(e))
            # Don't raise - continue with other integrations

    async def _setup_qdrant_collections(self, tenant: Tenant):
        """Setup Qdrant vector database collections"""
        try:
            manager = QdrantManager(str(tenant.id))
            await manager.create_collections()

            logger.info(f"Created Qdrant collections for tenant: {tenant.id}")

        except Exception as e:
            logger.error(f"Failed to setup Qdrant collections", error=str(e))
            # Don't raise - continue with other integrations

    async def get_tenant_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get statistics for a tenant"""
        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            # Get counts
            property_count = await session.scalar(
                select(func.count(Property.id)).where(
                    and_(
                        Property.tenant_id == tenant_id,
                        Property.is_active == True
                    )
                )
            )

            lead_count = await session.scalar(
                select(func.count(Lead.id)).where(Lead.tenant_id == tenant_id)
            )

            conversation_count = await session.scalar(
                select(func.count(Conversation.id)).where(
                    Conversation.tenant_id == tenant_id
                )
            )

            appointment_count = await session.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.tenant_id == tenant_id
                )
            )

            # Get active counts
            active_properties = await session.scalar(
                select(func.count(Property.id)).where(
                    and_(
                        Property.tenant_id == tenant_id,
                        Property.status == PropertyStatus.AVAILABLE
                    )
                )
            )

            active_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == tenant_id,
                        Lead.status.in_([LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.QUALIFIED])
                    )
                )
            )

            active_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == tenant_id,
                        Conversation.status == ConversationStatus.ACTIVE
                    )
                )
            )

            # Calculate conversion rate
            converted_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == tenant_id,
                        Lead.status == LeadStatus.CONVERTED
                    )
                )
            )

            conversion_rate = (converted_leads / lead_count * 100) if lead_count > 0 else 0

            return {
                "tenant_id": tenant_id,
                "status": tenant.status.value,
                "created_at": tenant.created_at.isoformat(),
                "stats": {
                    "properties": {
                        "total": property_count,
                        "active": active_properties
                    },
                    "leads": {
                        "total": lead_count,
                        "active": active_leads,
                        "converted": converted_leads,
                        "conversion_rate": round(conversion_rate, 2)
                    },
                    "conversations": {
                        "total": conversation_count,
                        "active": active_conversations
                    },
                    "appointments": {
                        "total": appointment_count
                    }
                },
                "integrations": {
                    "evo_api": bool(tenant.evo_instance_key),
                    "chatwoot": bool(tenant.chatwoot_inbox_id),
                    "google_calendar": bool(tenant.google_calendar_id),
                    "qdrant": bool(tenant.qdrant_namespace)
                }
            }
