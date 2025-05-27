# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development Server
```bash
# Start the FastAPI development server
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

# With custom environment
ENVIRONMENT=development python -m uvicorn src.api.main:app --reload
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_property_agent.py

# Run tests with output
pytest -v -s
```

### Code Quality
```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```

### Docker Services
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Reset databases (WARNING: deletes data)
docker-compose down -v
```

### Database Migrations
```bash
# Initialize Alembic (if needed)
alembic init alembic

# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Architecture Overview

### Multi-Tenant System
Each corretor (real estate agent) has isolated:
- WhatsApp instance via EVO API
- Chatwoot inbox with dedicated agent
- Qdrant namespace for vector search
- Database records filtered by tenant_id
- Google Calendar integration

### Core Components

**API Layer (`src/api/`)**
- FastAPI application with async request handling
- Webhook endpoints for EVO API and Chatwoot
- RESTful endpoints for properties, leads, appointments
- Health checks for all critical services

**AI Agent (`src/agents/property_agent.py`)**
- LangChain-based conversational agent
- Tools: property search, appointment scheduling, lead capture
- Vector memory with Qdrant for context
- Automatic handoff detection to human agents
- Multi-language support (Portuguese primary)

**Integrations (`src/integrations/`)**
- **EVO API**: WhatsApp Business messaging
- **Chatwoot**: Customer support platform
- **Google Calendar**: Appointment scheduling
- **Supabase**: Primary database and auth
- **Qdrant**: Vector search for AI context

**Database Models (`src/database/models.py`)**
- Tenant-based isolation pattern
- UUID primary keys throughout
- Comprehensive indexes for performance
- JSON fields for flexible metadata

### Request Flow
1. WhatsApp message → EVO API webhook
2. Webhook handler validates and processes
3. AI agent generates response using:
   - Property database search
   - Conversation history from vector DB
   - Business rules from config
4. Response sent via EVO API
5. Conversation synced to Chatwoot

### Key Patterns

**Async Everywhere**
- All database operations use async SQLAlchemy
- HTTP calls use httpx with connection pooling
- Background tasks for heavy operations

**Error Handling**
- Custom exceptions in `src/core/exceptions.py`
- Structured logging with request correlation
- Graceful degradation for external services

**Configuration**
- Environment-based settings via Pydantic
- Feature flags for gradual rollout
- Per-tenant customization support

### Testing Strategy
- Unit tests for business logic
- Integration tests for API endpoints
- Mock external services (EVO, Chatwoot, etc.)
- Use faker for test data generation

### Performance Considerations
- Redis caching for frequent queries
- Vector search limited to relevant namespace
- Database query optimization with proper indexes
- Connection pooling for all external services

### Security
- JWT authentication for API access
- Webhook signature validation
- Environment-specific security settings
- No credentials in code (use .env)