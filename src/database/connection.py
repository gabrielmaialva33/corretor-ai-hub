"""
Database connection and session management
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.APP_DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    poolclass=NullPool if settings.APP_DEBUG else None
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session
    
    Usage:
        async with get_session() as session:
            # Use session here
            pass
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_database():
    """Initialize database tables"""
    try:
        from src.database.models import Base

        async with engine.begin() as conn:
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables initialized")

    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def check_database_connection():
    """Check if database is accessible"""
    try:
        async with get_session() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error("Database connection check failed", error=str(e))
        return False
