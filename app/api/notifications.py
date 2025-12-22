from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import json
import logging

from app.schemas.notification_schema import (
    NotificationResponse,
    NotificationListResponse,
    NotificationStats,
    NotificationUpdate,
    WebSocketNotification
)
from app.services.notification_service import NotificationService
from app.services.auth_service import get_current_user
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's notifications"""
    try:
        service = NotificationService(db)
        return await service.get_user_notifications(
            user_id=current_user.id,
            skip=skip,
            limit=limit,
            unread_only=unread_only
        )
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notifications"
        )

@router.get("/latest", response_model=List[NotificationResponse])
async def get_latest_notifications(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get latest notifications"""
    try:
        service = NotificationService(db)
        return await service.get_latest_notifications(
            user_id=current_user.id,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Error getting latest notifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get latest notifications"
        )

@router.get("/stats", response_model=NotificationStats)
async def get_notification_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get notification statistics"""
    try:
        service = NotificationService(db)
        return await service.get_notification_stats(user_id=current_user.id)
    except Exception as e:
        logger.error(f"Error getting notification stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notification stats"
        )

@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark a notification as read"""
    try:
        service = NotificationService(db)
        notification = await service.mark_as_read(
            notification_id=notification_id,
            user_id=current_user.id
        )
        
        if not notification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"message": "Notification marked as read"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read"
        )

@router.put("/read-all")
async def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Mark all notifications as read"""
    try:
        service = NotificationService(db)
        count = await service.mark_all_as_read(user_id=current_user.id)
        
        return {"message": f"Marked {count} notifications as read"}
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark all notifications as read"
        )

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a notification"""
    try:
        service = NotificationService(db)
        deleted = await service.delete_notification(
            notification_id=notification_id,
            user_id=current_user.id
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"message": "Notification deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete notification"
        )

@router.delete("/")
async def delete_all_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete all notifications"""
    try:
        service = NotificationService(db)
        count = await service.delete_all_notifications(user_id=current_user.id)
        
        return {"message": f"Deleted {count} notifications"}
    except Exception as e:
        logger.error(f"Error deleting all notifications: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete all notifications"
        )

@router.websocket("/ws")
async def websocket_notifications(
    websocket: WebSocket,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """WebSocket endpoint for real-time notifications"""
    try:
        # Verify token and get user
        from app.services.auth_service import AuthService
        
        auth_service = AuthService(db)
        token_data = await auth_service.verify_token(token)
        
        if not token_data:
            await websocket.close(code=1008)  # Policy violation
            return
        
        # Get user
        from sqlalchemy import select
        
        stmt = select(User).where(User.id == token_data.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            await websocket.close(code=1008)
            return
        
        # Subscribe to notifications
        service = NotificationService(db)
        await service.subscribe_to_notifications(user.id, websocket)
        
        # Send initial unread count
        unread_count = await service.get_unread_count(user.id)
        await websocket.send_text(json.dumps({
            "type": "init",
            "data": {"unread_count": unread_count}
        }))
        
        # Keep connection alive and handle messages
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "data": {"timestamp": message.get("timestamp")}
                    }))
                
                elif message.get("type") == "mark_as_read":
                    notification_id = message.get("notification_id")
                    if notification_id:
                        await service.mark_as_read(notification_id, user.id)
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user.id}")
        finally:
            await service.unsubscribe_from_notifications(user.id, websocket)
            
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011)  # Internal error
        except:
            pass