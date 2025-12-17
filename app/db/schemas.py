"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
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
    DONUT = "donut"
    SURYA = "surya"
    SURYA_GPU = "surya_gpu"
    HYBRID = "hybrid"


class DocumentType(str, Enum):
    """Document type classification."""
    INVOICE = "invoice"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    FORM = "form"
    LETTER = "letter"
    REPORT = "report"
    OTHER = "other"


class DataCategory(str, Enum):
    """GDPR data category for retention policies."""
    PERSONAL_IDENTIFIABLE = "personal_identifiable"  # 365 Tage
    SPECIAL_CATEGORY = "special_category"  # 180 Tage (Gesundheit, Religion, etc.)
    FINANCIAL = "financial"  # 3650 Tage (10 Jahre HGB)
    CONTACT = "contact"  # 365 Tage
    DOCUMENT_CONTENT = "document_content"  # 2555 Tage (7 Jahre HGB)
    METADATA = "metadata"  # 90 Tage
    ANONYMOUS = "anonymous"  # Unbegrenzt


class DocumentMetadata(BaseModel):
    """
    Typisiertes Schema für Dokument-Metadata.

    SICHERHEIT: Verhindert willkürliche Daten-Injektion durch strikte Validierung.
    Nur definierte Felder sind erlaubt (extra="forbid").
    """
    # Quelle und Ursprung
    source: Optional[str] = Field(None, max_length=200, description="Ursprung des Dokuments")
    source_url: Optional[str] = Field(None, max_length=500, description="URL des Ursprungs")

    # Benutzerdefinierte Felder
    custom_tags: Optional[List[str]] = Field(
        default=None,
        max_length=20,
        description="Benutzerdefinierte Tags (max 20)"
    )
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Notizen zum Dokument (max 2000 Zeichen)"
    )

    # Geschäftliche Informationen
    customer_id: Optional[str] = Field(None, max_length=100, description="Kunden-ID")
    project_id: Optional[str] = Field(None, max_length=100, description="Projekt-ID")
    department: Optional[str] = Field(None, max_length=100, description="Abteilung")

    # Dokumentenspezifisch
    invoice_number: Optional[str] = Field(None, max_length=50, description="Rechnungsnummer")
    contract_number: Optional[str] = Field(None, max_length=50, description="Vertragsnummer")
    reference_number: Optional[str] = Field(None, max_length=50, description="Referenznummer")

    # Validierung: Keine zusätzlichen Felder erlaubt
    model_config = ConfigDict(extra="forbid")

    @field_validator("custom_tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validiere Tags: max 50 Zeichen pro Tag, keine Sonderzeichen."""
        if v is None:
            return v
        validated = []
        for tag in v:
            if len(tag) > 50:
                raise ValueError(f"Tag zu lang: max 50 Zeichen, gefunden {len(tag)}")
            # Nur alphanumerische Zeichen, Bindestriche und Unterstriche
            if not tag.replace("-", "").replace("_", "").replace(" ", "").isalnum():
                raise ValueError(f"Tag enthält ungültige Zeichen: {tag}")
            validated.append(tag.strip().lower())
        return validated


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
    filename: str = Field(..., min_length=1, max_length=255, description="Dateiname")
    language: str = Field(default="de", pattern="^[a-z]{2}$", max_length=5, description="Sprache (ISO 639-1)")
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
    status: Optional[ProcessingStatus] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    message: Optional[str] = Field(None, max_length=500, description="Status-Nachricht")
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = Field(None, max_length=2000, description="Fehlermeldung")


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
    language: str = Field(default="de", pattern="^(de|en)$", description="Zielsprache")
    detect_layout: bool = True
    extract_entities: bool = True
    priority: int = Field(5, ge=1, le=10, description="Verarbeitungsprioritaet (1-10)")


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
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    backend: OCRBackend = OCRBackend.AUTO
    language: str = Field(default="de", pattern="^(de|en)$")
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
    session_warning: Optional[str] = None  # Warnung über automatisch beendete Sessions


# Alias für Backwards-Kompatibilität mit Tests
TokenResponse = Token


class TokenPayload(BaseModel):
    """Token payload data."""
    sub: str  # user_id
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"
    jti: str  # unique token ID


class LoginRequest(BaseModel):
    """Login request."""
    email: EmailStr = Field(..., max_length=254, description="RFC 5321 max email length")
    password: str = Field(..., min_length=1, max_length=256, description="Passwort")


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str = Field(..., min_length=32, max_length=512, description="JWT Refresh Token")


class LogoutRequest(BaseModel):
    """Logout request."""
    refresh_token: Optional[str] = None


# Password Reset Schemas
class PasswordResetRequest(BaseModel):
    """Request password reset via email."""
    email: EmailStr = Field(..., max_length=254, description="RFC 5321 max email length")


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with token."""
    token: str = Field(..., min_length=32, max_length=64)
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements."""
        if not any(c.isupper() for c in v):
            raise ValueError("Passwort muss mindestens einen Großbuchstaben enthalten")
        if not any(c.islower() for c in v):
            raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
        if not any(c.isdigit() for c in v):
            raise ValueError("Passwort muss mindestens eine Zahl enthalten")
        if not any(c in "!@#$%^&*(),.?\":{}|<>-_=+[]'" for c in v):
            raise ValueError("Passwort muss mindestens ein Sonderzeichen enthalten")
        return v


class PasswordResetValidate(BaseModel):
    """Validate a password reset token."""
    token: str = Field(..., min_length=32, max_length=64)


class PasswordResetResponse(BaseModel):
    """Password reset response."""
    success: bool
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


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


# ============================================================================
# SEARCH SCHEMAS
# ============================================================================

class SearchType(str, Enum):
    """Search type options."""
    FTS = "fts"  # Full-text search only
    SEMANTIC = "semantic"  # Semantic/vector search only
    HYBRID = "hybrid"  # Combined FTS + semantic


class SortField(str, Enum):
    """Available sort fields for document listing."""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    FILENAME = "filename"
    FILE_SIZE = "file_size"
    OCR_CONFIDENCE = "ocr_confidence"
    RELEVANCE = "relevance"  # For search results


class SortOrder(str, Enum):
    """Sort order options."""
    ASC = "asc"
    DESC = "desc"


class FavoriteSortField(str, Enum):
    """Sort fields for favorites listing."""
    PRIORITY = "priority"
    CREATED_AT = "created_at"


class UserSortField(str, Enum):
    """Sort fields for user administration."""
    CREATED_AT = "created_at"
    EMAIL = "email"
    USERNAME = "username"
    LAST_LOGIN = "last_login"


class AuditSortField(str, Enum):
    """Sort fields for audit log listing."""
    CREATED_AT = "created_at"
    USER_ID = "user_id"
    ACTION = "action"
    RESOURCE_TYPE = "resource_type"


class JobSortField(str, Enum):
    """Sort fields for job administration."""
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    STATUS = "status"
    PRIORITY = "priority"


class SearchFilters(BaseModel):
    """Filters for document search and listing."""
    document_type: Optional[DocumentType] = None
    status: Optional[ProcessingStatus] = None
    tags: Optional[List[str]] = Field(None, description="Filter by tag names")
    date_from: Optional[datetime] = Field(None, description="Filter documents created after this date")
    date_to: Optional[datetime] = Field(None, description="Filter documents created before this date")
    confidence_min: Optional[float] = Field(None, ge=0, le=100, description="Minimum OCR confidence score")
    has_embedding: Optional[bool] = Field(None, description="Filter by embedding availability")
    language: Optional[str] = Field(None, pattern="^(de|en)$")


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(1, ge=1, description="Page number (1-based)")
    per_page: int = Field(20, ge=1, le=100, description="Items per page")


class SearchRequest(BaseModel):
    """Search request schema."""
    query: str = Field(..., min_length=1, max_length=1000, description="Suchbegriff")
    search_type: SearchType = Field(SearchType.HYBRID, description="Art der Suche")
    filters: Optional[SearchFilters] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    sort_by: SortField = Field(SortField.RELEVANCE)
    sort_order: SortOrder = Field(SortOrder.DESC)
    highlight: bool = Field(True, description="Include text highlights in results")
    similarity_threshold: float = Field(0.5, ge=0, le=1, description="Minimum similarity for semantic search")


class SearchResultItem(BaseModel):
    """Single search result item."""
    document_id: uuid.UUID
    filename: str
    original_filename: str
    document_type: DocumentType
    status: ProcessingStatus
    created_at: datetime
    updated_at: datetime
    file_size: int
    page_count: Optional[int] = None
    ocr_confidence: Optional[float] = None

    # Search relevance scores
    score: float = Field(..., description="Combined relevance score (0-1)")
    fts_rank: Optional[float] = Field(None, description="Full-text search rank")
    semantic_similarity: Optional[float] = Field(None, description="Semantic similarity score")

    # Text snippets with highlighting
    highlight: Optional[str] = Field(None, description="Text snippet with search term highlighting")
    text_preview: Optional[str] = Field(None, max_length=500, description="Preview of extracted text")

    # Metadata
    tags: List[str] = []
    owner_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel):
    """Search response with results and metadata."""
    query: str
    search_type: SearchType
    total: int = Field(..., description="Total number of matching documents")
    page: int
    per_page: int
    total_pages: int
    results: List[SearchResultItem]
    took_ms: int = Field(..., description="Query execution time in milliseconds")
    filters_applied: Dict[str, Any] = {}
    analytics_id: Optional[uuid.UUID] = Field(None, description="Analytics ID for click tracking")


class SimilarDocumentsRequest(BaseModel):
    """Request for finding similar documents."""
    limit: int = Field(10, ge=1, le=50, description="Maximum number of similar documents")
    similarity_threshold: float = Field(0.6, ge=0, le=1, description="Minimum similarity score")
    exclude_same_type: bool = Field(False, description="Exclude documents of the same type")


class SimilarDocumentItem(BaseModel):
    """Similar document result."""
    document_id: uuid.UUID
    filename: str
    document_type: DocumentType
    similarity: float
    created_at: datetime
    text_preview: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# BATCH OPERATION SCHEMAS
# ============================================================================

class TagOperation(str, Enum):
    """Tag operation types for batch tagging."""
    ADD = "add"
    REMOVE = "remove"
    SET = "set"  # Replace all tags


class ExportFormat(str, Enum):
    """Export format options."""
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    ZIP = "zip"  # Multiple files as ZIP


class BatchDeleteRequest(BaseModel):
    """Request for batch document deletion with safety features.

    Safeguards:
    - confirm: Must be true to execute
    - dry_run: Simulate deletion without executing
    - X-Force-Confirm header required for >50 documents

    Beispiel dry_run Request:
        POST /documents/batch/delete
        {"document_ids": [...], "confirm": true, "dry_run": true}
    """
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    confirm: bool = Field(..., description="Bestaetigung erforderlich (muss true sein)")
    dry_run: bool = Field(
        default=False,
        description="Nur simulieren, nicht loeschen. Zeigt welche Dokumente betroffen waeren."
    )

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Löschung muss mit confirm=true bestätigt werden")
        return v


