"""
Database models for Corretor AI Hub
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, JSON, Text,
    ForeignKey, Float, Enum as SQLEnum, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class TenantStatus(str, Enum):
    """Tenant status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class ConversationStatus(str, Enum):
    """Conversation status enum"""
    ACTIVE = "active"
    ENDED = "ended"
    HANDED_OFF = "handed_off"
    TIMEOUT = "timeout"


class PropertyStatus(str, Enum):
    """Property status enum"""
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    RENTED = "rented"
    INACTIVE = "inactive"


class AppointmentStatus(str, Enum):
    """Appointment status enum"""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class LeadStatus(str, Enum):
    """Lead status enum"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    NURTURING = "nurturing"
    CONVERTED = "converted"
    LOST = "lost"


class Tenant(Base):
    """
    Tenant model - represents a real estate agent/broker
    """
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(50), nullable=False)
    company_name = Column(String(255))

    # Integrations
    evo_instance_key = Column(String(255), unique=True)
    chatwoot_inbox_id = Column(Integer)
    google_calendar_id = Column(String(255))
    qdrant_namespace = Column(String(255), unique=True)

    # Settings
    settings = Column(JSON, default={})
    features = Column(JSON, default={})
    automation_config = Column(JSON, default={
        "require_new_contact": True,
        "require_portal_link": False,
        "new_contact_hours": 24,
        "allowed_portals": ["zonaprop", "argenprop", "mercadolibre", "properati", "remax"]
    })

    # Status
    status = Column(SQLEnum(TenantStatus), default=TenantStatus.TRIAL)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = Column(DateTime)
    suspended_at = Column(DateTime)

    # Relationships
    properties = relationship("Property", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="tenant", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="tenant", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_tenant_email", "email"),
        Index("idx_tenant_status", "status"),
    )


class Property(Base):
    """
    Property model - represents real estate properties
    """
    __tablename__ = "properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # Basic Info
    title = Column(String(500), nullable=False)
    description = Column(Text)
    property_type = Column(String(100))  # apartment, house, commercial, land
    transaction_type = Column(String(50))  # sale, rent

    # Location
    address = Column(String(500))
    neighborhood = Column(String(255))
    city = Column(String(255), nullable=False)
    state = Column(String(100))
    zip_code = Column(String(20))
    latitude = Column(Float)
    longitude = Column(Float)

    # Characteristics
    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    parking_spaces = Column(Integer)
    total_area = Column(Float)  # m²
    built_area = Column(Float)  # m²
    floor = Column(Integer)
    total_floors = Column(Integer)

    # Financial
    price = Column(Float, nullable=False)
    condo_fee = Column(Float)
    property_tax = Column(Float)

    # Features
    features = Column(JSON, default=[])  # pool, gym, balcony, etc.
    amenities = Column(JSON, default=[])

    # Media
    images = Column(JSON, default=[])
    video_url = Column(String(500))
    virtual_tour_url = Column(String(500))

    # Source
    source_url = Column(String(500))
    source_id = Column(String(255))
    scraped_at = Column(DateTime)

    # Status
    status = Column(SQLEnum(PropertyStatus), default=PropertyStatus.AVAILABLE)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="properties")
    appointments = relationship("Appointment", back_populates="property")

    # Indexes
    __table_args__ = (
        Index("idx_property_tenant", "tenant_id"),
        Index("idx_property_city", "city"),
        Index("idx_property_status", "status"),
        Index("idx_property_price", "price"),
        Index("idx_property_bedrooms", "bedrooms"),
        UniqueConstraint("tenant_id", "source_id", name="uq_tenant_source"),
    )


class Lead(Base):
    """
    Lead model - represents potential customers
    """
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)

    # Contact Info
    name = Column(String(255))
    phone = Column(String(50), nullable=False)
    email = Column(String(255))
    whatsapp_id = Column(String(255))

    # Preferences
    preferences = Column(JSON, default={})
    budget_min = Column(Float)
    budget_max = Column(Float)
    preferred_locations = Column(JSON, default=[])
    property_type_interest = Column(JSON, default=[])

    # Scoring
    score = Column(Integer, default=0)
    score_factors = Column(JSON, default={})

    # Status
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.NEW)
    qualification_notes = Column(Text)

    # Source
    source = Column(String(100))  # whatsapp, website, manual
    source_details = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact_at = Column(DateTime)
    converted_at = Column(DateTime)

    # Relationships
    tenant = relationship("Tenant", back_populates="leads")
    conversations = relationship("Conversation", back_populates="lead")
    appointments = relationship("Appointment", back_populates="lead")

    # Indexes
    __table_args__ = (
        Index("idx_lead_tenant", "tenant_id"),
        Index("idx_lead_phone", "phone"),
        Index("idx_lead_status", "status"),
        Index("idx_lead_score", "score"),
    )


class Conversation(Base):
    """
    Conversation model - represents chat conversations
    """
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"))

    # External IDs
    evo_chat_id = Column(String(255))
    chatwoot_conversation_id = Column(Integer)

    # Context
    context = Column(JSON, default={})
    metadata = Column(JSON, default={})

    # AI State
    ai_state = Column(JSON, default={})
    handoff_requested = Column(Boolean, default=False)
    handoff_reason = Column(String(500))

    # Status
    status = Column(SQLEnum(ConversationStatus), default=ConversationStatus.ACTIVE)

    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    last_message_at = Column(DateTime)

    # Relationships
    tenant = relationship("Tenant", back_populates="conversations")
    lead = relationship("Lead", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("idx_conversation_tenant", "tenant_id"),
        Index("idx_conversation_lead", "lead_id"),
        Index("idx_conversation_status", "status"),
        Index("idx_conversation_evo_chat", "evo_chat_id"),
    )


class Message(Base):
    """
    Message model - represents individual messages in conversations
    """
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)

    # Message Content
    content = Column(Text, nullable=False)
    message_type = Column(String(50))  # text, image, audio, video, document
    media_url = Column(String(500))

    # Sender
    sender_type = Column(String(50))  # customer, agent, bot
    sender_id = Column(String(255))
    sender_name = Column(String(255))

    # AI Processing
    ai_processed = Column(Boolean, default=False)
    ai_response = Column(Text)
    ai_confidence = Column(Float)
    intent = Column(String(100))
    entities = Column(JSON, default={})

    # Status
    is_read = Column(Boolean, default=False)
    is_delivered = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")

    # Indexes
    __table_args__ = (
        Index("idx_message_conversation", "conversation_id"),
        Index("idx_message_created", "created_at"),
        Index("idx_message_sender", "sender_type", "sender_id"),
    )


class Appointment(Base):
    """
    Appointment model - represents property viewing appointments
    """
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)

    # Schedule
    scheduled_date = Column(DateTime, nullable=False)  # Renamed from scheduled_at
    duration_minutes = Column(Integer, default=60)

    # Google Calendar
    google_event_id = Column(String(255))
    calendar_link = Column(String(500))

    # Details
    notes = Column(Text)
    location_details = Column(String(500))

    # Status
    status = Column(SQLEnum(AppointmentStatus), default=AppointmentStatus.SCHEDULED)
    cancellation_reason = Column(String(500))

    # Reminders
    reminder_24h_sent = Column(Boolean, default=False)
    reminder_24h_sent_at = Column(DateTime)
    reminder_3h_sent = Column(Boolean, default=False)
    reminder_3h_sent_at = Column(DateTime)
    reminder_confirmations = Column(JSON, default={})

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    confirmed_at = Column(DateTime)
    completed_at = Column(DateTime)
    cancelled_at = Column(DateTime)

    # Relationships
    tenant = relationship("Tenant", back_populates="appointments")
    lead = relationship("Lead", back_populates="appointments")
    property = relationship("Property", back_populates="appointments")

    # Indexes
    __table_args__ = (
        Index("idx_appointment_tenant", "tenant_id"),
        Index("idx_appointment_lead", "lead_id"),
        Index("idx_appointment_property", "property_id"),
        Index("idx_appointment_scheduled", "scheduled_at"),
        Index("idx_appointment_status", "status"),
    )


class WebhookLog(Base):
    """
    Webhook log model - for debugging and monitoring
    """
    __tablename__ = "webhook_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Request Info
    source = Column(String(100))  # evo, chatwoot
    endpoint = Column(String(255))
    method = Column(String(10))
    headers = Column(JSON)
    body = Column(JSON)

    # Response
    status_code = Column(Integer)
    response_body = Column(JSON)
    error_message = Column(Text)

    # Processing
    processed = Column(Boolean, default=False)
    processing_time_ms = Column(Integer)

    # Timestamps
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    # Indexes
    __table_args__ = (
        Index("idx_webhook_source", "source"),
        Index("idx_webhook_received", "received_at"),
        Index("idx_webhook_processed", "processed"),
    )
