# Corretor AI Hub

🏠 **Plataforma de IA conversacional multi-tenant para corretores imobiliários**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) | [Español](README.es.md) | [Português](README.pt.md)

## 📋 Visão Geral

O **Corretor AI Hub** é uma plataforma completa de automação inteligente para corretores imobiliários da REMAX Argentina. O sistema integra WhatsApp Business via EVO API com um assistente de IA conversacional, oferecendo atendimento automatizado 24/7, busca inteligente de imóveis, agendamento de visitas e gestão qualificada de leads.

### 🎯 Principais Benefícios

- **Atendimento 24/7**: Responde consultas instantaneamente, mesmo fora do horário comercial
- **Qualificação Automática**: Identifica e qualifica leads com base em suas preferências
- **Agendamento Inteligente**: Marca visitas diretamente no Google Calendar do corretor
- **Multi-idiomas**: Suporte nativo para Português, Espanhol e Inglês
- **Análise em Tempo Real**: Dashboard com métricas de conversão e engajamento

## 🚀 Funcionalidades

### ✅ Implementadas

- **🤖 Assistente IA Conversacional**
  - Respostas humanizadas com GPT-4
  - Consolidação de múltiplas perguntas
  - Detecção de intenção para handoff humano
  
- **📱 Integração WhatsApp Business**
  - Recebimento e envio de mensagens
  - Suporte para texto, áudio e imagens
  - Segunda linha dedicada por corretor

- **🏢 Sistema Multi-Tenant**
  - Isolamento completo entre corretores
  - Configurações personalizadas por tenant
  - Base de dados segregada

- **📅 Gestão de Agendamentos**
  - Integração com Google Calendar
  - Oferece 2 opções de horários
  - Lembretes automáticos (24h e 3h antes)

- **👥 Gestão de Leads**
  - Captura automática de dados
  - Score de qualificação
  - Histórico de interações

- **🏷️ Classificação Automática**
  - Tags no Chatwoot por status
  - Priorização de atendimento
  - Métricas de conversão

### 🚧 Em Desenvolvimento

- **🔍 Scraping REMAX Argentina** - Busca automática de imóveis no site oficial
- **🎯 Matching Inteligente** - Correlação entre novos imóveis e leads antigos
- **📸 Processamento Multimídia** - Análise de imagens e transcrição de áudios
- **🔔 Notificações Proativas** - Alertas sobre oportunidades para o corretor

## 🏗️ Arquitetura

### Visão Geral do Sistema

```mermaid
graph TB
    subgraph "Camada Cliente"
        WA[WhatsApp Business]
        CW[Chatwoot Hub]
    end
    
    subgraph "Backend"
        API[FastAPI]
        AI[AI Agent<br/>LangChain]
        SCRAPER[REMAX Scraper]
    end
    
    subgraph "Dados"
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

### Fluxo de Conversação

1. **Cliente** envia mensagem via WhatsApp
2. **EVO API** recebe e envia webhook
3. **AI Agent** processa e identifica intenção
4. **Ações** executadas conforme necessidade:
   - Busca de imóveis (scraping)
   - Agendamento de visitas
   - Qualificação de lead
5. **Resposta** enviada ao cliente
6. **Chatwoot** atualizado com status

Para diagramas detalhados, veja [architecture.mmd](architecture.mmd).

## 🛠️ Stack Tecnológica

### Backend
- **Python 3.11+** - Linguagem principal
- **FastAPI** - Framework web assíncrono
- **SQLAlchemy** - ORM com suporte async
- **Pydantic** - Validação de dados

### IA & Machine Learning
- **LangChain** - Framework para AI agents
- **OpenAI GPT-4** - Modelo de linguagem
- **Qdrant** - Vector database para contexto
- **Whisper API** - Transcrição de áudio

### Infraestrutura
- **PostgreSQL** - Banco de dados principal (via Supabase)
- **Redis** - Cache e filas
- **Docker** - Containerização
- **EVO API** - Integração WhatsApp
- **Chatwoot** - Plataforma de suporte

## 📋 Pré-requisitos

- Python 3.11 ou superior
- Docker e Docker Compose
- Conta Supabase
- Instância EVO API configurada
- Chave API OpenAI
- Projeto Google Cloud com Calendar API
- Instância Chatwoot (opcional)

## 🚀 Instalação Rápida

### 1. Clone o repositório
```bash
git clone https://github.com/yourusername/corretor-ai-hub.git
cd corretor-ai-hub
```

### 2. Configure as variáveis de ambiente
```bash
cp .env.example .env
# Edite .env com suas credenciais
```

### 3. Inicie os serviços
```bash
docker-compose up -d
```

### 4. Instale as dependências
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Execute as migrações
```bash
alembic upgrade head
```

### 6. Inicie o servidor
```bash
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## ⚙️ Configuração

### Variáveis de Ambiente Essenciais

```bash
# API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Banco de Dados
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

## 📚 Documentação da API

Com o servidor rodando, acesse:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Principais Endpoints

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/webhooks/evo` | Webhook EVO API |
| POST | `/webhooks/chatwoot` | Webhook Chatwoot |
| GET | `/properties` | Lista imóveis |
| POST | `/properties/search` | Busca semântica |
| POST | `/appointments` | Agenda visitas |
| GET | `/leads` | Lista leads |
| GET | `/analytics/dashboard` | Métricas |

## 🧪 Testes

```bash
# Executar todos os testes
pytest

# Com cobertura
pytest --cov=src --cov-report=html

# Testes específicos
pytest tests/test_property_agent.py -v
```

## 📁 Estrutura do Projeto

```
corretor-ai-hub/
├── src/
│   ├── agents/          # Lógica do AI Agent
│   ├── api/             # Endpoints FastAPI
│   │   └── routes/      # Rotas organizadas
│   ├── core/            # Configurações e utils
│   ├── database/        # Modelos e schemas
│   ├── integrations/    # Serviços externos
│   ├── scrapers/        # Web scraping
│   └── services/        # Lógica de negócio
├── tests/               # Suite de testes
├── scripts/             # Scripts úteis
├── docs/                # Documentação
└── docker-compose.yml   # Orquestração
```

## 🔒 Segurança

- Autenticação JWT para APIs
- Validação de webhooks
- Rate limiting por tenant
- Dados criptografados em repouso
- Logs sem informações sensíveis

## 📈 Monitoramento

- Health checks em `/health`
- Métricas Prometheus em `/metrics`
- Logs estruturados com correlation ID
- Alertas para falhas críticas

## 🤝 Contribuindo

1. Fork o projeto
2. Crie uma branch (`git checkout -b feature/AmazingFeature`)
3. Commit suas mudanças (`git commit -m 'Add AmazingFeature'`)
4. Push para a branch (`git push origin feature/AmazingFeature`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a MIT License - veja [LICENSE](LICENSE) para detalhes.

## 🙏 Agradecimentos

- [LangChain](https://langchain.com/) - Framework de IA
- [EVO API](https://github.com/EvolutionAPI/evolution-api) - WhatsApp Business
- [Chatwoot](https://www.chatwoot.com/) - Plataforma de suporte
- [Supabase](https://supabase.com/) - Backend as a Service

---

Desenvolvido com ❤️ para revolucionar o mercado imobiliário