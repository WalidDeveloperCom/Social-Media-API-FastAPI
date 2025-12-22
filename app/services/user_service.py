"""
User Service for handling user-related business logic
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, desc, func, case
from sqlalchemy.orm import selectinload
import asyncio

# Import models carefully to avoid circular imports
from app.models.user import User
# Post, Follow, Like, Comment are imported inside methods when needed
from app.schemas.user_schema import (
    UserCreate,
    UserUpdate,
    UserPublic,
    UserStats,
    UserSearchResult,
    UserListResponse
)
from app.schemas.auth_schema import PasswordResetConfirm, ChangePasswordRequest
from app.services.auth_service import AuthService, pwd_context
from app.services.redis_service import RedisService
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
        self.search_service = SearchService()
        self.auth_service = AuthService(db)
    
    # ... rest of the class methods ...
    
    # Update the _get_user_post_count method to import Post locally:
    async def _get_user_post_count(self, user_id: int) -> int:
        """Get user's post count"""
        from app.models.post import Post  # Local import to avoid circular dependency
        
        stmt = select(func.count()).where(
            and_(Post.user_id == user_id, Post.is_public == True)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _get_user_follower_count(self, user_id: int) -> int:
        """Get user's follower count"""
        from app.models.follow import Follow  # Local import
        
        stmt = select(func.count()).where(Follow.following_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _get_user_following_count(self, user_id: int) -> int:
        """Get user's following count"""
        from app.models.follow import Follow  # Local import
        
        stmt = select(func.count()).where(Follow.follower_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _get_user_like_count(self, user_id: int) -> int:
        """Get user's total likes given"""
        from app.models.like import Like  # Local import
        
        stmt = select(func.count()).where(Like.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    async def _get_user_comment_count(self, user_id: int) -> int:
        """Get user's total comments"""
        from app.models.comment import Comment  # Local import
        
        stmt = select(func.count()).where(Comment.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
    
    # Update get_user_activity_timeline method:
    async def get_user_activity_timeline(
        self, user_id: int, days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get user activity timeline"""
        try:
            # Import models locally
            from app.models.post import Post
            from app.models.like import Like
            from app.models.comment import Comment
            
            cache_key = f"user:{user_id}:activity:{days}"
            cached = await self.redis.get(cache_key)

            if cached:
                return cached

            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Get posts activity
            posts_stmt = (
                select(
                    Post.created_at.label("date"),
                    func.count().label("post_count"),
                )
                .where(
                    and_(
                        Post.user_id == user_id,
                        Post.created_at >= start_date,
                        Post.created_at <= end_date,
                    )
                )
                .group_by(func.date(Post.created_at))
            )

            # Get likes activity
            likes_stmt = (
                select(
                    Like.created_at.label("date"),
                    func.count().label("like_count"),
                )
                .where(
                    and_(
                        Like.user_id == user_id,
                        Like.created_at >= start_date,
                        Like.created_at <= end_date,
                    )
                )
                .group_by(func.date(Like.created_at))
            )

            # Get comments activity
            comments_stmt = (
                select(
                    Comment.created_at.label("date"),
                    func.count().label("comment_count"),
                )
                .where(
                    and_(
                        Comment.user_id == user_id,
                        Comment.created_at >= start_date,
                        Comment.created_at <= end_date,
                    )
                )
                .group_by(func.date(Comment.created_at))
            )

            posts_result = await self.db.execute(posts_stmt)
            likes_result = await self.db.execute(likes_stmt)
            comments_result = await self.db.execute(comments_stmt)

            # ... rest of the method ...

            # Combine results
            timeline = {}
            for date, count in posts_result:
                if date not in timeline:
                    timeline[date] = {"posts": 0, "likes": 0, "comments": 0}
                timeline[date]["posts"] = count

            for date, count in likes_result:
                if date not in timeline:
                    timeline[date] = {"posts": 0, "likes": 0, "comments": 0}
                timeline[date]["likes"] = count

            for date, count in comments_result:
                if date not in timeline:
                    timeline[date] = {"posts": 0, "likes": 0, "comments": 0}
                timeline[date]["comments"] = count

            # Convert to list
            activity_list = [
                {
                    "date": date.isoformat(),
                    "posts": data["posts"],
                    "likes": data["likes"],
                    "comments": data["comments"],
                    "total": data["posts"] + data["likes"] + data["comments"],
                }
                for date, data in sorted(timeline.items(), reverse=True)
            ]

            # Cache for 1 hour
            await self.redis.setex(cache_key, 3600, activity_list)

            return activity_list
        except Exception as e:
            logger.error(f"Error getting user activity timeline {user_id}: {e}")
            return []

    # Private helper methods
    async def _get_users_by_ids(
        self, user_ids: List[int], viewer_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get multiple users by IDs"""
        if not user_ids:
            return []

        stmt = (
            select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label("followers_count"),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == viewer_id,
                            Follow.following_id == User.id,
                        )
                    )
                ).label("you_follow"),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == User.id,
                            Follow.following_id == viewer_id,
                        )
                    )
                ).label("follows_you"),
            )
            .outerjoin(Follow, Follow.following_id == User.id)
            .where(User.id.in_(user_ids))
            .group_by(User.id)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        users = []
        for row in rows:
            users.append(
                {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "followers_count": row.followers_count,
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you,
                    "relevance_score": 0.0,  # Would be calculated in search
                }
            )

        return users

    async def _get_popular_users(
        self, exclude_id: int, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular users (most followers)"""
        stmt = (
            select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label("followers_count"),
            )
            .outerjoin(Follow, Follow.following_id == User.id)
            .where(
                and_(
                    User.id != exclude_id,
                    User.is_active == True,
                )
            )
            .group_by(User.id)
            .order_by(desc("followers_count"), desc(User.created_at))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        popular_users = []
        for row in rows:
            user = {
                "id": row.id,
                "username": row.username,
                "full_name": row.full_name,
                "profile_picture": row.profile_picture,
                "bio": row.bio,
                "followers_count": row.followers_count,
                "reason": "Popular in the community",
            }
            popular_users.append(user)

        return popular_users

    async def _get_user_post_count(self, user_id: int) -> int:
        """Get user's post count"""
        stmt = select(func.count()).where(
            and_(Post.user_id == user_id, Post.is_public == True)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_user_follower_count(self, user_id: int) -> int:
        """Get user's follower count"""
        stmt = select(func.count()).where(Follow.following_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_user_following_count(self, user_id: int) -> int:
        """Get user's following count"""
        stmt = select(func.count()).where(Follow.follower_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_user_like_count(self, user_id: int) -> int:
        """Get user's total likes given"""
        stmt = select(func.count()).where(Like.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _get_user_comment_count(self, user_id: int) -> int:
        """Get user's total comments"""
        stmt = select(func.count()).where(Comment.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def _invalidate_user_cache(self, user: User) -> None:
        """Invalidate user-related cache"""
        try:
            await self.redis.delete_pattern(f"user:{user.id}:*")
            await self.redis.delete(f"user:username:{user.username}")
            await self.redis.delete_pattern(f"users:*")
            await self.redis.delete_pattern(f"user:search:*")
        except Exception as e:
            logger.error(f"Error invalidating user cache: {e}")

    # Email methods (placeholder implementations)
    async def _send_welcome_email(self, user: User) -> None:
        """Send welcome email to new user"""
        try:
            subject = "Welcome to Social Media API!"
            body = f"""
            Hello {user.full_name or user.username},
            
            Welcome to our platform! We're excited to have you join our community.
            
            Your account has been created successfully.
            Username: {user.username}
            Email: {user.email}
            
            Please verify your email address to unlock all features.
            
            Best regards,
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent welcome email to {user.email}")
        except Exception as e:
            logger.error(f"Error sending welcome email: {e}")

    async def _send_verification_email(self, user: User) -> None:
        """Send email verification email"""
        try:
            subject = "Email Verification - Social Media API"
            body = f"""
            Hello {user.full_name or user.username},
            
            Your email has been successfully verified!
            
            You now have full access to all platform features.
            
            Thank you,
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent verification email to {user.email}")
        except Exception as e:
            logger.error(f"Error sending verification email: {e}")

    async def _send_password_change_email(self, user: User) -> None:
        """Send password change notification"""
        try:
            subject = "Password Changed - Social Media API"
            body = f"""
            Hello {user.full_name or user.username},
            
            Your password has been changed successfully.
            
            If you did not make this change, please contact support immediately.
            
            For security reasons, all your active sessions have been terminated.
            
            Thank you,
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent password change email to {user.email}")
        except Exception as e:
            logger.error(f"Error sending password change email: {e}")

    async def _send_password_reset_confirmation_email(self, user: User) -> None:
        """Send password reset confirmation"""
        try:
            subject = "Password Reset Confirmation - Social Media API"
            body = f"""
            Hello {user.full_name or user.username},
            
            Your password has been successfully reset.
            
            For security reasons, all your active sessions have been terminated.
            
            If you did not request this reset, please contact support immediately.
            
            Thank you,
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent password reset confirmation to {user.email}")
        except Exception as e:
            logger.error(f"Error sending password reset confirmation: {e}")

    async def _send_deactivation_email(self, user: User, reason: str) -> None:
        """Send account deactivation email"""
        try:
            subject = "Account Deactivated - Social Media API"
            body = f"""
            Hello {user.full_name or user.username},
            
            Your account has been deactivated.
            
            Reason: {reason or "No reason provided"}
            
            If you believe this is a mistake, please contact support.
            
            Thank you,
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent deactivation email to {user.email}")
        except Exception as e:
            logger.error(f"Error sending deactivation email: {e}")

    async def _send_activation_email(self, user: User) -> None:
        """Send account activation email"""
        try:
            subject = "Account Activated - Social Media API"
            body = f"""
            Hello {user.full_name or user.username},
            
            Your account has been activated!
            
            You can now log in and use all features of our platform.
            
            Welcome back!
            
            The Social Media Team
            """
            
            await send_email(
                to_email=user.email,
                subject=subject,
                body=body,
                is_html=False,
            )
            
            logger.info(f"Sent activation email to {user.email}")
        except Exception as e:
            logger.error(f"Error sending activation email: {e}")