from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from app.schemas.comment_schema import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentListResponse,
    CommentTreeResponse,
    CommentStats
)
from app.services.comment_service import CommentService
from app.services.auth_service import get_current_user
from app.services.notification_service import NotificationService
from app.db.session import get_db
from app.models.user import User
from app.models.post import Post
from app.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/posts/{post_id}/comments", response_model=CommentResponse)
@rate_limit("10/minute")
async def create_comment(
    post_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new comment on a post"""
    try:
        comment_service = CommentService(db)
        
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
        
        # Check if user can comment on this post
        if not post.is_public and post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to comment on this post"
            )
        
        # Create the comment
        comment = await comment_service.create_comment(
            post_id=post_id,
            user_id=current_user.id,
            comment_data=comment_data
        )
        
        # Send notification to post owner (if not the commenter)
        if post.user_id != current_user.id:
            notification_service = NotificationService(db)
            await notification_service.create_comment_notification(
                comment_id=comment.id,
                commenter_id=current_user.id,
                post_id=post_id,
                post_owner_id=post.user_id,
                parent_comment_id=comment_data.parent_id
            )
        
        # If this is a reply to another comment, notify that comment's author
        if comment_data.parent_id:
            parent_comment = await comment_service.get_comment(comment_data.parent_id)
            if parent_comment and parent_comment.user_id != current_user.id:
                await notification_service.create_comment_notification(
                    comment_id=comment.id,
                    commenter_id=current_user.id,
                    post_id=post_id,
                    post_owner_id=parent_comment.user_id,
                    parent_comment_id=comment_data.parent_id
                )
        
        logger.info(f"User {current_user.id} created comment {comment.id} on post {post_id}")
        
        return comment
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create comment"
        )

@router.get("/posts/{post_id}/comments", response_model=CommentListResponse)
@rate_limit("60/minute")
async def get_post_comments(
    post_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("newest", regex="^(newest|oldest|popular)$"),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comments for a post"""
    try:
        comment_service = CommentService(db)
        
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
        
        # Check if user can view comments on this post
        if not post.is_public:
            if not current_user or (current_user.id != post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view comments on this post"
                )
        
        user_id = current_user.id if current_user else None
        
        comments = await comment_service.get_post_comments(
            post_id=post_id,
            user_id=user_id,
            skip=skip,
            limit=limit,
            sort_by=sort_by
        )
        
        total_comments = await comment_service.get_post_comment_count(post_id)
        
        return CommentListResponse(
            comments=comments,
            total=total_comments,
            skip=skip,
            limit=limit,
            post_id=post_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting post comments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comments"
        )

@router.get("/posts/{post_id}/comments/tree", response_model=List[CommentTreeResponse])
@rate_limit("60/minute")
async def get_comment_tree(
    post_id: int,
    max_depth: int = Query(5, ge=1, le=10),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comments in tree structure (nested replies)"""
    try:
        comment_service = CommentService(db)
        
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
        
        # Check if user can view comments
        if not post.is_public:
            if not current_user or (current_user.id != post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view comments on this post"
                )
        
        user_id = current_user.id if current_user else None
        
        comments = await comment_service.get_comment_tree(
            post_id=post_id,
            user_id=user_id,
            max_depth=max_depth
        )
        
        return comments
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment tree: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comment tree"
        )

@router.get("/comments/{comment_id}", response_model=CommentResponse)
@rate_limit("60/minute")
async def get_comment(
    comment_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific comment by ID"""
    try:
        comment_service = CommentService(db)
        
        user_id = current_user.id if current_user else None
        comment = await comment_service.get_comment_with_user(
            comment_id=comment_id,
            user_id=user_id
        )
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check if user can view this comment (through post visibility)
        if not comment.post.is_public:
            if not current_user or (current_user.id != comment.post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view this comment"
                )
        
        return comment
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comment"
        )

@router.get("/comments/{comment_id}/replies", response_model=List[CommentResponse])
@rate_limit("60/minute")
async def get_comment_replies(
    comment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get replies to a specific comment"""
    try:
        comment_service = CommentService(db)
        
        user_id = current_user.id if current_user else None
        replies = await comment_service.get_comment_replies(
            comment_id=comment_id,
            user_id=user_id,
            skip=skip,
            limit=limit
        )
        
        # Check if parent comment exists
        parent_comment = await comment_service.get_comment(comment_id)
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check if user can view replies (through post visibility)
        if not parent_comment.post.is_public:
            if not current_user or (current_user.id != parent_comment.post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view these replies"
                )
        
        return replies
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment replies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comment replies"
        )

@router.put("/comments/{comment_id}", response_model=CommentResponse)
@rate_limit("30/minute")
async def update_comment(
    comment_id: int,
    comment_update: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a comment"""
    try:
        comment_service = CommentService(db)
        
        # Check if comment exists and user owns it
        comment = await comment_service.get_comment(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        if comment.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this comment"
            )
        
        # Update the comment
        updated_comment = await comment_service.update_comment(
            comment_id=comment_id,
            comment_update=comment_update
        )
        
        logger.info(f"User {current_user.id} updated comment {comment_id}")
        
        return updated_comment
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update comment"
        )

@router.delete("/comments/{comment_id}")
@rate_limit("30/minute")
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a comment"""
    try:
        comment_service = CommentService(db)
        
        # Check if comment exists
        comment = await comment_service.get_comment_with_post(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check permissions (user owns comment OR user owns post)
        if comment.user_id != current_user.id and comment.post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this comment"
            )
        
        # Delete the comment
        await comment_service.delete_comment(
            comment_id=comment_id,
            user_id=current_user.id
        )
        
        logger.info(f"User {current_user.id} deleted comment {comment_id}")
        
        return {"message": "Comment deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete comment"
        )

@router.post("/comments/{comment_id}/like")
@rate_limit("30/minute")
async def like_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Like a comment"""
    try:
        comment_service = CommentService(db)
        
        # Check if comment exists
        comment = await comment_service.get_comment(comment_id)
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
        
        # Like the comment
        liked = await comment_service.like_comment(
            comment_id=comment_id,
            user_id=current_user.id
        )
        
        if not liked:
            return {"message": "Comment already liked"}
        
        # Send notification to comment author (if not the liker)
        if comment.user_id != current_user.id:
            notification_service = NotificationService(db)
            await notification_service.create_like_notification(
                post_id=comment.post_id,
                liker_id=current_user.id,
                post_owner_id=comment.user_id
            )
        
        logger.info(f"User {current_user.id} liked comment {comment_id}")
        
        return {"message": "Comment liked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error liking comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to like comment"
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
        comment_service = CommentService(db)
        
        # Check if comment exists
        comment = await comment_service.get_comment(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Unlike the comment
        unliked = await comment_service.unlike_comment(
            comment_id=comment_id,
            user_id=current_user.id
        )
        
        if not unliked:
            return {"message": "Comment not liked"}
        
        logger.info(f"User {current_user.id} unliked comment {comment_id}")
        
        return {"message": "Comment unliked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unliking comment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlike comment"
        )

@router.get("/users/{user_id}/comments", response_model=CommentListResponse)
@rate_limit("60/minute")
async def get_user_comments(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all comments by a specific user"""
    try:
        comment_service = CommentService(db)
        
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
        
        requester_id = current_user.id if current_user else None
        
        comments = await comment_service.get_user_comments(
            user_id=user_id,
            requester_id=requester_id,
            skip=skip,
            limit=limit
        )
        
        total_comments = await comment_service.get_user_comment_count(user_id)
        
        return CommentListResponse(
            comments=comments,
            total=total_comments,
            skip=skip,
            limit=limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user comments: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user comments"
        )

@router.get("/comments/stats/{comment_id}", response_model=CommentStats)
@rate_limit("60/minute")
async def get_comment_stats(
    comment_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get statistics for a comment"""
    try:
        comment_service = CommentService(db)
        
        # Check if comment exists
        comment = await comment_service.get_comment(comment_id)
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check if user can view stats (through post visibility)
        if not comment.post.is_public:
            if not current_user or (current_user.id != comment.post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view these stats"
                )
        
        stats = await comment_service.get_comment_stats(comment_id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting comment stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get comment stats"
        )

@router.get("/posts/{post_id}/comments/stats")
@rate_limit("60/minute")
async def get_post_comment_stats(
    post_id: int,
    current_user: Optional[User] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comment statistics for a post"""
    try:
        comment_service = CommentService(db)
        
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
        
        # Check if user can view stats
        if not post.is_public:
            if not current_user or (current_user.id != post.user_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view these stats"
                )
        
        stats = await comment_service.get_post_comment_stats(post_id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting post comment stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get post comment stats"
        )