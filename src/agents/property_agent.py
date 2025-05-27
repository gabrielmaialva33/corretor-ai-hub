"""
Property AI Agent - Main conversational agent for real estate assistance
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import structlog
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.chat_models import ChatOpenAI, ChatAnthropic
from langchain.embeddings import OpenAIEmbeddings
from langchain.memory import ConversationSummaryBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.tools import Tool

from src.agents.tools import (
    search_properties_tool,
    get_property_details_tool,
    schedule_appointment_tool,
    capture_lead_info_tool,
    check_availability_tool
)
from src.core.config import get_settings
from src.integrations.qdrant import QdrantManager

logger = structlog.get_logger()
settings = get_settings()


class PropertyAgent:
    """
    AI Agent for handling real estate conversations
    """

    def __init__(self, tenant_id: str, conversation_id: str):
        self.tenant_id = tenant_id
        self.conversation_id = conversation_id
        self.embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        self.vector_manager = QdrantManager(tenant_id)

        # Initialize LLM
        if settings.OPENAI_API_KEY:
            self.llm = ChatOpenAI(
                model_name=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                openai_api_key=settings.OPENAI_API_KEY
            )
        elif settings.ANTHROPIC_API_KEY:
            self.llm = ChatAnthropic(
                model=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=settings.LLM_MAX_TOKENS,
                anthropic_api_key=settings.ANTHROPIC_API_KEY
            )
        else:
            raise ValueError("No LLM API key configured")

        # Initialize memory
        self.memory = ConversationSummaryBufferMemory(
            llm=self.llm,
            max_token_limit=2000,
            return_messages=True
        )

        # Initialize tools
        self.tools = self._create_tools()

        # Create agent
        self.agent = self._create_agent()

    def _create_tools(self) -> List[Tool]:
        """Create tools for the agent"""
        return [
            Tool(
                name="search_properties",
                description="Search for properties based on criteria like location, price, bedrooms, etc.",
                func=lambda query: search_properties_tool(self.tenant_id, query)
            ),
            Tool(
                name="get_property_details",
                description="Get detailed information about a specific property",
                func=lambda property_id: get_property_details_tool(self.tenant_id, property_id)
            ),
            Tool(
                name="schedule_appointment",
                description="Schedule a property viewing appointment",
                func=lambda data: schedule_appointment_tool(self.tenant_id, json.loads(data))
            ),
            Tool(
                name="capture_lead_info",
                description="Capture and update lead information",
                func=lambda data: capture_lead_info_tool(self.tenant_id, json.loads(data))
            ),
            Tool(
                name="check_availability",
                description="Check agent availability for appointments",
                func=lambda date: check_availability_tool(self.tenant_id, date)
            )
        ]

    def _create_agent(self) -> AgentExecutor:
        """Create the conversational agent"""
        system_template = """Você é um assistente virtual especializado em imóveis, trabalhando para um corretor imobiliário.
        
        Suas responsabilidades:
        1. Ajudar clientes a encontrar imóveis que atendam suas necessidades
        2. Fornecer informações detalhadas sobre os imóveis disponíveis
        3. Agendar visitas aos imóveis
        4. Capturar informações dos leads de forma natural durante a conversa
        5. Responder perguntas sobre localização, preços, características dos imóveis
        
        Diretrizes importantes:
        - Seja sempre educado, profissional e prestativo
        - Faça perguntas para entender melhor as necessidades do cliente
        - Sugira alternativas quando não encontrar exatamente o que o cliente procura
        - Capture informações do lead naturalmente (nome, telefone, email, preferências)
        - Ao agendar visitas, sempre confirme data, horário e dados de contato
        - Se o cliente quiser falar com um humano, informe que irá transferir para o corretor
        - Use as ferramentas disponíveis para buscar informações precisas
        
        Informações do contexto:
        - Você está atendendo via WhatsApp
        - Os imóveis são do mercado brasileiro
        - Preços devem ser formatados em Reais (R$)
        - Datas e horários no formato brasileiro
        
        Tenant ID: {tenant_id}
        Conversation ID: {conversation_id}
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])

        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )

        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            memory=self.memory,
            verbose=True,
            max_iterations=5,
            early_stopping_method="generate"
        )

    async def process_message(
            self,
            message: str,
            metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Process a user message and generate response
        
        Returns:
            Tuple of (response_text, agent_state)
        """
        try:
            # Store message in vector database for context
            message_embedding = await self._get_embedding(message)
            await self.vector_manager.store_conversation_message(
                conversation_id=self.conversation_id,
                message_id=metadata.get("message_id", ""),
                content=message,
                embedding=message_embedding,
                metadata={
                    "timestamp": datetime.utcnow().isoformat(),
                    "sender": "user",
                    **metadata
                }
            )

            # Get relevant context from previous conversations
            context = await self._get_conversation_context(message_embedding)

            # Run agent
            result = await self.agent.ainvoke({
                "input": message,
                "tenant_id": self.tenant_id,
                "conversation_id": self.conversation_id,
                "context": context
            })

            response = result.get("output", "")

            # Store agent response
            response_embedding = await self._get_embedding(response)
            await self.vector_manager.store_conversation_message(
                conversation_id=self.conversation_id,
                message_id=f"ai_{metadata.get('message_id', '')}",
                content=response,
                embedding=response_embedding,
                metadata={
                    "timestamp": datetime.utcnow().isoformat(),
                    "sender": "assistant"
                }
            )

            # Extract agent state
            agent_state = self._extract_agent_state(result)

            return response, agent_state

        except Exception as e:
            logger.error(
                "Error processing message",
                error=str(e),
                conversation_id=self.conversation_id
            )

            # Fallback response
            fallback_response = (
                "Desculpe, encontrei um problema ao processar sua mensagem. "
                "Vou transferir você para um de nossos corretores para melhor atendê-lo."
            )

            return fallback_response, {
                "error": str(e),
                "handoff_requested": True,
                "handoff_reason": "processing_error"
            }

    async def _get_embedding(self, text: str) -> List[float]:
        """Get embedding for text"""
        return await self.embeddings.aembed_query(text)

    async def _get_conversation_context(
            self,
            query_embedding: List[float],
            limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get relevant conversation context"""
        return await self.vector_manager.search_conversation_context(
            conversation_id=self.conversation_id,
            query_embedding=query_embedding,
            limit=limit
        )

    def _extract_agent_state(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant state information from agent result"""
        state = {
            "tools_used": [],
            "properties_shown": [],
            "appointment_scheduled": False,
            "lead_info_captured": {},
            "handoff_requested": False,
            "confidence_score": 1.0
        }

        # Extract information from intermediate steps
        for step in result.get("intermediate_steps", []):
            tool_name = step[0].tool if hasattr(step[0], 'tool') else None
            tool_result = step[1] if len(step) > 1 else None

            if tool_name:
                state["tools_used"].append(tool_name)

                if tool_name == "search_properties" and tool_result:
                    state["properties_shown"] = [
                        p.get("property_id") for p in tool_result.get("properties", [])
                    ]
                elif tool_name == "schedule_appointment" and tool_result:
                    state["appointment_scheduled"] = tool_result.get("success", False)
                elif tool_name == "capture_lead_info" and tool_result:
                    state["lead_info_captured"] = tool_result.get("captured_info", {})

        # Check for handoff indicators in the response
        response = result.get("output", "").lower()
        handoff_keywords = ["corretor", "humano", "atendente", "falar com alguém"]
        if any(keyword in response for keyword in handoff_keywords):
            state["handoff_requested"] = True

        return state

    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation"""
        return self.memory.predict_new_summary(
            messages=self.memory.chat_memory.messages,
            existing_summary=""
        )

    async def handle_handoff_request(self) -> str:
        """Handle request to transfer to human agent"""
        response = (
            "Entendi que você prefere falar com um de nossos corretores. "
            "Vou transferir nossa conversa agora mesmo. "
            "Um corretor entrará em contato com você em breve. "
            "Enquanto isso, fique à vontade para continuar navegando pelos imóveis disponíveis!"
        )

        # Update conversation state for handoff
        # This would trigger notifications to human agents

        return response

    async def suggest_properties_based_on_history(self) -> List[Dict[str, Any]]:
        """Suggest properties based on conversation history"""
        # Get conversation summary
        summary = self.get_conversation_summary()

        # Extract preferences from summary
        preferences_prompt = f"""
        Based on this conversation summary, extract the client's property preferences:
        {summary}
        
        Return a JSON with: location, property_type, bedrooms, price_range, and any other relevant criteria.
        """

        preferences_response = await self.llm.apredict(preferences_prompt)

        try:
            preferences = json.loads(preferences_response)
        except:
            preferences = {}

        # Search for properties based on extracted preferences
        if preferences:
            return await search_properties_tool(self.tenant_id, json.dumps(preferences))

        return []
