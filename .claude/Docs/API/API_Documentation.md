🚀 FASTAPI ENDPOINTS GUIDE - COMPLETE API DOCUMENTATION
Production-Ready REST API Implementation

📋 TABLE OF CONTENTS

Introduction
FastAPI Setup & Configuration
Project Structure
Pydantic Schemas
Dependency Injection
Authentication & Authorization
CRUD Operations
File Upload Endpoints
Pagination & Filtering
Error Handling
WebSocket Endpoints
Background Tasks
API Versioning
OpenAPI Documentation
Testing
Best Practices


🎯 INTRODUCTION
What We'll Build
Complete REST API with:
├── Authentication (JWT + OAuth2)
├── User Management
├── Document Management
├── OCR Processing
├── File Uploads
├── Real-time Updates (WebSocket)
├── Background Tasks
└── Auto-generated API Docs
API Architecture
┌─────────────────────────────────────────────────────────┐
│                    CLIENT APPLICATIONS                   │
│  (Web Frontend, Mobile Apps, Third-party Services)      │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP/HTTPS
                       │
┌──────────────────────▼──────────────────────────────────┐
│                  FASTAPI APPLICATION                     │
├─────────────────────────────────────────────────────────┤
│  Routers                                                 │
│  ├── /api/v1/auth      (Login, Register, Token)        │
│  ├── /api/v1/users     (User Management)               │
│  ├── /api/v1/documents (Document CRUD)                 │
│  ├── /api/v1/ocr       (OCR Processing)                │
│  └── /api/v1/admin     (Admin Operations)              │
│                                                          │
│  Middleware                                              │
│  ├── CORS                                               │
│  ├── Rate Limiting                                      │
│  ├── Request Logging                                    │
│  └── Error Handling                                     │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              BUSINESS LOGIC & SERVICES                   │
│  ├── Authentication Service                             │
│  ├── Document Service                                   │
│  ├── OCR Service                                        │
│  └── Storage Service                                    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                DATABASE (PostgreSQL)                     │
│  SQLAlchemy ORM Models                                  │
└─────────────────────────────────────────────────────────┘

📦 FASTAPI SETUP & CONFIGURATION
1. Installation
bash# requirements.txt

# FastAPI & Server
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-multipart==0.0.6  # For file uploads

# Database
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
alembic==1.13.1

# Authentication
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-dotenv==1.0.0

# Validation & Serialization
pydantic==2.5.3
pydantic-settings==2.1.0
email-validator==2.1.0

# CORS & Security
python-cors==1.0.0

# Background Tasks
celery==5.3.4
redis==5.0.1

# Testing
pytest==7.4.4
httpx==0.26.0
pytest-asyncio==0.23.3
bashpip install -r requirements.txt
2. Main Application Setup
python# backend/main.py

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import time
import logging

from api.v1 import auth, users, documents, ocr, admin
from database import engine, Base
from core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting OCR Backend API...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database: {settings.DATABASE_URL}")
    
    # Create database tables (in production use Alembic migrations)
    # Base.metadata.create_all(bind=engine)
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down OCR Backend API...")


