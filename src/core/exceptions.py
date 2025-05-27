"""
Custom exceptions and error handling
"""
from typing import Dict, Any, Optional

import structlog
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = structlog.get_logger()


class CoreException(Exception):
    """Base exception for all custom exceptions"""

    def __init__(
            self,
            message: str,
            code: str = "UNKNOWN_ERROR",
            status_code: int = 500,
            details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class BusinessLogicError(CoreException):
    """Business logic validation error"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="BUSINESS_LOGIC_ERROR",
            status_code=400,
            details=details
        )


class NotFoundError(CoreException):
    """Resource not found error"""

    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)}
        )


class AuthenticationError(CoreException):
    """Authentication error"""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401
        )


class AuthorizationError(CoreException):
    """Authorization error"""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403
        )


class ExternalAPIError(CoreException):
    """External API integration error"""

    def __init__(self, message: str, service: str = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if service:
            details["service"] = service

        super().__init__(
            message=message,
            code="EXTERNAL_API_ERROR",
            status_code=502,
            details=details
        )


class RateLimitError(CoreException):
    """Rate limit exceeded error"""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = None):
        details = {}
        if retry_after:
            details["retry_after"] = retry_after

        super().__init__(
            message=message,
            code="RATE_LIMIT_ERROR",
            status_code=429,
            details=details
        )


class ValidationError(CoreException):
    """Data validation error"""

    def __init__(self, message: str, field: str = None, details: Optional[Dict[str, Any]] = None):
        details = details or {}
        if field:
            details["field"] = field

        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details=details
        )


class ConfigurationError(CoreException):
    """Configuration error"""

    def __init__(self, message: str, config_key: str = None):
        details = {}
        if config_key:
            details["config_key"] = config_key

        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=500,
            details=details
        )


class TenantNotActiveError(CoreException):
    """Tenant not active or suspended"""

    def __init__(self, tenant_id: str):
        super().__init__(
            message="Tenant is not active",
            code="TENANT_NOT_ACTIVE",
            status_code=403,
            details={"tenant_id": tenant_id}
        )


class ConversationHandoffError(CoreException):
    """Error during conversation handoff"""

    def __init__(self, message: str, conversation_id: str):
        super().__init__(
            message=message,
            code="HANDOFF_ERROR",
            status_code=500,
            details={"conversation_id": conversation_id}
        )


async def core_exception_handler(request: Request, exc: CoreException) -> JSONResponse:
    """Handle core exceptions"""
    logger.error(
        exc.message,
        code=exc.code,
        status_code=exc.status_code,
        details=exc.details,
        path=request.url.path
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions"""
    logger.warning(
        f"HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail
            }
        }
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger.exception(
        "Unexpected error",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=request.url.path
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred"
            }
        }
    )


def setup_exception_handlers(app: FastAPI):
    """Setup exception handlers for FastAPI app"""
    app.add_exception_handler(CoreException, core_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
