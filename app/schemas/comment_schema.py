from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class CommentBase(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    parent_id: Optional[int] = None

class CommentCreate(CommentBase):
    pass

class CommentUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

class UserInfo(BaseModel):
    id: int
    username: str
    profile_picture: Optional[str] = None

class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    post_id: int
    user_id: int
    content: str
    parent_id: Optional[int] = None
    like_count: int = 0
    liked: bool = False
    created_at: datetime
    updated_at: datetime
    user: UserInfo

class CommentTreeResponse(CommentResponse):
    replies: List['CommentTreeResponse'] = []

class CommentListResponse(BaseModel):
    comments: List[CommentResponse]
    total: int
    skip: int
    limit: int
    post_id: Optional[int] = None

class CommentStats(BaseModel):
    comment_id: int
    like_count: int
    reply_count: int
    unique_likers: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# For nested models
CommentTreeResponse.model_rebuild()