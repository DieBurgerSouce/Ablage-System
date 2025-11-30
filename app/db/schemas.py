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
    """Request for batch document deletion."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    confirm: bool = Field(..., description="Bestaetigung erforderlich (muss true sein)")

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Loeschung muss mit confirm=true bestaetigt werden")
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


class DocumentUpdateRequest(BaseModel):
    """Document update request."""
    document_type: Optional[DocumentType] = None
    language: Optional[str] = Field(None, pattern="^(de|en)$")
    tags: Optional[List[str]] = Field(None, max_length=20)
    metadata: Optional[Dict[str, str]] = None


class DocumentPartialUpdateRequest(BaseModel):
    """Partial document update request (PATCH).

    Phase 2.1: Ermoeglicht partielle Updates einzelner Felder.
    Nur angegebene Felder werden aktualisiert.
    """
    document_type: Optional[DocumentType] = Field(None, description="Dokumenttyp aendern")
    language: Optional[str] = Field(None, pattern="^(de|en)$", description="Sprache aendern")
    tags: Optional[List[str]] = Field(None, max_length=20, description="Tags ersetzen")
    add_tags: Optional[List[str]] = Field(None, max_length=20, description="Tags hinzufuegen")
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
    """Filter fuer Bulk-Update Operationen.

    Phase 2.2: Ermoeglicht Updates basierend auf Filterkriterien.
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

    Phase 2.2: Ermoeglicht Massenaktualisierungen.
    """
    filter: DocumentFilterForBulkUpdate = Field(..., description="Filter fuer betroffene Dokumente")
    updates: DocumentPartialUpdateRequest = Field(..., description="Anzuwendende Aenderungen")
    dry_run: bool = Field(False, description="Nur simulieren, nicht ausfuehren")


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

    Phase 2.3: Soft-Delete ermoeglicht Wiederherstellung und GDPR-Compliance.
    """
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Grund fuer die Loeschung (optional)"
    )
    confirm: bool = Field(
        ...,
        description="Bestaetigung erforderlich (muss true sein)"
    )

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Loeschung muss mit confirm=true bestaetigt werden")
        return v


class SoftDeleteResponse(BaseModel):
    """Response after soft-deleting a document."""
    document_id: uuid.UUID
    deleted_at: datetime
    deleted_by_id: uuid.UUID
    can_restore_until: datetime = Field(
        description="Zeitpunkt bis zu dem Wiederherstellung moeglich ist (30 Tage)"
    )
    message: str = "Dokument wurde geloescht und kann innerhalb von 30 Tagen wiederhergestellt werden"


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
    message: str = "Passwort wurde zurueckgesetzt"


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