class BatchTagRequest(BaseModel):
    """Request for batch tagging documents."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    tags: List[str] = Field(..., min_length=1, max_length=20)
    operation: TagOperation = Field(TagOperation.ADD)


class BatchExportRequest(BaseModel):
    """Request for batch document export."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    format: ExportFormat = Field(ExportFormat.JSON)
    include_text: bool = Field(True, description="Include extracted text in export")
    include_metadata: bool = Field(True, description="Include document metadata")
    include_original_files: bool = Field(False, description="Include original document files")


class BatchFetchRequest(BaseModel):
    """Request for batch document fetch.

    Ermoeglicht das Abrufen mehrerer Dokumente in einem API-Call.
    Reduziert Netzwerk-Overhead bei Frontend-Dashboard-Ansichten.

    Beispiel:
        POST /api/v1/documents/batch/fetch
        {"document_ids": ["uuid1", "uuid2"], "include_text": false}
    """
    document_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Liste der Dokument-IDs (max 50)"
    )
    include_text: bool = Field(
        default=False,
        description="Extrahierten Text inkludieren (erhöht Response-Größe)"
    )
    include_ocr_metadata: bool = Field(
        default=True,
        description="OCR-Metadaten inkludieren (Confidence, Backend, etc.)"
    )


class BatchFetchResponse(BaseModel):
    """Response for batch document fetch."""
    success: bool
    total_requested: int
    found: int
    not_found: int
    documents: List["DocumentDetailResponse"]
    not_found_ids: List[uuid.UUID] = Field(
        default_factory=list,
        description="IDs der nicht gefundenen Dokumente"
    )


class BatchOperationError(BaseModel):
    """Error details for a single item in batch operation."""
    document_id: uuid.UUID
    error: str
    error_code: Optional[str] = None


class BatchOperationResult(BaseModel):
    """Result of a batch operation."""
    success: bool
    operation: str
    total_requested: int
    processed: int
    failed: int
    errors: List[BatchOperationError] = []
    message: str  # German message
    dry_run: bool = Field(default=False, description="War dies eine Simulation?")
    affected_documents: Optional[List[uuid.UUID]] = Field(
        default=None,
        description="IDs der betroffenen Dokumente (bei dry_run)"
    )


class BatchExportResult(BatchOperationResult):
    """Result of batch export operation."""
    download_url: Optional[str] = None
    expires_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    format: ExportFormat


# ============================================================================
# DOCUMENT CRUD SCHEMAS (Extended)
# ============================================================================

class DocumentCreateRequest(BaseModel):
    """Extended document creation request."""
    document_type: DocumentType = Field(DocumentType.OTHER)
    language: str = Field("de", pattern="^(de|en)$")
    tags: List[str] = Field(default_factory=list, max_length=20)
    metadata: Dict[str, str] = Field(default_factory=dict)
    ocr_backend: OCRBackend = Field(OCRBackend.AUTO)
    priority: int = Field(5, ge=1, le=10)
    generate_embedding: bool = Field(True, description="Generate semantic embedding after OCR")


class DocumentCreateResponse(BaseModel):
    """Response nach erfolgreichem Document Upload."""
    id: uuid.UUID = Field(..., description="Dokument-ID")
    filename: str = Field(..., description="Gespeicherter Dateiname")
    original_filename: str = Field(..., description="Original-Dateiname")
    file_size: int = Field(..., description="Dateigröße in Bytes")
    mime_type: str = Field(..., description="MIME-Type")
    status: ProcessingStatus = Field(..., description="Verarbeitungsstatus")
    storage_path: str = Field(..., description="Pfad im Object Storage")
    created_at: datetime = Field(..., description="Erstellungszeitpunkt")
    processing_job_id: Optional[uuid.UUID] = Field(None, description="ID des OCR-Jobs (falls gestartet)")
    message: str = Field(..., description="Statusnachricht")

    model_config = {"from_attributes": True}


class DocumentUpdateRequest(BaseModel):
    """Document update request."""
    document_type: Optional[DocumentType] = None
    language: Optional[str] = Field(None, pattern="^(de|en)$")
    tags: Optional[List[str]] = Field(None, max_length=20)
    metadata: Optional[DocumentMetadata] = Field(
        None,
        description="Typisierte Metadaten - nur definierte Felder erlaubt"
    )
    data_category: Optional[DataCategory] = Field(
        None,
        description="GDPR-Datenkategorie für Aufbewahrungsfristen"
    )


class DocumentPartialUpdateRequest(BaseModel):
    """Partial document update request (PATCH).

    Phase 2.1: Ermöglicht partielle Updates einzelner Felder.
    Nur angegebene Felder werden aktualisiert.
    """
    document_type: Optional[DocumentType] = Field(None, description="Dokumenttyp ändern")
    language: Optional[str] = Field(None, pattern="^(de|en)$", description="Sprache ändern")
    tags: Optional[List[str]] = Field(None, max_length=20, description="Tags ersetzen")
    add_tags: Optional[List[str]] = Field(None, max_length=20, description="Tags hinzufügen")
    remove_tags: Optional[List[str]] = Field(None, max_length=20, description="Tags entfernen")
    metadata: Optional[Dict[str, str]] = Field(None, description="Metadaten aktualisieren")

    @model_validator(mode='after')
    def validate_tags_operations(self) -> 'DocumentPartialUpdateRequest':
        """Ensure tags operations are mutually exclusive."""
        tag_ops = [self.tags, self.add_tags, self.remove_tags]
        non_none = [op for op in tag_ops if op is not None]
        if len(non_none) > 1:
            raise ValueError(
                "Nur eine Tag-Operation erlaubt: tags (ersetzen), add_tags, oder remove_tags"
            )
        return self


class DocumentFilterForBulkUpdate(BaseModel):
    """Filter für Bulk-Update Operationen.

    Phase 2.2: Ermöglicht Updates basierend auf Filterkriterien.
    """
    document_ids: Optional[List[uuid.UUID]] = Field(
        None,
        max_length=100,
        description="Spezifische Dokument-IDs (max. 100)"
    )
    document_type: Optional[DocumentType] = Field(None, description="Nach Dokumenttyp filtern")
    status: Optional[ProcessingStatus] = Field(None, description="Nach Status filtern")
    date_from: Optional[datetime] = Field(None, description="Erstellt nach")
    date_to: Optional[datetime] = Field(None, description="Erstellt vor")
    tags: Optional[List[str]] = Field(None, description="Dokumente mit diesen Tags")

    @model_validator(mode='after')
    def validate_has_filter(self) -> 'DocumentFilterForBulkUpdate':
        """Ensure at least one filter is provided."""
        has_filter = any([
            self.document_ids,
            self.document_type,
            self.status,
            self.date_from,
            self.date_to,
            self.tags
        ])
        if not has_filter:
            raise ValueError("Mindestens ein Filter muss angegeben werden")
        return self


class BulkUpdateRequest(BaseModel):
    """Bulk update request for multiple documents.

    Phase 2.2: Ermöglicht Massenaktualisierungen.
    """
    filter: DocumentFilterForBulkUpdate = Field(..., description="Filter für betroffene Dokumente")
    updates: DocumentPartialUpdateRequest = Field(..., description="Anzuwendende Änderungen")
    dry_run: bool = Field(False, description="Nur simulieren, nicht ausführen")


class BulkUpdateResult(BaseModel):
    """Result of bulk update operation."""
    total_matched: int = Field(description="Anzahl gefundener Dokumente")
    total_updated: int = Field(description="Anzahl aktualisierter Dokumente")
    failed: int = Field(default=0, description="Anzahl fehlgeschlagener Updates")
    dry_run: bool = Field(description="War dies ein Testlauf?")
    errors: List[str] = Field(default_factory=list, description="Fehlermeldungen")


# ============================================================================
# SOFT-DELETE SCHEMAS (GDPR Phase 2.3)
# ============================================================================

class SoftDeleteRequest(BaseModel):
    """Request for soft-deleting a document (GDPR-compliant).

    Phase 2.3: Soft-Delete ermöglicht Wiederherstellung und GDPR-Compliance.
    """
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Grund für die Löschung (optional)"
    )
    confirm: bool = Field(
        ...,
        description="Bestätigung erforderlich (muss true sein)"
    )

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Löschung muss mit confirm=true bestätigt werden")
        return v


class SoftDeleteResponse(BaseModel):
    """Response after soft-deleting a document."""
    document_id: uuid.UUID
    deleted_at: datetime
    deleted_by_id: uuid.UUID
    can_restore_until: datetime = Field(
        description="Zeitpunkt bis zu dem Wiederherstellung möglich ist (30 Tage)"
    )
    message: str = "Dokument wurde gelöscht und kann innerhalb von 30 Tagen wiederhergestellt werden"


class RestoreDocumentResponse(BaseModel):
    """Response after restoring a soft-deleted document."""
    document_id: uuid.UUID
    restored_at: datetime
    message: str = "Dokument wurde erfolgreich wiederhergestellt"


class DeletedDocumentSummary(BaseModel):
    """Summary of a soft-deleted document."""
    id: uuid.UUID
    filename: str
    document_type: DocumentType
    deleted_at: datetime
    deleted_by_id: uuid.UUID
    days_until_permanent_deletion: int
    can_restore: bool = True


class DeletedDocumentsListResponse(BaseModel):
    """List of soft-deleted documents."""
    total: int
    documents: List[DeletedDocumentSummary]


class DocumentDetailResponse(BaseModel):
    """Detailed document response with all fields."""
    id: uuid.UUID
    filename: str
    original_filename: str
    file_path: Optional[str] = None
    file_size: int
    mime_type: Optional[str] = None
    checksum: Optional[str] = None

    # Classification
    document_type: DocumentType
    status: ProcessingStatus
    page_count: Optional[int] = None

    # OCR results
    extracted_text: Optional[str] = None
    ocr_backend_used: Optional[str] = None
    ocr_confidence: Optional[float] = None
    processing_duration_ms: Optional[int] = None

    # German validation
    has_umlauts: bool = False
    german_validation_score: Optional[float] = None
    detected_language: Optional[str] = None

    # Metadata
    document_metadata: Dict[str, Any] = {}
    tags: List[TagResponse] = []

    # Timestamps
    upload_date: Optional[datetime] = None
    processed_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # Version info
    current_version_number: int = 0
    total_versions: int = 0

    # Search/embedding info
    has_embedding: bool = False
    embedding_updated_at: Optional[datetime] = None
    embedding_model: Optional[str] = None

    # Ownership
    owner_id: uuid.UUID

    # URLs (generated)
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Quick Classification (schnelle Klassifizierung waehrend Upload)
    quick_classification_status: str = "pending"
    quick_classification_result: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentSummary(BaseModel):
    """Compact document summary for listings."""
    id: uuid.UUID
    filename: str
    document_type: DocumentType
    status: ProcessingStatus
    file_size: int
    page_count: Optional[int] = None
    ocr_confidence: Optional[float] = None
    created_at: datetime
    tags: List[str] = []
    has_embedding: bool = False

    # Quick Classification (schnelle Klassifizierung waehrend Upload)
    quick_classification_status: str = "pending"
    quick_classification_result: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentListRequest(BaseModel):
    """Request parameters for document listing."""
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    filters: Optional[SearchFilters] = None
    sort_by: SortField = Field(SortField.CREATED_AT)
    sort_order: SortOrder = Field(SortOrder.DESC)


