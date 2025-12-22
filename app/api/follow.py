from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.schemas.follow_schema import (
    FollowCreate,
    FollowResponse,
    FollowListResponse,
    FollowStats,
    UserRelationship
)
from app.services.follow_service import FollowService
from app.services.notification_service import NotificationService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.utils.rate_limit import rate_limit
from app.utils.cache import cache_response

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/users/{user_id}/follow", response_model=FollowResponse)
@rate_limit("30/minute")
async def follow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Follow a user"""
    try:
        follow_service = FollowService(db)
        notification_service = NotificationService(db)
        
        # Check if user exists
        from sqlalchemy import select
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if trying to follow self
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot follow yourself"
            )
        
        # Check if already following
        existing = await follow_service.get_follow_relationship(
            follower_id=current_user.id,
            following_id=user_id
        )
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already following this user"
            )
        
        # Create follow relationship
        follow_data = FollowCreate(
            follower_id=current_user.id,
            following_id=user_id
        )
        
        follow = await follow_service.create_follow(follow_data)
        
        # Send notification
        await notification_service.create_follow_notification(
            follower_id=current_user.id,
            following_id=user_id
        )
        
        # Update user stats cache
        await follow_service.update_user_stats_cache(current_user.id, user_id)
        
        logger.info(f"User {current_user.id} started following user {user_id}")
        
        return FollowResponse(
            id=follow.id,
            follower_id=follow.follower_id,
            following_id=follow.following_id,
            created_at=follow.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error following user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to follow user"
        )

@router.delete("/users/{user_id}/follow")
@rate_limit("30/minute")
async def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unfollow a user"""
    try:
        follow_service = FollowService(db)
        
        # Check if user exists
        from sqlalchemy import select
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if trying to unfollow self
        if user_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot unfollow yourself"
            )
        
        # Check if following
        existing = await follow_service.get_follow_relationship(
            follower_id=current_user.id,
            following_id=user_id
        )
        
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not following this user"
            )
        
        # Delete follow relationship
        deleted = await follow_service.delete_follow(
            follower_id=current_user.id,
            following_id=user_id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to unfollow user"
            )
        
        # Update user stats cache
        await follow_service.update_user_stats_cache(current_user.id, user_id)
        
        logger.info(f"User {current_user.id} unfollowed user {user_id}")
        
        return {"message": "Successfully unfollowed user"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unfollowing user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unfollow user"
        )

@router.get("/followers", response_model=FollowListResponse)
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def get_followers(
    user_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get followers of a user"""
    try:
        follow_service = FollowService(db)
        
        # Determine target user
        target_user = None
        if user_id:
            from sqlalchemy import select
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        elif username:
            from sqlalchemy import select
            stmt = select(User).where(User.username == username)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        else:
            # Default to current user if authenticated
            if current_user:
                target_user = current_user
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Must provide user_id, username, or be authenticated"
                )
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get followers
        followers = await follow_service.get_user_followers(
            user_id=target_user.id,
            viewer_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit
        )
        
        # Get total count
        total_followers = await follow_service.get_follower_count(target_user.id)
        
        # Check if current user follows this user
        follows_you = False
        if current_user and current_user.id != target_user.id:
            relationship = await follow_service.get_follow_relationship(
                follower_id=current_user.id,
                following_id=target_user.id
            )
            follows_you = relationship is not None
        
        # Check if you follow this user
        you_follow = False
        if current_user and current_user.id != target_user.id:
            relationship = await follow_service.get_follow_relationship(
                follower_id=target_user.id,
                following_id=current_user.id
            )
            you_follow = relationship is not None
        
        return FollowListResponse(
            followers=followers,
            total=total_followers,
            skip=skip,
            limit=limit,
            user_id=target_user.id,
            username=target_user.username,
            follows_you=follows_you,
            you_follow=you_follow
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting followers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get followers"
        )

@router.get("/following", response_model=FollowListResponse)
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def get_following(
    user_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get users that a user is following"""
    try:
        follow_service = FollowService(db)
        
        # Determine target user
        target_user = None
        if user_id:
            from sqlalchemy import select
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        elif username:
            from sqlalchemy import select
            stmt = select(User).where(User.username == username)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        else:
            # Default to current user if authenticated
            if current_user:
                target_user = current_user
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Must provide user_id, username, or be authenticated"
                )
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Get following
        following = await follow_service.get_user_following(
            user_id=target_user.id,
            viewer_id=current_user.id if current_user else None,
            skip=skip,
            limit=limit
        )
        
        # Get total count
        total_following = await follow_service.get_following_count(target_user.id)
        
        # Check relationship status
        follows_you = False
        you_follow = False
        
        if current_user and current_user.id != target_user.id:
            # Check if current user follows target
            relationship1 = await follow_service.get_follow_relationship(
                follower_id=current_user.id,
                following_id=target_user.id
            )
            you_follow = relationship1 is not None
            
            # Check if target follows current user
            relationship2 = await follow_service.get_follow_relationship(
                follower_id=target_user.id,
                following_id=current_user.id
            )
            follows_you = relationship2 is not None
        
        return FollowListResponse(
            followers=following,  # Reusing same schema for following
            total=total_following,
            skip=skip,
            limit=limit,
            user_id=target_user.id,
            username=target_user.username,
            follows_you=follows_you,
            you_follow=you_follow
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting following: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get following"
        )

