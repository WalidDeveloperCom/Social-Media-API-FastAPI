from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, CheckConstraint, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel

class Like(BaseModel):
    __tablename__ = "likes"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    like_type = Column(String(20))  # 'post', 'comment'
    
    # Relationships
    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")
    comment = relationship("Comment", back_populates="likes")
    
    # Ensure like is for either post or comment, not both
    __table_args__ = (
        # Unique constraints
        Index('ix_likes_user_post', 'user_id', 'post_id', unique=True, postgresql_where=post_id.is_not(None)),
        Index('ix_likes_user_comment', 'user_id', 'comment_id', unique=True, postgresql_where=comment_id.is_not(None)),
        
        # Check constraint
        CheckConstraint(
            '(post_id IS NOT NULL AND comment_id IS NULL) OR (post_id IS NULL AND comment_id IS NOT NULL)',
            name='check_like_target'
        ),
        
        # Indexes for performance
        Index('ix_likes_post_id', 'post_id'),
        Index('ix_likes_comment_id', 'comment_id'),
        Index('ix_likes_user_id', 'user_id'),
        Index('ix_likes_created_at', 'created_at'),
    )