# Create FastAPI app
app = FastAPI(
    title="OCR Backend API",
    description="Advanced OCR Document Processing System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Request Timing Middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add X-Process-Time header to all responses"""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Request Logging Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    logger.info(f"📨 {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"📤 {request.method} {request.url.path} - {response.status_code}")
    return response


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors"""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(str(x) for x in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation Error",
            "errors": errors
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions"""
    logger.error(f"❌ Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An error occurred"
        }
    )


# ============================================================================
# ROUTERS
# ============================================================================

# Health Check
@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - health check"""
    return {
        "status": "online",
        "service": "OCR Backend API",
        "version": "1.0.0"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",  # Add actual DB check
        "cache": "connected",     # Add Redis check
        "timestamp": time.time()
    }


# Include API routers
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    users.router,
    prefix="/api/v1/users",
    tags=["Users"]
)

app.include_router(
    documents.router,
    prefix="/api/v1/documents",
    tags=["Documents"]
)

app.include_router(
    ocr.router,
    prefix="/api/v1/ocr",
    tags=["OCR Processing"]
)

app.include_router(
    admin.router,
    prefix="/api/v1/admin",
    tags=["Admin"]
)


# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )
3. Configuration Management
python# backend/core/config.py

from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    """
    Application settings.
    Automatically loads from environment variables or .env file.
    """
    
    # Application
    APP_NAME: str = "OCR Backend API"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/ocr_db"
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
    ]
    
    # File Upload
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    UPLOAD_DIR: str = "./uploads"
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"]
    
    # Redis (for caching & Celery)
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
bash# .env

# Application
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=super-secret-key-change-this-in-production

# Database
DATABASE_URL=postgresql://prod_user:prod_pass@db-server:5432/ocr_prod

# CORS
CORS_ORIGINS=["https://app.example.com","https://admin.example.com"]

# Redis
REDIS_URL=redis://redis-server:6379/0
```

---

## 📁 PROJECT STRUCTURE
```
backend/
├── main.py                      # FastAPI app entry point
├── requirements.txt
├── .env
│
├── api/                         # API endpoints
│   └── v1/                      # API version 1
│       ├── __init__.py
│       ├── auth.py              # Authentication endpoints
│       ├── users.py             # User management
│       ├── documents.py         # Document CRUD
│       ├── ocr.py               # OCR processing
│       └── admin.py             # Admin endpoints
│
├── schemas/                     # Pydantic models (Request/Response)
│   ├── __init__.py
│   ├── auth.py
│   ├── user.py
│   ├── document.py
│   ├── ocr.py
│   └── common.py
│
├── core/                        # Core functionality
│   ├── __init__.py
│   ├── config.py                # Settings
│   ├── security.py              # Auth utilities
│   └── dependencies.py          # Dependency injection
│
├── services/                    # Business logic
│   ├── __init__.py
│   ├── auth_service.py
│   ├── user_service.py
│   ├── document_service.py
│   └── ocr_service.py
│
├── models/                      # SQLAlchemy models (from previous guides)
│   ├── __init__.py
│   ├── base.py
│   ├── auth.py
│   ├── documents.py
│   └── ...
│
├── utils/                       # Utilities
│   ├── __init__.py
│   ├── file_handler.py
│   └── validators.py
│
├── database.py                  # Database connection
├── alembic/                     # Database migrations
└── tests/                       # Tests
    ├── __init__.py
    ├── test_auth.py
    ├── test_documents.py
    └── conftest.py

📝 PYDANTIC SCHEMAS
1. Common Schemas
python# backend/schemas/common.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Generic, TypeVar
from datetime import datetime
from uuid import UUID


# Generic type for pagination
T = TypeVar('T')


class PaginationParams(BaseModel):
    """Pagination query parameters"""
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response"""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class MessageResponse(BaseModel):
    """Simple message response"""
    message: str
    detail: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    errors: Optional[List[dict]] = None


class IDResponse(BaseModel):
    """Response with ID"""
    id: UUID
    message: str = "Created successfully"


class StatusResponse(BaseModel):
    """Status response"""
    status: str
    message: Optional[str] = None
2. User Schemas
python# backend/schemas/user.py

from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID
import re


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    """Schema for user registration"""
    password: str = Field(..., min_length=8, max_length=100)
    password_confirm: str
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v
    
    @field_validator('password_confirm')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        """Validate passwords match"""
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v


class UserUpdate(BaseModel):
    """Schema for user update"""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    
    model_config = ConfigDict(extra='forbid')


class UserResponse(UserBase):
    """Schema for user response"""
    id: UUID
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class UserWithStats(UserResponse):
    """User with statistics"""
    document_count: int = 0
    total_storage_mb: float = 0.0


class UserList(BaseModel):
    """List of users"""
    users: List[UserResponse]
    total: int


class PasswordChange(BaseModel):
    """Password change schema"""
    current_password: str
    new_password: str = Field(..., min_length=8)
    new_password_confirm: str
    
    @field_validator('new_password_confirm')
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if 'new_password' in info.data and v != info.data['new_password']:
            raise ValueError('Passwords do not match')
        return v
3. Authentication Schemas
python# backend/schemas/auth.py

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class TokenData(BaseModel):
    """Token payload data"""
    user_id: str
    email: str
    username: str


class Token(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefresh(BaseModel):
    """Refresh token request"""
    refresh_token: str


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Login response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RegisterRequest(BaseModel):
    """Registration request"""
    email: EmailStr
    username: str
    password: str
    password_confirm: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class PasswordResetRequest(BaseModel):
    """Password reset request"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Password reset confirmation"""
    token: str
    new_password: str
    new_password_confirm: str
4. Document Schemas
python# backend/schemas/document.py

from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class DocumentStatus(str, Enum):
    """Document status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentType(str, Enum):
    """Document type enum"""
    INVOICE = "invoice"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    DELIVERY_NOTE = "delivery_note"
    OTHER = "other"


class DocumentBase(BaseModel):
    """Base document schema"""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    document_type: Optional[DocumentType] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DocumentCreate(DocumentBase):
    """Schema for document creation"""
    category_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None


class DocumentUpdate(BaseModel):
    """Schema for document update"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    document_type: Optional[DocumentType] = None
    tags: Optional[List[str]] = None
    status: Optional[DocumentStatus] = None
    metadata: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra='forbid')


class DocumentResponse(DocumentBase):
    """Schema for document response"""
    id: UUID
    user_id: UUID
    status: DocumentStatus
    file_path: str
    file_size: int
    mime_type: str
    page_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentResponse):
    """Detailed document response with relationships"""
    category: Optional[dict] = None
    supplier: Optional[dict] = None
    ocr_results: Optional[List[dict]] = Field(default_factory=list)
    pages: Optional[List[dict]] = Field(default_factory=list)


class DocumentFilter(BaseModel):
    """Document filtering parameters"""
    status: Optional[DocumentStatus] = None
    document_type: Optional[DocumentType] = None
    category_id: Optional[UUID] = None
    supplier_id: Optional[UUID] = None
    search: Optional[str] = None
    tags: Optional[List[str]] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class DocumentSort(str, Enum):
    """Sorting options"""
    CREATED_ASC = "created_at"
    CREATED_DESC = "-created_at"
    UPDATED_ASC = "updated_at"
    UPDATED_DESC = "-updated_at"
    TITLE_ASC = "title"
    TITLE_DESC = "-title"
    SIZE_ASC = "file_size"
    SIZE_DESC = "-file_size"
5. OCR Schemas
python# backend/schemas/ocr.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class OCRBackend(str, Enum):
    """OCR backend options"""
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    CPU_SURYA = "cpu_surya"


class OCRJobStatus(str, Enum):
    """OCR job status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OCRProcessRequest(BaseModel):
    """Request to process document with OCR"""
    document_id: UUID
    backend: OCRBackend = OCRBackend.DEEPSEEK
    language: str = "en"
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class OCRJobResponse(BaseModel):
    """OCR job response"""
    id: UUID
    document_id: UUID
    backend: str
    status: OCRJobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None
    
    model_config = ConfigDict(from_attributes=True)


class OCRResultResponse(BaseModel):
    """OCR result response"""
    id: UUID
    job_id: UUID
    extracted_text: str
    confidence_score: Optional[float] = None
    extracted_data: Optional[Dict[str, Any]] = None
    language: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class OCRBatchRequest(BaseModel):
    """Batch OCR processing request"""
    document_ids: List[UUID] = Field(..., max_length=100)
    backend: OCRBackend = OCRBackend.DEEPSEEK
    language: str = "en"


class OCRBatchResponse(BaseModel):
    """Batch OCR response"""
    total: int
    successful: int
    failed: int
    job_ids: List[UUID]

🔐 DEPENDENCY INJECTION
python# backend/core/dependencies.py

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional
from uuid import UUID

from database import SessionLocal
from models.auth import User
from core.config import settings
from schemas.auth import TokenData


# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================================================
# DATABASE DEPENDENCY
# ============================================================================

def get_db():
    """
    Database session dependency.
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# AUTHENTICATION DEPENDENCIES
# ============================================================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Raises:
        HTTPException: 401 if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Decode JWT token
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        
        if user_id is None:
            raise credentials_exception
        
        token_data = TokenData(
            user_id=user_id,
            email=payload.get("email"),
            username=payload.get("username")
        )
        
    except JWTError:
        raise credentials_exception
    
    # Get user from database
    user = db.query(User).filter(User.id == UUID(token_data.user_id)).first()
    
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get current active user.
    
    Raises:
        HTTPException: 403 if user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_verified_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current verified user.
    
    Raises:
        HTTPException: 403 if user is not verified
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User email not verified"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Get current admin user.
    
    Raises:
        HTTPException: 403 if user is not admin
    """
    # Check if user has admin role
    if not any(role.name == 'admin' for role in current_user.roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# ============================================================================
# OPTIONAL AUTHENTICATION
# ============================================================================

async def get_current_user_optional(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user if authenticated, None otherwise.
    Useful for public endpoints with optional authentication.
    """
    if token is None:
        return None
    
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


