from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"

class LoginRequest(BaseModel):
    """Schema for login request"""
    username_or_email: str = Field(..., description="Username or email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password")

class RegisterRequest(BaseModel):
    """Schema for registration request"""
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r'^[a-zA-Z0-9_]+$',
        description="Username (letters, numbers, underscores only)"
    )
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="Password (min 8 characters)"
    )
    full_name: Optional[str] = Field(None, max_length=100, description="Full name")
    bio: Optional[str] = Field(None, max_length=500, description="Bio")

class PasswordResetRequest(BaseModel):
    """Schema for password reset request"""
    email: EmailStr = Field(..., description="Email address")

class PasswordResetConfirm(BaseModel):
    """Schema for password reset confirmation"""
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New password"
    )

class ChangePasswordRequest(BaseModel):
    """Schema for changing password"""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="New password"
    )

class EmailVerificationRequest(BaseModel):
    """Schema for email verification request"""
    token: str = Field(..., description="Email verification token")

class TokenResponse(BaseModel):
    """Schema for token response"""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")

class TokenData(BaseModel):
    """Schema for token payload data"""
    user_id: int = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email")
    is_active: bool = Field(default=True, description="User active status")
    is_verified: bool = Field(default=False, description="Email verified status")
    exp: Optional[int] = Field(None, description="Expiration timestamp")

class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str = Field(..., description="Refresh token")

class LogoutRequest(BaseModel):
    """Schema for logout request"""
    refresh_token: Optional[str] = Field(None, description="Refresh token to invalidate")

class OAuthProvider(str, Enum):
    """OAuth provider types"""
    GOOGLE = "google"
    FACEBOOK = "facebook"
    GITHUB = "github"
    TWITTER = "twitter"

class OAuthLoginRequest(BaseModel):
    """Schema for OAuth login request"""
    provider: OAuthProvider = Field(..., description="OAuth provider")
    token: str = Field(..., description="OAuth access token")
    redirect_uri: Optional[str] = Field(None, description="OAuth redirect URI")

class OAuthUserInfo(BaseModel):
    """Schema for OAuth user information"""
    provider: OAuthProvider = Field(..., description="OAuth provider")
    provider_user_id: str = Field(..., description="User ID from provider")
    email: Optional[EmailStr] = Field(None, description="Email from provider")
    username: Optional[str] = Field(None, description="Username from provider")
    full_name: Optional[str] = Field(None, description="Full name from provider")
    avatar_url: Optional[str] = Field(None, description="Avatar URL from provider")

class TwoFactorRequest(BaseModel):
    """Schema for 2FA request"""
    code: str = Field(..., min_length=6, max_length=6, description="2FA code")

class TwoFactorSetupRequest(BaseModel):
    """Schema for 2FA setup request"""
    enable: bool = Field(..., description="Enable or disable 2FA")

class TwoFactorSetupResponse(BaseModel):
    """Schema for 2FA setup response"""
    qr_code_url: str = Field(..., description="QR code URL for 2FA setup")
    secret_key: str = Field(..., description="Secret key for manual setup")
    backup_codes: List[str] = Field(..., description="Backup codes")

class SessionInfo(BaseModel):
    """Schema for session information"""
    model_config = ConfigDict(from_attributes=True)
    
    session_id: str = Field(..., description="Session ID")
    user_agent: Optional[str] = Field(None, description="User agent")
    ip_address: Optional[str] = Field(None, description="IP address")
    created_at: datetime = Field(..., description="Session creation time")
    last_activity: datetime = Field(..., description="Last activity time")
    is_current: bool = Field(default=False, description="Is current session")

class SessionListResponse(BaseModel):
    """Schema for session list response"""
    sessions: List[SessionInfo] = Field(..., description="List of sessions")
    total: int = Field(..., description="Total number of sessions")

