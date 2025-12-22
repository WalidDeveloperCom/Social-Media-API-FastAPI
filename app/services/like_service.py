from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func, text, case
from sqlalchemy.orm import selectinload, joinedload
import logging
import json
from datetime import datetime, timedelta

from app.models.like import Like
from app.models.user import User
from app.models.post import Post
from app.models.comment import Comment
from app.schemas.like_schema import (
    LikeCreate,
    LikeResponse,
    LikeStats,
    LikeType
)
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

class LikeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
    
    async def create_like(self, like_data: LikeCreate) -> Like:
        """Create a new like"""
        try:
            # Validate like data
            if like_data.post_id and like_data.comment_id:
                raise ValueError("Cannot like both post and comment at once")
            
            if not like_data.post_id and not like_data.comment_id:
                raise ValueError("Must like either a post or comment")
            
            # Check if already liked
            existing = await self._get_existing_like(
                user_id=like_data.user_id,
                post_id=like_data.post_id,
                comment_id=like_data.comment_id
            )
            
            if existing:
                raise ValueError("Already liked")
            
            # Create like
            like = Like(
                user_id=like_data.user_id,
                post_id=like_data.post_id,
                comment_id=like_data.comment_id,
                like_type=like_data.like_type.value if like_data.like_type else None
            )
            
            self.db.add(like)
            await self.db.commit()
            await self.db.refresh(like)
            
            # Update like count
            await self._update_like_count(
                post_id=like_data.post_id,
                comment_id=like_data.comment_id,
                increment=True
            )
            
            # Update cache
            await self._update_like_cache(
                user_id=like_data.user_id,
                post_id=like_data.post_id,
                comment_id=like_data.comment_id,
                action="like"
            )
            
            logger.info(f"Created like: user={like_data.user_id}, post={like_data.post_id}, comment={like_data.comment_id}")
            
            return like
            
        except Exception as e:
            logger.error(f"Error creating like: {e}")
            await self.db.rollback()
            raise
    
    async def delete_like(
        self,
        user_id: int,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None
    ) -> bool:
        """Delete a like"""
        try:
            # Validate input
            if post_id and comment_id:
                raise ValueError("Cannot specify both post_id and comment_id")
            
            if not post_id and not comment_id:
                raise ValueError("Must specify either post_id or comment_id")
            
            # Find the like
            conditions = [Like.user_id == user_id]
            if post_id:
                conditions.append(Like.post_id == post_id)
            if comment_id:
                conditions.append(Like.comment_id == comment_id)
            
            stmt = select(Like).where(and_(*conditions))
            result = await self.db.execute(stmt)
            like = result.scalar_one_or_none()
            
            if not like:
                return False
            
            await self.db.delete(like)
            await self.db.commit()
            
            # Update like count
            await self._update_like_count(
                post_id=post_id,
                comment_id=comment_id,
                increment=False
            )
            
            # Update cache
            await self._update_like_cache(
                user_id=user_id,
                post_id=post_id,
                comment_id=comment_id,
                action="unlike"
            )
            
            logger.info(f"Deleted like: user={user_id}, post={post_id}, comment={comment_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting like: {e}")
            await self.db.rollback()
            return False
    
    async def _get_existing_like(
        self,
        user_id: int,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None
    ) -> Optional[Like]:
        """Check if like already exists"""
        try:
            conditions = [Like.user_id == user_id]
            if post_id:
                conditions.append(Like.post_id == post_id)
            if comment_id:
                conditions.append(Like.comment_id == comment_id)
            
            stmt = select(Like).where(and_(*conditions))
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error checking existing like: {e}")
            return None
    
    async def has_user_liked(
        self,
        user_id: int,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None
    ) -> bool:
        """Check if user has liked a post or comment"""
        try:
            if post_id:
                cache_key = f"like:user:{user_id}:post:{post_id}"
            elif comment_id:
                cache_key = f"like:user:{user_id}:comment:{comment_id}"
            else:
                return False
            
            cached = await self.redis.get(cache_key)
            if cached is not None:
                return cached == "1"
            
            existing = await self._get_existing_like(
                user_id=user_id,
                post_id=post_id,
                comment_id=comment_id
            )
            
            liked = existing is not None
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, "1" if liked else "0")
            
            return liked
            
        except Exception as e:
            logger.error(f"Error checking if user liked: {e}")
            return False
    
    async def get_post_likes(
        self,
        post_id: int,
        viewer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get users who liked a post"""
        try:
            cache_key = f"post:{post_id}:likes:{skip}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build query
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                Like.created_at.label('liked_at'),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == viewer_id,
                            Follow.following_id == User.id
                        )
                    )
                ).label('you_follow') if viewer_id else False,
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == User.id,
                            Follow.following_id == viewer_id
                        )
                    )
                ).label('follows_you') if viewer_id else False
            ).join(
                Like, Like.user_id == User.id
            ).outerjoin(
                Follow, and_(
                    Follow.follower_id == viewer_id if viewer_id else False,
                    Follow.following_id == User.id
                )
            ).where(
                and_(
                    Like.post_id == post_id,
                    User.is_active == True
                )
            ).order_by(
                desc(Like.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            likes = []
            for row in rows:
                like_info = {
                    "user": {
                        "id": row.id,
                        "username": row.username,
                        "full_name": row.full_name,
                        "profile_picture": row.profile_picture
                    },
                    "liked_at": row.liked_at.isoformat(),
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you
                }
                likes.append(like_info)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, json.dumps(likes))
            
            return likes
            
        except Exception as e:
            logger.error(f"Error getting post likes: {e}")
            return []
    
    async def get_comment_likes(
        self,
        comment_id: int,
        viewer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get users who liked a comment"""
        try:
            cache_key = f"comment:{comment_id}:likes:{skip}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build query
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                Like.created_at.label('liked_at'),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == viewer_id,
                            Follow.following_id == User.id
                        )
                    )
                ).label('you_follow') if viewer_id else False,
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == User.id,
                            Follow.following_id == viewer_id
                        )
                    )
                ).label('follows_you') if viewer_id else False
            ).join(
                Like, Like.user_id == User.id
            ).outerjoin(
                Follow, and_(
                    Follow.follower_id == viewer_id if viewer_id else False,
                    Follow.following_id == User.id
                )
            ).where(
                and_(
                    Like.comment_id == comment_id,
                    User.is_active == True
                )
            ).order_by(
                desc(Like.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            likes = []
            for row in rows:
                like_info = {
                    "user": {
                        "id": row.id,
                        "username": row.username,
                        "full_name": row.full_name,
                        "profile_picture": row.profile_picture
                    },
                    "liked_at": row.liked_at.isoformat(),
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you
                }
                likes.append(like_info)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, json.dumps(likes))
            
            return likes
            
        except Exception as e:
            logger.error(f"Error getting comment likes: {e}")
            return []
    
    async def get_user_likes(
        self,
        user_id: int,
        like_type: Optional[LikeType] = None,
        viewer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get likes by a specific user"""
        try:
            cache_key = f"user:{user_id}:likes:{like_type}:{skip}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build base query
            stmt = select(
                Like.id,
                Like.post_id,
                Like.comment_id,
                Like.like_type,
                Like.created_at.label('liked_at'),
                case(
                    (Like.post_id.is_not(None), Post.content),
                    (Like.comment_id.is_not(None), Comment.content),
                    else_=None
                ).label('content'),
                case(
                    (Like.post_id.is_not(None), Post.user_id),
                    (Like.comment_id.is_not(None), Comment.user_id),
                    else_=None
                ).label('content_owner_id')
            ).outerjoin(
                Post, Like.post_id == Post.id
            ).outerjoin(
                Comment, Like.comment_id == Comment.id
            ).where(
                Like.user_id == user_id
            )
            
            # Filter by like type
            if like_type == LikeType.POST:
                stmt = stmt.where(Like.post_id.is_not(None))
            elif like_type == LikeType.COMMENT:
                stmt = stmt.where(Like.comment_id.is_not(None))
            
            # Apply sorting and pagination
            stmt = stmt.order_by(
                desc(Like.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            # Get user info for content owners
            likes = []
            for row in rows:
                like_info = {
                    "id": row.id,
                    "post_id": row.post_id,
                    "comment_id": row.comment_id,
                    "like_type": row.like_type,
                    "liked_at": row.liked_at.isoformat(),
                    "content_preview": (row.content[:100] + '...') if row.content and len(row.content) > 100 else row.content
                }
                
                # Get content owner info if viewer can see it
                if row.content_owner_id and viewer_id:
                    # Check if content is accessible
                    accessible = await self._is_content_accessible(
                        viewer_id=viewer_id,
                        post_id=row.post_id,
                        comment_id=row.comment_id
                    )
                    
                    if accessible:
                        owner_stmt = select(
                            User.id,
                            User.username,
                            User.profile_picture
                        ).where(User.id == row.content_owner_id)
                        
                        owner_result = await self.db.execute(owner_stmt)
                        owner = owner_result.first()
                        
                        if owner:
                            like_info["content_owner"] = {
                                "id": owner.id,
                                "username": owner.username,
                                "profile_picture": owner.profile_picture
                            }
                
                likes.append(like_info)
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(likes))
            
            return likes
            
        except Exception as e:
            logger.error(f"Error getting user likes: {e}")
            return []
    
    async def _is_content_accessible(
        self,
        viewer_id: int,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None
    ) -> bool:
        """Check if content is accessible to viewer"""
        try:
            if post_id:
                # Check post accessibility
                stmt = select(Post).where(Post.id == post_id)
                result = await self.db.execute(stmt)
                post = result.scalar_one_or_none()
                
                if not post:
                    return False
                
                return post.is_public or post.user_id == viewer_id
            
            elif comment_id:
                # Check comment accessibility through post
                stmt = select(Comment).options(
                    selectinload(Comment.post)
                ).where(Comment.id == comment_id)
                
                result = await self.db.execute(stmt)
                comment = result.scalar_one_or_none()
                
                if not comment or not comment.post:
                    return False
                
                return comment.post.is_public or comment.post.user_id == viewer_id
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking content accessibility: {e}")
            return False
    
    async def get_post_like_count(self, post_id: int) -> int:
        """Get number of likes for a post"""
        try:
            cache_key = f"post:{post_id}:like_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                and_(
                    Like.post_id == post_id,
                    Like.comment_id.is_(None)
                )
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting post like count: {e}")
            return 0
    
    async def get_comment_like_count(self, comment_id: int) -> int:
        """Get number of likes for a comment"""
        try:
            cache_key = f"comment:{comment_id}:like_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                Like.comment_id == comment_id
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting comment like count: {e}")
            return 0
    
    async def get_user_like_count(
        self,
        user_id: int,
        like_type: Optional[LikeType] = None
    ) -> int:
        """Get number of likes by a user"""
        try:
            cache_key = f"user:{user_id}:like_count:{like_type}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            conditions = [Like.user_id == user_id]
            
            if like_type == LikeType.POST:
                conditions.append(Like.post_id.is_not(None))
            elif like_type == LikeType.COMMENT:
                conditions.append(Like.comment_id.is_not(None))
            
            stmt = select(func.count()).where(and_(*conditions))
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting user like count: {e}")
            return 0
    
    async def get_post_like_stats(self, post_id: int) -> LikeStats:
        """Get like statistics for a post"""
        try:
            cache_key = f"post:{post_id}:like_stats"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return LikeStats(**json.loads(cached))
            
            # Get total likes
            total_likes = await self.get_post_like_count(post_id)
            
            # Get likes by time period
            now = datetime.utcnow()
            time_periods = {
                "last_hour": now - timedelta(hours=1),
                "last_24h": now - timedelta(days=1),
                "last_week": now - timedelta(days=7),
                "last_month": now - timedelta(days=30)
            }
            
            likes_by_period = {}
            for period_name, period_start in time_periods.items():
                stmt = select(func.count()).where(
                    and_(
                        Like.post_id == post_id,
                        Like.created_at >= period_start
                    )
                )
                
                result = await self.db.execute(stmt)
                count = result.scalar() or 0
                likes_by_period[period_name] = count
            
            # Get top likers (users who liked this post and have most followers)
            top_likers_stmt = select(
                User.id,
                User.username,
                User.profile_picture,
                func.count(Follow.id).label('follower_count')
            ).join(
                Like, Like.user_id == User.id
            ).outerjoin(
                Follow, Follow.following_id == User.id
            ).where(
                and_(
                    Like.post_id == post_id,
                    User.is_active == True
                )
            ).group_by(
                User.id
            ).order_by(
                desc('follower_count')
            ).limit(5)
            
            top_likers_result = await self.db.execute(top_likers_stmt)
            top_likers = [
                {
                    "id": row.id,
                    "username": row.username,
                    "profile_picture": row.profile_picture,
                    "follower_count": row.follower_count
                }
                for row in top_likers_result.all()
            ]
            
            # Get like timeline (last 7 days)
            timeline = {}
            for i in range(7):
                date = (now - timedelta(days=i)).date()
                day_start = datetime.combine(date, datetime.min.time())
                day_end = datetime.combine(date, datetime.max.time())
                
                day_stmt = select(func.count()).where(
                    and_(
                        Like.post_id == post_id,
                        Like.created_at >= day_start,
                        Like.created_at <= day_end
                    )
                )
                
                day_result = await self.db.execute(day_stmt)
                count = day_result.scalar() or 0
                timeline[date.isoformat()] = count
            
            stats = LikeStats(
                post_id=post_id,
                total_likes=total_likes,
                likes_by_period=likes_by_period,
                top_likers=top_likers,
                like_timeline=timeline
            )
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(stats.dict()))
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting post like stats: {e}")
            return LikeStats(
                post_id=post_id,
                total_likes=0,
                likes_by_period={},
                top_likers=[],
                like_timeline={}
            )
    
    async def get_user_like_stats(self, user_id: int) -> LikeStats:
        """Get like statistics for a user"""
        try:
            cache_key = f"user:{user_id}:like_stats"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return LikeStats(**json.loads(cached))
            
            # Get counts by type
            post_likes = await self.get_user_like_count(user_id, LikeType.POST)
            comment_likes = await self.get_user_like_count(user_id, LikeType.COMMENT)
            total_likes = post_likes + comment_likes
            
            # Get recent likes (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            
            recent_stmt = select(func.count()).where(
                and_(
                    Like.user_id == user_id,
                    Like.created_at >= week_ago
                )
            )
            
            recent_result = await self.db.execute(recent_stmt)
            recent_likes = recent_result.scalar() or 0
            
            # Get most liked content types
            content_types_stmt = select(
                case(
                    (Like.post_id.is_not(None), 'post'),
                    (Like.comment_id.is_not(None), 'comment'),
                    else_='unknown'
                ).label('content_type'),
                func.count().label('count')
            ).where(
                Like.user_id == user_id
            ).group_by('content_type')
            
            content_types_result = await self.db.execute(content_types_stmt)
            content_type_distribution = {
                row.content_type: row.count
                for row in content_types_result.all()
            }
            
            # Get top liked posts/comments
            top_liked_stmt = select(
                Post.id,
                Post.content,
                func.count(Like.id).label('like_count')
            ).join(
                Like, Like.post_id == Post.id
            ).where(
                Like.user_id == user_id
            ).group_by(
                Post.id
            ).order_by(
                desc('like_count')
            ).limit(5)
            
            top_liked_result = await self.db.execute(top_liked_stmt)
            top_liked_content = [
                {
                    "id": row.id,
                    "content": row.content[:100] + '...' if len(row.content) > 100 else row.content,
                    "like_count": row.like_count
                }
                for row in top_liked_result.all()
            ]
            
            stats = LikeStats(
                user_id=user_id,
                total_likes=total_likes,
                post_likes=post_likes,
                comment_likes=comment_likes,
                recent_likes=recent_likes,
                content_type_distribution=content_type_distribution,
                top_liked_content=top_liked_content
            )
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(stats.dict()))
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user like stats: {e}")
            return LikeStats(
                user_id=user_id,
                total_likes=0,
                post_likes=0,
                comment_likes=0,
                recent_likes=0,
                content_type_distribution={},
                top_liked_content=[]
            )
    
    async def get_trending_posts(
        self,
        time_range: str = "day",
        viewer_id: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get trending posts based on likes"""
        try:
            cache_key = f"trending_posts:{time_range}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Calculate time range
            now = datetime.utcnow()
            if time_range == "hour":
                start_time = now - timedelta(hours=1)
            elif time_range == "day":
                start_time = now - timedelta(days=1)
            elif time_range == "week":
                start_time = now - timedelta(days=7)
            elif time_range == "month":
                start_time = now - timedelta(days=30)
            else:
                start_time = now - timedelta(days=1)
            
            # Build trending query
            stmt = select(
                Post.id,
                Post.content,
                Post.user_id,
                Post.media_url,
                Post.created_at,
                func.count(Like.id).label('like_count'),
                func.count(
                    case(
                        (Like.created_at >= start_time, 1),
                        else_=None
                    )
                ).label('recent_likes'),
                User.username,
                User.profile_picture,
                func.exists(
                    select(1).where(
                        and_(
                            Like.user_id == viewer_id,
                            Like.post_id == Post.id
                        )
                    )
                ).label('user_liked') if viewer_id else False
            ).join(
                Like, Like.post_id == Post.id
            ).join(
                User, Post.user_id == User.id
            ).where(
                and_(
                    Post.is_public == True,
                    Like.created_at >= start_time,
                    User.is_active == True
                )
            ).group_by(
                Post.id, User.id
            ).order_by(
                desc('recent_likes'),
                desc(Post.created_at)
            ).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            trending_posts = []
            for row in rows:
                post = {
                    "id": row.id,
                    "content": row.content[:200] + '...' if len(row.content) > 200 else row.content,
                    "media_url": row.media_url,
                    "created_at": row.created_at.isoformat(),
                    "like_count": row.like_count,
                    "recent_likes": row.recent_likes,
                    "author": {
                        "id": row.user_id,
                        "username": row.username,
                        "profile_picture": row.profile_picture
                    },
                    "user_liked": row.user_liked
                }
                trending_posts.append(post)
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(trending_posts))
            
            return trending_posts
            
        except Exception as e:
            logger.error(f"Error getting trending posts: {e}")
            return []
    
    async def get_recent_likes(
        self,
        like_type: Optional[LikeType] = None,
        viewer_id: Optional[int] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent likes globally"""
        try:
            cache_key = f"recent_likes:{like_type}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build query
            stmt = select(
                Like.id,
                Like.post_id,
                Like.comment_id,
                Like.like_type,
                Like.created_at,
                User.id.label('liker_id'),
                User.username.label('liker_username'),
                User.profile_picture.label('liker_profile_picture'),
                case(
                    (Like.post_id.is_not(None), Post.content),
                    (Like.comment_id.is_not(None), Comment.content),
                    else_=None
                ).label('content'),
                case(
                    (Like.post_id.is_not(None), Post.user_id),
                    (Like.comment_id.is_not(None), Comment.user_id),
                    else_=None
                ).label('content_owner_id')
            ).join(
                User, Like.user_id == User.id
            ).outerjoin(
                Post, Like.post_id == Post.id
            ).outerjoin(
                Comment, Like.comment_id == Comment.id
            ).where(
                User.is_active == True
            )
            
            # Filter by like type
            if like_type == LikeType.POST:
                stmt = stmt.where(Like.post_id.is_not(None))
            elif like_type == LikeType.COMMENT:
                stmt = stmt.where(Like.comment_id.is_not(None))
            
            # Apply sorting and limit
            stmt = stmt.order_by(
                desc(Like.created_at)
            ).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            recent_likes = []
            for row in rows:
                like_info = {
                    "id": row.id,
                    "post_id": row.post_id,
                    "comment_id": row.comment_id,
                    "like_type": row.like_type,
                    "created_at": row.created_at.isoformat(),
                    "liker": {
                        "id": row.liker_id,
                        "username": row.liker_username,
                        "profile_picture": row.liker_profile_picture
                    },
                    "content_preview": (row.content[:100] + '...') if row.content and len(row.content) > 100 else row.content
                }
                
                recent_likes.append(like_info)
            
            # Cache for 30 seconds
            await self.redis.setex(cache_key, 30, json.dumps(recent_likes))
            
            return recent_likes
            
        except Exception as e:
            logger.error(f"Error getting recent likes: {e}")
            return []
    
    async def _update_like_count(
        self,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None,
        increment: bool = True
    ):
        """Update like count for post or comment"""
        try:
            if post_id:
                # Update post like count
                from sqlalchemy import update as sql_update
                
                if increment:
                    update_stmt = sql_update(Post).where(
                        Post.id == post_id
                    ).values(
                        like_count=Post.like_count + 1
                    )
                else:
                    update_stmt = sql_update(Post).where(
                        Post.id == post_id
                    ).values(
                        like_count=Post.like_count - 1
                    )
                
                await self.db.execute(update_stmt)
                await self.db.commit()
                
                # Invalidate post cache
                await self.redis.delete_pattern(f"*post:{post_id}*")
                
            elif comment_id:
                # Update comment like count
                from sqlalchemy import update as sql_update
                
                if increment:
                    update_stmt = sql_update(Comment).where(
                        Comment.id == comment_id
                    ).values(
                        like_count=Comment.like_count + 1
                    )
                else:
                    update_stmt = sql_update(Comment).where(
                        Comment.id == comment_id
                    ).values(
                        like_count=Comment.like_count - 1
                    )
                
                await self.db.execute(update_stmt)
                await self.db.commit()
                
                # Invalidate comment cache
                await self.redis.delete_pattern(f"*comment:{comment_id}*")
            
        except Exception as e:
            logger.error(f"Error updating like count: {e}")
    
    async def _update_like_cache(
        self,
        user_id: int,
        post_id: Optional[int] = None,
        comment_id: Optional[int] = None,
        action: str = "like"
    ):
        """Update cache after like/unlike action"""
        try:
            if post_id:
                # Update post-specific caches
                await self.redis.delete(f"like:user:{user_id}:post:{post_id}")
                await self.redis.delete_pattern(f"post:{post_id}:likes:*")
                await self.redis.delete(f"post:{post_id}:like_count")
                await self.redis.delete(f"post:{post_id}:like_stats")
                
            elif comment_id:
                # Update comment-specific caches
                await self.redis.delete(f"like:user:{user_id}:comment:{comment_id}")
                await self.redis.delete_pattern(f"comment:{comment_id}:likes:*")
                await self.redis.delete(f"comment:{comment_id}:like_count")
            
            # Update user-specific caches
            await self.redis.delete_pattern(f"user:{user_id}:likes:*")
            await self.redis.delete_pattern(f"user:{user_id}:like_count:*")
            await self.redis.delete(f"user:{user_id}:like_stats")
            
            # Update global caches
            await self.redis.delete_pattern("trending_posts:*")
            await self.redis.delete_pattern("recent_likes:*")
            
            logger.debug(f"Updated cache for {action}: user={user_id}, post={post_id}, comment={comment_id}")
            
        except Exception as e:
            logger.error(f"Error updating like cache: {e}")