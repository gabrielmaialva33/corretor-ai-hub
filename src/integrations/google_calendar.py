"""
Google Calendar Integration for appointment scheduling
"""
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import structlog
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import select

from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import Property, Lead, Appointment

logger = structlog.get_logger()
settings = get_settings()


class GoogleCalendarClient:
    """
    Client for Google Calendar API integration
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.scopes = [settings.GOOGLE_CALENDAR_SCOPES]
        self.service = None
        self._initialize_service()

    def _get_credentials_path(self) -> str:
        """Get tenant-specific credentials path"""
        base_path = os.path.dirname(settings.GOOGLE_CALENDAR_TOKEN_PATH)
        return os.path.join(base_path, f"token_{self.tenant_id}.json")

    def _initialize_service(self):
        """Initialize Google Calendar service"""
        creds = None
        token_path = self._get_credentials_path()

        # Load existing token
        if os.path.exists(token_path):
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(settings.GOOGLE_CALENDAR_CREDENTIALS_PATH):
                    raise FileNotFoundError(
                        f"Credentials file not found: {settings.GOOGLE_CALENDAR_CREDENTIALS_PATH}"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.GOOGLE_CALENDAR_CREDENTIALS_PATH,
                    self.scopes
                )
                creds = flow.run_local_server(port=0)

            # Save the credentials for the next run
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('calendar', 'v3', credentials=creds)

    async def get_calendar_id(self) -> str:
        """
        Get or create tenant-specific calendar
        
        Returns:
            Calendar ID
        """
        try:
            # List all calendars
            calendar_list = self.service.calendarList().list().execute()

            # Look for tenant calendar
            calendar_name = f"Corretor AI - {self.tenant_id}"
            for calendar in calendar_list.get('items', []):
                if calendar.get('summary') == calendar_name:
                    return calendar['id']

            # Create new calendar if not found
            calendar_body = {
                'summary': calendar_name,
                'description': f'Agenda de visitas do corretor {self.tenant_id}',
                'timeZone': 'America/Sao_Paulo'
            }

            created_calendar = self.service.calendars().insert(
                body=calendar_body
            ).execute()

            return created_calendar['id']

        except HttpError as error:
            logger.error(f"Error getting calendar ID: {error}")
            raise

    async def create_appointment_event(
            self,
            appointment_id: str,
            property_id: str,
            scheduled_at: datetime,
            duration_minutes: int = 60,
            notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a calendar event for property viewing
        
        Args:
            appointment_id: Appointment ID
            property_id: Property ID
            scheduled_at: Appointment datetime
            duration_minutes: Duration in minutes
            notes: Additional notes
        
        Returns:
            Created event data
        """
        try:
            # Get property and lead information
            async with get_session() as session:
                # Get appointment with property and lead
                stmt = select(Appointment).where(Appointment.id == appointment_id)
                result = await session.execute(stmt)
                appointment = result.scalar_one_or_none()

                if not appointment:
                    raise ValueError(f"Appointment {appointment_id} not found")

                # Get property
                stmt = select(Property).where(Property.id == property_id)
                result = await session.execute(stmt)
                property = result.scalar_one_or_none()

                # Get lead
                stmt = select(Lead).where(Lead.id == appointment.lead_id)
                result = await session.execute(stmt)
                lead = result.scalar_one_or_none()

            # Build event
            event = {
                'summary': f'Visita: {property.title if property else "Imóvel"}',
                'location': self._format_location(property),
                'description': self._format_description(property, lead, notes),
                'start': {
                    'dateTime': scheduled_at.isoformat(),
                    'timeZone': 'America/Sao_Paulo',
                },
                'end': {
                    'dateTime': (scheduled_at + timedelta(minutes=duration_minutes)).isoformat(),
                    'timeZone': 'America/Sao_Paulo',
                },
                'attendees': self._format_attendees(lead),
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                        {'method': 'popup', 'minutes': 60},  # 1 hour before
                    ],
                },
                'colorId': '3',  # Purple color for property viewings
            }

            # Get calendar ID
            calendar_id = await self.get_calendar_id()

            # Create event
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event,
                sendNotifications=True
            ).execute()

            logger.info(
                f"Created calendar event",
                event_id=created_event['id'],
                appointment_id=appointment_id
            )

            return created_event

        except HttpError as error:
            logger.error(f"Error creating event: {error}")
            raise

    async def update_appointment_event(
            self,
            event_id: str,
            updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event
        
        Args:
            event_id: Google Calendar event ID
            updates: Fields to update
        
        Returns:
            Updated event data
        """
        try:
            calendar_id = await self.get_calendar_id()

            # Get existing event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            # Apply updates
            if 'scheduled_at' in updates:
                event['start']['dateTime'] = updates['scheduled_at'].isoformat()
                if 'duration_minutes' in updates:
                    end_time = updates['scheduled_at'] + timedelta(minutes=updates['duration_minutes'])
                else:
                    # Calculate duration from existing event
                    start = datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
                    end = datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
                    duration = end - start
                    end_time = updates['scheduled_at'] + duration
                event['end']['dateTime'] = end_time.isoformat()

            if 'notes' in updates:
                event['description'] = updates['notes'] + "\n\n" + event.get('description', '')

            # Update event
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendNotifications=True
            ).execute()

            return updated_event

        except HttpError as error:
            logger.error(f"Error updating event: {error}")
            raise

    async def cancel_appointment_event(
            self,
            event_id: str,
            cancellation_reason: Optional[str] = None
    ) -> bool:
        """
        Cancel a calendar event
        
        Args:
            event_id: Google Calendar event ID
            cancellation_reason: Reason for cancellation
        
        Returns:
            True if cancelled successfully
        """
        try:
            calendar_id = await self.get_calendar_id()

            # Update event status to cancelled
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()

            event['status'] = 'cancelled'
            if cancellation_reason:
                event['description'] = f"CANCELADO: {cancellation_reason}\n\n" + event.get('description', '')

            # Update event
            self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event,
                sendNotifications=True
            ).execute()

            return True

        except HttpError as error:
            logger.error(f"Error cancelling event: {error}")
            return False

    async def get_available_slots(
            self,
            date: datetime,
            duration_minutes: int = 60,
            business_hours: Dict[str, int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get available time slots for a specific date
        
        Args:
            date: Date to check
            duration_minutes: Appointment duration
            business_hours: Business hours configuration
        
        Returns:
            List of available time slots
        """
        if business_hours is None:
            business_hours = {
                "start": 8,  # 8 AM
                "end": 19,  # 7 PM
                "break_start": 12,  # 12 PM
                "break_end": 13  # 1 PM
            }

        try:
            calendar_id = await self.get_calendar_id()

            # Set time range for the day
            time_min = datetime.combine(date.date(), datetime.min.time()).replace(
                hour=business_hours["start"]
            )
            time_max = datetime.combine(date.date(), datetime.min.time()).replace(
                hour=business_hours["end"]
            )

            # Get events for the day
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Calculate available slots
            available_slots = []
            current_time = time_min

            for event in events:
                if 'dateTime' not in event['start']:
                    continue

                event_start = datetime.fromisoformat(
                    event['start']['dateTime'].replace('Z', '+00:00')
                )
                event_end = datetime.fromisoformat(
                    event['end']['dateTime'].replace('Z', '+00:00')
                )

                # Add available slots before this event
                while current_time + timedelta(minutes=duration_minutes) <= event_start:
                    # Skip lunch break
                    if current_time.hour >= business_hours.get("break_start", 12) and \
                            current_time.hour < business_hours.get("break_end", 13):
                        current_time = current_time.replace(
                            hour=business_hours.get("break_end", 13),
                            minute=0
                        )
                        continue

                    available_slots.append({
                        "start": current_time.isoformat(),
                        "end": (current_time + timedelta(minutes=duration_minutes)).isoformat(),
                        "available": True
                    })
                    current_time += timedelta(minutes=30)  # 30-minute intervals

                # Move to after the event
                current_time = max(current_time, event_end)

            # Add remaining slots after last event
            while current_time + timedelta(minutes=duration_minutes) <= time_max:
                # Skip lunch break
                if current_time.hour >= business_hours.get("break_start", 12) and \
                        current_time.hour < business_hours.get("break_end", 13):
                    current_time = current_time.replace(
                        hour=business_hours.get("break_end", 13),
                        minute=0
                    )
                    continue

                available_slots.append({
                    "start": current_time.isoformat(),
                    "end": (current_time + timedelta(minutes=duration_minutes)).isoformat(),
                    "available": True
                })
                current_time += timedelta(minutes=30)

            return available_slots

        except HttpError as error:
            logger.error(f"Error getting available slots: {error}")
            return []

    def _format_location(self, property: Optional[Property]) -> str:
        """Format property location for calendar event"""
        if not property:
            return ""

        parts = []
        if property.address:
            parts.append(property.address)
        if property.neighborhood:
            parts.append(property.neighborhood)
        if property.city:
            parts.append(property.city)
        if property.state:
            parts.append(property.state)

        return ", ".join(parts)

    def _format_description(
            self,
            property: Optional[Property],
            lead: Optional[Lead],
            notes: Optional[str]
    ) -> str:
        """Format event description"""
        lines = []

        if property:
            lines.append(f"🏠 Imóvel: {property.title}")
            lines.append(f"💰 Preço: R$ {property.price:,.2f}")
            if property.bedrooms:
                lines.append(f"🛏️ Quartos: {property.bedrooms}")
            if property.total_area:
                lines.append(f"📐 Área: {property.total_area} m²")
            lines.append("")

        if lead:
            lines.append(f"👤 Cliente: {lead.name or 'Não informado'}")
            lines.append(f"📱 Telefone: {lead.phone}")
            if lead.email:
                lines.append(f"✉️ Email: {lead.email}")
            lines.append("")

        if notes:
            lines.append("📝 Observações:")
            lines.append(notes)

        return "\n".join(lines)

    def _format_attendees(self, lead: Optional[Lead]) -> List[Dict[str, str]]:
        """Format attendees list"""
        attendees = []

        if lead and lead.email:
            attendees.append({
                'email': lead.email,
                'displayName': lead.name or lead.email,
                'responseStatus': 'needsAction'
            })

        return attendees
