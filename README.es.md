# Hub de IA Inmobiliaria

Una plataforma de IA conversacional multi-inquilino para agentes inmobiliarios, integrando WhatsApp Business a través de EVO API con coincidencia inteligente de propiedades, programación de citas y gestión de leads.

## 🚀 Características

- **Conversaciones Impulsadas por IA**: Procesamiento de lenguaje natural para consultas de propiedades en portugués
- **Arquitectura Multi-Inquilino**: Entornos aislados para cada agente inmobiliario
- **Integración con WhatsApp Business**: Mensajería perfecta a través de EVO API
- **Coincidencia Inteligente de Propiedades**: Búsqueda semántica basada en vectores para recomendaciones de propiedades
- **Programación de Citas**: Integración con Google Calendar con recordatorios automatizados
- **Gestión de Leads**: Puntuación y calificación automática de leads
- **Plataforma de Soporte al Cliente**: Integración con Chatwoot para transferencia a humanos
- **Dashboard de Analytics**: Métricas en tiempo real e insights de conversaciones

## 🏗️ Arquitectura

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   WhatsApp      │────▶│   EVO API    │────▶│   FastAPI       │
│   Business      │     │   Webhook    │     │   Backend       │
└─────────────────┘     └──────────────┘     └────────┬────────┘
                                                       │
                               ┌───────────────────────┴───────────────────────┐
                               │                                               │
                        ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────┐ │
                        │  Agente IA  │  │   Qdrant    │  │    Supabase     │ │
                        │ (LangChain) │  │  Vector DB  │  │   PostgreSQL    │ │
                        └─────────────┘  └─────────────┘  └─────────────────┘ │
                               │                                               │
                        ┌──────▼──────┐  ┌─────────────┐  ┌─────────────────┐ │
                        │  Chatwoot   │  │   Google    │  │     Redis       │ │
                        │   Soporte   │  │  Calendar   │  │     Cache       │ │
                        └─────────────┘  └─────────────┘  └─────────────────┘ │
```

## 🛠️ Stack Tecnológico

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Pydantic
- **IA/ML**: LangChain, OpenAI GPT-4, Qdrant Vector Database
- **Bases de Datos**: PostgreSQL (Supabase), Redis
- **Mensajería**: EVO API (WhatsApp Business), Chatwoot
- **Infraestructura**: Docker, Docker Compose
- **Pruebas**: Pytest, Coverage

## 📋 Prerrequisitos

- Python 3.11+
- Docker y Docker Compose
- Instancia de EVO API
- Cuenta de Supabase
- Clave de API de OpenAI
- Proyecto de Google Cloud con Calendar API habilitada
- Instancia de Chatwoot (opcional)

## 🚀 Inicio Rápido

1. **Clonar el repositorio**
   ```bash
   git clone https://github.com/tuusuario/corretor-ai-hub.git
   cd corretor-ai-hub
   ```

2. **Configurar variables de entorno**
   ```bash
   cp .env.example .env
   # Edite .env con sus credenciales
   ```

3. **Iniciar servicios de infraestructura**
   ```bash
   docker-compose up -d
   ```

4. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

5. **Ejecutar migraciones de base de datos**
   ```bash
   alembic upgrade head
   ```

6. **Iniciar el servidor de desarrollo**
   ```bash
   python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

## 🔧 Configuración

Variables de entorno clave:

```bash
# Configuración de API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Base de Datos
DATABASE_URL=postgresql+asyncpg://usuario:contraseña@localhost/nombrebd

# Servicios de IA
OPENAI_API_KEY=tu-clave-openai
QDRANT_URL=http://localhost:6333

# Integración WhatsApp
EVO_API_URL=https://tu-instancia-evo.com
EVO_API_KEY=tu-clave-evo-api

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS=json-codificado-base64

# Chatwoot
CHATWOOT_URL=https://tu-chatwoot.com
CHATWOOT_API_KEY=tu-clave-chatwoot
```

## 📚 Documentación de la API

Una vez en ejecución, acceda a la documentación interactiva de la API en:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Endpoints Principales

- `POST /webhooks/evo` - Webhook de EVO API para mensajes de WhatsApp
- `POST /webhooks/chatwoot` - Webhook de Chatwoot para tickets de soporte
- `GET /properties` - Listar propiedades con filtros
- `POST /properties/search` - Búsqueda semántica de propiedades
- `POST /appointments` - Programar visitas a propiedades
- `GET /analytics/dashboard` - Métricas en tiempo real

## 🧪 Pruebas

Ejecutar el conjunto de pruebas:
```bash
# Todas las pruebas
pytest

# Con cobertura
pytest --cov=src --cov-report=html

# Módulo específico
pytest tests/test_property_agent.py -v
```

## 📦 Estructura del Proyecto

```
corretor-ai-hub/
├── src/
│   ├── agents/          # Lógica del agente IA
│   ├── api/             # Aplicación FastAPI
│   ├── core/            # Utilidades principales
│   ├── database/        # Modelos de base de datos
│   ├── integrations/    # Servicios externos
│   ├── scrapers/        # Scrapers de propiedades
│   └── services/        # Lógica de negocio
├── tests/               # Conjunto de pruebas
├── scripts/             # Scripts de utilidad
├── config/              # Archivos de configuración
└── docs/                # Documentación
```

## 🤝 Contribuyendo

1. Haz un fork del repositorio
2. Crea una rama de características (`git checkout -b feature/caracteristica-increible`)
3. Confirma tus cambios (`git commit -m 'Agregar característica increíble'`)
4. Empuja a la rama (`git push origin feature/caracteristica-increible`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está licenciado bajo la Licencia MIT - vea el archivo [LICENSE](LICENSE) para más detalles.

## 🙏 Agradecimientos

- [LangChain](https://langchain.com/) por el framework de IA
- [EVO API](https://github.com/EvolutionAPI/evolution-api) por la integración de WhatsApp
- [Chatwoot](https://www.chatwoot.com/) por el soporte al cliente
- [Supabase](https://supabase.com/) por la infraestructura backend