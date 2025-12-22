from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pathlib import Path
from app.schemas.post_schema import PostCreate, PostUpdate, PostInDB, PostWithUser
from app.services.post_service import PostService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.utils.file_upload import save_upload_file
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=PostInDB)
async def create_post(
    content: str = Query(...),
    is_public: bool = Query(True),
    location: Optional[str] = Query(None),
    media: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new post"""
    try:
        post_service = PostService(db)
        
        media_url = None
        media_type = None
        
        if media:
            # Save uploaded file
            media_path = await save_upload_file(media)
            media_url = str(media_path)
            media_type = media.content_type.split('/')[0]  # image, video, etc.
        
        post_data = PostCreate(
            content=content,
            media_url=media_url,
            media_type=media_type,
            is_public=is_public,
            location=location
        )
        
        post = await post_service.create_post(current_user.id, post_data)
        return post
    except Exception as e:
        logger.error(f"Create post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create post"
        )

@router.get("/{post_id}", response_model=PostWithUser)
async def get_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a post by ID"""
    try:
        post_service = PostService(db)
        post = await post_service.get_post_with_user(post_id, current_user.id)
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Check if user can view post
        if not post.is_public and post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this post"
            )
        
        return post
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get post"
        )

@router.get("/", response_model=List[PostWithUser])
async def get_posts(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get posts with pagination"""
    try:
        post_service = PostService(db)
        
        if user_id:
            # Get user's posts
            posts = await post_service.get_user_posts(
                user_id, current_user.id, skip, limit
            )
        else:
            # Get feed posts
            posts = await post_service.get_feed_posts(
                current_user.id, skip, limit
            )
        
        return posts
    except Exception as e:
        logger.error(f"Get posts error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get posts"
        )

@router.put("/{post_id}", response_model=PostInDB)
async def update_post(
    post_id: int,
    post_update: PostUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a post"""
    try:
        post_service = PostService(db)
        
        # Check if post exists and user owns it
        post = await post_service.get_post(post_id)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        if post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this post"
            )
        
        updated_post = await post_service.update_post(post_id, post_update)
        return updated_post
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update post"
        )

@router.delete("/{post_id}")
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a post"""
    try:
        post_service = PostService(db)
        
        # Check if post exists and user owns it
        post = await post_service.get_post(post_id)
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        if post.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this post"
            )
        
        await post_service.delete_post(post_id)
        return {"message": "Post deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete post"
        )