class DocumentListResponseExtended(BaseModel):
    """Extended document list response with pagination info."""
    total: int
    page: int
    per_page: int
    total_pages: int
    has_next: bool
    has_prev: bool
    documents: List[DocumentSummary]
    filters_applied: Dict[str, Any] = {}


# ============================================================================
# ADMIN CONSOLE SCHEMAS
# ============================================================================

class UserTier(str, Enum):
    """User subscription tier."""
    FREE = "free"
    PREMIUM = "premium"
    ADMIN = "admin"


class UserRole(str, Enum):
    """User role options."""
    USER = "user"
    ADMIN = "admin"
    SUPERUSER = "superuser"


class UserStatus(str, Enum):
    """User account status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEACTIVATED = "deactivated"


# ----- User Admin Schemas -----

class UserAdminView(BaseModel):
    """Detailed user view for admin console."""
    id: uuid.UUID
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    tier: str = "free"
    daily_quota: int
    documents_processed_today: int
    rate_limit_hourly: Optional[int] = None
    rate_limit_daily: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    password_reset_required: bool = False
    deactivated_at: Optional[datetime] = None
    notes: Optional[str] = None

    # Computed fields
    role: str = "user"  # Computed from is_superuser
    status: str = "active"  # Computed from is_active + deactivated_at

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_computed(cls, user) -> "UserAdminView":
        """Create instance with computed fields."""
        role = "superuser" if user.is_superuser else ("admin" if user.tier == "admin" else "user")
        status = "deactivated" if user.deactivated_at else ("active" if user.is_active else "inactive")
        return cls(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            tier=user.tier or "free",
            daily_quota=user.daily_quota,
            documents_processed_today=user.documents_processed_today,
            rate_limit_hourly=user.rate_limit_hourly,
            rate_limit_daily=user.rate_limit_daily,
            created_at=user.created_at,
            updated_at=user.updated_at,
            last_login=user.last_login,
            last_activity_at=user.last_activity_at,
            password_reset_required=user.password_reset_required or False,
            deactivated_at=user.deactivated_at,
            notes=user.notes,
            role=role,
            status=status,
        )


class UserListFilters(BaseModel):
    """Filters for user listing."""
    role: Optional[UserRole] = None
    status: Optional[UserStatus] = None
    tier: Optional[UserTier] = None
    search: Optional[str] = Field(None, max_length=100, description="Suche nach E-Mail, Benutzername, Name")
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    last_login_from: Optional[datetime] = None
    last_login_to: Optional[datetime] = None


class UserListRequest(BaseModel):
    """Request for user listing with filters and pagination."""
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    filters: Optional[UserListFilters] = None
    sort_by: str = Field("created_at", pattern="^(created_at|email|username|last_login|tier)$")
    sort_order: SortOrder = Field(SortOrder.DESC)


class UserListResponse(BaseModel):
    """Paginated user list response."""
    users: List[UserAdminView]
    total: int
    page: int
    per_page: int
    total_pages: int


class UserAdminCreate(BaseModel):
    """Admin user creation schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    is_superuser: bool = False
    tier: UserTier = UserTier.FREE
    daily_quota: int = Field(100, ge=1)
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Benutzername darf nur Buchstaben, Zahlen, Unterstrich und Bindestrich enthalten")
        return v.lower()


class UserAdminUpdate(BaseModel):
    """Admin user update schema."""
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    tier: Optional[UserTier] = None
    daily_quota: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = Field(None, max_length=1000)


class UserRoleChange(BaseModel):
    """Schema for changing user role."""
    is_superuser: bool


class UserPasswordReset(BaseModel):
    """Response for password reset."""
    success: bool
    temporary_password: str
    message: str = "Passwort wurde zurückgesetzt"


class UserDeactivate(BaseModel):
    """Request for user deactivation."""
    reason: Optional[str] = Field(None, max_length=500)


class UserActivityItem(BaseModel):
    """Single user activity entry."""
    id: uuid.UUID
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    created_at: datetime
    details: Dict[str, Any] = {}

    model_config = ConfigDict(from_attributes=True)


class UserActivityResponse(BaseModel):
    """User activity history response."""
    user_id: uuid.UUID
    activities: List[UserActivityItem]
    total: int


# ----- Rate Limit Schemas -----

class RateLimitTierDefaults(BaseModel):
    """Default rate limits per tier."""
    tier: UserTier
    ocr_hourly: int
    ocr_daily: int
    batch_hourly: int
    api_per_minute: int


class RateLimitOverrideCreate(BaseModel):
    """Create rate limit override for a user."""
    ocr_hourly: Optional[int] = Field(None, ge=1)
    ocr_daily: Optional[int] = Field(None, ge=1)
    batch_hourly: Optional[int] = Field(None, ge=1)
    api_per_minute: Optional[int] = Field(None, ge=1)
    valid_until: Optional[datetime] = None
    reason: str = Field(..., min_length=1, max_length=500)


class RateLimitOverrideResponse(BaseModel):
    """Rate limit override response."""
    id: uuid.UUID
    user_id: uuid.UUID
    ocr_hourly: Optional[int] = None
    ocr_daily: Optional[int] = None
    batch_hourly: Optional[int] = None
    api_per_minute: Optional[int] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime
    reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RateLimitStatus(BaseModel):
    """Current rate limit status for a user."""
    user_id: uuid.UUID
    email: str
    tier: str
    effective_limits: Dict[str, int]
    current_usage: Dict[str, int]
    has_override: bool
    override_valid_until: Optional[datetime] = None
    override_reason: Optional[str] = None


class RateLimitUsageStats(BaseModel):
    """Aggregated rate limit usage statistics."""
    total_users: int
    users_at_limit: int
    users_with_overrides: int
    usage_by_tier: Dict[str, Dict[str, Any]]
    top_users_by_usage: List[Dict[str, Any]]


# ----- System Dashboard Schemas -----

class GPUStatusAdmin(BaseModel):
    """Extended GPU status for admin dashboard."""
    available: bool
    gpu_name: Optional[str] = None
    total_gb: float = 0
    free_gb: float = 0
    allocated_gb: float = 0
    utilization_percent: float = 0
    temperature_celsius: Optional[float] = None
    memory_usage_percent: float = 0
    current_allocations: List[str] = []
    recommendations: List[str] = []


class QueueStatus(BaseModel):
    """Job queue status."""
    pending_jobs: int
    processing_jobs: int
    completed_today: int
    failed_today: int
    cancelled_today: int
    avg_wait_time_seconds: float
    avg_processing_time_seconds: float
    queue_by_priority: Dict[int, int] = {}
    queue_by_backend: Dict[str, int] = {}


class BackendHealthStatus(BaseModel):
    """Health status for a single backend service."""
    name: str
    status: str  # healthy, unhealthy, unknown
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    last_check: datetime


class SystemHealthStatus(BaseModel):
    """Overall system health status."""
    postgresql: BackendHealthStatus
    redis: BackendHealthStatus
    minio: BackendHealthStatus
    celery: BackendHealthStatus
    overall: str  # healthy, degraded, unhealthy


class ProcessingStats(BaseModel):
    """Processing statistics for dashboard."""
    documents_processed_today: int
    documents_processed_hour: int
    success_rate: float  # 0-100
    avg_processing_time_ms: float
    total_documents: int
    total_pages_processed: int
    by_backend: Dict[str, Dict[str, Any]] = {}
    by_document_type: Dict[str, int] = {}
    hourly_trend: List[Dict[str, Any]] = []  # Last 24 hours


class SystemDashboard(BaseModel):
    """Complete system dashboard data."""
    gpu: GPUStatusAdmin
    queue: QueueStatus
    health: SystemHealthStatus
    processing: ProcessingStats
    timestamp: datetime


# ----- Job Admin Schemas -----

class JobAdminView(BaseModel):
    """Job details for admin view."""
    id: uuid.UUID
    document_id: uuid.UUID
    document_filename: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    job_type: str
    backend: Optional[str] = None
    status: ProcessingStatus
    priority: int
    retry_count: int
    max_retries: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    worker_id: Optional[str] = None
    result: Dict[str, Any] = {}

    # Computed fields
    duration_ms: Optional[int] = None
    wait_time_ms: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class JobListFilters(BaseModel):
    """Filters for job listing."""
    status: Optional[ProcessingStatus] = None
    backend: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    has_error: Optional[bool] = None


class JobListRequest(BaseModel):
    """Request for job listing with filters."""
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    filters: Optional[JobListFilters] = None
    sort_by: str = Field("created_at", pattern="^(created_at|started_at|priority|status)$")
    sort_order: SortOrder = Field(SortOrder.DESC)


class JobListResponse(BaseModel):
    """Paginated job list response."""
    jobs: List[JobAdminView]
    total: int
    page: int
    per_page: int
    total_pages: int
    status_summary: Dict[str, int] = {}


class JobCancelRequest(BaseModel):
    """Request to cancel a job."""
    reason: Optional[str] = Field(None, max_length=500)


class JobRetryRequest(BaseModel):
    """Request to retry a failed job."""
    priority: Optional[int] = Field(None, ge=1, le=10)
    backend: Optional[str] = None


class JobActionResponse(BaseModel):
    """Response for job actions (cancel, retry)."""
    success: bool
    job_id: uuid.UUID
    action: str
    message: str


class QueueClearRequest(BaseModel):
    """Request to clear pending jobs."""
    confirm: bool = Field(..., description="Bestaetigung erforderlich")
    status: ProcessingStatus = Field(ProcessingStatus.PENDING, description="Status der zu loeschenden Jobs")

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Aktion muss mit confirm=true bestaetigt werden")
        return v


class QueueClearResponse(BaseModel):
    """Response for queue clear action."""
    success: bool
    cleared_count: int
    message: str


# ----- Audit Log Schemas -----

class AuditLogView(BaseModel):
    """Audit log entry for admin view."""
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    user_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_method: Optional[str] = None
    request_path: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogFilters(BaseModel):
    """Filters for audit log listing."""
    user_id: Optional[uuid.UUID] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    ip_address: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    search: Optional[str] = Field(None, max_length=100)


class AuditLogListRequest(BaseModel):
    """Request for audit log listing."""
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=500)
    filters: Optional[AuditLogFilters] = None
    sort_order: SortOrder = Field(SortOrder.DESC)


class AuditLogListResponse(BaseModel):
    """Paginated audit log response."""
    logs: List[AuditLogView]
    total: int
    page: int
    per_page: int
    total_pages: int


class AuditLogExportRequest(BaseModel):
    """Request for exporting audit logs."""
    format: ExportFormat = Field(ExportFormat.CSV)
    filters: Optional[AuditLogFilters] = None
    max_records: int = Field(10000, ge=1, le=100000)


