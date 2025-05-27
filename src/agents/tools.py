"""
Tools for the Property AI Agent
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any

import structlog
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import get_session
from src.database.models import Property, Lead, Appointment, PropertyStatus
from src.integrations.google_calendar import GoogleCalendarClient

logger = structlog.get_logger()


async def search_properties_tool(tenant_id: str, query: str) -> Dict[str, Any]:
    """
    Search for properties based on criteria
    
    Args:
        tenant_id: Tenant identifier
        query: JSON string with search criteria
    
    Returns:
        Dict with found properties
    """
    try:
        # Parse search criteria
        if isinstance(query, str):
            criteria = json.loads(query)
        else:
            criteria = query

        async with get_session() as session:
            # Build query
            stmt = select(Property).where(
                and_(
                    Property.tenant_id == tenant_id,
                    Property.status == PropertyStatus.AVAILABLE,
                    Property.is_active == True
                )
            )

            # Apply filters
            if "city" in criteria:
                stmt = stmt.where(Property.city.ilike(f"%{criteria['city']}%"))

            if "neighborhood" in criteria:
                stmt = stmt.where(Property.neighborhood.ilike(f"%{criteria['neighborhood']}%"))

            if "property_type" in criteria:
                stmt = stmt.where(Property.property_type == criteria["property_type"])

            if "min_price" in criteria:
                stmt = stmt.where(Property.price >= criteria["min_price"])

            if "max_price" in criteria:
                stmt = stmt.where(Property.price <= criteria["max_price"])

            if "bedrooms" in criteria:
                if isinstance(criteria["bedrooms"], dict):
                    if "min" in criteria["bedrooms"]:
                        stmt = stmt.where(Property.bedrooms >= criteria["bedrooms"]["min"])
                    if "max" in criteria["bedrooms"]:
                        stmt = stmt.where(Property.bedrooms <= criteria["bedrooms"]["max"])
                else:
                    stmt = stmt.where(Property.bedrooms == criteria["bedrooms"])

            if "min_area" in criteria:
                stmt = stmt.where(Property.total_area >= criteria["min_area"])

            if "max_area" in criteria:
                stmt = stmt.where(Property.total_area <= criteria["max_area"])

            # Execute query
            result = await session.execute(stmt.limit(10))
            properties = result.scalars().all()

            # Format response
            properties_data = []
            for prop in properties:
                properties_data.append({
                    "property_id": str(prop.id),
                    "title": prop.title,
                    "description": prop.description[:200] + "..." if len(prop.description) > 200 else prop.description,
                    "price": prop.price,
                    "bedrooms": prop.bedrooms,
                    "bathrooms": prop.bathrooms,
                    "area": prop.total_area,
                    "address": prop.address,
                    "neighborhood": prop.neighborhood,
                    "city": prop.city,
                    "features": prop.features[:5] if prop.features else []
                })

            return {
                "success": True,
                "count": len(properties_data),
                "properties": properties_data,
                "search_criteria": criteria
            }

    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "Invalid search criteria format",
            "properties": []
        }
    except Exception as e:
        logger.error("Error searching properties", error=str(e), tenant_id=tenant_id)
        return {
            "success": False,
            "error": "Failed to search properties",
            "properties": []
        }


async def get_property_details_tool(tenant_id: str, property_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific property
    
    Args:
        tenant_id: Tenant identifier
        property_id: Property identifier
    
    Returns:
        Dict with property details
    """
    try:
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == tenant_id
                )
            )

            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                return {
                    "success": False,
                    "error": "Property not found"
                }

            return {
                "success": True,
                "property": {
                    "id": str(property.id),
                    "title": property.title,
                    "description": property.description,
                    "property_type": property.property_type,
                    "transaction_type": property.transaction_type,
                    "price": property.price,
                    "condo_fee": property.condo_fee,
                    "property_tax": property.property_tax,
                    "address": property.address,
                    "neighborhood": property.neighborhood,
                    "city": property.city,
                    "state": property.state,
                    "zip_code": property.zip_code,
                    "bedrooms": property.bedrooms,
                    "bathrooms": property.bathrooms,
                    "parking_spaces": property.parking_spaces,
                    "total_area": property.total_area,
                    "built_area": property.built_area,
                    "floor": property.floor,
                    "total_floors": property.total_floors,
                    "features": property.features,
                    "amenities": property.amenities,
                    "images": property.images[:5] if property.images else [],
                    "video_url": property.video_url,
                    "virtual_tour_url": property.virtual_tour_url,
                    "status": property.status.value,
                    "available": property.status == PropertyStatus.AVAILABLE
                }
            }

    except Exception as e:
        logger.error("Error getting property details", error=str(e), property_id=property_id)
        return {
            "success": False,
            "error": "Failed to get property details"
        }


