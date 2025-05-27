# Corretor AI Hub

🏠 **Plataforma de IA conversacional multi-tenant para agentes inmobiliarios**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) | [Español](README.es.md) | [Português](README.pt.md)

## 📋 Visión General

**Corretor AI Hub** es una plataforma completa de automatización inteligente para agentes inmobiliarios de REMAX Argentina. El sistema integra WhatsApp Business vía EVO API con un asistente de IA conversacional, ofreciendo atención automatizada 24/7, búsqueda inteligente de propiedades, programación de visitas y gestión calificada de leads.

### 🎯 Principales Beneficios

- **Atención 24/7**: Responde consultas instantáneamente, incluso fuera del horario comercial
- **Calificación Automática**: Identifica y califica leads según sus preferencias
- **Programación Inteligente**: Agenda visitas directamente en Google Calendar del agente
- **Multi-idiomas**: Soporte nativo para Español, Portugués e Inglés
- **Análisis en Tiempo Real**: Dashboard con métricas de conversión y engagement

## 🚀 Funcionalidades

### ✅ Implementadas

- **🤖 Asistente IA Conversacional**
  - Respuestas humanizadas con GPT-4
  - Consolidación de múltiples preguntas
  - Detección de intención para handoff humano
  
- **📱 Integración WhatsApp Business**
  - Recepción y envío de mensajes
  - Soporte para texto, audio e imágenes
  - Segunda línea dedicada por agente

- **🏢 Sistema Multi-Tenant**
  - Aislamiento completo entre agentes
  - Configuraciones personalizadas por tenant
  - Base de datos segregada

- **📅 Gestión de Citas**
  - Integración con Google Calendar
  - Ofrece 2 opciones de horarios
  - Recordatorios automáticos (24h y 3h antes)

- **👥 Gestión de Leads**
  - Captura automática de datos
  - Score de calificación
  - Historial de interacciones

- **🏷️ Clasificación Automática**
  - Etiquetas en Chatwoot por estado
  - Priorización de atención
  - Métricas de conversión

### 🚧 En Desarrollo

- **🔍 Scraping REMAX Argentina** - Búsqueda automática de propiedades en el sitio oficial
- **🎯 Matching Inteligente** - Correlación entre nuevas propiedades y leads antiguos
- **📸 Procesamiento Multimedia** - Análisis de imágenes y transcripción de audios
- **🔔 Notificaciones Proactivas** - Alertas sobre oportunidades para el agente

## 🏗️ Arquitectura

### Visión General del Sistema

```mermaid
graph TB
    subgraph "Capa Cliente"
        WA[WhatsApp Business]
        CW[Chatwoot Hub]
    end
    
    subgraph "Backend"
        API[FastAPI]
        AI[AI Agent<br/>LangChain]
        SCRAPER[REMAX Scraper]
    end
    
    subgraph "Datos"
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

### Flujo de Conversación

1. **Cliente** envía mensaje vía WhatsApp
2. **EVO API** recibe y envía webhook
3. **AI Agent** procesa e identifica intención
4. **Acciones** ejecutadas según necesidad:
   - Búsqueda de propiedades (scraping)
   - Programación de visitas
   - Calificación de lead
5. **Respuesta** enviada al cliente
6. **Chatwoot** actualizado con estado

Para diagramas detallados, ver [architecture.mmd](architecture.mmd).

## 🛠️ Stack Tecnológico

### Backend
- **Python 3.11+** - Lenguaje principal
- **FastAPI** - Framework web asíncrono
- **SQLAlchemy** - ORM con soporte async
- **Pydantic** - Validación de datos

### IA & Machine Learning
- **LangChain** - Framework para AI agents
- **OpenAI GPT-4** - Modelo de lenguaje
- **Qdrant** - Vector database para contexto
- **Whisper API** - Transcripción de audio

### Infraestructura
- **PostgreSQL** - Base de datos principal (vía Supabase)
- **Redis** - Cache y colas
- **Docker** - Containerización
- **EVO API** - Integración WhatsApp
- **Chatwoot** - Plataforma de soporte

## 📋 Prerequisitos

- Python 3.11 o superior
- Docker y Docker Compose
- Cuenta Supabase
- Instancia EVO API configurada
- Clave API OpenAI
- Proyecto Google Cloud con Calendar API
- Instancia Chatwoot (opcional)

## 🚀 Instalación Rápida

### 1. Clonar el repositorio
```bash
git clone https://github.com/yourusername/corretor-ai-hub.git
cd corretor-ai-hub
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
# Editar .env con sus credenciales
```

### 3. Iniciar servicios
```bash
docker-compose up -d
```

### 4. Instalar dependencias
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Ejecutar migraciones
```bash
alembic upgrade head
```

### 6. Iniciar el servidor
```bash
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## ⚙️ Configuración

### Variables de Entorno Esenciales

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Base de Datos
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

## 📚 Documentación de la API

Con el servidor ejecutándose, acceder a:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Principales Endpoints

| Método | Endpoint               | Descripción        |
|--------|------------------------|--------------------|
| POST   | `/webhooks/evo`        | Webhook EVO API    |
| POST   | `/webhooks/chatwoot`   | Webhook Chatwoot   |
| GET    | `/properties`          | Lista propiedades  |
| POST   | `/properties/search`   | Búsqueda semántica |
| POST   | `/appointments`        | Agenda visitas     |
| GET    | `/leads`               | Lista leads        |
| GET    | `/analytics/dashboard` | Métricas           |

## 🧪 Tests

```bash
# Ejecutar todos los tests
pytest

# Con cobertura
pytest --cov=src --cov-report=html

# Tests específicos
pytest tests/test_property_agent.py -v
```

## 📁 Estructura del Proyecto

```
corretor-ai-hub/
├── src/
│   ├── agents/          # Lógica del AI Agent
│   ├── api/             # Endpoints FastAPI
│   │   └── routes/      # Rutas organizadas
│   ├── core/            # Configuraciones y utils
│   ├── database/        # Modelos y schemas
│   ├── integrations/    # Servicios externos
│   ├── scrapers/        # Web scraping
│   └── services/        # Lógica de negocio
├── tests/               # Suite de tests
├── scripts/             # Scripts útiles
├── docs/                # Documentación
└── docker-compose.yml   # Orquestación
```

## 🔒 Seguridad

- Autenticación JWT para APIs
- Validación de webhooks
- Rate limiting por tenant
- Datos encriptados en reposo
- Logs sin información sensible

## 📈 Monitoreo

- Health checks en `/health`
- Métricas Prometheus en `/metrics`
- Logs estructurados con correlation ID
- Alertas para fallas críticas

## 🤝 Contribuyendo

1. Fork el proyecto
2. Crear una branch (`git checkout -b feature/AmazingFeature`)
3. Commit sus cambios (`git commit -m 'Add AmazingFeature'`)
4. Push a la branch (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## 📄 Licencia

Este proyecto está licenciado bajo MIT License - ver [LICENSE](LICENSE) para detalles.

## 🙏 Agradecimientos

- [LangChain](https://langchain.com/) - Framework de IA
- [EVO API](https://github.com/EvolutionAPI/evolution-api) - WhatsApp Business
- [Chatwoot](https://www.chatwoot.com/) - Plataforma de soporte
- [Supabase](https://supabase.com/) - Backend as a Service

---

Desarrollado con ❤️ para revolucionar el mercado inmobiliario