class AuditLogExportResponse(BaseModel):
    """Response for audit log export."""
    success: bool
    download_url: str
    record_count: int
    format: ExportFormat
    expires_at: datetime


class AuditSummary(BaseModel):
    """Aggregated audit activity summary."""
    total_actions: int
    unique_users: int
    actions_by_type: Dict[str, int]
    actions_by_user: List[Dict[str, Any]]
    recent_admin_actions: List[AuditLogView]
    period_start: datetime
    period_end: datetime


# ----- Admin Action Schemas -----

class AdminActionView(BaseModel):
    """Admin action log entry."""
    id: uuid.UUID
    admin_id: Optional[uuid.UUID] = None
    admin_email: Optional[str] = None
    target_user_id: Optional[uuid.UUID] = None
    target_user_email: Optional[str] = None
    action: str
    action_details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminActionListResponse(BaseModel):
    """List of admin actions."""
    actions: List[AdminActionView]
    total: int
    page: int
    per_page: int


# ============================================================================
# GDPR DELETION SCHEMAS (Art. 17 DSGVO)
# ============================================================================

class DeletionRequestCreate(BaseModel):
    """Anfrage zur Kontolöschung (Art. 17 DSGVO)."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Grund für Löschung (optional)"
    )
    confirm_deletion: bool = Field(
        ...,
        description="Bestätigung der unwiderruflichen Löschung"
    )

    @field_validator("confirm_deletion")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Löschung muss explizit bestätigt werden (confirm_deletion=true)")
        return v


class DeletionCancelRequest(BaseModel):
    """Abbruch einer Löschanfrage."""
    reason: Optional[str] = Field(
        None,
        max_length=200,
        description="Grund für den Abbruch (optional)"
    )


class DeletionStatusResponse(BaseModel):
    """Status einer Löschanfrage."""
    deletion_requested: bool
    deletion_requested_at: Optional[datetime] = None
    deletion_scheduled_for: Optional[datetime] = None
    days_remaining: Optional[int] = None
    can_cancel: bool
    nachricht: str  # Deutsche Nachricht

    model_config = ConfigDict(from_attributes=True)


class DeletionExecutionStats(BaseModel):
    """Statistiken nach Löschausführung."""
    documents_deleted: int
    api_keys_deleted: int
    audit_logs_anonymized: int
    user_deleted: bool
    hard_delete: bool


class DeletionExecutionResponse(BaseModel):
    """Antwort nach Löschausführung (Admin)."""
    success: bool
    user_id: uuid.UUID
    stats: DeletionExecutionStats
    nachricht: str


# ============================================================================
# GDPR DATA EXPORT SCHEMAS (Art. 20 DSGVO)
# ============================================================================

class ExportRequestCreate(BaseModel):
    """Anfrage zum Datenexport (Art. 20 DSGVO)."""
    format: str = Field(
        default="json",
        pattern="^(json|csv)$",
        description="Export-Format: json oder csv"
    )


class ExportStatusResponse(BaseModel):
    """Status eines Datenexports."""
    export_id: uuid.UUID
    status: str
    format: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    download_count: int = 0
    error_message: Optional[str] = None
    nachricht: str  # Deutsche Nachricht

    model_config = ConfigDict(from_attributes=True)


class ExportListResponse(BaseModel):
    """Liste aller Datenexports eines Benutzers."""
    exports: List[ExportStatusResponse]
    total: int


class ExportDownloadResponse(BaseModel):
    """Download-URL für einen Export."""
    download_url: str
    expires_in_seconds: int
    nachricht: str


# ============================================================================
# SESSION MANAGEMENT SCHEMAS
# ============================================================================

class SessionInfo(BaseModel):
    """Informationen zu einer aktiven Session."""
    id: uuid.UUID
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    ip_address: str
    location: Optional[str] = None
    last_activity_at: datetime
    created_at: datetime
    expires_at: datetime
    is_current: bool

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """Liste aller aktiven Sessions."""
    sessions: List[SessionInfo]
    total: int
    current_session_id: Optional[uuid.UUID] = None


class SessionRevokeRequest(BaseModel):
    """Anfrage zum Widerruf einer Session."""
    session_id: uuid.UUID


class SessionRevokeAllRequest(BaseModel):
    """Anfrage zum Widerruf aller Sessions."""
    except_current: bool = Field(
        default=True,
        description="Aktuelle Session ausschließen"
    )


class SessionRevokeResponse(BaseModel):
    """Antwort nach Session-Widerruf."""
    success: bool
    revoked_count: int
    nachricht: str


class LoginResponseWithSession(BaseModel):
    """Login-Antwort mit Session-Informationen."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    session_id: uuid.UUID
    user: "UserResponse"
    nachricht: str = "Erfolgreich angemeldet"

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# EMAIL VERIFICATION SCHEMAS
# ============================================================================

class EmailVerificationRequest(BaseModel):
    """Anfrage zum erneuten Senden der Verifizierungs-Email."""
    pass  # Keine Parameter erforderlich, verwendet aktuelle User-Email


class EmailVerificationResponse(BaseModel):
    """Antwort auf Verifizierungs-Anfrage."""
    success: bool
    email: str
    nachricht: str


class EmailVerifyTokenRequest(BaseModel):
    """Anfrage zur Token-Verifizierung."""
    token: str = Field(..., min_length=32, description="Verifizierungs-Token aus der Email")


class EmailVerifyResponse(BaseModel):
    """Antwort nach erfolgreicher Verifizierung."""
    success: bool
    email_verified: bool
    nachricht: str


class EmailChangeRequest(BaseModel):
    """Anfrage zur Email-Änderung."""
    new_email: EmailStr = Field(..., description="Neue Email-Adresse")
    password: str = Field(..., min_length=1, description="Aktuelles Passwort zur Bestätigung")


class EmailChangeResponse(BaseModel):
    """Antwort auf Email-Änderungs-Anfrage."""
    success: bool
    new_email: str
    nachricht: str


class EmailVerificationStatusResponse(BaseModel):
    """Status der Email-Verifizierung."""
    email: str
    email_verified: bool
    email_verified_at: Optional[datetime] = None
    pending_verification: bool
    pending_email_change: bool


# ============================================================================
# Webhook Schemas
# ============================================================================

class WebhookEventType(str, Enum):
    """Verfügbare Webhook Event-Typen."""
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_PROCESSING = "document.processing"
    DOCUMENT_COMPLETED = "document.completed"
    DOCUMENT_FAILED = "document.failed"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    SYSTEM_HEALTH_FAILED = "system.health_check_failed"
    SYSTEM_QUOTA_EXCEEDED = "system.quota_exceeded"
    BATCH_COMPLETED = "batch.completed"


class WebhookSubscriptionCreate(BaseModel):
    """Webhook-Abonnement erstellen."""
    name: str = Field(..., min_length=1, max_length=100, description="Name des Webhooks")
    url: str = Field(..., min_length=10, max_length=500, description="Webhook-Ziel-URL (HTTPS empfohlen)")
    description: Optional[str] = Field(None, max_length=500, description="Beschreibung")
    event_types: List[str] = Field(..., min_length=1, description="Liste der Event-Typen")
    headers: Optional[Dict[str, str]] = Field(None, description="Custom HTTP Headers")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximale Wiederholungsversuche")
    retry_delay_seconds: int = Field(default=60, ge=10, le=3600, description="Verzögerung zwischen Versuchen")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL muss mit http:// oder https:// beginnen")
        return v

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: List[str]) -> List[str]:
        valid_types = {e.value for e in WebhookEventType}
        for event_type in v:
            if event_type not in valid_types:
                raise ValueError(f"Ungültiger Event-Typ: {event_type}. Gültige Typen: {valid_types}")
        return v


class WebhookSubscriptionUpdate(BaseModel):
    """Webhook-Abonnement aktualisieren."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    url: Optional[str] = Field(None, min_length=10, max_length=500)
    description: Optional[str] = Field(None, max_length=500)
    event_types: Optional[List[str]] = None
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    retry_delay_seconds: Optional[int] = Field(None, ge=10, le=3600)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL muss mit http:// oder https:// beginnen")
        return v


class WebhookSubscriptionResponse(BaseModel):
    """Webhook-Abonnement-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    description: Optional[str] = None
    event_types: List[str]
    headers: Optional[Dict[str, str]] = None
    is_active: bool
    is_verified: bool
    max_retries: int
    retry_delay_seconds: int
    total_deliveries: int
    successful_deliveries: int
    failed_deliveries: int
    last_delivery_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionWithSecret(WebhookSubscriptionResponse):
    """Webhook-Abonnement mit Secret (nur bei Erstellung)."""
    secret: str = Field(..., description="HMAC-Secret für Signaturverifizierung (nur einmalig angezeigt)")


class WebhookSecretRotateResponse(BaseModel):
    """Antwort auf Secret-Rotation."""
    id: uuid.UUID
    secret: str = Field(..., description="Neues HMAC-Secret")
    rotated_at: datetime


class WebhookDeliveryResponse(BaseModel):
    """Webhook-Zustellungsprotokoll."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: str
    event_type: str
    status: str
    attempt: int
    max_attempts: int
    response_status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    created_at: datetime
    delivered_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None


class WebhookDeliveryListResponse(BaseModel):
    """Liste der Webhook-Zustellungen."""
    subscription_id: uuid.UUID
    total: int
    deliveries: List[WebhookDeliveryResponse]


class WebhookTestRequest(BaseModel):
    """Test-Webhook senden."""
    event_type: str = Field(default="document.created", description="Event-Typ für Test")


class WebhookTestResponse(BaseModel):
    """Antwort auf Test-Webhook."""
    success: bool
    status_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    error: Optional[str] = None


class WebhookListResponse(BaseModel):
    """Liste aller Webhook-Abonnements."""
    total: int
    webhooks: List[WebhookSubscriptionResponse]


# ============================================================================
# Favorites Schemas
# ============================================================================

class FavoriteCreate(BaseModel):
    """Favorit erstellen."""
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    note: Optional[str] = Field(None, max_length=500, description="Optionale Notiz")
    priority: int = Field(default=0, ge=0, le=100, description="Priorität (höher = wichtiger)")


class FavoriteUpdate(BaseModel):
    """Favorit aktualisieren."""
    note: Optional[str] = Field(None, max_length=500)
    priority: Optional[int] = Field(None, ge=0, le=100)


class FavoriteResponse(BaseModel):
    """Favorit-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    note: Optional[str] = None
    priority: int
    created_at: datetime

    # Optional: Dokument-Details (wenn mitgeladen)
    document_filename: Optional[str] = None
    document_status: Optional[str] = None


class FavoriteWithDocumentResponse(FavoriteResponse):
    """Favorit mit vollständigen Dokument-Details."""
    document: Optional[Dict[str, Any]] = None


class FavoriteListResponse(BaseModel):
    """Liste der Favoriten."""
    total: int
    favorites: List[FavoriteResponse]


# ============================================================================
# Advanced Search Schemas (Facets & Suggestions)
# ============================================================================

