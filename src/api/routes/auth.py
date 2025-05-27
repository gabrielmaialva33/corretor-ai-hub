"""
Authentication routes
"""
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.database.connection import get_session
from src.database.models import Tenant
from src.database.schemas import TenantResponse

logger = structlog.get_logger()
settings = get_settings()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")

router = APIRouter()


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class TokenData(BaseModel):
    tenant_id: Optional[str] = None
    email: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


async def get_current_tenant(token: str = Depends(oauth2_scheme)) -> Tenant:
    """Get current authenticated tenant"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        tenant_id: str = payload.get("tenant_id")
        token_type: str = payload.get("type")

        if tenant_id is None or token_type != "access":
            raise credentials_exception

        token_data = TokenData(tenant_id=tenant_id)

    except JWTError:
        raise credentials_exception

    async with get_session() as session:
        stmt = select(Tenant).where(Tenant.id == token_data.tenant_id)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

    if tenant is None:
        raise credentials_exception

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant account is not active"
        )

    return tenant


async def get_current_active_tenant(
        current_tenant: Tenant = Depends(get_current_tenant)
) -> Tenant:
    """Ensure tenant is active"""
    if not current_tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive tenant"
        )
    return current_tenant


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login with email and password
    
    Returns access and refresh tokens
    """
    async with get_session() as session:
        stmt = select(Tenant).where(Tenant.email == form_data.username)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

    if not tenant:
        logger.warning(f"Login attempt for non-existent email: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # For now, we'll use a simple password check
    # In production, you'd store hashed passwords
    if not verify_password(form_data.password, tenant.password_hash):
        logger.warning(f"Failed login attempt for tenant: {tenant.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active"
        )

    # Create tokens
    access_token_data = {
        "tenant_id": str(tenant.id),
        "email": tenant.email
    }

    access_token = create_access_token(data=access_token_data)
    refresh_token = create_refresh_token(data=access_token_data)

    # Update last login
    async with get_session() as session:
        tenant.last_login_at = datetime.utcnow()
        session.add(tenant)
        await session.commit()

    logger.info(f"Successful login for tenant: {tenant.id}")

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            request.refresh_token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        tenant_id: str = payload.get("tenant_id")
        token_type: str = payload.get("type")

        if tenant_id is None or token_type != "refresh":
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    # Verify tenant still exists and is active
    async with get_session() as session:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

    if not tenant or not tenant.is_active:
        raise credentials_exception

    # Create new access token
    access_token_data = {
        "tenant_id": str(tenant.id),
        "email": tenant.email
    }

    access_token = create_access_token(data=access_token_data)

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", response_model=TenantResponse)
async def get_me(current_tenant: Tenant = Depends(get_current_active_tenant)):
    """
    Get current tenant information
    """
    return current_tenant


@router.post("/change-password")
async def change_password(
        request: ChangePasswordRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Change password for current tenant
    """
    # Verify current password
    if not verify_password(request.current_password, current_tenant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Update password
    async with get_session() as session:
        current_tenant.password_hash = get_password_hash(request.new_password)
        current_tenant.password_changed_at = datetime.utcnow()
        session.add(current_tenant)
        await session.commit()

    logger.info(f"Password changed for tenant: {current_tenant.id}")

    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(current_tenant: Tenant = Depends(get_current_active_tenant)):
    """
    Logout current tenant
    
    In a real implementation, you might want to:
    - Invalidate the token (store in Redis blacklist)
    - Clear any server-side session
    - Log the logout event
    """
    logger.info(f"Logout for tenant: {current_tenant.id}")

    return {"message": "Logged out successfully"}


@router.post("/forgot-password")
async def forgot_password(email: str):
    """
    Request password reset
    
    In production, this would:
    - Generate a reset token
    - Send email with reset link
    - Store token with expiration
    """
    async with get_session() as session:
        stmt = select(Tenant).where(Tenant.email == email)
        result = await session.execute(stmt)
        tenant = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if tenant:
        # TODO: Implement password reset logic
        logger.info(f"Password reset requested for tenant: {tenant.id}")

    return {
        "message": "If the email exists, a password reset link will be sent"
    }


@router.post("/reset-password")
async def reset_password(token: str, new_password: str):
    """
    Reset password with token
    
    In production, this would:
    - Validate the reset token
    - Check token expiration
    - Update password
    - Invalidate token
    """
    # TODO: Implement password reset logic

    return {"message": "Password reset successfully"}
