from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel

class Post(BaseModel):
    __tablename__ = "posts"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    media_url = Column(String(255))
    media_type = Column(String(20))  # image, video, etc.
    is_public = Column(Boolean, default=True)
    location = Column(String(100))
    
    # Relationships
    user = relationship("User", back_populates="posts")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")
    
    # Denormalized counts for performance
    like_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    share_count = Column(Integer, default=0, nullable=False)
    
    # Indexes for better performance
    __table_args__ = (
        Index('ix_posts_user_id', 'user_id'),
        Index('ix_posts_created_at', 'created_at'),
        Index('ix_posts_is_public', 'is_public'),
        Index('ix_posts_like_count', 'like_count'),
    )