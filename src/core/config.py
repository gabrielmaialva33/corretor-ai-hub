"""
Application configuration using Pydantic Settings
"""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Application
    APP_NAME: str = "Corretor AI Hub"
    APP_ENV: str = Field(default="development", pattern="^(development|staging|production)$")
    APP_DEBUG: bool = False
    APP_URL: str = "http://localhost:8000"
    APP_SECRET_KEY: str

    # API
    API_PREFIX: str = "/api/v1"
    API_RATE_LIMIT: str = "100 per minute"

    # Database - Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_KEY: str
    DATABASE_URL: str

    # Vector Database - Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_COLLECTION_PREFIX: str = "corretor_"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # EVO API
    EVO_API_BASE_URL: str
    EVO_API_KEY: str
    EVO_WEBHOOK_URL: str

    # Chatwoot
    CHATWOOT_BASE_URL: str
    CHATWOOT_API_ACCESS_TOKEN: str
    CHATWOOT_ACCOUNT_ID: str
    CHATWOOT_WEBHOOK_URL: str

    # Google Calendar
    GOOGLE_CALENDAR_CREDENTIALS_PATH: str = "./config/google_calendar_credentials.json"
    GOOGLE_CALENDAR_TOKEN_PATH: str = "./config/token.json"
    GOOGLE_CALENDAR_SCOPES: str = "https://www.googleapis.com/auth/calendar"

    # AI/LLM
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 2000

    # Scraping
    SCRAPER_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    SCRAPER_TIMEOUT: int = 30
    SCRAPER_RETRY_ATTEMPTS: int = 3
    SCRAPER_RATE_LIMIT_DELAY: int = 2

    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    SENTRY_ENVIRONMENT: str = Field(default_factory=lambda: "development")
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_METRICS_PORT: int = 9090

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE_PATH: str = "./logs/app.log"

    # Multi-tenant
    MAX_TENANTS_PER_INSTANCE: int = 10
    TENANT_ISOLATION_MODE: str = Field(default="schema", pattern="^(schema|database|namespace)$")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # Webhook
    WEBHOOK_SECRET: str
    WEBHOOK_TIMEOUT: int = 30

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM_EMAIL: str = "noreply@corretor-ai.com"

    # Feature Flags
    FEATURE_AUTO_SCHEDULING: bool = True
    FEATURE_LEAD_SCORING: bool = True
    FEATURE_PROPERTY_RECOMMENDATIONS: bool = True
    FEATURE_FOLLOW_UP_AUTOMATION: bool = True

    # Business Rules
    MAX_PROPERTIES_PER_SUGGESTION: int = 5
    CONVERSATION_TIMEOUT_MINUTES: int = 30
    MAX_CONVERSATION_HISTORY_DAYS: int = 90
    AUTO_HANDOFF_THRESHOLD: int = 3

    # Scheduled Tasks
    SCRAPER_CRON_SCHEDULE: str = "0 */6 * * *"
    CLEANUP_CRON_SCHEDULE: str = "0 2 * * *"
    METRICS_AGGREGATION_SCHEDULE: str = "*/15 * * * *"

    # Additional
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]

    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @validator("SENTRY_ENVIRONMENT", pre=True, always=True)
    def set_sentry_environment(cls, v, values):
        return v or values.get("APP_ENV", "development")

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.APP_ENV == "development"

    @property
    def redis_url_with_password(self) -> str:
        """Get Redis URL with password if set"""
        if self.REDIS_PASSWORD:
            parts = self.REDIS_URL.split("://")
            return f"{parts[0]}://:{self.REDIS_PASSWORD}@{parts[1]}"
        return self.REDIS_URL


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
