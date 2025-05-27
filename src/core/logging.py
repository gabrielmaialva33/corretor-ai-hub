"""
Structured logging configuration
"""
import sys
from pathlib import Path

import structlog

import logging
from src.core.config import get_settings

settings = get_settings()


def setup_logging():
    """Configure structured logging"""

    # Create log directory if needed
    if settings.LOG_FILE_PATH:
        log_dir = Path(settings.LOG_FILE_PATH).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    # Configure Python logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper())
    )

    # Configure structlog processors
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on format
    if settings.LOG_FORMAT == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set log level for third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING if not settings.APP_DEBUG else logging.INFO)

    # Add file handler if configured
    if settings.LOG_FILE_PATH:
        file_handler = logging.FileHandler(settings.LOG_FILE_PATH)
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

        if settings.LOG_FORMAT == "json":
            formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
            )
        else:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        file_handler.setFormatter(formatter)
        logging.root.addHandler(file_handler)

    # Log startup message
    logger = structlog.get_logger()
    logger.info(
        "Logging configured",
        level=settings.LOG_LEVEL,
        format=settings.LOG_FORMAT,
        environment=settings.APP_ENV
    )


def get_logger(name: str = None) -> structlog.BoundLogger:
    """Get a structured logger instance"""
    return structlog.get_logger(name)
