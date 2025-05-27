"""
Appointment reminder service for scheduling visit notifications
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import structlog
from celery import Celery
from jinja2 import Template
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import Appointment, Lead, Property, Tenant, AppointmentStatus
from src.integrations.evo_api import EvoAPIClient

logger = structlog.get_logger()
settings = get_settings()

# Celery configuration for scheduled tasks
celery_app = Celery(
    'appointment_reminders',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    timezone='America/Sao_Paulo',
    enable_utc=True,
    beat_schedule={
        'check-upcoming-appointments': {
            'task': 'src.services.appointment_reminder.check_upcoming_appointments',
            'schedule': 300.0,  # Every 5 minutes
        },
    }
)


class AppointmentReminderService:
    """
    Service for managing appointment reminders
    """

    # Reminder templates
    REMINDER_TEMPLATES = {
        "24_hours": Template("""
Olá {{ lead_name }}! 👋

Lembramos que você tem uma visita agendada amanhã:

📍 *Imóvel*: {{ property_title }}
📅 *Data*: {{ appointment_date }}
🕐 *Horário*: {{ appointment_time }}
📍 *Endereço*: {{ property_address }}

{% if notes %}
ℹ️ *Observações*: {{ notes }}
{% endif %}

Confirme sua presença respondendo:
✅ *SIM* - Confirmo minha presença
❌ *NÃO* - Preciso cancelar/remarcar

Aguardamos você! 🏠
        """),

        "3_hours": Template("""
Olá {{ lead_name }}! 👋

Sua visita está próxima! ⏰

📍 *Imóvel*: {{ property_title }}
🕐 *Horário*: {{ appointment_time }} (em 3 horas)
📍 *Endereço*: {{ property_address }}

{% if google_maps_link %}
🗺️ *Como chegar*: {{ google_maps_link }}
{% endif %}

Estamos te esperando! 

Se precisar cancelar ou remarcar, responda esta mensagem.
        """),

        "confirmation_request": Template("""
Olá {{ lead_name }}! 👋

Você tem uma visita agendada:

📍 *Imóvel*: {{ property_title }}
📅 *Data*: {{ appointment_date }}
🕐 *Horário*: {{ appointment_time }}

Por favor, confirme sua presença respondendo *SIM* ou *NÃO*.

