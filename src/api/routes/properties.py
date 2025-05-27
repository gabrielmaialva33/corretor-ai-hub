"""
Property management routes
"""
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.auth import get_current_active_tenant
from src.core.exceptions import NotFoundError
from src.database.connection import get_session
from src.database.models import Property, Tenant, PropertyStatus
from src.database.schemas import (
    PropertyCreate, PropertyUpdate, PropertyResponse,
    PaginatedResponse,
    SuccessResponse
)
from src.integrations.qdrant import QdrantManager

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
async def create_property(
        property_data: PropertyCreate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Create a new property
    
    Add a new property to the tenant's inventory
    """
    try:
        async with get_session() as session:
            # Check if property with same source_id already exists
            if property_data.source_id:
                stmt = select(Property).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.source_id == property_data.source_id
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Property with this source ID already exists"
                    )

            # Create property
            property_dict = property_data.dict()
            property_dict["tenant_id"] = current_tenant.id

            property = Property(**property_dict)
            session.add(property)
            await session.commit()
            await session.refresh(property)

            # TODO: Add to vector database for semantic search

            logger.info(f"Created property: {property.id}")
            return property

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error creating property", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create property"
        )


@router.get("/", response_model=PaginatedResponse)
async def list_properties(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        # Filters
        city: Optional[str] = None,
        neighborhood: Optional[str] = None,
        property_type: Optional[str] = None,
        transaction_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        min_area: Optional[float] = None,
        max_area: Optional[float] = None,
        status: Optional[PropertyStatus] = None,
        # Pagination
        skip: int = Query(0, ge=0),
        limit: int = Query(10, ge=1, le=100),
        # Sorting
        sort_by: str = Query("created_at", regex="^(created_at|price|area|bedrooms)$"),
        sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    """
    List properties with filters
    
    Get a paginated list of properties with optional filters
    """
    try:
        async with get_session() as session:
            # Build query
            stmt = select(Property).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True
                )
            )

            # Apply filters
            if city:
                stmt = stmt.where(Property.city.ilike(f"%{city}%"))
            if neighborhood:
                stmt = stmt.where(Property.neighborhood.ilike(f"%{neighborhood}%"))
            if property_type:
                stmt = stmt.where(Property.property_type == property_type)
            if transaction_type:
                stmt = stmt.where(Property.transaction_type == transaction_type)
            if min_price is not None:
                stmt = stmt.where(Property.price >= min_price)
            if max_price is not None:
                stmt = stmt.where(Property.price <= max_price)
            if min_bedrooms is not None:
                stmt = stmt.where(Property.bedrooms >= min_bedrooms)
            if max_bedrooms is not None:
                stmt = stmt.where(Property.bedrooms <= max_bedrooms)
            if min_area is not None:
                stmt = stmt.where(Property.total_area >= min_area)
            if max_area is not None:
                stmt = stmt.where(Property.total_area <= max_area)
            if status:
                stmt = stmt.where(Property.status == status)

            # Count total
            count_stmt = select(func.count()).select_from(stmt.subquery())
            total = await session.scalar(count_stmt)

            # Apply sorting
            sort_column = getattr(Property, sort_by)
            if sort_order == "desc":
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())

            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)

            # Execute query
            result = await session.execute(stmt)
            properties = result.scalars().all()

            return PaginatedResponse(
                items=properties,
                total=total,
                limit=limit,
                offset=skip,
                has_more=(skip + limit) < total
            )

    except Exception as e:
        logger.error("Error listing properties", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list properties"
        )


@router.get("/search", response_model=List[PropertyResponse])
async def search_properties(
        query: str,
        current_tenant: Tenant = Depends(get_current_active_tenant),
        limit: int = Query(10, ge=1, le=50)
):
    """
    Search properties using semantic search
    
    Uses AI embeddings to find properties matching the natural language query
    """
    try:
        # Use vector database for semantic search
        vector_manager = QdrantManager(str(current_tenant.id))

        # Get embedding for query
        from langchain.embeddings import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings()
        query_embedding = await embeddings.aembed_query(query)

        # Search in vector database
        search_results = await vector_manager.search_properties(
            query_embedding=query_embedding,
            limit=limit
        )

        if not search_results:
            return []

        # Get full property details
        property_ids = [result["property_id"] for result in search_results]

        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id.in_(property_ids),
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True
                )
            )
            result = await session.execute(stmt)
            properties = result.scalars().all()

            # Sort by search score
            property_dict = {str(p.id): p for p in properties}
            sorted_properties = []
            for result in search_results:
                if result["property_id"] in property_dict:
                    sorted_properties.append(property_dict[result["property_id"]])

            return sorted_properties

    except Exception as e:
        logger.error("Error searching properties", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search properties"
        )


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
        property_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get property details
    
    Get detailed information about a specific property
    """
    try:
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                raise NotFoundError("Property", property_id)

            return property

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found"
        )
    except Exception as e:
        logger.error("Error getting property", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get property"
        )