class SecurityLog(BaseModel):
    """Schema for security log entry"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(..., description="Log entry ID")
    user_id: int = Field(..., description="User ID")
    action: str = Field(..., description="Action performed")
    ip_address: Optional[str] = Field(None, description="IP address")
    user_agent: Optional[str] = Field(None, description="User agent")
    status: str = Field(..., description="Status (success/failure)")
    details: Optional[str] = Field(None, description="Additional details")
    created_at: datetime = Field(..., description="Creation timestamp")

class SecurityLogResponse(BaseModel):
    """Schema for security log response"""
    logs: List[SecurityLog] = Field(..., description="List of security logs")
    total: int = Field(..., description="Total number of logs")
    skip: int = Field(..., description="Skip value for pagination")
    limit: int = Field(..., description="Limit value for pagination")

class PasswordStrengthResponse(BaseModel):
    """Schema for password strength response"""
    score: int = Field(..., ge=0, le=100, description="Password strength score (0-100)")
    strength: str = Field(..., description="Password strength (very_weak, weak, moderate, strong, very_strong)")
    suggestions: List[str] = Field(default_factory=list, description="Password improvement suggestions")

class AuthStatusResponse(BaseModel):
    """Schema for authentication status response"""
    is_authenticated: bool = Field(..., description="Whether user is authenticated")
    user_id: Optional[int] = Field(None, description="User ID if authenticated")
    username: Optional[str] = Field(None, description="Username if authenticated")
    requires_2fa: bool = Field(default=False, description="Whether 2FA is required")
    session_count: int = Field(default=0, description="Number of active sessions")

class DeviceInfo(BaseModel):
    """Schema for device information"""
    device_id: str = Field(..., description="Device identifier")
    device_name: Optional[str] = Field(None, description="Device name")
    device_type: Optional[str] = Field(None, description="Device type")
    os: Optional[str] = Field(None, description="Operating system")
    browser: Optional[str] = Field(None, description="Browser")
    last_login: datetime = Field(..., description="Last login time")
    is_trusted: bool = Field(default=False, description="Whether device is trusted")

class DeviceListResponse(BaseModel):
    """Schema for device list response"""
    devices: List[DeviceInfo] = Field(..., description="List of devices")
    total: int = Field(..., description="Total number of devices")

class TrustDeviceRequest(BaseModel):
    """Schema for trusting a device"""
    device_id: str = Field(..., description="Device identifier")
    trust: bool = Field(default=True, description="Whether to trust the device")

class APIKeyCreateRequest(BaseModel):
    """Schema for creating API key"""
    name: str = Field(..., min_length=1, max_length=100, description="API key name")
    expires_in: Optional[int] = Field(None, ge=1, le=365, description="Expiration in days")

class APIKeyResponse(BaseModel):
    """Schema for API key response"""
    id: int = Field(..., description="API key ID")
    name: str = Field(..., description="API key name")
    key: str = Field(..., description="API key (only shown on creation)")
    prefix: str = Field(..., description="API key prefix")
    created_at: datetime = Field(..., description="Creation time")
    expires_at: Optional[datetime] = Field(None, description="Expiration time")
    last_used: Optional[datetime] = Field(None, description="Last used time")
    is_active: bool = Field(default=True, description="Whether key is active")

class APIKeyListResponse(BaseModel):
    """Schema for API key list response"""
    keys: List[APIKeyResponse] = Field(..., description="List of API keys")
    total: int = Field(..., description="Total number of keys")

class PermissionCheck(BaseModel):
    """Schema for permission check"""
    resource: str = Field(..., description="Resource to check")
    action: str = Field(..., description="Action to perform")
    granted: bool = Field(..., description="Whether permission is granted")

class RateLimitInfo(BaseModel):
    """Schema for rate limit information"""
    limit: int = Field(..., description="Rate limit")
    remaining: int = Field(..., description="Remaining requests")
    reset_time: int = Field(..., description="Reset timestamp")
    window: str = Field(..., description="Time window")

class AuthConfig(BaseModel):
    """Schema for authentication configuration"""
    require_email_verification: bool = Field(default=True, description="Whether email verification is required")
    allow_registration: bool = Field(default=True, description="Whether registration is allowed")
    password_min_length: int = Field(default=8, description="Minimum password length")
    session_timeout: int = Field(default=86400, description="Session timeout in seconds")
    max_sessions_per_user: int = Field(default=10, description="Maximum sessions per user")
    enable_2fa: bool = Field(default=False, description="Whether 2FA is enabled")
    enable_oauth: bool = Field(default=True, description="Whether OAuth is enabled")
    oauth_providers: List[str] = Field(default_factory=list, description="Enabled OAuth providers")

class LoginHistory(BaseModel):
    """Schema for login history"""
    timestamp: datetime = Field(..., description="Login timestamp")
    ip_address: Optional[str] = Field(None, description="IP address")
    location: Optional[str] = Field(None, description="Location")
    device: Optional[str] = Field(None, description="Device information")
    status: str = Field(..., description="Login status (success/failure)")
    method: str = Field(..., description="Login method (password/oauth/2fa)")

class LoginHistoryResponse(BaseModel):
    """Schema for login history response"""
    history: List[LoginHistory] = Field(..., description="Login history")
    total: int = Field(..., description="Total number of logins")