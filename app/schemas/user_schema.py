from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    bio: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[str] = None

class UserInDB(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_active: bool
    is_verified: bool
    profile_picture: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

class UserPublic(UserInDB):
    followers_count: int = 0
    following_count: int = 0
    posts_count: int = 0
    # Relationship status with current user
    you_follow: bool = False
    follows_you: bool = False
    is_mutual: bool = False

class UserStats(BaseModel):
    """User statistics"""
    posts_count: int = 0
    followers_count: int = 0
    following_count: int = 0
    likes_count: int = 0
    comments_count: int = 0
    total_views: int = 0
    engagement_rate: float = 0.0

class UserSearchResult(BaseModel):
    """User search result"""
    id: int
    username: str
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None
    bio: Optional[str] = None
    followers_count: int = 0
    you_follow: bool = False
    follows_you: bool = False
    relevance_score: float = 0.0

class UserListResponse(BaseModel):
    """User list response with pagination"""
    users: List[UserPublic]
    total: int
    skip: int
    limit: int

# For backward compatibility
Token = dict  # Defined in auth_schema.py
TokenData = dict  # Defined in auth_schema.py