# ============================================================================
# API KEY AUTHENTICATION
# ============================================================================

async def get_api_key(
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Authenticate using API key from X-API-Key header.
    
    Raises:
        HTTPException: 401 if API key is invalid
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required"
        )
    
    from models.auth import APIKey
    from datetime import datetime
    
    # Find API key
    api_key = db.query(APIKey).filter(
        APIKey.key == x_api_key,
        APIKey.is_active == True
    ).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    
    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key expired"
        )
    
    # Update last used
    api_key.last_used_at = datetime.utcnow()
    db.commit()
    
    return api_key.user


# ============================================================================
# PERMISSION CHECKING
# ============================================================================

class PermissionChecker:
    """
    Check if user has specific permission.
    
    Usage:
        @app.get("/admin/users")
        async def admin_users(
            user: User = Depends(PermissionChecker("users.manage"))
        ):
            ...
    """
    
    def __init__(self, permission: str):
        self.permission = permission
    
    def __call__(
        self,
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        # Check if user has permission
        user_permissions = [
            perm.name
            for role in current_user.roles
            for perm in role.permissions
        ]
        
        if self.permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{self.permission}' required"
            )
        
        return current_user


# ============================================================================
# RATE LIMITING
# ============================================================================

from collections import defaultdict
from time import time


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    Usage:
        @app.get("/api/data")
        async def get_data(
            _: None = Depends(RateLimiter(times=10, seconds=60))
        ):
            ...
    """
    
    def __init__(self, times: int, seconds: int):
        self.times = times
        self.seconds = seconds
        self.requests = defaultdict(list)
    
    def __call__(
        self,
        request: Request,
        user: Optional[User] = Depends(get_current_user_optional)
    ):
        # Use user ID if authenticated, otherwise IP address
        identifier = str(user.id) if user else request.client.host
        
        now = time()
        
        # Remove old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if now - req_time < self.seconds
        ]
        
        # Check rate limit
        if len(self.requests[identifier]) >= self.times:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {self.seconds} seconds."
            )
        
        # Add current request
        self.requests[identifier].append(now)

🔑 AUTHENTICATION & AUTHORIZATION
python# backend/core/security.py

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import jwt
from passlib.context import CryptContext
from uuid import UUID

from core.config import settings


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================================
# PASSWORD HASHING
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


# ============================================================================
# JWT TOKEN GENERATION
# ============================================================================

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token.
    
    Args:
        data: Data to encode in token
        expires_delta: Token expiration time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT refresh token.
    
    Args:
        data: Data to encode in token
        expires_delta: Token expiration time
    
    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            days=settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode JWT token.
    
    Args:
        token: JWT token to decode
    
    Returns:
        Decoded token payload
    
    Raises:
        JWTError: If token is invalid
    """
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM]
    )

📚 CRUD OPERATIONS
Authentication Endpoints
python# backend/api/v1/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from core.dependencies import get_db, get_current_user
from core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token
)
from models.auth import User
from schemas.auth import (
    LoginResponse,
    RegisterRequest,
    Token,
    TokenRefresh
)
from schemas.user import UserResponse


router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Register a new user.
    
    - **email**: Valid email address
    - **username**: Unique username (3-50 chars)
    - **password**: Strong password (min 8 chars, uppercase, lowercase, digit)
    - **password_confirm**: Must match password
    """
    # Check if email exists
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user
    user = User(
        email=user_data.email,
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        is_active=True,
        is_verified=False  # Require email verification
    )
    
    user.set_password(user_data.password)
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # TODO: Send verification email
    
    return user


@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Login with email/username and password.
    
    Returns access token and refresh token.
    """
    # Find user by email or username
    user = db.query(User).filter(
        (User.email == form_data.username) | 
        (User.username == form_data.username)
    ).first()
    
    # Verify credentials
    if not user or not user.verify_password(form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email/username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create tokens
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "username": user.username
        }
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )
    
    # Update last login
    from datetime import datetime
    user.last_login_at = datetime.utcnow()
    db.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: TokenRefresh,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token.
    """
    from jose import JWTError
    from core.security import decode_token
    from uuid import UUID
    
    try:
        payload = decode_token(refresh_data.refresh_token)
        
        # Verify token type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Get user
    user = db.query(User).filter(User.id == UUID(user_id)).first()
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "username": user.username
        }
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    """
    return current_user


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_user)
):
    """
    Logout current user.
    
    Note: With JWT, actual logout requires token blacklisting (Redis).
    For now, client should discard the token.
    """
    # TODO: Add token to blacklist in Redis
    
    return {"message": "Successfully logged out"}
Documents Endpoints
python# backend/api/v1/documents.py

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from core.dependencies import get_db, get_current_user
from models.auth import User
from models.documents import Document
from schemas.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentDetailResponse,
    DocumentFilter,
    DocumentSort
)
from schemas.common import PaginatedResponse, PaginationParams, IDResponse


router = APIRouter()


