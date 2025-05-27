# Corretor AI Hub

🏠 **Multi-tenant conversational AI platform for real estate agents**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) | [Español](README.es.md) | [Português](README.pt.md)

## 📋 Overview

**Corretor AI Hub** is a comprehensive intelligent automation platform for REMAX Argentina real estate agents. The system integrates WhatsApp Business via EVO API with a conversational AI assistant, offering 24/7 automated service, intelligent property search, appointment scheduling, and qualified lead management.

### 🎯 Key Benefits

- **24/7 Service**: Instantly responds to inquiries, even outside business hours
- **Automatic Qualification**: Identifies and qualifies leads based on their preferences
- **Smart Scheduling**: Books appointments directly in the agent's Google Calendar
- **Multi-language**: Native support for Spanish, Portuguese, and English
- **Real-time Analytics**: Dashboard with conversion metrics and engagement insights

## 🚀 Features

### ✅ Implemented

- **🤖 Conversational AI Assistant**
  - Humanized responses with GPT-4
  - Multiple question consolidation
  - Intent detection for human handoff
  
- **📱 WhatsApp Business Integration**
  - Message receiving and sending
  - Support for text, audio, and images
  - Dedicated second line per agent

- **🏢 Multi-Tenant System**
  - Complete isolation between agents
  - Customized settings per tenant
  - Segregated database

- **📅 Appointment Management**
  - Google Calendar integration
  - Offers 2 time slot options
  - Automatic reminders (24h and 3h before)

- **👥 Lead Management**
  - Automatic data capture
  - Qualification scoring
  - Interaction history

- **🏷️ Automatic Classification**
  - Chatwoot tags by status
  - Service prioritization
  - Conversion metrics

### 🚧 In Development

- **🔍 REMAX Argentina Scraping** - Automatic property search on official website
- **🎯 Smart Matching** - Correlation between new properties and old leads
- **📸 Multimedia Processing** - Image analysis and audio transcription
- **🔔 Proactive Notifications** - Opportunity alerts for agents

## 🏗️ Architecture

### System Overview

```mermaid
graph TB
    subgraph "Client Layer"
        WA[WhatsApp Business]
        CW[Chatwoot Hub]
    end
    
    subgraph "Backend"
        API[FastAPI]
        AI[AI Agent<br/>LangChain]
        SCRAPER[REMAX Scraper]
    end
    
    subgraph "Data"
        PG[(PostgreSQL)]
        QDRANT[(Vector DB)]
        REDIS[(Cache)]
    end
    
    WA --> API
    CW --> API
    API --> AI
    API --> SCRAPER
    AI --> QDRANT
    SCRAPER --> REDIS
    API --> PG
```

### Conversation Flow

1. **Client** sends message via WhatsApp
2. **EVO API** receives and sends webhook
3. **AI Agent** processes and identifies intent
4. **Actions** executed as needed:
   - Property search (scraping)
   - Appointment scheduling
   - Lead qualification
5. **Response** sent to client
6. **Chatwoot** updated with status

For detailed diagrams, see [architecture.mmd](architecture.mmd).

## 🛠️ Tech Stack

### Backend
- **Python 3.11+** - Main language
- **FastAPI** - Async web framework
- **SQLAlchemy** - ORM with async support
- **Pydantic** - Data validation

### AI & Machine Learning
- **LangChain** - AI agents framework
- **OpenAI GPT-4** - Language model
- **Qdrant** - Vector database for context
- **Whisper API** - Audio transcription

### Infrastructure
- **PostgreSQL** - Main database (via Supabase)
- **Redis** - Cache and queues
- **Docker** - Containerization
- **EVO API** - WhatsApp integration
- **Chatwoot** - Support platform

## 📋 Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose
- Supabase account
- Configured EVO API instance
- OpenAI API key
- Google Cloud project with Calendar API
- Chatwoot instance (optional)

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/corretor-ai-hub.git
cd corretor-ai-hub
```

### 2. Set up environment variables
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Start services
```bash
docker-compose up -d
```

### 4. Install dependencies
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Run migrations
```bash
alembic upgrade head
```

### 6. Start the server
```bash
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## ⚙️ Configuration

### Essential Environment Variables

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...

# EVO API (WhatsApp)
EVO_API_URL=https://your-evo-instance.com
EVO_API_KEY=your-key

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS=base64-encoded-json

# Chatwoot
CHATWOOT_URL=https://your-chatwoot.com
CHATWOOT_API_KEY=your-key

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your-key
```

## 📚 API Documentation

Once running, access:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Main Endpoints

| Method | Endpoint               | Description      |
|--------|------------------------|------------------|
| POST   | `/webhooks/evo`        | EVO API webhook  |
| POST   | `/webhooks/chatwoot`   | Chatwoot webhook |
| GET    | `/properties`          | List properties  |
| POST   | `/properties/search`   | Semantic search  |
| POST   | `/appointments`        | Schedule visits  |
| GET    | `/leads`               | List leads       |
| GET    | `/analytics/dashboard` | Metrics          |

## 🧪 Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific tests
pytest tests/test_property_agent.py -v
```

## 📁 Project Structure

```
corretor-ai-hub/
├── src/
│   ├── agents/          # AI Agent logic
│   ├── api/             # FastAPI endpoints
│   │   └── routes/      # Organized routes
│   ├── core/            # Config and utils
│   ├── database/        # Models and schemas
│   ├── integrations/    # External services
│   ├── scrapers/        # Web scraping
│   └── services/        # Business logic
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── docs/                # Documentation
└── docker-compose.yml   # Orchestration
```

## 🔒 Security

- JWT authentication for APIs
- Webhook validation
- Rate limiting per tenant
- Encrypted data at rest
- Logs without sensitive information

## 📈 Monitoring

- Health checks at `/health`
- Prometheus metrics at `/metrics`
- Structured logs with correlation ID
- Alerts for critical failures

## 🤝 Contributing

1. Fork the project
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [LangChain](https://langchain.com/) - AI framework
- [EVO API](https://github.com/EvolutionAPI/evolution-api) - WhatsApp Business
- [Chatwoot](https://www.chatwoot.com/) - Support platform
- [Supabase](https://supabase.com/) - Backend as a Service

---

Built with ❤️ to revolutionize the real estate market