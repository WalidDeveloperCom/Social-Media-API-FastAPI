from sqlalchemy import Column, Text, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Comment(BaseModel):
    __tablename__ = "comments"
    
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")
    parent = relationship(
        "Comment", 
        remote_side="Comment.id",
        backref="replies",
        foreign_keys=[parent_id]
    )
    likes = relationship("Like", back_populates="comment", cascade="all, delete-orphan")
    
    # Denormalized for performance
    like_count = Column(Integer, default=0, nullable=False)
    
    # Indexes for better performance
    __table_args__ = (
        Index('ix_comments_post_id', 'post_id'),
        Index('ix_comments_user_id', 'user_id'),
        Index('ix_comments_parent_id', 'parent_id'),
        Index('ix_comments_created_at', 'created_at'),
        Index('ix_comments_like_count', 'like_count'),
    )