@router.get("/", response_model=PaginatedResponse[DocumentResponse])
async def list_documents(
    pagination: PaginationParams = Depends(),
    filters: DocumentFilter = Depends(),
    sort_by: DocumentSort = Query(DocumentSort.CREATED_DESC),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List documents with pagination and filtering.
    
    **Filters:**
    - status: Filter by document status
    - document_type: Filter by document type
    - category_id: Filter by category
    - search: Search in title/description
    - tags: Filter by tags
    - created_after/created_before: Date range filter
    
    **Sorting:**
    - created_at, -created_at (newest first)
    - updated_at, -updated_at
    - title, -title
    - file_size, -file_size
    """
    # Build query
    query = db.query(Document).filter(Document.user_id == current_user.id)
    
    # Apply filters
    if filters.status:
        query = query.filter(Document.status == filters.status)
    
    if filters.document_type:
        query = query.filter(Document.document_type == filters.document_type)
    
    if filters.category_id:
        query = query.filter(Document.category_id == filters.category_id)
    
    if filters.supplier_id:
        query = query.filter(Document.detected_supplier_id == filters.supplier_id)
    
    if filters.search:
        search_term = f"%{filters.search}%"
        query = query.filter(
            (Document.title.ilike(search_term)) |
            (Document.description.ilike(search_term))
        )
    
    if filters.tags:
        # PostgreSQL array contains
        query = query.filter(Document.tags.contains(filters.tags))
    
    if filters.created_after:
        query = query.filter(Document.created_at >= filters.created_after)
    
    if filters.created_before:
        query = query.filter(Document.created_at <= filters.created_before)
    
    # Apply sorting
    if sort_by.value.startswith('-'):
        # Descending
        order_col = getattr(Document, sort_by.value[1:])
        query = query.order_by(order_col.desc())
    else:
        # Ascending
        order_col = getattr(Document, sort_by.value)
        query = query.order_by(order_col.asc())
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    documents = query.offset(pagination.offset).limit(pagination.page_size).all()
    
    # Calculate pagination metadata
    total_pages = (total + pagination.page_size - 1) // pagination.page_size
    
    return {
        "items": documents,
        "total": total,
        "page": pagination.page,
        "page_size": pagination.page_size,
        "total_pages": total_pages,
        "has_next": pagination.page < total_pages,
        "has_prev": pagination.page > 1
    }


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get single document by ID with detailed information.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    return document


@router.post("/", response_model=IDResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    file: UploadFile = File(...),
    title: Optional[str] = None,
    description: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload and create a new document.
    
    **File Requirements:**
    - Max size: 50MB
    - Allowed types: PDF, JPG, PNG, TIFF
    """
    from utils.file_handler import save_upload_file, get_file_hash
    import os
    
    # Validate file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to start
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    # Validate file extension
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Save file
    file_path = save_upload_file(file, current_user.id)
    file_hash = get_file_hash(file_path)
    
    # Create document
    document = Document(
        user_id=current_user.id,
        title=title or file.filename,
        description=description,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
        file_hash=file_hash,
        status="pending"
    )
    
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # TODO: Trigger OCR processing (Celery task)
    
    return {
        "id": document.id,
        "message": "Document uploaded successfully"
    }


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: UUID,
    document_data: DocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update document metadata.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Update fields
    update_data = document_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)
    
    db.commit()
    db.refresh(document)
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a document (soft delete).
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    # Soft delete
    from datetime import datetime
    document.deleted_at = datetime.utcnow()
    
    db.commit()
    
    return None


@router.post("/{document_id}/restore", response_model=DocumentResponse)
async def restore_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Restore a soft-deleted document.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.deleted_at.isnot(None)
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deleted document not found"
        )
    
    # Restore
    document.deleted_at = None
    db.commit()
    db.refresh(document)
    
    return document





🚀 FASTAPI ENDPOINTS GUIDE - TEIL 2
File Uploads, WebSockets, Background Tasks & More

📤 FILE UPLOAD ENDPOINTS
1. File Upload Handler Utility
python# backend/utils/file_handler.py

import os
import hashlib
import shutil
from pathlib import Path
from typing import Optional, BinaryIO
from fastapi import UploadFile
from uuid import UUID, uuid4
from datetime import datetime

from core.config import settings


def ensure_upload_dir(user_id: UUID) -> Path:
    """
    Ensure user upload directory exists.
    
    Creates: uploads/{user_id}/
    """
    upload_path = Path(settings.UPLOAD_DIR) / str(user_id)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def get_file_hash(file_path: str, algorithm: str = 'sha256') -> str:
    """
    Calculate file hash.
    
    Args:
        file_path: Path to file
        algorithm: Hash algorithm (sha256, md5)
    
    Returns:
        Hexadecimal hash string
    """
    hash_obj = hashlib.new(algorithm)
    
    with open(file_path, 'rb') as f:
        while chunk := f.read(8192):
            hash_obj.update(chunk)
    
    return hash_obj.hexdigest()


def save_upload_file(
    upload_file: UploadFile,
    user_id: UUID,
    preserve_filename: bool = False
) -> str:
    """
    Save uploaded file to disk.
    
    Args:
        upload_file: FastAPI UploadFile object
        user_id: User ID for directory organization
        preserve_filename: If True, keep original filename
    
    Returns:
        Relative path to saved file
    """
    # Ensure directory exists
    upload_dir = ensure_upload_dir(user_id)
    
    # Generate filename
    if preserve_filename:
        filename = upload_file.filename
    else:
        # Generate unique filename
        file_ext = os.path.splitext(upload_file.filename)[1]
        filename = f"{uuid4()}{file_ext}"
    
    file_path = upload_dir / filename
    
    # Save file
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    
    # Return relative path
    return str(file_path.relative_to(settings.UPLOAD_DIR))


def delete_file(file_path: str) -> bool:
    """
    Delete file from disk.
    
    Args:
        file_path: Relative path to file
    
    Returns:
        True if deleted, False if not found
    """
    full_path = Path(settings.UPLOAD_DIR) / file_path
    
    if full_path.exists():
        full_path.unlink()
        return True
    
    return False


