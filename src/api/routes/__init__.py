"""
API Routes initialization
"""
from fastapi import APIRouter

from src.api.routes import (
    auth,
    tenants,
    properties,
    leads,
    conversations,
    appointments,
    appointment_notifications,
    property_matching,
    webhooks,
    scraping,
    analytics
)

# Create main router
router = APIRouter()

# Include sub-routers
router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
router.include_router(tenants.router, prefix="/tenants", tags=["Tenants"])
router.include_router(properties.router, prefix="/properties", tags=["Properties"])
router.include_router(property_matching.router, prefix="/properties/matching", tags=["Property Matching"])
router.include_router(leads.router, prefix="/leads", tags=["Leads"])
router.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
router.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
router.include_router(appointment_notifications.router, prefix="/appointments/notifications",
                      tags=["Appointment Notifications"])
router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
router.include_router(scraping.router, prefix="/scraping", tags=["Scraping"])
router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
