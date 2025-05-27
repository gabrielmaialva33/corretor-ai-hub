# Hub de IA Imobiliária

Uma plataforma de IA conversacional multi-tenant para corretores de imóveis, integrando WhatsApp Business através da EVO API com correspondência inteligente de propriedades, agendamento de compromissos e gerenciamento de leads.

## 🚀 Funcionalidades

- **Conversas Alimentadas por IA**: Processamento de linguagem natural para consultas de imóveis em português
- **Arquitetura Multi-Tenant**: Ambientes isolados para cada corretor de imóveis
- **Integração com WhatsApp Business**: Mensagens perfeitas através da EVO API
- **Correspondência Inteligente de Imóveis**: Busca semântica baseada em vetores para recomendações de propriedades
- **Agendamento de Compromissos**: Integração com Google Calendar com lembretes automatizados
- **Gerenciamento de Leads**: Pontuação e qualificação automática de leads
- **Plataforma de Suporte ao Cliente**: Integração com Chatwoot para transferência para humanos
- **Dashboard de Analytics**: Métricas em tempo real e insights de conversas

## 🏗️ Arquitetura

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
                        │   Suporte   │  │  Calendar   │  │     Cache       │ │
                        └─────────────┘  └─────────────┘  └─────────────────┘ │
```

## 🛠️ Stack Tecnológica

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, Pydantic
- **IA/ML**: LangChain, OpenAI GPT-4, Qdrant Vector Database
- **Bancos de Dados**: PostgreSQL (Supabase), Redis
- **Mensageria**: EVO API (WhatsApp Business), Chatwoot
- **Infraestrutura**: Docker, Docker Compose
- **Testes**: Pytest, Coverage

## 📋 Pré-requisitos

- Python 3.11+
- Docker e Docker Compose
- Instância da EVO API
- Conta Supabase
- Chave da API OpenAI
- Projeto Google Cloud com Calendar API habilitada
- Instância Chatwoot (opcional)

## 🚀 Início Rápido

1. **Clone o repositório**
   ```bash
   git clone https://github.com/seuusuario/corretor-ai-hub.git
   cd corretor-ai-hub
   ```

2. **Configure as variáveis de ambiente**
   ```bash
   cp .env.example .env
   # Edite .env com suas credenciais
   ```

3. **Inicie os serviços de infraestrutura**
   ```bash
   docker-compose up -d
   ```

4. **Instale as dependências**
   ```bash
   pip install -r requirements.txt
   ```

5. **Execute as migrações do banco de dados**
   ```bash
   alembic upgrade head
   ```

6. **Inicie o servidor de desenvolvimento**
   ```bash
   python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
   ```

## 🔧 Configuração

Principais variáveis de ambiente:

```bash
# Configuração da API
API_HOST=0.0.0.0
API_PORT=8000
ENVIRONMENT=development

# Banco de Dados
DATABASE_URL=postgresql+asyncpg://usuario:senha@localhost/nomebd

# Serviços de IA
OPENAI_API_KEY=sua-chave-openai
QDRANT_URL=http://localhost:6333

# Integração WhatsApp
EVO_API_URL=https://sua-instancia-evo.com
EVO_API_KEY=sua-chave-evo-api

# Google Calendar
GOOGLE_CALENDAR_CREDENTIALS=json-codificado-base64

# Chatwoot
CHATWOOT_URL=https://seu-chatwoot.com
CHATWOOT_API_KEY=sua-chave-chatwoot
```

## 📚 Documentação da API

Uma vez em execução, acesse a documentação interativa da API em:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Endpoints Principais

- `POST /webhooks/evo` - Webhook da EVO API para mensagens WhatsApp
- `POST /webhooks/chatwoot` - Webhook Chatwoot para tickets de suporte
- `GET /properties` - Listar imóveis com filtros
- `POST /properties/search` - Busca semântica de imóveis
- `POST /appointments` - Agendar visitas a imóveis
- `GET /analytics/dashboard` - Métricas em tempo real

## 🧪 Testes

Execute a suíte de testes:
```bash
# Todos os testes
pytest

# Com cobertura
pytest --cov=src --cov-report=html

# Módulo específico
pytest tests/test_property_agent.py -v
```

## 📦 Estrutura do Projeto

```
corretor-ai-hub/
├── src/
│   ├── agents/          # Lógica do agente IA
│   ├── api/             # Aplicação FastAPI
│   ├── core/            # Utilitários principais
│   ├── database/        # Modelos de banco de dados
│   ├── integrations/    # Serviços externos
│   ├── scrapers/        # Scrapers de imóveis
│   └── services/        # Lógica de negócios
├── tests/               # Suíte de testes
├── scripts/             # Scripts utilitários
├── config/              # Arquivos de configuração
└── docs/                # Documentação
```

## 🤝 Contribuindo

1. Faça um fork do repositório
2. Crie uma branch de feature (`git checkout -b feature/funcionalidade-incrivel`)
3. Faça commit das suas mudanças (`git commit -m 'Adiciona funcionalidade incrível'`)
4. Faça push para a branch (`git push origin feature/funcionalidade-incrivel`)
5. Abra um Pull Request

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🙏 Agradecimentos

- [LangChain](https://langchain.com/) pelo framework de IA
- [EVO API](https://github.com/EvolutionAPI/evolution-api) pela integração WhatsApp
- [Chatwoot](https://www.chatwoot.com/) pelo suporte ao cliente
- [Supabase](https://supabase.com/) pela infraestrutura backend