import pytest
from httpx import AsyncClient
from app.main import app
from app.config import settings
from app.models.user import User
from app.services.auth_service import AuthService

@pytest.mark.asyncio
async def test_register_user(test_client: AsyncClient, test_db):
    """Test user registration"""
    user_data = {
        "username": "newuser",
        "email": "newuser@example.com",
        "password": "Password123!",
        "full_name": "New User"
    }
    
    response = await test_client.post("/api/v1/auth/register", json=user_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user_data["username"]
    assert data["email"] == user_data["email"]
    assert "id" in data
    assert "password" not in data  # Password should not be in response

@pytest.mark.asyncio
async def test_login_user(test_client: AsyncClient, test_db):
    """Test user login"""
    # First create a user
    auth_service = AuthService(test_db)
    user_data = {
        "username": "loginuser",
        "email": "login@example.com",
        "password": "Password123!",
        "full_name": "Login User"
    }
    
    await auth_service.create_user(**user_data)
    
    # Test login
    login_data = {
        "username": "loginuser",
        "password": "Password123!"
    }
    
    response = await test_client.post("/api/v1/auth/login", data=login_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_protected_endpoint(test_client: AsyncClient, test_db):
    """Test accessing protected endpoint"""
    # Create user and get token
    auth_service = AuthService(test_db)
    user_data = {
        "username": "protecteduser",
        "email": "protected@example.com",
        "password": "Password123!",
        "full_name": "Protected User"
    }
    
    user = await auth_service.create_user(**user_data)
    
    login_data = {
        "username": "protecteduser",
        "password": "Password123!"
    }
    
    login_response = await test_client.post("/api/v1/auth/login", data=login_data)
    token = login_response.json()["access_token"]
    
    # Test protected endpoint
    headers = {"Authorization": f"Bearer {token}"}
    response = await test_client.get("/api/v1/users/me", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == user_data["username"]