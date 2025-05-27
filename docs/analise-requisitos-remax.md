# Análise de Requisitos - Projeto REMAX Argentina

## 📋 Visão Geral do Projeto

O **Corretor AI Hub** é uma plataforma de automação inteligente para corretores imobiliários, integrando WhatsApp Business, IA conversacional e ferramentas de gestão. O sistema fornece um assistente virtual que responde consultas, agenda visitas e gerencia leads de forma autônoma.

## 🎯 Objetivos Principais

1. **Automatizar o atendimento inicial** de clientes interessados em imóveis
2. **Centralizar conversas** de múltiplos canais em uma única plataforma
3. **Fazer scraping inteligente** do site REMAX para buscar imóveis
4. **Agendar visitas automaticamente** integrando com Google Calendar
5. **Qualificar e gerenciar leads** com base em suas preferências
6. **Notificar corretores** sobre oportunidades relevantes

## 📊 Checklist de Funcionalidades

### ✅ Funcionalidades Já Implementadas

#### 1. **Conversas Multicanal** ✅
- **Descrição**: Recebe consultas via WhatsApp e centraliza no Chatwoot
- **Status**: Implementado para WhatsApp (Instagram pendente)
- **Componentes**:
  - Multi-tenancy com isolamento por corretor
  - Integração EVO API para WhatsApp Business
  - Chatwoot como hub central de conversas
  - Caixas de entrada isoladas por corretor

#### 3. **Atendimento Automático com IA** ✅
- **Descrição**: Responde consultas simulando conversa humana
- **Status**: Totalmente implementado
- **Componentes**:
  - AI Agent com LangChain e GPT-4
  - Respostas humanizadas com delays configuráveis
  - Consolidação de múltiplas perguntas
  - Contexto de conversa mantido via Qdrant

#### 6. **Gestão de Calendário** ✅
- **Descrição**: Consulta disponibilidade e agenda visitas
- **Status**: Totalmente implementado
- **Componentes**:
  - Integração completa com Google Calendar
  - Oferece 2 opções de horários disponíveis
  - Confirmação automática de agendamento
  - Suporte para cancelamento/reagendamento

#### 8. **Classificação de Status das Conversas** ✅
- **Descrição**: Etiqueta conversas por status no Chatwoot
- **Status**: Totalmente implementado
- **Etiquetas**:
  - `dados-enviados`: Informações do imóvel compartilhadas
  - `visita-pendente`: Aguardando confirmação de visita
  - `visita-agendada`: Visita confirmada
  - `revisao-manual`: Requer atenção do corretor

#### 9. **Parada de Automação (Cliente)** ✅
- **Descrição**: Interrompe automação quando cliente pede humano
- **Status**: Totalmente implementado
- **Fluxo**:
  - Detecção de palavras-chave ("falar com humano", "atendente")
  - Tag `humano` aplicada no Chatwoot
  - Notificação enviada ao corretor via WhatsApp

#### 10. **Parada de Automação (Corretor)** ✅
- **Descrição**: Corretor pode interromper automação via Chatwoot
- **Status**: Totalmente implementado
- **Métodos**:
  - Menu de contexto no Chatwoot
  - Interrupção automática ao intervir na conversa

#### 11. **Registro de Leads** ✅
- **Descrição**: Coleta e armazena dados de cada lead
- **Status**: Totalmente implementado
- **Dados coletados**:
  - Nome, telefone, email
  - Preferências: quartos, área, cidade, faixa de preço
  - Histórico de interações
  - Score de qualificação

### 🚧 Funcionalidades a Desenvolver

#### 2. **Ativação por Tipo de Mensagem** 🔧
- **Descrição**: Ativa automação apenas para casos específicos
- **Requisitos**:
  - Detectar contatos novos vs existentes
  - Identificar links de portais (ZonaProp, ArgenProp, Mercado Libre)
  - Lógica de ativação condicional
- **Complexidade**: Média

#### 4. **Scraping do Site REMAX** 🔧
- **Descrição**: Busca imóveis no site oficial baseado em critérios
- **Requisitos**:
  - Scraping de https://www.remax.com.ar
  - Uso de filtros do site (localização, quartos, preço)
  - Cache de resultados
  - Apresentação de opções ao cliente
- **Complexidade**: Alta

#### 5. **Processamento de Mensagens Multimídia** 🔧
- **Descrição**: Processa áudios, imagens e textos
- **Requisitos**:
  - Transcrição de áudios (Whisper API)
  - Análise de imagens (OCR/Vision)
  - Extração de informações relevantes
- **Complexidade**: Média

#### 7. **Notificações de Lembrete de Visitas** 🔧
- **Descrição**: Envia lembretes automáticos antes das visitas
- **Requisitos**:
  - Lembrete 24h antes
  - Lembrete 3h antes
  - Templates personalizáveis
  - Sistema de fila para envios
- **Complexidade**: Baixa

#### 12. **Matching de Imóveis com Leads** 🔧
- **Descrição**: Compara novos imóveis com preferências de leads antigos
- **Requisitos**:
  - Lista semanal de imóveis do corretor
  - Motor de matching com critérios salvos
  - Notificação ao corretor sobre matches
  - Sugestão de recontato com leads
- **Complexidade**: Alta

#### 13. **Identificação de Leads Compatíveis** 🔧
- **Descrição**: Marca no Chatwoot leads interessados em imóveis do corretor
- **Requisitos**:
  - Análise contínua de compatibilidade
  - Tags dinâmicas no Chatwoot
  - Histórico de imóveis compatíveis
- **Complexidade**: Média

## Estimativa de Desenvolvimento

### Fase 1 - Adaptações Core (2 semanas)
- Configurar multi-tenancy para Argentina
- Adaptar templates de mensagem para espanhol
- Configurar regras de negócio específicas

### Fase 2 - Scraping e Multimídia (3 semanas)
- Desenvolver scraper REMAX Argentina
- Implementar processamento de áudio/imagem
- Testes de integração

### Fase 3 - Automações Avançadas (2 semanas)
- Sistema de notificações
- Motor de matching leads/propriedades
- Ativação condicional

### Fase 4 - Otimizações (1 semana)
- Performance tuning
- Monitoramento
- Documentação

## Considerações Técnicas

### Scraping REMAX
- Análise preliminar do site necessária
- Possível necessidade de Playwright para conteúdo dinâmico
- Rate limiting para evitar bloqueios

### Processamento de Áudio
- Integração com Whisper API (OpenAI) ou similar
- Suporte para áudios do WhatsApp (opus/ogg)

### Sistema de Notificações
- Usar Celery/Redis para agendamento
- Templates personalizáveis por corretor

### Performance
- Cache agressivo para buscas frequentes
- Índices otimizados para matching
- Processamento assíncrono para operações pesadas

## Próximos Passos

1. Validar acesso e estrutura do site REMAX Argentina
2. Definir prioridades de implementação
3. Setup ambiente de desenvolvimento para Argentina
4. Criar roadmap detalhado com entregas incrementais