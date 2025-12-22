import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import get_db
from app.config import settings
import os

# Set testing mode
settings.TESTING = True

# Test database URL - in-memory SQLite
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create test session factory
TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override dependency for testing"""
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Override the dependency
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_client() -> Generator:
    """Create test client"""
    with TestClient(app) as client:
        yield client

@pytest.fixture(scope="session")
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """Create test database session"""
    async with TestSessionLocal() as session:
        yield session

@pytest.fixture(scope="session", autouse=True)
async def setup_test_database():
    """Setup test database with tables"""
    from app.models import Base
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await test_engine.dispose()

@pytest.fixture
async def test_user(test_db: AsyncSession):
    """Create a test user"""
    from app.models.user import User
    from app.services.auth_service import AuthService
    
    auth_service = AuthService(test_db)
    
    # Create test user
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User"
    }
    
    user = await auth_service.create_user(**user_data)
    
    yield user
    
    # Cleanup
    await test_db.delete(user)
    await test_db.commit()