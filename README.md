# Real Estate AI Hub

A multi-tenant conversational AI platform for real estate agents, integrating WhatsApp Business through EVO API with intelligent property matching, appointment scheduling, and lead management.

## 🚀 Features

- **AI-Powered Conversations**: Natural language processing for property inquiries in Portuguese
- **Multi-Tenant Architecture**: Isolated environments for each real estate agent
- **WhatsApp Business Integration**: Seamless messaging through EVO API
- **Smart Property Matching**: Vector-based semantic search for property recommendations
- **Appointment Scheduling**: Google Calendar integration with automated reminders
- **Lead Management**: Automatic lead scoring and qualification
- **Customer Support Platform**: Chatwoot integration for human handoff
- **Analytics Dashboard**: Real-time metrics and conversation insights

## 🏗️ Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   WhatsApp      │────▶│   EVO API    │────▶│   FastAPI       │
│   Business      │     │   Webhook    │     │   Backend       │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                       │
                               ┌───────────────────────┴───────────────────────┐
                               │                                               │
                        ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────┐ │
                        │  AI Agent   │  │   Qdrant    │  │    Supabase     │ │
                        │ (LangChain) │  │  Vector DB  │  │   PostgreSQL    │ │
                        └─────────────┘  └─────────────┘  └─────────────────┘ │
                               │                                               │
                        ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────┐ │
                        │  Chatwoot   │  │   Google    │  │     Redis       │ │
                        │   Support   │  │  Calendar   │  │     Cache       │ │
                        └─────────────┘  └─────────────┘  └─────────────────┘ │
```

## 🛠️ Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Pydantic
- **AI/ML**: LangChain, OpenAI GPT-4, Qdrant Vector Database
- **Databases**: PostgreSQL (Supabase), Redis
- **Messaging**: EVO API (WhatsApp Business), Chatwoot
- **Infrastructure**: Docker, Docker Compose
- **Testing**: Pytest, Coverage

## 📋 Prerequisites

- Python 3.11+
- Docker and Docker Compose
- EVO API instance
- Supabase account
- OpenAI API key
- Google Cloud project with Calendar API enabled
- Chatwoot instance (optional)

## 🚀 Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/corretor-ai-hub.git
   cd corretor-ai-hub
   ```

2. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Start infrastructure services**
   ```bash
   docker-compose up -d
   ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

6. **Start the development server**
   ```bash
   python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

## 🔧 Configuration

Key environment variables:

```bash
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname

# AI Services
OPENAI_API_KEY=your-openai-key
QDRANT_URL=http://localhost:6333

# WhatsApp Integration
EVO_API_URL=https://your-evo-instance.com
EVO_API_KEY=your-evo-api-key

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS=base64-encoded-json

# Chatwoot
CHATWOOT_URL=https://your-chatwoot.com
CHATWOOT_API_KEY=your-chatwoot-key
```

## 📚 API Documentation

Once running, access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Key Endpoints

- `POST /webhooks/evo` - EVO API webhook for WhatsApp messages
- `POST /webhooks/chatwoot` - Chatwoot webhook for support tickets
- `GET /properties` - List properties with filters
- `POST /properties/search` - Semantic property search
- `POST /appointments` - Schedule property viewings
- `GET /analytics/dashboard` - Real-time metrics

## 🧪 Testing

Run the test suite:
```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Specific module
pytest tests/test_property_agent.py -v
```

## 📦 Project Structure

```
corretor-ai-hub/
├── src/
│   ├── agents/          # AI agent logic
│   ├── api/             # FastAPI application
│   ├── core/            # Core utilities
│   ├── database/        # Database models
│   ├── integrations/    # External services
│   ├── scrapers/        # Property scrapers
│   └── services/        # Business logic
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── config/              # Configuration files
└── docs/                # Documentation
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [LangChain](https://langchain.com/) for the AI framework
- [EVO API](https://github.com/EvolutionAPI/evolution-api) for WhatsApp integration
- [Chatwoot](https://www.chatwoot.com/) for customer support
- [Supabase](https://supabase.com/) for backend infrastructure