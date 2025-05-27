"""
Redis integration for caching and message queuing
"""
import json
from typing import Optional, Any

import redis.asyncio as redis
import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Global Redis client
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis client"""
    global redis_client

    try:
        redis_client = redis.from_url(
            settings.redis_url_with_password,
            encoding="utf-8",
            decode_responses=True
        )

        # Test connection
        await redis_client.ping()

        logger.info("Redis client initialized successfully")

    except Exception as e:
        logger.error("Failed to initialize Redis client", error=str(e))
        raise


def get_redis_client() -> redis.Redis:
    """Get Redis client instance"""
    if not redis_client:
        raise RuntimeError("Redis client not initialized")
    return redis_client


class RedisCache:
    """Redis cache helper"""

    def __init__(self, prefix: str = "cache"):
        self.client = get_redis_client()
        self.prefix = prefix

    def _key(self, key: str) -> str:
        """Generate cache key with prefix"""
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = await self.client.get(self._key(key))
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error", error=str(e), key=key)
            return None

    async def set(self, key: str, value: Any, expire: int = 3600):
        """Set value in cache with expiration"""
        try:
            await self.client.set(
                self._key(key),
                json.dumps(value),
                ex=expire
            )
        except Exception as e:
            logger.error(f"Redis set error", error=str(e), key=key)

    async def delete(self, key: str):
        """Delete value from cache"""
        try:
            await self.client.delete(self._key(key))
        except Exception as e:
            logger.error(f"Redis delete error", error=str(e), key=key)

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            return await self.client.exists(self._key(key)) > 0
        except Exception as e:
            logger.error(f"Redis exists error", error=str(e), key=key)
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        try:
            return await self.client.incrby(self._key(key), amount)
        except Exception as e:
            logger.error(f"Redis increment error", error=str(e), key=key)
            return 0

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values"""
        try:
            pipeline = self.client.pipeline()
            for key in keys:
                pipeline.get(self._key(key))

            values = await pipeline.execute()
            result = {}

            for key, value in zip(keys, values):
                if value:
                    result[key] = json.loads(value)

            return result
        except Exception as e:
            logger.error(f"Redis get_many error", error=str(e))
            return {}


class RedisQueue:
    """Redis queue helper for background tasks"""

    def __init__(self, queue_name: str = "tasks"):
        self.client = get_redis_client()
        self.queue_name = f"queue:{queue_name}"

    async def push(self, task: Dict[str, Any]):
        """Push task to queue"""
        try:
            await self.client.rpush(
                self.queue_name,
                json.dumps(task)
            )
        except Exception as e:
            logger.error(f"Redis queue push error", error=str(e))

    async def pop(self, timeout: int = 0) -> Optional[Dict[str, Any]]:
        """Pop task from queue"""
        try:
            if timeout > 0:
                result = await self.client.blpop(self.queue_name, timeout)
                if result:
                    return json.loads(result[1])
            else:
                result = await self.client.lpop(self.queue_name)
                if result:
                    return json.loads(result)
            return None
        except Exception as e:
            logger.error(f"Redis queue pop error", error=str(e))
            return None

    async def size(self) -> int:
        """Get queue size"""
        try:
            return await self.client.llen(self.queue_name)
        except Exception as e:
            logger.error(f"Redis queue size error", error=str(e))
            return 0


class RateLimiter:
    """Redis-based rate limiter"""

    def __init__(self, prefix: str = "ratelimit"):
        self.client = get_redis_client()
        self.prefix = prefix

    async def is_allowed(
            self,
            key: str,
            limit: int,
            window: int = 60
    ) -> tuple[bool, int]:
        """
        Check if request is allowed under rate limit
        
        Args:
            key: Unique identifier (e.g., user_id, ip_address)
            limit: Maximum requests allowed
            window: Time window in seconds
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        try:
            full_key = f"{self.prefix}:{key}"

            # Use pipeline for atomic operations
            pipeline = self.client.pipeline()
            pipeline.incr(full_key)
            pipeline.expire(full_key, window)

            results = await pipeline.execute()
            current_count = results[0]

            is_allowed = current_count <= limit
            remaining = max(0, limit - current_count)

            return is_allowed, remaining

        except Exception as e:
            logger.error(f"Rate limiter error", error=str(e), key=key)
            # Fail open - allow request if Redis fails
            return True, limit

    async def reset(self, key: str):
        """Reset rate limit for a key"""
        try:
            full_key = f"{self.prefix}:{key}"
            await self.client.delete(full_key)
        except Exception as e:
            logger.error(f"Rate limiter reset error", error=str(e), key=key)
