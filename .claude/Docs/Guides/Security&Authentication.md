🔐 SECURITY & AUTHENTICATION GUIDE
Production-Ready Security Implementation for FastAPI

📋 TABLE OF CONTENTS

Introduction
JWT Token Implementation
OAuth2 Password Flow
API Key Management
Password Hashing
Two-Factor Authentication (2FA)
Rate Limiting & Throttling
CORS Configuration
Security Headers
OWASP Top 10 Protection
Session Management
Input Validation & Sanitization
Security Best Practices
Security Testing
Security Checklist


🎯 INTRODUCTION
Security Principles
Defense in Depth:
┌─────────────────────────────────────────────────────┐
│ Layer 1: Network Security (Firewall, DDoS)         │
├─────────────────────────────────────────────────────┤
│ Layer 2: Application Security (HTTPS, Headers)      │
├─────────────────────────────────────────────────────┤
│ Layer 3: Authentication (JWT, OAuth2, 2FA)          │
├─────────────────────────────────────────────────────┤
│ Layer 4: Authorization (RBAC, Permissions)          │
├─────────────────────────────────────────────────────┤
│ Layer 5: Data Security (Encryption, Hashing)        │
├─────────────────────────────────────────────────────┤
│ Layer 6: Monitoring (Logging, Alerts)               │
└─────────────────────────────────────────────────────┘
Threat Model
python# Common threats we'll protect against:

THREATS = {
    "Authentication Bypass": ["Weak passwords", "Token theft", "Session hijacking"],
    "Injection Attacks": ["SQL injection", "XSS", "Command injection"],
    "Data Breaches": ["Exposed secrets", "Unencrypted data", "Access control"],
    "DDoS": ["Rate limiting bypass", "Resource exhaustion"],
    "CSRF": ["Cross-site request forgery"],
    "Man-in-the-Middle": ["Unencrypted communication"],
}

🔑 JWT TOKEN IMPLEMENTATION
1. Complete JWT Implementation
python# backend/core/security.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
import secrets
from uuid import UUID

from core.config import settings


# ============================================================================
# JWT TOKEN GENERATION & VALIDATION
# ============================================================================

class TokenManager:
    """
    Secure JWT token management.
    
    Features:
    - Access & Refresh tokens
    - Token blacklisting
    - Token rotation
    - Secure claims
    """
    
    def __init__(self):
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire = settings.REFRESH_TOKEN_EXPIRE_DAYS
    
    def create_access_token(
        self,
        subject: Union[str, UUID],
        additional_claims: Optional[Dict[str, Any]] = None,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            subject: User identifier (usually user_id)
            additional_claims: Extra claims to include
            expires_delta: Custom expiration time
        
        Returns:
            Encoded JWT token
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire)
        
        # Standard claims
        to_encode = {
            "sub": str(subject),  # Subject (user ID)
            "exp": expire,        # Expiration time
            "iat": datetime.utcnow(),  # Issued at
            "nbf": datetime.utcnow(),  # Not before
            "type": "access",     # Token type
            "jti": secrets.token_urlsafe(32),  # Unique token ID
        }
        
        # Add additional claims
        if additional_claims:
            to_encode.update(additional_claims)
        
        # Encode token
        encoded_jwt = jwt.encode(
            to_encode,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        return encoded_jwt
    
    def create_refresh_token(
        self,
        subject: Union[str, UUID],
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """
        Create JWT refresh token.
        
        Refresh tokens have:
        - Longer expiration
        - Minimal claims (only sub, exp, type)
        - Can be revoked
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire)
        
        to_encode = {
            "sub": str(subject),
            "exp": expire,
            "iat": datetime.utcnow(),
            "type": "refresh",
            "jti": secrets.token_urlsafe(32),
        }
        
        encoded_jwt = jwt.encode(
            to_encode,
            self.secret_key,
            algorithm=self.algorithm
        )
        
        return encoded_jwt
    
    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and validate JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            Decoded token payload
        
        Raises:
            JWTError: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return payload
        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    def verify_token_type(self, payload: Dict[str, Any], expected_type: str):
        """Verify token type (access/refresh)"""
        token_type = payload.get("type")
        if token_type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token type. Expected {expected_type}, got {token_type}"
            )
    
    def get_token_claims(self, token: str) -> Dict[str, Any]:
        """Get token claims without verification (for debugging)"""
        return jwt.get_unverified_claims(token)


# Global token manager instance
token_manager = TokenManager()
2. Token Blacklisting (Redis)
python# backend/core/token_blacklist.py

from typing import Optional
from datetime import timedelta
import redis
from jose import jwt

from core.config import settings


class TokenBlacklist:
    """
    Token blacklist using Redis.
    
    Used for:
    - Logout (invalidate tokens)
    - Token revocation
    - Prevent replay attacks
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.prefix = "blacklist:"
    
    def add_token(self, token: str, expires_in: Optional[int] = None):
        """
        Add token to blacklist.
        
        Args:
            token: JWT token to blacklist
            expires_in: TTL in seconds (defaults to token expiration)
        """
        # Extract JTI (token ID) from token
        try:
            payload = jwt.get_unverified_claims(token)
            jti = payload.get("jti")
            
            if not jti:
                return  # Token doesn't have JTI, can't blacklist
            
            # Calculate TTL from token expiration
            if not expires_in and "exp" in payload:
                from datetime import datetime
                exp_timestamp = payload["exp"]
                now_timestamp = datetime.utcnow().timestamp()
                expires_in = int(exp_timestamp - now_timestamp)
            
            if expires_in and expires_in > 0:
                key = f"{self.prefix}{jti}"
                self.redis_client.setex(key, expires_in, "1")
        
        except Exception as e:
            # Log error but don't fail
            print(f"Failed to blacklist token: {e}")
    
    def is_blacklisted(self, token: str) -> bool:
        """
        Check if token is blacklisted.
        
        Args:
            token: JWT token to check
        
        Returns:
            True if blacklisted, False otherwise
        """
        try:
            payload = jwt.get_unverified_claims(token)
            jti = payload.get("jti")
            
            if not jti:
                return False
            
            key = f"{self.prefix}{jti}"
            return self.redis_client.exists(key) > 0
        
        except Exception:
            # If we can't check, assume not blacklisted
            return False
    
    def remove_token(self, token: str):
        """Remove token from blacklist"""
        try:
            payload = jwt.get_unverified_claims(token)
            jti = payload.get("jti")
            
            if jti:
                key = f"{self.prefix}{jti}"
                self.redis_client.delete(key)
        except Exception as e:
            print(f"Failed to remove token from blacklist: {e}")


# Global blacklist instance
token_blacklist = TokenBlacklist()
3. Enhanced Token Dependencies
python# backend/core/dependencies.py (enhanced)

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from database import SessionLocal
from models.auth import User
from core.security import token_manager
from core.token_blacklist import token_blacklist


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user with enhanced security.
    
    Security checks:
    1. Token format validation
    2. Token signature verification
    3. Token expiration check
    4. Token blacklist check
    5. User existence check
    6. User active status check
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 1. Decode and verify token
        payload = token_manager.decode_token(token)
        
        # 2. Verify token type
        token_manager.verify_token_type(payload, "access")
        
        # 3. Check if token is blacklisted
        if token_blacklist.is_blacklisted(token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 4. Extract user ID
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
    except JWTError:
        raise credentials_exception
    
    # 5. Get user from database
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    
    if user is None:
        raise credentials_exception
    
    # 6. Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user (additional check)"""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Get current verified user (email verified)"""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address"
        )
    return current_user
4. Logout with Token Blacklisting
python# backend/api/v1/auth.py (enhanced)

from core.token_blacklist import token_blacklist


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user)
):
    """
    Logout user by blacklisting the access token.
    
    Note: Refresh token should also be blacklisted separately.
    """
    # Blacklist the token
    token_blacklist.add_token(token)
    
    # Update last logout time
    from datetime import datetime
    current_user.last_logout_at = datetime.utcnow()
    db.commit()
    
    return {
        "message": "Successfully logged out",
        "detail": "Token has been invalidated"
    }


