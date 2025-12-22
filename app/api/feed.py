from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.services.feed_service import FeedService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/")
@rate_limit("60/minute")
async def get_feed(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("newest", regex="^(newest|popular)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's feed"""
    try:
        feed_service = FeedService(db)
        
        feed = await feed_service.get_user_feed(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            sort_by=sort_by
        )
        
        return {
            "posts": feed,
            "skip": skip,
            "limit": limit,
            "sort_by": sort_by,
            "has_more": len(feed) == limit
        }
        
    except Exception as e:
        logger.error(f"Error getting feed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get feed"
        )

@router.get("/explore")
@rate_limit("60/minute")
async def explore_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Explore posts (for non-logged in users or to discover new content)"""
    try:
        feed_service = FeedService(db)
        
        user_id = current_user.id if current_user else None