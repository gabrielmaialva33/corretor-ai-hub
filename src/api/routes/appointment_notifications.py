"""
Appointment notification management routes
"""
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, and_

from src.api.routes.auth import get_current_active_tenant
from src.database.connection import get_session
from src.database.models import Tenant, Appointment, AppointmentStatus
from src.services.appointment_reminder import AppointmentReminderService

logger = structlog.get_logger()
router = APIRouter()


class ReminderScheduleRequest(BaseModel):
    """Request to schedule reminders for an appointment"""
    appointment_id: str


class ReminderTestRequest(BaseModel):
    """Request to test reminder sending"""
    appointment_id: str
    reminder_type: str = "24_hours"  # 24_hours, 3_hours, confirmation_request


class ReminderResponseRequest(BaseModel):
    """Customer response to reminder"""
    appointment_id: str
    response: str
    lead_phone: str


@router.post("/schedule-reminders")
async def schedule_reminders(
        request: ReminderScheduleRequest,
        background_tasks: BackgroundTasks,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Schedule automatic reminders for an appointment
    
    Sets up 24-hour and 3-hour reminders
    """
    try:
        # Verify appointment belongs to tenant
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == request.appointment_id,
                    Appointment.tenant_id == current_tenant.id,
                    Appointment.status == AppointmentStatus.SCHEDULED
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Appointment not found or not scheduled"
                )

        # Schedule reminders in background
        reminder_service = AppointmentReminderService()
        background_tasks.add_task(
            reminder_service.schedule_reminders,
            request.appointment_id
        )

        return {
            "message": "Reminders scheduled successfully",
            "appointment_id": request.appointment_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error scheduling reminders", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule reminders"
        )


@router.post("/send-test-reminder")
async def send_test_reminder(
        request: ReminderTestRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Send a test reminder immediately
    
    Useful for testing reminder templates and delivery
    """
    try:
        # Verify appointment belongs to tenant
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == request.appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Appointment not found"
                )

        # Send reminder
        reminder_service = AppointmentReminderService()
        success = await reminder_service.send_reminder(
            request.appointment_id,
            request.reminder_type
        )

        if success:
            return {
                "message": "Test reminder sent successfully",
                "appointment_id": request.appointment_id,
                "reminder_type": request.reminder_type
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send test reminder"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error sending test reminder", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send test reminder"
        )


@router.post("/process-response")
async def process_reminder_response(
        request: ReminderResponseRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Process customer response to appointment reminder
    
    Handles confirmations and cancellations
    """
    try:
        # Verify appointment belongs to tenant
        async with get_session() as session:
            stmt = select(Appointment).where(
                and_(
                    Appointment.id == request.appointment_id,
                    Appointment.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            appointment = result.scalar_one_or_none()

            if not appointment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Appointment not found"
                )

        # Process response
        reminder_service = AppointmentReminderService()
        result = await reminder_service.process_reminder_response(
            request.appointment_id,
            request.response,
            request.lead_phone
        )

        if result["success"]:
            return {
                "message": f"Response processed: {result['action']}",
                "appointment_id": request.appointment_id,
                "action": result["action"]
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Failed to process response")
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing reminder response", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process reminder response"
        )


@router.get("/upcoming")
async def get_upcoming_reminders(
        hours_ahead: int = 48,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get appointments with upcoming reminders
    
    Shows appointments scheduled in the next X hours
    """
    try:
        reminder_service = AppointmentReminderService()
        appointments = await reminder_service.get_upcoming_appointments(hours_ahead)

        # Filter by tenant
        tenant_appointments = [
            apt for apt in appointments
            if apt.tenant_id == current_tenant.id
        ]

        # Format response
        upcoming = []
        for apt in tenant_appointments:
            hours_until = (apt.scheduled_date - datetime.utcnow()).total_seconds() / 3600

            upcoming.append({
                "appointment_id": str(apt.id),
                "scheduled_date": apt.scheduled_date.isoformat(),
                "hours_until": round(hours_until, 1),
                "lead_name": apt.lead.name if apt.lead else "Unknown",
                "property_title": apt.property.title if apt.property else "Unknown",
                "reminder_24h_sent": apt.reminder_24h_sent,
                "reminder_3h_sent": apt.reminder_3h_sent,
                "status": apt.status.value
            })

        return {
            "upcoming_appointments": upcoming,
            "total": len(upcoming),
            "hours_ahead": hours_ahead
        }

    except Exception as e:
        logger.error("Error getting upcoming reminders", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get upcoming reminders"
        )


@router.get("/reminder-stats")
async def get_reminder_statistics(
        days_back: int = 30,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get reminder statistics
    
    Shows reminder performance metrics
    """
    try:
        async with get_session() as session:
            # Get appointments from the last X days
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            stmt = select(Appointment).where(
                and_(
                    Appointment.tenant_id == current_tenant.id,
                    Appointment.scheduled_date >= cutoff_date
                )
            )
            result = await session.execute(stmt)
            appointments = result.scalars().all()

            # Calculate statistics
            total_appointments = len(appointments)
            reminders_24h_sent = sum(1 for apt in appointments if apt.reminder_24h_sent)
            reminders_3h_sent = sum(1 for apt in appointments if apt.reminder_3h_sent)
            confirmed_after_reminder = sum(
                1 for apt in appointments
                if apt.status == AppointmentStatus.CONFIRMED and apt.reminder_24h_sent
            )
            cancelled_after_reminder = sum(
                1 for apt in appointments
                if apt.status == AppointmentStatus.CANCELLED and apt.reminder_24h_sent
            )

            return {
                "period_days": days_back,
                "total_appointments": total_appointments,
                "reminders_sent": {
                    "24_hours": reminders_24h_sent,
                    "3_hours": reminders_3h_sent
                },
                "response_stats": {
                    "confirmed": confirmed_after_reminder,
                    "cancelled": cancelled_after_reminder,
                    "confirmation_rate": (
                        round(confirmed_after_reminder / reminders_24h_sent * 100, 1)
                        if reminders_24h_sent > 0 else 0
                    )
                }
            }

    except Exception as e:
        logger.error("Error getting reminder statistics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get reminder statistics"
        )