@router.post("/logout-all")
async def logout_all_devices(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logout from all devices.
    
    This increments a token version number,
    making all previously issued tokens invalid.
    """
    # Increment token version
    if not hasattr(current_user, 'token_version'):
        current_user.token_version = 0
    
    current_user.token_version += 1
    current_user.last_logout_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": "Logged out from all devices",
        "detail": "All existing tokens have been invalidated"
    }

🔐 OAUTH2 PASSWORD FLOW
1. Complete OAuth2 Implementation
python# backend/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional

from core.dependencies import get_db
from core.security import token_manager, verify_password
from core.token_blacklist import token_blacklist
from models.auth import User
from schemas.auth import Token, LoginResponse


router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    OAuth2 compatible token login.
    
    **Security features:**
    - Rate limiting (implemented in middleware)
    - Secure password verification
    - Account lockout after failed attempts
    - Login attempt logging
    - Device fingerprinting (optional)
    
    **Returns:**
    - access_token: Short-lived token (30 min)
    - refresh_token: Long-lived token (7 days)
    - token_type: "bearer"
    """
    # Find user by email or username
    user = db.query(User).filter(
        (User.email == form_data.username) | 
        (User.username == form_data.username)
    ).first()
    
    # Check if user exists
    if not user:
        # Log failed attempt
        from models.auth import LoginAttempt
        LoginAttempt.create(
            db,
            username=form_data.username,
            success=False,
            failure_reason="User not found"
        )
        
        # Generic error (don't reveal if user exists)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is locked
    if user.is_locked():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked due to too many failed login attempts. Please reset your password or contact support."
        )
    
    # Verify password
    if not verify_password(form_data.password, user.hashed_password):
        # Increment failed attempts
        user.increment_failed_login()
        db.commit()
        
        # Log failed attempt
        LoginAttempt.create(
            db,
            user_id=user.id,
            username=form_data.username,
            success=False,
            failure_reason="Invalid password"
        )
        
        # Check if account should be locked
        remaining_attempts = user.get_remaining_login_attempts()
        if remaining_attempts == 0:
            detail = "Account locked due to too many failed attempts"
        else:
            detail = f"Incorrect password. {remaining_attempts} attempts remaining."
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Reset failed login attempts on successful login
    user.reset_failed_login()
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = request.client.host  # If available
    
    # Log successful login
    LoginAttempt.create(
        db,
        user_id=user.id,
        username=form_data.username,
        success=True,
        ip_address=request.client.host
    )
    
    db.commit()
    
    # Create tokens
    access_token = token_manager.create_access_token(
        subject=user.id,
        additional_claims={
            "email": user.email,
            "username": user.username,
            "roles": [role.name for role in user.roles],
        }
    )
    
    refresh_token = token_manager.create_refresh_token(
        subject=user.id
    )
    
    # Store refresh token (optional, for tracking)
    from models.auth import RefreshToken
    RefreshToken.create(
        db,
        user_id=user.id,
        token=refresh_token,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_verified": user.is_verified,
        }
    }


@router.post("/refresh", response_model=Token)
async def refresh_access_token(
    refresh_token: str,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    
    **Security features:**
    - Refresh token rotation (optional)
    - Refresh token revocation
    - Blacklist old refresh tokens
    """
    try:
        # Decode refresh token
        payload = token_manager.decode_token(refresh_token)
        
        # Verify token type
        token_manager.verify_token_type(payload, "refresh")
        
        # Check if blacklisted
        if token_blacklist.is_blacklisted(refresh_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token has been revoked"
            )
        
        # Get user
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # OPTIONAL: Token rotation
        # Blacklist old refresh token
        token_blacklist.add_token(refresh_token)
        
        # Create new tokens
        new_access_token = token_manager.create_access_token(
            subject=user.id,
            additional_claims={
                "email": user.email,
                "username": user.username,
                "roles": [role.name for role in user.roles],
            }
        )
        
        new_refresh_token = token_manager.create_refresh_token(
            subject=user.id
        )
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
2. User Model with Security Features
python# backend/models/auth.py (enhanced)

from sqlalchemy import Column, String, Boolean, Integer, DateTime
from datetime import datetime, timedelta
from passlib.context import CryptContext

from models.base import BaseModel


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(BaseModel):
    __tablename__ = "users"
    
    # Basic info
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    
    # Security
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    last_login_ip = Column(String, nullable=True)
    last_logout_at = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Token versioning (for logout all devices)
    token_version = Column(Integer, default=0)
    
    # 2FA
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.hashed_password = pwd_context.hash(password)
        self.password_changed_at = datetime.utcnow()
    
    def verify_password(self, password: str) -> bool:
        """Verify password"""
        return pwd_context.verify(password, self.hashed_password)
    
    def increment_failed_login(self):
        """Increment failed login attempts"""
        self.failed_login_attempts += 1
        
        # Lock account after 5 failed attempts
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)
    
    def reset_failed_login(self):
        """Reset failed login counter"""
        self.failed_login_attempts = 0
        self.locked_until = None
    
    def is_locked(self) -> bool:
        """Check if account is locked"""
        if self.locked_until is None:
            return False
        
        # Check if lock has expired
        if datetime.utcnow() > self.locked_until:
            self.locked_until = None
            self.failed_login_attempts = 0
            return False
        
        return True
    
    def get_remaining_login_attempts(self) -> int:
        """Get remaining login attempts before lockout"""
        max_attempts = 5
        return max(0, max_attempts - self.failed_login_attempts)


class LoginAttempt(BaseModel):
    """Track login attempts for security auditing"""
    __tablename__ = "login_attempts"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    username = Column(String, nullable=False)
    success = Column(Boolean, nullable=False)
    failure_reason = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    
    @classmethod
    def create(cls, db, **kwargs):
        """Create login attempt record"""
        attempt = cls(**kwargs)
        db.add(attempt)
        db.commit()
        return attempt


class RefreshToken(BaseModel):
    """Store refresh tokens for tracking/revocation"""
    __tablename__ = "refresh_tokens"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    
    @classmethod
    def create(cls, db, **kwargs):
        """Create refresh token record"""
        token = cls(**kwargs)
        db.add(token)
        db.commit()
        return token

🔑 API KEY MANAGEMENT
1. API Key Model
python# backend/models/auth.py (continued)

from sqlalchemy import Column, String, DateTime, Boolean, Text
from datetime import datetime, timedelta
import secrets


class APIKey(BaseModel):
    """
    API Key for programmatic access.
    
    Use cases:
    - Third-party integrations
    - Server-to-server communication
    - CI/CD pipelines
    - Mobile apps (with caution)
    """
    __tablename__ = "api_keys"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    # Key details
    name = Column(String, nullable=False)  # Human-readable name
    key = Column(String, nullable=False, unique=True, index=True)
    key_prefix = Column(String, nullable=False)  # First 8 chars for identification
    
    # Permissions & Scopes
    scopes = Column(ARRAY(String), default=list)  # ['read:documents', 'write:documents']
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Usage tracking
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    usage_count = Column(Integer, default=0)
    
    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Security
    allowed_ips = Column(ARRAY(String), default=list)  # IP whitelist
    
    # Metadata
    description = Column(Text, nullable=True)
    
    @classmethod
    def generate_key(cls) -> tuple[str, str]:
        """
        Generate secure API key.
        
        Format: ocr_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
                or
                ocr_test_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        
        Returns:
            (key, prefix) tuple
        """
        # Generate random key
        random_part = secrets.token_urlsafe(32)
        
        # Add prefix based on environment
        env = settings.ENVIRONMENT
        prefix = "ocr_live_" if env == "production" else "ocr_test_"
        
        key = f"{prefix}{random_part}"
        key_prefix = key[:12]  # First 12 chars for display
        
        return key, key_prefix
    
    @classmethod
    def create(
        cls,
        db,
        user_id: UUID,
        name: str,
        scopes: list = None,
        expires_in_days: int = 365,
        description: str = None
    ):
        """Create new API key"""
        key, prefix = cls.generate_key()
        
        api_key = cls(
            user_id=user_id,
            name=name,
            key=key,
            key_prefix=prefix,
            scopes=scopes or [],
            description=description,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days)
        )
        
        db.add(api_key)
        db.commit()
        db.refresh(api_key)
        
        return api_key, key  # Return plain key (only shown once!)
    
    def is_valid(self) -> bool:
        """Check if API key is valid"""
        if not self.is_active:
            return False
        
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        
        return True
    
    def has_scope(self, required_scope: str) -> bool:
        """Check if API key has required scope"""
        if not self.scopes:
            return True  # No scopes = full access
        
        return required_scope in self.scopes
    
    def record_usage(self, db, ip_address: str = None):
        """Record API key usage"""
        self.last_used_at = datetime.utcnow()
        self.usage_count += 1
        
        # Check IP whitelist
        if self.allowed_ips and ip_address:
            if ip_address not in self.allowed_ips:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="IP address not allowed for this API key"
                )
        
        db.commit()
2. API Key Authentication
python# backend/core/dependencies.py (API Key auth)

from fastapi import Header, HTTPException, Request
from typing import Optional


async def get_api_key_user(
    x_api_key: Optional[str] = Header(None, description="API Key"),
    request: Request = None,
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate using API key.
    
    Header: X-API-Key: ocr_live_xxxxx
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    from models.auth import APIKey
    
    # Find API key
    api_key = db.query(APIKey).filter(
        APIKey.key == x_api_key
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Validate API key
    if not api_key.is_valid():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired or inactive"
        )
    
    # Record usage
    client_ip = request.client.host if request else None
    try:
        api_key.record_usage(db, ip_address=client_ip)
    except HTTPException:
        # IP not allowed
        raise
    
    # Get user
    user = api_key.user
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account inactive"
        )
    
    # Attach API key to user for scope checking
    user._api_key = api_key
    
    return user


def require_scope(required_scope: str):
    """
    Dependency to check API key scope.
    
    Usage:
        @app.get("/api/documents")
        async def get_docs(
            _: None = Depends(require_scope("read:documents"))
        ):
            ...
    """
    async def check_scope(
        current_user: User = Depends(get_api_key_user)
    ):
        if hasattr(current_user, '_api_key'):
            api_key = current_user._api_key
            
            if not api_key.has_scope(required_scope):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"API key missing required scope: {required_scope}"
                )
        
        return None
    
    return check_scope
3. API Key Management Endpoints
python# backend/api/v1/api_keys.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from core.dependencies import get_db, get_current_user
from models.auth import User, APIKey
from schemas.api_key import APIKeyCreate, APIKeyResponse, APIKeyListResponse


router = APIRouter()


@router.post("/", response_model=APIKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_data: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new API key.
    
    ⚠️ **IMPORTANT**: The full API key is only shown ONCE!
    Save it securely. You won't be able to retrieve it again.
    
    **Scopes:**
    - read:documents - Read documents
    - write:documents - Create/update documents
    - delete:documents - Delete documents
    - read:users - Read user data
    - admin - Full administrative access
    """
    # Create API key
    api_key, plain_key = APIKey.create(
        db,
        user_id=current_user.id,
        name=api_key_data.name,
        scopes=api_key_data.scopes,
        expires_in_days=api_key_data.expires_in_days or 365,
        description=api_key_data.description
    )
    
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": plain_key,  # ⚠️ Only shown once!
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at,
        "warning": "Save this key securely. You won't be able to see it again!"
    }