def get_file_info(file_path: str) -> dict:
    """
    Get file information.
    
    Returns:
        Dictionary with file stats
    """
    full_path = Path(settings.UPLOAD_DIR) / file_path
    
    if not full_path.exists():
        return None
    
    stat = full_path.stat()
    
    return {
        'size': stat.st_size,
        'created': datetime.fromtimestamp(stat.st_ctime),
        'modified': datetime.fromtimestamp(stat.st_mtime),
        'extension': full_path.suffix,
        'name': full_path.name
    }


def validate_file_type(filename: str, allowed_types: list) -> bool:
    """
    Validate file extension.
    
    Args:
        filename: Name of file
        allowed_types: List of allowed extensions (e.g., ['.pdf', '.jpg'])
    
    Returns:
        True if valid, False otherwise
    """
    file_ext = os.path.splitext(filename)[1].lower()
    return file_ext in allowed_types


async def save_chunks(
    file: UploadFile,
    destination: Path,
    chunk_size: int = 1024 * 1024  # 1MB chunks
):
    """
    Save large file in chunks (for streaming uploads).
    
    Args:
        file: UploadFile object
        destination: Destination path
        chunk_size: Size of each chunk in bytes
    """
    with destination.open("wb") as buffer:
        while chunk := await file.read(chunk_size):
            buffer.write(chunk)
2. Advanced File Upload Endpoints
python# backend/api/v1/documents.py (extended)

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from typing import List, Optional
import mimetypes
from pathlib import Path

# ... previous imports ...


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(..., description="Document file to upload"),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    document_type: Optional[str] = Form(None),
    category_id: Optional[UUID] = Form(None),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a document with metadata.
    
    **Multipart form data:**
    - file: Document file (required)
    - title: Document title (optional, defaults to filename)
    - description: Document description (optional)
    - document_type: Type of document (optional)
    - category_id: Category UUID (optional)
    - tags: Comma-separated tags (optional)
    
    **File requirements:**
    - Max size: 50MB
    - Allowed: PDF, JPG, JPEG, PNG, TIF, TIFF
    """
    from utils.file_handler import save_upload_file, get_file_hash, validate_file_type
    
    # Validate file type
    if not validate_file_type(file.filename, settings.ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Validate file size
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max: {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB"
        )
    
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty"
        )
    
    # Save file
    try:
        file_path = save_upload_file(file, current_user.id)
        full_path = Path(settings.UPLOAD_DIR) / file_path
        file_hash = get_file_hash(str(full_path))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # Check for duplicate (by hash)
    existing = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.file_hash == file_hash,
        Document.deleted_at.is_(None)
    ).first()
    
    if existing:
        # Delete newly uploaded file
        delete_file(file_path)
        
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document already exists",
            headers={"X-Duplicate-ID": str(existing.id)}
        )
    
    # Parse tags
    tag_list = [tag.strip() for tag in tags.split(",")] if tags else []
    
    # Create document
    document = Document(
        user_id=current_user.id,
        title=title or file.filename,
        description=description,
        document_type=document_type,
        category_id=category_id,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
        file_hash=file_hash,
        tags=tag_list,
        status="pending"
    )
    
    db.add(document)
    db.commit()
    db.refresh(document)
    
    # Trigger OCR processing (async)
    from tasks.ocr_tasks import process_document_ocr
    process_document_ocr.delay(str(document.id))
    
    return document


@router.post("/upload/multiple", response_model=List[DocumentResponse])
async def upload_multiple_documents(
    files: List[UploadFile] = File(..., description="Multiple files to upload"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload multiple documents at once.
    
    **Limits:**
    - Max 10 files per request
    - Each file max 50MB
    """
    if len(files) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 files per request"
        )
    
    documents = []
    errors = []
    
    for file in files:
        try:
            # Validate file
            if not validate_file_type(file.filename, settings.ALLOWED_EXTENSIONS):
                errors.append({
                    "file": file.filename,
                    "error": "Invalid file type"
                })
                continue
            
            # Save file
            file_path = save_upload_file(file, current_user.id)
            full_path = Path(settings.UPLOAD_DIR) / file_path
            
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
            
            file_hash = get_file_hash(str(full_path))
            
            # Create document
            document = Document(
                user_id=current_user.id,
                title=file.filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=file.content_type,
                file_hash=file_hash,
                status="pending"
            )
            
            db.add(document)
            documents.append(document)
            
        except Exception as e:
            errors.append({
                "file": file.filename,
                "error": str(e)
            })
    
    if documents:
        db.commit()
        
        # Trigger OCR for all documents
        from tasks.ocr_tasks import process_document_ocr
        for doc in documents:
            process_document_ocr.delay(str(doc.id))
    
    if errors:
        # Return partial success with errors
        return JSONResponse(
            status_code=status.HTTP_207_MULTI_STATUS,
            content={
                "documents": [DocumentResponse.from_orm(d).dict() for d in documents],
                "errors": errors
            }
        )
    
    return documents


@router.get("/{document_id}/download")
async def download_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download document file.
    
    Returns the original uploaded file.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.deleted_at.is_(None)
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_path = Path(settings.UPLOAD_DIR) / document.file_path
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk"
        )
    
    # Guess MIME type
    mime_type = document.mime_type or mimetypes.guess_type(str(file_path))[0] or 'application/octet-stream'
    
    return FileResponse(
        path=file_path,
        media_type=mime_type,
        filename=document.title,
        headers={
            "Content-Disposition": f'attachment; filename="{document.title}"'
        }
    )


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Preview document inline (for PDFs and images).
    
    Opens file in browser instead of downloading.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id,
        Document.deleted_at.is_(None)
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_path = Path(settings.UPLOAD_DIR) / document.file_path
    
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    return FileResponse(
        path=file_path,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.title}"'
        }
    )


