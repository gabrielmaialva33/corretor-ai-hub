"""
Property matching routes for lead-property recommendations
"""
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select, and_

from src.api.routes.auth import get_current_active_tenant
from src.database.connection import get_session
from src.database.models import Tenant, Lead, Property
from src.services.property_matcher import PropertyMatcher

logger = structlog.get_logger()
router = APIRouter()


class PropertyMatchRequest(BaseModel):
    """Request for finding matching properties"""
    lead_id: str
    limit: int = 10
    min_score: float = 0.7


class LeadMatchRequest(BaseModel):
    """Request for finding matching leads"""
    property_id: str
    limit: int = 20
    min_score: float = 0.7


class WeeklyMatchingRequest(BaseModel):
    """Request for running weekly matching"""
    property_ids: Optional[List[str]] = None


@router.post("/find-properties")
async def find_matching_properties(
        request: PropertyMatchRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Find properties matching lead preferences
    
    Returns scored list of suitable properties
    """
    try:
        # Verify lead belongs to tenant
        async with get_session() as session:
            stmt = select(Lead).where(
                and_(
                    Lead.id == request.lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lead not found"
                )

        # Find matches
        matcher = PropertyMatcher()
        matches = await matcher.find_matching_properties(
            request.lead_id,
            request.limit,
            request.min_score
        )

        # Format response
        results = []
        for match in matches:
            property = match["property"]
            results.append({
                "property_id": str(property.id),
                "title": property.title,
                "price": property.price,
                "location": {
                    "address": property.address,
                    "neighborhood": property.neighborhood,
                    "city": property.city
                },
                "details": {
                    "bedrooms": property.bedrooms,
                    "bathrooms": property.bathrooms,
                    "area": property.area,
                    "property_type": property.property_type.value if property.property_type else None
                },
                "match_score": round(match["score"], 2),
                "score_breakdown": {
                    k: round(v, 2) for k, v in match["breakdown"].items()
                },
                "source_url": property.source_url
            })

        return {
            "lead_id": request.lead_id,
            "matches": results,
            "total_matches": len(results)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error finding matching properties", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find matching properties"
        )


@router.post("/find-leads")
async def find_matching_leads(
        request: LeadMatchRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Find leads interested in a specific property
    
    Returns scored list of potential buyers/renters
    """
    try:
        # Verify property belongs to tenant
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == request.property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Property not found"
                )

        # Find matches
        matcher = PropertyMatcher()
        matches = await matcher.find_leads_for_property(
            request.property_id,
            request.limit,
            request.min_score
        )

        # Format response
        results = []
        for match in matches:
            lead = match["lead"]
            results.append({
                "lead_id": str(lead.id),
                "name": lead.name,
                "phone": lead.phone,
                "email": lead.email,
                "preferences": {
                    "budget_min": lead.budget_min,
                    "budget_max": lead.budget_max,
                    "preferred_locations": lead.preferred_locations,
                    "property_types": [t.value for t in
                                       lead.property_type_interest] if lead.property_type_interest else [],
                    "other": lead.preferences
                },
                "match_score": round(match["score"], 2),
                "score_breakdown": {
                    k: round(v, 2) for k, v in match["breakdown"].items()
                },
                "lead_status": lead.status.value if lead.status else None,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None
            })

        return {
            "property_id": request.property_id,
            "matches": results,
            "total_matches": len(results)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error finding matching leads", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find matching leads"
        )


