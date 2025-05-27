"""
Scraping management routes
"""
from typing import Dict, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from src.services.scraping_service import ScrapingService

from src.api.routes.auth import get_current_active_tenant
from src.database.models import Tenant
from src.scrapers.generic_scraper import GenericRealEstateScraper
from src.scrapers.remax_scraper import RemaxArgentinaScraper

logger = structlog.get_logger()
router = APIRouter()


class ScrapingConfigCreate(BaseModel):
    """Schema for creating scraping configuration"""
    name: str
    base_url: str
    listing_url_pattern: str
    use_browser: bool = False
    selectors: Dict[str, str]


class ScrapingJobCreate(BaseModel):
    """Schema for creating a scraping job"""
    config_name: str
    max_pages: int = 10
    max_properties_per_page: int = 20


@router.post("/configs", status_code=status.HTTP_201_CREATED)
async def create_scraping_config(
        config_data: ScrapingConfigCreate,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Create a new scraping configuration
    
    Define selectors and settings for scraping a real estate website
    """
    try:
        scraping_service = ScrapingService()
        config = await scraping_service.create_config(
            tenant_id=str(current_tenant.id),
            config_data=config_data.dict()
        )

        return {
            "message": "Scraping configuration created successfully",
            "config_id": config["id"],
            "config_name": config["name"]
        }

    except Exception as e:
        logger.error("Error creating scraping config", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create scraping configuration"
        )


@router.get("/configs")
async def list_scraping_configs(
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    List all scraping configurations
    
    Get all configured real estate websites for scraping
    """
    try:
        scraping_service = ScrapingService()
        configs = await scraping_service.list_configs(str(current_tenant.id))

        return {
            "configs": configs,
            "total": len(configs)
        }

    except Exception as e:
        logger.error("Error listing scraping configs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list scraping configurations"
        )


@router.get("/configs/{config_id}")
async def get_scraping_config(
        config_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get scraping configuration details
    
    Get details of a specific scraping configuration
    """
    try:
        scraping_service = ScrapingService()
        config = await scraping_service.get_config(
            tenant_id=str(current_tenant.id),
            config_id=config_id
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scraping configuration not found"
            )

        return config

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting scraping config", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scraping configuration"
        )


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def start_scraping_job(
        job_data: ScrapingJobCreate,
        background_tasks: BackgroundTasks,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Start a new scraping job
    
    Begin scraping properties from a configured website
    """
    try:
        scraping_service = ScrapingService()

        # Get configuration
        config = await scraping_service.get_config(
            tenant_id=str(current_tenant.id),
            config_name=job_data.config_name
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scraping configuration not found"
            )

        # Create job record
        job = await scraping_service.create_job(
            tenant_id=str(current_tenant.id),
            config_id=config["id"],
            max_pages=job_data.max_pages,
            max_properties_per_page=job_data.max_properties_per_page
        )

        # Start scraping in background
        background_tasks.add_task(
            scraping_service.run_scraping_job,
            job_id=job["id"],
            tenant_id=str(current_tenant.id),
            config=config,
            max_pages=job_data.max_pages,
            max_properties_per_page=job_data.max_properties_per_page
        )

        return {
            "message": "Scraping job started",
            "job_id": job["id"],
            "status": "running"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error starting scraping job", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start scraping job"
        )


@router.get("/jobs")
async def list_scraping_jobs(
        current_tenant: Tenant = Depends(get_current_active_tenant),
        status: Optional[str] = None,
        limit: int = 10
):
    """
    List scraping jobs
    
    Get history of scraping jobs with their status
    """
    try:
        scraping_service = ScrapingService()
        jobs = await scraping_service.list_jobs(
            tenant_id=str(current_tenant.id),
            status=status,
            limit=limit
        )

        return {
            "jobs": jobs,
            "total": len(jobs)
        }

    except Exception as e:
        logger.error("Error listing scraping jobs", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list scraping jobs"
        )


@router.get("/jobs/{job_id}")
async def get_scraping_job(
        job_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Get scraping job details
    
    Get status and results of a specific scraping job
    """
    try:
        scraping_service = ScrapingService()
        job = await scraping_service.get_job(
            tenant_id=str(current_tenant.id),
            job_id=job_id
        )

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scraping job not found"
            )

        return job

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting scraping job", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get scraping job"
        )


@router.post("/jobs/{job_id}/stop")
async def stop_scraping_job(
        job_id: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Stop a running scraping job
    
    Cancel an in-progress scraping job
    """
    try:
        scraping_service = ScrapingService()
        result = await scraping_service.stop_job(
            tenant_id=str(current_tenant.id),
            job_id=job_id
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Scraping job not found or already stopped"
            )

        return {
            "message": "Scraping job stopped",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error stopping scraping job", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stop scraping job"
        )


@router.post("/test-scraper")
async def test_scraper(
        config_data: ScrapingConfigCreate,
        test_url: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Test scraper configuration
    
    Test selectors on a single property URL
    """
    try:
        # Create temporary scraper
        config = config_data.dict()
        scraper = GenericRealEstateScraper(
            tenant_id=str(current_tenant.id),
            config=config
        )

        async with scraper:
            # Test scraping single property
            property_data = await scraper.scrape_property(test_url)

            if property_data:
                return {
                    "success": True,
                    "property_data": property_data,
                    "message": "Scraper configuration is working correctly"
                }
            else:
                return {
                    "success": False,
                    "property_data": None,
                    "message": "Failed to extract property data. Check your selectors."
                }

    except Exception as e:
        logger.error("Error testing scraper", error=str(e))
        return {
            "success": False,
            "error": str(e),
            "message": "Error occurred while testing scraper"
        }


class RemaxSearchRequest(BaseModel):
    """Schema for REMAX search request"""
    operation: str = "venta"  # venta/alquiler
    property_type: Optional[str] = None  # casa/departamento/etc
    location: Optional[str] = None  # city or neighborhood
    bedrooms: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    limit: int = 20


@router.post("/remax/search")
async def search_remax_properties(
        search_params: RemaxSearchRequest,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Search properties on REMAX Argentina
    
    Search and import properties from REMAX based on filters
    """
    try:
        scraper = RemaxArgentinaScraper(str(current_tenant.id))

        # Perform search
        properties = await scraper.search_properties(
            filters=search_params.dict(exclude_none=True),
            limit=search_params.limit
        )

        # Save properties to database
        saved_count = 0
        errors = []

        for property_data in properties:
            try:
                # Save property
                saved_property = await scraper.save_property(property_data)
                if saved_property:
                    saved_count += 1
            except Exception as e:
                errors.append({
                    "url": property_data.get("source_url"),
                    "error": str(e)
                })

        return {
            "message": f"Found {len(properties)} properties, saved {saved_count}",
            "total_found": len(properties),
            "saved": saved_count,
            "errors": len(errors),
            "error_details": errors[:5] if errors else []
        }

    except Exception as e:
        logger.error("Error searching REMAX properties", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search REMAX properties: {str(e)}"
        )


@router.post("/remax/scrape-url")
async def scrape_remax_url(
        url: str,
        current_tenant: Tenant = Depends(get_current_active_tenant)
):
    """
    Scrape a single REMAX property URL
    
    Import a specific property from its REMAX URL
    """
    try:
        scraper = RemaxArgentinaScraper(str(current_tenant.id))

        # Scrape property
        property_data = await scraper.scrape_property(url)

        if not property_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to scrape property data from URL"
            )

        # Save to database
        saved_property = await scraper.save_property(property_data)

        return {
            "message": "Property scraped and saved successfully",
            "property": saved_property
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error scraping REMAX URL", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to scrape REMAX property: {str(e)}"
        )
