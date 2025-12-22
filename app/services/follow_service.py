from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func, text
from sqlalchemy.orm import selectinload
import logging
import json

from app.models.follow import Follow
from app.models.user import User
from app.schemas.follow_schema import (
    FollowCreate,
    FollowResponse,
    FollowStats,
    UserRelationship,
    RelationshipStatus
)
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)

class FollowService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
    
    async def create_follow(self, follow_data: FollowCreate) -> Follow:
        """Create a new follow relationship"""
        try:
            # Check if relationship already exists
            existing = await self.get_follow_relationship(
                follower_id=follow_data.follower_id,
                following_id=follow_data.following_id
            )
            
            if existing:
                raise ValueError("Already following this user")
            
            # Create follow
            follow = Follow(
                follower_id=follow_data.follower_id,
                following_id=follow_data.following_id
            )
            
            self.db.add(follow)
            await self.db.commit()
            await self.db.refresh(follow)
            
            # Update cache
            await self._update_follow_cache(
                follower_id=follow_data.follower_id,
                following_id=follow_data.following_id,
                action="follow"
            )
            
            logger.info(f"Created follow: {follow_data.follower_id} -> {follow_data.following_id}")
            
            return follow
            
        except Exception as e:
            logger.error(f"Error creating follow: {e}")
            await self.db.rollback()
            raise
    
    async def delete_follow(
        self,
        follower_id: int,
        following_id: int
    ) -> bool:
        """Delete a follow relationship"""
        try:
            stmt = select(Follow).where(
                and_(
                    Follow.follower_id == follower_id,
                    Follow.following_id == following_id
                )
            )
            
            result = await self.db.execute(stmt)
            follow = result.scalar_one_or_none()
            
            if not follow:
                return False
            
            await self.db.delete(follow)
            await self.db.commit()
            
            # Update cache
            await self._update_follow_cache(
                follower_id=follower_id,
                following_id=following_id,
                action="unfollow"
            )
            
            logger.info(f"Deleted follow: {follower_id} -> {following_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting follow: {e}")
            await self.db.rollback()
            return False
    
    async def get_follow_relationship(
        self,
        follower_id: int,
        following_id: int
    ) -> Optional[Follow]:
        """Get follow relationship between two users"""
        try:
            cache_key = f"follow:{follower_id}:{following_id}"
            cached = await self.redis.get(cache_key)
            
            if cached is not None:
                # Cache hit - check if relationship exists
                if cached == "1":
                    stmt = select(Follow).where(
                        and_(
                            Follow.follower_id == follower_id,
                            Follow.following_id == following_id
                        )
                    )
                    result = await self.db.execute(stmt)
                    return result.scalar_one_or_none()
                else:
                    return None
            
            # Cache miss - query database
            stmt = select(Follow).where(
                and_(
                    Follow.follower_id == follower_id,
                    Follow.following_id == following_id
                )
            )
            
            result = await self.db.execute(stmt)
            follow = result.scalar_one_or_none()
            
            # Update cache
            await self.redis.setex(
                cache_key,
                300,  # 5 minutes
                "1" if follow else "0"
            )
            
            return follow
            
        except Exception as e:
            logger.error(f"Error getting follow relationship: {e}")
            return None
    
    async def get_user_followers(
        self,
        user_id: int,
        viewer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get followers of a user"""
        try:
            cache_key = f"user:{user_id}:followers:{skip}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build query
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label('followers_count'),
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
                Follow, Follow.follower_id == User.id
            ).outerjoin(
                Follow.__table__.alias('f2'), User.id == Follow.__table__.alias('f2').c.following_id
            ).where(
                Follow.following_id == user_id
            ).group_by(
                User.id
            ).order_by(
                desc(Follow.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            followers = []
            for row in rows:
                follower = {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "followers_count": row.followers_count,
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you
                }
                followers.append(follower)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, json.dumps(followers))
            
            return followers
            
        except Exception as e:
            logger.error(f"Error getting user followers: {e}")
            return []
    
    async def get_user_following(
        self,
        user_id: int,
        viewer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get users that a user is following"""
        try:
            cache_key = f"user:{user_id}:following:{skip}:{limit}:viewer:{viewer_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build query
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label('followers_count'),
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
                Follow, Follow.following_id == User.id
            ).outerjoin(
                Follow.__table__.alias('f2'), User.id == Follow.__table__.alias('f2').c.following_id
            ).where(
                Follow.follower_id == user_id
            ).group_by(
                User.id
            ).order_by(
                desc(Follow.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            following = []
            for row in rows:
                user = {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "followers_count": row.followers_count,
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you
                }
                following.append(user)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, json.dumps(following))
            
            return following
            
        except Exception as e:
            logger.error(f"Error getting user following: {e}")
            return []
    
    async def get_mutual_follows(
        self,
        user1_id: int,
        user2_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get mutual followers between two users"""
        try:
            cache_key = f"mutual:{user1_id}:{user2_id}:{skip}:{limit}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Subquery for users followed by user1
            user1_following = select(Follow.following_id).where(
                Follow.follower_id == user1_id
            ).subquery()
            
            # Subquery for users followed by user2
            user2_following = select(Follow.following_id).where(
                Follow.follower_id == user2_id
            ).subquery()
            
            # Query mutual follows
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label('followers_count')
            ).join(
                Follow, Follow.following_id == User.id
            ).where(
                and_(
                    User.id.in_(user1_following),
                    User.id.in_(user2_following),
                    User.id != user1_id,
                    User.id != user2_id
                )
            ).group_by(
                User.id
            ).order_by(
                desc('followers_count')
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            mutual_follows = []
            for row in rows:
                user = {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "followers_count": row.followers_count
                }
                mutual_follows.append(user)
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(mutual_follows))
            
            return mutual_follows
            
        except Exception as e:
            logger.error(f"Error getting mutual follows: {e}")
            return []
    
    async def get_follow_suggestions(
        self,
        user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get follow suggestions for a user"""
        try:
            cache_key = f"user:{user_id}:follow_suggestions:{limit}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Get users followed by people you follow (friends of friends)
            friends_following = select(Follow.following_id).where(
                and_(
                    Follow.follower_id.in_(
                        select(Follow.following_id).where(Follow.follower_id == user_id)
                    ),
                    Follow.following_id != user_id,
                    ~Follow.following_id.in_(
                        select(Follow.following_id).where(Follow.follower_id == user_id)
                    )
                )
            ).subquery()
            
            # Get popular users in the same network
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.count(Follow.id).label('mutual_friends'),
                func.coalesce(func.count(Follow2.id), 0).label('followers_count')
            ).join(
                Follow, Follow.following_id == User.id
            ).outerjoin(
                Follow.__table__.alias('f2'), User.id == Follow.__table__.alias('f2').c.following_id
            ).where(
                and_(
                    User.id.in_(friends_following),
                    User.id != user_id,
                    User.is_active == True
                )
            ).group_by(
                User.id
            ).order_by(
                desc('mutual_friends'),
                desc('followers_count')
            ).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            suggestions = []
            for row in rows:
                suggestion = {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "mutual_friends": row.mutual_friends,
                    "followers_count": row.followers_count,
                    "reason": f"Followed by {row.mutual_friends} of your friends"
                }
                suggestions.append(suggestion)
            
            # If not enough suggestions, add popular users
            if len(suggestions) < limit:
                popular_limit = limit - len(suggestions)
                popular_users = await self._get_popular_users(
                    exclude_id=user_id,
                    limit=popular_limit
                )
                suggestions.extend(popular_users)
            
            # Cache for 10 minutes
            await self.redis.setex(cache_key, 600, json.dumps(suggestions))
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting follow suggestions: {e}")
            return await self._get_popular_users(exclude_id=user_id, limit=limit)
    
    async def _get_popular_users(
        self,
        exclude_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular users (most followers)"""
        try:
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label('followers_count')
            ).outerjoin(
                Follow, Follow.following_id == User.id
            ).where(
                and_(
                    User.id != exclude_id,
                    User.is_active == True
                )
            ).group_by(
                User.id
            ).order_by(
                desc('followers_count'),
                desc(User.created_at)
            ).limit(limit)
            
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
                    "reason": "Popular in the community"
                }
                popular_users.append(user)
            
            return popular_users
            
        except Exception as e:
            logger.error(f"Error getting popular users: {e}")
            return []
    
    async def get_follower_count(self, user_id: int) -> int:
        """Get number of followers for a user"""
        try:
            cache_key = f"user:{user_id}:follower_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                Follow.following_id == user_id
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting follower count: {e}")
            return 0
    
    async def get_following_count(self, user_id: int) -> int:
        """Get number of users a user is following"""
        try:
            cache_key = f"user:{user_id}:following_count"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            stmt = select(func.count()).where(
                Follow.follower_id == user_id
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting following count: {e}")
            return 0
    
    async def get_mutual_follow_count(
        self,
        user1_id: int,
        user2_id: int
    ) -> int:
        """Get number of mutual followers between two users"""
        try:
            cache_key = f"mutual_count:{user1_id}:{user2_id}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return int(cached)
            
            # Users followed by user1
            user1_following = select(Follow.following_id).where(
                Follow.follower_id == user1_id
            ).subquery()
            
            # Users followed by user2
            user2_following = select(Follow.following_id).where(
                Follow.follower_id == user2_id
            ).subquery()
            
            # Count mutual follows
            stmt = select(func.count()).select_from(User).where(
                and_(
                    User.id.in_(user1_following),
                    User.id.in_(user2_following),
                    User.id != user1_id,
                    User.id != user2_id
                )
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting mutual follow count: {e}")
            return 0
    
    async def get_user_follow_stats(self, user_id: int) -> FollowStats:
        """Get follow statistics for a user"""
        try:
            cache_key = f"user:{user_id}:follow_stats"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return FollowStats(**json.loads(cached))
            
            # Get counts
            follower_count = await self.get_follower_count(user_id)
            following_count = await self.get_following_count(user_id)
            
            # Get recent followers (last 7 days)
            from datetime import datetime, timedelta
            
            week_ago = datetime.utcnow() - timedelta(days=7)
            
            recent_stmt = select(func.count()).where(
                and_(
                    Follow.following_id == user_id,
                    Follow.created_at >= week_ago
                )
            )
            
            recent_result = await self.db.execute(recent_stmt)
            recent_followers = recent_result.scalar() or 0
            
            # Get top followers (users with most followers who follow this user)
            top_followers_stmt = select(
                User.id,
                User.username,
                User.profile_picture
            ).join(
                Follow, Follow.follower_id == User.id
            ).where(
                Follow.following_id == user_id
            ).order_by(
                desc(User.followers_count)
            ).limit(5)
            
            top_followers_result = await self.db.execute(top_followers_stmt)
            top_followers = [
                {"id": row[0], "username": row[1], "profile_picture": row[2]}
                for row in top_followers_result.all()
            ]
            
            stats = FollowStats(
                user_id=user_id,
                follower_count=follower_count,
                following_count=following_count,
                recent_followers=recent_followers,
                top_followers=top_followers
            )
            
            # Cache for 5 minutes
            await self.redis.setex(cache_key, 300, json.dumps(stats.dict()))
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user follow stats: {e}")
            return FollowStats(
                user_id=user_id,
                follower_count=0,
                following_count=0,
                recent_followers=0,
                top_followers=[]
            )
    
    async def get_relationship_status(
        self,
        viewer_id: int,
        target_id: int
    ) -> UserRelationship:
        """Get relationship status between two users"""
        try:
            if viewer_id == target_id:
                return UserRelationship(
                    viewer_id=viewer_id,
                    target_id=target_id,
                    status=RelationshipStatus.SELF,
                    you_follow=False,
                    follows_you=False,
                    is_mutual=False
                )
            
            # Check if viewer follows target
            viewer_follows_target = await self.get_follow_relationship(
                follower_id=viewer_id,
                following_id=target_id
            )
            
            # Check if target follows viewer
            target_follows_viewer = await self.get_follow_relationship(
                follower_id=target_id,
                following_id=viewer_id
            )
            
            # Determine status
            status = RelationshipStatus.NONE
            if viewer_follows_target and target_follows_viewer:
                status = RelationshipStatus.MUTUAL
            elif viewer_follows_target:
                status = RelationshipStatus.FOLLOWING
            elif target_follows_viewer:
                status = RelationshipStatus.FOLLOWED_BY
            
            return UserRelationship(
                viewer_id=viewer_id,
                target_id=target_id,
                status=status,
                you_follow=viewer_follows_target is not None,
                follows_you=target_follows_viewer is not None,
                is_mutual=viewer_follows_target is not None and target_follows_viewer is not None
            )
            
        except Exception as e:
            logger.error(f"Error getting relationship status: {e}")
            return UserRelationship(
                viewer_id=viewer_id,
                target_id=target_id,
                status=RelationshipStatus.NONE,
                you_follow=False,
                follows_you=False,
                is_mutual=False
            )
    
    async def search_users(
        self,
        query: str,
        searcher_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Search for users to follow"""
        try:
            cache_key = f"search_users:{query}:{searcher_id}:{skip}:{limit}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return json.loads(cached)
            
            # Build search query
            search_terms = f"%{query}%"
            
            stmt = select(
                User.id,
                User.username,
                User.full_name,
                User.profile_picture,
                User.bio,
                func.coalesce(func.count(Follow.id), 0).label('followers_count'),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == searcher_id,
                            Follow.following_id == User.id
                        )
                    )
                ).label('you_follow'),
                func.exists(
                    select(1).where(
                        and_(
                            Follow.follower_id == User.id,
                            Follow.following_id == searcher_id
                        )
                    )
                ).label('follows_you')
            ).outerjoin(
                Follow, Follow.following_id == User.id
            ).where(
                and_(
                    User.id != searcher_id,
                    User.is_active == True,
                    or_(
                        User.username.ilike(search_terms),
                        User.full_name.ilike(search_terms),
                        User.bio.ilike(search_terms)
                    )
                )
            ).group_by(
                User.id
            ).order_by(
                desc('followers_count'),
                desc(User.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            users = []
            for row in rows:
                user = {
                    "id": row.id,
                    "username": row.username,
                    "full_name": row.full_name,
                    "profile_picture": row.profile_picture,
                    "bio": row.bio,
                    "followers_count": row.followers_count,
                    "you_follow": row.you_follow,
                    "follows_you": row.follows_you
                }
                users.append(user)
            
            # Cache for 2 minutes
            await self.redis.setex(cache_key, 120, json.dumps(users))
            
            return users
            
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []
    
    async def _update_follow_cache(
        self,
        follower_id: int,
        following_id: int,
        action: str
    ):
        """Update cache after follow/unfollow action"""
        try:
            # Invalidate relationship cache
            await self.redis.delete(f"follow:{follower_id}:{following_id}")
            await self.redis.delete(f"follow:{following_id}:{follower_id}")
            
            # Invalidate counts cache
            await self.redis.delete(f"user:{follower_id}:following_count")
            await self.redis.delete(f"user:{following_id}:follower_count")
            
            # Invalidate lists cache
            await self.redis.delete_pattern(f"user:{follower_id}:following:*")
            await self.redis.delete_pattern(f"user:{following_id}:followers:*")
            
            # Invalidate suggestions cache
            await self.redis.delete_pattern(f"user:{follower_id}:follow_suggestions:*")
            await self.redis.delete_pattern(f"user:{following_id}:follow_suggestions:*")
            
            # Invalidate stats cache
            await self.redis.delete(f"user:{follower_id}:follow_stats")
            await self.redis.delete(f"user:{following_id}:follow_stats")
            
            # Invalidate mutual follows cache
            await self.redis.delete_pattern(f"mutual:*{follower_id}*")
            await self.redis.delete_pattern(f"mutual:*{following_id}*")
            
            logger.debug(f"Updated cache for {action}: {follower_id} -> {following_id}")
            
        except Exception as e:
            logger.error(f"Error updating follow cache: {e}")
    
    async def update_user_stats_cache(self, follower_id: int, following_id: int):
        """Update user statistics cache after follow/unfollow"""
        try:
            # Update follower's following stats
            follower_stats_key = f"user:{follower_id}:follow_stats"
            if await self.redis.exists(follower_stats_key):
                follower_stats = await self.redis.get(follower_stats_key)
                if follower_stats:
                    stats = json.loads(follower_stats)
                    # You'd update the counts here based on the action
                    await self.redis.delete(follower_stats_key)
            
            # Update following's follower stats
            following_stats_key = f"user:{following_id}:follow_stats"
            if await self.redis.exists(following_stats_key):
                await self.redis.delete(following_stats_key)
            
        except Exception as e:
            logger.error(f"Error updating user stats cache: {e}")