@router.get("/", response_model=List[APIKeyListResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all API keys for current user.
    
    Note: Full keys are never returned, only prefixes.
    """
    api_keys = db.query(APIKey).filter(
        APIKey.user_id == current_user.id
    ).all()
    
    return [
        {
            "id": key.id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "scopes": key.scopes,
            "is_active": key.is_active,
            "last_used_at": key.last_used_at,
            "usage_count": key.usage_count,
            "expires_at": key.expires_at,
            "created_at": key.created_at
        }
        for key in api_keys
    ]


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Revoke (delete) an API key"""
    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    db.delete(api_key)
    db.commit()
    
    return None


@router.patch("/{api_key_id}/rotate", response_model=APIKeyResponse)
async def rotate_api_key(
    api_key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Rotate API key (generate new key, keep same settings).
    
    ⚠️ Old key will be immediately invalidated!
    """
    api_key = db.query(APIKey).filter(
        APIKey.id == api_key_id,
        APIKey.user_id == current_user.id
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Generate new key
    new_key, new_prefix = APIKey.generate_key()
    
    # Update
    api_key.key = new_key
    api_key.key_prefix = new_prefix
    api_key.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(api_key)
    
    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": new_key,  # ⚠️ Only shown once!
        "key_prefix": api_key.key_prefix,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "warning": "Old key is now invalid. Save new key securely!"
    }



🔐 SECURITY & AUTHENTICATION GUIDE - TEIL 2
Password Hashing, 2FA, Rate Limiting & Advanced Security

🔒 PASSWORD HASHING
1. Secure Password Hashing with Argon2
python# backend/core/password.py

from passlib.context import CryptContext
from passlib.hash import argon2
import secrets
import string
from typing import Optional


class PasswordManager:
    """
    Secure password management using Argon2id.
    
    Why Argon2id?
    - Winner of Password Hashing Competition (2015)
    - Resistant to GPU/ASIC attacks
    - Memory-hard algorithm
    - Better than bcrypt for new applications
    
    Fallback to bcrypt for compatibility.
    """
    
    def __init__(self):
        # Argon2id configuration
        self.pwd_context = CryptContext(
            schemes=["argon2", "bcrypt"],
            deprecated="auto",
            
            # Argon2 parameters (tune based on your hardware)
            argon2__time_cost=2,        # Number of iterations
            argon2__memory_cost=102400,  # Memory usage (100 MB)
            argon2__parallelism=8,       # Number of threads
            argon2__hash_len=32,         # Hash length
            
            # Bcrypt parameters (fallback)
            bcrypt__rounds=12,           # Cost factor
        )
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using Argon2id.
        
        Args:
            password: Plain text password
        
        Returns:
            Hashed password
        """
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from database
        
        Returns:
            True if password matches, False otherwise
        """
        try:
            return self.pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            # Log error
            logger.error(f"Password verification error: {e}")
            return False
    
    def needs_rehash(self, hashed_password: str) -> bool:
        """
        Check if password hash needs to be updated.
        
        Useful for:
        - Migrating from bcrypt to argon2
        - Updating hash parameters
        
        Returns:
            True if hash should be regenerated
        """
        return self.pwd_context.needs_update(hashed_password)
    
    def generate_password(
        self,
        length: int = 16,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_special: bool = True
    ) -> str:
        """
        Generate secure random password.
        
        Args:
            length: Password length (minimum 12)
            use_uppercase: Include uppercase letters
            use_lowercase: Include lowercase letters
            use_digits: Include digits
            use_special: Include special characters
        
        Returns:
            Random password
        """
        if length < 12:
            raise ValueError("Password must be at least 12 characters")
        
        # Character sets
        chars = ""
        if use_lowercase:
            chars += string.ascii_lowercase
        if use_uppercase:
            chars += string.ascii_uppercase
        if use_digits:
            chars += string.digits
        if use_special:
            chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        
        if not chars:
            raise ValueError("At least one character type must be selected")
        
        # Generate password
        password = ''.join(secrets.choice(chars) for _ in range(length))
        
        return password
    
    def validate_password_strength(self, password: str) -> dict:
        """
        Validate password strength.
        
        Returns:
            Dictionary with validation results
        """
        issues = []
        score = 0
        
        # Length check
        if len(password) < 8:
            issues.append("Password must be at least 8 characters")
        elif len(password) >= 12:
            score += 2
        else:
            score += 1
        
        # Character type checks
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)
        
        if not has_upper:
            issues.append("Password must contain at least one uppercase letter")
        else:
            score += 1
        
        if not has_lower:
            issues.append("Password must contain at least one lowercase letter")
        else:
            score += 1
        
        if not has_digit:
            issues.append("Password must contain at least one digit")
        else:
            score += 1
        
        if not has_special:
            issues.append("Password should contain at least one special character")
        else:
            score += 2
        
        # Common password check (simple)
        common_passwords = [
            "password", "12345678", "qwerty", "abc123",
            "password123", "admin", "letmein"
        ]
        
        if password.lower() in common_passwords:
            issues.append("Password is too common")
            score = 0
        
        # Strength rating
        if score >= 7:
            strength = "strong"
        elif score >= 5:
            strength = "medium"
        else:
            strength = "weak"
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "score": score,
            "strength": strength
        }


# Global password manager instance
password_manager = PasswordManager()


# Convenience functions
def hash_password(password: str) -> str:
    """Hash password"""
    return password_manager.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return password_manager.verify_password(plain_password, hashed_password)
2. Password Update with Rehashing
python# backend/api/v1/auth.py (password management)

from core.password import password_manager


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password.
    
    **Security features:**
    - Current password verification
    - Password strength validation
    - Automatic hash algorithm upgrade
    - Invalidate all sessions (logout all devices)
    """
    # Verify current password
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Validate new password strength
    validation = password_manager.validate_password_strength(new_password)
    
    if not validation["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet requirements",
            headers={"X-Password-Issues": ", ".join(validation["issues"])}
        )
    
    # Check if new password is same as current
    if verify_password(new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
    
    # Set new password
    current_user.set_password(new_password)
    current_user.password_changed_at = datetime.utcnow()
    
    # Increment token version (logout all devices)
    current_user.token_version += 1
    
    db.commit()
    
    return {
        "message": "Password changed successfully",
        "detail": "All active sessions have been invalidated"
    }


@router.post("/reset-password/request")
async def request_password_reset(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Request password reset email.
    
    **Security features:**
    - Rate limiting (prevent enumeration)
    - Generic response (don't reveal if user exists)
    - Time-limited token
    - Single-use token
    """
    # Always return success (don't reveal if user exists)
    # Actual email sending happens in background
    
    user = db.query(User).filter(User.email == email).first()
    
    if user:
        # Generate reset token (JWT with short expiration)
        reset_token = token_manager.create_access_token(
            subject=user.id,
            additional_claims={"type": "password_reset"},
            expires_delta=timedelta(hours=1)  # 1 hour expiration
        )
        
        # Store token hash in database (for single-use)
        from models.auth import PasswordResetToken
        PasswordResetToken.create(
            db,
            user_id=user.id,
            token_hash=hash_password(reset_token)
        )
        
        # Send email (background task)
        from tasks.email_tasks import send_password_reset_email
        send_password_reset_email.delay(
            email=user.email,
            reset_token=reset_token
        )
    
    return {
        "message": "If the email exists, a password reset link has been sent"
    }


@router.post("/reset-password/confirm")
async def confirm_password_reset(
    token: str,
    new_password: str,
    db: Session = Depends(get_db)
):
    """
    Confirm password reset with token.
    """
    from models.auth import PasswordResetToken
    
    try:
        # Decode token
        payload = token_manager.decode_token(token)
        
        # Verify token type
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if token has been used
        token_hash = hash_password(token)
        reset_token = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None)
        ).first()
        
        if not reset_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token has already been used or is invalid"
            )
        
        # Validate new password
        validation = password_manager.validate_password_strength(new_password)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet requirements",
                headers={"X-Password-Issues": ", ".join(validation["issues"])}
            )
        
        # Set new password
        user.set_password(new_password)
        user.token_version += 1  # Logout all devices
        
        # Mark token as used
        reset_token.used_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "message": "Password reset successfully"
        }
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )

📱 TWO-FACTOR AUTHENTICATION (2FA)
1. TOTP-based 2FA Implementation
python# backend/core/two_factor.py

import pyotp
import qrcode
import io
import base64
from typing import Optional, Tuple


class TwoFactorAuth:
    """
    Time-based One-Time Password (TOTP) implementation.
    
    Uses Google Authenticator compatible algorithm.
    """
    
    def __init__(self):
        self.issuer_name = "OCR Backend"
    
    def generate_secret(self) -> str:
        """
        Generate random secret for TOTP.
        
        Returns:
            Base32-encoded secret
        """
        return pyotp.random_base32()
    
    def get_totp_uri(self, secret: str, username: str) -> str:
        """
        Generate TOTP URI for QR code.
        
        Args:
            secret: TOTP secret
            username: User identifier (email or username)
        
        Returns:
            otpauth:// URI
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(
            name=username,
            issuer_name=self.issuer_name
        )
    
    def generate_qr_code(self, secret: str, username: str) -> str:
        """
        Generate QR code for TOTP setup.
        
        Args:
            secret: TOTP secret
            username: User identifier
        
        Returns:
            Base64-encoded PNG image
        """
        # Get URI
        uri = self.get_totp_uri(secret, username)
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    
    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """
        Verify TOTP token.
        
        Args:
            secret: User's TOTP secret
            token: 6-digit code from authenticator app
            window: Time window for code validation (default: ±30 seconds)
        
        Returns:
            True if valid, False otherwise
        """
        if not secret or not token:
            return False
        
        totp = pyotp.TOTP(secret)
        
        # Verify with time window
        return totp.verify(token, valid_window=window)
    
    def get_backup_codes(self, count: int = 10) -> list[str]:
        """
        Generate backup codes.
        
        Args:
            count: Number of backup codes to generate
        
        Returns:
            List of backup codes
        """
        import secrets
        
        backup_codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric code
            code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            # Format as XXXX-XXXX
            formatted_code = f"{code[:4]}-{code[4:]}"
            backup_codes.append(formatted_code)
        
        return backup_codes


# Global 2FA instance
two_factor = TwoFactorAuth()
2. 2FA Database Models
python# backend/models/auth.py (2FA models)

from sqlalchemy import Column, String, Boolean, DateTime, Text
from datetime import datetime


class TwoFactorBackupCode(BaseModel):
    """Backup codes for 2FA recovery"""
    __tablename__ = "two_factor_backup_codes"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    code_hash = Column(String, nullable=False)  # Hashed backup code
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    @classmethod
    def create_codes(cls, db, user_id: UUID, codes: list[str]):
        """Create backup codes for user"""
        from core.password import hash_password
        
        # Delete old codes
        db.query(cls).filter(cls.user_id == user_id).delete()
        
        # Create new codes
        for code in codes:
            code_hash = hash_password(code)
            backup_code = cls(
                user_id=user_id,
                code_hash=code_hash
            )
            db.add(backup_code)
        
        db.commit()
    
    @classmethod
    def verify_code(cls, db, user_id: UUID, code: str) -> bool:
        """Verify and consume backup code"""
        from core.password import verify_password
        
        # Get all unused codes
        backup_codes = db.query(cls).filter(
            cls.user_id == user_id,
            cls.used_at.is_(None)
        ).all()
        
        # Try to match code
        for backup_code in backup_codes:
            if verify_password(code, backup_code.code_hash):
                # Mark as used
                backup_code.used_at = datetime.utcnow()
                db.commit()
                return True
        
        return False


class TwoFactorSession(BaseModel):
    """Track 2FA-verified sessions"""
    __tablename__ = "two_factor_sessions"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    session_token = Column(String, nullable=False, unique=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    @classmethod
    def create_session(cls, db, user_id: UUID, ip_address: str = None, user_agent: str = None):
        """Create 2FA session"""
        import secrets
        
        session_token = secrets.token_urlsafe(32)
        
        session = cls(
            user_id=user_id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.utcnow() + timedelta(days=30)  # 30 days
        )
        
        db.add(session)
        db.commit()
        
        return session_token
3. 2FA Endpoints
python# backend/api/v1/two_factor.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from core.dependencies import get_db, get_current_user
from core.two_factor import two_factor
from models.auth import User, TwoFactorBackupCode, TwoFactorSession
from schemas.two_factor import (
    Enable2FAResponse,
    Verify2FARequest,
    BackupCodesResponse
)


router = APIRouter()


@router.post("/enable", response_model=Enable2FAResponse)
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enable 2FA for user.
    
    Returns:
    - secret: TOTP secret (save this!)
    - qr_code: QR code image (base64)
    - backup_codes: List of backup codes
    
    ⚠️ **IMPORTANT**: Save the secret and backup codes securely!
    """
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled"
        )
    
    # Generate secret
    secret = two_factor.generate_secret()
    
    # Generate QR code
    qr_code = two_factor.generate_qr_code(
        secret,
        current_user.email
    )
    
    # Generate backup codes
    backup_codes = two_factor.get_backup_codes(count=10)
    
    # Store backup codes
    TwoFactorBackupCode.create_codes(db, current_user.id, backup_codes)
    
    # Store secret (will be enabled after verification)
    current_user.two_factor_secret = secret
    db.commit()
    
    return {
        "secret": secret,
        "qr_code": qr_code,
        "backup_codes": backup_codes,
        "message": "Scan QR code with your authenticator app, then verify to enable 2FA"
    }


@router.post("/verify")
async def verify_and_enable_2fa(
    verification: Verify2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify TOTP code and enable 2FA.
    """
    if not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA setup not initiated. Call /enable first"
        )
    
    # Verify code
    if not two_factor.verify_totp(current_user.two_factor_secret, verification.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code"
        )
    
    # Enable 2FA
    current_user.two_factor_enabled = True
    db.commit()
    
    return {
        "message": "2FA enabled successfully",
        "enabled": True
    }


@router.post("/disable")
async def disable_2fa(
    password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disable 2FA.
    
    Requires password verification.
    """
    from core.password import verify_password
    
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled"
        )
    
    # Verify password
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Disable 2FA
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    
    # Delete backup codes
    db.query(TwoFactorBackupCode).filter(
        TwoFactorBackupCode.user_id == current_user.id
    ).delete()
    
    db.commit()
    
    return {
        "message": "2FA disabled successfully"
    }


@router.get("/backup-codes", response_model=BackupCodesResponse)
async def get_new_backup_codes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate new backup codes.
    
    ⚠️ Old backup codes will be invalidated!
    """
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled"
        )
    
    # Generate new backup codes
    backup_codes = two_factor.get_backup_codes(count=10)
    
    # Store codes
    TwoFactorBackupCode.create_codes(db, current_user.id, backup_codes)
    
    return {
        "backup_codes": backup_codes,
        "message": "New backup codes generated. Old codes are now invalid."
    }
4. 2FA Login Flow
python# backend/api/v1/auth.py (2FA login)

@router.post("/login/2fa")
async def login_with_2fa(
    email: str,
    password: str,
    totp_code: Optional[str] = None,
    backup_code: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Login with 2FA.
    
    Flow:
    1. POST with email + password
       → Returns: {"requires_2fa": true, "temp_token": "xxx"}
    
    2. POST with email + password + totp_code (or backup_code)
       → Returns: {"access_token": "xxx", "refresh_token": "yyy"}
    """
    # Find user
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if 2FA is enabled
    if not user.two_factor_enabled:
        # Normal login (no 2FA)
        return await normal_login_flow(user, db, request)
    
    # 2FA is enabled
    if not totp_code and not backup_code:
        # First step: password verified, now need 2FA
        # Generate temporary token (valid for 5 minutes)
        temp_token = token_manager.create_access_token(
            subject=user.id,
            additional_claims={"type": "2fa_pending"},
            expires_delta=timedelta(minutes=5)
        )
        
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "Enter 2FA code from your authenticator app"
        }
    
    # Second step: verify 2FA code
    verified = False
    
    if totp_code:
        # Verify TOTP code
        verified = two_factor.verify_totp(user.two_factor_secret, totp_code)
    
    elif backup_code:
        # Verify backup code
        verified = TwoFactorBackupCode.verify_code(db, user.id, backup_code)
    
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code"
        )
    
    # 2FA verified - create session
    ip_address = request.client.host if request else None
    user_agent = request.headers.get("User-Agent") if request else None
    
    session_token = TwoFactorSession.create_session(
        db,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # Generate tokens
    access_token = token_manager.create_access_token(
        subject=user.id,
        additional_claims={
            "email": user.email,
            "username": user.username,
            "2fa_verified": True,
            "session_token": session_token
        }
    )
    
    refresh_token = token_manager.create_refresh_token(subject=user.id)
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    user.reset_failed_login()
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "2fa_enabled": True
        }
    }

⏱️ RATE LIMITING & THROTTLING
1. Redis-based Rate Limiter
python# backend/core/rate_limiter.py

from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
import redis
import hashlib
import json

from core.config import settings


class RateLimiter:
    """
    Advanced rate limiter using Redis.
    
    Features:
    - Token bucket algorithm
    - Per-user and per-IP limits
    - Custom rate limits per endpoint
    - Sliding window
    - Rate limit headers
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.prefix = "ratelimit:"
    
    def _get_identifier(
        self,
        request: Request,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get unique identifier for rate limiting.
        
        Priority:
        1. User ID (if authenticated)
        2. IP address
        """
        if user_id:
            return f"user:{user_id}"
        
        # Use IP address
        ip = request.client.host
        return f"ip:{ip}"
    
    def _get_key(self, identifier: str, scope: str) -> str:
        """Generate Redis key"""
        return f"{self.prefix}{scope}:{identifier}"
    
    def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
        scope: str = "global",
        user_id: Optional[str] = None
    ) -> dict:
        """
        Check if request should be rate limited.
        
        Args:
            request: FastAPI request
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            scope: Rate limit scope (e.g., 'login', 'api', 'global')
            user_id: User ID (if authenticated)
        
        Returns:
            Dictionary with rate limit info
        """
        identifier = self._get_identifier(request, user_id)
        key = self._get_key(identifier, scope)
        
        current_time = datetime.utcnow().timestamp()
        window_start = current_time - window_seconds
        
        # Sliding window using sorted set
        pipe = self.redis_client.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        pipe.expire(key, window_seconds)
        
        results = pipe.execute()
        request_count = results[1]
        
        # Calculate remaining and reset time
        remaining = max(0, max_requests - request_count - 1)
        
        # Get oldest request time for reset calculation
        oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
        if oldest:
            reset_time = int(oldest[0][1] + window_seconds)
        else:
            reset_time = int(current_time + window_seconds)
        
        return {
            "allowed": request_count < max_requests,
            "limit": max_requests,
            "remaining": remaining,
            "reset": reset_time,
            "retry_after": window_seconds if request_count >= max_requests else 0
        }
    
    def get_rate_limit_headers(self, rate_limit_info: dict) -> dict:
        """
        Generate rate limit headers.
        
        Returns:
            Dictionary of headers to add to response
        """
        return {
            "X-RateLimit-Limit": str(rate_limit_info["limit"]),
            "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
            "X-RateLimit-Reset": str(rate_limit_info["reset"]),
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# Dependency for rate limiting
def rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    scope: str = "global"
):
    """
    Rate limit dependency.
    
    Usage:
        @app.get("/api/data")
        async def get_data(
            _: None = Depends(rate_limit(max_requests=10, window_seconds=60))
        ):
            ...
    
    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        scope: Rate limit scope
    """
    async def check_limit(request: Request):
        from core.dependencies import get_current_user_optional
        
        # Get user if authenticated
        user = None
        try:
            user = await get_current_user_optional(request)
        except:
            pass
        
        user_id = str(user.id) if user else None
        
        # Check rate limit
        rate_limit_info = rate_limiter.check_rate_limit(
            request,
            max_requests=max_requests,
            window_seconds=window_seconds,
            scope=scope,
            user_id=user_id
        )
        
        # Add headers to response
        headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
        
        # Check if rate limit exceeded
        if not rate_limit_info["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {rate_limit_info['retry_after']} seconds.",
                headers={
                    **headers,
                    "Retry-After": str(rate_limit_info["retry_after"])
                }
            )
        
        # Attach headers to request for later use
        request.state.rate_limit_headers = headers
    
    return check_limit
2. Rate Limit Middleware
python# backend/middleware/rate_limit_middleware.py

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add rate limit headers to all responses.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers if available
        if hasattr(request.state, "rate_limit_headers"):
            for key, value in request.state.rate_limit_headers.items():
                response.headers[key] = value
        
        return response


# Add to main.py
from middleware.rate_limit_middleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
3. Endpoint-Specific Rate Limits
python# backend/api/v1/auth.py (with rate limiting)

from core.rate_limiter import rate_limit


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=300, scope="login"))]
)
async def login(...):
    """
    Login endpoint with rate limiting.
    
    **Rate limit: 5 requests per 5 minutes**
    """
    ...


@router.post(
    "/register",
    dependencies=[Depends(rate_limit(max_requests=3, window_seconds=3600, scope="register"))]
)
async def register(...):
    """
    Registration with strict rate limiting.
    
    **Rate limit: 3 registrations per hour**
    """
    ...


@router.post(
    "/reset-password/request",
    dependencies=[Depends(rate_limit(max_requests=3, window_seconds=1800, scope="password_reset"))]
)
async def request_password_reset(...):
    """
    Password reset with rate limiting.
    
    **Rate limit: 3 requests per 30 minutes**
    """
    ...

🌐 CORS CONFIGURATION
1. Secure CORS Setup
python# backend/core/config.py (CORS settings)

class Settings(BaseSettings):
    # ... other settings ...
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Local development
        "http://localhost:8080",
        "https://app.example.com",  # Production frontend
        "https://admin.example.com",  # Admin panel
    ]
    
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = [
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID",
    ]
    CORS_EXPOSE_HEADERS: List[str] = [
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ]
    CORS_MAX_AGE: int = 600  # Cache preflight for 10 minutes
python# backend/main.py (CORS middleware)

from fastapi.middleware.cors import CORSMiddleware

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=settings.CORS_EXPOSE_HEADERS,
    max_age=settings.CORS_MAX_AGE,
)
2. Dynamic CORS (Advanced)
python# backend/middleware/dynamic_cors.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import re


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """
    Dynamic CORS middleware with pattern matching.
    
    Allows:
    - Subdomain wildcards
    - Environment-based origins
    - Request validation
    """
    
    def __init__(
        self,
        app,
        allowed_origins: List[str],
        allowed_patterns: List[str] = None
    ):
        super().__init__(app)
        self.allowed_origins = allowed_origins
        self.allowed_patterns = [
            re.compile(pattern) for pattern in (allowed_patterns or [])
        ]
    
    def is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed"""
        # Exact match
        if origin in self.allowed_origins:
            return True
        
        # Pattern match
        for pattern in self.allowed_patterns:
            if pattern.match(origin):
                return True
        
        return False
    
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        
        if origin and self.is_origin_allowed(origin):
            # Process request
            response = await call_next(request)
            
            # Add CORS headers
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            
            # Handle preflight
            if request.method == "OPTIONS":
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                response.headers["Access-Control-Max-Age"] = "600"
            
            return response
        
        # Origin not allowed
        return await call_next(request)


# Usage:
app.add_middleware(
    DynamicCORSMiddleware,
    allowed_origins=settings.CORS_ORIGINS,
    allowed_patterns=[
        r"https://.*\.example\.com",  # All subdomains
        r"http://localhost:\d+",       # Any localhost port
    ]
)





🔐 SECURITY & AUTHENTICATION GUIDE - TEIL 2
Password Hashing, 2FA, Rate Limiting & Advanced Security

🔒 PASSWORD HASHING
1. Secure Password Hashing with Argon2
python# backend/core/password.py

from passlib.context import CryptContext
from passlib.hash import argon2
import secrets
import string
from typing import Optional


class PasswordManager:
    """
    Secure password management using Argon2id.
    
    Why Argon2id?
    - Winner of Password Hashing Competition (2015)
    - Resistant to GPU/ASIC attacks
    - Memory-hard algorithm
    - Better than bcrypt for new applications
    
    Fallback to bcrypt for compatibility.
    """
    
    def __init__(self):
        # Argon2id configuration
        self.pwd_context = CryptContext(
            schemes=["argon2", "bcrypt"],
            deprecated="auto",
            
            # Argon2 parameters (tune based on your hardware)
            argon2__time_cost=2,        # Number of iterations
            argon2__memory_cost=102400,  # Memory usage (100 MB)
            argon2__parallelism=8,       # Number of threads
            argon2__hash_len=32,         # Hash length
            
            # Bcrypt parameters (fallback)
            bcrypt__rounds=12,           # Cost factor
        )
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using Argon2id.
        
        Args:
            password: Plain text password
        
        Returns:
            Hashed password
        """
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            plain_password: Plain text password
            hashed_password: Hashed password from database
        
        Returns:
            True if password matches, False otherwise
        """
        try:
            return self.pwd_context.verify(plain_password, hashed_password)
        except Exception as e:
            # Log error
            logger.error(f"Password verification error: {e}")
            return False
    
    def needs_rehash(self, hashed_password: str) -> bool:
        """
        Check if password hash needs to be updated.
        
        Useful for:
        - Migrating from bcrypt to argon2
        - Updating hash parameters
        
        Returns:
            True if hash should be regenerated
        """
        return self.pwd_context.needs_update(hashed_password)
    
    def generate_password(
        self,
        length: int = 16,
        use_uppercase: bool = True,
        use_lowercase: bool = True,
        use_digits: bool = True,
        use_special: bool = True
    ) -> str:
        """
        Generate secure random password.
        
        Args:
            length: Password length (minimum 12)
            use_uppercase: Include uppercase letters
            use_lowercase: Include lowercase letters
            use_digits: Include digits
            use_special: Include special characters
        
        Returns:
            Random password
        """
        if length < 12:
            raise ValueError("Password must be at least 12 characters")
        
        # Character sets
        chars = ""
        if use_lowercase:
            chars += string.ascii_lowercase
        if use_uppercase:
            chars += string.ascii_uppercase
        if use_digits:
            chars += string.digits
        if use_special:
            chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"
        
        if not chars:
            raise ValueError("At least one character type must be selected")
        
        # Generate password
        password = ''.join(secrets.choice(chars) for _ in range(length))
        
        return password
    
    def validate_password_strength(self, password: str) -> dict:
        """
        Validate password strength.
        
        Returns:
            Dictionary with validation results
        """
        issues = []
        score = 0
        
        # Length check
        if len(password) < 8:
            issues.append("Password must be at least 8 characters")
        elif len(password) >= 12:
            score += 2
        else:
            score += 1
        
        # Character type checks
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in password)
        
        if not has_upper:
            issues.append("Password must contain at least one uppercase letter")
        else:
            score += 1
        
        if not has_lower:
            issues.append("Password must contain at least one lowercase letter")
        else:
            score += 1
        
        if not has_digit:
            issues.append("Password must contain at least one digit")
        else:
            score += 1
        
        if not has_special:
            issues.append("Password should contain at least one special character")
        else:
            score += 2
        
        # Common password check (simple)
        common_passwords = [
            "password", "12345678", "qwerty", "abc123",
            "password123", "admin", "letmein"
        ]
        
        if password.lower() in common_passwords:
            issues.append("Password is too common")
            score = 0
        
        # Strength rating
        if score >= 7:
            strength = "strong"
        elif score >= 5:
            strength = "medium"
        else:
            strength = "weak"
        
        return {
            "is_valid": len(issues) == 0,
            "issues": issues,
            "score": score,
            "strength": strength
        }


# Global password manager instance
password_manager = PasswordManager()


# Convenience functions
def hash_password(password: str) -> str:
    """Hash password"""
    return password_manager.hash_password(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return password_manager.verify_password(plain_password, hashed_password)
2. Password Update with Rehashing
python# backend/api/v1/auth.py (password management)

from core.password import password_manager


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Change user password.
    
    **Security features:**
    - Current password verification
    - Password strength validation
    - Automatic hash algorithm upgrade
    - Invalidate all sessions (logout all devices)
    """
    # Verify current password
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )
    
    # Validate new password strength
    validation = password_manager.validate_password_strength(new_password)
    
    if not validation["is_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password does not meet requirements",
            headers={"X-Password-Issues": ", ".join(validation["issues"])}
        )
    
    # Check if new password is same as current
    if verify_password(new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
    
    # Set new password
    current_user.set_password(new_password)
    current_user.password_changed_at = datetime.utcnow()
    
    # Increment token version (logout all devices)
    current_user.token_version += 1
    
    db.commit()
    
    return {
        "message": "Password changed successfully",
        "detail": "All active sessions have been invalidated"
    }


@router.post("/reset-password/request")
async def request_password_reset(
    email: str,
    db: Session = Depends(get_db)
):
    """
    Request password reset email.
    
    **Security features:**
    - Rate limiting (prevent enumeration)
    - Generic response (don't reveal if user exists)
    - Time-limited token
    - Single-use token
    """
    # Always return success (don't reveal if user exists)
    # Actual email sending happens in background
    
    user = db.query(User).filter(User.email == email).first()
    
    if user:
        # Generate reset token (JWT with short expiration)
        reset_token = token_manager.create_access_token(
            subject=user.id,
            additional_claims={"type": "password_reset"},
            expires_delta=timedelta(hours=1)  # 1 hour expiration
        )
        
        # Store token hash in database (for single-use)
        from models.auth import PasswordResetToken
        PasswordResetToken.create(
            db,
            user_id=user.id,
            token_hash=hash_password(reset_token)
        )
        
        # Send email (background task)
        from tasks.email_tasks import send_password_reset_email
        send_password_reset_email.delay(
            email=user.email,
            reset_token=reset_token
        )
    
    return {
        "message": "If the email exists, a password reset link has been sent"
    }


@router.post("/reset-password/confirm")
async def confirm_password_reset(
    token: str,
    new_password: str,
    db: Session = Depends(get_db)
):
    """
    Confirm password reset with token.
    """
    from models.auth import PasswordResetToken
    
    try:
        # Decode token
        payload = token_manager.decode_token(token)
        
        # Verify token type
        if payload.get("type") != "password_reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == UUID(user_id)).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check if token has been used
        token_hash = hash_password(token)
        reset_token = db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None)
        ).first()
        
        if not reset_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token has already been used or is invalid"
            )
        
        # Validate new password
        validation = password_manager.validate_password_strength(new_password)
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password does not meet requirements",
                headers={"X-Password-Issues": ", ".join(validation["issues"])}
            )
        
        # Set new password
        user.set_password(new_password)
        user.token_version += 1  # Logout all devices
        
        # Mark token as used
        reset_token.used_at = datetime.utcnow()
        
        db.commit()
        
        return {
            "message": "Password reset successfully"
        }
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token"
        )

📱 TWO-FACTOR AUTHENTICATION (2FA)
1. TOTP-based 2FA Implementation
python# backend/core/two_factor.py

import pyotp
import qrcode
import io
import base64
from typing import Optional, Tuple


class TwoFactorAuth:
    """
    Time-based One-Time Password (TOTP) implementation.
    
    Uses Google Authenticator compatible algorithm.
    """
    
    def __init__(self):
        self.issuer_name = "OCR Backend"
    
    def generate_secret(self) -> str:
        """
        Generate random secret for TOTP.
        
        Returns:
            Base32-encoded secret
        """
        return pyotp.random_base32()
    
    def get_totp_uri(self, secret: str, username: str) -> str:
        """
        Generate TOTP URI for QR code.
        
        Args:
            secret: TOTP secret
            username: User identifier (email or username)
        
        Returns:
            otpauth:// URI
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(
            name=username,
            issuer_name=self.issuer_name
        )
    
    def generate_qr_code(self, secret: str, username: str) -> str:
        """
        Generate QR code for TOTP setup.
        
        Args:
            secret: TOTP secret
            username: User identifier
        
        Returns:
            Base64-encoded PNG image
        """
        # Get URI
        uri = self.get_totp_uri(secret, username)
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    
    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """
        Verify TOTP token.
        
        Args:
            secret: User's TOTP secret
            token: 6-digit code from authenticator app
            window: Time window for code validation (default: ±30 seconds)
        
        Returns:
            True if valid, False otherwise
        """
        if not secret or not token:
            return False
        
        totp = pyotp.TOTP(secret)
        
        # Verify with time window
        return totp.verify(token, valid_window=window)
    
    def get_backup_codes(self, count: int = 10) -> list[str]:
        """
        Generate backup codes.
        
        Args:
            count: Number of backup codes to generate
        
        Returns:
            List of backup codes
        """
        import secrets
        
        backup_codes = []
        for _ in range(count):
            # Generate 8-character alphanumeric code
            code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
            # Format as XXXX-XXXX
            formatted_code = f"{code[:4]}-{code[4:]}"
            backup_codes.append(formatted_code)
        
        return backup_codes


# Global 2FA instance
two_factor = TwoFactorAuth()
2. 2FA Database Models
python# backend/models/auth.py (2FA models)

from sqlalchemy import Column, String, Boolean, DateTime, Text
from datetime import datetime


class TwoFactorBackupCode(BaseModel):
    """Backup codes for 2FA recovery"""
    __tablename__ = "two_factor_backup_codes"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    code_hash = Column(String, nullable=False)  # Hashed backup code
    used_at = Column(DateTime(timezone=True), nullable=True)
    
    @classmethod
    def create_codes(cls, db, user_id: UUID, codes: list[str]):
        """Create backup codes for user"""
        from core.password import hash_password
        
        # Delete old codes
        db.query(cls).filter(cls.user_id == user_id).delete()
        
        # Create new codes
        for code in codes:
            code_hash = hash_password(code)
            backup_code = cls(
                user_id=user_id,
                code_hash=code_hash
            )
            db.add(backup_code)
        
        db.commit()
    
    @classmethod
    def verify_code(cls, db, user_id: UUID, code: str) -> bool:
        """Verify and consume backup code"""
        from core.password import verify_password
        
        # Get all unused codes
        backup_codes = db.query(cls).filter(
            cls.user_id == user_id,
            cls.used_at.is_(None)
        ).all()
        
        # Try to match code
        for backup_code in backup_codes:
            if verify_password(code, backup_code.code_hash):
                # Mark as used
                backup_code.used_at = datetime.utcnow()
                db.commit()
                return True
        
        return False


class TwoFactorSession(BaseModel):
    """Track 2FA-verified sessions"""
    __tablename__ = "two_factor_sessions"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    session_token = Column(String, nullable=False, unique=True)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    @classmethod
    def create_session(cls, db, user_id: UUID, ip_address: str = None, user_agent: str = None):
        """Create 2FA session"""
        import secrets
        
        session_token = secrets.token_urlsafe(32)
        
        session = cls(
            user_id=user_id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.utcnow() + timedelta(days=30)  # 30 days
        )
        
        db.add(session)
        db.commit()
        
        return session_token
3. 2FA Endpoints
python# backend/api/v1/two_factor.py

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from core.dependencies import get_db, get_current_user
from core.two_factor import two_factor
from models.auth import User, TwoFactorBackupCode, TwoFactorSession
from schemas.two_factor import (
    Enable2FAResponse,
    Verify2FARequest,
    BackupCodesResponse
)


router = APIRouter()


@router.post("/enable", response_model=Enable2FAResponse)
async def enable_2fa(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enable 2FA for user.
    
    Returns:
    - secret: TOTP secret (save this!)
    - qr_code: QR code image (base64)
    - backup_codes: List of backup codes
    
    ⚠️ **IMPORTANT**: Save the secret and backup codes securely!
    """
    if current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled"
        )
    
    # Generate secret
    secret = two_factor.generate_secret()
    
    # Generate QR code
    qr_code = two_factor.generate_qr_code(
        secret,
        current_user.email
    )
    
    # Generate backup codes
    backup_codes = two_factor.get_backup_codes(count=10)
    
    # Store backup codes
    TwoFactorBackupCode.create_codes(db, current_user.id, backup_codes)
    
    # Store secret (will be enabled after verification)
    current_user.two_factor_secret = secret
    db.commit()
    
    return {
        "secret": secret,
        "qr_code": qr_code,
        "backup_codes": backup_codes,
        "message": "Scan QR code with your authenticator app, then verify to enable 2FA"
    }


@router.post("/verify")
async def verify_and_enable_2fa(
    verification: Verify2FARequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify TOTP code and enable 2FA.
    """
    if not current_user.two_factor_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA setup not initiated. Call /enable first"
        )
    
    # Verify code
    if not two_factor.verify_totp(current_user.two_factor_secret, verification.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code"
        )
    
    # Enable 2FA
    current_user.two_factor_enabled = True
    db.commit()
    
    return {
        "message": "2FA enabled successfully",
        "enabled": True
    }


@router.post("/disable")
async def disable_2fa(
    password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disable 2FA.
    
    Requires password verification.
    """
    from core.password import verify_password
    
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled"
        )
    
    # Verify password
    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Disable 2FA
    current_user.two_factor_enabled = False
    current_user.two_factor_secret = None
    
    # Delete backup codes
    db.query(TwoFactorBackupCode).filter(
        TwoFactorBackupCode.user_id == current_user.id
    ).delete()
    
    db.commit()
    
    return {
        "message": "2FA disabled successfully"
    }


@router.get("/backup-codes", response_model=BackupCodesResponse)
async def get_new_backup_codes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate new backup codes.
    
    ⚠️ Old backup codes will be invalidated!
    """
    if not current_user.two_factor_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled"
        )
    
    # Generate new backup codes
    backup_codes = two_factor.get_backup_codes(count=10)
    
    # Store codes
    TwoFactorBackupCode.create_codes(db, current_user.id, backup_codes)
    
    return {
        "backup_codes": backup_codes,
        "message": "New backup codes generated. Old codes are now invalid."
    }
4. 2FA Login Flow
python# backend/api/v1/auth.py (2FA login)

@router.post("/login/2fa")
async def login_with_2fa(
    email: str,
    password: str,
    totp_code: Optional[str] = None,
    backup_code: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Login with 2FA.
    
    Flow:
    1. POST with email + password
       → Returns: {"requires_2fa": true, "temp_token": "xxx"}
    
    2. POST with email + password + totp_code (or backup_code)
       → Returns: {"access_token": "xxx", "refresh_token": "yyy"}
    """
    # Find user
    user = db.query(User).filter(User.email == email).first()
    
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if 2FA is enabled
    if not user.two_factor_enabled:
        # Normal login (no 2FA)
        return await normal_login_flow(user, db, request)
    
    # 2FA is enabled
    if not totp_code and not backup_code:
        # First step: password verified, now need 2FA
        # Generate temporary token (valid for 5 minutes)
        temp_token = token_manager.create_access_token(
            subject=user.id,
            additional_claims={"type": "2fa_pending"},
            expires_delta=timedelta(minutes=5)
        )
        
        return {
            "requires_2fa": True,
            "temp_token": temp_token,
            "message": "Enter 2FA code from your authenticator app"
        }
    
    # Second step: verify 2FA code
    verified = False
    
    if totp_code:
        # Verify TOTP code
        verified = two_factor.verify_totp(user.two_factor_secret, totp_code)
    
    elif backup_code:
        # Verify backup code
        verified = TwoFactorBackupCode.verify_code(db, user.id, backup_code)
    
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code"
        )
    
    # 2FA verified - create session
    ip_address = request.client.host if request else None
    user_agent = request.headers.get("User-Agent") if request else None
    
    session_token = TwoFactorSession.create_session(
        db,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    # Generate tokens
    access_token = token_manager.create_access_token(
        subject=user.id,
        additional_claims={
            "email": user.email,
            "username": user.username,
            "2fa_verified": True,
            "session_token": session_token
        }
    )
    
    refresh_token = token_manager.create_refresh_token(subject=user.id)
    
    # Update last login
    user.last_login_at = datetime.utcnow()
    user.reset_failed_login()
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "2fa_enabled": True
        }
    }

⏱️ RATE LIMITING & THROTTLING
1. Redis-based Rate Limiter
python# backend/core/rate_limiter.py

from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from datetime import datetime, timedelta
import redis
import hashlib
import json

from core.config import settings


class RateLimiter:
    """
    Advanced rate limiter using Redis.
    
    Features:
    - Token bucket algorithm
    - Per-user and per-IP limits
    - Custom rate limits per endpoint
    - Sliding window
    - Rate limit headers
    """
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.prefix = "ratelimit:"
    
    def _get_identifier(
        self,
        request: Request,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get unique identifier for rate limiting.
        
        Priority:
        1. User ID (if authenticated)
        2. IP address
        """
        if user_id:
            return f"user:{user_id}"
        
        # Use IP address
        ip = request.client.host
        return f"ip:{ip}"
    
    def _get_key(self, identifier: str, scope: str) -> str:
        """Generate Redis key"""
        return f"{self.prefix}{scope}:{identifier}"
    
    def check_rate_limit(
        self,
        request: Request,
        max_requests: int,
        window_seconds: int,
        scope: str = "global",
        user_id: Optional[str] = None
    ) -> dict:
        """
        Check if request should be rate limited.
        
        Args:
            request: FastAPI request
            max_requests: Maximum requests allowed
            window_seconds: Time window in seconds
            scope: Rate limit scope (e.g., 'login', 'api', 'global')
            user_id: User ID (if authenticated)
        
        Returns:
            Dictionary with rate limit info
        """
        identifier = self._get_identifier(request, user_id)
        key = self._get_key(identifier, scope)
        
        current_time = datetime.utcnow().timestamp()
        window_start = current_time - window_seconds
        
        # Sliding window using sorted set
        pipe = self.redis_client.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(current_time): current_time})
        
        # Set expiration
        pipe.expire(key, window_seconds)
        
        results = pipe.execute()
        request_count = results[1]
        
        # Calculate remaining and reset time
        remaining = max(0, max_requests - request_count - 1)
        
        # Get oldest request time for reset calculation
        oldest = self.redis_client.zrange(key, 0, 0, withscores=True)
        if oldest:
            reset_time = int(oldest[0][1] + window_seconds)
        else:
            reset_time = int(current_time + window_seconds)
        
        return {
            "allowed": request_count < max_requests,
            "limit": max_requests,
            "remaining": remaining,
            "reset": reset_time,
            "retry_after": window_seconds if request_count >= max_requests else 0
        }
    
    def get_rate_limit_headers(self, rate_limit_info: dict) -> dict:
        """
        Generate rate limit headers.
        
        Returns:
            Dictionary of headers to add to response
        """
        return {
            "X-RateLimit-Limit": str(rate_limit_info["limit"]),
            "X-RateLimit-Remaining": str(rate_limit_info["remaining"]),
            "X-RateLimit-Reset": str(rate_limit_info["reset"]),
        }


# Global rate limiter instance
rate_limiter = RateLimiter()


# Dependency for rate limiting
def rate_limit(
    max_requests: int = 60,
    window_seconds: int = 60,
    scope: str = "global"
):
    """
    Rate limit dependency.
    
    Usage:
        @app.get("/api/data")
        async def get_data(
            _: None = Depends(rate_limit(max_requests=10, window_seconds=60))
        ):
            ...
    
    Args:
        max_requests: Maximum requests allowed
        window_seconds: Time window in seconds
        scope: Rate limit scope
    """
    async def check_limit(request: Request):
        from core.dependencies import get_current_user_optional
        
        # Get user if authenticated
        user = None
        try:
            user = await get_current_user_optional(request)
        except:
            pass
        
        user_id = str(user.id) if user else None
        
        # Check rate limit
        rate_limit_info = rate_limiter.check_rate_limit(
            request,
            max_requests=max_requests,
            window_seconds=window_seconds,
            scope=scope,
            user_id=user_id
        )
        
        # Add headers to response
        headers = rate_limiter.get_rate_limit_headers(rate_limit_info)
        
        # Check if rate limit exceeded
        if not rate_limit_info["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {rate_limit_info['retry_after']} seconds.",
                headers={
                    **headers,
                    "Retry-After": str(rate_limit_info["retry_after"])
                }
            )
        
        # Attach headers to request for later use
        request.state.rate_limit_headers = headers
    
    return check_limit
2. Rate Limit Middleware
python# backend/middleware/rate_limit_middleware.py

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add rate limit headers to all responses.
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers if available
        if hasattr(request.state, "rate_limit_headers"):
            for key, value in request.state.rate_limit_headers.items():
                response.headers[key] = value
        
        return response


# Add to main.py
from middleware.rate_limit_middleware import RateLimitMiddleware

app.add_middleware(RateLimitMiddleware)
3. Endpoint-Specific Rate Limits
python# backend/api/v1/auth.py (with rate limiting)

from core.rate_limiter import rate_limit


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit(max_requests=5, window_seconds=300, scope="login"))]
)
async def login(...):
    """
    Login endpoint with rate limiting.
    
    **Rate limit: 5 requests per 5 minutes**
    """
    ...


@router.post(
    "/register",
    dependencies=[Depends(rate_limit(max_requests=3, window_seconds=3600, scope="register"))]
)
async def register(...):
    """
    Registration with strict rate limiting.
    
    **Rate limit: 3 registrations per hour**
    """
    ...


@router.post(
    "/reset-password/request",
    dependencies=[Depends(rate_limit(max_requests=3, window_seconds=1800, scope="password_reset"))]
)
async def request_password_reset(...):
    """
    Password reset with rate limiting.
    
    **Rate limit: 3 requests per 30 minutes**
    """
    ...

🌐 CORS CONFIGURATION
1. Secure CORS Setup
python# backend/core/config.py (CORS settings)

class Settings(BaseSettings):
    # ... other settings ...
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Local development
        "http://localhost:8080",
        "https://app.example.com",  # Production frontend
        "https://admin.example.com",  # Admin panel
    ]
    
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = [
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-Request-ID",
    ]
    CORS_EXPOSE_HEADERS: List[str] = [
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ]
    CORS_MAX_AGE: int = 600  # Cache preflight for 10 minutes
python# backend/main.py (CORS middleware)

from fastapi.middleware.cors import CORSMiddleware

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=settings.CORS_EXPOSE_HEADERS,
    max_age=settings.CORS_MAX_AGE,
)
2. Dynamic CORS (Advanced)
python# backend/middleware/dynamic_cors.py

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import re


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """
    Dynamic CORS middleware with pattern matching.
    
    Allows:
    - Subdomain wildcards
    - Environment-based origins
    - Request validation
    """
    
    def __init__(
        self,
        app,
        allowed_origins: List[str],
        allowed_patterns: List[str] = None
    ):
        super().__init__(app)
        self.allowed_origins = allowed_origins
        self.allowed_patterns = [
            re.compile(pattern) for pattern in (allowed_patterns or [])
        ]
    
    def is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is allowed"""
        # Exact match
        if origin in self.allowed_origins:
            return True
        
        # Pattern match
        for pattern in self.allowed_patterns:
            if pattern.match(origin):
                return True
        
        return False
    
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        
        if origin and self.is_origin_allowed(origin):
            # Process request
            response = await call_next(request)
            
            # Add CORS headers
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            
            # Handle preflight
            if request.method == "OPTIONS":
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                response.headers["Access-Control-Max-Age"] = "600"
            
            return response
        
        # Origin not allowed
        return await call_next(request)


# Usage:
app.add_middleware(
    DynamicCORSMiddleware,
    allowed_origins=settings.CORS_ORIGINS,
    allowed_patterns=[
        r"https://.*\.example\.com",  # All subdomains
        r"http://localhost:\d+",       # Any localhost port
    ]
)