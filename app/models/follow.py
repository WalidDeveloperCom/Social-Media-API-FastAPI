from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel

class Follow(BaseModel):
    __tablename__ = "follows"
    
    follower_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    following_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Relationships
    follower = relationship(
        "User", 
        foreign_keys=[follower_id],
        back_populates="following"
    )
    following = relationship(
        "User", 
        foreign_keys=[following_id],
        back_populates="followers"
    )
    
    # Ensure unique follow relationships
    __table_args__ = (
        UniqueConstraint('follower_id', 'following_id', name='unique_follow'),
        # Index for faster queries
        Index('ix_follows_follower_id', 'follower_id'),
        Index('ix_follows_following_id', 'following_id'),
        Index('ix_follows_created_at', 'created_at'),
    )