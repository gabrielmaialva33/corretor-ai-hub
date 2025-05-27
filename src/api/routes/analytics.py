"""
Analytics routes for business insights
"""
from datetime import datetime, timedelta

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_, case, extract

from src.api.routes.auth import get_current_active_tenant
from src.database.connection import get_session
from src.database.models import (
    Tenant, Property, Lead, Conversation, Appointment, Message,
    PropertyStatus, LeadStatus, ConversationStatus, AppointmentStatus
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/dashboard")
async def get_dashboard_metrics(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365)
):
    """
    Get dashboard metrics
    
    Returns key metrics for the main dashboard
    """
    try:
        async with get_session() as session:
            # Date ranges
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=period_days)
            previous_start = start_date - timedelta(days=period_days)

            # Properties metrics
            total_properties = await session.scalar(
                select(func.count(Property.id)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.is_active == True
                    )
                )
            )

            available_properties = await session.scalar(
                select(func.count(Property.id)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.status == PropertyStatus.AVAILABLE,
                        Property.is_active == True
                    )
                )
            )

            # Leads metrics - current period
            new_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.created_at >= start_date
                    )
                )
            )

            # Leads metrics - previous period
            previous_new_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.created_at >= previous_start,
                        Lead.created_at < start_date
                    )
                )
            )

            # Calculate growth
            leads_growth = 0
            if previous_new_leads > 0:
                leads_growth = ((new_leads - previous_new_leads) / previous_new_leads) * 100

            # Conversations metrics
            total_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.started_at >= start_date
                    )
                )
            )

            active_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.status == ConversationStatus.ACTIVE
                    )
                )
            )

            # Appointments metrics
            scheduled_appointments = await session.scalar(
                select(func.count(Appointment.id)).where(
                    and_(
                        Appointment.tenant_id == current_tenant.id,
                        Appointment.created_at >= start_date
                    )
                )
            )

            completed_appointments = await session.scalar(
                select(func.count(Appointment.id)).where(
                    and_(
                        Appointment.tenant_id == current_tenant.id,
                        Appointment.status == AppointmentStatus.COMPLETED,
                        Appointment.completed_at >= start_date
                    )
                )
            )

            # Conversion metrics
            converted_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.status == LeadStatus.CONVERTED,
                        Lead.converted_at >= start_date
                    )
                )
            )

            conversion_rate = 0
            if new_leads > 0:
                conversion_rate = (converted_leads / new_leads) * 100

            # Average response time
            avg_response_time = await self._calculate_avg_response_time(
                session, current_tenant.id, start_date
            )

            return {
                "period_days": period_days,
                "properties": {
                    "total": total_properties,
                    "available": available_properties,
                    "occupancy_rate": round(
                        ((total_properties - available_properties) / total_properties * 100)
                        if total_properties > 0 else 0, 1
                    )
                },
                "leads": {
                    "new_count": new_leads,
                    "growth_percentage": round(leads_growth, 1),
                    "conversion_rate": round(conversion_rate, 1),
                    "converted_count": converted_leads
                },
                "conversations": {
                    "total": total_conversations,
                    "active": active_conversations,
                    "avg_response_time_minutes": avg_response_time
                },
                "appointments": {
                    "scheduled": scheduled_appointments,
                    "completed": completed_appointments,
                    "completion_rate": round(
                        (completed_appointments / scheduled_appointments * 100)
                        if scheduled_appointments > 0 else 0, 1
                    )
                }
            }

    except Exception as e:
        logger.error("Error getting dashboard metrics", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get dashboard metrics"
        )