@router.get("/{document_id}/stream")
async def stream_document(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Stream large document (for video/large files).
    
    Supports range requests for partial content.
    """
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
    
    file_path = Path(settings.UPLOAD_DIR) / document.file_path
    
    def iterfile():
        with open(file_path, mode="rb") as file_like:
            yield from file_like
    
    return StreamingResponse(
        iterfile(),
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="{document.title}"',
            "Accept-Ranges": "bytes",
            "Content-Length": str(document.file_size)
        }
    )
3. Chunked Upload (for Large Files)
python# backend/api/v1/documents.py (continued)

from fastapi import BackgroundTasks
import aiofiles


@router.post("/upload/chunked/init")
async def init_chunked_upload(
    filename: str = Form(...),
    file_size: int = Form(...),
    chunk_size: int = Form(1024 * 1024),  # 1MB default
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initialize chunked upload for large files.
    
    Returns upload_id for subsequent chunk uploads.
    """
    from models.documents import ChunkedUpload
    
    # Create chunked upload record
    upload = ChunkedUpload(
        user_id=current_user.id,
        filename=filename,
        file_size=file_size,
        chunk_size=chunk_size,
        total_chunks=(file_size + chunk_size - 1) // chunk_size,
        status="initialized"
    )
    
    db.add(upload)
    db.commit()
    db.refresh(upload)
    
    return {
        "upload_id": str(upload.id),
        "total_chunks": upload.total_chunks,
        "chunk_size": chunk_size
    }


@router.post("/upload/chunked/{upload_id}/chunk/{chunk_number}")
async def upload_chunk(
    upload_id: UUID,
    chunk_number: int,
    chunk: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a single chunk of a large file.
    """
    from models.documents import ChunkedUpload
    
    # Get upload record
    upload = db.query(ChunkedUpload).filter(
        ChunkedUpload.id == upload_id,
        ChunkedUpload.user_id == current_user.id
    ).first()
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found"
        )
    
    if chunk_number < 0 or chunk_number >= upload.total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid chunk number"
        )
    
    # Save chunk
    chunk_dir = Path(settings.UPLOAD_DIR) / "chunks" / str(upload_id)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    
    chunk_path = chunk_dir / f"chunk_{chunk_number}"
    
    async with aiofiles.open(chunk_path, 'wb') as f:
        content = await chunk.read()
        await f.write(content)
    
    # Update uploaded chunks
    if upload.uploaded_chunks is None:
        upload.uploaded_chunks = []
    
    if chunk_number not in upload.uploaded_chunks:
        upload.uploaded_chunks.append(chunk_number)
    
    db.commit()
    
    # Check if all chunks uploaded
    is_complete = len(upload.uploaded_chunks) == upload.total_chunks
    
    return {
        "chunk_number": chunk_number,
        "uploaded_chunks": len(upload.uploaded_chunks),
        "total_chunks": upload.total_chunks,
        "is_complete": is_complete
    }


@router.post("/upload/chunked/{upload_id}/complete", response_model=DocumentResponse)
async def complete_chunked_upload(
    upload_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Complete chunked upload and merge chunks into final file.
    """
    from models.documents import ChunkedUpload
    
    # Get upload record
    upload = db.query(ChunkedUpload).filter(
        ChunkedUpload.id == upload_id,
        ChunkedUpload.user_id == current_user.id
    ).first()
    
    if not upload:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found"
        )
    
    # Check if all chunks uploaded
    if len(upload.uploaded_chunks) != upload.total_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing chunks: {upload.total_chunks - len(upload.uploaded_chunks)}"
        )
    
    # Merge chunks
    chunk_dir = Path(settings.UPLOAD_DIR) / "chunks" / str(upload_id)
    final_path = ensure_upload_dir(current_user.id) / f"{uuid4()}{Path(upload.filename).suffix}"
    
    with open(final_path, 'wb') as final_file:
        for i in range(upload.total_chunks):
            chunk_path = chunk_dir / f"chunk_{i}"
            
            if not chunk_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Chunk {i} not found"
                )
            
            with open(chunk_path, 'rb') as chunk_file:
                final_file.write(chunk_file.read())
    
    # Calculate hash
    file_hash = get_file_hash(str(final_path))
    
    # Create document
    document = Document(
        user_id=current_user.id,
        title=upload.filename,
        file_path=str(final_path.relative_to(settings.UPLOAD_DIR)),
        file_size=upload.file_size,
        mime_type=mimetypes.guess_type(upload.filename)[0],
        file_hash=file_hash,
        status="pending"
    )
    
    db.add(document)
    
    # Update upload status
    upload.status = "completed"
    upload.document_id = document.id
    
    db.commit()
    db.refresh(document)
    
    # Cleanup chunks in background
    def cleanup_chunks():
        shutil.rmtree(chunk_dir, ignore_errors=True)
    
    background_tasks.add_task(cleanup_chunks)
    
    # Trigger OCR
    from tasks.ocr_tasks import process_document_ocr
    background_tasks.add_task(process_document_ocr.delay, str(document.id))
    
    return document

🔍 PAGINATION & FILTERING (Advanced)
1. Cursor-Based Pagination
python# backend/schemas/common.py (extended)

from typing import Optional, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')


class CursorPaginationParams(BaseModel):
    """Cursor-based pagination parameters"""
    cursor: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Cursor-paginated response"""
    items: List[T]
    next_cursor: Optional[str] = None
    has_more: bool
python# backend/api/v1/documents.py (extended)

import base64
import json
from datetime import datetime


@router.get("/feed", response_model=CursorPaginatedResponse[DocumentResponse])
async def get_document_feed(
    cursor: Optional[str] = Query(None, description="Pagination cursor"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get document feed with cursor-based pagination.
    
    **Benefits over offset pagination:**
    - Consistent results even when data changes
    - Fast for any page (no scanning previous rows)
    - Ideal for infinite scroll
    
    **Cursor format:**
    Base64-encoded JSON: {"created_at": "ISO datetime", "id": "UUID"}
    """
    query = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.deleted_at.is_(None)
    )
    
    # Decode cursor
    if cursor:
        try:
            cursor_data = json.loads(base64.b64decode(cursor))
            cursor_created_at = datetime.fromisoformat(cursor_data['created_at'])
            cursor_id = UUID(cursor_data['id'])
            
            # Filter: created_at < cursor OR (created_at = cursor AND id < cursor_id)
            query = query.filter(
                or_(
                    Document.created_at < cursor_created_at,
                    and_(
                        Document.created_at == cursor_created_at,
                        Document.id < cursor_id
                    )
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cursor"
            )
    
    # Order by created_at DESC, id DESC (for consistency)
    query = query.order_by(
        Document.created_at.desc(),
        Document.id.desc()
    )
    
    # Fetch limit + 1 to check if there are more items
    documents = query.limit(limit + 1).all()
    
    # Check if there are more items
    has_more = len(documents) > limit
    items = documents[:limit]
    
    # Generate next cursor
    next_cursor = None
    if has_more and items:
        last_item = items[-1]
        cursor_data = {
            'created_at': last_item.created_at.isoformat(),
            'id': str(last_item.id)
        }
        next_cursor = base64.b64encode(
            json.dumps(cursor_data).encode()
        ).decode()
    
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more
    }
