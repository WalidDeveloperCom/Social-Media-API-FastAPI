import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update, desc, func
from sqlalchemy.orm import selectinload
import logging

from app.models.user import User
from app.models.post import Post
from app.models.notification import Notification
from app.models.like import Like
from app.models.comment import Comment
from app.models.follow import Follow
from app.schemas.notification_schema import (
    NotificationCreate, 
    NotificationResponse,
    NotificationListResponse,
    NotificationStats,
    NotificationType
)
from app.services.redis_service import RedisService
from app.websocket.manager import WebSocketManager
from app.tasks.email_tasks import send_email_notification
from app.tasks.push_tasks import send_push_notification

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.redis = RedisService()
        self.ws_manager = WebSocketManager()
        
        # Notification templates
        self.templates = {
            NotificationType.LIKE: {
                "title": "New Like",
                "message": "{sender} liked your post",
                "icon": "❤️"
            },
            NotificationType.COMMENT: {
                "title": "New Comment",
                "message": "{sender} commented on your post",
                "icon": "💬"
            },
            NotificationType.REPLY: {
                "title": "Reply to Comment",
                "message": "{sender} replied to your comment",
                "icon": "↪️"
            },
            NotificationType.FOLLOW: {
                "title": "New Follower",
                "message": "{sender} started following you",
                "icon": "👤"
            },
            NotificationType.MENTION: {
                "title": "Mention",
                "message": "{sender} mentioned you in a post",
                "icon": "@"
            },
            NotificationType.SHARE: {
                "title": "Post Shared",
                "message": "{sender} shared your post",
                "icon": "🔄"
            },
            NotificationType.SYSTEM: {
                "title": "System Notification",
                "message": "{content}",
                "icon": "🔔"
            }
        }
    
    async def create_notification(
        self, 
        notification_data: NotificationCreate
    ) -> Notification:
        """Create a new notification"""
        try:
            # Get template for notification type
            template = self.templates.get(
                notification_data.type, 
                self.templates[NotificationType.SYSTEM]
            )
            
            # Format message
            message = template["message"].format(
                sender=notification_data.sender_name or "Someone",
                content=notification_data.content or ""
            )
            
            # Create notification
            notification = Notification(
                receiver_id=notification_data.receiver_id,
                sender_id=notification_data.sender_id,
                type=notification_data.type.value,
                content=message,
                related_post_id=notification_data.related_post_id,
                is_read=False,
                created_at=datetime.utcnow()
            )
            
            self.db.add(notification)
            await self.db.commit()
            await self.db.refresh(notification)
            
            # Get sender info for real-time notification
            sender = None
            if notification_data.sender_id:
                stmt = select(User).where(User.id == notification_data.sender_id)
                result = await self.db.execute(stmt)
                sender = result.scalar_one_or_none()
            
            # Prepare notification data for real-time delivery
            notification_dict = {
                "id": notification.id,
                "type": notification.type,
                "title": template["title"],
                "message": message,
                "icon": template["icon"],
                "sender": {
                    "id": sender.id if sender else None,
                    "username": sender.username if sender else None,
                    "profile_picture": sender.profile_picture if sender else None
                } if sender else None,
                "related_post_id": notification.related_post_id,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat(),
                "read_at": notification.read_at.isoformat() if notification.read_at else None
            }
            
            # Send real-time notification via WebSocket
            await self.ws_manager.send_personal_notification(
                notification_data.receiver_id,
                notification_dict
            )
            
            # Cache notification for quick access
            cache_key = f"user:{notification_data.receiver_id}:latest_notifications"
            await self.redis.lpush(cache_key, json.dumps(notification_dict))
            await self.redis.ltrim(cache_key, 0, 9)  # Keep only 10 latest
            
            # Increment unread count in cache
            unread_key = f"user:{notification_data.receiver_id}:unread_count"
            await self.redis.incr(unread_key)
            
            # Send email notification (async)
            if notification_data.send_email:
                await self.send_email_notification_async(notification_data, notification_dict)
            
            # Send push notification (if enabled)
            if notification_data.send_push:
                await self.send_push_notification_async(notification_data, notification_dict)
            
            logger.info(f"Created notification: {notification.id} for user: {notification_data.receiver_id}")
            
            return notification
            
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            await self.db.rollback()
            raise
    
    async def send_email_notification_async(
        self, 
        notification_data: NotificationCreate,
        notification_dict: Dict[str, Any]
    ):
        """Send email notification asynchronously"""
        try:
            # Get receiver email
            stmt = select(User.email).where(User.id == notification_data.receiver_id)
            result = await self.db.execute(stmt)
            receiver_email = result.scalar_one_or_none()
            
            if receiver_email:
                # Queue email task
                send_email_notification.delay(
                    to_email=receiver_email,
                    subject=notification_dict["title"],
                    template="notification",
                    context={
                        "notification": notification_dict,
                        "user_id": notification_data.receiver_id
                    }
                )
        except Exception as e:
            logger.error(f"Error queuing email notification: {e}")
    
    async def send_push_notification_async(
        self,
        notification_data: NotificationCreate,
        notification_dict: Dict[str, Any]
    ):
        """Send push notification asynchronously"""
        try:
            # Get user's push token from cache
            push_token_key = f"user:{notification_data.receiver_id}:push_token"
            push_token = await self.redis.get(push_token_key)
            
            if push_token:
                # Queue push notification task
                send_push_notification.delay(
                    token=push_token,
                    title=notification_dict["title"],
                    body=notification_dict["message"],
                    data=notification_dict
                )
        except Exception as e:
            logger.error(f"Error queuing push notification: {e}")
    
    async def create_like_notification(
        self,
        post_id: int,
        liker_id: int,
        post_owner_id: int
    ) -> Optional[Notification]:
        """Create notification for a like"""
        try:
            # Don't notify if user liked their own post
            if liker_id == post_owner_id:
                return None
            
            # Check if notification already exists
            existing_stmt = select(Notification).where(
                and_(
                    Notification.receiver_id == post_owner_id,
                    Notification.sender_id == liker_id,
                    Notification.related_post_id == post_id,
                    Notification.type == NotificationType.LIKE.value
                )
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update timestamp if notification exists
                existing.created_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing)
                return existing
            
            # Get liker info
            stmt = select(User.username, User.full_name).where(User.id == liker_id)
            result = await self.db.execute(stmt)
            liker = result.first()
            
            notification_data = NotificationCreate(
                receiver_id=post_owner_id,
                sender_id=liker_id,
                sender_name=liker.full_name or liker.username if liker else None,
                type=NotificationType.LIKE,
                related_post_id=post_id,
                send_email=True,
                send_push=True
            )
            
            return await self.create_notification(notification_data)
            
        except Exception as e:
            logger.error(f"Error creating like notification: {e}")
            return None
    
    async def create_comment_notification(
        self,
        comment_id: int,
        commenter_id: int,
        post_id: int,
        post_owner_id: int,
        parent_comment_id: Optional[int] = None
    ) -> Optional[Notification]:
        """Create notification for a comment"""
        try:
            # Determine notification type and receiver
            if parent_comment_id:
                # This is a reply to a comment
                # Get parent comment author
                stmt = select(Comment.user_id).where(Comment.id == parent_comment_id)
                result = await self.db.execute(stmt)
                parent_comment = result.scalar_one_or_none()
                
                if parent_comment and parent_comment.user_id != commenter_id:
                    receiver_id = parent_comment.user_id
                    notification_type = NotificationType.REPLY
                else:
                    return None
            else:
                # This is a comment on a post
                if commenter_id == post_owner_id:
                    return None
                receiver_id = post_owner_id
                notification_type = NotificationType.COMMENT
            
            # Check if notification already exists
            existing_stmt = select(Notification).where(
                and_(
                    Notification.receiver_id == receiver_id,
                    Notification.sender_id == commenter_id,
                    Notification.related_post_id == post_id,
                    Notification.type == notification_type.value
                )
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update timestamp if notification exists
                existing.created_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing)
                return existing
            
            # Get commenter info
            stmt = select(User.username, User.full_name).where(User.id == commenter_id)
            result = await self.db.execute(stmt)
            commenter = result.first()
            
            notification_data = NotificationCreate(
                receiver_id=receiver_id,
                sender_id=commenter_id,
                sender_name=commenter.full_name or commenter.username if commenter else None,
                type=notification_type,
                related_post_id=post_id,
                content=f"Comment ID: {comment_id}",
                send_email=True,
                send_push=True
            )
            
            return await self.create_notification(notification_data)
            
        except Exception as e:
            logger.error(f"Error creating comment notification: {e}")
            return None
    
    async def create_follow_notification(
        self,
        follower_id: int,
        following_id: int
    ) -> Optional[Notification]:
        """Create notification for a follow"""
        try:
            # Don't notify if user followed themselves
            if follower_id == following_id:
                return None
            
            # Check if notification already exists
            existing_stmt = select(Notification).where(
                and_(
                    Notification.receiver_id == following_id,
                    Notification.sender_id == follower_id,
                    Notification.type == NotificationType.FOLLOW.value
                )
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                # Update timestamp if notification exists
                existing.created_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing)
                return existing
            
            # Get follower info
            stmt = select(User.username, User.full_name).where(User.id == follower_id)
            result = await self.db.execute(stmt)
            follower = result.first()
            
            notification_data = NotificationCreate(
                receiver_id=following_id,
                sender_id=follower_id,
                sender_name=follower.full_name or follower.username if follower else None,
                type=NotificationType.FOLLOW,
                send_email=True,
                send_push=True
            )
            
            return await self.create_notification(notification_data)
            
        except Exception as e:
            logger.error(f"Error creating follow notification: {e}")
            return None
    
    async def create_mention_notification(
        self,
        post_id: int,
        sender_id: int,
        mentioned_user_ids: List[int]
    ) -> List[Notification]:
        """Create notifications for mentions in a post"""
        notifications = []
        
        for user_id in mentioned_user_ids:
            if user_id == sender_id:
                continue
                
            try:
                # Get sender info
                stmt = select(User.username, User.full_name).where(User.id == sender_id)
                result = await self.db.execute(stmt)
                sender = result.first()
                
                notification_data = NotificationCreate(
                    receiver_id=user_id,
                    sender_id=sender_id,
                    sender_name=sender.full_name or sender.username if sender else None,
                    type=NotificationType.MENTION,
                    related_post_id=post_id,
                    send_email=True,
                    send_push=True
                )
                
                notification = await self.create_notification(notification_data)
                if notification:
                    notifications.append(notification)
                    
            except Exception as e:
                logger.error(f"Error creating mention notification for user {user_id}: {e}")
                continue
        
        return notifications
    
    async def get_user_notifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        unread_only: bool = False
    ) -> NotificationListResponse:
        """Get notifications for a user"""
        try:
            # Try to get from cache first
            cache_key = f"user:{user_id}:notifications:{skip}:{limit}:{unread_only}"
            cached = await self.redis.get(cache_key)
            
            if cached:
                return NotificationListResponse(**cached)
            
            # Build query
            stmt = select(Notification).where(
                Notification.receiver_id == user_id
            ).options(
                selectinload(Notification.sender)
            )
            
            if unread_only:
                stmt = stmt.where(Notification.is_read == False)
            
            # Get total count
            count_stmt = select(func.count()).select_from(
                stmt.subquery()
            )
            count_result = await self.db.execute(count_stmt)
            total = count_result.scalar()
            
            # Get notifications with pagination
            stmt = stmt.order_by(
                desc(Notification.created_at)
            ).offset(skip).limit(limit)
            
            result = await self.db.execute(stmt)
            notifications = result.scalars().all()
            
            # Convert to response format
            notification_responses = []
            for notification in notifications:
                response = await self._notification_to_response(notification)
                notification_responses.append(response)
            
            # Get unread count
            unread_count = await self.get_unread_count(user_id)
            
            response = NotificationListResponse(
                notifications=notification_responses,
                total=total,
                skip=skip,
                limit=limit,
                unread_count=unread_count
            )
            
            # Cache for 30 seconds
            await self.redis.setex(cache_key, 30, response.dict())
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return NotificationListResponse(
                notifications=[],
                total=0,
                skip=skip,
                limit=limit,
                unread_count=0
            )
    
    async def _notification_to_response(
        self, 
        notification: Notification
    ) -> NotificationResponse:
        """Convert notification model to response schema"""
        sender_info = None
        if notification.sender:
            sender_info = {
                "id": notification.sender.id,
                "username": notification.sender.username,
                "full_name": notification.sender.full_name,
                "profile_picture": notification.sender.profile_picture
            }
        
        return NotificationResponse(
            id=notification.id,
            type=notification.type,
            content=notification.content,
            sender=sender_info,
            related_post_id=notification.related_post_id,
            is_read=notification.is_read,
            created_at=notification.created_at,
            read_at=notification.read_at
        )
    
    async def mark_as_read(
        self,
        notification_id: int,
        user_id: int
    ) -> Optional[Notification]:
        """Mark a notification as read"""
        try:
            stmt = select(Notification).where(
                and_(
                    Notification.id == notification_id,
                    Notification.receiver_id == user_id
                )
            )
            result = await self.db.execute(stmt)
            notification = result.scalar_one_or_none()
            
            if not notification:
                return None
            
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = datetime.utcnow()
                
                await self.db.commit()
                await self.db.refresh(notification)
                
                # Update cache
                unread_key = f"user:{user_id}:unread_count"
                current = await self.redis.get(unread_key)
                if current and int(current) > 0:
                    await self.redis.decr(unread_key)
                
                # Invalidate notifications cache
                await self.redis.delete_pattern(f"user:{user_id}:notifications:*")
                
                logger.info(f"Marked notification {notification_id} as read for user {user_id}")
            
            return notification
            
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            await self.db.rollback()
            return None
    
    async def mark_all_as_read(self, user_id: int) -> int:
        """Mark all notifications as read for a user"""
        try:
            # Update in database
            stmt = update(Notification).where(
                and_(
                    Notification.receiver_id == user_id,
                    Notification.is_read == False
                )
            ).values(
                is_read=True,
                read_at=datetime.utcnow()
            )
            
            result = await self.db.execute(stmt)
            await self.db.commit()
            updated_count = result.rowcount
            
            if updated_count > 0:
                # Reset unread count cache
                unread_key = f"user:{user_id}:unread_count"
                await self.redis.set(unread_key, 0)
                
                # Invalidate notifications cache
                await self.redis.delete_pattern(f"user:{user_id}:notifications:*")
                
                logger.info(f"Marked {updated_count} notifications as read for user {user_id}")
            
            return updated_count
            
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            await self.db.rollback()
            return 0
    
    async def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications for a user"""
        try:
            # Try cache first
            cache_key = f"user:{user_id}:unread_count"
            cached = await self.redis.get(cache_key)
            
            if cached is not None:
                return int(cached)
            
            # Query database
            stmt = select(func.count()).where(
                and_(
                    Notification.receiver_id == user_id,
                    Notification.is_read == False
                )
            )
            
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            # Cache for 1 minute
            await self.redis.setex(cache_key, 60, count)
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0
    
    async def get_notification_stats(self, user_id: int) -> NotificationStats:
        """Get notification statistics for a user"""
        try:
            # Get counts by type
            stmt = select(
                Notification.type,
                func.count().label('count')
            ).where(
                Notification.receiver_id == user_id
            ).group_by(
                Notification.type
            )
            
            result = await self.db.execute(stmt)
            rows = result.all()
            
            # Convert to dictionary
            counts_by_type = {row.type: row.count for row in rows}
            
            # Get total counts
            total_stmt = select(func.count()).where(
                Notification.receiver_id == user_id
            )
            total_result = await self.db.execute(total_stmt)
            total_count = total_result.scalar() or 0
            
            # Get unread count
            unread_count = await self.get_unread_count(user_id)
            
            # Get recent activity (last 24 hours)
            yesterday = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            recent_stmt = select(func.count()).where(
                and_(
                    Notification.receiver_id == user_id,
                    Notification.created_at >= yesterday
                )
            )
            recent_result = await self.db.execute(recent_stmt)
            last_24h_count = recent_result.scalar() or 0
            
            return NotificationStats(
                total_count=total_count,
                unread_count=unread_count,
                last_24h_count=last_24h_count,
                counts_by_type=counts_by_type
            )
            
        except Exception as e:
            logger.error(f"Error getting notification stats: {e}")
            return NotificationStats(
                total_count=0,
                unread_count=0,
                last_24h_count=0,
                counts_by_type={}
            )
    
    async def delete_notification(
        self,
        notification_id: int,
        user_id: int
    ) -> bool:
        """Delete a notification"""
        try:
            stmt = select(Notification).where(
                and_(
                    Notification.id == notification_id,
                    Notification.receiver_id == user_id
                )
            )
            result = await self.db.execute(stmt)
            notification = result.scalar_one_or_none()
            
            if not notification:
                return False
            
            was_unread = not notification.is_read
            
            await self.db.delete(notification)
            await self.db.commit()
            
            # Update cache if notification was unread
            if was_unread:
                unread_key = f"user:{user_id}:unread_count"
                current = await self.redis.get(unread_key)
                if current and int(current) > 0:
                    await self.redis.decr(unread_key)
            
            # Invalidate cache
            await self.redis.delete_pattern(f"user:{user_id}:notifications:*")
            await self.redis.delete_pattern(f"user:{user_id}:latest_notifications")
            
            logger.info(f"Deleted notification {notification_id} for user {user_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            await self.db.rollback()
            return False
    
    async def delete_all_notifications(self, user_id: int) -> int:
        """Delete all notifications for a user"""
        try:
            # Get count before deletion
            stmt = select(func.count()).where(
                Notification.receiver_id == user_id
            )
            result = await self.db.execute(stmt)
            count = result.scalar() or 0
            
            if count == 0:
                return 0
            
            # Delete notifications
            delete_stmt = Notification.__table__.delete().where(
                Notification.receiver_id == user_id
            )
            
            await self.db.execute(delete_stmt)
            await self.db.commit()
            
            # Clear cache
            await self.redis.delete_pattern(f"user:{user_id}:notifications:*")
            await self.redis.delete(f"user:{user_id}:unread_count")
            await self.redis.delete(f"user:{user_id}:latest_notifications")
            
            logger.info(f"Deleted all {count} notifications for user {user_id}")
            
            return count
            
        except Exception as e:
            logger.error(f"Error deleting all notifications: {e}")
            await self.db.rollback()
            return 0
    
    async def get_latest_notifications(
        self, 
        user_id: int, 
        limit: int = 10
    ) -> List[NotificationResponse]:
        """Get latest notifications (cached)"""
        try:
            cache_key = f"user:{user_id}:latest_notifications"
            cached = await self.redis.lrange(cache_key, 0, limit - 1)
            
            if cached:
                notifications = [json.loads(item) for item in cached]
                # Convert to NotificationResponse objects
                return [
                    NotificationResponse(**notification)
                    for notification in notifications
                ]
            
            # Get from database if not in cache
            stmt = select(Notification).where(
                Notification.receiver_id == user_id
            ).options(
                selectinload(Notification.sender)
            ).order_by(
                desc(Notification.created_at)
            ).limit(limit)
            
            result = await self.db.execute(stmt)
            notifications = result.scalars().all()
            
            # Convert to response format
            response_notifications = []
            for notification in notifications:
                response = await self._notification_to_response(notification)
                response_notifications.append(response)
                
                # Cache the notification
                await self.redis.lpush(cache_key, json.dumps(response.dict()))
            
            # Trim cache to limit
            await self.redis.ltrim(cache_key, 0, limit - 1)
            
            return response_notifications
            
        except Exception as e:
            logger.error(f"Error getting latest notifications: {e}")
            return []
    
    async def subscribe_to_notifications(
        self,
        user_id: int,
        websocket
    ):
        """Subscribe user to real-time notifications"""
        await self.ws_manager.connect(user_id, websocket)
    
    async def unsubscribe_from_notifications(
        self,
        user_id: int,
        websocket
    ):
        """Unsubscribe user from real-time notifications"""
        await self.ws_manager.disconnect(user_id, websocket)
    
    async def cleanup_old_notifications(self, days: int = 30):
        """Clean up notifications older than specified days"""
        try:
            cutoff_date = datetime.utcnow().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            
            stmt = select(Notification).where(
                Notification.created_at < cutoff_date
            )
            
            result = await self.db.execute(stmt)
            old_notifications = result.scalars().all()
            
            count = len(old_notifications)
            
            if count > 0:
                # Delete old notifications
                delete_stmt = Notification.__table__.delete().where(
                    Notification.created_at < cutoff_date
                )
                
                await self.db.execute(delete_stmt)
                await self.db.commit()
                
                # Clear cache for affected users
                user_ids = {notification.receiver_id for notification in old_notifications}
                for user_id in user_ids:
                    await self.redis.delete_pattern(f"user:{user_id}:notifications:*")
                    await self.redis.delete(f"user:{user_id}:latest_notifications")
                
                logger.info(f"Cleaned up {count} notifications older than {days} days")
            
            return count
            
        except Exception as e:
            logger.error(f"Error cleaning up old notifications: {e}")
            await self.db.rollback()
            return 0