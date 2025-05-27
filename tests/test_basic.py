"""
Basic tests to verify test environment setup
"""
import pytest
from datetime import datetime
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_environment():
    """Test that environment is set correctly"""
    assert os.getenv('TESTING') == 'true' or os.getenv('ENVIRONMENT') == 'test'


def test_imports():
    """Test that all main modules can be imported"""
    try:
        from src.core.config import get_settings
        from src.database.models import Base, Tenant, Lead, Property
        from src.api.main import app
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import modules: {e}")


@pytest.mark.asyncio
async def test_database_connection(async_session):
    """Test database connection works"""
    # Simple query to test connection
    result = await async_session.execute("SELECT 1")
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_create_tenant(async_session, sample_tenant_data):
    """Test creating a tenant in database"""
    from src.database.models import Tenant
    
    tenant = Tenant(**sample_tenant_data)
    async_session.add(tenant)
    await async_session.commit()
    
    assert tenant.id is not None
    assert tenant.email == sample_tenant_data["email"]


def test_property_matcher_import():
    """Test property matcher can be imported"""
    try:
        from src.services.property_matcher import PropertyMatcher
        matcher = PropertyMatcher()
        assert matcher is not None
    except ImportError as e:
        pytest.fail(f"Failed to import PropertyMatcher: {e}")


def test_media_processor_import():
    """Test media processor can be imported"""
    try:
        from src.services.media_processor import MediaProcessor
        # Don't instantiate as it requires OpenAI key
        assert MediaProcessor is not None
    except ImportError as e:
        pytest.fail(f"Failed to import MediaProcessor: {e}")


def test_message_filters_import():
    """Test message filters can be imported"""
    try:
        from src.utils.message_filters import MessageFilter
        assert MessageFilter is not None
    except ImportError as e:
        pytest.fail(f"Failed to import MessageFilter: {e}")


@pytest.mark.asyncio
async def test_webhook_processor_import():
    """Test webhook processor can be imported"""
    try:
        from src.services.webhook_processor import WebhookProcessor
        # Don't instantiate as it requires services
        assert WebhookProcessor is not None
    except ImportError as e:
        pytest.fail(f"Failed to import WebhookProcessor: {e}")