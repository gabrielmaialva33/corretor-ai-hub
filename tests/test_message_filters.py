"""
Tests for message filtering functionality
"""
import pytest
from datetime import datetime, timedelta
from src.utils.message_filters import MessageFilter
from src.database.models import Tenant, Lead, Conversation, Message
from src.database.connection import get_session
from sqlalchemy import select


@pytest.fixture
async def test_tenant(async_session):
    """Create a test tenant"""
    tenant = Tenant(
        name="Test Agent",
        email="test@example.com",
        phone="+5511999999999",
        evo_instance_key="test_instance",
        automation_config={
            "require_new_contact": True,
            "require_portal_link": True,
            "new_contact_hours": 24,
            "allowed_portals": ["zonaprop", "mercadolibre"]
        }
    )
    async_session.add(tenant)
    await async_session.commit()
    return tenant


@pytest.fixture
async def existing_lead(async_session, test_tenant):
    """Create an existing lead"""
    lead = Lead(
        tenant_id=test_tenant.id,
        phone="+5511888888888",
        name="Existing Customer",
        status="active"
    )
    async_session.add(lead)
    await async_session.commit()
    return lead


class TestMessageFilter:
    """Test message filtering functionality"""
    
    def test_extract_portal_links(self):
        """Test extraction of real estate portal links"""
        # Test with single link
        message = "Olá, gostaria de saber sobre https://www.zonaprop.com.ar/propiedades/casa-en-venta-45678.html"
        links = MessageFilter.extract_portal_links(message)
        
        assert len(links) == 1
        assert links[0]["portal"] == "zonaprop"
        assert "45678" in links[0]["url"]
        
        # Test with multiple links
        message = """
        Vi estes imóveis:
        https://www.mercadolibre.com.ar/MLA-12345
        www.argenprop.com/detalles/9876
        E também este: zonaprop.com.ar/propiedades/depto-54321.html
        """
        links = MessageFilter.extract_portal_links(message)
        
        assert len(links) == 3
        portals = [link["portal"] for link in links]
        assert "mercadolibre" in portals
        assert "argenprop" in portals
        assert "zonaprop" in portals
        
        # Test without links
        message = "Preciso de um apartamento de 2 quartos"
        links = MessageFilter.extract_portal_links(message)
        assert len(links) == 0
    
    async def test_is_new_contact(self, test_tenant):
        """Test new contact detection"""
        # Test with completely new contact
        is_new = await MessageFilter.is_new_contact(
            str(test_tenant.id),
            "+5511777777777",
            24
        )
        assert is_new is True
        
    async def test_is_not_new_contact(self, test_tenant, existing_lead):
        """Test existing contact detection"""
        # Create a recent conversation
        async with get_session() as session:
            conversation = Conversation(
                tenant_id=test_tenant.id,
                lead_id=existing_lead.id,
                evo_chat_id="test_chat",
                last_message_at=datetime.utcnow() - timedelta(hours=2)
            )
            session.add(conversation)
            await session.commit()
        
        # Test with existing contact with recent activity
        is_new = await MessageFilter.is_new_contact(
            str(test_tenant.id),
            existing_lead.phone,
            24
        )
        assert is_new is False
        
        # Test with shorter window
        is_new = await MessageFilter.is_new_contact(
            str(test_tenant.id),
            existing_lead.phone,
            1  # Only 1 hour
        )
        assert is_new is True  # Should be considered new since last message was 2 hours ago
    
    async def test_should_activate_automation_new_with_link(self, test_tenant):
        """Test automation activation for new contact with portal link"""
        message = "Olá, vi este imóvel: https://www.zonaprop.com.ar/propiedades/casa-123.html"
        
        result = await MessageFilter.should_activate_automation(
            str(test_tenant.id),
            "+5511666666666",
            message,
            test_tenant.automation_config
        )
        
        assert result["activate"] is True
        assert result["is_new_contact"] is True
        assert result["has_portal_link"] is True
        assert len(result["portal_links"]) == 1
        assert result["portal_links"][0]["portal"] == "zonaprop"
    
    async def test_should_not_activate_automation_disallowed_portal(self, test_tenant):
        """Test automation not activated for disallowed portal"""
        message = "Vi este imóvel: https://www.properati.com.ar/detalles/casa-456"
        
        result = await MessageFilter.should_activate_automation(
            str(test_tenant.id),
            "+5511555555555",
            message,
            test_tenant.automation_config
        )
        
        assert result["activate"] is False
        assert result["reason"] == "no_portal_link"  # Portal not in allowed list
        assert result["is_new_contact"] is True
    
    async def test_should_not_activate_existing_contact(self, test_tenant, existing_lead):
        """Test automation not activated for existing contact"""
        # Create recent conversation
        async with get_session() as session:
            conversation = Conversation(
                tenant_id=test_tenant.id,
                lead_id=existing_lead.id,
                evo_chat_id="test_chat_2",
                last_message_at=datetime.utcnow() - timedelta(hours=2)
            )
            session.add(conversation)
            await session.commit()
        
        message = "Vi este imóvel: https://www.zonaprop.com.ar/propiedades/casa-789.html"
        
        result = await MessageFilter.should_activate_automation(
            str(test_tenant.id),
            existing_lead.phone,
            message,
            test_tenant.automation_config
        )
        
        assert result["activate"] is False
        assert result["reason"] == "not_new_contact"
        assert result["has_portal_link"] is True
    
    def test_extract_property_id_from_url(self):
        """Test property ID extraction from URLs"""
        # Test different portal formats
        test_cases = [
            ("https://www.zonaprop.com.ar/propiedades/45678-casa-en-venta.html", "zonaprop_45678"),
            ("https://www.mercadolibre.com.ar/MLA-12345-departamento", "mercadolibre_12345"),
            ("https://www.argenprop.com/detalles/9876", "argenprop_9876"),
            ("https://www.remax.com.ar/listing/54321", "remax_54321"),
        ]
        
        for url, expected_id in test_cases:
            property_id = MessageFilter.extract_property_id_from_url(url)
            assert property_id == expected_id
    
    async def test_get_message_context(self, test_tenant, existing_lead):
        """Test retrieval of message context"""
        # Create conversation and messages
        async with get_session() as session:
            conversation = Conversation(
                tenant_id=test_tenant.id,
                lead_id=existing_lead.id,
                evo_chat_id="test_chat_3"
            )
            session.add(conversation)
            await session.commit()
            
            # Add some messages
            for i in range(3):
                message = Message(
                    conversation_id=conversation.id,
                    content=f"Test message {i}",
                    message_type="text",
                    sender_type="customer" if i % 2 == 0 else "bot",
                    sender_id=existing_lead.phone,
                    created_at=datetime.utcnow() - timedelta(minutes=30-i*10)
                )
                session.add(message)
            await session.commit()
        
        # Get message context
        context = await MessageFilter.get_message_context(
            str(test_tenant.id),
            existing_lead.phone,
            limit=5
        )
        
        assert len(context) == 3
        assert context[0]["content"] == "Test message 2"  # Most recent
        assert context[-1]["content"] == "Test message 0"  # Oldest