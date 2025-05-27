"""
Appointment management routes
"""
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.auth import get_current_active_tenant
from src.core.exceptions import NotFoundError, BusinessLogicError
from src.database.connection import get_session
from src.database.models import (
    Appointment, Tenant, Lead, Property,
    AppointmentStatus
)
from src.database.schemas import (
    AppointmentCreate, AppointmentUpdate, AppointmentResponse,
    PaginatedResponse
)
from src.integrations.google_calendar import GoogleCalendarClient

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
        appointment_data: AppointmentCreate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Create a new appointment
    
    Schedule a property viewing appointment
    """
    try:
        async with get_session() as session:
            # Verify lead belongs to tenant
            lead_stmt = select(Lead).where(
                and_(
                    Lead.id == appointment_data.lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            lead_result = await session.execute(lead_stmt)
            lead = lead_result.scalar_one_or_none()

            if not lead:
                raise NotFoundError("Lead", appointment_data.lead_id)

            # Verify property belongs to tenant
            prop_stmt = select(Property).where(
                and_(
                    Property.id == appointment_data.property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            prop_result = await session.execute(prop_stmt)
            property = prop_result.scalar_one_or_none()

            if not property:
                raise NotFoundError("Property", appointment_data.property_id)

            # Check for scheduling conflicts
            conflict_stmt = select(Appointment).where(
                and_(
                    Appointment.tenant_id == current_tenant.id,
                    Appointment.scheduled_at >= appointment_data.scheduled_at - timedelta(hours=1),
                    Appointment.scheduled_at <= appointment_data.scheduled_at + timedelta(hours=1),
                    Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED])
                )
            )

            conflict_result = await session.execute(conflict_stmt)
            conflicts = conflict_result.scalars().all()

            if conflicts:
                raise BusinessLogicError("Time slot is not available due to scheduling conflict")

            # Create appointment
            appointment_dict = appointment_data.dict()
            appointment_dict["tenant_id"] = current_tenant.id

            appointment = Appointment(**appointment_dict)
            session.add(appointment)
            await session.commit()
            await session.refresh(appointment)

            # Create Google Calendar event
            try:
                calendar_client = GoogleCalendarClient(str(current_tenant.id))
                event_result = await calendar_client.create_appointment_event(
                    appointment_id=str(appointment.id),
                    property_id=str(appointment.property_id),
                    scheduled_at=appointment.scheduled_at,
                    duration_minutes=appointment.duration_minutes,
                    notes=appointment.notes
                )

                appointment.google_event_id = event_result["id"]
                appointment.calendar_link = event_result["htmlLink"]
                await session.commit()

            except Exception as e:
                logger.error("Failed to create calendar event", error=str(e))
                # Continue without calendar integration

            logger.info(f"Created appointment: {appointment.id}")
            return appointment

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error creating appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create appointment"
        )


@router.get("/", response_model=PaginatedResponse)
async def list_appointments(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        # Filters
        status: Optional[AppointmentStatus] = None,
        lead_id: Optional[str] = None,
        property_id: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        # Pagination
        skip: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=100),
        # Sorting
        sort_by: str = Query("scheduled_at", regex="^(scheduled_at|created_at)$"),
        sort_order: str = Query("asc", regex="^(asc|desc)$")
):
    """
    List appointments with filters
    
    Get a paginated list of appointments
    """
    try:
        async with get_session() as session:
            # Build query
            stmt = select(Appointment).where(
                Appointment.tenant_id == current_tenant.id
            )

            # Apply filters
            if status:
                stmt = stmt.where(Appointment.status == status)
            if lead_id:
                stmt = stmt.where(Appointment.lead_id == lead_id)
            if property_id:
                stmt = stmt.where(Appointment.property_id == property_id)
            if date_from:
                stmt = stmt.where(Appointment.scheduled_at >= date_from)
            if date_to:
                stmt = stmt.where(Appointment.scheduled_at <= date_to)

            # Count total
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = await session.scalar(count_stmt)

            # Apply sorting
            sort_column = getattr(Appointment, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())

            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)

            # Execute query
            result = await session.execute(stmt)
            appointments = result.scalars().all()

            return PaginatedResponse(
                items=appointments,
                total=total,
                limit=limit,
                offset=skip,
                has_more=(skip + limit) < total
            )

    except Exception as e:
        logger.error("Error listing appointments", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list appointments"
        )


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
        appointment_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get appointment details
    
    Get detailed information about a specific appointment
    """
    try:
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise NotFoundError("Appointment", appointment_id)

            return appointment

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {appointment_id} not found"
        )
    except Exception as e:
        logger.error("Error getting appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get appointment"
        )


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
        appointment_id: str,
        appointment_update: AppointmentUpdate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Update appointment information
    
    Update details of an existing appointment
    """
    try:
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise NotFoundError("Appointment", appointment_id)

            # Check if appointment can be modified
            if appointment.status in [AppointmentStatus.COMPLETED, AppointmentStatus.NO_SHOW]:
                raise BusinessLogicError("Cannot modify completed or no-show appointments")

            # Update fields
            update_data = appointment_update.dict(exclude_unset=True)

            # If rescheduling, check for conflicts
            if "scheduled_at" in update_data:
                conflict_stmt = select(Appointment).where(
                    and_(
                        Appointment.tenant_id == current_tenant.id,
                        Appointment.id != appointment_id,
                        Appointment.scheduled_at >= update_data["scheduled_at"] - timedelta(hours=1),
                        Appointment.scheduled_at <= update_data["scheduled_at"] + timedelta(hours=1),
                        Appointment.status.in_([AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED])
                    )
                )

                conflict_result = await session.execute(conflict_stmt)
                conflicts = conflict_result.scalars().all()

                if conflicts:
                    raise BusinessLogicError("New time slot is not available")

            for field, value in update_data.items():
                setattr(appointment, field, value)

            await session.commit()
            await session.refresh(appointment)

            # Update Google Calendar event if rescheduled
            if "scheduled_at" in update_data and appointment.google_event_id:
                try:
                    calendar_client = GoogleCalendarClient(str(current_tenant.id))
                    await calendar_client.update_appointment_event(
                        event_id=appointment.google_event_id,
                        updates={
                            "scheduled_at": appointment.scheduled_at,
                            "duration_minutes": appointment.duration_minutes
                        }
                    )
                except Exception as e:
                    logger.error("Failed to update calendar event", error=str(e))

            logger.info(f"Updated appointment: {appointment_id}")
            return appointment

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {appointment_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error updating appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update appointment"
        )


@router.post("/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
        appointment_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Confirm an appointment
    
    Mark an appointment as confirmed
    """
    try:
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise NotFoundError("Appointment", appointment_id)

            if appointment.status != AppointmentStatus.SCHEDULED:
                raise BusinessLogicError("Only scheduled appointments can be confirmed")

            appointment.status = AppointmentStatus.CONFIRMED
            appointment.confirmed_at = datetime.utcnow()

            await session.commit()
            await session.refresh(appointment)

            logger.info(f"Confirmed appointment: {appointment_id}")
            return appointment

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {appointment_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error confirming appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm appointment"
        )


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
        appointment_id: str,
        cancellation_reason: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Cancel an appointment
    
    Cancel a scheduled appointment
    """
    try:
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise NotFoundError("Appointment", appointment_id)

            if appointment.status in [AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED]:
                raise BusinessLogicError("Appointment is already cancelled or completed")

            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancellation_reason = cancellation_reason

            await session.commit()
            await session.refresh(appointment)

            # Cancel Google Calendar event
            if appointment.google_event_id:
                try:
                    calendar_client = GoogleCalendarClient(str(current_tenant.id))
                    await calendar_client.cancel_appointment_event(
                        event_id=appointment.google_event_id,
                        cancellation_reason=cancellation_reason
                    )
                except Exception as e:
                    logger.error("Failed to cancel calendar event", error=str(e))

            logger.info(f"Cancelled appointment: {appointment_id}")
            return appointment

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {appointment_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error cancelling appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel appointment"
        )


@router.post("/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
        appointment_id: str,
        notes: Optional[str] = None,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Mark appointment as completed
    
    Mark an appointment as completed after the viewing
    """
    try:
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise NotFoundError("Appointment", appointment_id)

            if appointment.status == AppointmentStatus.COMPLETED:
                raise BusinessLogicError("Appointment is already completed")

            appointment.status = AppointmentStatus.COMPLETED
            appointment.completed_at = datetime.utcnow()

            if notes:
                appointment.notes = (appointment.notes or "") + f"\n\nCompletion notes: {notes}"

            await session.commit()
            await session.refresh(appointment)

            logger.info(f"Completed appointment: {appointment_id}")
            return appointment

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment {appointment_id} not found"
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Error completing appointment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete appointment"
        )


@router.get("/availability/check")
async def check_availability(
        date: datetime,
        duration_minutes: int = Query(60, ge=15, le=480),
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Check availability for appointments
    
    Get available time slots for a specific date
    """
    try:
        calendar_client = GoogleCalendarClient(str(current_tenant.id))
        available_slots = await calendar_client.get_available_slots(
            date=date,
            duration_minutes=duration_minutes
        )

        return {
            "date": date.date().isoformat(),
            "duration_minutes": duration_minutes,
            "available_slots": available_slots,
            "total_available": len(available_slots)
        }

    except Exception as e:
        logger.error("Error checking availability", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check availability"
        )
