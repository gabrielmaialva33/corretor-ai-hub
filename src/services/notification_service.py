"""
Notification service for alerts and communications
"""
import asyncio
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any, Optional

import structlog
from sqlalchemy import select

from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import Tenant, Lead, Conversation, Appointment
from src.integrations.redis import RedisQueue

logger = structlog.get_logger()
settings = get_settings()


class NotificationService:
    """
    Service for sending notifications via email, SMS, and push notifications
    """

    def __init__(self):
        self.queue = RedisQueue("notifications")
        self.smtp_configured = bool(
            settings.SMTP_HOST and
            settings.SMTP_USERNAME and
            settings.SMTP_PASSWORD
        )

    async def notify_handoff_required(
            self,
            tenant_id: str,
            conversation_id: str,
            lead_id: str
    ):
        """Notify agents that a conversation requires human handoff"""
        try:
            # Get tenant and lead information
            async with get_session() as session:
                tenant = await session.get(Tenant, tenant_id)
                lead = await session.get(Lead, lead_id)
                conversation = await session.get(Conversation, conversation_id)

            if not all([tenant, lead, conversation]):
                logger.error("Missing data for handoff notification")
                return

            # Create notification
            notification = {
                "type": "handoff_required",
                "tenant_id": str(tenant_id),
                "data": {
                    "conversation_id": str(conversation_id),
                    "lead_name": lead.name or "Cliente",
                    "lead_phone": lead.phone,
                    "handoff_reason": conversation.handoff_reason or "Cliente solicitou atendente",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }

            # Queue notification
            await self.queue.push(notification)

            # Send immediate email if configured
            if self.smtp_configured and tenant.email:
                subject = f"🚨 Atendimento Humano Necessário - {lead.name or lead.phone}"
                body = f"""
                Um cliente solicitou atendimento humano.
                
                Cliente: {lead.name or 'Não informado'}
                Telefone: {lead.phone}
                Motivo: {conversation.handoff_reason or 'Cliente solicitou atendente'}
                
                Acesse o Chatwoot para continuar o atendimento.
                """

                await self.send_email(
                    to_email=tenant.email,
                    subject=subject,
                    body=body,
                    is_html=False
                )

        except Exception as e:
            logger.error("Error sending handoff notification", error=str(e))

    async def notify_appointment_reminder(
            self,
            appointment_id: str,
            hours_before: int = 24
    ):
        """Send appointment reminder"""
        try:
            async with get_session() as session:
                stmt = select(Appointment).where(Appointment.id == appointment_id)
                result = await session.execute(stmt)
                appointment = result.scalar_one_or_none()

                if not appointment:
                    logger.error(f"Appointment not found: {appointment_id}")
                    return

                # Get related data
                tenant = await session.get(Tenant, appointment.tenant_id)
                lead = await session.get(Lead, appointment.lead_id)
                property = await session.get(Property, appointment.property_id)

            if not all([tenant, lead, property]):
                logger.error("Missing data for appointment reminder")
                return

            # Create notification
            notification = {
                "type": "appointment_reminder",
                "tenant_id": str(appointment.tenant_id),
                "data": {
                    "appointment_id": str(appointment_id),
                    "lead_name": lead.name or "Cliente",
                    "lead_phone": lead.phone,
                    "property_title": property.title,
                    "scheduled_at": appointment.scheduled_at.isoformat(),
                    "hours_before": hours_before
                }
            }

            # Queue notification
            await self.queue.push(notification)

            # Send email to lead if available
            if lead.email:
                subject = f"Lembrete: Visita ao imóvel {property.title}"
                body = f"""
                Olá {lead.name or 'Cliente'},
                
                Este é um lembrete sobre sua visita agendada:
                
                Imóvel: {property.title}
                Endereço: {property.address}, {property.neighborhood}, {property.city}
                Data e Hora: {appointment.scheduled_at.strftime('%d/%m/%Y às %H:%M')}
                
                Em caso de dúvidas ou para reagendar, entre em contato conosco.
                
                Atenciosamente,
                {tenant.name}
                """

                await self.send_email(
                    to_email=lead.email,
                    subject=subject,
                    body=body,
                    is_html=False
                )

            # Mark reminder as sent
            async with get_session() as session:
                appointment.reminder_sent = True
                appointment.reminder_sent_at = datetime.utcnow()
                session.add(appointment)
                await session.commit()

        except Exception as e:
            logger.error("Error sending appointment reminder", error=str(e))

    async def notify_new_lead(
            self,
            tenant_id: str,
            lead_id: str
    ):
        """Notify about new lead captured"""
        try:
            async with get_session() as session:
                tenant = await session.get(Tenant, tenant_id)
                lead = await session.get(Lead, lead_id)

            if not tenant or not lead:
                return

            notification = {
                "type": "new_lead",
                "tenant_id": str(tenant_id),
                "data": {
                    "lead_id": str(lead_id),
                    "lead_name": lead.name or "Não informado",
                    "lead_phone": lead.phone,
                    "lead_email": lead.email,
                    "source": lead.source,
                    "timestamp": lead.created_at.isoformat()
                }
            }

            await self.queue.push(notification)

        except Exception as e:
            logger.error("Error sending new lead notification", error=str(e))

    async def notify_daily_summary(
            self,
            tenant_id: str,
            summary_data: Dict[str, Any]
    ):
        """Send daily summary to tenant"""
        try:
            async with get_session() as session:
                tenant = await session.get(Tenant, tenant_id)

            if not tenant or not tenant.email:
                return

            subject = f"📊 Resumo Diário - {datetime.now().strftime('%d/%m/%Y')}"

            body = f"""
            Resumo das atividades de hoje:
            
            📱 Conversas: {summary_data.get('total_conversations', 0)}
            👥 Novos Leads: {summary_data.get('new_leads', 0)}
            🏠 Imóveis Visualizados: {summary_data.get('properties_viewed', 0)}
            📅 Visitas Agendadas: {summary_data.get('appointments_scheduled', 0)}
            
            Taxa de Conversão: {summary_data.get('conversion_rate', 0):.1f}%
            
            Principais Interesses:
            """

            for interest in summary_data.get('top_interests', [])[:5]:
                body += f"\n- {interest['type']}: {interest['count']} buscas"

            await self.send_email(
                to_email=tenant.email,
                subject=subject,
                body=body,
                is_html=False
            )

        except Exception as e:
            logger.error("Error sending daily summary", error=str(e))

    async def send_email(
            self,
            to_email: str,
            subject: str,
            body: str,
            is_html: bool = False,
            attachments: Optional[List[Dict[str, Any]]] = None
    ):
        """Send email notification"""
        if not self.smtp_configured:
            logger.warning("SMTP not configured, skipping email")
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = settings.SMTP_FROM_EMAIL
            msg['To'] = to_email
            msg['Subject'] = subject

            # Add body
            msg.attach(MIMEText(body, 'html' if is_html else 'plain'))

            # Add attachments if any
            if attachments:
                for attachment in attachments:
                    # Implementation for attachments
                    pass

            # Send email
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}")

        except Exception as e:
            logger.error(f"Failed to send email", error=str(e), to=to_email)

    async def process_notification_queue(self):
        """Process notifications from queue"""
        while True:
            try:
                # Get notification from queue
                notification = await self.queue.pop(timeout=5)

                if notification:
                    await self._process_notification(notification)

            except Exception as e:
                logger.error("Error processing notification queue", error=str(e))

            await asyncio.sleep(1)

    async def _process_notification(self, notification: Dict[str, Any]):
        """Process a single notification"""
        try:
            notification_type = notification.get("type")

            if notification_type == "handoff_required":
                # Could send push notification to mobile app
                # Could send SMS via Twilio
                # Could trigger other integrations
                pass

            elif notification_type == "appointment_reminder":
                # Could send WhatsApp reminder via EVO API
                pass

            elif notification_type == "new_lead":
                # Could update CRM
                # Could trigger marketing automation
                pass

            logger.info(
                f"Processed notification",
                type=notification_type,
                tenant_id=notification.get("tenant_id")
            )

        except Exception as e:
            logger.error("Error processing notification", error=str(e), notification=notification)
