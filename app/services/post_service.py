from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func
import logging

from app.models.post import Post
from app.models.user import User
from app.models.like import Like
from app.models.follow import Follow
from app.schemas.post_schema import PostCreate, PostUpdate
from app.services.redis_service import RedisService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

class PostService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
        self.search_service = SearchService()
    
    async def create_post(self, user_id: int, post_data: PostCreate) -> Post:
        """Create a new post"""
        post = Post(
            user_id=user_id,
            content=post_data.content,
            media_url=post_data.media_url,
            media_type=post_data.media_type,
            is_public=post_data.is_public,
            location=post_data.location
        )
        
        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)
        
        # Index in Elasticsearch for search
        await self.search_service.index_post(post)
        
        # Invalidate user's feed cache
        await self.redis.delete(f"user:{user_id}:feed")
        
        return post
    
    async def get_post(self, post_id: int) -> Optional[Post]:
        """Get a post by ID"""
        stmt = select(Post).where(Post.id == post_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_post_with_user(self, post_id: int, current_user_id: int) -> Optional[dict]:
        """Get a post with user info and like status"""
        stmt = select(
            Post,
            User.username,
            User.profile_picture,
            func.coalesce(func.count(Like.id), 0).label('like_count'),
            func.exists(
                select(1).where(
                    and_(
                        Like.post_id == Post.id,
                        Like.user_id == current_user_id
                    )
                )
            ).label('liked')
        ).join(
            User, Post.user_id == User.id
        ).outerjoin(
            Like, Post.id == Like.post_id
        ).where(
            Post.id == post_id
        ).group_by(
            Post.id, User.id
        )
        
        result = await self.db.execute(stmt)
        row = result.first()
        
        if not row:
            return None
        
        post_dict = {
            **row.Post.__dict__,
            'user': {
                'username': row.username,
                'profile_picture': row.profile_picture
            },
            'like_count': row.like_count,
            'liked': row.liked
        }
        
        return post_dict
    
    async def get_user_posts(
        self, 
        user_id: int, 
        current_user_id: int, 
        skip: int = 0, 
        limit: int = 20
    ) -> List[dict]:
        """Get posts by a specific user"""
        cache_key = f"user:{user_id}:posts:{skip}:{limit}"
        cached = await self.redis.get(cache_key)
        
        if cached and not cached.get('from_cache', False):
            return cached['data']
        
        # Check if user can see private posts
        can_see_private = user_id == current_user_id
        
        stmt = select(
            Post,
            User.username,
            User.profile_picture,
            func.coalesce(func.count(Like.id), 0).label('like_count'),
            func.exists(
                select(1).where(
                    and_(
                        Like.post_id == Post.id,
                        Like.user_id == current_user_id
                    )
                )
            ).label('liked')
        ).join(
            User, Post.user_id == User.id
        ).outerjoin(
            Like, Post.id == Like.post_id
        ).where(
            Post.user_id == user_id
        )
        
        if not can_see_private:
            stmt = stmt.where(Post.is_public == True)
        
        stmt = stmt.group_by(
            Post.id, User.id
        ).order_by(
            desc(Post.created_at)
        ).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        posts = []
        for row in rows:
            post_dict = {
                **row.Post.__dict__,
                'user': {
                    'username': row.username,
                    'profile_picture': row.profile_picture
                },
                'like_count': row.like_count,
                'liked': row.liked
            }
            posts.append(post_dict)
        
        # Cache for 5 minutes
        await self.redis.setex(cache_key, 300, {'data': posts, 'from_cache': True})
        
        return posts
    
    async def get_feed_posts(
        self, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 20
    ) -> List[dict]:
        """Get feed posts for a user (posts from followed users + own posts)"""
        cache_key = f"user:{user_id}:feed:{skip}:{limit}"
        cached = await self.redis.get(cache_key)
        
        if cached and not cached.get('from_cache', False):
            return cached['data']
        
        # Get users that current user follows
        following_stmt = select(Follow.following_id).where(
            Follow.follower_id == user_id
        )
        following_result = await self.db.execute(following_stmt)
        following_ids = [row[0] for row in following_result]
        
        # Include current user's own posts
        following_ids.append(user_id)
        
        stmt = select(
            Post,
            User.username,
            User.profile_picture,
            func.coalesce(func.count(Like.id), 0).label('like_count'),
            func.exists(
                select(1).where(
                    and_(
                        Like.post_id == Post.id,
                        Like.user_id == user_id
                    )
                )
            ).label('liked')
        ).join(
            User, Post.user_id == User.id
        ).outerjoin(
            Like, Post.id == Like.post_id
        ).where(
            Post.user_id.in_(following_ids),
            Post.is_public == True
        ).group_by(
            Post.id, User.id
        ).order_by(
            desc(Post.created_at)
        ).offset(skip).limit(limit)
        
        result = await self.db.execute(stmt)
        rows = result.all()
        
        posts = []
        for row in rows:
            post_dict = {
                **row.Post.__dict__,
                'user': {
                    'username': row.username,
                    'profile_picture': row.profile_picture
                },
                'like_count': row.like_count,
                'liked': row.liked
            }
            posts.append(post_dict)
        
        # Cache for 1 minute (feed updates frequently)
        await self.redis.setex(cache_key, 60, {'data': posts, 'from_cache': True})
        
        return posts
    
    async def update_post(self, post_id: int, post_update: PostUpdate) -> Post:
        """Update a post"""
        stmt = select(Post).where(Post.id == post_id)
        result = await self.db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise ValueError("Post not found")
        
        update_data = post_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(post, field, value)
        
        await self.db.commit()
        await self.db.refresh(post)
        
        # Update Elasticsearch index
        await self.search_service.update_post(post)
        
        # Invalidate cache
        await self.redis.delete_pattern(f"*post:{post_id}*")
        await self.redis.delete_pattern(f"user:{post.user_id}:*")
        
        return post
    
    async def delete_post(self, post_id: int) -> None:
        """Delete a post"""
        stmt = select(Post).where(Post.id == post_id)
        result = await self.db.execute(stmt)
        post = result.scalar_one_or_none()
        
        if not post:
            raise ValueError("Post not found")
        
        # Get user_id for cache invalidation
        user_id = post.user_id
        
        await self.db.delete(post)
        await self.db.commit()
        
        # Remove from Elasticsearch
        await self.search_service.delete_post(post_id)
        
        # Invalidate cache
        await self.redis.delete_pattern(f"*post:{post_id}*")
        await self.redis.delete_pattern(f"user:{user_id}:*")
    
    async def search_posts(self, query: str, skip: int = 0, limit: int = 20) -> List[Post]:
        """Search posts using Elasticsearch"""
        results = await self.search_service.search_posts(query, skip, limit)
        
        if not results:
            return []
        
        # Get posts from database
        post_ids = [hit['_id'] for hit in results]
        stmt = select(Post).where(Post.id.in_(post_ids)).order_by(
            desc(Post.created_at)
        )
        result = await self.db.execute(stmt)
        posts = result.scalars().all()
        
        return posts