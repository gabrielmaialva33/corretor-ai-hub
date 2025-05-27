"""
Corretor AI Hub - Main FastAPI Application
"""
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from src.api.routes import router
from src.core.config import get_settings
from src.core.exceptions import setup_exception_handlers
from src.core.logging import setup_logging
from src.integrations.qdrant import init_qdrant
from src.integrations.redis import init_redis
from src.integrations.supabase import init_supabase

# Setup logging
setup_logging()
logger = structlog.get_logger()

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle
    """
    # Startup
    logger.info("Starting Corretor AI Hub", environment=settings.APP_ENV)

    # Initialize connections
    await init_redis()
    await init_qdrant()
    await init_supabase()

    logger.info("All services initialized successfully")

    yield

    # Shutdown
    logger.info("Shutting down Corretor AI Hub")
    # Cleanup connections here if needed


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered real estate assistant platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.APP_DEBUG else None,
    redoc_url="/redoc" if settings.APP_DEBUG else None,
    openapi_url="/openapi.json" if settings.APP_DEBUG else None,
)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.APP_DEBUG else settings.ALLOWED_HOSTS,
)

# Setup exception handlers
setup_exception_handlers(app)

# Setup Prometheus metrics
if settings.PROMETHEUS_ENABLED:
    instrumentator = Instrumentator()
    instrumentator.instrument(app).expose(app, endpoint="/metrics")

# Include routers
app.include_router(router, prefix=settings.API_PREFIX)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.APP_ENV,
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "services": {
            "redis": await check_redis_health(),
            "qdrant": await check_qdrant_health(),
            "supabase": await check_supabase_health(),
        }
    }


async def check_redis_health():
    """Check Redis connection health"""
    try:
        from src.integrations.redis import redis_client
        await redis_client.ping()
        return "healthy"
    except Exception:
        return "unhealthy"


async def check_qdrant_health():
    """Check Qdrant connection health"""
    try:
        from src.integrations.qdrant import qdrant_client
        await qdrant_client.get_collections()
        return "healthy"
    except Exception:
        return "unhealthy"


async def check_supabase_health():
    """Check Supabase connection health"""
    try:
        from src.integrations.supabase import supabase_client
        # Simple health check query
        supabase_client.table("health_check").select("*").limit(1).execute()
        return "healthy"
    except Exception:
        return "unhealthy"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.APP_DEBUG,
        log_config=None,  # Use structlog instead
    )
