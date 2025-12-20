from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

class PostBase(BaseModel):
    content: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    is_public: bool = True
    location: Optional[str] = None

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    content: Optional[str] = None
    is_public: Optional[bool] = None
    location: Optional[str] = None

class PostInDB(PostBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    created_at: datetime
    updated_at: datetime

class PostWithUser(PostInDB):
    user: Optional[dict] = None
    liked: bool = False