@router.get("/performance/agent")
async def get_agent_performance(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365)
):
    """
    Get AI agent performance metrics
    
    Returns metrics about the AI agent's performance
    """
    try:
        async with get_session() as session:
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Total messages processed
            total_messages = await session.scalar(
                select(func.count(Message.id)).where(
                    and_(
                        Message.conversation_id.in_(
                            select(Conversation.id).where(
                                Conversation.tenant_id == current_tenant.id
                            )
                        ),
                        Message.created_at >= start_date,
                        Message.ai_processed == True
                    )
                )
            )

            # Handoff rate
            total_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.started_at >= start_date
                    )
                )
            )

            handoff_conversations = await session.scalar(
                select(func.count(Conversation.id)).where(
                    and_(
                        Conversation.tenant_id == current_tenant.id,
                        Conversation.handoff_requested == True,
                        Conversation.started_at >= start_date
                    )
                )
            )

            handoff_rate = 0
            if total_conversations > 0:
                handoff_rate = (handoff_conversations / total_conversations) * 100

            # Intent recognition accuracy (simplified)
            messages_with_intent = await session.scalar(
                select(func.count(Message.id)).where(
                    and_(
                        Message.conversation_id.in_(
                            select(Conversation.id).where(
                                Conversation.tenant_id == current_tenant.id
                            )
                        ),
                        Message.intent.isnot(None),
                        Message.created_at >= start_date
                    )
                )
            )

            # Average confidence score
            avg_confidence = await session.scalar(
                select(func.avg(Message.ai_confidence)).where(
                    and_(
                        Message.conversation_id.in_(
                            select(Conversation.id).where(
                                Conversation.tenant_id == current_tenant.id
                            )
                        ),
                        Message.ai_confidence.isnot(None),
                        Message.created_at >= start_date
                    )
                )
            )

            # Most common intents
            intent_query = select(
                Message.intent,
                func.count(Message.id).label('count')
            ).where(
                and_(
                    Message.conversation_id.in_(
                        select(Conversation.id).where(
                            Conversation.tenant_id == current_tenant.id
                        )
                    ),
                    Message.intent.isnot(None),
                    Message.created_at >= start_date
                )
            ).group_by(Message.intent).order_by(func.count(Message.id).desc()).limit(5)

            result = await session.execute(intent_query)
            top_intents = [{"intent": row[0], "count": row[1]} for row in result]

            return {
                "period_days": period_days,
                "messages_processed": total_messages,
                "conversations_handled": total_conversations,
                "handoff_rate": round(handoff_rate, 1),
                "intent_recognition_rate": round(
                    (messages_with_intent / total_messages * 100)
                    if total_messages > 0 else 0, 1
                ),
                "average_confidence": round(float(avg_confidence) if avg_confidence else 0, 2),
                "top_intents": top_intents
            }

    except Exception as e:
        logger.error("Error getting agent performance", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get agent performance metrics"
        )


@router.get("/trends/leads")
async def get_lead_trends(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365),
        group_by: str = Query("day", regex="^(day|week|month)$")
):
    """
    Get lead trends over time
    
    Returns lead acquisition and conversion trends
    """
    try:
        async with get_session() as session:
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Determine grouping
            if group_by == "day":
                date_trunc = func.date_trunc('day', Lead.created_at)
            elif group_by == "week":
                date_trunc = func.date_trunc('week', Lead.created_at)
            else:
                date_trunc = func.date_trunc('month', Lead.created_at)

            # Lead acquisition trend
            acquisition_query = select(
                date_trunc.label('period'),
                func.count(Lead.id).label('count')
            ).where(
                and_(
                    Lead.tenant_id == current_tenant.id,
                    Lead.created_at >= start_date
                )
            ).group_by(date_trunc).order_by(date_trunc)

            result = await session.execute(acquisition_query)
            acquisition_trend = [
                {
                    "period": row[0].isoformat(),
                    "count": row[1]
                }
                for row in result
            ]

            # Lead source distribution
            source_query = select(
                Lead.source,
                func.count(Lead.id).label('count')
            ).where(
                and_(
                    Lead.tenant_id == current_tenant.id,
                    Lead.created_at >= start_date
                )
            ).group_by(Lead.source)

            result = await session.execute(source_query)
            source_distribution = [
                {
                    "source": row[0],
                    "count": row[1]
                }
                for row in result
            ]

            # Lead status distribution
            status_query = select(
                Lead.status,
                func.count(Lead.id).label('count')
            ).where(
                and_(
                    Lead.tenant_id == current_tenant.id,
                    Lead.created_at >= start_date
                )
            ).group_by(Lead.status)

            result = await session.execute(status_query)
            status_distribution = [
                {
                    "status": row[0].value,
                    "count": row[1]
                }
                for row in result
            ]

            return {
                "period_days": period_days,
                "group_by": group_by,
                "acquisition_trend": acquisition_trend,
                "source_distribution": source_distribution,
                "status_distribution": status_distribution
            }

    except Exception as e:
        logger.error("Error getting lead trends", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get lead trends"
        )


