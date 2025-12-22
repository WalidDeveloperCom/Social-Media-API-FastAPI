from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class LikeType(str, Enum):
    POST = "post"
    COMMENT = "comment"

class LikeBase(BaseModel):
    user_id: int
    post_id: Optional[int] = None
    comment_id: Optional[int] = None
    like_type: LikeType

class LikeCreate(LikeBase):
    pass

class LikeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    post_id: Optional[int] = None
    comment_id: Optional[int] = None
    like_type: Optional[str] = None
    created_at: datetime

class UserInfo(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None

class LikeInfo(BaseModel):
    user: UserInfo
    liked_at: str
    you_follow: Optional[bool] = None
    follows_you: Optional[bool] = None

class LikeListResponse(BaseModel):
    likes: List[Dict[str, Any]]
    total: int
    skip: int
    limit: int
    post_id: Optional[int] = None
    comment_id: Optional[int] = None
    user_id: Optional[int] = None
    like_type: Optional[LikeType] = None
    user_liked: Optional[bool] = None

class LikeStats(BaseModel):
    post_id: Optional[int] = None
    user_id: Optional[int] = None
    total_likes: int = 0
    post_likes: Optional[int] = None
    comment_likes: Optional[int] = None
    recent_likes: Optional[int] = None
    likes_by_period: Optional[Dict[str, int]] = None
    content_type_distribution: Optional[Dict[str, int]] = None
    top_likers: Optional[List[Dict[str, Any]]] = None
    top_liked_content: Optional[List[Dict[str, Any]]] = None
    like_timeline: Optional[Dict[str, int]] = None