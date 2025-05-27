"""
Pydantic schemas for API validation and serialization
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict, validator

from src.database.models import (
    TenantStatus, ConversationStatus, PropertyStatus,
    AppointmentStatus, LeadStatus
)


# Base schemas
class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(from_attributes=True)


class TimestampedSchema(BaseSchema):
    """Schema with timestamp fields"""
    created_at: datetime
    updated_at: datetime


# Tenant schemas
class TenantBase(BaseSchema):
    """Base tenant schema"""
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    settings: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)


class TenantCreate(TenantBase):
    """Schema for creating a tenant"""
    pass


class TenantUpdate(BaseSchema):
    """Schema for updating a tenant"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=50)
    company_name: Optional[str] = Field(None, max_length=255)
    settings: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, Any]] = None
    status: Optional[TenantStatus] = None


class TenantResponse(TenantBase, TimestampedSchema):
    """Schema for tenant response"""
    id: UUID
    status: TenantStatus
    is_active: bool
    evo_instance_key: Optional[str]
    chatwoot_inbox_id: Optional[int]
    google_calendar_id: Optional[str]
    qdrant_namespace: Optional[str]
    activated_at: Optional[datetime]
    suspended_at: Optional[datetime]


# Property schemas
class PropertyBase(BaseSchema):
    """Base property schema"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    property_type: Optional[str] = Field(None, max_length=100)
    transaction_type: Optional[str] = Field(None, max_length=50)

    # Location
    address: Optional[str] = Field(None, max_length=500)
    neighborhood: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=1, max_length=255)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    # Characteristics
    bedrooms: Optional[int] = Field(None, ge=0)
    bathrooms: Optional[int] = Field(None, ge=0)
    parking_spaces: Optional[int] = Field(None, ge=0)
    total_area: Optional[float] = Field(None, ge=0)
    built_area: Optional[float] = Field(None, ge=0)
    floor: Optional[int] = None
    total_floors: Optional[int] = Field(None, ge=1)

    # Financial
    price: float = Field(..., ge=0)
    condo_fee: Optional[float] = Field(None, ge=0)
    property_tax: Optional[float] = Field(None, ge=0)

    # Features
    features: List[str] = Field(default_factory=list)
    amenities: List[str] = Field(default_factory=list)

    # Media
    images: List[str] = Field(default_factory=list)
    video_url: Optional[str] = Field(None, max_length=500)
    virtual_tour_url: Optional[str] = Field(None, max_length=500)


class PropertyCreate(PropertyBase):
    """Schema for creating a property"""
    source_url: Optional[str] = Field(None, max_length=500)
    source_id: Optional[str] = Field(None, max_length=255)


class PropertyUpdate(BaseSchema):
    """Schema for updating a property"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    status: Optional[PropertyStatus] = None
    is_active: Optional[bool] = None
    # Add other optional fields as needed


class PropertyResponse(PropertyBase, TimestampedSchema):
    """Schema for property response"""
    id: UUID
    tenant_id: UUID
    status: PropertyStatus
    is_active: bool
    source_url: Optional[str]
    source_id: Optional[str]
    scraped_at: Optional[datetime]


