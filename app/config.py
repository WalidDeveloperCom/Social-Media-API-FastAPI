from pydantic_settings import BaseSettings
from typing import List, Optional, Literal
from functools import lru_cache
import os

class Settings(BaseSettings):
    # Environment
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    
    # Project
    PROJECT_NAME: str = "Social Media API"
    VERSION: str = "1.0.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/social_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    
    # SQLite for testing
    TEST_DATABASE_URL: str = "sqlite+aiosqlite:///./test.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_POOL_SIZE: int = 10
    
    # Test Redis
    TEST_REDIS_URL: str = "redis://localhost:6379/1"  # Use DB 1 for testing
    
    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    
    # Test Elasticsearch (mock or skip in tests)
    TEST_ELASTICSEARCH_URL: Optional[str] = None
    
    # JWT
    SECRET_KEY: str = "your-secret-key-here-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Test JWT Secret (different from production)
    TEST_SECRET_KEY: str = "test-secret-key"
    
    # Security
    CORS_ORIGINS: List[str] = ["*"]
    API_V1_PREFIX: str = "/api/v1"
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # File upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    ALLOWED_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".mp4"]
    
    # Testing
    TESTING: bool = False
    
    @property
    def is_testing(self) -> bool:
        return self.TESTING or self.ENVIRONMENT == "testing"
    
    @property
    def database_url(self) -> str:
        """Get appropriate database URL based on environment"""
        if self.is_testing:
            return self.TEST_DATABASE_URL
        return self.DATABASE_URL
    
    @property
    def redis_url(self) -> str:
        """Get appropriate Redis URL based on environment"""
        if self.is_testing:
            return self.TEST_REDIS_URL
        return self.REDIS_URL
    
    @property
    def secret_key(self) -> str:
        """Get appropriate secret key based on environment"""
        if self.is_testing:
            return self.TEST_SECRET_KEY
        return self.SECRET_KEY
    
    class Config:
        env_file = ".env"
        case_sensitive = True

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()