2. Advanced Filtering with Query Builder
python# backend/utils/query_builder.py

from sqlalchemy.orm import Query
from sqlalchemy import or_, and_, func
from typing import Any, Dict, List, Optional
from datetime import datetime


class QueryBuilder:
    """
    Advanced query builder for dynamic filtering.
    
    Supports:
    - Multiple filter operators (eq, ne, gt, lt, contains, in, between)
    - AND/OR combinations
    - Nested filters
    - Full-text search
    """
    
    OPERATORS = {
        'eq': lambda col, val: col == val,
        'ne': lambda col, val: col != val,
        'gt': lambda col, val: col > val,
        'gte': lambda col, val: col >= val,
        'lt': lambda col, val: col < val,
        'lte': lambda col, val: col <= val,
        'contains': lambda col, val: col.ilike(f'%{val}%'),
        'startswith': lambda col, val: col.ilike(f'{val}%'),
        'endswith': lambda col, val: col.ilike(f'%{val}'),
        'in': lambda col, val: col.in_(val),
        'not_in': lambda col, val: ~col.in_(val),
        'between': lambda col, val: col.between(val[0], val[1]),
        'is_null': lambda col, val: col.is_(None) if val else col.isnot(None),
    }
    
    @classmethod
    def apply_filters(
        cls,
        query: Query,
        model: Any,
        filters: Dict[str, Any]
    ) -> Query:
        """
        Apply filters to query.
        
        Example filters:
        {
            "status": {"eq": "completed"},
            "created_at": {"gte": "2024-01-01", "lt": "2024-02-01"},
            "title": {"contains": "invoice"},
            "tags": {"in": ["urgent", "important"]}
        }
        """
        for field, conditions in filters.items():
            if not hasattr(model, field):
                continue
            
            column = getattr(model, field)
            
            if isinstance(conditions, dict):
                # Multiple operators on same field
                for operator, value in conditions.items():
                    if operator in cls.OPERATORS:
                        query = query.filter(
                            cls.OPERATORS[operator](column, value)
                        )
            else:
                # Simple equality
                query = query.filter(column == conditions)
        
        return query
    
    @classmethod
    def apply_search(
        cls,
        query: Query,
        model: Any,
        search_term: str,
        search_fields: List[str]
    ) -> Query:
        """
        Apply full-text search across multiple fields.
        
        Args:
            query: SQLAlchemy query
            model: Model class
            search_term: Search term
            search_fields: List of field names to search in
        """
        if not search_term:
            return query
        
        search_pattern = f'%{search_term}%'
        
        conditions = []
        for field in search_fields:
            if hasattr(model, field):
                column = getattr(model, field)
                conditions.append(column.ilike(search_pattern))
        
        if conditions:
            query = query.filter(or_(*conditions))
        
        return query


# Usage in endpoint:
@router.get("/advanced-search", response_model=List[DocumentResponse])
async def advanced_document_search(
    filters: Optional[str] = Query(
        None,
        description='JSON filters: {"status": {"eq": "completed"}, "created_at": {"gte": "2024-01-01"}}'
    ),
    search: Optional[str] = Query(None, description="Full-text search"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Advanced document search with complex filters.
    
    **Filter operators:**
    - eq: Equal
    - ne: Not equal
    - gt/gte: Greater than / Greater than or equal
    - lt/lte: Less than / Less than or equal
    - contains: Contains substring (case-insensitive)
    - in: In list
    - between: Between two values
    
    **Example:**
```json
    {
        "status": {"eq": "completed"},
        "file_size": {"gte": 1000000},
        "created_at": {"between": ["2024-01-01", "2024-12-31"]},
        "tags": {"in": ["invoice", "receipt"]}
    }
```
    """
    query = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.deleted_at.is_(None)
    )
    
    # Apply filters
    if filters:
        try:
            filter_dict = json.loads(filters)
            query = QueryBuilder.apply_filters(query, Document, filter_dict)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON in filters parameter"
            )
    
    # Apply search
    if search:
        query = QueryBuilder.apply_search(
            query,
            Document,
            search,
            ['title', 'description']
        )
    
    documents = query.all()
    
    return documents

⚠️ ERROR HANDLING
1. Custom Exception Classes
python# backend/core/exceptions.py

from fastapi import HTTPException, status
from typing import Optional, Any, Dict


class AppException(HTTPException):
    """Base application exception"""
    
    def __init__(
        self,
        status_code: int,
        detail: str,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)


class NotFoundException(AppException):
    """Resource not found"""
    
    def __init__(self, resource: str, identifier: Any = None):
        detail = f"{resource} not found"
        if identifier:
            detail += f": {identifier}"
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class ValidationException(AppException):
    """Validation error"""
    
    def __init__(self, detail: str, errors: Optional[list] = None):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail
        )
        self.errors = errors


class ConflictException(AppException):
    """Resource conflict"""
    
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class UnauthorizedException(AppException):
    """Unauthorized access"""
    
    def __init__(self, detail: str = "Unauthorized"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class ForbiddenException(AppException):
    """Forbidden access"""
    
    def __init__(self, detail: str = "Forbidden"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class RateLimitException(AppException):
    """Rate limit exceeded"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)}
        )


class ServiceUnavailableException(AppException):
    """Service temporarily unavailable"""
    
    def __init__(self, detail: str = "Service temporarily unavailable"):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail
        )


