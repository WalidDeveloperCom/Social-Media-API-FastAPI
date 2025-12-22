import pytest
from httpx import AsyncClient
from app.services.auth_service import AuthService
from app.services.post_service import PostService

@pytest.mark.asyncio
async def test_create_post(test_client: AsyncClient, test_db):
    """Test creating a post"""
    # Create user and get token
    auth_service = AuthService(test_db)
    user = await auth_service.create_user(
        username="postuser",
        email="post@example.com",
        password="Password123!",
        full_name="Post User"
    )
    
    login_response = await test_client.post("/api/v1/auth/login", data={
        "username": "postuser",
        "password": "Password123!"
    })
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create post
    post_data = {
        "content": "This is a test post",
        "is_public": True
    }
    
    response = await test_client.post(
        "/api/v1/posts/",
        params=post_data,
        headers=headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == post_data["content"]
    assert data["user_id"] == user.id
    assert data["is_public"] == post_data["is_public"]

@pytest.mark.asyncio
async def test_get_posts(test_client: AsyncClient, test_db):
    """Test getting posts"""
    # Create user and posts
    auth_service = AuthService(test_db)
    post_service = PostService(test_db)
    
    user = await auth_service.create_user(
        username="getpostsuser",
        email="getposts@example.com",
        password="Password123!",
        full_name="Get Posts User"
    )
    
    # Create some posts
    for i in range(3):
        await post_service.create_post(
            user_id=user.id,
            content=f"Test post {i}",
            is_public=True
        )
    
    login_response = await test_client.post("/api/v1/auth/login", data={
        "username": "getpostsuser",
        "password": "Password123!"
    })
    token = login_response.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Get posts
    response = await test_client.get("/api/v1/posts/", headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3  # Should have 3 posts