class PropertySearchParams(BaseSchema):
    """Schema for property search parameters"""
    city: Optional[str] = None
    neighborhood: Optional[str] = None
    property_type: Optional[str] = None
    transaction_type: Optional[str] = None
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    min_bedrooms: Optional[int] = Field(None, ge=0)
    max_bedrooms: Optional[int] = Field(None, ge=0)
    min_area: Optional[float] = Field(None, ge=0)
    max_area: Optional[float] = Field(None, ge=0)
    features: Optional[List[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @validator("max_price")
    def validate_price_range(cls, v, values):
        if v and "min_price" in values and values["min_price"] and v < values["min_price"]:
            raise ValueError("max_price must be greater than min_price")
        return v


# Lead schemas
class LeadBase(BaseSchema):
    """Base lead schema"""
    name: Optional[str] = Field(None, max_length=255)
    phone: str = Field(..., min_length=10, max_length=50)
    email: Optional[EmailStr] = None
    preferences: Dict[str, Any] = Field(default_factory=dict)
    budget_min: Optional[float] = Field(None, ge=0)
    budget_max: Optional[float] = Field(None, ge=0)
    preferred_locations: List[str] = Field(default_factory=list)
    property_type_interest: List[str] = Field(default_factory=list)


class LeadCreate(LeadBase):
    """Schema for creating a lead"""
    whatsapp_id: Optional[str] = Field(None, max_length=255)
    source: str = Field(..., max_length=100)
    source_details: Dict[str, Any] = Field(default_factory=dict)


class LeadUpdate(BaseSchema):
    """Schema for updating a lead"""
    name: Optional[str] = Field(None, max_length=255)
    email: Optional[EmailStr] = None
    preferences: Optional[Dict[str, Any]] = None
    status: Optional[LeadStatus] = None
    score: Optional[int] = Field(None, ge=0, le=100)
    qualification_notes: Optional[str] = None


class LeadResponse(LeadBase, TimestampedSchema):
    """Schema for lead response"""
    id: UUID
    tenant_id: UUID
    whatsapp_id: Optional[str]
    score: int
    score_factors: Dict[str, Any]
    status: LeadStatus
    qualification_notes: Optional[str]
    source: str
    source_details: Dict[str, Any]
    last_contact_at: Optional[datetime]
    converted_at: Optional[datetime]


# Conversation schemas
class ConversationBase(BaseSchema):
    """Base conversation schema"""
    context: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(ConversationBase):
    """Schema for creating a conversation"""
    lead_id: Optional[UUID] = None
    evo_chat_id: Optional[str] = Field(None, max_length=255)
    chatwoot_conversation_id: Optional[int] = None


class ConversationUpdate(BaseSchema):
    """Schema for updating a conversation"""
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[ConversationStatus] = None
    handoff_requested: Optional[bool] = None
    handoff_reason: Optional[str] = Field(None, max_length=500)


class ConversationResponse(ConversationBase, BaseSchema):
    """Schema for conversation response"""
    id: UUID
    tenant_id: UUID
    lead_id: Optional[UUID]
    evo_chat_id: Optional[str]
    chatwoot_conversation_id: Optional[int]
    ai_state: Dict[str, Any]
    handoff_requested: bool
    handoff_reason: Optional[str]
    status: ConversationStatus
    started_at: datetime
    ended_at: Optional[datetime]
    last_message_at: Optional[datetime]


# Message schemas
class MessageBase(BaseSchema):
    """Base message schema"""
    content: str
    message_type: str = Field(default="text", max_length=50)
    media_url: Optional[str] = Field(None, max_length=500)
    sender_type: str = Field(..., max_length=50)
    sender_id: str = Field(..., max_length=255)
    sender_name: Optional[str] = Field(None, max_length=255)


class MessageCreate(MessageBase):
    """Schema for creating a message"""
    conversation_id: UUID


class MessageResponse(MessageBase, BaseSchema):
    """Schema for message response"""
    id: UUID
    conversation_id: UUID
    ai_processed: bool
    ai_response: Optional[str]
    ai_confidence: Optional[float]
    intent: Optional[str]
    entities: Dict[str, Any]
    is_read: bool
    is_delivered: bool
    created_at: datetime
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]


# Appointment schemas
class AppointmentBase(BaseSchema):
    """Base appointment schema"""
    scheduled_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    notes: Optional[str] = None
    location_details: Optional[str] = Field(None, max_length=500)


class AppointmentCreate(AppointmentBase):
    """Schema for creating an appointment"""
    lead_id: UUID
    property_id: UUID


class AppointmentUpdate(BaseSchema):
    """Schema for updating an appointment"""
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    notes: Optional[str] = None
    location_details: Optional[str] = Field(None, max_length=500)
    status: Optional[AppointmentStatus] = None
    cancellation_reason: Optional[str] = Field(None, max_length=500)


class AppointmentResponse(AppointmentBase, TimestampedSchema):
    """Schema for appointment response"""
    id: UUID
    tenant_id: UUID
    lead_id: UUID
    property_id: UUID
    google_event_id: Optional[str]
    calendar_link: Optional[str]
    status: AppointmentStatus
    cancellation_reason: Optional[str]
    reminder_sent: bool
    reminder_sent_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    completed_at: Optional[datetime]


# Webhook schemas
class WebhookPayload(BaseSchema):
    """Schema for webhook payload"""
    source: str = Field(..., max_length=100)
    event_type: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EvoWebhookPayload(WebhookPayload):
    """Schema for EVO API webhook payload"""
    instance_id: str
    message_id: Optional[str] = None
    chat_id: str

    @validator("source", pre=True, always=True)
    def set_source(cls, v):
        return "evo"


class ChatwootWebhookPayload(WebhookPayload):
    """Schema for Chatwoot webhook payload"""
    account_id: int
    conversation_id: int
    inbox_id: int

    @validator("source", pre=True, always=True)
    def set_source(cls, v):
        return "chatwoot"


# Response schemas
class HealthCheckResponse(BaseSchema):
    """Schema for health check response"""
    status: str
    services: Dict[str, str]


class PaginatedResponse(BaseSchema):
    """Schema for paginated response"""
    items: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool


class ErrorResponse(BaseSchema):
    """Schema for error response"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SuccessResponse(BaseSchema):
    """Schema for success response"""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None
