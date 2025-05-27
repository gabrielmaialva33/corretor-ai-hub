"""
Tests for appointment reminder service
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.appointment_reminder import AppointmentReminderService
from src.database.models import Appointment, Lead, Property, Tenant, AppointmentStatus


class TestAppointmentReminder:
    """Test appointment reminder functionality"""
    
    @pytest.fixture
    def reminder_service(self):
        """Create reminder service instance"""
        return AppointmentReminderService()
    
    @pytest.fixture
    async def test_appointment(self, async_session, sample_tenant_data, sample_lead_data, sample_property_data):
        """Create test appointment with related data"""
        from src.database.models import Tenant, Lead, Property, Appointment
        
        # Create tenant
        tenant = Tenant(**sample_tenant_data)
        async_session.add(tenant)
        
        # Create lead
        lead = Lead(tenant_id=tenant.id, **sample_lead_data)
        async_session.add(lead)
        
        # Create property
        property_data = sample_property_data.copy()
        property_data['tenant_id'] = tenant.id
        property = Property(**property_data)
        async_session.add(property)
        
        # Create appointment
        appointment = Appointment(
            tenant_id=tenant.id,
            lead_id=lead.id,
            property_id=property.id,
            scheduled_date=datetime.utcnow() + timedelta(days=2),
            duration_minutes=60,
            status=AppointmentStatus.SCHEDULED,
            notes="Test appointment"
        )
        async_session.add(appointment)
        
        await async_session.commit()
        
        return {
            "appointment": appointment,
            "lead": lead,
            "property": property,
            "tenant": tenant
        }
    
    @pytest.mark.asyncio
    async def test_send_reminder_24h(self, reminder_service, test_appointment, mock_evo_api):
        """Test sending 24-hour reminder"""
        appointment_data = await test_appointment
        appointment = appointment_data["appointment"]
        
        # Send reminder
        result = await reminder_service.send_reminder(
            str(appointment.id),
            "24_hours"
        )
        
        assert result is True
        
        # Verify EVO API was called
        mock_evo_api.send_text_message.assert_called_once()
        call_args = mock_evo_api.send_text_message.call_args
        
        # Check message content
        message = call_args[1]["message"]
        assert "visita agendada amanhã" in message
        assert appointment_data["property"].title in message
        assert appointment_data["property"].address in message
    
    @pytest.mark.asyncio
    async def test_send_reminder_3h(self, reminder_service, test_appointment, mock_evo_api):
        """Test sending 3-hour reminder"""
        appointment_data = await test_appointment
        appointment = appointment_data["appointment"]
        
        # Send reminder
        result = await reminder_service.send_reminder(
            str(appointment.id),
            "3_hours"
        )
        
        assert result is True
        
        # Check message content
        call_args = mock_evo_api.send_text_message.call_args
        message = call_args[1]["message"]
        assert "em 3 horas" in message
        assert appointment_data["property"].address in message
    
    @pytest.mark.asyncio
    async def test_process_confirmation_response(self, reminder_service, test_appointment):
        """Test processing confirmation responses"""
        appointment_data = await test_appointment
        appointment = appointment_data["appointment"]
        lead = appointment_data["lead"]
        
        # Mock EVO API
        with patch('src.services.appointment_reminder.EvoAPIClient') as mock_evo:
            mock_client = AsyncMock()
            mock_client.send_text_message = AsyncMock()
            mock_evo.return_value.__aenter__.return_value = mock_client
            
            # Test confirmation
            result = await reminder_service.process_reminder_response(
                str(appointment.id),
                "Sim, confirmo",
                lead.phone
            )
            
            assert result["success"] is True
            assert result["action"] == "confirmed"
            
            # Verify confirmation message was sent
            mock_client.send_text_message.assert_called_once()
            confirm_msg = mock_client.send_text_message.call_args[1]["message"]
            assert "confirmada" in confirm_msg
    
    @pytest.mark.asyncio
    async def test_process_cancellation_response(self, reminder_service, test_appointment):
        """Test processing cancellation responses"""
        appointment_data = await test_appointment
        appointment = appointment_data["appointment"]
        lead = appointment_data["lead"]
        
        # Mock EVO API
        with patch('src.services.appointment_reminder.EvoAPIClient') as mock_evo:
            mock_client = AsyncMock()
            mock_client.send_text_message = AsyncMock()
            mock_evo.return_value.__aenter__.return_value = mock_client
            
            # Test cancellation
            result = await reminder_service.process_reminder_response(
                str(appointment.id),
                "Não posso ir",
                lead.phone
            )
            
            assert result["success"] is True
            assert result["action"] == "cancelled"
            
            # Verify cancellation message was sent
            cancel_msg = mock_client.send_text_message.call_args[1]["message"]
            assert "cancelada" in cancel_msg
    
    @pytest.mark.asyncio
    async def test_process_unknown_response(self, reminder_service, test_appointment):
        """Test processing unknown responses"""
        appointment_data = await test_appointment
        appointment = appointment_data["appointment"]
        lead = appointment_data["lead"]
        
        # Mock EVO API
        with patch('src.services.appointment_reminder.EvoAPIClient') as mock_evo:
            mock_client = AsyncMock()
            mock_client.send_text_message = AsyncMock()
            mock_evo.return_value.__aenter__.return_value = mock_client
            
            # Test unknown response
            result = await reminder_service.process_reminder_response(
                str(appointment.id),
                "talvez eu vá",
                lead.phone
            )
            
            assert result["success"] is True
            assert result["action"] == "unknown"
            
            # Verify clarification was requested
            clarify_msg = mock_client.send_text_message.call_args[1]["message"]
            assert "SIM" in clarify_msg
            assert "NÃO" in clarify_msg
    
    @pytest.mark.asyncio
    async def test_get_upcoming_appointments(self, reminder_service, async_session):
        """Test getting upcoming appointments"""
        from src.database.models import Tenant, Lead, Property, Appointment
        
        # Create test data
        tenant = Tenant(
            name="Test Agent",
            email="test@example.com",
            phone="+5511999999999"
        )
        async_session.add(tenant)
        
        lead = Lead(
            tenant_id=tenant.id,
            name="Test Lead",
            phone="+5511888888888"
        )
        async_session.add(lead)
        
        property = Property(
            tenant_id=tenant.id,
            title="Test Property",
            price=100000,
            address="Test Address",
            city="Test City"
        )
        async_session.add(property)
        
        # Create appointments at different times
        appointments = []
        
        # Upcoming appointment (should be included)
        apt1 = Appointment(
            tenant_id=tenant.id,
            lead_id=lead.id,
            property_id=property.id,
            scheduled_date=datetime.utcnow() + timedelta(hours=12),
            status=AppointmentStatus.SCHEDULED
        )
        appointments.append(apt1)
        async_session.add(apt1)
        
        # Past appointment (should not be included)
        apt2 = Appointment(
            tenant_id=tenant.id,
            lead_id=lead.id,
            property_id=property.id,
            scheduled_date=datetime.utcnow() - timedelta(hours=1),
            status=AppointmentStatus.SCHEDULED
        )
        async_session.add(apt2)
        
        # Far future appointment (should not be included with 48h window)
        apt3 = Appointment(
            tenant_id=tenant.id,
            lead_id=lead.id,
            property_id=property.id,
            scheduled_date=datetime.utcnow() + timedelta(days=5),
            status=AppointmentStatus.SCHEDULED
        )
        async_session.add(apt3)
        
        # Cancelled appointment (should not be included)
        apt4 = Appointment(
            tenant_id=tenant.id,
            lead_id=lead.id,
            property_id=property.id,
            scheduled_date=datetime.utcnow() + timedelta(hours=6),
            status=AppointmentStatus.CANCELLED
        )
        async_session.add(apt4)
        
        await async_session.commit()
        
        # Get upcoming appointments
        upcoming = await reminder_service.get_upcoming_appointments(hours_ahead=48)
        
        # Should only include apt1
        assert len(upcoming) == 1
        assert upcoming[0].id == apt1.id
    
    def test_generate_maps_link(self, reminder_service):
        """Test Google Maps link generation"""
        from src.database.models import Property
        
        # Test with coordinates
        property1 = Property(
            title="Test",
            price=100000,
            address="Test Address",
            city="Buenos Aires",
            latitude=-34.5795,
            longitude=-58.4089
        )
        link1 = reminder_service._generate_maps_link(property1)
        assert link1 == "https://maps.google.com/?q=-34.5795,-58.4089"
        
        # Test with address only
        property2 = Property(
            title="Test",
            price=100000,
            address="Av. Libertador 1234",
            city="Buenos Aires",
            state="Buenos Aires"
        )
        link2 = reminder_service._generate_maps_link(property2)
        assert "Av.+Libertador+1234" in link2
        assert "Buenos+Aires" in link2
    
    def test_reminder_templates(self, reminder_service):
        """Test reminder template rendering"""
        # Test 24h template
        template_24h = reminder_service.REMINDER_TEMPLATES["24_hours"]
        rendered = template_24h.render(
            lead_name="João Silva",
            property_title="Casa em Palermo",
            appointment_date="25/12/2023",
            appointment_time="15:00",
            property_address="Av. Santa Fe 1234",
            notes="Levar documentos"
        )
        
        assert "João Silva" in rendered
        assert "Casa em Palermo" in rendered
        assert "25/12/2023" in rendered
        assert "15:00" in rendered
        assert "Av. Santa Fe 1234" in rendered
        assert "Levar documentos" in rendered
        
        # Test 3h template
        template_3h = reminder_service.REMINDER_TEMPLATES["3_hours"]
        rendered = template_3h.render(
            lead_name="Maria Santos",
            property_title="Apartamento Recoleta",
            appointment_time="10:00",
            property_address="Av. Callao 456",
            google_maps_link="https://maps.google.com/test"
        )
        
        assert "Maria Santos" in rendered
        assert "10:00" in rendered
        assert "em 3 horas" in rendered
        assert "https://maps.google.com/test" in rendered