class FacetValue(BaseModel):
    """Ein einzelner Facet-Wert mit Anzahl."""
    value: str
    count: int
    label: Optional[str] = None  # Optional: deutscher Label


class FacetGroup(BaseModel):
    """Gruppe von Facet-Werten für ein Feld."""
    field: str
    label: str  # Deutscher Name (z.B. "Dokumenttyp")
    values: List[FacetValue]
    total_distinct: int


class SearchFacetsResponse(BaseModel):
    """Facetten-Antwort für Suchseite."""
    facets: List[FacetGroup]
    total_documents: int


class SuggestItem(BaseModel):
    """Ein Vorschlag für die Autovervollständigung."""
    text: str
    type: str  # "document", "tag", "term"
    score: float = 1.0
    document_id: Optional[uuid.UUID] = None
    highlight: Optional[str] = None  # HTML mit <mark>-Tags


class SuggestResponse(BaseModel):
    """Autovervollständigungs-Antwort."""
    query: str
    suggestions: List[SuggestItem]
    total: int


class SearchWithFacetsRequest(BaseModel):
    """Suchanfrage mit Facetten-Anforderung."""
    query: str = Field(..., min_length=1, max_length=500)
    search_type: Optional[str] = Field("hybrid", description="fts, semantic, hybrid")
    filters: Optional[Dict[str, Any]] = None
    facet_fields: List[str] = Field(
        default=["document_type", "status", "tags", "ocr_backend_used"],
        description="Felder für Facetten"
    )
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


class SearchWithFacetsResponse(BaseModel):
    """Suchantwort mit Facetten."""
    query: str
    search_type: str
    results: List[Dict[str, Any]]  # SearchResultItem-ähnlich
    facets: List[FacetGroup]
    total: int
    page: int
    per_page: int
    total_pages: int


# =============================================================================
# API Key Schemas
# =============================================================================

class APIKeyPermission(str, Enum):
    """Verfügbare API-Key-Berechtigungen."""
    READ_DOCUMENTS = "read:documents"
    WRITE_DOCUMENTS = "write:documents"
    DELETE_DOCUMENTS = "delete:documents"
    OCR_PROCESS = "ocr:process"
    SEARCH = "search"
    ADMIN = "admin"


class APIKeyCreate(BaseModel):
    """Schema zum Erstellen eines API-Keys."""
    name: str = Field(..., min_length=1, max_length=100, description="Name des API-Keys")
    description: Optional[str] = Field(None, max_length=255, description="Beschreibung")
    permissions: List[APIKeyPermission] = Field(
        default=[APIKeyPermission.READ_DOCUMENTS, APIKeyPermission.SEARCH],
        description="Berechtigungen des API-Keys"
    )
    rate_limit: int = Field(default=1000, ge=1, le=100000, description="Rate Limit pro Stunde")
    expires_in_days: Optional[int] = Field(
        None, ge=1, le=365,
        description="Ablauf in Tagen (None = kein Ablauf)"
    )


class APIKeyResponse(BaseModel):
    """Schema für API-Key-Antwort (ohne Secret)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    permissions: List[str]
    rate_limit: int
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime]
    expires_at: Optional[datetime]
    key_prefix: Optional[str] = Field(None, description="Erste 8 Zeichen des Keys")


class APIKeyCreateResponse(BaseModel):
    """Schema für neu erstellten API-Key (einmalig mit Secret)."""
    id: uuid.UUID
    name: str
    api_key: str = Field(..., description="Vollständiger API-Key - NUR EINMAL ANGEZEIGT!")
    key_prefix: str = Field(..., description="Erste 8 Zeichen zur Identifikation")
    permissions: List[str]
    rate_limit: int
    expires_at: Optional[datetime]
    warnung: str = Field(
        default="WICHTIG: Speichern Sie diesen API-Key sicher! Er wird nur einmal angezeigt.",
        description="Sicherheitshinweis"
    )


class APIKeyUpdate(BaseModel):
    """Schema zum Aktualisieren eines API-Keys."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=255)
    permissions: Optional[List[APIKeyPermission]] = None
    rate_limit: Optional[int] = Field(None, ge=1, le=100000)
    is_active: Optional[bool] = None


class APIKeyListResponse(BaseModel):
    """Liste von API-Keys."""
    api_keys: List[APIKeyResponse]
    total: int


class APIKeyDeleteResponse(BaseModel):
    """Antwort nach Löschen eines API-Keys."""
    success: bool
    nachricht: str
    deleted_key_name: str


# ============================================================================
# BUSINESS ENTITY SCHEMAS (Kunden/Lieferanten)
# ============================================================================

class EntityType(str, Enum):
    """Geschaeftspartner-Typ."""
    CUSTOMER = "customer"      # Kunde
    SUPPLIER = "supplier"      # Lieferant
    BOTH = "both"             # Kann beides sein
    INTERNAL = "internal"      # Interne Entitaet


class BusinessEntityBase(BaseModel):
    """Base schema fuer Geschaeftspartner."""
    name: str = Field(..., min_length=1, max_length=255, description="Firmenname")
    entity_type: EntityType = Field(EntityType.SUPPLIER, description="Typ: customer, supplier, both, internal")
    display_name: Optional[str] = Field(None, max_length=255, description="Anzeigename")
    short_name: Optional[str] = Field(None, max_length=50, description="Kurzname")

    # Deutsche Geschaeftsnummern
    vat_id: Optional[str] = Field(None, max_length=20, pattern=r"^DE[0-9]{9}$", description="USt-IdNr (DE123456789)")
    tax_number: Optional[str] = Field(None, max_length=30, description="Steuernummer")
    trade_register: Optional[str] = Field(None, max_length=50, description="Handelsregisternummer (z.B. HRB 12345)")

    # Banking
    iban: Optional[str] = Field(None, max_length=34, description="IBAN")
    bic: Optional[str] = Field(None, max_length=11, description="BIC/SWIFT")
    bank_name: Optional[str] = Field(None, max_length=100, description="Bankname")

    # Kontaktdaten
    street: Optional[str] = Field(None, max_length=255, description="Strasse")
    street_number: Optional[str] = Field(None, max_length=20, description="Hausnummer")
    postal_code: Optional[str] = Field(None, max_length=10, description="PLZ")
    city: Optional[str] = Field(None, max_length=100, description="Stadt")
    country: str = Field("DE", max_length=2, description="Laendercode (ISO 3166-1 alpha-2)")
    phone: Optional[str] = Field(None, max_length=30, description="Telefon")
    fax: Optional[str] = Field(None, max_length=30, description="Fax")
    email: Optional[EmailStr] = Field(None, description="E-Mail")
    website: Optional[str] = Field(None, max_length=255, description="Website")

    notes: Optional[str] = Field(None, max_length=2000, description="Notizen")

    @field_validator("vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiere deutsche USt-IdNr."""
        if v is None:
            return v
        # Entferne Leerzeichen
        v = v.replace(" ", "").upper()
        if not v.startswith("DE") or len(v) != 11:
            raise ValueError("USt-IdNr muss das Format DE123456789 haben")
        return v

    @field_validator("iban")
    @classmethod
    def validate_iban(cls, v: Optional[str]) -> Optional[str]:
        """Validiere IBAN-Format."""
        if v is None:
            return v
        # Entferne Leerzeichen
        v = v.replace(" ", "").upper()
        if len(v) < 15 or len(v) > 34:
            raise ValueError("IBAN muss zwischen 15 und 34 Zeichen haben")
        return v


class BusinessEntityCreate(BusinessEntityBase):
    """Schema zum Erstellen eines Geschaeftspartners."""
    name_aliases: List[str] = Field(default_factory=list, max_length=20, description="Alternative Namen")
    email_domains: List[str] = Field(default_factory=list, max_length=10, description="E-Mail-Domains")


class BusinessEntityUpdate(BaseModel):
    """Schema zum Aktualisieren eines Geschaeftspartners."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    entity_type: Optional[EntityType] = None
    display_name: Optional[str] = Field(None, max_length=255)
    short_name: Optional[str] = Field(None, max_length=50)
    vat_id: Optional[str] = Field(None, max_length=20)
    tax_number: Optional[str] = Field(None, max_length=30)
    trade_register: Optional[str] = Field(None, max_length=50)
    iban: Optional[str] = Field(None, max_length=34)
    bic: Optional[str] = Field(None, max_length=11)
    bank_name: Optional[str] = Field(None, max_length=100)
    street: Optional[str] = Field(None, max_length=255)
    street_number: Optional[str] = Field(None, max_length=20)
    postal_code: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)
    phone: Optional[str] = Field(None, max_length=30)
    fax: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    website: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=2000)
    name_aliases: Optional[List[str]] = None
    email_domains: Optional[List[str]] = None
    is_active: Optional[bool] = None
    verified: Optional[bool] = None


class BusinessEntityResponse(BusinessEntityBase):
    """Antwort-Schema fuer Geschaeftspartner."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_aliases: List[str] = []
    email_domains: List[str] = []
    document_count: int = 0
    first_document_date: Optional[datetime] = None
    last_document_date: Optional[datetime] = None
    total_invoice_amount: float = 0.0
    currency: str = "EUR"
    is_active: bool = True
    verified: bool = False
    confidence_score: float = 0.0
    auto_detected: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    full_address: Optional[str] = None


class BusinessEntitySummary(BaseModel):
    """Kompakte Zusammenfassung eines Geschaeftspartners."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: EntityType
    vat_id: Optional[str] = None
    city: Optional[str] = None
    document_count: int = 0
    is_active: bool = True


class BusinessEntityListResponse(BaseModel):
    """Liste von Geschaeftspartnern."""
    total: int
    page: int
    per_page: int
    total_pages: int
    entities: List[BusinessEntitySummary]


class BusinessEntitySearchRequest(BaseModel):
    """Suchanfrage fuer Geschaeftspartner."""
    query: Optional[str] = Field(None, max_length=255, description="Suchbegriff (Name, USt-IdNr, IBAN)")
    entity_type: Optional[EntityType] = None
    is_active: Optional[bool] = None
    verified: Optional[bool] = None
    has_documents: Optional[bool] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class BusinessEntitySuggestion(BaseModel):
    """Vorschlag fuer automatisch erkannten Geschaeftspartner aus OCR."""
    name: str
    vat_id: Optional[str] = None
    iban: Optional[str] = None
    address: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1, description="Konfidenz der Erkennung (0-1)")
    matched_existing: Optional[uuid.UUID] = Field(None, description="ID eines passenden existierenden Geschaeftspartners")
    match_reason: Optional[str] = Field(None, description="Grund fuer die Uebereinstimmung")


# ============================================================================
# DOCUMENT GROUP SCHEMAS (Zusammengehoerige Dokumente)
# ============================================================================

class DocumentGroupType(str, Enum):
    """Dokumentgruppen-Typ."""
    STAPLED = "stapled"              # Physisch geheftet
    MULTI_PAGE = "multi_page"        # Mehrseitiger Scan
    TRANSACTION = "transaction"      # Transaktionsbezogen
    CORRESPONDENCE = "correspondence" # Briefwechsel
    PROJECT = "project"              # Projektbezogen
    MANUAL = "manual"                # Manuell erstellt


class DocumentGroupBase(BaseModel):
    """Base schema fuer Dokumentgruppen."""
    name: str = Field(..., min_length=1, max_length=255, description="Name der Gruppe")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    group_type: DocumentGroupType = Field(DocumentGroupType.STAPLED, description="Gruppentyp")
    reference_number: Optional[str] = Field(None, max_length=100, description="Referenznummer")


class DocumentGroupCreate(DocumentGroupBase):
    """Schema zum manuellen Erstellen einer Dokumentgruppe."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100, description="Dokument-IDs fuer die Gruppe")
    primary_document_id: Optional[uuid.UUID] = Field(None, description="ID des primaeren Dokuments")
    business_entity_id: Optional[uuid.UUID] = Field(None, description="Zugehoeriger Geschaeftspartner")


class DocumentGroupUpdate(BaseModel):
    """Schema zum Aktualisieren einer Dokumentgruppe."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    group_type: Optional[DocumentGroupType] = None
    reference_number: Optional[str] = Field(None, max_length=100)
    primary_document_id: Optional[uuid.UUID] = None
    business_entity_id: Optional[uuid.UUID] = None


class DocumentInGroup(BaseModel):
    """Dokument innerhalb einer Gruppe."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    page_number_in_group: Optional[int] = None
    is_group_primary: bool = False
    ocr_confidence: Optional[float] = None
    created_at: datetime


class DocumentGroupResponse(DocumentGroupBase):
    """Antwort-Schema fuer Dokumentgruppen."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    primary_document_id: Optional[uuid.UUID] = None
    detection_method: Optional[str] = None
    detection_confidence: float = 0.0
    total_pages: int = 1
    combined_text: Optional[str] = None
    business_entity_id: Optional[uuid.UUID] = None
    business_entity_name: Optional[str] = None
    document_date: Optional[datetime] = None
    user_confirmed: bool = False
    needs_review: bool = False
    documents: List[DocumentInGroup] = []
    created_at: datetime
    updated_at: Optional[datetime] = None


class DocumentGroupSummary(BaseModel):
    """Kompakte Zusammenfassung einer Dokumentgruppe."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    group_type: DocumentGroupType
    total_pages: int
    document_count: int
    detection_confidence: float
    user_confirmed: bool
    needs_review: bool
    created_at: datetime


class DocumentGroupListResponse(BaseModel):
    """Liste von Dokumentgruppen."""
    total: int
    page: int
    per_page: int
    total_pages: int
    groups: List[DocumentGroupSummary]


class DocumentGroupDetailResponse(DocumentGroupResponse):
    """Erweiterte Antwort mit allen Details einer Dokumentgruppe."""
    model_config = ConfigDict(from_attributes=True)

    documents: List[DocumentInGroup] = []
    owner_name: Optional[str] = None
    created_by_name: Optional[str] = None


class GroupDetectionRequest(BaseModel):
    """Anfrage zur automatischen Gruppenerkennung."""
    document_ids: Optional[List[uuid.UUID]] = Field(
        None,
        max_length=1000,
        description="Spezifische Dokument-IDs (None = alle unzugeordneten)"
    )
    min_confidence: float = Field(0.99, ge=0, le=1, description="Minimale Konfidenz fuer Auto-Gruppierung")
    detection_methods: List[str] = Field(
        default=["filename_sequence", "content_similarity"],
        description="Zu verwendende Erkennungsmethoden"
    )
    dry_run: bool = Field(True, description="Nur simulieren, nicht speichern")


class GroupDetectionResult(BaseModel):
    """Ergebnis einer einzelnen Gruppenerkennung."""
    documents: List[uuid.UUID]
    group_type: DocumentGroupType
    detection_method: str
    confidence: float
    signals: List[Dict[str, Any]] = []
    suggested_name: str
    primary_document_id: Optional[uuid.UUID] = None


class GroupDetectionResponse(BaseModel):
    """Antwort auf Gruppenerkennungs-Anfrage."""
    total_documents_analyzed: int
    groups_detected: int
    groups_auto_confirmed: int  # >= 0.99 confidence
    groups_need_review: int     # < 0.99 confidence
    detected_groups: List[GroupDetectionResult]
    dry_run: bool
    message: str


class GroupConfirmRequest(BaseModel):
    """Anfrage zur Bestaetigung einer Gruppe."""
    confirmed: bool = Field(True, description="Gruppe bestaetigen (True) oder ablehnen (False)")
    adjust_documents: Optional[List[uuid.UUID]] = Field(
        None,
        description="Optionale Liste der finalen Dokument-IDs (fuer Korrekturen)"
    )


class GroupSplitRequest(BaseModel):
    """Anfrage zum Aufteilen einer Gruppe."""
    split_after_document_id: uuid.UUID = Field(..., description="Gruppe nach diesem Dokument trennen")
    new_group_name: Optional[str] = Field(None, max_length=255, description="Name der neuen Gruppe")


class GroupMergeRequest(BaseModel):
    """Anfrage zum Zusammenfuehren von Gruppen."""
    target_group_id: uuid.UUID = Field(..., description="Zielgruppe (bleibt bestehen)")
    source_group_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=10, description="Quellgruppen (werden geloescht)")