async def schedule_appointment_tool(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Schedule a property viewing appointment
    
    Args:
        tenant_id: Tenant identifier
        data: Appointment data (property_id, lead_id, datetime, notes)
    
    Returns:
        Dict with scheduling result
    """
    try:
        required_fields = ["property_id", "lead_id", "datetime"]
        for field in required_fields:
            if field not in data:
                return {
                    "success": False,
                    "error": f"Missing required field: {field}"
                }

        # Parse datetime
        appointment_dt = datetime.fromisoformat(data["datetime"])

        # Validate appointment time (business hours)
        if appointment_dt.hour < 8 or appointment_dt.hour >= 19:
            return {
                "success": False,
                "error": "Appointments must be scheduled between 8 AM and 7 PM"
            }

        # Check if slot is available
        async with get_session() as session:
            # Check for conflicts
            stmt = select(Appointment).where(
                and_(
                    Appointment.tenant_id == tenant_id,
                    Appointment.scheduled_at >= appointment_dt - timedelta(hours=1),
                    Appointment.scheduled_at <= appointment_dt + timedelta(hours=1),
                    Appointment.status.in_(["scheduled", "confirmed"])
                )
            )

            result = await session.execute(stmt)
            conflicts = result.scalars().all()

            if conflicts:
                return {
                    "success": False,
                    "error": "This time slot is not available. Please choose another time."
                }

            # Create appointment
            appointment = Appointment(
                tenant_id=tenant_id,
                lead_id=data["lead_id"],
                property_id=data["property_id"],
                scheduled_at=appointment_dt,
                duration_minutes=data.get("duration_minutes", 60),
                notes=data.get("notes", ""),
                location_details=data.get("location_details", "")
            )

            session.add(appointment)
            await session.commit()

            # Create Google Calendar event
            try:
                calendar_client = GoogleCalendarClient(tenant_id)
                event_result = await calendar_client.create_appointment_event(
                    appointment_id=str(appointment.id),
                    property_id=data["property_id"],
                    scheduled_at=appointment_dt,
                    duration_minutes=appointment.duration_minutes,
                    notes=appointment.notes
                )

                # Update appointment with calendar info
                appointment.google_event_id = event_result["id"]
                appointment.calendar_link = event_result["htmlLink"]
                await session.commit()

            except Exception as e:
                logger.error("Failed to create calendar event", error=str(e))

            return {
                "success": True,
                "appointment_id": str(appointment.id),
                "scheduled_at": appointment.scheduled_at.isoformat(),
                "calendar_link": appointment.calendar_link,
                "message": f"Appointment scheduled for {appointment_dt.strftime('%d/%m/%Y at %H:%M')}"
            }

    except Exception as e:
        logger.error("Error scheduling appointment", error=str(e), data=data)
        return {
            "success": False,
            "error": "Failed to schedule appointment"
        }


async def capture_lead_info_tool(tenant_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Capture and update lead information
    
    Args:
        tenant_id: Tenant identifier
        data: Lead information to capture/update
    
    Returns:
        Dict with operation result
    """
    try:
        phone = data.get("phone")
        if not phone:
            return {
                "success": False,
                "error": "Phone number is required"
            }

        async with get_session() as session:
            # Try to find existing lead
            stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == tenant_id,
                    Lead.phone == phone
                )
            )

            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            captured_info = {}

            if lead:
                # Update existing lead
                if "name" in data and data["name"]:
                    lead.name = data["name"]
                    captured_info["name"] = data["name"]

                if "email" in data and data["email"]:
                    lead.email = data["email"]
                    captured_info["email"] = data["email"]

                if "preferences" in data:
                    lead.preferences = {**lead.preferences, **data["preferences"]}
                    captured_info["preferences"] = data["preferences"]

                if "budget_min" in data:
                    lead.budget_min = data["budget_min"]
                    captured_info["budget_min"] = data["budget_min"]

                if "budget_max" in data:
                    lead.budget_max = data["budget_max"]
                    captured_info["budget_max"] = data["budget_max"]

                if "preferred_locations" in data:
                    lead.preferred_locations = data["preferred_locations"]
                    captured_info["preferred_locations"] = data["preferred_locations"]

                lead.last_contact_at = datetime.utcnow()

            else:
                # Create new lead
                lead = Lead(
                    tenant_id=tenant_id,
                    phone=phone,
                    name=data.get("name"),
                    email=data.get("email"),
                    preferences=data.get("preferences", {}),
                    budget_min=data.get("budget_min"),
                    budget_max=data.get("budget_max"),
                    preferred_locations=data.get("preferred_locations", []),
                    property_type_interest=data.get("property_type_interest", []),
                    source="whatsapp",
                    source_details={"captured_via": "ai_agent"}
                )
                session.add(lead)
                captured_info = {k: v for k, v in data.items() if v is not None}

            await session.commit()

            return {
                "success": True,
                "lead_id": str(lead.id),
                "is_new": lead.created_at == lead.updated_at,
                "captured_info": captured_info,
                "message": "Lead information captured successfully"
            }

    except Exception as e:
        logger.error("Error capturing lead info", error=str(e), data=data)
        return {
            "success": False,
            "error": "Failed to capture lead information"
        }