@router.get("/property-performance")
async def get_property_performance(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365)
):
    """
    Get property performance metrics
    
    Returns metrics about property views and interest
    """
    try:
        async with get_session() as session:
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Most viewed properties (based on appointments)
            popular_properties_query = select(
                Property.id,
                Property.title,
                Property.price,
                Property.neighborhood,
                func.count(Appointment.id).label('appointment_count')
            ).join(
                Appointment, Appointment.property_id == Property.id
            ).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Appointment.created_at >= start_date
                )
            ).group_by(
                Property.id, Property.title, Property.price, Property.neighborhood
            ).order_by(func.count(Appointment.id).desc()).limit(10)

            result = await session.execute(popular_properties_query)
            popular_properties = [
                {
                    "id": str(row[0]),
                    "title": row[1],
                    "price": float(row[2]),
                    "neighborhood": row[3],
                    "appointment_count": row[4]
                }
                for row in result
            ]

            # Properties by status
            status_query = select(
                Property.status,
                func.count(Property.id).label('count')
            ).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True
                )
            ).group_by(Property.status)

            result = await session.execute(status_query)
            status_distribution = {
                row[0].value: row[1] for row in result
            }

            # Average days on market (simplified)
            avg_days_on_market_query = select(
                func.avg(
                    extract('epoch', func.now() - Property.created_at) / 86400
                )
            ).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.status == PropertyStatus.AVAILABLE
                )
            )

            avg_days_on_market = await session.scalar(avg_days_on_market_query)

            # Price range distribution
            price_ranges = [
                (0, 200000, "Up to 200k"),
                (200000, 500000, "200k-500k"),
                (500000, 1000000, "500k-1M"),
                (1000000, None, "1M+")
            ]

            price_distribution = []
            for min_price, max_price, label in price_ranges:
                conditions = [
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True,
                    Property.price >= min_price
                ]
                if max_price:
                    conditions.append(Property.price < max_price)

                count = await session.scalar(
                    select(func.count(Property.id)).where(and_(*conditions))
                )

                price_distribution.append({
                    "range": label,
                    "count": count
                })

            return {
                "period_days": period_days,
                "popular_properties": popular_properties,
                "status_distribution": status_distribution,
                "average_days_on_market": round(float(avg_days_on_market) if avg_days_on_market else 0, 1),
                "price_distribution": price_distribution
            }

    except Exception as e:
        logger.error("Error getting property performance", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get property performance metrics"
        )


@router.get("/conversion-funnel")
async def get_conversion_funnel(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        period_days: int = Query(30, ge=1, le=365)
):
    """
    Get conversion funnel metrics
    
    Returns the conversion funnel from lead to customer
    """
    try:
        async with get_session() as session:
            start_date = datetime.utcnow() - timedelta(days=period_days)

            # Total leads
            total_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.created_at >= start_date
                    )
                )
            )

            # Contacted leads
            contacted_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.status.in_([LeadStatus.CONTACTED, LeadStatus.QUALIFIED, LeadStatus.CONVERTED]),
                        Lead.created_at >= start_date
                    )
                )
            )

            # Qualified leads
            qualified_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.status.in_([LeadStatus.QUALIFIED, LeadStatus.CONVERTED]),
                        Lead.created_at >= start_date
                    )
                )
            )

            # Leads with appointments
            leads_with_appointments = await session.scalar(
                select(func.count(func.distinct(Appointment.lead_id))).where(
                    and_(
                        Appointment.tenant_id == current_tenant.id,
                        Appointment.created_at >= start_date
                    )
                )
            )

            # Converted leads
            converted_leads = await session.scalar(
                select(func.count(Lead.id)).where(
                    and_(
                        Lead.tenant_id == current_tenant.id,
                        Lead.status == LeadStatus.CONVERTED,
                        Lead.created_at >= start_date
                    )
                )
            )

            # Calculate conversion rates
            funnel = [
                {
                    "stage": "Total Leads",
                    "count": total_leads,
                    "percentage": 100.0
                },
                {
                    "stage": "Contacted",
                    "count": contacted_leads,
                    "percentage": round((contacted_leads / total_leads * 100) if total_leads > 0 else 0, 1)
                },
                {
                    "stage": "Qualified",
                    "count": qualified_leads,
                    "percentage": round((qualified_leads / total_leads * 100) if total_leads > 0 else 0, 1)
                },
                {
                    "stage": "Appointments",
                    "count": leads_with_appointments,
                    "percentage": round((leads_with_appointments / total_leads * 100) if total_leads > 0 else 0, 1)
                },
                {
                    "stage": "Converted",
                    "count": converted_leads,
                    "percentage": round((converted_leads / total_leads * 100) if total_leads > 0 else 0, 1)
                }
            ]

            # Stage-to-stage conversion rates
            stage_conversions = []
            for i in range(1, len(funnel)):
                prev_count = funnel[i - 1]["count"]
                curr_count = funnel[i]["count"]
                conversion_rate = (curr_count / prev_count * 100) if prev_count > 0 else 0

                stage_conversions.append({
                    "from_stage": funnel[i - 1]["stage"],
                    "to_stage": funnel[i]["stage"],
                    "conversion_rate": round(conversion_rate, 1)
                })

            return {
                "period_days": period_days,
                "funnel": funnel,
                "stage_conversions": stage_conversions,
                "overall_conversion_rate": round(
                    (converted_leads / total_leads * 100) if total_leads > 0 else 0, 1
                )
            }

    except Exception as e:
        logger.error("Error getting conversion funnel", error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get conversion funnel metrics"
        )


async def _calculate_avg_response_time(session, tenant_id: str, start_date: datetime) -> float:
    """Calculate average response time in minutes"""
    try:
        # This is a simplified calculation
        # In production, you'd track actual response times
        conversations_with_messages = await session.scalar(
            select(func.count(func.distinct(Conversation.id))).where(
                and_(
                    Conversation.tenant_id == tenant_id,
                    Conversation.started_at >= start_date
                )
            )
        )

        # Assume average of 5 minutes response time for now
        return 5.0

    except Exception:
        return 0.0
