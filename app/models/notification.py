from sqlalchemy import Column, String, Text, Integer, ForeignKey, Boolean, DateTime, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel

class Notification(BaseModel):
    __tablename__ = "notifications"
    
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    type = Column(String(50), nullable=False)  # like, comment, follow, etc.
    content = Column(Text)
    related_post_id = Column(Integer, ForeignKey("posts.id"), nullable=True)
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    
    # Relationships
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_notifications")
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_notifications")
    
    # Indexes for better performance
    __table_args__ = (
        Index('ix_notifications_receiver_id', 'receiver_id'),
        Index('ix_notifications_sender_id', 'sender_id'),
        Index('ix_notifications_type', 'type'),
        Index('ix_notifications_created_at', 'created_at'),
        Index('ix_notifications_is_read', 'is_read'),
    )