@router.patch("/{property_id}", response_model=PropertyResponse)
async def update_property(
        property_id: str,
        property_update: PropertyUpdate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Update property information
    
    Update details of an existing property
    """
    try:
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                raise NotFoundError("Property", property_id)

            # Update fields
            update_data = property_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(property, field, value)

            await session.commit()
            await session.refresh(property)

            # TODO: Update vector database if description changed

            logger.info(f"Updated property: {property_id}")
            return property

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found"
        )
    except Exception as e:
        logger.error("Error updating property", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update property"
        )


@router.delete("/{property_id}", response_model=SuccessResponse)
async def delete_property(
        property_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Delete a property
    
    Soft delete a property from the inventory
    """
    try:
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                raise NotFoundError("Property", property_id)

            # Soft delete
            property.is_active = False
            property.status = PropertyStatus.INACTIVE

            await session.commit()

            # TODO: Remove from vector database

            logger.info(f"Deleted property: {property_id}")
            return SuccessResponse(
                message="Property deleted successfully"
            )

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found"
        )
    except Exception as e:
        logger.error("Error deleting property", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete property"
        )


@router.post("/{property_id}/toggle-status", response_model=PropertyResponse)
async def toggle_property_status(
        property_id: str,
        new_status: PropertyStatus,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Toggle property status
    
    Change property status (available, reserved, sold, etc.)
    """
    try:
        async with get_session() as session:
            stmt = select(Property).where(
                and_(
                    Property.id == property_id,
                    Property.tenant_id == current_tenant.id
                )
            )
            result = await session.execute(stmt)
            property = result.scalar_one_or_none()

            if not property:
                raise NotFoundError("Property", property_id)

            property.status = new_status

            await session.commit()
            await session.refresh(property)

            logger.info(f"Changed property {property_id} status to {new_status}")
            return property

    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Property {property_id} not found"
        )
    except Exception as e:
        logger.error("Error toggling property status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle property status"
        )


@router.get("/stats/summary")
async def get_properties_summary(
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get properties summary statistics
    
    Returns summary statistics about the property inventory
    """
    try:
        async with get_session() as session:
            # Total properties
            total = await session.scalar(
                select(func.count(Property.id)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.is_active == True
                    )
                )
            )

            # By status
            status_counts = {}
            for status in PropertyStatus:
                count = await session.scalar(
                    select(func.count(Property.id)).where(
                        and_(
                            Property.tenant_id == current_tenant.id,
                            Property.status == status,
                            Property.is_active == True
                        )
                    )
                )
                status_counts[status.value] = count

            # Average price
            avg_price = await session.scalar(
                select(func.avg(Property.price)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.is_active == True
                    )
                )
            )

            # Price range
            min_price = await session.scalar(
                select(func.min(Property.price)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.is_active == True
                    )
                )
            )

            max_price = await session.scalar(
                select(func.max(Property.price)).where(
                    and_(
                        Property.tenant_id == current_tenant.id,
                        Property.is_active == True
                    )
                )
            )

            # By type
            stmt = select(
                Property.property_type,
                func.count(Property.id)
            ).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True
                )
            ).group_by(Property.property_type)

            result = await session.execute(stmt)
            type_counts = dict(result.all())

            # By city
            stmt = select(
                Property.city,
                func.count(Property.id)
            ).where(
                and_(
                    Property.tenant_id == current_tenant.id,
                    Property.is_active == True
                )
            ).group_by(Property.city).order_by(func.count(Property.id).desc()).limit(10)

            result = await session.execute(stmt)
            city_counts = dict(result.all())

            return {
                "total": total,
                "by_status": status_counts,
                "price": {
                    "average": float(avg_price) if avg_price else 0,
                    "min": float(min_price) if min_price else 0,
                    "max": float(max_price) if max_price else 0
                },
                "by_type": type_counts,
                "by_city": city_counts
            }

    except Exception as e:
        logger.error("Error getting properties summary", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get properties summary"
        )
