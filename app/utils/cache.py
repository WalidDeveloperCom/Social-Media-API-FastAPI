from functools import wraps
from typing import Callable, Any
import json
import logging
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)
redis_service = RedisService()

def cache_response(ttl: int = 60):
    """Decorator to cache API responses"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                # Generate cache key from function name and arguments
                cache_key = f"response:{func.__name__}"
                
                # Add significant arguments to cache key
                for arg in args:
                    if isinstance(arg, (int, str, float, bool)):
                        cache_key += f":{arg}"
                
                for key, value in kwargs.items():
                    if isinstance(value, (int, str, float, bool)):
                        cache_key += f":{key}:{value}"
                
                # Try to get from cache
                cached = await redis_service.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit for {cache_key}")
                    return json.loads(cached)
                
                # Cache miss, execute function
                logger.debug(f"Cache miss for {cache_key}")
                result = await func(*args, **kwargs)
                
                # Cache the result
                try:
                    await redis_service.setex(
                        cache_key,
                        ttl,
                        json.dumps(result, default=str)
                    )
                except Exception as e:
                    logger.error(f"Error caching result: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"Cache decorator error: {e}")
                # Fall back to executing the function
                return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator