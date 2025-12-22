# app/services/redis_service.py
from redis.asyncio import Redis
from app.config import settings

class RedisService:
    def __init__(self):
        self.redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def set(self, key: str, value: str, expire: int = None):
        """Set a key with optional expiration in seconds"""
        await self.redis.set(name=key, value=value, ex=expire)

    async def get(self, key: str):
        """Get the value of a key"""
        return await self.redis.get(key)

    async def delete(self, key: str):
        """Delete a key"""
        await self.redis.delete(key)

    async def close(self):
        """Close the Redis connection"""
        await self.redis.close()