async def check_availability_tool(tenant_id: str, date_str: str) -> Dict[str, Any]:
    """
    Check agent availability for appointments
    
    Args:
        tenant_id: Tenant identifier
        date_str: Date to check (ISO format)
    
    Returns:
        Dict with available time slots
    """
    try:
        check_date = datetime.fromisoformat(date_str).date()

        # Business hours
        business_hours = {
            "start": 8,  # 8 AM
            "end": 19,  # 7 PM
            "slot_duration": 60  # 60 minutes per slot
        }

        async with get_session() as session:
            # Get all appointments for the date
            stmt = select(Appointment).where(
                and_(
                    Appointment.tenant_id == tenant_id,
                    Appointment.scheduled_at >= datetime.combine(check_date, datetime.min.time()),
                    Appointment.scheduled_at < datetime.combine(check_date + timedelta(days=1), datetime.min.time()),
                    Appointment.status.in_(["scheduled", "confirmed"])
                )
            )

            result = await session.execute(stmt)
            appointments = result.scalars().all()

            # Generate all possible slots
            available_slots = []
            current_time = datetime.combine(check_date, datetime.min.time().replace(hour=business_hours["start"]))
            end_time = datetime.combine(check_date, datetime.min.time().replace(hour=business_hours["end"]))

            while current_time < end_time:
                # Check if slot is available
                is_available = True
                for appointment in appointments:
                    appointment_end = appointment.scheduled_at + timedelta(minutes=appointment.duration_minutes)
                    if (current_time >= appointment.scheduled_at and current_time < appointment_end) or \
                            (current_time <= appointment.scheduled_at and current_time + timedelta(
                                minutes=business_hours["slot_duration"]) > appointment.scheduled_at):
                        is_available = False
                        break

                if is_available and current_time > datetime.now():
                    available_slots.append({
                        "start": current_time.isoformat(),
                        "end": (current_time + timedelta(minutes=business_hours["slot_duration"])).isoformat(),
                        "formatted": current_time.strftime("%H:%M")
                    })

                current_time += timedelta(minutes=30)  # Check every 30 minutes

            return {
                "success": True,
                "date": check_date.isoformat(),
                "available_slots": available_slots,
                "total_available": len(available_slots),
                "business_hours": f"{business_hours['start']}:00 - {business_hours['end']}:00"
            }

    except Exception as e:
        logger.error("Error checking availability", error=str(e), date=date_str)
        return {
            "success": False,
            "error": "Failed to check availability",
            "available_slots": []
        }


async def request_human_handoff_tool(tenant_id: str, conversation_id: str, reason: str) -> Dict[str, Any]:
    """
    Request handoff to human agent
    
    Args:
        tenant_id: Tenant identifier
        conversation_id: Conversation identifier
        reason: Reason for handoff
    
    Returns:
        Dict with handoff result
    """
    try:
        # This would typically update the conversation status and notify human agents
        # For now, we'll just return a success response

        return {
            "success": True,
            "message": "Handoff requested successfully",
            "reason": reason,
            "estimated_wait_time": "5-10 minutes"
        }

    except Exception as e:
        logger.error("Error requesting handoff", error=str(e))
        return {
            "success": False,
            "error": "Failed to request handoff"
        }
