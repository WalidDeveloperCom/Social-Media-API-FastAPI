from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.services.search_service import SearchService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/posts")
@rate_limit("60/minute")
async def search_posts(
    query: str = Query(..., min_length=1, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search posts"""
    try:
        search_service = SearchService()
        
        # Check if search service is available
        if not await search_service.is_available():
            return {"results": [], "total": 0, "message": "Search service unavailable"}
        
        results = await search_service.search_posts(
            query=query,
            skip=skip,
            limit=limit,
            user_id=current_user.id if current_user else None,
            is_public=True if not current_user else None
        )
        
        return {
            "results": results,
            "total": len(results),
            "query": query,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error searching posts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search posts"
        )

@router.get("/users")
@rate_limit("60/minute")
async def search_users(
    query: str = Query(..., min_length=1, max_length=50),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search users"""
    try:
        search_service = SearchService()
        
        if not await search_service.is_available():
            return {"results": [], "total": 0, "message": "Search service unavailable"}
        
        results = await search_service.search_users(
            query=query,
            skip=skip,
            limit=limit,
            only_active=True
        )
        
        return {
            "results": results,
            "total": len(results),
            "query": query,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search users"
        )

@router.get("/autocomplete/users")
@rate_limit("120/minute")
async def autocomplete_users(
    query: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(10, ge=1, le=20),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Autocomplete user search"""
    try:
        search_service = SearchService()
        
        if not await search_service.is_available():
            return {"suggestions": [], "message": "Search service unavailable"}
        
        suggestions = await search_service.autocomplete_users(
            query=query,
            limit=limit
        )
        
        return {"suggestions": suggestions, "query": query}
        
    except Exception as e:
        logger.error(f"Error autocomplete users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to autocomplete users"
        )

@router.get("/popular/posts")
@rate_limit("60/minute")
async def get_popular_posts(
    time_range: str = Query("week", regex="^(day|week|month|year)$"),
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get popular posts"""
    try:
        search_service = SearchService()
        
        if not await search_service.is_available():
            return {"posts": [], "message": "Search service unavailable"}
        
        popular_posts = await search_service.get_popular_posts(
            time_range=time_range,
            limit=limit
        )
        
        return {
            "posts": popular_posts,
            "time_range": time_range,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error getting popular posts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get popular posts"
        )

@router.get("/stats")
@rate_limit("30/minute")
async def get_search_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get search service statistics"""
    try:
        search_service = SearchService()
        
        if not await search_service.is_available():
            return {"available": False, "message": "Search service unavailable"}
        
        stats = await search_service.get_index_stats()
        
        return {
            "available": True,
            "indices": stats,
            "elasticsearch_url": settings.ELASTICSEARCH_URL
        }
        
    except Exception as e:
        logger.error(f"Error getting search stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get search stats"
        )