# Usage in endpoints:
@router.get("/{document_id}")
async def get_document(document_id: UUID, db: Session = Depends(get_db)):
    document = db.query(Document).get(document_id)
    
    if not document:
        raise NotFoundException("Document", document_id)
    
    return document
2. Global Exception Handlers
python# backend/main.py (extended)

from core.exceptions import (
    AppException,
    NotFoundException,
    ValidationException,
    UnauthorizedException
)
from sqlalchemy.exc import IntegrityError, OperationalError


@app.exception_handler(NotFoundException)
async def not_found_exception_handler(request: Request, exc: NotFoundException):
    """Handle not found exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "Not Found",
            "detail": exc.detail,
            "path": request.url.path
        }
    )


@app.exception_handler(ValidationException)
async def validation_exception_handler(request: Request, exc: ValidationException):
    """Handle validation exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "Validation Error",
            "detail": exc.detail,
            "errors": exc.errors if hasattr(exc, 'errors') else None
        }
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError):
    """Handle database integrity errors"""
    logger.error(f"Database integrity error: {exc}")
    
    # Parse common integrity errors
    error_msg = str(exc.orig)
    
    if "unique constraint" in error_msg.lower():
        detail = "Resource already exists"
    elif "foreign key constraint" in error_msg.lower():
        detail = "Related resource not found"
    else:
        detail = "Database constraint violation"
    
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "Conflict",
            "detail": detail
        }
    )


@app.exception_handler(OperationalError)
async def operational_error_handler(request: Request, exc: OperationalError):
    """Handle database operational errors"""
    logger.error(f"Database operational error: {exc}")
    
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Service Unavailable",
            "detail": "Database temporarily unavailable"
        }
    )

🔌 WEBSOCKET ENDPOINTS
python# backend/api/v1/websocket.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import List, Dict
import json
import asyncio
from datetime import datetime

from core.dependencies import get_db
from models.auth import User


router = APIRouter()


class ConnectionManager:
    """
    WebSocket connection manager.
    
    Manages active WebSocket connections for real-time updates.
    """
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register new connection"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        logger.info(f"WebSocket connected: user={user_id}")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove connection"""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        logger.info(f"WebSocket disconnected: user={user_id}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send message to specific user"""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    # Remove dead connection
                    self.disconnect(connection, user_id)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected users"""
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except:
                    self.disconnect(connection, user_id)


manager = ConnectionManager()


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(..., description="JWT access token")
):
    """
    WebSocket endpoint for real-time updates.
    
    **Connection:**
```javascript
    const ws = new WebSocket('ws://localhost:8000/api/v1/ws/USER_ID?token=JWT_TOKEN');
```
    
    **Message types:**
    - ocr_progress: OCR processing progress
    - ocr_complete: OCR completed
    - document_updated: Document metadata updated
    - notification: General notification
    """
    from jose import jwt, JWTError
    from core.config import settings
    
    # Verify token
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        token_user_id = payload.get("sub")
        
        if token_user_id != user_id:
            await websocket.close(code=1008, reason="Unauthorized")
            return
    except JWTError:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    # Connect
    await manager.connect(websocket, user_id)
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connection_established",
            "message": "Connected to OCR Backend",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                # Handle ping/pong
                if message_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Handle other message types
                elif message_type == "subscribe":
                    # Subscribe to specific events
                    await websocket.send_json({
                        "type": "subscribed",
                        "events": message.get("events", [])
                    })
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, user_id)


# Helper function to send OCR progress updates
async def send_ocr_progress(user_id: str, document_id: str, progress: int, status: str):
    """
    Send OCR progress update via WebSocket.
    
    Called from Celery tasks.
    """
    await manager.send_personal_message(
        {
            "type": "ocr_progress",
            "document_id": document_id,
            "progress": progress,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        },
        user_id=user_id
    )


async def send_ocr_complete(user_id: str, document_id: str, success: bool, result: dict = None):
    """Send OCR completion notification"""
    await manager.send_personal_message(
        {
            "type": "ocr_complete",
            "document_id": document_id,
            "success": success,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        },
        user_id=user_id
    )
WebSocket Client Example (JavaScript)
javascript// frontend/websocket-client.js

class OCRWebSocket {
    constructor(userId, token) {
        this.userId = userId;
        this.token = token;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
    }
    
    connect() {
        const wsUrl = `ws://localhost:8000/api/v1/ws/${this.userId}?token=${this.token}`;
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            
            // Start ping interval
            this.pingInterval = setInterval(() => {
                this.send({ type: 'ping' });
            }, 30000);
        };
        
        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket closed');
            clearInterval(this.pingInterval);
            this.reconnect();
        };
    }
    
    handleMessage(data) {
        switch (data.type) {
            case 'connection_established':
                console.log('Connection established:', data.message);
                break;
            
            case 'ocr_progress':
                console.log(`OCR Progress: ${data.progress}%`);
                // Update UI progress bar
                this.onOCRProgress(data);
                break;
            
            case 'ocr_complete':
                console.log('OCR Complete:', data.success);
                // Update document in UI
                this.onOCRComplete(data);
                break;
            
            case 'pong':
                // Pong received
                break;
            
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    reconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;
            
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
            
            setTimeout(() => {
                this.connect();
            }, delay);
        } else {
            console.error('Max reconnection attempts reached');
        }
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
    
    // Event handlers (override these)
    onOCRProgress(data) {}
    onOCRComplete(data) {}
}

// Usage:
const ws = new OCRWebSocket(userId, jwtToken);

ws.onOCRProgress = (data) => {
    document.getElementById(`progress-${data.document_id}`).value = data.progress;
};

ws.onOCRComplete = (data) => {
    if (data.success) {
        alert('OCR processing completed!');
        // Reload document
        fetchDocument(data.document_id);
    }
};

ws.connect();