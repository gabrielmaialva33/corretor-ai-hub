"""
Supabase integration
"""
from typing import Optional

import structlog

from src.core.config import get_settings
from supabase import create_client, Client

logger = structlog.get_logger()
settings = get_settings()

# Global client instance
supabase_client: Optional[Client] = None


async def init_supabase():
    """Initialize Supabase client"""
    global supabase_client

    try:
        supabase_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )

        # Test connection
        supabase_client.table("tenants").select("id").limit(1).execute()

        logger.info("Supabase client initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize Supabase client", error=str(e))
        raise


def get_supabase_client() -> Client:
    """Get Supabase client instance"""
    if not supabase_client:
        raise RuntimeError("Supabase client not initialized")
    return supabase_client