Obrigado! 🏠
        """)
    }

    async def schedule_reminders(self, appointment_id: str):
        """
        Schedule reminders for an appointment
        
        Args:
            appointment_id: Appointment ID
        """
        try:
            async with get_session() as session:
                # Get appointment with related data
                stmt = (
                    select(Appointment)
                    .where(Appointment.id == appointment_id)
                    .options(
                        selectinload(Appointment.lead),
                        selectinload(Appointment.property),
                        selectinload(Appointment.tenant)
                    )
                )
                result = await session.execute(stmt)
                appointment = result.scalar_one_or_none()

                if not appointment:
                    logger.error(f"Appointment not found: {appointment_id}")
                    return

                # Schedule 24-hour reminder
                reminder_24h = appointment.scheduled_date - timedelta(hours=24)
                if reminder_24h > datetime.utcnow():
                    send_appointment_reminder.apply_async(
                        args=[str(appointment_id), "24_hours"],
                        eta=reminder_24h
                    )
                    logger.info(f"Scheduled 24h reminder for appointment {appointment_id}")

                # Schedule 3-hour reminder
                reminder_3h = appointment.scheduled_date - timedelta(hours=3)
                if reminder_3h > datetime.utcnow():
                    send_appointment_reminder.apply_async(
                        args=[str(appointment_id), "3_hours"],
                        eta=reminder_3h
                    )
                    logger.info(f"Scheduled 3h reminder for appointment {appointment_id}")

        except Exception as e:
            logger.error("Error scheduling reminders", error=str(e), appointment_id=appointment_id)

    async def send_reminder(
            self,
            appointment_id: str,
            reminder_type: str = "24_hours"
    ) -> bool:
        """
        Send a reminder for an appointment
        
        Args:
            appointment_id: Appointment ID
            reminder_type: Type of reminder (24_hours, 3_hours, etc)
            
        Returns:
            Success status
        """
        try:
            async with get_session() as session:
                # Get appointment with related data
                stmt = (
                    select(Appointment, Lead, Property, Tenant)
                    .join(Lead, Appointment.lead_id == Lead.id)
                    .join(Property, Appointment.property_id == Property.id)
                    .join(Tenant, Appointment.tenant_id == Tenant.id)
                    .where(
                        and_(
                            Appointment.id == appointment_id,
                            Appointment.status == AppointmentStatus.SCHEDULED
                        )
                    )
                )
                result = await session.execute(stmt)
                row = result.one_or_none()

                if not row:
                    logger.warning(f"Appointment not found or not scheduled: {appointment_id}")
                    return False

                appointment, lead, property, tenant = row

                # Prepare template data
                template_data = {
                    "lead_name": lead.name or "Cliente",
                    "property_title": property.title,
                    "property_address": property.address,
                    "appointment_date": appointment.scheduled_date.strftime("%d/%m/%Y"),
                    "appointment_time": appointment.scheduled_date.strftime("%H:%M"),
                    "notes": appointment.notes,
                    "google_maps_link": self._generate_maps_link(property)
                }

                # Render message
                template = self.REMINDER_TEMPLATES.get(reminder_type)
                if not template:
                    logger.error(f"Unknown reminder type: {reminder_type}")
                    return False

                message = template.render(**template_data)

                # Send via WhatsApp
                if tenant.evo_instance_key and lead.whatsapp_id:
                    async with EvoAPIClient(tenant.evo_instance_key) as evo_client:
                        await evo_client.send_text_message(
                            to=lead.whatsapp_id,
                            message=message
                        )

                    # Update reminder status
                    if reminder_type == "24_hours":
                        appointment.reminder_24h_sent = True
                    elif reminder_type == "3_hours":
                        appointment.reminder_3h_sent = True

                    await session.commit()

                    logger.info(
                        f"Sent {reminder_type} reminder",
                        appointment_id=appointment_id,
                        lead_id=lead.id
                    )
                    return True
                else:
                    logger.error(
                        "Missing EVO instance or WhatsApp ID",
                        tenant_id=tenant.id,
                        lead_id=lead.id
                    )
                    return False

        except Exception as e:
            logger.error(
                "Error sending reminder",
                error=str(e),
                appointment_id=appointment_id,
                reminder_type=reminder_type
            )
            return False

    async def process_reminder_response(
            self,
            appointment_id: str,
            response: str,
            lead_phone: str
    ) -> Dict[str, Any]:
        """
        Process customer response to reminder
        
        Args:
            appointment_id: Appointment ID
            response: Customer response text
            lead_phone: Lead phone number
            
        Returns:
            Processing result
        """
        try:
            response_lower = response.lower().strip()

            async with get_session() as session:
                # Get appointment
                stmt = (
                    select(Appointment, Lead, Tenant)
                    .join(Lead, Appointment.lead_id == Lead.id)
                    .join(Tenant, Appointment.tenant_id == Tenant.id)
                    .where(
                        and_(
                            Appointment.id == appointment_id,
                            Lead.phone == lead_phone
                        )
                    )
                )
                result = await session.execute(stmt)
                row = result.one_or_none()

                if not row:
                    return {
                        "success": False,
                        "message": "Appointment not found"
                    }

                appointment, lead, tenant = row

                # Process confirmation
                if any(word in response_lower for word in ["sim", "confirmo", "yes", "si"]):
                    appointment.status = AppointmentStatus.CONFIRMED
                    appointment.confirmed_at = datetime.utcnow()
                    await session.commit()

                    # Send confirmation message
                    await self._send_confirmation_message(
                        tenant.evo_instance_key,
                        lead.whatsapp_id,
                        "Perfeito! Sua visita está confirmada. Te esperamos! 🏠"
                    )

                    return {
                        "success": True,
                        "action": "confirmed",
                        "message": "Appointment confirmed"
                    }

                # Process cancellation
                elif any(word in response_lower for word in ["não", "nao", "cancelar", "no", "remarcar"]):
                    appointment.status = AppointmentStatus.CANCELLED
                    appointment.cancelled_at = datetime.utcnow()
                    appointment.cancellation_reason = f"Customer response: {response}"
                    await session.commit()

                    # Send cancellation message
                    await self._send_confirmation_message(
                        tenant.evo_instance_key,
                        lead.whatsapp_id,
                        "Entendido. Sua visita foi cancelada. Se desejar reagendar, entre em contato conosco."
                    )

                    return {
                        "success": True,
                        "action": "cancelled",
                        "message": "Appointment cancelled"
                    }

                # Unknown response
                else:
                    await self._send_confirmation_message(
                        tenant.evo_instance_key,
                        lead.whatsapp_id,
                        "Por favor, responda com SIM para confirmar ou NÃO para cancelar a visita."
                    )

                    return {
                        "success": True,
                        "action": "unknown",
                        "message": "Unknown response, clarification requested"
                    }

        except Exception as e:
            logger.error(
                "Error processing reminder response",
                error=str(e),
                appointment_id=appointment_id
            )
            return {
                "success": False,
                "error": str(e)
            }

    def _generate_maps_link(self, property: Property) -> Optional[str]:
        """Generate Google Maps link for property"""
        if property.latitude and property.longitude:
            return f"https://maps.google.com/?q={property.latitude},{property.longitude}"
        elif property.address:
            # Encode address for URL
            from urllib.parse import quote
            address = f"{property.address}, {property.city}, {property.state}"
            return f"https://maps.google.com/?q={quote(address)}"
        return None

    async def _send_confirmation_message(
            self,
            evo_instance: str,
            whatsapp_id: str,
            message: str
    ):
        """Send confirmation message via WhatsApp"""
        try:
            async with EvoAPIClient(evo_instance) as evo_client:
                await evo_client.send_text_message(
                    to=whatsapp_id,
                    message=message
                )
        except Exception as e:
            logger.error("Error sending confirmation message", error=str(e))

    async def get_upcoming_appointments(
            self,
            hours_ahead: int = 48
    ) -> List[Appointment]:
        """
        Get appointments scheduled in the next X hours
        
        Args:
            hours_ahead: Number of hours to look ahead
            
        Returns:
            List of upcoming appointments
        """
        try:
            cutoff_time = datetime.utcnow() + timedelta(hours=hours_ahead)

            async with get_session() as session:
                stmt = (
                    select(Appointment)
                    .where(
                        and_(
                            Appointment.status == AppointmentStatus.SCHEDULED,
                            Appointment.scheduled_date > datetime.utcnow(),
                            Appointment.scheduled_date <= cutoff_time
                        )
                    )
                    .options(
                        selectinload(Appointment.lead),
                        selectinload(Appointment.property),
                        selectinload(Appointment.tenant)
                    )
                )
                result = await session.execute(stmt)
                return result.scalars().all()

        except Exception as e:
            logger.error("Error getting upcoming appointments", error=str(e))
            return []


# Celery tasks
@celery_app.task
def send_appointment_reminder(appointment_id: str, reminder_type: str):
    """Celery task to send appointment reminder"""
    service = AppointmentReminderService()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            service.send_reminder(appointment_id, reminder_type)
        )
        return result
    finally:
        loop.close()


@celery_app.task
def check_upcoming_appointments():
    """Celery task to check and schedule reminders for upcoming appointments"""
    service = AppointmentReminderService()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        appointments = loop.run_until_complete(
            service.get_upcoming_appointments(hours_ahead=48)
        )

        scheduled_count = 0
        for appointment in appointments:
            # Check if reminders need to be scheduled
            hours_until = (appointment.scheduled_date - datetime.utcnow()).total_seconds() / 3600

            # Schedule 24h reminder if not sent and time is right
            if not appointment.reminder_24h_sent and 23 <= hours_until <= 25:
                send_appointment_reminder.apply_async(
                    args=[str(appointment.id), "24_hours"],
                    countdown=60  # Send in 1 minute
                )
                scheduled_count += 1

            # Schedule 3h reminder if not sent and time is right
            if not appointment.reminder_3h_sent and 2.5 <= hours_until <= 3.5:
                send_appointment_reminder.apply_async(
                    args=[str(appointment.id), "3_hours"],
                    countdown=60  # Send in 1 minute
                )
                scheduled_count += 1

        logger.info(f"Scheduled {scheduled_count} reminders for {len(appointments)} appointments")
        return scheduled_count

    finally:
        loop.close()