# ============================================================================
# DOCUMENT RELATIONSHIP SCHEMAS (Beziehungen zwischen Dokumenten)
# ============================================================================

class RelationshipType(str, Enum):
    """Beziehungstyp zwischen Dokumenten."""
    CHILD_OF = "child_of"           # Seite gehoert zu Dokument
    REFERENCES = "references"        # Verweist auf
    REPLIES_TO = "replies_to"        # Antwort auf
    SUPPLEMENTS = "supplements"      # Ergaenzung zu
    SUPERSEDES = "supersedes"        # Ersetzt
    DUPLICATE_OF = "duplicate_of"    # Duplikat von
    RELATED = "related"              # Allgemein verwandt


class DocumentRelationshipCreate(BaseModel):
    """Schema zum Erstellen einer Dokumentbeziehung."""
    source_document_id: uuid.UUID = Field(..., description="Quell-Dokument")
    target_document_id: uuid.UUID = Field(..., description="Ziel-Dokument")
    relationship_type: RelationshipType = Field(..., description="Beziehungstyp")
    sequence_number: Optional[int] = Field(None, ge=1, description="Reihenfolge (fuer CHILD_OF)")

    @model_validator(mode='after')
    def validate_different_documents(self) -> 'DocumentRelationshipCreate':
        """Validate that source and target are different."""
        if self.source_document_id == self.target_document_id:
            raise ValueError("Quell- und Zieldokument muessen unterschiedlich sein")
        return self


class DocumentRelationshipResponse(BaseModel):
    """Antwort-Schema fuer Dokumentbeziehungen."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    relationship_type: RelationshipType
    confidence: float
    sequence_number: Optional[int] = None
    detected_by: Optional[str] = None
    user_confirmed: bool
    user_rejected: bool
    created_at: datetime

    # Optional: Dokument-Details
    source_filename: Optional[str] = None
    target_filename: Optional[str] = None


class RelatedDocumentResponse(BaseModel):
    """Verwandtes Dokument mit Beziehungsdetails."""
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    filename: str
    document_type: Optional[str] = None
    relationship_type: RelationshipType
    relationship_direction: str  # "outgoing" oder "incoming"
    confidence: float
    sequence_number: Optional[int] = None
    created_at: datetime


class DocumentRelationshipsResponse(BaseModel):
    """Alle Beziehungen eines Dokuments."""
    document_id: uuid.UUID
    total_relationships: int
    outgoing: List[DocumentRelationshipResponse] = []
    incoming: List[DocumentRelationshipResponse] = []


class RelationshipDetectionRequest(BaseModel):
    """Anfrage zur automatischen Beziehungserkennung."""
    document_ids: Optional[List[uuid.UUID]] = Field(
        None,
        max_length=100,
        description="Spezifische Dokument-IDs (None = alle)"
    )
    relationship_types: List[RelationshipType] = Field(
        default=[RelationshipType.REFERENCES, RelationshipType.DUPLICATE_OF],
        description="Zu erkennende Beziehungstypen"
    )
    min_confidence: float = Field(0.99, ge=0, le=1)
    dry_run: bool = Field(True)


class RelationshipDetectionResult(BaseModel):
    """Einzelnes Erkennungsergebnis."""
    source_document_id: uuid.UUID
    target_document_id: uuid.UUID
    relationship_type: RelationshipType
    confidence: float
    detection_method: str
    evidence: Dict[str, Any] = {}


class RelationshipDetectionResponse(BaseModel):
    """Antwort auf Beziehungserkennungs-Anfrage."""
    total_documents_analyzed: int
    relationships_detected: int
    relationships_auto_confirmed: int
    relationships_need_review: int
    detected_relationships: List[RelationshipDetectionResult]
    dry_run: bool
    message: str


# ============================================================================
# VALIDATION QUEUE SCHEMAS (Pruef-Warteschlange fuer 99%+ Praezision)
# ============================================================================

class ValidationQueueItem(BaseModel):
    """Element in der Validierungs-Warteschlange."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_type: str  # "group" oder "relationship"
    item_id: uuid.UUID
    confidence: float
    detection_method: str
    detection_details: Dict[str, Any] = {}
    priority: int
    created_at: datetime

    # Details je nach Typ
    group_name: Optional[str] = None
    document_count: Optional[int] = None
    relationship_type: Optional[str] = None


class ValidationQueueListResponse(BaseModel):
    """Liste der Validierungs-Warteschlange."""
    total: int
    items: List[ValidationQueueItem]


class ValidationQueueResponse(BaseModel):
    """Antwort fuer Validierungswarteschlange mit Zusammenfassung."""
    total_pending: int
    groups_pending: int
    relationships_pending: int
    items: List[ValidationQueueItem] = []


class ValidationDecision(BaseModel):
    """Entscheidung fuer ein Element in der Warteschlange."""
    approved: bool = Field(..., description="True = bestaetigen, False = ablehnen")
    adjustment: Optional[Dict[str, Any]] = Field(None, description="Optionale Anpassungen")
    reason: Optional[str] = Field(None, max_length=500, description="Begruendung")


# ============================================================================
# ENTITY EXTRACTION SCHEMAS (Entitaetsextraktion aus OCR-Text)
# ============================================================================

class BusinessEntityDetailResponse(BusinessEntityResponse):
    """Erweiterte Antwort mit allen Details eines Geschaeftspartners."""
    model_config = ConfigDict(from_attributes=True)

    # Statistiken
    document_count: int = 0
    total_invoice_amount: float = 0.0
    last_document_date: Optional[datetime] = None

    # Aliase und Patterns
    name_aliases: List[str] = []
    address_patterns: List[str] = []

    # Audit
    created_by_id: Optional[uuid.UUID] = None
    verified_by_id: Optional[uuid.UUID] = None


