from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum

class NotificationType(str, Enum):
    LIKE = "like"
    COMMENT = "comment"
    REPLY = "reply"
    FOLLOW = "follow"
    MENTION = "mention"
    SHARE = "share"
    SYSTEM = "system"

class NotificationBase(BaseModel):
    receiver_id: int
    sender_id: Optional[int] = None
    sender_name: Optional[str] = None
    type: NotificationType
    content: Optional[str] = None
    related_post_id: Optional[int] = None
    send_email: bool = False
    send_push: bool = False

class NotificationCreate(NotificationBase):
    pass

class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None

class SenderInfo(BaseModel):
    id: Optional[int] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None

class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    type: str
    content: str
    sender: Optional[SenderInfo] = None
    related_post_id: Optional[int] = None
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime] = None

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int
    skip: int
    limit: int
    unread_count: int

class NotificationStats(BaseModel):
    total_count: int
    unread_count: int
    last_24h_count: int
    counts_by_type: Dict[str, int]

class WebSocketNotification(BaseModel):
    action: str  # "new", "read", "delete"
    notification: NotificationResponse