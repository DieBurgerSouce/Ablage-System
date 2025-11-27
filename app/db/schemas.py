"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pathlib import Path
import uuid

from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator, ConfigDict


# Enums (matching SQLAlchemy models)
class ProcessingStatus(str, Enum):
    """Document processing status."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OCRBackend(str, Enum):
    """Available OCR backends."""
    AUTO = "auto"
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"
    SURYA_GPU = "surya_gpu"


class DocumentType(str, Enum):
    """Document type classification."""
    INVOICE = "invoice"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    FORM = "form"
    LETTER = "letter"
    REPORT = "report"
    OTHER = "other"


# User Schemas
class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    full_name: Optional[str] = None
    preferred_language: str = Field(default="de", pattern="^(de|en)$")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Benutzername darf nur Buchstaben, Zahlen, Unterstrich und Bindestrich enthalten")
        return v.lower()


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """User update schema."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    preferred_language: Optional[str] = Field(None, pattern="^(de|en)$")
    preferred_ocr_backend: Optional[str] = None


class UserChangePassword(BaseModel):
    """Schema for password change."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=100)


class UserInDB(UserBase):
    """User schema with ID and hashed password."""
    id: uuid.UUID
    hashed_password: str
    is_active: bool = True
    is_superuser: bool = False
    preferred_ocr_backend: str = "auto"
    daily_quota: int = 100
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    documents_processed_today: int = 0
    model_config = ConfigDict(from_attributes=True)


class UserResponse(UserBase):
    """User response schema (public - no password)."""
    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    preferred_ocr_backend: str
    daily_quota: int
    created_at: datetime
    last_login: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Document Schemas
class DocumentBase(BaseModel):
    """Base document schema."""
    filename: str
    language: str = "de"
    document_type: DocumentType = DocumentType.OTHER


class DocumentCreate(DocumentBase):
    """Document creation schema."""
    backend: OCRBackend = OCRBackend.AUTO
    detect_layout: bool = True


class DocumentUpdate(BaseModel):
    """Document update schema."""
    document_type: Optional[DocumentType] = None
    language: Optional[str] = None
    tags: Optional[List[str]] = None


class DocumentInDB(DocumentBase):
    """Document schema with all fields."""
    id: uuid.UUID
    owner_id: uuid.UUID
    status: ProcessingStatus
    file_size: int
    mime_type: Optional[str]
    page_count: int
    created_at: datetime
    updated_at: datetime
    
    # Processing info
    processing_started_at: Optional[datetime]
    processing_completed_at: Optional[datetime]
    processing_duration_ms: Optional[int]
    ocr_backend: Optional[str]
    ocr_confidence: Optional[float]
    
    # Extracted content
    extracted_text: Optional[str]
    extracted_metadata: Dict[str, Any] = {}
    has_umlauts: Optional[bool]
    german_validation_score: Optional[float]
    
    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(DocumentInDB):
    """Document response schema."""
    storage_url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Document list response."""
    total: int
    page: int
    per_page: int
    documents: List[DocumentResponse]


# Processing Job Schemas
class ProcessingJobCreate(BaseModel):
    """Processing job creation schema."""
    document_id: uuid.UUID
    job_type: str = "ocr"
    backend: OCRBackend = OCRBackend.AUTO
    priority: int = Field(5, ge=1, le=10)


class ProcessingJobUpdate(BaseModel):
    """Processing job update schema."""
    status: Optional[ProcessingStatus]
    progress: Optional[int] = Field(None, ge=0, le=100)
    message: Optional[str]
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]


class ProcessingJobResponse(BaseModel):
    """Processing job response schema."""
    id: uuid.UUID
    document_id: uuid.UUID
    status: ProcessingStatus
    progress: int
    message: Optional[str]
    backend: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# OCR Request/Response Schemas
class OCRRequest(BaseModel):
    """OCR processing request."""
    backend: OCRBackend = OCRBackend.AUTO
    language: str = "de"
    detect_layout: bool = True
    extract_entities: bool = True
    priority: int = Field(5, ge=1, le=10)


