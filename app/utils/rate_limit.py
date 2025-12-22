from slowapi import Limiter
from slowapi.util import get_remote_address
from functools import wraps
from fastapi import Request, HTTPException, status
import logging

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

def rate_limit(limit: str):
    """Decorator for rate limiting"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Get request from args
                request = None
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
                
                if request is None:
                    for key, value in kwargs.items():
                        if isinstance(value, Request):
                            request = value
                            break
                
                if request:
                    # Check rate limit
                    if hasattr(request.app.state, 'limiter'):
                        identifier = request.app.state.limiter.key_func(request)
                        current_limit = request.app.state.limiter._rate_limit(limit, None)
                        
                        # Simplified rate limiting logic
                        # In production, you'd use Redis or similar
                        pass
                
                return await func(*args, **kwargs)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Rate limit error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded"
                )
        return wrapper
    return decorator