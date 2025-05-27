"""
Lead management routes
"""
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.auth import get_current_active_tenant
from src.core.exceptions import NotFoundError, BusinessLogicError
from src.database.connection import get_session
from src.database.models import Lead, Tenant, LeadStatus, Conversation, Appointment
from src.database.schemas import (
    LeadCreate, LeadUpdate, LeadResponse,
    PaginatedResponse, SuccessResponse
)
from src.services.lead_scoring import LeadScoringService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
        lead_data: LeadCreate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Create a new lead
    
    Manually create a lead in the system
    """
    try:
        async with get_session() as session:
            # Check if lead with same phone already exists
            stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == current_tenant.id,
                    Lead.phone == lead_data.phone
                )
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lead with this phone number already exists"
                )

            # Create lead
            lead_dict = lead_data.dict()
            lead_dict["tenant_id"] = current_tenant.id

            lead = Lead(**lead_dict)
            session.add(lead)
            await session.commit()
            await session.refresh(lead)

            # Calculate initial score
            scoring_service = LeadScoringService()
            lead.score = await scoring_service.calculate_score(lead)
            await session.commit()

            logger.info(f"Created lead: {lead.id}")
            return lead

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating lead", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create lead"
        )


@router.get("/", response_model=PaginatedResponse)
async def list_leads(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        # Filters
        status: Optional[LeadStatus] = None,
        source: Optional[str] = None,
        min_score: Optional[int] = Query(None, ge=0, le=100),
        max_score: Optional[int] = Query(None, ge=0, le=100),
        search: Optional[str] = None,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        # Pagination
        skip: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=100),
        # Sorting
        sort_by: str = Query("created_at", regex="^(created_at|score|last_contact_at|name)$"),
        sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    """
    List leads with filters
    
    Get a paginated list of leads with optional filters
    """
    try:
        async with get_session() as session:
            # Build query
            stmt = select(Lead).where(Lead.tenant_id == current_tenant.id)

            # Apply filters
            if status:
                stmt = stmt.where(Lead.status == status)
            if source:
                stmt = stmt.where(Lead.source == source)
            if min_score is not None:
                stmt = stmt.where(Lead.score >= min_score)
            if max_score is not None:
                stmt = stmt.where(Lead.score <= max_score)
            if search:
                stmt = stmt.where(
                    or_(
                        Lead.name.ilike(f"%{search}%"),
                        Lead.phone.ilike(f"%{search}%"),
                        Lead.email.ilike(f"%{search}%")
                    )
                )
            if created_after:
                stmt = stmt.where(Lead.created_at >= created_after)
            if created_before:
                stmt = stmt.where(Lead.created_at <= created_before)

            # Count total
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = await session.scalar(count_stmt)

            # Apply sorting
            sort_column = getattr(Lead, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())

            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)

            # Execute query
            result = await session.execute(stmt)
            leads = result.scalars().all()

            return PaginatedResponse(
                items=leads,
                total=total,
                limit=limit,
                offset=skip,
                has_more=(skip + limit) < total
            )

    except Exception as e:
        logger.error("Error listing leads", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list leads"
        )


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
        lead_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get lead details
    
    Get detailed information about a specific lead
    """
    try:
        async with get_session() as session:
            stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", lead_id)

            return lead

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found"
        )
    except Exception as e:
        logger.error("Error getting lead", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get lead"
        )


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
        lead_id: str,
        lead_update: LeadUpdate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Update lead information
    
    Update details of an existing lead
    """
    try:
        async with get_session() as session:
            stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", lead_id)

            # Update fields
            update_data = lead_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(lead, field, value)

            # Update last contact
            lead.last_contact_at = datetime.utcnow()

            # Recalculate score if relevant fields changed
            if any(field in update_data for field in ["preferences", "budget_min", "budget_max", "status"]):
                scoring_service = LeadScoringService()
                lead.score = await scoring_service.calculate_score(lead)

            await session.commit()
            await session.refresh(lead)

            logger.info(f"Updated lead: {lead_id}")
            return lead

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found"
        )
    except Exception as e:
        logger.error("Error updating lead", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update lead"
        )


@router.delete("/{lead_id}", response_model=SuccessResponse)
async def delete_lead(
        lead_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Delete a lead
    
    Permanently delete a lead and all associated data
    """
    try:
        async with get_session() as session:
            stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", lead_id)

            # Check if lead has active conversations or appointments
            active_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.lead_id == lead_id,
                        Conversation.status == "active"
                    )
                )
            )

            if active_conversations > 0:
                raise BusinessLogicError("Cannot delete lead with active conversations")

            # Delete lead (cascade will handle related records)
            await session.delete(lead)
            await session.commit()

            logger.info(f"Deleted lead: {lead_id}")
            return SuccessResponse(
                message="Lead deleted successfully"
            )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error deleting lead", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete lead"
        )


@router.post("/{lead_id}/convert", response_model=LeadResponse)
async def convert_lead(
        lead_id: str,
        notes: Optional[str] = None,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Convert a lead to customer
    
    Mark a lead as successfully converted
    """
    try:
        async with get_session() as session:
            stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", lead_id)

            if lead.status == LeadStatus.CONVERTED:
                raise BusinessLogicError("Lead is already converted")

            # Update status
            lead.status = LeadStatus.CONVERTED
            lead.converted_at = datetime.utcnow()

            if notes:
                lead.qualification_notes = (lead.qualification_notes or "") + f"\n\nConversion notes: {notes}"

            await session.commit()
            await session.refresh(lead)

            logger.info(f"Converted lead: {lead_id}")
            return lead

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error converting lead", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to convert lead"
        )


@router.get("/{lead_id}/timeline")
async def get_lead_timeline(
        lead_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get lead interaction timeline
    
    Returns all interactions with the lead (conversations, appointments, etc.)
    """
    try:
        async with get_session() as session:
            # Verify lead exists and belongs to tenant
            stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", lead_id)

            timeline = []

            # Get conversations
            stmt = select(Conversation).where(Conversation.lead_id == lead_id)
            result = await session.execute(stmt)
            conversations = result.scalars().all()

            for conv in conversations:
                timeline.append({
                    "type": "conversation",
                    "id": str(conv.id),
                    "timestamp": conv.started_at,
                    "status": conv.status.value,
                    "data": {
                        "duration": (conv.ended_at - conv.started_at).total_seconds() if conv.ended_at else None,
                        "handoff_requested": conv.handoff_requested
                    }
                })

            # Get appointments
            stmt = select(Appointment).where(Appointment.lead_id == lead_id)
            result = await session.execute(stmt)
            appointments = result.scalars().all()

            for appt in appointments:
                timeline.append({
                    "type": "appointment",
                    "id": str(appt.id),
                    "timestamp": appt.scheduled_at,
                    "status": appt.status.value,
                    "data": {
                        "property_id": str(appt.property_id),
                        "duration_minutes": appt.duration_minutes
                    }
                })

            # Sort by timestamp
            timeline.sort(key=lambda x: x["timestamp"], reverse=True)

            return {
                "lead_id": lead_id,
                "total_interactions": len(timeline),
                "timeline": timeline
            }

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lead {lead_id} not found"
        )
    except Exception as e:
        logger.error("Error getting lead timeline", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get lead timeline"
        )


@router.get("/stats/summary")
async def get_leads_summary(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365)
):
    """
    Get leads summary statistics
    
    Returns summary statistics about leads
    """
    try:
        async with get_session() as session:
            # Date range
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Total leads
            total = await session.scalar(
                select(func.count(Lead.id)).where(
                    Lead.tenant_id == current_tenant.id
                )
            )

            # New leads in period
            new_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.created_at >= start_date
                    )
                )
            )

            # By status
            status_counts = {}
            for status in LeadStatus:
                count = await session.scalar(
                    select(func.count(Lead.id)).where(
                        and_(
                            Lead.tenant_id == current_tenant.id,
                            Lead.status == status
                        )
                    )
                )
                status_counts[status.value] = count

            # Conversion rate
            converted = status_counts.get(LeadStatus.CONVERTED.value, 0)
            conversion_rate = (converted / total * 100) if total > 0 else 0

            # Average score
            avg_score = await session.scalar(
                select(func.avg(Lead.score)).where(
                    Lead.tenant_id == current_tenant.id
                )
            )

            # By source
            stmt = select(
                Lead.source,
                func.count(Lead.id)
            ).where(
                Lead.tenant_id == current_tenant.id
            ).group_by(Lead.source)

            result = await session.execute(stmt)
            source_counts = dict(result.all())

            # Hot leads (high score, recent contact)
            hot_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.score >= 70,
                        Lead.last_contact_at >= datetime.utcnow() - timedelta(days=7),
                        Lead.status.in_([LeadStatus.CONTACTED, LeadStatus.QUALIFIED])
                    )
                )
            )

            return {
                "period_days": period_days,
                "total": total,
                "new_leads": new_leads,
                "by_status": status_counts,
                "conversion_rate": round(conversion_rate, 2),
                "average_score": round(float(avg_score) if avg_score else 0, 1),
                "by_source": source_counts,
                "hot_leads": hot_leads
            }

    except Exception as e:
        logger.error("Error getting leads summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get leads summary"
        )