@router.post("/run-weekly-matching")
async def run_weekly_matching(
        request: WeeklyMatchingRequest,
        background_tasks: BackgroundTasks,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Run weekly matching process
    
    Matches all active leads with new/specified properties
    """
    try:
        # Verify property IDs if provided
        if request.property_ids:
            async with get_session() as session:
                stmt = select(Property.id).where(
                    and_(
                        Property.id.in_(request.property_ids),
                        Property.tenant_id == current_tenant.id
                    )
                )
                result = await session.execute(stmt)
                valid_ids = [str(id) for id in result.scalars().all()]

                if len(valid_ids) != len(request.property_ids):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Some property IDs are invalid or don't belong to tenant"
                    )

        # Run matching in background
        matcher = PropertyMatcher()
        background_tasks.add_task(
            matcher.run_weekly_matching,
            str(current_tenant.id),
            request.property_ids
        )

        return {
            "message": "Weekly matching process started",
            "tenant_id": str(current_tenant.id),
            "property_ids": request.property_ids,
            "status": "running"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting weekly matching", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start weekly matching"
        )


@router.get("/matching-stats")
async def get_matching_statistics(
        days_back: int = 30,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get property matching statistics
    
    Shows matching performance and insights
    """
    try:
        async with get_session() as session:
            # Get leads with preferences
            leads_stmt = select(Lead).where(
                and_(
                    Lead.tenant_id == current_tenant.id,
                    Lead.status.in_(["new", "contacted", "qualified"])
                )
            )
            leads_result = await session.execute(leads_stmt)
            all_leads = leads_result.scalars().all()

            # Count leads with different preference types
            leads_with_budget = sum(1 for l in all_leads if l.budget_min or l.budget_max)
            leads_with_location = sum(1 for l in all_leads if l.preferred_locations)
            leads_with_type = sum(1 for l in all_leads if l.property_type_interest)
            leads_with_any_pref = sum(
                1 for l in all_leads
                if l.budget_min or l.budget_max or l.preferred_locations or l.property_type_interest
            )

            # Get properties
            properties_stmt = select(Property).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.status == "available",
                    Property.is_active == True
                )
            )
            properties_result = await session.execute(properties_stmt)
            property_count = len(properties_result.scalars().all())

            return {
                "period_days": days_back,
                "lead_statistics": {
                    "total_active_leads": len(all_leads),
                    "leads_with_preferences": leads_with_any_pref,
                    "leads_with_budget": leads_with_budget,
                    "leads_with_location_pref": leads_with_location,
                    "leads_with_type_pref": leads_with_type
                },
                "property_statistics": {
                    "total_available": property_count
                },
                "matching_potential": {
                    "max_possible_matches": leads_with_any_pref * property_count,
                    "average_properties_per_lead": property_count if leads_with_any_pref > 0 else 0
                }
            }

    except Exception as e:
        logger.error("Error getting matching statistics", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get matching statistics"
        )


@router.post("/test-match")
async def test_property_lead_match(
        lead_id: str,
        property_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Test match score between specific lead and property
    
    Useful for debugging matching algorithm
    """
    try:
        # Verify both belong to tenant
        async with get_session() as session:
            # Check lead
            lead_stmt = select(Lead).where(
                and_(
                    Lead.id == lead_id,
                    Lead.tenant_id == current_tenant.id
                )
            )
            lead_result = await session.execute(lead_stmt)
            lead = lead_result.scalar_one_or_none()

            if not lead:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lead not found"
                )

            # Check property
            property_stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            property_result = await session.execute(property_stmt)
            property = property_result.scalar_one_or_none()

            if not property:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Property not found"
                )

        # Calculate match
        matcher = PropertyMatcher()
        score, breakdown = matcher._calculate_match_score(lead, property)

        return {
            "lead": {
                "id": str(lead.id),
                "name": lead.name,
                "preferences": {
                    "budget_min": lead.budget_min,
                    "budget_max": lead.budget_max,
                    "preferred_locations": lead.preferred_locations,
                    "property_types": [t.value for t in
                                       lead.property_type_interest] if lead.property_type_interest else [],
                    "other": lead.preferences
                }
            },
            "property": {
                "id": str(property.id),
                "title": property.title,
                "price": property.price,
                "location": f"{property.neighborhood}, {property.city}" if property.neighborhood else property.city,
                "type": property.property_type.value if property.property_type else None,
                "bedrooms": property.bedrooms,
                "area": property.area
            },
            "match_score": round(score, 2),
            "score_breakdown": {
                k: round(v, 2) for k, v in breakdown.items()
            },
            "match_percentage": round(score * 100, 1)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error testing match", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test match"
        )