@router.get("/mutual", response_model=FollowListResponse)
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def get_mutual_follows(
    user_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get mutual followers between current user and another user"""
    try:
        follow_service = FollowService(db)
        
        # Determine target user
        target_user = None
        if user_id:
            from sqlalchemy import select
            stmt = select(User).where(User.id == user_id)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        elif username:
            from sqlalchemy import select
            stmt = select(User).where(User.username == username)
            result = await db.execute(stmt)
            target_user = result.scalar_one_or_none()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must provide user_id or username"
            )
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if current_user.id == target_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot get mutual follows with yourself"
            )
        
        # Get mutual follows
        mutual_follows = await follow_service.get_mutual_follows(
            user1_id=current_user.id,
            user2_id=target_user.id,
            skip=skip,
            limit=limit
        )
        
        # Get total count
        total_mutual = await follow_service.get_mutual_follow_count(
            user1_id=current_user.id,
            user2_id=target_user.id
        )
        
        return FollowListResponse(
            followers=mutual_follows,
            total=total_mutual,
            skip=skip,
            limit=limit,
            user_id=target_user.id,
            username=target_user.username
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting mutual follows: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get mutual follows"
        )

@router.get("/suggestions", response_model=List[dict])
@rate_limit("60/minute")
@cache_response(300)  # Cache for 5 minutes
async def get_follow_suggestions(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get follow suggestions for current user"""
    try:
        follow_service = FollowService(db)
        
        suggestions = await follow_service.get_follow_suggestions(
            user_id=current_user.id,
            limit=limit
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Error getting follow suggestions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get follow suggestions"
        )

@router.get("/stats/{user_id}", response_model=FollowStats)
@rate_limit("60/minute")
@cache_response(120)  # Cache for 2 minutes
async def get_follow_stats(
    user_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get follow statistics for a user"""
    try:
        follow_service = FollowService(db)
        
        # Check if user exists
        from sqlalchemy import select
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        stats = await follow_service.get_user_follow_stats(user_id)
        
        # Add relationship info if current user is viewing
        if current_user:
            relationship = await follow_service.get_relationship_status(
                viewer_id=current_user.id,
                target_id=user_id
            )
            stats.relationship = relationship
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting follow stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get follow stats"
        )

@router.get("/relationship/{user_id}", response_model=UserRelationship)
@rate_limit("60/minute")
async def get_relationship_status(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get relationship status between current user and another user"""
    try:
        follow_service = FollowService(db)
        
        # Check if user exists
        from sqlalchemy import select
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        target_user = result.scalar_one_or_none()
        
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if current_user.id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot get relationship with yourself"
            )
        
        relationship = await follow_service.get_relationship_status(
            viewer_id=current_user.id,
            target_id=user_id
        )
        
        return relationship
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting relationship status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get relationship status"
        )

@router.get("/pending", response_model=List[dict])
@rate_limit("60/minute")
async def get_pending_follow_requests(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get pending follow requests (for private accounts)"""
    try:
        # This endpoint would be used if you implement private accounts
        # where follow requests need approval
        
        # For now, return empty list (public accounts only)
        return []
        
    except Exception as e:
        logger.error(f"Error getting pending requests: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pending requests"
        )

@router.get("/search", response_model=List[dict])
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def search_users_to_follow(
    query: str = Query(..., min_length=1, max_length=50),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Search for users to follow"""
    try:
        follow_service = FollowService(db)
        
        users = await follow_service.search_users(
            query=query,
            searcher_id=current_user.id,
            skip=skip,
            limit=limit
        )
        
        return users
        
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search users"
        )

@router.post("/batch/follow")
@rate_limit("30/minute")
async def batch_follow_users(
    user_ids: List[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Follow multiple users at once"""
    try:
        follow_service = FollowService(db)
        
        if len(user_ids) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot follow more than 50 users at once"
            )
        
        # Remove duplicates and self
        unique_ids = list(set(user_ids))
        if current_user.id in unique_ids:
            unique_ids.remove(current_user.id)
        
        if not unique_ids:
            return {"message": "No valid users to follow", "followed": []}
        
        # Check if users exist
        from sqlalchemy import select
        stmt = select(User.id).where(User.id.in_(unique_ids))
        result = await db.execute(stmt)
        existing_ids = {row[0] for row in result.all()}
        
        invalid_ids = set(unique_ids) - existing_ids
        valid_ids = list(existing_ids)
        
        if invalid_ids:
            logger.warning(f"Invalid user IDs in batch follow: {invalid_ids}")
        
        if not valid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid users found to follow"
            )
        
        # Follow users
        followed = []
        already_following = []
        
        for user_id in valid_ids:
            try:
                # Check if already following
                existing = await follow_service.get_follow_relationship(
                    follower_id=current_user.id,
                    following_id=user_id
                )
                
                if existing:
                    already_following.append(user_id)
                    continue
                
                # Create follow relationship
                follow_data = FollowCreate(
                    follower_id=current_user.id,
                    following_id=user_id
                )
                
                follow = await follow_service.create_follow(follow_data)
                followed.append(user_id)
                
                # Send notification
                notification_service = NotificationService(db)
                await notification_service.create_follow_notification(
                    follower_id=current_user.id,
                    following_id=user_id
                )
                
            except Exception as e:
                logger.error(f"Error following user {user_id}: {e}")
                continue
        
        # Update cache
        for user_id in followed:
            await follow_service.update_user_stats_cache(current_user.id, user_id)
        
        logger.info(f"User {current_user.id} followed {len(followed)} users in batch")
        
        return {
            "message": "Batch follow completed",
            "followed": followed,
            "already_following": already_following,
            "invalid_users": list(invalid_ids) if invalid_ids else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch follow: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch follow users"
        )