class EntityExtractionRequest(BaseModel):
    """Anfrage zur Entitaetsextraktion aus Text."""
    text: str = Field(..., min_length=10, max_length=100000, description="OCR-Text zur Analyse")
    document_id: Optional[uuid.UUID] = Field(None, description="Optionale Dokument-ID fuer Verknuepfung")
    match_existing: bool = Field(True, description="Mit bestehenden Entitaeten abgleichen")
    min_confidence: float = Field(0.7, ge=0, le=1, description="Minimale Konfidenz fuer Extraktion")


class ExtractedEntity(BaseModel):
    """Extrahierte Entitaet aus OCR-Text."""
    name: Optional[str] = None
    vat_id: Optional[str] = None
    iban: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    street: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1)
    source_text: Optional[str] = Field(None, description="Originaltext-Ausschnitt")


class EntityExtractionResponse(BaseModel):
    """Antwort mit extrahierten Entitaeten."""
    entities: List[ExtractedEntity] = []
    matched_entities: List[BusinessEntitySummary] = []
    processing_time_ms: int
    document_id: Optional[uuid.UUID] = None


class EntityMatchResponse(BaseModel):
    """Antwort fuer Entitaetsmatching."""
    match_found: bool
    matched_entity: Optional[BusinessEntitySummary] = None
    match_confidence: float = 0.0
    match_reasons: List[str] = []
    suggested_updates: Dict[str, Any] = {}


class EntityMergeRequest(BaseModel):
    """Anfrage zum Zusammenfuehren von Entitaeten."""
    target_entity_id: uuid.UUID = Field(..., description="Ziel-Entitaet (bleibt bestehen)")
    source_entity_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Quell-Entitaeten (werden geloescht)"
    )
    merge_documents: bool = Field(True, description="Dokumente zur Ziel-Entitaet verschieben")
    merge_aliases: bool = Field(True, description="Aliase zusammenfuehren")


# ============================================================================
# OCR TRAINING & VALIDATION SCHEMAS
# Enterprise OCR Training System mit Self-Learning
# ============================================================================

class TrainingSampleStatus(str, Enum):
    """Status eines Training-Samples."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ANNOTATED = "annotated"
    VERIFIED = "verified"
    REJECTED = "rejected"


class CorrectionType(str, Enum):
    """Typ der OCR-Korrektur."""
    UMLAUT = "umlaut"
    DATE = "date"
    AMOUNT = "amount"
    NAME = "name"
    IBAN = "iban"
    VAT_ID = "vat_id"
    GENERAL = "general"


class TrainingBatchType(str, Enum):
    """Typ des Stichproben-Batches."""
    RANDOM = "random"
    STRATIFIED = "stratified"
    TARGETED = "targeted"
    LOW_CONFIDENCE = "low_confidence"


class TrainingBatchStatus(str, Enum):
    """Status des Stichproben-Batches."""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


# --- Training Sample Schemas ---

class TrainingSampleBase(BaseModel):
    """Basis-Schema fuer Training Sample."""
    language: str = Field("de", pattern="^(de|nl|pl|en)$")
    document_type: Optional[str] = Field(None, max_length=50)
    difficulty: str = Field("medium", pattern="^(easy|medium|hard)$")
    has_umlauts: bool = False
    has_fraktur: bool = False
    has_tables: bool = False
    has_handwriting: bool = False
    has_stamps: bool = False
    has_signatures: bool = False


class TrainingSampleCreate(TrainingSampleBase):
    """Training Sample erstellen."""
    file_path: str = Field(..., max_length=500)
    file_hash: str = Field(..., max_length=64)
    thumbnail_path: Optional[str] = Field(None, max_length=500)
    ground_truth_text: Optional[str] = None
    umlaut_words: List[str] = Field(default_factory=list)
    extracted_fields: Dict[str, Any] = Field(default_factory=dict)


class TrainingSampleUpdate(BaseModel):
    """Training Sample aktualisieren."""
    ground_truth_text: Optional[str] = None
    language: Optional[str] = Field(None, pattern="^(de|nl|pl|en)$")
    document_type: Optional[str] = Field(None, max_length=50)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    has_umlauts: Optional[bool] = None
    has_fraktur: Optional[bool] = None
    has_tables: Optional[bool] = None
    has_handwriting: Optional[bool] = None
    umlaut_words: Optional[List[str]] = None
    extracted_fields: Optional[Dict[str, Any]] = None
    annotation_notes: Optional[str] = Field(None, max_length=2000)
    status: Optional[TrainingSampleStatus] = None


class TrainingSampleResponse(TrainingSampleBase):
    """Training Sample Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    file_path: str
    file_hash: str
    thumbnail_path: Optional[str] = None
    ground_truth_text: Optional[str] = None
    umlaut_words: List[str] = []
    extracted_fields: Dict[str, Any] = {}
    status: TrainingSampleStatus
    annotated_by_id: Optional[uuid.UUID] = None
    verified_by_id: Optional[uuid.UUID] = None
    annotation_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    annotated_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None


class TrainingSampleListResponse(BaseModel):
    """Liste von Training Samples."""
    total: int
    limit: int
    offset: int
    samples: List[TrainingSampleResponse]


# --- Benchmark Schemas ---

class BenchmarkCreate(BaseModel):
    """Benchmark erstellen."""
    training_sample_id: uuid.UUID
    backend_name: str = Field(..., pattern="^(deepseek|got_ocr|surya_gpu|surya_cpu)$")
    backend_version: Optional[str] = Field(None, max_length=50)


class BenchmarkResponse(BaseModel):
    """Benchmark Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    training_sample_id: uuid.UUID
    backend_name: str
    backend_version: Optional[str] = None
    raw_text: Optional[str] = None
    confidence_score: Optional[float] = None
    cer: Optional[float] = None
    wer: Optional[float] = None
    umlaut_accuracy: Optional[float] = None
    capitalization_accuracy: Optional[float] = None
    field_accuracies: Dict[str, float] = {}
    error_patterns: Dict[str, int] = {}
    insertions: int = 0
    deletions: int = 0
    substitutions: int = 0
    processing_time_ms: Optional[int] = None
    gpu_memory_mb: Optional[int] = None
    processed_at: datetime


class BenchmarkRunRequest(BaseModel):
    """Anfrage zum Starten eines Benchmark-Laufs."""
    sample_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    backends: List[str] = Field(
        default=["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"],
        description="Zu testende Backends"
    )
    force_rerun: bool = Field(False, description="Existierende Benchmarks ueberschreiben")


class BenchmarkRunResponse(BaseModel):
    """Antwort auf Benchmark-Lauf."""
    success: bool
    samples_processed: int
    samples_failed: int
    backends_used: List[str]
    total_time_ms: int


class BackendComparisonResponse(BaseModel):
    """Backend-Vergleich Antwort."""
    backends: Dict[str, Dict[str, Any]] = {}
    best_backend: Optional[str] = None
    sample_count: int = 0


# --- Correction Schemas ---

class CorrectionCreate(BaseModel):
    """Korrektur erstellen."""
    document_id: Optional[uuid.UUID] = None
    original_text: str = Field(..., min_length=1)
    corrected_text: str = Field(..., min_length=1)
    correction_type: CorrectionType = CorrectionType.GENERAL
    field_corrected: Optional[str] = Field(None, max_length=50)
    backend_used: str = Field(..., pattern="^(deepseek|got_ocr|surya_gpu|surya_cpu)$")
    confidence_before: Optional[float] = Field(None, ge=0, le=1)
    applies_to_training: bool = True


class CorrectionResponse(BaseModel):
    """Korrektur Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: Optional[uuid.UUID] = None
    original_text: str
    corrected_text: str
    correction_type: CorrectionType
    field_corrected: Optional[str] = None
    backend_used: str
    confidence_before: Optional[float] = None
    applies_to_training: bool
    learning_processed: bool
    learning_processed_at: Optional[datetime] = None
    corrector_id: Optional[uuid.UUID] = None
    created_at: datetime


class CorrectionListResponse(BaseModel):
    """Liste von Korrekturen."""
    total: int
    page: int
    per_page: int
    corrections: List[CorrectionResponse]


# --- Training Batch Schemas ---

class StratificationConfig(BaseModel):
    """Konfiguration fuer stratifizierte Stichproben."""
    by_document_type: bool = True
    by_language: bool = True
    by_difficulty: bool = False
    type_weights: Dict[str, float] = Field(default_factory=dict)
    language_weights: Dict[str, float] = Field(default_factory=dict)


class BatchCreate(BaseModel):
    """Training Batch erstellen."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    batch_type: TrainingBatchType = TrainingBatchType.STRATIFIED
    target_size: int = Field(100, ge=10, le=1000)
    stratification_config: Optional[StratificationConfig] = None


class BatchResponse(BaseModel):
    """Training Batch Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    batch_type: TrainingBatchType
    stratification_config: Optional[Dict[str, Any]] = None
    target_size: int
    actual_size: int
    status: TrainingBatchStatus
    items_pending: int
    items_completed: int
    progress_percent: float = 0.0
    created_by_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class BatchItemResponse(BaseModel):
    """Batch Item Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID
    training_sample_id: uuid.UUID
    sequence_number: int
    assigned_to_id: Optional[uuid.UUID] = None
    status: str
    validation_notes: Optional[str] = None
    validation_time_seconds: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Eingebettet Sample-Info
    sample: Optional[TrainingSampleResponse] = None


class BatchDetailResponse(BatchResponse):
    """Batch mit allen Items."""
    items: List[BatchItemResponse] = []


class BatchListResponse(BaseModel):
    """Liste von Batches."""
    total: int
    batches: List[BatchResponse]


class BatchItemUpdate(BaseModel):
    """Batch Item aktualisieren."""
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed|skipped)$")
    validation_notes: Optional[str] = Field(None, max_length=2000)
    validation_time_seconds: Optional[int] = Field(None, ge=0)


# --- Statistics Schemas ---

class BackendStats(BaseModel):
    """Statistiken fuer ein Backend."""
    backend_name: str
    samples_processed: int
    avg_cer: Optional[float] = None
    avg_wer: Optional[float] = None
    avg_umlaut_accuracy: Optional[float] = None
    avg_processing_time_ms: Optional[float] = None
    p50_cer: Optional[float] = None
    p90_cer: Optional[float] = None
    p95_cer: Optional[float] = None


class FieldAccuracyStats(BaseModel):
    """Feld-Genauigkeitsstatistiken."""
    field_name: str
    avg_accuracy: float
    sample_count: int
    per_backend: Dict[str, float] = {}


class LanguageStats(BaseModel):
    """Sprach-Statistiken."""
    language: str
    sample_count: int
    avg_cer: float
    per_backend: Dict[str, float] = {}


class DocumentTypeStats(BaseModel):
    """Dokumenttyp-Statistiken."""
    document_type: str
    sample_count: int
    avg_cer: float
    per_backend: Dict[str, float] = {}


class TrainingOverviewStats(BaseModel):
    """Gesamtuebersicht Statistiken."""
    total_samples: int
    verified_samples: int
    pending_annotations: int
    active_batches: int
    recent_corrections_24h: int
    unprocessed_corrections: int
    samples_by_language: Dict[str, int] = {}
    samples_by_document_type: Dict[str, int] = {}


class TrainingStatsResponse(BaseModel):
    """Vollstaendige Training-Statistiken."""
    overview: TrainingOverviewStats
    backends: List[BackendStats]
    field_accuracies: List[FieldAccuracyStats]
    language_stats: List[LanguageStats]
    document_type_stats: List[DocumentTypeStats]


class DailyStatsResponse(BaseModel):
    """Taegliche Statistiken."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backend_name: str
    report_date: datetime
    samples_processed: int
    samples_verified: int
    avg_cer: Optional[float] = None
    avg_wer: Optional[float] = None
    avg_umlaut_accuracy: Optional[float] = None
    avg_processing_time_ms: Optional[float] = None
    p50_cer: Optional[float] = None
    p90_cer: Optional[float] = None
    p95_cer: Optional[float] = None
    corrections_count: int = 0


