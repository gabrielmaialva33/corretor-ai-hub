"""
Qdrant Vector Database Integration
"""
import uuid
from typing import List, Dict, Any, Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    SearchRequest, SearchParams, ScoreModifier
)

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Global client instance
qdrant_client: Optional[QdrantClient] = None


async def init_qdrant():
    """Initialize Qdrant client"""
    global qdrant_client

    try:
        if settings.QDRANT_API_KEY:
            qdrant_client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=settings.QDRANT_API_KEY,
                timeout=30
            )
        else:
            qdrant_client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=30
            )

        # Test connection
        await qdrant_client.get_collections()
        logger.info("Qdrant client initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize Qdrant client", error=str(e))
        raise


class QdrantManager:
    """
    Manager for Qdrant vector database operations
    """

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.namespace = f"{settings.QDRANT_COLLECTION_PREFIX}{tenant_id}"
        self.client = qdrant_client

        if not self.client:
            raise RuntimeError("Qdrant client not initialized")

    async def create_collections(self):
        """Create necessary collections for the tenant"""
        collections = {
            "conversations": {
                "size": 1536,  # OpenAI embeddings size
                "distance": Distance.COSINE
            },
            "properties": {
                "size": 1536,
                "distance": Distance.COSINE
            },
            "knowledge": {
                "size": 1536,
                "distance": Distance.COSINE
            }
        }

        for collection_suffix, params in collections.items():
            collection_name = f"{self.namespace}_{collection_suffix}"

            try:
                # Check if collection exists
                collections_list = await self.client.get_collections()
                if collection_name not in [c.name for c in collections_list.collections]:
                    await self.client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=params["size"],
                            distance=params["distance"]
                        )
                    )
                    logger.info(f"Created collection: {collection_name}")
                else:
                    logger.info(f"Collection already exists: {collection_name}")

            except Exception as e:
                logger.error(f"Failed to create collection {collection_name}", error=str(e))
                raise

    async def store_conversation_message(
            self,
            conversation_id: str,
            message_id: str,
            content: str,
            embedding: List[float],
            metadata: Dict[str, Any]
    ):
        """Store a conversation message with its embedding"""
        collection_name = f"{self.namespace}_conversations"

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "conversation_id": conversation_id,
                "message_id": message_id,
                "content": content,
                "tenant_id": self.tenant_id,
                **metadata
            }
        )

        await self.client.upsert(
            collection_name=collection_name,
            points=[point]
        )

    async def search_conversation_context(
            self,
            conversation_id: str,
            query_embedding: List[float],
            limit: int = 10,
            score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for relevant context within a conversation"""
        collection_name = f"{self.namespace}_conversations"

        search_result = await self.client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="conversation_id",
                        match=MatchValue(value=conversation_id)
                    )
                ]
            ),
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "content": hit.payload.get("content"),
                "message_id": hit.payload.get("message_id"),
                "score": hit.score,
                "metadata": {k: v for k, v in hit.payload.items()
                             if k not in ["content", "message_id", "conversation_id", "tenant_id"]}
            }
            for hit in search_result
        ]

    async def store_property(
            self,
            property_id: str,
            title: str,
            description: str,
            embedding: List[float],
            metadata: Dict[str, Any]
    ):
        """Store a property with its embedding"""
        collection_name = f"{self.namespace}_properties"

        point = PointStruct(
            id=property_id,
            vector=embedding,
            payload={
                "property_id": property_id,
                "title": title,
                "description": description,
                "tenant_id": self.tenant_id,
                **metadata
            }
        )

        await self.client.upsert(
            collection_name=collection_name,
            points=[point]
        )

    async def search_properties(
            self,
            query_embedding: List[float],
            filters: Optional[Dict[str, Any]] = None,
            limit: int = 10,
            score_threshold: float = 0.6
    ) -> List[Dict[str, Any]]:
        """Search for properties based on semantic similarity"""
        collection_name = f"{self.namespace}_properties"

        # Build filter conditions
        must_conditions = []

        if filters:
            for key, value in filters.items():
                if value is not None:
                    if isinstance(value, dict):
                        # Range filters (e.g., {"min": 100000, "max": 500000})
                        if "min" in value and value["min"] is not None:
                            must_conditions.append(
                                FieldCondition(
                                    key=key,
                                    range={"gte": value["min"]}
                                )
                            )
                        if "max" in value and value["max"] is not None:
                            must_conditions.append(
                                FieldCondition(
                                    key=key,
                                    range={"lte": value["max"]}
                                )
                            )
                    else:
                        # Exact match filters
                        must_conditions.append(
                            FieldCondition(
                                key=key,
                                match=MatchValue(value=value)
                            )
                        )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        search_result = await self.client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "property_id": hit.payload.get("property_id"),
                "title": hit.payload.get("title"),
                "description": hit.payload.get("description"),
                "score": hit.score,
                "metadata": {k: v for k, v in hit.payload.items()
                             if k not in ["property_id", "title", "description", "tenant_id"]}
            }
            for hit in search_result
        ]

    async def store_knowledge(
            self,
            knowledge_id: str,
            content: str,
            embedding: List[float],
            metadata: Dict[str, Any]
    ):
        """Store general knowledge or FAQ items"""
        collection_name = f"{self.namespace}_knowledge"

        point = PointStruct(
            id=knowledge_id,
            vector=embedding,
            payload={
                "knowledge_id": knowledge_id,
                "content": content,
                "tenant_id": self.tenant_id,
                **metadata
            }
        )

        await self.client.upsert(
            collection_name=collection_name,
            points=[point]
        )

    async def search_knowledge(
            self,
            query_embedding: List[float],
            category: Optional[str] = None,
            limit: int = 5,
            score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Search for relevant knowledge base items"""
        collection_name = f"{self.namespace}_knowledge"

        must_conditions = []
        if category:
            must_conditions.append(
                FieldCondition(
                    key="category",
                    match=MatchValue(value=category)
                )
            )

        query_filter = Filter(must=must_conditions) if must_conditions else None

        search_result = await self.client.search(
            collection_name=collection_name,
            query_vector=query_embedding,
            query_filter=query_filter,
            limit=limit,
            score_threshold=score_threshold
        )

        return [
            {
                "knowledge_id": hit.payload.get("knowledge_id"),
                "content": hit.payload.get("content"),
                "score": hit.score,
                "metadata": {k: v for k, v in hit.payload.items()
                             if k not in ["knowledge_id", "content", "tenant_id"]}
            }
            for hit in search_result
        ]

    async def delete_conversation_messages(self, conversation_id: str):
        """Delete all messages from a conversation"""
        collection_name = f"{self.namespace}_conversations"

        await self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="conversation_id",
                        match=MatchValue(value=conversation_id)
                    )
                ]
            )
        )

    async def delete_property(self, property_id: str):
        """Delete a property from the vector database"""
        collection_name = f"{self.namespace}_properties"

        await self.client.delete(
            collection_name=collection_name,
            points_selector=[property_id]
        )

    async def update_property_metadata(
            self,
            property_id: str,
            metadata_updates: Dict[str, Any]
    ):
        """Update property metadata"""
        collection_name = f"{self.namespace}_properties"

        # Get existing point
        points = await self.client.retrieve(
            collection_name=collection_name,
            ids=[property_id]
        )

        if points:
            point = points[0]
            # Update payload
            updated_payload = {**point.payload, **metadata_updates}

            await self.client.set_payload(
                collection_name=collection_name,
                payload=updated_payload,
                points=[property_id]
            )

    async def get_collection_info(self, collection_suffix: str) -> Dict[str, Any]:
        """Get information about a collection"""
        collection_name = f"{self.namespace}_{collection_suffix}"

        info = await self.client.get_collection(collection_name=collection_name)

        return {
            "name": collection_name,
            "vector_size": info.config.params.vectors.size,
            "distance": info.config.params.vectors.distance,
            "points_count": info.points_count,
            "indexed_vectors_count": info.indexed_vectors_count
        }

    async def cleanup_old_conversations(self, days: int = 90):
        """Clean up old conversation messages"""
        collection_name = f"{self.namespace}_conversations"

        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        await self.client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="created_at",
                        range={"lt": cutoff_date.isoformat()}
                    )
                ]
            )
        )
