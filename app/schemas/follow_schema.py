from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class RelationshipStatus(str, Enum):
    NONE = "none"
    FOLLOWING = "following"
    FOLLOWED_BY = "followed_by"
    MUTUAL = "mutual"
    SELF = "self"

class FollowBase(BaseModel):
    follower_id: int
    following_id: int

class FollowCreate(FollowBase):
    pass

class FollowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    follower_id: int
    following_id: int
    created_at: datetime

class FollowerInfo(BaseModel):
    id: int
    username: str
    full_name: Optional[str] = None
    profile_picture: Optional[str] = None
    bio: Optional[str] = None
    followers_count: int = 0
    you_follow: bool = False
    follows_you: bool = False

class FollowListResponse(BaseModel):
    followers: List[Dict[str, Any]]  # Can be followers or following
    total: int
    skip: int
    limit: int
    user_id: int
    username: str
    follows_you: Optional[bool] = None
    you_follow: Optional[bool] = None

class FollowStats(BaseModel):
    user_id: int
    follower_count: int
    following_count: int
    recent_followers: int = 0  # Last 7 days
    top_followers: List[Dict[str, Any]] = []
    relationship: Optional['UserRelationship'] = None

class UserRelationship(BaseModel):
    viewer_id: int
    target_id: int
    status: RelationshipStatus
    you_follow: bool
    follows_you: bool
    is_mutual: bool

# For circular references
FollowStats.model_rebuild()