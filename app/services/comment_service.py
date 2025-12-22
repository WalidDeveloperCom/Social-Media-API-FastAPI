from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func, update
from sqlalchemy.orm import selectinload, joinedload
import logging

from app.models.comment import Comment
from app.models.user import User
from app.models.post import Post
from app.models.like import Like
from app.schemas.comment_schema import (
    CommentCreate,
    CommentUpdate,
    CommentResponse,
    CommentTreeResponse,
    CommentStats
)
from app.services.redis_service import RedisService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

class CommentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
        self.search_service = SearchService()
    
    async def create_comment(
        self,
        post_id: int,
        user_id: int,
        comment_data: CommentCreate
    ) -> Comment:
        """Create a new comment"""
        try:
            # Validate parent comment if provided
            if comment_data.parent_id:
                parent_stmt = select(Comment).where(
                    and_(
                        Comment.id == comment_data.parent_id,
                        Comment.post_id == post_id
                    )
                )
                parent_result = await self.db.execute(parent_stmt)
                parent = parent_result.scalar_one_or_none()
                
                if not parent:
                    raise ValueError("Parent comment not found or doesn't belong to this post")
            
            # Create comment
            comment = Comment(
                post_id=post_id,
                user_id=user_id,
                content=comment_data.content,
                parent_id=comment_data.parent_id
            )
            
            self.db.add(comment)
            await self.db.commit()
            await self.db.refresh(comment)
            
            # Update post comment count
            await self._update_post_comment_count(post_id)
            
            # Update parent comment reply count if applicable
            if comment_data.parent_id:
                await self._update_parent_comment_stats(comment_data.parent_id)
            
            # Cache invalidation
            await self._invalidate_comment_caches(post_id, user_id, comment_data.parent_id)
            
            # Index in search if needed
            await self.search_service.index_comment(comment)
            
            logger.info(f"Created comment {comment.id} by user {user_id} on post {post_id}")
            
            return comment
            
        except Exception as e:
            logger.error(f"Error creating comment: {e}")
            await self.db.rollback()
            raise
    
    async def get_comment(self, comment_id: int) -> Optional[Comment]:
        """Get a comment by ID"""
        stmt = select(Comment).where(Comment.id == comment_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_comment_with_post(self, comment_id: int) -> Optional[Comment]:
        """Get a comment with post relationship"""
        stmt = select(Comment).options(
            selectinload(Comment.post)
        ).where(Comment.id == comment_id)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_comment_with_user(
        self,
        comment_id: int,
        user_id: Optional[int] = None
    ) -> Optional[CommentResponse]:
        """Get a comment with user info and like status"""
        try:
            cache_key = f"comment:{comment_id}:user:{user_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return CommentResponse(**cached)
            
            # Build query
            stmt = select(
                Comment,
                User.username,
                User.profile_picture,
                func.coalesce(func.count(Like.id), 0).label('like_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Like.post_id == Comment.post_id,
                            Like.user_id == user_id,
                            Like.id == Comment.id  # Assuming Like has comment_id
                        )
                    )
                ).label('liked') if user_id else False
            ).join(
                User, Comment.user_id == User.id
            ).outerjoin(
                Like, and_(
                    Like.comment_id == Comment.id,
                    Like.user_id == user_id if user_id else False
                )
            ).where(
                Comment.id == comment_id
            ).group_by(
                Comment.id, User.id
            )
            
            result = await self.db.execute(stmt)
            row = result.first()
            
            if not row:
                return None
            
            comment_dict = {
                "id": row.Comment.id,
                "post_id": row.Comment.post_id,
                "user_id": row.Comment.user_id,
                "content": row.Comment.content,
                "parent_id": row.Comment.parent_id,
                "like_count": row.like_count,
                "liked": row.liked,
                "created_at": row.Comment.created_at,
                "updated_at": row.Comment.updated_at,
                "user": {
                    "id": row.Comment.user_id,
                    "username": row.username,
                    "profile_picture": row.profile_picture
                }
            }
            
            response = CommentResponse(**comment_dict)
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, response.dict())
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting comment with user: {e}")
            return None
    
    async def get_post_comments(
        self,
        post_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: str = "newest"
    ) -> List[CommentResponse]:
        """Get comments for a post with pagination"""
        try:
            cache_key = f"post:{post_id}:comments:{skip}:{limit}:{sort_by}:user:{user_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return [CommentResponse(**item) for item in cached]
            
            # Build base query
            stmt = select(
                Comment,
                User.username,
                User.profile_picture,
                func.coalesce(func.count(Like.id), 0).label('like_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Like.comment_id == Comment.id,
                            Like.user_id == user_id
                        )
                    )
                ).label('liked') if user_id else False
            ).join(
                User, Comment.user_id == User.id
            ).outerjoin(
                Like, Comment.id == Like.comment_id
            ).where(
                Comment.post_id == post_id,
                Comment.parent_id == None  # Get only top-level comments
            ).group_by(
                Comment.id, User.id
            )
            
            # Apply sorting
            if sort_by == "newest":
                stmt = stmt.order_by(desc(Comment.created_at))
            elif sort_by == "oldest":
                stmt = stmt.order_by(asc(Comment.created_at))
            elif sort_by == "popular":
                stmt = stmt.order_by(desc('like_count'), desc(Comment.created_at))
            
            # Apply pagination
            stmt = stmt.offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            comments = []
            for row in rows:
                comment_dict = {
                    "id": row.Comment.id,
                    "post_id": row.Comment.post_id,
                    "user_id": row.Comment.user_id,
                    "content": row.Comment.content,
                    "parent_id": row.Comment.parent_id,
                    "like_count": row.like_count,
                    "liked": row.liked,
                    "created_at": row.Comment.created_at,
                    "updated_at": row.Comment.updated_at,
                    "user": {
                        "id": row.Comment.user_id,
                        "username": row.username,
                        "profile_picture": row.profile_picture
                    }
                }
                comments.append(CommentResponse(**comment_dict))
            
            # Cache for 1 minute
            await self.redis.setex(cache_key, 60, [c.dict() for c in comments])
            
            return comments
            
        except Exception as e:
            logger.error(f"Error getting post comments: {e}")
            return []
    
    async def get_comment_tree(
        self,
        post_id: int,
        user_id: Optional[int] = None,
        max_depth: int = 5
    ) -> List[CommentTreeResponse]:
        """Get comments in nested tree structure"""
        try:
            cache_key = f"post:{post_id}:comment_tree:depth:{max_depth}:user:{user_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return [CommentTreeResponse(**item) for item in cached]
            
            # Get all comments for the post
            stmt = select(
                Comment,
                User.username,
                User.profile_picture,
                func.coalesce(func.count(Like.id), 0).label('like_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Like.comment_id == Comment.id,
                            Like.user_id == user_id
                        )
                    )
                ).label('liked') if user_id else False
            ).join(
                User, Comment.user_id == User.id
            ).outerjoin(
                Like, Comment.id == Like.comment_id
            ).where(
                Comment.post_id == post_id
            ).group_by(
                Comment.id, User.id
            ).order_by(
                Comment.created_at
            )
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            # Build comment dictionary
            comments_dict = {}
            for row in rows:
                comment_data = {
                    "id": row.Comment.id,
                    "post_id": row.Comment.post_id,
                    "user_id": row.Comment.user_id,
                    "content": row.Comment.content,
                    "parent_id": row.Comment.parent_id,
                    "like_count": row.like_count,
                    "liked": row.liked,
                    "created_at": row.Comment.created_at,
                    "updated_at": row.Comment.updated_at,
                    "user": {
                        "id": row.Comment.user_id,
                        "username": row.username,
                        "profile_picture": row.profile_picture
                    },
                    "replies": []
                }
                comments_dict[row.Comment.id] = CommentTreeResponse(**comment_data)
            
            # Build tree structure
            root_comments = []
            for comment_id, comment in comments_dict.items():
                parent_id = comment.parent_id
                if parent_id and parent_id in comments_dict:
                    # Add as reply to parent
                    comments_dict[parent_id].replies.append(comment)
                else:
                    # Root level comment
                    root_comments.append(comment)
            
            # Limit depth
            def limit_depth(comment: CommentTreeResponse, current_depth: int = 0):
                if current_depth >= max_depth:
                    comment.replies = []
                    return
                
                for reply in comment.replies:
                    limit_depth(reply, current_depth + 1)
            
            for comment in root_comments:
                limit_depth(comment)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, [c.dict() for c in root_comments])
            
            return root_comments
            
        except Exception as e:
            logger.error(f"Error getting comment tree: {e}")
            return []
    
    async def get_comment_replies(
        self,
        comment_id: int,
        user_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[CommentResponse]:
        """Get replies to a specific comment"""
        try:
            cache_key = f"comment:{comment_id}:replies:{skip}:{limit}:user:{user_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return [CommentResponse(**item) for item in cached]
            
            stmt = select(
                Comment,
                User.username,
                User.profile_picture,
                func.coalesce(func.count(Like.id), 0).label('like_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Like.comment_id == Comment.id,
                            Like.user_id == user_id
                        )
                    )
                ).label('liked') if user_id else False
            ).join(
                User, Comment.user_id == User.id
            ).outerjoin(
                Like, Comment.id == Like.comment_id
            ).where(
                Comment.parent_id == comment_id
            ).group_by(
                Comment.id, User.id
            ).order_by(
                desc(Comment.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            replies = []
            for row in rows:
                comment_dict = {
                    "id": row.Comment.id,
                    "post_id": row.Comment.post_id,
                    "user_id": row.Comment.user_id,
                    "content": row.Comment.content,
                    "parent_id": row.Comment.parent_id,
                    "like_count": row.like_count,
                    "liked": row.liked,
                    "created_at": row.Comment.created_at,
                    "updated_at": row.Comment.updated_at,
                    "user": {
                        "id": row.Comment.user_id,
                        "username": row.username,
                        "profile_picture": row.profile_picture
                    }
                }
                replies.append(CommentResponse(**comment_dict))
            
            # Cache for 1 minute
            await self.redis.setex(cache_key, 60, [c.dict() for c in replies])
            
            return replies
            
        except Exception as e:
            logger.error(f"Error getting comment replies: {e}")
            return []
    
    async def update_comment(
        self,
        comment_id: int,
        comment_update: CommentUpdate
    ) -> CommentResponse:
        """Update a comment"""
        try:
            stmt = select(Comment).where(Comment.id == comment_id)
            result = await self.db.execute(stmt)
            comment = result.scalar_one_or_none()
            
            if not comment:
                raise ValueError("Comment not found")
            
            # Update fields
            update_data = comment_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                setattr(comment, field, value)
            
            await self.db.commit()
            await self.db.refresh(comment)
            
            # Invalidate caches
            await self._invalidate_comment_caches(
                comment.post_id,
                comment.user_id,
                comment.parent_id
            )
            
            # Get updated comment with user info
            updated = await self.get_comment_with_user(comment_id, comment.user_id)
            
            return updated
            
        except Exception as e:
            logger.error(f"Error updating comment: {e}")
            await self.db.rollback()
            raise
    
    async def delete_comment(
        self,
        comment_id: int,
        user_id: int
    ) -> None:
        """Delete a comment and its replies"""
        try:
            # Get comment with post info
            stmt = select(Comment).options(
                selectinload(Comment.post)
            ).where(Comment.id == comment_id)
            
            result = await self.db.execute(stmt)
            comment = result.scalar_one_or_none()
            
            if not comment:
                raise ValueError("Comment not found")
            
            # Store info for cache invalidation
            post_id = comment.post_id
            parent_id = comment.parent_id
            
            # Delete comment and all replies (cascade)
            await self._delete_comment_tree(comment_id)
            
            # Update post comment count
            await self._update_post_comment_count(post_id)
            
            # Update parent comment stats if applicable
            if parent_id:
                await self._update_parent_comment_stats(parent_id)
            
            # Invalidate caches
            await self._invalidate_comment_caches(post_id, user_id, parent_id)
            
            logger.info(f"Deleted comment {comment_id} and its replies")
            
        except Exception as e:
            logger.error(f"Error deleting comment: {e}")
            await self.db.rollback()
            raise
    
    async def _delete_comment_tree(self, comment_id: int):
        """Recursively delete comment and all replies"""
        # First, get all reply IDs
        reply_stmt = select(Comment.id).where(Comment.parent_id == comment_id)
        reply_result = await self.db.execute(reply_stmt)
        reply_ids = [row[0] for row in reply_result]
        
        # Recursively delete replies
        for reply_id in reply_ids:
            await self._delete_comment_tree(reply_id)
        
        # Delete the comment
        delete_stmt = Comment.__table__.delete().where(Comment.id == comment_id)
        await self.db.execute(delete_stmt)
    
    async def like_comment(self, comment_id: int, user_id: int) -> bool:
        """Like a comment"""
        try:
            # Check if already liked
            check_stmt = select(Like).where(
                and_(
                    Like.comment_id == comment_id,
                    Like.user_id == user_id
                )
            )
            check_result = await self.db.execute(check_stmt)
            existing = check_result.scalar_one_or_none()
            
            if existing:
                return False  # Already liked
            
            # Create like
            like = Like(
                comment_id=comment_id,
                user_id=user_id
            )
            
            self.db.add(like)
            await self.db.commit()
            
            # Update comment like count
            update_stmt = update(Comment).where(
                Comment.id == comment_id
            ).values(
                like_count=Comment.like_count + 1
            )
            
            await self.db.execute(update_stmt)
            await self.db.commit()
            
            # Invalidate caches
            await self.redis.delete_pattern(f"*comment:{comment_id}*")
            await self.redis.delete_pattern(f"*post:*comments*")
            
            return True
            
        except Exception as e:
            logger.error(f"Error liking comment: {e}")
            await self.db.rollback()
            return False
    
    async def unlike_comment(self, comment_id: int, user_id: int) -> bool:
        """Unlike a comment"""
        try:
            # Find the like
            stmt = select(Like).where(
                and_(
                    Like.comment_id == comment_id,
                    Like.user_id == user_id
                )
            )
            result = await self.db.execute(stmt)
            like = result.scalar_one_or_none()
            
            if not like:
                return False  # Not liked
            
            # Delete like
            await self.db.delete(like)
            await self.db.commit()
            
            # Update comment like count
            update_stmt = update(Comment).where(
                Comment.id == comment_id
            ).values(
                like_count=Comment.like_count - 1
            )
            
            await self.db.execute(update_stmt)
            await self.db.commit()
            
            # Invalidate caches
            await self.redis.delete_pattern(f"*comment:{comment_id}*")
            await self.redis.delete_pattern(f"*post:*comments*")
            
            return True
            
        except Exception as e:
            logger.error(f"Error unliking comment: {e}")
            await self.db.rollback()
            return False
    
    async def get_user_comments(
        self,
        user_id: int,
        requester_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[CommentResponse]:
        """Get all comments by a user"""
        try:
            cache_key = f"user:{user_id}:comments:{skip}:{limit}:requester:{requester_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return [CommentResponse(**item) for item in cached]
            
            # Build query
            stmt = select(
                Comment,
                User.username,
                User.profile_picture,
                func.coalesce(func.count(Like.id), 0).label('like_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Like.comment_id == Comment.id,
                            Like.user_id == requester_id
                        )
                    )
                ).label('liked') if requester_id else False
            ).join(
                User, Comment.user_id == User.id
            ).outerjoin(
                Like, Comment.id == Like.comment_id
            ).where(
                Comment.user_id == user_id
            ).group_by(
                Comment.id, User.id
            ).order_by(
                desc(Comment.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            comments = []
            for row in rows:
                comment_dict = {
                    "id": row.Comment.id,
                    "post_id": row.Comment.post_id,
                    "user_id": row.Comment.user_id,
                    "content": row.Comment.content,
                    "parent_id": row.Comment.parent_id,
                    "like_count": row.like_count,
                    "liked": row.liked,
                    "created_at": row.Comment.created_at,
                    "updated_at": row.Comment.updated_at,
                    "user": {
                        "id": row.Comment.user_id,
                        "username": row.username,
                        "profile_picture": row.profile_picture
                    }
                }
                comments.append(CommentResponse(**comment_dict))
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, [c.dict() for c in comments])
            
            return comments
            
        except Exception as e:
            logger.error(f"Error getting user comments: {e}")
            return []
    
    async def get_post_comment_count(self, post_id: int) -> int:
        """Get total comment count for a post"""
        try:
            cache_key = f"post:{post_id}:comment_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                Comment.post_id == post_id
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting post comment count: {e}")
            return 0
    
    async def get_user_comment_count(self, user_id: int) -> int:
        """Get total comment count for a user"""
        try:
            cache_key = f"user:{user_id}:comment_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                Comment.user_id == user_id
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting user comment count: {e}")
            return 0
    
    async def get_comment_stats(self, comment_id: int) -> CommentStats:
        """Get statistics for a comment"""
        try:
            cache_key = f"comment:{comment_id}:stats"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return CommentStats(**cached)
            
            # Get comment with relationships
            stmt = select(Comment).where(Comment.id == comment_id)
            result = await self.db.execute(stmt)
            comment = result.scalar_one_or_none()
            
            if not comment:
                raise ValueError("Comment not found")
            
            # Get reply count
            reply_stmt = select(func.count()).where(
                Comment.parent_id == comment_id
            )
            reply_result = await self.db.execute(reply_stmt)
            reply_count = reply_result.scalar() or 0
            
            # Get unique likers count
            liker_stmt = select(func.count()).select_from(
                Like.__table__.join(User, Like.user_id == User.id)
            ).where(
                Like.comment_id == comment_id
            ).group_by(User.id)
            
            liker_result = await self.db.execute(liker_stmt)
            unique_likers = len(liker_result.all())
            
            stats = CommentStats(
                comment_id=comment_id,
                like_count=comment.like_count,
                reply_count=reply_count,
                unique_likers=unique_likers,
                created_at=comment.created_at,
                updated_at=comment.updated_at
            )
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, stats.dict())
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting comment stats: {e}")
            return CommentStats(
                comment_id=comment_id,
                like_count=0,
                reply_count=0,
                unique_likers=0
            )
    
    async def get_post_comment_stats(self, post_id: int) -> Dict[str, Any]:
        """Get comment statistics for a post"""
        try:
            cache_key = f"post:{post_id}:comment_stats"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return cached
            
            # Get total comments
            total_stmt = select(func.count()).where(
                Comment.post_id == post_id
            )
            total_result = await self.db.execute(total_stmt)
            total_comments = total_result.scalar() or 0
            
            # Get top-level comments
            top_level_stmt = select(func.count()).where(
                and_(
                    Comment.post_id == post_id,
                    Comment.parent_id == None
                )
            )
            top_level_result = await self.db.execute(top_level_stmt)
            top_level_comments = top_level_result.scalar() or 0
            
            # Get replies
            reply_count = total_comments - top_level_comments
            
            # Get most active commenters
            commenter_stmt = select(
                User.id,
                User.username,
                func.count(Comment.id).label('comment_count')
            ).join(
                Comment, User.id == Comment.user_id
            ).where(
                Comment.post_id == post_id
            ).group_by(
                User.id, User.username
            ).order_by(
                desc('comment_count')
            ).limit(10)
            
            commenter_result = await self.db.execute(commenter_stmt)
            top_commenters = [
                {"user_id": row[0], "username": row[1], "comment_count": row[2]}
                for row in commenter_result.all()
            ]
            
            # Get comments over time (last 7 days)
            from datetime import datetime, timedelta
            
            time_series = {}
            for i in range(7):
                date = (datetime.utcnow() - timedelta(days=i)).date()
                day_start = datetime.combine(date, datetime.min.time())
                day_end = datetime.combine(date, datetime.max.time())
                
                day_stmt = select(func.count()).where(
                    and_(
                        Comment.post_id == post_id,
                        Comment.created_at >= day_start,
                        Comment.created_at <= day_end
                    )
                )
                
                day_result = await self.db.execute(day_stmt)
                count = day_result.scalar() or 0
                time_series[date.isoformat()] = count
            
            stats = {
                "total_comments": total_comments,
                "top_level_comments": top_level_comments,
                "reply_count": reply_count,
                "top_commenters": top_commenters,
                "comments_over_time": time_series
            }
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting post comment stats: {e}")
            return {
                "total_comments": 0,
                "top_level_comments": 0,
                "reply_count": 0,
                "top_commenters": [],
                "comments_over_time": {}
            }
    
    async def _update_post_comment_count(self, post_id: int):
        """Update comment count for a post"""
        try:
            # Calculate new count
            count_stmt = select(func.count()).where(
                Comment.post_id == post_id
            )
            count_result = await self.db.execute(count_stmt)
            new_count = count_result.scalar() or 0
            
            # Update post
            from sqlalchemy import update as sql_update
            update_stmt = sql_update(Post).where(
                Post.id == post_id
            ).values(
                comment_count=new_count
            )
            
            await self.db.execute(update_stmt)
            await self.db.commit()
            
            # Invalidate post cache
            await self.redis.delete_pattern(f"*post:{post_id}*")
            
        except Exception as e:
            logger.error(f"Error updating post comment count: {e}")
    
    async def _update_parent_comment_stats(self, parent_comment_id: int):
        """Update reply count for parent comment"""
        try:
            # Calculate new reply count
            count_stmt = select(func.count()).where(
                Comment.parent_id == parent_comment_id
            )
            count_result = await self.db.execute(count_stmt)
            reply_count = count_result.scalar() or 0
            
            # Update parent comment
            from sqlalchemy import update as sql_update
            update_stmt = sql_update(Comment).where(
                Comment.id == parent_comment_id
            ).values(
                like_count=reply_count  # Using like_count field for reply count
            )
            
            await self.db.execute(update_stmt)
            await self.db.commit()
            
        except Exception as e:
            logger.error(f"Error updating parent comment stats: {e}")
    
    async def _invalidate_comment_caches(
        self,
        post_id: int,
        user_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ):
        """Invalidate relevant caches after comment operations"""
        try:
            # Invalidate post comment caches
            await self.redis.delete_pattern(f"*post:{post_id}:comments*")
            await self.redis.delete_pattern(f"*post:{post_id}:comment*")
            
            # Invalidate user comment caches
            if user_id:
                await self.redis.delete_pattern(f"*user:{user_id}:comments*")
            
            # Invalidate parent comment caches
            if parent_id:
                await self.redis.delete_pattern(f"*comment:{parent_id}:replies*")
                await self.redis.delete_pattern(f"*comment:{parent_id}:*")
            
            # Invalidate comment tree cache
            await self.redis.delete_pattern(f"*post:{post_id}:comment_tree*")
            
            # Invalidate post count cache
            await self.redis.delete(f"post:{post_id}:comment_count")
            
            logger.debug(f"Invalidated caches for post:{post_id}, user:{user_id}, parent:{parent_id}")
            
        except Exception as e:
            logger.error(f"Error invalidating caches: {e}")