class OCRResult(BaseModel):
    """OCR processing result."""
    success: bool
    text: Optional[str]
    confidence: Optional[float]
    backend_used: str
    processing_time_ms: int
    
    # German validation
    has_umlauts: bool = False
    german_validation_score: Optional[float]
    
    # Extracted data
    dates: List[str] = []
    amounts: List[Dict[str, Any]] = []
    entities: Dict[str, List[str]] = {}
    ibans: List[str] = []
    vat_ids: List[str] = []
    
    # Layout data
    layout: Optional[Dict[str, Any]]
    
    # Metadata
    page_count: int = 1
    language_detected: Optional[str]
    warnings: List[str] = []


class BatchOCRRequest(BaseModel):
    """Batch OCR processing request."""
    document_ids: List[uuid.UUID]
    backend: OCRBackend = OCRBackend.AUTO
    language: str = "de"
    priority: int = Field(5, ge=1, le=10)


class BatchOCRResponse(BaseModel):
    """Batch OCR processing response."""
    job_ids: List[uuid.UUID]
    total: int
    queued: int
    message: str


# System/Health Schemas
class HealthCheck(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    components: Dict[str, Any]
    message: Optional[str]


class GPUStatus(BaseModel):
    """GPU status information."""
    available: bool
    device_name: Optional[str]
    device_id: Optional[int]
    memory_used_mb: Optional[float]
    memory_total_mb: Optional[float]
    utilization_percent: Optional[float]
    temperature_celsius: Optional[float]


class SystemStats(BaseModel):
    """System statistics."""
    documents_total: int
    documents_processed_today: int
    active_jobs: int
    average_processing_time_ms: float
    success_rate: float
    gpu_status: GPUStatus


# Authentication Schemas
class Token(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Token payload data."""
    sub: str  # user_id
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"
    jti: str  # unique token ID


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """Logout request."""
    refresh_token: Optional[str] = None


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Tag Schemas
class TagCreate(BaseModel):
    """Tag creation schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class TagResponse(BaseModel):
    """Tag response schema."""
    id: uuid.UUID
    name: str
    description: Optional[str]
    color: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# Error Schemas  
class ErrorResponse(BaseModel):
    """Error response schema."""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None


# ============================================================================
# STORAGE SCHEMAS
# ============================================================================

class DocumentUploadRequest(BaseModel):
    """Document upload request schema."""
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = None
    document_type: DocumentType = DocumentType.OTHER
    language: str = Field(default="de", pattern="^(de|en)$")
    tags: List[str] = []
    metadata: Dict[str, str] = {}
    enable_versioning: bool = True

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate filename format."""
        # Prevent path traversal
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Ungültiger Dateiname")

        # Check extension
        allowed_ext = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"]
        ext = Path(v).suffix.lower()
        if ext not in allowed_ext:
            raise ValueError(f"Dateiformat nicht erlaubt. Erlaubt: {', '.join(allowed_ext)}")

        return v


class DocumentUploadResponse(BaseModel):
    """Document upload response schema."""
    success: bool
    document_id: uuid.UUID
    storage_path: str
    bucket: str
    size_bytes: int
    stored_size_bytes: int
    compressed: bool
    content_type: str
    sha256: str
    upload_timestamp: str
    message: str = "Dokument erfolgreich hochgeladen"


class DocumentDownloadResponse(BaseModel):
    """Document download response schema (for metadata, not actual file)."""
    filename: str
    content_type: str
    size_bytes: int
    download_url: Optional[str] = None


class DocumentVersionInfo(BaseModel):
    """Document version information."""
    version_key: str
    size: int
    last_modified: Optional[str]
    etag: Optional[str]
    version_number: int


class DocumentVersionListResponse(BaseModel):
    """List of document versions."""
    document_id: uuid.UUID
    current_version: str
    versions: List[DocumentVersionInfo]
    total_versions: int


class PresignedUrlResponse(BaseModel):
    """Presigned URL response."""
    url: str
    expires_at: datetime
    expiry_hours: int


class StorageStatsResponse(BaseModel):
    """Storage statistics response."""
    documents: Dict[str, int]
    thumbnails: Dict[str, int]
    exports: Dict[str, int]
    archive: Dict[str, int]
    versions: Dict[str, int]
    total_size_bytes: int
    total_count: int
    total_size_mb: float


# ============================================================================
# OCR VERSION SCHEMAS
# ============================================================================

class OCRVersionBase(BaseModel):
    """Base schema for OCR version."""
    version_number: int
    backend: str
    confidence_score: Optional[float] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None
    has_umlauts: bool = False
    german_validation_score: Optional[float] = None
    processing_time_ms: Optional[int] = None


class OCRVersionCreate(BaseModel):
    """Schema for creating a new OCR version."""
    document_id: uuid.UUID
    version_note: Optional[str] = Field(None, max_length=500)


class OCRVersionResponse(OCRVersionBase):
    """Full OCR version response schema."""
    id: uuid.UUID
    document_id: uuid.UUID
    ocr_result_id: Optional[uuid.UUID] = None
    is_current: bool
    is_rollback: bool
    rollback_from_version: Optional[int] = None
    extracted_text: Optional[str] = None
    detected_dates: List[str] = []
    detected_amounts: List[Dict[str, Any]] = []
    detected_ibans: List[str] = []
    detected_vat_ids: List[str] = []
    business_terms: List[Dict[str, Any]] = []
    detected_layout: Dict[str, Any] = {}
    bounding_boxes: List[Dict[str, Any]] = []
    created_at: datetime
    created_by_id: Optional[uuid.UUID] = None
    version_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OCRVersionSummary(OCRVersionBase):
    """Summary schema for version listings (without full text)."""
    id: uuid.UUID
    is_current: bool
    is_rollback: bool
    rollback_from_version: Optional[int] = None
    created_at: datetime
    version_note: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class OCRVersionListResponse(BaseModel):
    """List of OCR versions for a document."""
    document_id: uuid.UUID
    document_filename: str
    current_version: int
    total_versions: int
    versions: List[OCRVersionSummary]


class OCRVersionCompareRequest(BaseModel):
    """Request schema for comparing two versions."""
    version_a: int = Field(..., ge=1, description="Erste Version zum Vergleichen")
    version_b: int = Field(..., ge=1, description="Zweite Version zum Vergleichen")

    @model_validator(mode='after')
    def versions_must_differ(self) -> 'OCRVersionCompareRequest':
        """Validate that version_a and version_b are different."""
        if self.version_a == self.version_b:
            raise ValueError("Versionen müssen unterschiedlich sein")
        return self


class OCRVersionDiff(BaseModel):
    """Structured diff information between versions."""
    backend_changed: bool
    text_length_delta: int
    dates_count_delta: int
    amounts_count_delta: int
    ibans_count_delta: int
    vat_ids_count_delta: int
    confidence_improved: Optional[bool] = None


class OCRVersionCompareResponse(BaseModel):
    """Response schema for version comparison."""
    document_id: uuid.UUID
    version_a: OCRVersionResponse
    version_b: OCRVersionResponse
    differences: OCRVersionDiff
    text_diff_html: Optional[str] = None  # HTML diff for side-by-side view
    text_diff_unified: Optional[str] = None  # Unified diff like git
    confidence_delta: Optional[float] = None
    word_count_delta: Optional[int] = None


class OCRVersionRollbackRequest(BaseModel):
    """Request schema for rollback to a previous version."""
    target_version: int = Field(..., ge=1, description="Zielversion fur Rollback")
    rollback_note: Optional[str] = Field(
        None,
        max_length=500,
        description="Optionale Notiz fur diesen Rollback"
    )


class OCRVersionRollbackResponse(BaseModel):
    """Response schema for rollback result."""
    success: bool
    new_version_number: int
    rolled_back_from: int
    message: str  # German message
