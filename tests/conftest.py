"""
Pytest configuration and fixtures
"""
import os
import sys
import asyncio
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load test environment
load_dotenv('.env.test')
os.environ['TESTING'] = 'true'

from src.database.models import Base
from src.core.config import get_settings

# Override settings for testing
settings = get_settings()
settings.DATABASE_URL = os.getenv('TEST_DATABASE_URL', 'postgresql+asyncpg://postgres:postgres@localhost:5432/corretor_test')
settings.TESTING = True


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create test database engine"""
    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=False
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async session for tests"""
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_settings(monkeypatch):
    """Mock settings for testing"""
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/corretor_test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setenv("OPENAI_API_KEY", "test_key")
    return get_settings()


@pytest.fixture
def sample_tenant_data():
    """Sample tenant data for testing"""
    return {
        "name": "Test Agent",
        "email": "test@example.com",
        "phone": "+5511999999999",
        "company_name": "Test Realty",
        "evo_instance_key": "test_instance",
        "chatwoot_inbox_id": 1,
        "google_calendar_id": "test@gmail.com",
        "qdrant_namespace": "test_namespace"
    }


@pytest.fixture
def sample_property_data():
    """Sample property data for testing"""
    return {
        "title": "Beautiful House in Buenos Aires",
        "description": "A stunning 3-bedroom house",
        "property_type": "house",
        "address": "Av. Libertador 1234",
        "neighborhood": "Palermo",
        "city": "Buenos Aires",
        "state": "Buenos Aires",
        "country": "Argentina",
        "postal_code": "1425",
        "latitude": -34.5795,
        "longitude": -58.4089,
        "bedrooms": 3,
        "bathrooms": 2,
        "area": 150.0,
        "built_area": 130.0,
        "price": 250000.0,
        "currency": "USD",
        "listing_type": "sale",
        "features": ["garage", "garden", "pool"],
        "amenities": ["security", "gym"],
        "images": ["https://example.com/image1.jpg"],
        "source_url": "https://www.remax.com.ar/listing/12345"
    }


@pytest.fixture
def sample_lead_data():
    """Sample lead data for testing"""
    return {
        "name": "John Doe",
        "phone": "+5491155555555",
        "email": "john@example.com",
        "whatsapp_id": "5491155555555@s.whatsapp.net",
        "preferences": {
            "bedrooms": 3,
            "min_area": 100,
            "max_area": 200
        },
        "budget_min": 200000,
        "budget_max": 300000,
        "preferred_locations": ["Palermo", "Recoleta"],
        "property_type_interest": ["house", "apartment"],
        "source": "whatsapp"
    }


@pytest.fixture
def sample_conversation_data():
    """Sample conversation data for testing"""
    return {
        "evo_chat_id": "5491155555555@s.whatsapp.net",
        "chatwoot_conversation_id": 123,
        "status": "active",
        "ai_enabled": True,
        "handoff_requested": False
    }


@pytest.fixture
def sample_appointment_data():
    """Sample appointment data for testing"""
    from datetime import datetime, timedelta
    
    return {
        "scheduled_date": datetime.utcnow() + timedelta(days=2),
        "duration_minutes": 60,
        "notes": "Cliente muito interessado",
        "location_details": "Portaria principal",
        "status": "scheduled"
    }


# Mock external services
@pytest.fixture
def mock_evo_api(monkeypatch):
    """Mock EVO API client"""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.send_text_message = AsyncMock(return_value={"success": True})
    mock_client.send_media_message = AsyncMock(return_value={"success": True})
    mock_client.get_instance_info = AsyncMock(return_value={"status": "connected"})
    
    monkeypatch.setattr("src.integrations.evo_api.EvoAPIClient", lambda *args, **kwargs: mock_client)
    return mock_client


@pytest.fixture
def mock_openai(monkeypatch):
    """Mock OpenAI client"""
    from unittest.mock import AsyncMock, MagicMock
    
    mock_client = AsyncMock()
    
    # Mock chat completion
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Mocked AI response"
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    # Mock audio transcription
    mock_transcription = MagicMock()
    mock_transcription.text = "Mocked transcription"
    mock_transcription.language = "pt"
    mock_transcription.duration = 5.0
    mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_transcription)
    
    monkeypatch.setattr("openai.AsyncOpenAI", lambda *args, **kwargs: mock_client)
    return mock_client


@pytest.fixture
def mock_chatwoot(monkeypatch):
    """Mock Chatwoot client"""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.create_contact = AsyncMock(return_value={"id": 1})
    mock_client.create_conversation = AsyncMock(return_value={"id": 1})
    mock_client.send_message = AsyncMock(return_value={"id": 1})
    
    monkeypatch.setattr("src.integrations.chatwoot.ChatwootClient", lambda *args, **kwargs: mock_client)
    return mock_client


@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis client"""
    from unittest.mock import AsyncMock
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.set = AsyncMock(return_value=True)
    mock_client.delete = AsyncMock(return_value=True)
    mock_client.expire = AsyncMock(return_value=True)
    
    monkeypatch.setattr("src.integrations.redis.redis_client", mock_client)
    return mock_client