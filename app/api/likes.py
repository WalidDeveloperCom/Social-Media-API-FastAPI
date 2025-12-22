from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.schemas.like_schema import (
    LikeCreate,
    LikeResponse,
    LikeListResponse,
    LikeStats,
    LikeType
)
from app.services.like_service import LikeService
from app.services.notification_service import NotificationService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.post import Post
from app.models.comment import Comment
from app.utils.rate_limit import rate_limit
from app.utils.cache import cache_response

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/posts/{post_id}/like", response_model=LikeResponse)
@rate_limit("30/minute")
async def like_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Like a post"""
    try:
        like_service = LikeService(db)
        notification_service = NotificationService(db)
        
        # Check if post exists
        from sqlalchemy import select
        stmt = select(Post).where(Post.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Check if user can like this post
        if not post.is_public and post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to like this post"
            )
        
        # Create like
        like_data = LikeCreate(
            user_id=current_user.id,
            post_id=post_id,
            like_type=LikeType.POST
        )
        
        like = await like_service.create_like(like_data)
        
        # Send notification to post owner (if not the liker)
        if post.user_id != current_user.id:
            await notification_service.create_like_notification(
                post_id=post_id,
                liker_id=current_user.id,
                post_owner_id=post.user_id
            )
        
        logger.info(f"User {current_user.id} liked post {post_id}")
        
        return LikeResponse(
            id=like.id,
            user_id=like.user_id,
            post_id=like.post_id,
            comment_id=like.comment_id,
            like_type=like.like_type,
            created_at=like.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking post: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to like post"
        )

@router.post("/comments/{comment_id}/like", response_model=LikeResponse)
@rate_limit("30/minute")
async def like_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Like a comment"""
    try:
        like_service = LikeService(db)
        notification_service = NotificationService(db)
        
        # Check if comment exists
        from sqlalchemy import select
        stmt = select(Comment).options(
            selectinload(Comment.post)
        ).where(Comment.id == comment_id)
        
        result = await db.execute(stmt)
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check if user can like this comment (through post visibility)
        if not comment.post.is_public and comment.post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to like this comment"
            )
        
        # Create like
        like_data = LikeCreate(
            user_id=current_user.id,
            comment_id=comment_id,
            like_type=LikeType.COMMENT
        )
        
        like = await like_service.create_like(like_data)
        
        # Send notification to comment author (if not the liker)
        if comment.user_id != current_user.id:
            await notification_service.create_like_notification(
                post_id=comment.post_id,
                liker_id=current_user.id,
                post_owner_id=comment.user_id
            )
        
        logger.info(f"User {current_user.id} liked comment {comment_id}")
        
        return LikeResponse(
            id=like.id,
            user_id=like.user_id,
            post_id=like.post_id,
            comment_id=like.comment_id,
            like_type=like.like_type,
            created_at=like.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to like comment"
        )

@router.delete("/posts/{post_id}/like")
@rate_limit("30/minute")
async def unlike_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unlike a post"""
    try:
        like_service = LikeService(db)
        
        # Check if post exists
        from sqlalchemy import select
        stmt = select(Post).where(Post.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Unlike the post
        deleted = await like_service.delete_like(
            user_id=current_user.id,
            post_id=post_id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Post not liked"
            )
        
        logger.info(f"User {current_user.id} unliked post {post_id}")
        
        return {"message": "Successfully unliked post"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unliking post: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlike post"
        )

@router.delete("/comments/{comment_id}/like")
@rate_limit("30/minute")
async def unlike_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unlike a comment"""
    try:
        like_service = LikeService(db)
        
        # Check if comment exists
        from sqlalchemy import select
        stmt = select(Comment).where(Comment.id == comment_id)
        result = await db.execute(stmt)
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Unlike the comment
        deleted = await like_service.delete_like(
            user_id=current_user.id,
            comment_id=comment_id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comment not liked"
            )
        
        logger.info(f"User {current_user.id} unliked comment {comment_id}")
        
        return {"message": "Successfully unliked comment"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unliking comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlike comment"
        )

