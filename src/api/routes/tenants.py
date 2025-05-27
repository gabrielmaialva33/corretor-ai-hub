"""
Tenant management routes
"""
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.auth import get_current_active_tenant
from src.core.exceptions import NotFoundError
from src.database.connection import get_session
from src.database.models import Tenant, TenantStatus
from src.database.schemas import (
    TenantCreate, TenantUpdate, TenantResponse,
    SuccessResponse
)
from src.services.tenant_service import TenantService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
        tenant_data: TenantCreate,
        background_tasks: BackgroundTasks
):
    """
    Create a new tenant
    
    This endpoint creates a new tenant account with all necessary integrations
    """
    try:
        # Check if email already exists
        async with get_session() as session:
            stmt = select(Tenant).where(Tenant.email == tenant_data.email)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # Create tenant
        tenant_service = TenantService()
        tenant = await tenant_service.create_tenant(tenant_data)

        # Setup integrations in background
        background_tasks.add_task(
            tenant_service.setup_tenant_integrations,
            str(tenant.id)
        )

        logger.info(f"Created new tenant: {tenant.id}")

        return tenant

    except Exception as e:
        logger.error("Error creating tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create tenant"
        )


@router.get("/", response_model=List[TenantResponse])
async def list_tenants(
        skip: int = 0,
        limit: int = 100,
        status: Optional[TenantStatus] = None,
        # This endpoint would typically be admin-only
        # current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    List all tenants
    
    This endpoint is typically restricted to admin users
    """
    try:
        async with get_session() as session:
            stmt = select(Tenant)

            if status:
                stmt = stmt.where(Tenant.status == status)

            stmt = stmt.offset(skip).limit(limit)

            result = await session.execute(stmt)
            tenants = result.scalars().all()

            return tenants

    except Exception as e:
        logger.error("Error listing tenants", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list tenants"
        )


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
        tenant_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get tenant details
    
    Tenants can only access their own information unless they're admins
    """
    try:
        # Check authorization
        if str(current_tenant.id) != tenant_id and not current_tenant.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        async with get_session() as session:
            tenant = await session.get(Tenant, tenant_id)

            if not tenant:
                raise NotFoundError("Tenant", tenant_id)

            return tenant

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error getting tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tenant"
        )


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
        tenant_id: str,
        tenant_update: TenantUpdate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Update tenant information
    
    Tenants can only update their own information
    """
    try:
        # Check authorization
        if str(current_tenant.id) != tenant_id and not current_tenant.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        tenant_service = TenantService()
        updated_tenant = await tenant_service.update_tenant(tenant_id, tenant_update)

        return updated_tenant

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error updating tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update tenant"
        )


@router.post("/{tenant_id}/activate", response_model=SuccessResponse)
async def activate_tenant(
        tenant_id: str,
        # This endpoint would typically be admin-only
        # current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Activate a tenant account
    
    This changes the tenant status to ACTIVE
    """
    try:
        tenant_service = TenantService()
        await tenant_service.activate_tenant(tenant_id)

        return SuccessResponse(
            message="Tenant activated successfully"
        )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error activating tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate tenant"
        )


@router.post("/{tenant_id}/suspend", response_model=SuccessResponse)
async def suspend_tenant(
        tenant_id: str,
        reason: Optional[str] = None,
        # This endpoint would typically be admin-only
        # current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Suspend a tenant account
    
    This prevents the tenant from accessing the system
    """
    try:
        tenant_service = TenantService()
        await tenant_service.suspend_tenant(tenant_id, reason)

        return SuccessResponse(
            message="Tenant suspended successfully"
        )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error suspending tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to suspend tenant"
        )


@router.delete("/{tenant_id}", response_model=SuccessResponse)
async def delete_tenant(
        tenant_id: str,
        # This endpoint would typically be admin-only
        # current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Delete a tenant account
    
    This performs a soft delete by marking the tenant as inactive
    """
    try:
        tenant_service = TenantService()
        await tenant_service.delete_tenant(tenant_id)

        return SuccessResponse(
            message="Tenant deleted successfully"
        )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error deleting tenant", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete tenant"
        )


@router.get("/{tenant_id}/stats")
async def get_tenant_stats(
        tenant_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get tenant statistics
    
    Returns various metrics about the tenant's usage
    """
    try:
        # Check authorization
        if str(current_tenant.id) != tenant_id and not current_tenant.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        tenant_service = TenantService()
        stats = await tenant_service.get_tenant_stats(tenant_id)

        return stats

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    except Exception as e:
        logger.error("Error getting tenant stats", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get tenant stats"
        )


@router.post("/{tenant_id}/setup-integrations", response_model=SuccessResponse)
async def setup_integrations(
        tenant_id: str,
        background_tasks: BackgroundTasks,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Setup or reset tenant integrations
    
    This creates/updates:
    - EVO API instance
    - Chatwoot inbox
    - Google Calendar
    - Qdrant collections
    """
    try:
        # Check authorization
        if str(current_tenant.id) != tenant_id and not current_tenant.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

        tenant_service = TenantService()

        # Run setup in background
        background_tasks.add_task(
            tenant_service.setup_tenant_integrations,
            tenant_id
        )

        return SuccessResponse(
            message="Integration setup started. This may take a few minutes."
        )

    except Exception as e:
        logger.error("Error setting up integrations", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to setup integrations"
        )