class TrendDataPoint(BaseModel):
    """Datenpunkt fuer Trend-Analyse."""
    date: datetime
    value: float


class TrendResponse(BaseModel):
    """Trend-Analyse Antwort."""
    metric: str
    backend: str
    data_points: List[TrendDataPoint]
    trend_direction: str = Field(description="up, down, stable")
    change_percent: float


# ============================================================================
# BULK OCR PROCESSING SCHEMAS
# Massenverarbeitung aller Trainings-Dokumente durch alle Backends
# ============================================================================

class BulkJobStatus(str, Enum):
    """Status eines Bulk Processing Jobs."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BulkProcessingJobCreate(BaseModel):
    """Bulk Processing Job erstellen."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    backends: List[str] = Field(
        default=["deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"],
        description="Zu verwendende OCR Backends"
    )
    configuration: Dict[str, Any] = Field(
        default_factory=dict,
        description="Backend-spezifische Konfiguration"
    )

    @field_validator("backends")
    @classmethod
    def validate_backends(cls, v: List[str]) -> List[str]:
        """Validiere Backend-Namen."""
        valid_backends = {"deepseek-janus-pro", "got-ocr-2.0", "surya-gpu", "surya"}
        for backend in v:
            if backend not in valid_backends:
                raise ValueError(f"Ungültiges Backend: {backend}. Erlaubt: {valid_backends}")
        return v


class BulkProcessingJobResponse(BaseModel):
    """Bulk Processing Job Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: BulkJobStatus
    backends: List[str]
    total_documents: int
    processed_documents: int
    failed_documents: int
    current_backend: Optional[str] = None
    current_backend_index: int = 0
    current_document_index: int = 0
    documents_per_backend: Dict[str, int] = {}
    configuration: Dict[str, Any] = {}
    error_log: List[Dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    last_checkpoint_at: Optional[datetime] = None
    created_by_id: Optional[uuid.UUID] = None


class BulkProcessingProgress(BaseModel):
    """Fortschritt eines Bulk Processing Jobs."""
    job_id: uuid.UUID
    status: BulkJobStatus
    total_documents: int
    processed_documents: int
    failed_documents: int
    progress_percent: float
    current_backend: Optional[str] = None
    current_backend_index: int
    total_backends: int
    documents_per_backend: Dict[str, int] = {}
    estimated_time_remaining_seconds: Optional[int] = None
    processing_rate_per_minute: Optional[float] = None
    started_at: Optional[datetime] = None
    elapsed_seconds: Optional[int] = None


class BulkProcessingJobListResponse(BaseModel):
    """Liste von Bulk Processing Jobs."""
    total: int
    jobs: List[BulkProcessingJobResponse]


class BulkProcessingStartResponse(BaseModel):
    """Antwort beim Starten eines Bulk Processing Jobs."""
    success: bool
    job_id: uuid.UUID
    message: str
    total_documents: int
    backends: List[str]
    estimated_time_hours: Optional[float] = None


class BulkProcessingPauseResponse(BaseModel):
    """Antwort beim Pausieren eines Bulk Processing Jobs."""
    success: bool
    job_id: uuid.UUID
    message: str
    processed_documents: int
    remaining_documents: int
    can_resume: bool


class BulkProcessingResumeResponse(BaseModel):
    """Antwort beim Fortsetzen eines Bulk Processing Jobs."""
    success: bool
    job_id: uuid.UUID
    message: str
    resume_from_backend: str
    resume_from_document: int


class BulkProcessingCancelResponse(BaseModel):
    """Antwort beim Abbrechen eines Bulk Processing Jobs."""
    success: bool
    job_id: uuid.UUID
    message: str
    documents_processed_before_cancel: int


# --- OCR Document Output Schemas ---

class OCRDocumentOutputResponse(BaseModel):
    """OCR Output pro Dokument pro Backend."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    training_sample_id: uuid.UUID
    bulk_job_id: Optional[uuid.UUID] = None
    backend_name: str
    backend_version: Optional[str] = None
    raw_text: Optional[str] = None
    structured_output: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    processing_time_ms: Optional[int] = None
    gpu_memory_mb: Optional[int] = None
    error_message: Optional[str] = None
    success: bool
    processed_at: datetime


class OCRDocumentOutputListResponse(BaseModel):
    """Liste von OCR Outputs fuer ein Sample."""
    sample_id: uuid.UUID
    outputs: List[OCRDocumentOutputResponse]
    total_backends: int
    successful_backends: int


# --- Quality Snapshot Schemas ---

class OCRQualitySnapshotResponse(BaseModel):
    """Quality Snapshot Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    backend_name: str
    snapshot_time: datetime
    sample_count: int
    avg_cer: Optional[float] = None
    avg_wer: Optional[float] = None
    avg_umlaut_accuracy: Optional[float] = None
    avg_processing_time_ms: Optional[float] = None
    p50_cer: Optional[float] = None
    p90_cer: Optional[float] = None
    p99_cer: Optional[float] = None
    correction_count: int = 0
    correction_types: Dict[str, int] = {}
    alert_triggered: bool = False
    alert_reason: Optional[str] = None
    created_at: datetime


class QualitySnapshotListResponse(BaseModel):
    """Liste von Quality Snapshots."""
    backend_name: str
    snapshots: List[OCRQualitySnapshotResponse]
    total: int


# --- Model Deployment Schemas ---

class ModelDeploymentCreate(BaseModel):
    """Model Deployment erstellen."""
    model_name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    model_type: str = Field(..., pattern="^(base|finetuned|lora)$")
    checkpoint_path: Optional[str] = Field(None, max_length=500)
    training_job_id: Optional[uuid.UUID] = None
    traffic_percentage: float = Field(0.0, ge=0.0, le=100.0)


class ModelDeploymentResponse(BaseModel):
    """Model Deployment Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    model_name: str
    version: str
    model_type: str
    is_active: bool
    is_default: bool
    traffic_percentage: float
    performance_metrics: Dict[str, Any] = {}
    checkpoint_path: Optional[str] = None
    training_job_id: Optional[uuid.UUID] = None
    previous_version: Optional[str] = None
    rollback_reason: Optional[str] = None
    deployed_at: Optional[datetime] = None
    deactivated_at: Optional[datetime] = None
    created_at: datetime
    deployed_by_id: Optional[uuid.UUID] = None


class ModelDeploymentListResponse(BaseModel):
    """Liste von Model Deployments."""
    model_name: str
    deployments: List[ModelDeploymentResponse]
    active_version: Optional[str] = None
    total: int


# =============================================================================
# Training Dataset Export Schemas
# =============================================================================

class TrainingExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    DEEPSEEK_JSONL = "deepseek_jsonl"
    SURYA_HF = "surya_hf"
    GENERIC_JSONL = "generic_jsonl"
    CSV = "csv"


class SplitStrategy(str, Enum):
    """Strategie für Train/Val/Test Split."""
    RANDOM = "random"
    STRATIFIED = "stratified"
    TEMPORAL = "temporal"


class ExportConfigRequest(BaseModel):
    """Konfiguration für Dataset-Export."""
    format: TrainingExportFormat = Field(default=TrainingExportFormat.DEEPSEEK_JSONL, description="Export-Format")
    split_ratio: Tuple[float, float, float] = Field(
        default=(0.8, 0.1, 0.1),
        description="Train/Val/Test Split-Verhältnis"
    )
    split_strategy: SplitStrategy = Field(default=SplitStrategy.RANDOM, description="Split-Strategie")
    filter_verified_only: bool = Field(default=True, description="Nur verifizierte Samples")
    min_umlaut_accuracy: Optional[float] = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Minimale Umlaut-Genauigkeit"
    )
    min_cer: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Maximale CER (Character Error Rate)"
    )
    include_metadata: bool = Field(default=True, description="Metadata inkludieren")
    include_image_base64: bool = Field(default=False, description="Bilder als Base64")
    image_reference_type: str = Field(
        default="path",
        pattern="^(path|base64|url)$",
        description="Typ der Bild-Referenz"
    )
    seed: int = Field(default=42, ge=0, description="Random Seed für Reproduzierbarkeit")

    @field_validator("split_ratio")
    @classmethod
    def validate_split_ratio(cls, v: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """Validiert dass Split-Ratio sich zu 1.0 summiert."""
        if not (0.99 <= sum(v) <= 1.01):
            raise ValueError("Split-Ratio muss sich zu 1.0 summieren")
        return v


class DeepSeekExportRequest(BaseModel):
    """Spezifische Konfiguration für DeepSeek-Export."""
    prompt_type: str = Field(
        default="full_ocr",
        pattern="^(full_ocr|structured|full_with_structure)$",
        description="Art des Prompts"
    )
    include_structured: bool = Field(default=True, description="Strukturierte Felder inkludieren")
    split_ratio: Tuple[float, float, float] = Field(default=(0.8, 0.1, 0.1))
    filter_verified_only: bool = Field(default=True)


class SuryaExportRequest(BaseModel):
    """Spezifische Konfiguration für Surya-Export."""
    create_arrow_files: bool = Field(default=True, description="HuggingFace Arrow-Dateien erstellen")
    split_ratio: Tuple[float, float, float] = Field(default=(0.8, 0.1, 0.1))
    filter_verified_only: bool = Field(default=True)


class ExportStatsResponse(BaseModel):
    """Statistiken eines Exports."""
    total_samples: int
    train_samples: int
    val_samples: int
    test_samples: int
    samples_with_umlauts: int
    avg_text_length: float
    document_types: Dict[str, int]
    export_time_seconds: float
    output_size_bytes: int


class ExportResultResponse(BaseModel):
    """Ergebnis eines Dataset-Exports."""
    success: bool
    export_id: str
    output_dir: str
    format: ExportFormat
    stats: ExportStatsResponse
    files_created: List[str]
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ExportListItemResponse(BaseModel):
    """Einzelner Export in der Liste."""
    export_id: str
    created_at: Optional[str] = None
    format: Optional[str] = None
    total_samples: int = 0
    output_dir: str


class TrainingExportListResponse(BaseModel):
    """Liste aller Training-Exports."""
    exports: List[ExportListItemResponse]
    total: int