@router.get("/posts/{post_id}/likes", response_model=LikeListResponse)
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def get_post_likes(
    post_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get users who liked a post"""
    try:
        like_service = LikeService(db)
        
        # Check if post exists
        from sqlalchemy import select
        stmt = select(Post).where(Post.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Check if user can view likes (through post visibility)
        if not post.is_public:
            if not current_user or (current_user.id != post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view likes on this post"
                )
        
        viewer_id = current_user.id if current_user else None
        
        likes = await like_service.get_post_likes(
            post_id=post_id,
            viewer_id=viewer_id,
            skip=skip,
            limit=limit
        )
        
        total_likes = await like_service.get_post_like_count(post_id)
        
        # Check if current user liked this post
        user_liked = False
        if current_user:
            user_liked = await like_service.has_user_liked(
                user_id=current_user.id,
                post_id=post_id
            )
        
        return LikeListResponse(
            likes=likes,
            total=total_likes,
            skip=skip,
            limit=limit,
            post_id=post_id,
            user_liked=user_liked
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting post likes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get post likes"
        )

@router.get("/comments/{comment_id}/likes", response_model=LikeListResponse)
@rate_limit("60/minute")
@cache_response(60)  # Cache for 60 seconds
async def get_comment_likes(
    comment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get users who liked a comment"""
    try:
        like_service = LikeService(db)
        
        # Check if comment exists
        from sqlalchemy import select
        stmt = select(Comment).options(
            selectinload(Comment.post)
        ).where(Comment.id == comment_id)
        
        result = await db.execute(stmt)
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check if user can view likes (through post visibility)
        if not comment.post.is_public:
            if not current_user or (current_user.id != comment.post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view likes on this comment"
                )
        
        viewer_id = current_user.id if current_user else None
        
        likes = await like_service.get_comment_likes(
            comment_id=comment_id,
            viewer_id=viewer_id,
            skip=skip,
            limit=limit
        )
        
        total_likes = await like_service.get_comment_like_count(comment_id)
        
        # Check if current user liked this comment
        user_liked = False
        if current_user:
            user_liked = await like_service.has_user_liked(
                user_id=current_user.id,
                comment_id=comment_id
            )
        
        return LikeListResponse(
            likes=likes,
            total=total_likes,
            skip=skip,
            limit=limit,
            comment_id=comment_id,
            user_liked=user_liked
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment likes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comment likes"
        )

@router.get("/users/{user_id}/likes", response_model=LikeListResponse)
@rate_limit("60/minute")
@cache_response(120)  # Cache for 2 minutes
async def get_user_likes(
    user_id: int,
    like_type: Optional[LikeType] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get likes by a specific user"""
    try:
        like_service = LikeService(db)
        
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
        
        viewer_id = current_user.id if current_user else None
        
        likes = await like_service.get_user_likes(
            user_id=user_id,
            like_type=like_type,
            viewer_id=viewer_id,
            skip=skip,
            limit=limit
        )
        
        total_likes = await like_service.get_user_like_count(user_id, like_type)
        
        return LikeListResponse(
            likes=likes,
            total=total_likes,
            skip=skip,
            limit=limit,
            user_id=user_id,
            like_type=like_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user likes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user likes"
        )

@router.get("/posts/{post_id}/liked")
@rate_limit("60/minute")
async def check_post_liked(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if current user liked a post"""
    try:
        like_service = LikeService(db)
        
        # Check if post exists
        from sqlalchemy import select
        stmt = select(Post).where(Post.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        liked = await like_service.has_user_liked(
            user_id=current_user.id,
            post_id=post_id
        )
        
        return {"liked": liked}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking if post liked: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check if post liked"
        )

@router.get("/comments/{comment_id}/liked")
@rate_limit("60/minute")
async def check_comment_liked(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Check if current user liked a comment"""
    try:
        like_service = LikeService(db)
        
        # Check if comment exists
        from sqlalchemy import select
        stmt = select(Comment).where(Comment.id == comment_id)
        result = await db.execute(stmt)
        comment = result.scalar_one_or_none()
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        liked = await like_service.has_user_liked(
            user_id=current_user.id,
            comment_id=comment_id
        )
        
        return {"liked": liked}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking if comment liked: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check if comment liked"
        )

@router.get("/posts/{post_id}/likes/stats", response_model=LikeStats)
@rate_limit("60/minute")
@cache_response(120)  # Cache for 2 minutes
async def get_post_like_stats(
    post_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get like statistics for a post"""
    try:
        like_service = LikeService(db)
        
        # Check if post exists
        from sqlalchemy import select
        stmt = select(Post).where(Post.id == post_id)
        result = await db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Check if user can view stats (through post visibility)
        if not post.is_public:
            if not current_user or (current_user.id != post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view stats on this post"
                )
        
        stats = await like_service.get_post_like_stats(post_id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting post like stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get post like stats"
        )

@router.get("/users/{user_id}/likes/stats", response_model=LikeStats)
@rate_limit("60/minute")
@cache_response(300)  # Cache for 5 minutes
async def get_user_like_stats(
    user_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get like statistics for a user"""
    try:
        like_service = LikeService(db)
        
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
        
        stats = await like_service.get_user_like_stats(user_id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user like stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user like stats"
        )

@router.get("/trending/posts")
@rate_limit("60/minute")
@cache_response(300)  # Cache for 5 minutes
async def get_trending_posts(
    time_range: str = Query("day", regex="^(hour|day|week|month)$"),
    limit: int = Query(10, ge=1, le=50),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get trending posts based on likes"""
    try:
        like_service = LikeService(db)
        
        viewer_id = current_user.id if current_user else None
        
        trending_posts = await like_service.get_trending_posts(
            time_range=time_range,
            viewer_id=viewer_id,
            limit=limit
        )
        
        return trending_posts
        
    except Exception as e:
        logger.error(f"Error getting trending posts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get trending posts"
        )

@router.get("/recent")
@rate_limit("60/minute")
@cache_response(30)  # Cache for 30 seconds
async def get_recent_likes(
    like_type: Optional[LikeType] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent likes globally"""
    try:
        like_service = LikeService(db)
        
        viewer_id = current_user.id if current_user else None
        
        recent_likes = await like_service.get_recent_likes(
            like_type=like_type,
            viewer_id=viewer_id,
            limit=limit
        )
        
        return recent_likes
        
    except Exception as e:
        logger.error(f"Error getting recent likes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get recent likes"
        )

@router.post("/batch/like")
@rate_limit("30/minute")
async def batch_like_posts(
    post_ids: List[int],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Like multiple posts at once"""
    try:
        like_service = LikeService(db)
        notification_service = NotificationService(db)
        
        if len(post_ids) > 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot like more than 50 posts at once"
            )
        
        # Remove duplicates
        unique_ids = list(set(post_ids))
        
        if not unique_ids:
            return {"message": "No posts to like", "liked": []}
        
        # Check if posts exist and are accessible
        from sqlalchemy import select
        stmt = select(Post).where(Post.id.in_(unique_ids))
        result = await db.execute(stmt)
        posts = result.scalars().all()
        
        valid_posts = []
        for post in posts:
            if post.is_public or post.user_id == current_user.id:
                valid_posts.append(post)
        
        if not valid_posts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No accessible posts found"
            )
        
        # Like posts
        liked = []
        already_liked = []
        
        for post in valid_posts:
            try:
                # Check if already liked
                existing = await like_service.has_user_liked(
                    user_id=current_user.id,
                    post_id=post.id
                )
                
                if existing:
                    already_liked.append(post.id)
                    continue
                
                # Create like
                like_data = LikeCreate(
                    user_id=current_user.id,
                    post_id=post.id,
                    like_type=LikeType.POST
                )
                
                like = await like_service.create_like(like_data)
                liked.append(post.id)
                
                # Send notification (if not own post)
                if post.user_id != current_user.id:
                    await notification_service.create_like_notification(
                        post_id=post.id,
                        liker_id=current_user.id,
                        post_owner_id=post.user_id
                    )
                
            except Exception as e:
                logger.error(f"Error liking post {post.id}: {e}")
                continue
        
        logger.info(f"User {current_user.id} liked {len(liked)} posts in batch")
        
        return {
            "message": "Batch like completed",
            "liked": liked,
            "already_liked": already_liked
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch like: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to batch like posts"
        )