"""Pydantic schemas for API request/response validation."""

from datetime import datetime, timedelta
from datetime import date as date_type  # Avoid Pydantic field name collision
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum
from pathlib import Path
import os
import uuid
from uuid import UUID  # Import UUID type explicitly for type annotations

from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator, ConfigDict
from pydantic.alias_generators import to_camel


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
    DOCUMENT = "document"  # Generic document (default for uncategorized)
    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"          # Gutschrift
    DUNNING = "dunning"                  # Mahnung
    ORDER = "order"
    PURCHASE_ORDER = "purchase_order"    # Bestellung
    OFFER = "offer"  # Angebote
    CONTRACT = "contract"
    DELIVERY_NOTE = "delivery_note"
    RECEIPT = "receipt"
    FORM = "form"
    LETTER = "letter"
    REPORT = "report"
    OTHER = "other"
    UNKNOWN = "unknown"
    # Finanz-Dokumenttypen
    TAX_DOCUMENT = "tax_document"               # Steuerdokument (generisch)
    TAX_ASSESSMENT = "tax_assessment"           # Grundabgabenbescheid
    TAX_NOTICE = "tax_notice"                   # Steuerbescheid
    TAX_PREPAYMENT = "tax_prepayment"           # Vorauszahlung
    TAX_RETURN = "tax_return"                   # Steuererklärung
    TAX_CORRESPONDENCE = "tax_correspondence"   # Finanzamt-Korrespondenz
    PAYROLL = "payroll"                         # Lohn/Gehalt
    SOCIAL_SECURITY = "social_security"         # Sozialversicherung
    TRADE_ASSOCIATION = "trade_association"     # Berufsgenossenschaft
    BANK_STATEMENT = "bank_statement"           # Kontoauszug


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

# bcrypt verarbeitet maximal 72 Bytes; bcrypt >= 4.1 wirft bei laengeren
# Passwoertern ValueError (-> 500 ohne Validierung). KEIN Truncating
# (Entscheidung 2026-06-11): Ueberlange Passwoerter werden sauber mit 422
# abgelehnt. Achtung: Byte-Laenge != Zeichen-Laenge (Umlaute = 2 Bytes),
# deshalb reicht Pydantic max_length nicht aus.
BCRYPT_MAX_PASSWORD_BYTES = 72


def validate_password_byte_length(v: str) -> str:
    """Lehnt Passwoerter ab, die UTF-8-kodiert laenger als 72 Bytes sind."""
    if len(v.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            "Passwort darf maximal 72 Bytes (UTF-8) lang sein "
            "(Umlaute und Sonderzeichen zaehlen mehrfach)"
        )
    return v


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

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """bcrypt-Limit: max 72 Bytes (UTF-8), kein Truncating."""
        return validate_password_byte_length(v)


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

    @field_validator("new_password")
    @classmethod
    def validate_new_password_bytes(cls, v: str) -> str:
        """bcrypt-Limit: max 72 Bytes (UTF-8), kein Truncating."""
        return validate_password_byte_length(v)


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
    # F-04: bestehende/Reserved-TLD-Mails (z.B. *.local) nicht an EmailStr
    # scheitern lassen -> Response als plain str serialisieren.
    email: str
    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    preferred_ocr_backend: str
    daily_quota: int
    created_at: datetime
    last_login: Optional[datetime] = None
    role: str = "viewer"  # admin, editor, viewer - computed from is_superuser or RBAC
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
    priority: int = Field(5, ge=1, le=10, description="Verarbeitungspriorität (1-10)")


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


class TwoFactorRequiredResponse(BaseModel):
    """Response when 2FA verification is required."""
    requires_2fa: bool = True
    temp_token: str = Field(..., description="Temporarer Token fur 2FA-Verifizierung (5 Min gultig)")
    message: str = "Bitte geben Sie Ihren 2FA-Code ein."


class TwoFactorVerifyRequest(BaseModel):
    """Request to verify 2FA code during login."""
    temp_token: str = Field(..., description="Temporarer Token aus Login-Response")
    code: str = Field(..., min_length=6, max_length=12, description="6-stelliger TOTP-Code oder Backup-Code")


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
        return validate_password_byte_length(v)


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


class UploadCompleteRequest(BaseModel):
    """Request für finales Speichern nach OCR-Review.

    Wird vom Frontend gesendet, nachdem der User das OCR-Ergebnis
    im Review-Modal bestätigt hat.
    """
    temp_file_id: str = Field(..., description="ID der temporaeren Datei aus /ocr/process")
    final_filename: str = Field(..., min_length=1, max_length=255, description="Finaler Dateiname (nach Umbenennung)")
    document_type: str = Field(..., description="Dokumenttyp (z.B. 'invoice', 'offer')")

    # Metadaten (optional, aus Quick Classification)
    document_number: Optional[str] = Field(None, max_length=100, description="Belegnummer (z.B. 'RG-2024-001')")
    document_date: Optional[date_type] = Field(None, description="Dokumentdatum")
    total_amount: Optional[Decimal] = Field(None, description="Gesamtbetrag")
    currency: str = Field(default="EUR", max_length=3, description="Währung (ISO-Code)")
    due_date: Optional[date_type] = Field(None, description="Fälligkeitsdatum (bei Rechnungen)")

    # Entity-Linking (aus Quick Classification oder manuell)
    business_entity_id: Optional[uuid.UUID] = Field(None, description="Verknüpfte Business Entity (Kunde/Lieferant)")
    folder_id: str = Field(..., description="Zielordner ('folie' oder 'messer')")
    category: str = Field(..., description="Kategorie (z.B. 'rechnungen', 'angebote')")
    entity_type: str = Field(..., description="Entity-Typ ('customer' oder 'supplier')")

    # Zusätzliche Daten
    tags: List[str] = Field(default_factory=list, description="Tags für das Dokument")
    ocr_text: Optional[str] = Field(None, description="OCR-Text (falls Speicherung gewünscht)")
    ocr_confidence: Optional[float] = Field(None, ge=0, le=100, description="OCR-Konfidenz")

    @field_validator("final_filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate and sanitize filename against path traversal (CWE-22)."""
        # Reject null bytes (CWE-158)
        if "\x00" in v:
            raise ValueError("Ungültiger Dateiname - Nullbytes nicht erlaubt")

        # Prevent path traversal
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Ungültiger Dateiname - Pfad-Traversal nicht erlaubt")

        # Normalize to basename only (defense in depth)
        v = os.path.basename(v).strip()
        if not v:
            raise ValueError("Dateiname darf nicht leer sein")

        return v

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        """Validate entity type."""
        if v not in ("customer", "supplier"):
            raise ValueError("entity_type muss 'customer' oder 'supplier' sein")
        return v

    @field_validator("folder_id")
    @classmethod
    def validate_folder_id(cls, v: str) -> str:
        """Validate folder ID."""
        allowed_folders = ("folie", "messer")
        if v not in allowed_folders:
            raise ValueError(f"folder_id muss einer von {allowed_folders} sein")
        return v


class UploadCompleteResponse(BaseModel):
    """Response nach erfolgreichem Upload-Abschluss."""
    success: bool = True
    document_id: uuid.UUID
    filename: str
    storage_path: str
    file_size: int
    entity_linked: bool = False
    entity_name: Optional[str] = None
    message: str = "Dokument erfolgreich abgelegt"


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
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"
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


class MatchedEntityInfo(BaseModel):
    """Entity match information for entity-aware search."""
    entity_id: uuid.UUID
    entity_name: str
    entity_type: str = Field(..., description="customer or supplier")
    match_type: str = Field(..., description="How entity was matched: name, customer_number, iban, vat_id")
    match_confidence: float = Field(..., ge=0, le=1, description="Confidence of the entity match")
    customer_number: Optional[str] = None
    supplier_number: Optional[str] = None


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

    # Entity-aware search
    matched_entity: Optional[MatchedEntityInfo] = Field(
        None,
        description="Entity that was matched if search found this document via entity linking"
    )

    model_config = ConfigDict(from_attributes=True)


class SynonymExpansion(BaseModel):
    """Information about a synonym expansion."""
    original: str = Field(..., description="Original search term")
    synonyms: List[str] = Field(default_factory=list, description="Synonyms used for this term")


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
    synonym_expansions: List[SynonymExpansion] = Field(
        default_factory=list,
        description="List of synonyms used in query expansion"
    )
    did_you_mean: Optional[str] = Field(
        None,
        description="Korrekturvorschlag bei Tippfehlern (pg_trgm-basiert)"
    )


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
    confirm: bool = Field(..., description="Bestätigung erforderlich (muss true sein)")
    dry_run: bool = Field(
        default=False,
        description="Nur simulieren, nicht löschen. Zeigt welche Dokumente betroffen waeren."
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

    Ermöglicht das Abrufen mehrerer Dokumente in einem API-Call.
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

    # Quick Classification (schnelle Klassifizierung während Upload)
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

    # Quick Classification (schnelle Klassifizierung während Upload)
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
    items: List[UserAdminView]
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

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """bcrypt-Limit: max 72 Bytes (UTF-8), kein Truncating."""
        return validate_password_byte_length(v)

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
    confirm: bool = Field(..., description="Bestätigung erforderlich")
    status: ProcessingStatus = Field(ProcessingStatus.PENDING, description="Status der zu löschenden Jobs")

    @field_validator("confirm")
    @classmethod
    def must_confirm(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Aktion muss mit confirm=true bestätigt werden")
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
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogFilters(BaseModel):
    """Filters for audit log listing."""
    user_id: Optional[uuid.UUID] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[uuid.UUID] = None
    ip_address: Optional[str] = None
    success: Optional[bool] = None
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
    did_you_mean: Optional[str] = None


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
    """Geschäftspartner-Typ."""
    CUSTOMER = "customer"      # Kunde
    SUPPLIER = "supplier"      # Lieferant
    BOTH = "both"             # Kann beides sein
    INTERNAL = "internal"      # Interne Entität


class BusinessEntityBase(BaseModel):
    """Base schema für Geschäftspartner."""
    name: str = Field(..., min_length=1, max_length=255, description="Firmenname")
    entity_type: EntityType = Field(EntityType.SUPPLIER, description="Typ: customer, supplier, both, internal")
    display_name: Optional[str] = Field(None, max_length=255, description="Anzeigename")
    short_name: Optional[str] = Field(None, max_length=50, description="Kurzname")

    # Deutsche Geschäftsnummern
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
    country: str = Field("DE", max_length=2, description="Ländercode (ISO 3166-1 alpha-2)")
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
        # Behandle ungültige Altdaten ("nan", "none", etc.)
        if v.lower() in ("nan", "none", "null", ""):
            return None
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
        # Behandle ungültige Altdaten ("nan", "none", etc.)
        if v.lower() in ("nan", "none", "null", ""):
            return None
        # Entferne Leerzeichen
        v = v.replace(" ", "").upper()
        if len(v) < 15 or len(v) > 34:
            raise ValueError("IBAN muss zwischen 15 und 34 Zeichen haben")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_nan(cls, v: Optional[str]) -> Optional[str]:
        """Behandle ungültige Email-Werte aus Altdaten."""
        if v is None:
            return v
        if isinstance(v, str) and v.lower() in ("nan", "none", "null", ""):
            return None
        return v


class BusinessEntityCreate(BusinessEntityBase):
    """Schema zum Erstellen eines Geschäftspartners."""
    name_aliases: List[str] = Field(default_factory=list, max_length=20, description="Alternative Namen")
    email_domains: List[str] = Field(default_factory=list, max_length=10, description="E-Mail-Domains")


class BusinessEntityUpdate(BaseModel):
    """Schema zum Aktualisieren eines Geschäftspartners."""
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
    """Antwort-Schema für Geschäftspartner."""
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

    # Risk Scoring
    risk_score: Optional[float] = Field(None, ge=0, le=100, description="Risk score 0-100")
    risk_factors: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Risk factor breakdown")
    payment_behavior_score: Optional[float] = Field(None, ge=0, le=100, description="Payment behavior 0-100")
    risk_calculated_at: Optional[datetime] = None

    created_at: datetime
    updated_at: Optional[datetime] = None
    full_address: Optional[str] = None


class BusinessEntitySummary(BaseModel):
    """Kompakte Zusammenfassung eines Geschäftspartners."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    entity_type: EntityType
    vat_id: Optional[str] = None
    city: Optional[str] = None
    document_count: int = 0
    is_active: bool = True
    risk_score: Optional[float] = None  # Quick access for dashboard


class BusinessEntityListResponse(BaseModel):
    """Liste von Geschäftspartnern."""
    total: int
    page: int
    per_page: int
    total_pages: int
    entities: List[BusinessEntitySummary]


class BusinessEntitySearchRequest(BaseModel):
    """Suchanfrage für Geschäftspartner."""
    query: Optional[str] = Field(None, max_length=255, description="Suchbegriff (Name, USt-IdNr, IBAN)")
    entity_type: Optional[EntityType] = None
    is_active: Optional[bool] = None
    verified: Optional[bool] = None
    has_documents: Optional[bool] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)


class BusinessEntitySuggestion(BaseModel):
    """Vorschlag für automatisch erkannten Geschäftspartner aus OCR."""
    name: str
    vat_id: Optional[str] = None
    iban: Optional[str] = None
    address: Optional[str] = None
    confidence: float = Field(..., ge=0, le=1, description="Konfidenz der Erkennung (0-1)")
    matched_existing: Optional[uuid.UUID] = Field(None, description="ID eines passenden existierenden Geschäftspartners")
    match_reason: Optional[str] = Field(None, description="Grund für die Übereinstimmung")


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
    """Base schema für Dokumentgruppen."""
    name: str = Field(..., min_length=1, max_length=255, description="Name der Gruppe")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    group_type: DocumentGroupType = Field(DocumentGroupType.STAPLED, description="Gruppentyp")
    reference_number: Optional[str] = Field(None, max_length=100, description="Referenznummer")


class DocumentGroupCreate(DocumentGroupBase):
    """Schema zum manuellen Erstellen einer Dokumentgruppe."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100, description="Dokument-IDs für die Gruppe")
    primary_document_id: Optional[uuid.UUID] = Field(None, description="ID des primären Dokuments")
    business_entity_id: Optional[uuid.UUID] = Field(None, description="Zugehoeriger Geschäftspartner")


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
    """Antwort-Schema für Dokumentgruppen."""
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
    min_confidence: float = Field(0.99, ge=0, le=1, description="Minimale Konfidenz für Auto-Gruppierung")
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
    """Anfrage zur Bestätigung einer Gruppe."""
    confirmed: bool = Field(True, description="Gruppe bestätigen (True) oder ablehnen (False)")
    adjust_documents: Optional[List[uuid.UUID]] = Field(
        None,
        description="Optionale Liste der finalen Dokument-IDs (für Korrekturen)"
    )


class GroupSplitRequest(BaseModel):
    """Anfrage zum Aufteilen einer Gruppe."""
    split_after_document_id: uuid.UUID = Field(..., description="Gruppe nach diesem Dokument trennen")
    new_group_name: Optional[str] = Field(None, max_length=255, description="Name der neuen Gruppe")


class GroupMergeRequest(BaseModel):
    """Anfrage zum Zusammenführen von Gruppen."""
    target_group_id: uuid.UUID = Field(..., description="Zielgruppe (bleibt bestehen)")
    source_group_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=10, description="Quellgruppen (werden gelöscht)")


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
    sequence_number: Optional[int] = Field(None, ge=1, description="Reihenfolge (für CHILD_OF)")

    @model_validator(mode='after')
    def validate_different_documents(self) -> 'DocumentRelationshipCreate':
        """Validate that source and target are different."""
        if self.source_document_id == self.target_document_id:
            raise ValueError("Quell- und Zieldokument müssen unterschiedlich sein")
        return self


class DocumentRelationshipResponse(BaseModel):
    """Antwort-Schema für Dokumentbeziehungen."""
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
# VALIDATION QUEUE SCHEMAS (Prüf-Warteschlange für 99%+ Präzision)
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
    """Antwort für Validierungswarteschlange mit Zusammenfassung."""
    total_pending: int
    groups_pending: int
    relationships_pending: int
    items: List[ValidationQueueItem] = []


class ValidationDecision(BaseModel):
    """Entscheidung für ein Element in der Warteschlange."""
    approved: bool = Field(..., description="True = bestätigen, False = ablehnen")
    adjustment: Optional[Dict[str, Any]] = Field(None, description="Optionale Anpassungen")
    reason: Optional[str] = Field(None, max_length=500, description="Begruendung")


# ============================================================================
# ENTITY EXTRACTION SCHEMAS (Entitätsextraktion aus OCR-Text)
# ============================================================================

class BusinessEntityDetailResponse(BusinessEntityResponse):
    """Erweiterte Antwort mit allen Details eines Geschäftspartners."""
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

    # Dokumente (optional, wird im Endpoint gesetzt)
    recent_documents: Optional[List[Dict[str, Any]]] = None


class EntityExtractionRequest(BaseModel):
    """Anfrage zur Entitätsextraktion aus Text."""
    text: str = Field(..., min_length=10, max_length=100000, description="OCR-Text zur Analyse")
    document_id: Optional[uuid.UUID] = Field(None, description="Optionale Dokument-ID für Verknüpfung")
    match_existing: bool = Field(True, description="Mit bestehenden Entitäten abgleichen")
    min_confidence: float = Field(0.7, ge=0, le=1, description="Minimale Konfidenz für Extraktion")


class ExtractedEntity(BaseModel):
    """Extrahierte Entität aus OCR-Text."""
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
    """Antwort mit extrahierten Entitäten."""
    entities: List[ExtractedEntity] = []
    matched_entities: List[BusinessEntitySummary] = []
    processing_time_ms: int
    document_id: Optional[uuid.UUID] = None


class EntityMatchResponse(BaseModel):
    """Antwort für Entitätsmatching."""
    match_found: bool
    matched_entity: Optional[BusinessEntitySummary] = None
    match_confidence: float = 0.0
    match_reasons: List[str] = []
    suggested_updates: Dict[str, Any] = {}


class EntityMergeRequest(BaseModel):
    """Anfrage zum Zusammenführen von Entitäten."""
    target_entity_id: uuid.UUID = Field(..., description="Ziel-Entität (bleibt bestehen)")
    source_entity_ids: List[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Quell-Entitäten (werden gelöscht)"
    )
    merge_documents: bool = Field(True, description="Dokumente zur Ziel-Entität verschieben")
    merge_aliases: bool = Field(True, description="Aliase zusammenführen")


# ============================================================================
# INVOICE TRACKING SCHEMAS (Rechnungsverfolgung für Risk Scoring)
# ============================================================================

class InvoiceStatusEnum(str, Enum):
    """Rechnungsstatus für Zahlungsverfolgung."""
    OPEN = "open"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    DUNNING = "dunning"
    CANCELLED = "cancelled"
    PARTIAL = "partial"


class InvoiceTrackingBase(BaseModel):
    """Basis-Schema für Rechnungsverfolgung."""
    invoice_number: Optional[str] = Field(None, max_length=100, description="Rechnungsnummer")
    invoice_date: Optional[datetime] = Field(None, description="Rechnungsdatum")
    due_date: Optional[datetime] = Field(None, description="Fälligkeitsdatum")
    amount: float = Field(0.0, ge=0, description="Rechnungsbetrag")
    currency: str = Field("EUR", pattern="^[A-Z]{3}$", description="Währung (ISO 4217)")
    status: InvoiceStatusEnum = Field(InvoiceStatusEnum.OPEN, description="Zahlungsstatus")


class InvoiceTrackingCreate(InvoiceTrackingBase):
    """Schema zum Erstellen einer Rechnungsverfolgung."""
    document_id: uuid.UUID = Field(..., description="Verknüpftes Rechnungsdokument")


class InvoiceTrackingUpdate(BaseModel):
    """Schema zum Aktualisieren einer Rechnungsverfolgung."""
    invoice_number: Optional[str] = Field(None, max_length=100)
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    amount: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = Field(None, pattern="^[A-Z]{3}$")
    status: Optional[InvoiceStatusEnum] = None
    paid_at: Optional[datetime] = None
    paid_amount: Optional[float] = Field(None, ge=0)
    dunning_level: Optional[int] = Field(None, ge=0, le=4)


class InvoiceTrackingResponse(InvoiceTrackingBase):
    """Antwort-Schema für Rechnungsverfolgung."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    paid_at: Optional[datetime] = None
    paid_amount: Optional[float] = None
    dunning_level: int = 0
    last_dunning_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Computed properties
    is_overdue: bool = False
    days_overdue: int = 0


# ============================================================================
# RISK SCORING SCHEMAS (Entity Risiko-Bewertung)
# ============================================================================

class RiskFactorsResponse(BaseModel):
    """Detaillierte Aufschluesselung der Risiko-Faktoren."""
    model_config = ConfigDict(from_attributes=True)

    # Payment behavior metrics
    payment_delay_days: float = Field(0.0, description="Durchschnittliche Zahlungsverzögerung in Tagen")
    default_rate: float = Field(0.0, ge=0, le=1, description="Ausfallrate (0-1)")

    # Invoice metrics
    invoice_volume: float = Field(0.0, ge=0, description="Gesamtes Rechnungsvolumen")
    document_frequency: float = Field(0.0, ge=0, description="Dokumente pro Monat")
    relationship_months: float = Field(0.0, ge=0, description="Geschäftsbeziehung in Monaten")

    # Invoice counts
    total_invoices: int = Field(0, ge=0, description="Gesamtzahl Rechnungen")
    paid_invoices: int = Field(0, ge=0, description="Bezahlte Rechnungen")
    overdue_invoices: int = Field(0, ge=0, description="Überfällige Rechnungen")
    open_invoices: int = Field(0, ge=0, description="Offene Rechnungen")

    # Additional metrics
    avg_invoice_amount: float = Field(0.0, ge=0, description="Durchschnittlicher Rechnungsbetrag")
    max_dunning_level: int = Field(0, ge=0, le=4, description="Hoechste erreichte Mahnstufe")


class RiskLevelEnum(str, Enum):
    """Risiko-Einstufung basierend auf Score."""
    UNKNOWN = "unbekannt"   # Keine Daten
    LOW = "niedrig"         # 0-25
    MEDIUM = "mittel"       # 26-50
    HIGH = "hoch"           # 51-75
    CRITICAL = "kritisch"   # 76-100


class EntityRiskResponse(BaseModel):
    """Vollständige Risiko-Bewertung einer Entität."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: uuid.UUID = Field(..., description="ID der Entität")
    entity_name: str = Field(..., description="Name der Entität")

    # Risk scores
    risk_score: Optional[float] = Field(None, ge=0, le=100, description="Gesamt-Risiko-Score (0-100, 100=hoechstes Risiko)")
    payment_behavior_score: Optional[float] = Field(None, ge=0, le=100, description="Zahlungsverhalten-Score (0-100, 100=bestes Verhalten)")

    # Risk factors breakdown
    risk_factors: RiskFactorsResponse = Field(
        default_factory=RiskFactorsResponse,
        description="Detaillierte Risiko-Faktoren"
    )

    # Metadata
    calculated_at: Optional[datetime] = Field(None, description="Zeitpunkt der letzten Berechnung")
    risk_level: RiskLevelEnum = Field(RiskLevelEnum.UNKNOWN, description="Risiko-Einstufung")

    # Entity context
    entity_type: Optional[str] = Field(None, description="Typ: customer, supplier, both")
    total_invoice_amount: float = Field(0.0, ge=0, description="Gesamtes Rechnungsvolumen")
    document_count: int = Field(0, ge=0, description="Anzahl verknüpfter Dokumente")


class RiskScoreCalculationRequest(BaseModel):
    """Anfrage zur Berechnung des Risk Scores."""
    entity_id: uuid.UUID = Field(..., description="ID der Entität")
    force_recalculate: bool = Field(False, description="Neuberechnung erzwingen (auch wenn aktuell)")


class RiskScoreBatchRequest(BaseModel):
    """Anfrage zur Batch-Berechnung von Risk Scores."""
    entity_type: Optional[str] = Field(None, pattern="^(customer|supplier|both)$", description="Nur bestimmten Typ berechnen")
    limit: int = Field(1000, ge=1, le=10000, description="Maximale Anzahl zu bearbeitender Entitäten")
    recalculate_all: bool = Field(False, description="Alle neu berechnen (nicht nur veraltete)")


class RiskScoreBatchResponse(BaseModel):
    """Antwort der Batch-Berechnung."""
    total_processed: int = Field(..., ge=0, description="Anzahl verarbeiteter Entitäten")
    successful: int = Field(..., ge=0, description="Erfolgreich berechnet")
    failed: int = Field(..., ge=0, description="Fehlgeschlagen")
    skipped: int = Field(..., ge=0, description="Übersprungen (noch aktuell)")
    processing_time_ms: int = Field(..., ge=0, description="Verarbeitungszeit in Millisekunden")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Fehlerdetails")


class InvoiceStatusDistributionItem(BaseModel):
    """Verteilung eines Rechnungsstatus."""
    count: int = Field(..., ge=0, description="Anzahl Rechnungen")
    amount: float = Field(..., ge=0, description="Gesamtbetrag")


class InvoiceStatisticsResponse(BaseModel):
    """Antwort-Schema für Rechnungsstatistiken."""
    totalInvoices: int = Field(..., ge=0, description="Gesamtzahl Rechnungen")
    totalAmount: float = Field(..., ge=0, description="Gesamtbetrag aller Rechnungen")
    statusDistribution: Dict[str, InvoiceStatusDistributionItem] = Field(
        ..., description="Verteilung nach Status"
    )
    overdueInvoices: InvoiceStatusDistributionItem = Field(
        ..., description="Überfällige Rechnungen"
    )
    generatedAt: datetime = Field(..., description="Zeitpunkt der Generierung")


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
    """Basis-Schema für Training Sample."""
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
    page: int
    per_page: int
    samples: List[TrainingSampleResponse]


class VerifySampleRequest(BaseModel):
    """Request Body für Sample-Verifizierung.

    Wird verwendet um Training-Samples zu verifizieren oder zu korrigieren.
    """
    approved: bool = Field(..., description="Ob Ground-Truth akzeptiert wird")
    corrected_text: Optional[str] = Field(None, description="Korrigierter Text bei Ablehnung")
    correction_notes: Optional[str] = Field(None, max_length=1000, description="Notizen zur Korrektur")


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
    force_rerun: bool = Field(False, description="Existierende Benchmarks überschreiben")


class BenchmarkRunResponse(BaseModel):
    """Antwort auf Benchmark-Lauf."""
    task_id: Optional[str] = None  # Celery Task ID für WebSocket-Updates
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
    """Konfiguration für stratifizierte Stichproben."""
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
    """Statistiken für ein Backend."""
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
    """Gesamtübersicht Statistiken."""
    total_samples: int
    verified_samples: int
    pending_annotations: int
    active_batches: int
    recent_corrections_24h: int
    unprocessed_corrections: int
    samples_by_language: Dict[str, int] = {}
    samples_by_document_type: Dict[str, int] = {}


class TrainingStatsResponse(BaseModel):
    """Vollständige Training-Statistiken."""
    overview: TrainingOverviewStats
    backends: List[BackendStats]
    field_accuracies: List[FieldAccuracyStats]
    language_stats: List[LanguageStats]
    document_type_stats: List[DocumentTypeStats]


class DailyStatsResponse(BaseModel):
    """Tägliche Statistiken."""
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
    """Datenpunkt für Trend-Analyse."""
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
    """Liste von OCR Outputs für ein Sample."""
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


# ============================================================================
# ABLAGE (DOCUMENT CATEGORY) SCHEMAS
# ============================================================================

class DocumentPaymentStatus(str, Enum):
    """Zahlungsstatus für Dokumente (Rechnungen, Bestellungen).

    Unterscheidet sich von banking.PaymentStatus (Zahlungsauftraege).
    """
    OFFEN = "offen"  # Noch nicht bezahlt
    BEZAHLT = "bezahlt"  # Vollständig bezahlt
    UEBERFAELLIG = "überfällig"  # Fälligkeitsdatum überschritten
    TEILBEZAHLT = "teilbezahlt"  # Teilweise bezahlt


class FinanceDocumentCategory(str, Enum):
    """Finanz-Dokument-Kategorien (18 Kategorien in 4 Paketen)."""
    # Steuern-Paket
    GRUNDABGABENBESCHEID = "grundabgabenbescheid"
    STEUERBESCHEIDE = "steuerbescheide"
    VORAUSZAHLUNGEN = "vorauszahlungen"
    STEUERERKLAERUNGEN = "steuererklärungen"
    FINANZAMT_KORRESPONDENZ = "finanzamt_korrespondenz"
    # Personal-Paket
    LOHN_GEHALT = "lohn_gehalt"
    SOZIALVERSICHERUNG = "sozialversicherung"
    BERUFSGENOSSENSCHAFT = "berufsgenossenschaft"
    ARBEITSVERTRAEGE = "arbeitsverträge"
    # Versicherungs-Paket
    BETRIEBSHAFTPFLICHT = "betriebshaftpflicht"
    SACHVERSICHERUNGEN = "sachversicherungen"
    KFZ_VERSICHERUNG = "kfz_versicherung"
    RECHTSSCHUTZ = "rechtsschutz"
    # Bank-Paket
    KONTOAUSZUEGE = "kontoauszuege"
    KREDITVERTRAEGE = "kreditverträge"
    BUERGSCHAFTEN = "buergschaften"
    DARLEHEN = "darlehen"


class TaxType(str, Enum):
    """Steuerart für Finanz-Dokumente."""
    EINKOMMENSTEUER = "einkommensteuer"
    KOERPERSCHAFTSTEUER = "koerperschaftsteuer"
    GEWERBESTEUER = "gewerbesteuer"
    UMSATZSTEUER = "umsatzsteuer"
    LOHNSTEUER = "lohnsteuer"
    GRUNDSTEUER = "grundsteuer"
    SONSTIGE = "sonstige"


class EntityType(str, Enum):
    """Entitätstyp für Ablage-Navigation."""
    CUSTOMER = "customer"  # Kunde
    SUPPLIER = "supplier"  # Lieferant
    FINANCE = "finance"    # Finanzen (Jahr-basiert)


class CategoryDocumentFilter(BaseModel):
    """Filter für Kategorie-Dokumentenliste.

    Ermöglicht umfangreiche Filterung nach:
    - Geschäftspartner (Kunde/Lieferant)
    - Ordner (z.B. Jahr oder Projekt)
    - Kategorie (Rechnungen, Angebote, etc.)
    - Zeitraum, Betrag, Status
    """
    # Pflicht: Kontext
    business_entity_id: uuid.UUID = Field(..., description="Kunden- oder Lieferanten-ID")
    folder_id: str = Field(..., description="Ordner-ID (z.B. '2024' oder 'projekt-xyz')")
    category: str = Field(..., description="Kategorie (rechnungen, angebote, verträge, etc.)")
    entity_type: EntityType = Field(EntityType.CUSTOMER, description="Kunde oder Lieferant")

    # Optional: Textsuche
    search: Optional[str] = Field(None, max_length=200, description="Suche in Dateiname, Dokumentnummer")

    # Optional: Datumsfilter
    date_from: Optional[datetime] = Field(None, description="Dokumentdatum ab")
    date_to: Optional[datetime] = Field(None, description="Dokumentdatum bis")

    # Optional: Betragsfilter
    amount_min: Optional[float] = Field(None, ge=0, description="Mindestbetrag")
    amount_max: Optional[float] = Field(None, ge=0, description="Höchstbetrag")

    # Optional: Statusfilter
    processing_status: Optional[List[ProcessingStatus]] = Field(
        None, description="Verarbeitungsstatus (pending, completed, etc.)"
    )
    payment_status: Optional[List[DocumentPaymentStatus]] = Field(
        None, description="Zahlungsstatus (nur für Rechnungen)"
    )

    # Optional: Tags
    tags: Optional[List[str]] = Field(None, max_length=10, description="Filter nach Tags")

    # Pagination
    page: int = Field(1, ge=1, description="Seitennummer (1-basiert)")
    page_size: int = Field(25, ge=1, le=100, description="Einträge pro Seite")

    # Sortierung
    sort_by: str = Field("document_date", description="Sortierfeld")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sortierrichtung")


class ExtractedDocumentData(BaseModel):
    """Extrahierte Daten aus einem Dokument.

    Diese Struktur spiegelt die JSONB-Daten in extracted_data.
    """
    # Allgemein
    document_number: Optional[str] = Field(None, description="Dokumentnummer (Rechnungsnr, Bestellnr)")
    document_date: Optional[datetime] = Field(None, description="Dokumentdatum")

    # Finanzielle Daten
    total_amount: Optional[float] = Field(None, description="Gesamtbetrag")
    net_amount: Optional[float] = Field(None, description="Nettobetrag")
    vat_amount: Optional[float] = Field(None, description="MwSt-Betrag")
    currency: str = Field("EUR", description="Währung")

    # Fälligkeit
    due_date: Optional[datetime] = Field(None, description="Fälligkeitsdatum")

    # Zahlungsstatus (manuell oder automatisch)
    payment_status: DocumentPaymentStatus = Field(
        DocumentPaymentStatus.OFFEN, description="Zahlungsstatus"
    )
    paid_amount: Optional[float] = Field(None, description="Bezahlter Betrag")
    payment_date: Optional[datetime] = Field(None, description="Zahlungsdatum")

    # Geschäftspartner
    partner_name: Optional[str] = Field(None, description="Name des Geschäftspartners")
    partner_address: Optional[str] = Field(None, description="Adresse")

    # Bankdaten
    iban: Optional[str] = Field(None, description="IBAN")
    bic: Optional[str] = Field(None, description="BIC")

    model_config = ConfigDict(extra="allow")  # Erlaube zusätzliche Felder


class CategoryDocumentResponse(BaseModel):
    """Einzelnes Dokument in der Kategorie-Ansicht.

    Optimiert für Tabellendarstellung mit allen relevanten Spalten.
    """
    id: uuid.UUID
    filename: str
    original_filename: str

    # Typ und Status
    document_type: DocumentType
    processing_status: ProcessingStatus

    # Metadaten
    file_size: int
    page_count: int
    mime_type: Optional[str] = None

    # Zeitstempel
    created_at: datetime
    updated_at: datetime
    document_date: Optional[datetime] = Field(None, description="Datum im Dokument")

    # OCR-Ergebnis
    ocr_confidence: Optional[float] = None

    # Extrahierte Daten (Subset für Tabelle)
    document_number: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "EUR"
    due_date: Optional[datetime] = None
    payment_status: DocumentPaymentStatus = DocumentPaymentStatus.OFFEN
    paid_amount: Optional[float] = None
    partner_name: Optional[str] = None

    # Tags
    tags: List[str] = Field(default_factory=list)

    # Vorschau-URLs
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None

    # Skonto-Daten (aus extracted_data.invoice)
    skonto_percent: Optional[float] = Field(None, ge=0, le=100, description="Skonto-Prozentsatz")
    skonto_days: Optional[int] = Field(None, ge=0, description="Skonto-Frist in Tagen")
    skonto_deadline: Optional[datetime] = Field(None, description="Skonto-Fälligkeitsdatum")
    skonto_amount: Optional[float] = Field(None, ge=0, description="Berechneter Skonto-Betrag")

    model_config = ConfigDict(from_attributes=True)


class CategoryDocumentListResponse(BaseModel):
    """Paginierte Liste von Kategorie-Dokumenten."""
    items: List[CategoryDocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    # Angewandte Filter (für Frontend-Synchronisation)
    filters_applied: Dict[str, Any] = Field(default_factory=dict)


class CategoryAggregations(BaseModel):
    """Aggregierte Statistiken für eine Kategorie.

    Ermöglicht Summen-Karten und Übersichtsgrafiken.
    """
    # Anzahlen
    total_documents: int = 0
    documents_by_status: Dict[str, int] = Field(default_factory=dict)
    documents_by_payment_status: Dict[str, int] = Field(default_factory=dict)

    # Betraege
    total_amount: float = 0.0
    total_paid: float = 0.0
    total_open: float = 0.0
    total_overdue: float = 0.0
    currency: str = "EUR"

    # Zeitraum-Info
    earliest_date: Optional[datetime] = None
    latest_date: Optional[datetime] = None

    # Überfällige Dokumente
    overdue_count: int = 0
    overdue_documents: List[uuid.UUID] = Field(default_factory=list, max_length=10)


# --- Bulk Operations for Ablage ---

class BulkDownloadZipRequest(BaseModel):
    """Request für ZIP-Download mehrerer Dokumente."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    filename: Optional[str] = Field(None, max_length=200, description="Optionaler Dateiname")


class BulkExportCsvRequest(BaseModel):
    """Request für CSV-Export von Dokument-Metadaten."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=500)
    columns: Optional[List[str]] = Field(
        None, description="Spezifische Spalten (None = alle)"
    )
    include_amounts: bool = Field(True, description="Betraege inkludieren")
    include_dates: bool = Field(True, description="Daten inkludieren")
    delimiter: str = Field(";", pattern="^[,;\\t]$", description="CSV-Trennzeichen")


class BulkMarkAsPaidRequest(BaseModel):
    """Request zum Markieren mehrerer Dokumente als bezahlt."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    payment_date: Optional[datetime] = Field(None, description="Zahlungsdatum (Standard: jetzt)")


class BulkMoveCategoryRequest(BaseModel):
    """Request zum Verschieben von Dokumenten in andere Kategorie."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    target_category: str = Field(..., min_length=1, max_length=100)


class BulkSetTagsRequest(BaseModel):
    """Request zum Setzen von Tags für mehrere Dokumente."""
    document_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    tags: List[str] = Field(..., min_length=1, max_length=20)
    mode: TagOperation = Field(TagOperation.ADD, description="add, remove, oder set")


class UpdatePaymentStatusRequest(BaseModel):
    """Request zum Aktualisieren des Zahlungsstatus eines Dokuments."""
    status: DocumentPaymentStatus
    paid_amount: Optional[float] = Field(None, ge=0, description="Bezahlter Betrag")
    payment_date: Optional[datetime] = Field(None, description="Zahlungsdatum")

    @model_validator(mode="after")
    def validate_paid_amount(self) -> "UpdatePaymentStatusRequest":
        """Validiere paid_amount bei teilbezahlt."""
        if self.status == DocumentPaymentStatus.TEILBEZAHLT and self.paid_amount is None:
            raise ValueError("Bei Teilzahlung muss paid_amount angegeben werden")
        return self


class UpdatePaymentStatusResponse(BaseModel):
    """Response nach Zahlungsstatus-Update."""
    document_id: uuid.UUID
    old_status: DocumentPaymentStatus
    new_status: DocumentPaymentStatus
    paid_amount: Optional[float] = None
    payment_date: Optional[datetime] = None
    message: str


class BulkOperationResultAblage(BaseModel):
    """Ergebnis einer Bulk-Operation in der Ablage."""
    success: bool
    operation: str
    success_count: int
    failed_count: int
    failed_ids: List[uuid.UUID] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    message: str  # Deutsche Nachricht


# ============================================================================
# FINANCE (FINANZEN) SCHEMAS
# ============================================================================

class FinanceYearResponse(BaseModel):
    """Response für ein einzelnes Finanz-Jahr."""
    id: str = Field(..., description="Jahr als String (z.B. '2024')")
    year: int = Field(..., ge=2000, le=2100)
    is_active: bool = Field(False, description="Aktuelles Jahr")
    last_document_date: Optional[datetime] = Field(None, description="Datum des letzten Dokuments")
    document_counts: Dict[str, int] = Field(
        default_factory=dict,
        description="Dokument-Anzahl pro Kategorie"
    )
    total_documents: int = Field(0, ge=0)
    total_nachzahlung: float = Field(0.0, ge=0, description="Summe Nachzahlungen in EUR")
    total_erstattung: float = Field(0.0, ge=0, description="Summe Erstattungen in EUR")
    pending_deadlines: int = Field(0, ge=0, description="Anzahl offener Fristen")


class FinanceYearListResponse(BaseModel):
    """Response für Liste aller Finanz-Jahre."""
    items: List[FinanceYearResponse]
    total: int = Field(0, ge=0)


class FinanceAggregationsResponse(BaseModel):
    """Aggregierte Statistiken für Finanzen (gesamt oder pro Jahr)."""
    total_documents: int = Field(0, ge=0)
    total_nachzahlung: float = Field(0.0, ge=0, description="Summe aller Nachzahlungen")
    total_erstattung: float = Field(0.0, ge=0, description="Summe aller Erstattungen")
    saldo: float = Field(0.0, description="Erstattung - Nachzahlung (positiv = Guthaben)")
    pending_deadlines: int = Field(0, ge=0, description="Offene Fristen")
    overdue_deadlines: int = Field(0, ge=0, description="Überfällige Fristen")
    documents_by_category: Dict[str, int] = Field(
        default_factory=dict,
        description="Dokumente pro Kategorie"
    )
    documents_by_package: Dict[str, int] = Field(
        default_factory=dict,
        description="Dokumente pro Paket (steuern, personal, versicherung, bank)"
    )


class FinanceCategoryFilter(BaseModel):
    """Filter für Finanz-Kategorie-Dokumentenliste."""
    year: int = Field(..., ge=2000, le=2100, description="Jahr")
    category: str = Field(..., description="Kategorie-Slug")

    # Optional: Textsuche
    search: Optional[str] = Field(None, max_length=200)

    # Optional: Datumsfilter
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None

    # Optional: Betragsfilter
    amount_min: Optional[float] = Field(None, ge=0)
    amount_max: Optional[float] = Field(None, ge=0)

    # Optional: Steuerart-Filter
    steuerart: Optional[TaxType] = None

    # Pagination
    page: int = Field(0, ge=0)
    page_size: int = Field(25, ge=1, le=100)

    # Sortierung
    sort_by: str = Field("document_date")
    sort_order: str = Field("desc", pattern="^(asc|desc)$")


class FinanceCategoryDocumentResponse(BaseModel):
    """Einzelnes Dokument in der Finanz-Kategorie-Ansicht.

    Erweitert CategoryDocumentResponse um Finanz-spezifische Felder.
    """
    id: uuid.UUID
    filename: str
    original_filename: str

    # Typ und Status
    document_type: DocumentType
    processing_status: ProcessingStatus

    # Metadaten
    file_size: int
    page_count: int
    mime_type: Optional[str] = None

    # Zeitstempel
    created_at: datetime
    updated_at: datetime
    document_date: Optional[datetime] = None

    # OCR-Ergebnis
    ocr_confidence: Optional[float] = None

    # Standard-Felder
    document_number: Optional[str] = None
    total_amount: Optional[float] = None
    currency: str = "EUR"

    # Finanz-spezifische Felder
    einspruchsfrist: Optional[datetime] = Field(None, description="Einspruchsfrist")
    aktenzeichen: Optional[str] = Field(None, description="Finanzamt-Aktenzeichen")
    steuernummer: Optional[str] = Field(None, description="Steuernummer")
    finanzamt: Optional[str] = Field(None, description="Name des Finanzamts")
    steuerart: Optional[TaxType] = Field(None, description="Art der Steuer")
    zeitraum: Optional[str] = Field(None, description="Steuerzeitraum (z.B. '2023', 'Q1/2024')")
    nachzahlung: Optional[float] = Field(None, ge=0, description="Nachzahlung in EUR")
    erstattung: Optional[float] = Field(None, ge=0, description="Erstattung in EUR")
    versicherungsnummer: Optional[str] = Field(None, description="Versicherungs-Policennummer")
    vertragsnummer: Optional[str] = Field(None, description="Vertragsnummer")

    # Tags
    tags: List[str] = Field(default_factory=list)

    # Vorschau-URLs
    thumbnail_url: Optional[str] = None
    preview_url: Optional[str] = None

    # Anomalie-Felder (Enterprise Feature)
    has_anomalies: bool = Field(False, description="Hat erkannte Anomalien")
    anomaly_count: int = Field(0, ge=0, description="Anzahl erkannter Anomalien")
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Risiko-Score 0-1")

    model_config = ConfigDict(from_attributes=True)


class FinanceCategoryDocumentListResponse(BaseModel):
    """Paginierte Liste von Finanz-Kategorie-Dokumenten."""
    items: List[FinanceCategoryDocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class FinanceCategoryAggregations(BaseModel):
    """Aggregationen für eine Finanz-Kategorie."""
    category: str
    year: int
    total_documents: int = 0
    total_nachzahlung: float = 0.0
    total_erstattung: float = 0.0
    pending_deadlines: int = 0
    overdue_deadlines: int = 0
    earliest_date: Optional[datetime] = None
    latest_date: Optional[datetime] = None


# =============================================================================
# FINANCE DOCUMENT CRUD SCHEMAS
# =============================================================================

class FinanceDocumentUpdateRequest(BaseModel):
    """Request für Aktualisierung von Finanz-Dokument-Feldern."""
    # Kategorie-Änderung
    category: Optional[str] = Field(None, description="Neue Finanz-Kategorie")

    # Finanz-spezifische Felder
    einspruchsfrist: Optional[datetime] = Field(None, description="Einspruchsfrist")
    aktenzeichen: Optional[str] = Field(None, description="Finanzamt-Aktenzeichen")
    steuernummer: Optional[str] = Field(None, description="Steuernummer")
    finanzamt: Optional[str] = Field(None, description="Name des Finanzamts")
    steuerart: Optional[TaxType] = Field(None, description="Art der Steuer")
    zeitraum: Optional[str] = Field(None, description="Steuerzeitraum")
    nachzahlung: Optional[float] = Field(None, ge=0, description="Nachzahlung in EUR")
    erstattung: Optional[float] = Field(None, ge=0, description="Erstattung in EUR")
    versicherungsnummer: Optional[str] = Field(None, description="Versicherungs-Policennummer")
    vertragsnummer: Optional[str] = Field(None, description="Vertragsnummer")

    # Standard-Felder
    document_date: Optional[datetime] = Field(None, description="Dokumentdatum")
    document_number: Optional[str] = Field(None, description="Dokumentnummer")
    total_amount: Optional[float] = Field(None, description="Gesamtbetrag")

    model_config = ConfigDict(extra="forbid")


class FinanceDocumentUploadResponse(BaseModel):
    """Response nach erfolgreichem Finance-Dokument-Upload."""
    id: uuid.UUID
    filename: str
    original_filename: str
    category: str
    year: int
    document_type: DocumentType
    processing_status: ProcessingStatus
    file_size: int
    created_at: datetime
    ocr_job_id: Optional[str] = Field(None, description="ID des OCR-Jobs falls gestartet")
    message: str = "Dokument erfolgreich hochgeladen"

    model_config = ConfigDict(from_attributes=True)


class FinanceDocumentDeleteResponse(BaseModel):
    """Response nach Löschung eines Finance-Dokuments."""
    id: uuid.UUID
    deleted: bool = True
    deleted_at: datetime
    message: str = "Dokument erfolgreich gelöscht"


# =============================================================================
# BULK OPERATION SCHEMAS
# =============================================================================

class FinanceBulkDeleteRequest(BaseModel):
    """Request für Bulk-Löschung von Finanz-Dokumenten."""
    document_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der zu löschenden Dokument-IDs (max 100)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_ids": ["550e8400-e29b-41d4-a716-446655440000"]
            }
        }
    )


class FinanceBulkDeleteResponse(BaseModel):
    """Response nach Bulk-Löschung."""
    deleted_count: int = Field(..., description="Anzahl gelöschter Dokumente")
    failed_count: int = Field(0, description="Anzahl fehlgeschlagener Löschungen")
    deleted_ids: list[uuid.UUID] = Field(default_factory=list, description="Gelöschte IDs")
    failed_ids: list[uuid.UUID] = Field(default_factory=list, description="Fehlgeschlagene IDs")
    errors: list[str] = Field(default_factory=list, description="Fehlermeldungen")
    message: str = "Bulk-Löschung abgeschlossen"


class FinanceBulkUpdateRequest(BaseModel):
    """Request für Bulk-Aktualisierung von Finanz-Dokumenten."""
    document_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Liste der zu aktualisierenden Dokument-IDs"
    )
    # Optionale Felder die auf alle Dokumente angewendet werden
    category: Optional[str] = Field(None, description="Neue Kategorie für alle")
    year: Optional[int] = Field(None, ge=2000, le=2100, description="Neues Jahr für alle")
    steuerart: Optional[str] = Field(None, description="Neue Steuerart")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                "category": "steuerbescheide",
                "year": 2024
            }
        }
    )


class FinanceBulkUpdateResponse(BaseModel):
    """Response nach Bulk-Aktualisierung."""
    updated_count: int = Field(..., description="Anzahl aktualisierter Dokumente")
    failed_count: int = Field(0, description="Anzahl fehlgeschlagener Updates")
    updated_ids: list[uuid.UUID] = Field(default_factory=list, description="Aktualisierte IDs")
    failed_ids: list[uuid.UUID] = Field(default_factory=list, description="Fehlgeschlagene IDs")
    errors: list[str] = Field(default_factory=list, description="Fehlermeldungen")
    message: str = "Bulk-Aktualisierung abgeschlossen"


class FinanceExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    JSON = "json"
    CSV = "csv"
    ZIP = "zip"


class FinanceExportRequest(BaseModel):
    """Request für Dokument-Export."""
    document_ids: Optional[list[uuid.UUID]] = Field(
        None,
        max_length=500,
        description="Spezifische Dokument-IDs (leer = alle)"
    )
    year: Optional[int] = Field(None, ge=2000, le=2100, description="Jahr-Filter")
    category: Optional[str] = Field(None, description="Kategorie-Filter")
    format: FinanceExportFormat = Field(
        FinanceExportFormat.ZIP,
        description="Export-Format (json, csv, zip)"
    )
    include_files: bool = Field(
        True,
        description="Original-Dateien in ZIP einschließen"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2024,
                "category": "steuerbescheide",
                "format": "zip",
                "include_files": True
            }
        }
    )


class FinanceExportResponse(BaseModel):
    """Response mit Export-Download-Informationen."""
    export_id: str = Field(..., description="Export-Job-ID")
    status: str = Field("pending", description="Export-Status")
    download_url: Optional[str] = Field(None, description="Download-URL (wenn fertig)")
    document_count: int = Field(0, description="Anzahl exportierter Dokumente")
    file_size_bytes: Optional[int] = Field(None, description="Dateigröße in Bytes")
    expires_at: Optional[datetime] = Field(None, description="URL-Ablaufzeit")
    message: str = "Export gestartet"


# =============================================================================
# DEADLINE SCHEMAS
# =============================================================================

class DeadlineType(str, Enum):
    """Frist-Typ für Finanz-Dokumente."""
    EINSPRUCHSFRIST = "einspruchsfrist"
    ZAHLUNGSFRIST = "zahlungsfrist"
    ABGABEFRIST = "abgabefrist"
    SONSTIGE = "sonstige"


class FinanceDeadlineItem(BaseModel):
    """Einzelne Frist mit Dokument-Referenz."""
    id: str = Field(..., description="Frist-ID")
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    document_name: str = Field(..., description="Dokument-Name")
    category: str = Field(..., description="Kategorie-ID")
    category_label: str = Field(..., description="Kategorie-Label")
    year: str = Field(..., description="Jahr")
    deadline: datetime = Field(..., description="Frist-Datum")
    deadline_type: DeadlineType = Field(..., description="Frist-Typ")
    aktenzeichen: Optional[str] = Field(None, description="Aktenzeichen")
    days_until: int = Field(..., description="Tage bis zur Frist (negativ = überfällig)")


class FinanceDeadlineListResponse(BaseModel):
    """Response mit Liste aller Fristen."""
    items: List[FinanceDeadlineItem] = Field(default_factory=list, description="Fristen")
    total: int = Field(0, description="Gesamtanzahl")
    overdue_count: int = Field(0, description="Anzahl überfälliger Fristen")
    urgent_count: int = Field(0, description="Anzahl dringender Fristen (7 Tage)")
    upcoming_count: int = Field(0, description="Anzahl anstehender Fristen (30 Tage)")


# =============================================================================
# FINANCE DOCUMENT HISTORY SCHEMAS
# =============================================================================


class FinanceHistoryAction(str, Enum):
    """Aktionstypen für Finanz-Dokument-History."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    RESTORED = "restored"
    CATEGORY_CHANGED = "category_changed"
    YEAR_CHANGED = "year_changed"
    OCR_COMPLETED = "ocr_completed"
    DEADLINE_SET = "deadline_set"
    DEADLINE_REMOVED = "deadline_removed"
    BULK_UPDATE = "bulk_update"


class FinanceDocumentHistoryItem(BaseModel):
    """Einzelner History-Eintrag für ein Finanz-Dokument."""
    id: uuid.UUID = Field(..., description="History-Eintrag-ID")
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    user_id: Optional[uuid.UUID] = Field(None, description="Benutzer-ID")
    user_email: Optional[str] = Field(None, description="Benutzer-Email")
    user_name: Optional[str] = Field(None, description="Benutzername")

    # Aktion
    action: FinanceHistoryAction = Field(..., description="Aktionstyp")
    description: Optional[str] = Field(None, description="Menschenlesbare Beschreibung")

    # Änderungsdetails
    old_values: Dict[str, Any] = Field(default_factory=dict, description="Vorherige Werte")
    new_values: Dict[str, Any] = Field(default_factory=dict, description="Neue Werte")
    changed_fields: List[str] = Field(default_factory=list, description="Geänderte Felder")

    # Kontext
    ip_address: Optional[str] = Field(None, description="IP-Adresse")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Zusätzliche Metadaten")

    # Zeitstempel
    created_at: datetime = Field(..., description="Zeitpunkt der Änderung")

    model_config = ConfigDict(from_attributes=True)


class FinanceDocumentHistoryResponse(BaseModel):
    """Response mit vollständiger History eines Finanz-Dokuments."""
    document_id: uuid.UUID = Field(..., description="Dokument-ID")
    document_name: str = Field(..., description="Dokumentname")
    items: List[FinanceDocumentHistoryItem] = Field(default_factory=list, description="History-Einträge")
    total: int = Field(0, description="Gesamtanzahl Einträge")


class FinanceDocumentHistoryCreate(BaseModel):
    """Schema zum Erstellen eines History-Eintrags (intern)."""
    document_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    action: FinanceHistoryAction
    old_values: Dict[str, Any] = Field(default_factory=dict)
    new_values: Dict[str, Any] = Field(default_factory=dict)
    changed_fields: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# KASSE-MODUL: ENUMS
# =============================================================================


class CashEntryType(str, Enum):
    """Typ der Kassenbuchung - GoBD-konform."""

    # Einnahmen
    INCOME = "income"
    DEPOSIT = "deposit"
    REFUND_RECEIVED = "refund_received"

    # Ausgaben
    EXPENSE = "expense"
    WITHDRAWAL = "withdrawal"
    ENTERTAINMENT = "entertainment"
    TRAVEL = "travel"
    OFFICE = "office"
    FUEL = "fuel"
    PARKING = "parking"
    POSTAGE = "postage"
    TIPS = "tips"
    GIFTS = "gifts"

    # Sonder
    DIFFERENCE_PLUS = "difference_plus"
    DIFFERENCE_MINUS = "difference_minus"
    CANCELLATION = "cancellation"
    OPENING = "opening"


class ExpenseReportStatus(str, Enum):
    """Status einer Spesenabrechnung - Workflow."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class ExpenseType(str, Enum):
    """Typ einer Spesenposition."""

    RECEIPT = "receipt"
    MILEAGE = "mileage"
    PER_DIEM = "per_diem"
    FLAT_RATE = "flat_rate"


class CompanyRole(str, Enum):
    """Rolle eines Users in einer Firma."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# =============================================================================
# KASSE-MODUL: COMPANY SCHEMAS
# =============================================================================


class CompanyBase(BaseModel):
    """Basis-Schema für Company."""

    name: str = Field(..., min_length=1, max_length=255, description="Firmenname")
    short_name: Optional[str] = Field(None, max_length=50, description="Kurzname")
    display_name: Optional[str] = Field(None, max_length=255, description="Anzeigename")

    # Rechtsform
    legal_form: Optional[str] = Field(None, max_length=50, description="Rechtsform (GmbH, UG, etc.)")
    commercial_register: Optional[str] = Field(None, max_length=100, description="Handelsregistereintrag")
    court: Optional[str] = Field(None, max_length=100, description="Registergericht")

    # Steuer
    vat_id: Optional[str] = Field(None, max_length=20, description="USt-ID (DE123456789)")
    tax_number: Optional[str] = Field(None, max_length=50, description="Steuernummer")

    # Adresse
    street: Optional[str] = Field(None, max_length=255, description="Strasse")
    street_number: Optional[str] = Field(None, max_length=20, description="Hausnummer")
    postal_code: Optional[str] = Field(None, max_length=10, description="PLZ")
    city: Optional[str] = Field(None, max_length=100, description="Stadt")
    country: str = Field("DE", max_length=2, description="Ländercode (ISO 3166-1 alpha-2)")

    # Kontakt
    email: Optional[EmailStr] = Field(None, description="E-Mail")
    phone: Optional[str] = Field(None, max_length=50, description="Telefon")
    website: Optional[str] = Field(None, max_length=255, description="Webseite")

    # Banking
    iban: Optional[str] = Field(None, max_length=34, description="IBAN")
    bic: Optional[str] = Field(None, max_length=11, description="BIC")
    bank_name: Optional[str] = Field(None, max_length=100, description="Bankname")

    # Einstellungen
    default_currency: str = Field("EUR", max_length=3, description="Standardwährung")
    fiscal_year_start: int = Field(1, ge=1, le=12, description="Beginn Geschäftsjahr (Monat)")
    kontenrahmen: str = Field("SKR03", description="Kontenrahmen (SKR03 oder SKR04)")

    @field_validator("vat_id")
    @classmethod
    def validate_vat_id(cls, v: Optional[str]) -> Optional[str]:
        """Validiert USt-ID Format."""
        if v is None:
            return v
        v = v.strip().upper()
        if v and not v.startswith("DE"):
            raise ValueError("USt-ID muss mit DE beginnen")
        if v and len(v) != 11:
            raise ValueError("Ungültige USt-ID Länge (DE + 9 Ziffern)")
        return v

    @field_validator("kontenrahmen")
    @classmethod
    def validate_kontenrahmen(cls, v: str) -> str:
        """Validiert Kontenrahmen."""
        if v not in ["SKR03", "SKR04"]:
            raise ValueError("Kontenrahmen muss SKR03 oder SKR04 sein")
        return v


class CompanyCreate(CompanyBase):
    """Schema zum Erstellen einer Company."""

    alternative_names: List[str] = Field(default_factory=list, description="Alternative Namen für OCR")


class CompanyUpdate(BaseModel):
    """Schema zum Aktualisieren einer Company."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    short_name: Optional[str] = Field(None, max_length=50)
    display_name: Optional[str] = Field(None, max_length=255)
    legal_form: Optional[str] = Field(None, max_length=50)
    commercial_register: Optional[str] = Field(None, max_length=100)
    court: Optional[str] = Field(None, max_length=100)
    vat_id: Optional[str] = Field(None, max_length=20)
    tax_number: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=255)
    street_number: Optional[str] = Field(None, max_length=20)
    postal_code: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    website: Optional[str] = Field(None, max_length=255)
    iban: Optional[str] = Field(None, max_length=34)
    bic: Optional[str] = Field(None, max_length=11)
    bank_name: Optional[str] = Field(None, max_length=100)
    alternative_names: Optional[List[str]] = None
    default_currency: Optional[str] = Field(None, max_length=3)
    fiscal_year_start: Optional[int] = Field(None, ge=1, le=12)
    kontenrahmen: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class CompanyResponse(CompanyBase):
    """Response-Schema für Company."""

    id: uuid.UUID
    alternative_names: List[str] = Field(default_factory=list)
    is_active: bool = True
    is_default: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompanyListResponse(BaseModel):
    """Response mit Liste von Companies."""

    items: List[CompanyResponse]
    total: int
    current_company_id: Optional[uuid.UUID] = None


class UserCompanyCreate(BaseModel):
    """Schema zum Hinzufuegen eines Users zu einer Company."""

    user_id: uuid.UUID
    company_id: uuid.UUID
    role: CompanyRole = Field(CompanyRole.MEMBER, description="Rolle in der Firma")
    can_manage_cash: bool = Field(False, description="Kassenbuchungen erstellen")
    can_approve_expenses: bool = Field(False, description="Spesen genehmigen")
    can_export_datev: bool = Field(False, description="DATEV-Export")
    can_manage_settings: bool = Field(False, description="Firmeneinstellungen")


class UserCompanyUpdate(BaseModel):
    """Schema zum Aktualisieren einer User-Company-Zuordnung."""

    role: Optional[CompanyRole] = None
    can_manage_cash: Optional[bool] = None
    can_approve_expenses: Optional[bool] = None
    can_export_datev: Optional[bool] = None
    can_manage_settings: Optional[bool] = None


class UserCompanyResponse(BaseModel):
    """Response-Schema für User-Company-Zuordnung."""

    id: uuid.UUID
    user_id: uuid.UUID
    company_id: uuid.UUID
    role: str
    can_manage_cash: bool
    can_approve_expenses: bool
    can_export_datev: bool
    can_manage_settings: bool
    is_current: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# KASSE-MODUL: CASH REGISTER SCHEMAS
# =============================================================================


class CashRegisterBase(BaseModel):
    """Basis-Schema für CashRegister."""

    name: str = Field(..., min_length=1, max_length=100, description="Kassenname")
    description: Optional[str] = Field(None, description="Beschreibung")
    register_number: Optional[str] = Field(None, max_length=50, description="Interne Kassennummer")
    currency: str = Field("EUR", max_length=3, description="Währung")
    max_balance: Optional[float] = Field(None, ge=0, description="Maximaler Kassenbestand")
    warning_threshold: Optional[float] = Field(None, ge=0, description="Warnschwelle")


class CashRegisterCreate(CashRegisterBase):
    """Schema zum Erstellen einer Kasse."""

    linked_bank_account_id: Optional[uuid.UUID] = Field(None, description="Verknüpftes Bankkonto")
    opening_balance: float = Field(0, description="Anfangsbestand")


class CashRegisterUpdate(BaseModel):
    """Schema zum Aktualisieren einer Kasse."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    register_number: Optional[str] = Field(None, max_length=50)
    max_balance: Optional[float] = Field(None, ge=0)
    warning_threshold: Optional[float] = Field(None, ge=0)
    linked_bank_account_id: Optional[uuid.UUID] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class CashRegisterResponse(CashRegisterBase):
    """Response-Schema für CashRegister."""

    id: uuid.UUID
    company_id: uuid.UUID
    current_balance: float
    balance_date: Optional[datetime] = None
    last_reconciliation_date: Optional[datetime] = None
    linked_bank_account_id: Optional[uuid.UUID] = None
    is_active: bool
    is_default: bool
    # Frontend erwartet diese Felder (werden dynamisch berechnet oder null)
    last_entry_date: Optional[datetime] = None
    last_count_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CashRegisterListResponse(BaseModel):
    """Response mit Liste von Kassen."""

    items: List[CashRegisterResponse]
    total: int


# =============================================================================
# KASSE-MODUL: CASH ENTRY SCHEMAS (GoBD-KONFORM!)
# =============================================================================


class EntertainmentData(BaseModel):
    """Schema für Bewirtungskosten-Daten (70% abzugsfaehig)."""

    participants: List[str] = Field(
        ...,
        min_length=1,
        description="Teilnehmer (mind. 1 Person)"
    )
    occasion: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Anlass der Bewirtung"
    )
    location: Optional[str] = Field(None, max_length=255, description="Ort/Restaurant")

    @field_validator("participants")
    @classmethod
    def validate_participants(cls, v: List[str]) -> List[str]:
        """Mindestens ein Teilnehmer erforderlich."""
        if not v or len(v) == 0:
            raise ValueError("Mindestens ein Teilnehmer muss angegeben werden")
        return [p.strip() for p in v if p.strip()]


class CashEntryBase(BaseModel):
    """Basis-Schema für CashEntry."""

    entry_type: CashEntryType = Field(..., description="Buchungstyp")
    entry_date: datetime = Field(..., description="Buchungsdatum (nicht in Zukunft!)")
    amount: float = Field(
        ...,
        gt=-9999999999999.99,  # Max 13 Stellen vor Komma (DB: Numeric(15,2))
        lt=9999999999999.99,
        description="Betrag (positiv=Einnahme, negativ=Ausgabe)"
    )
    description: str = Field(..., min_length=3, max_length=1000, description="Beschreibung")
    reference_number: Optional[str] = Field(None, max_length=100, description="Belegnummer")
    category_id: Optional[uuid.UUID] = Field(None, description="Kategorie-ID")

    # Steuer
    tax_rate: Optional[float] = Field(None, ge=0, le=100, description="MwSt-Satz")

    # Geschäftspartner
    counterparty_name: Optional[str] = Field(None, max_length=255, description="Geschäftspartner")
    counterparty_id: Optional[uuid.UUID] = Field(None, description="Geschäftspartner-ID")

    # Verknüpfungen
    document_id: Optional[uuid.UUID] = Field(None, description="Beleg-Dokument")
    bank_transaction_id: Optional[uuid.UUID] = Field(None, description="Bank-Transaktion")

    # Buchhaltung
    cost_center: Optional[str] = Field(None, max_length=50, description="Kostenstelle")

    @field_validator("entry_date")
    @classmethod
    def validate_entry_date(cls, v: datetime) -> datetime:
        """Buchungsdatum darf nicht in der Zukunft liegen (GoBD!)."""
        from datetime import date, timedelta
        if v.date() > date.today():
            raise ValueError("Buchungsdatum darf nicht in der Zukunft liegen (GoBD-Compliance)")
        # GoBD: Buchungen aelter als 10 Jahre sind verdaechtig
        if v.date() < date.today() - timedelta(days=3650):
            raise ValueError("Buchungsdatum darf nicht aelter als 10 Jahre sein")
        return v

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        """Betrag darf nicht 0 sein und maximal 2 Dezimalstellen (GoBD!)."""
        if v == 0:
            raise ValueError("Betrag darf nicht 0 sein")
        # Maximal 2 Dezimalstellen (Cent-Genauigkeit)
        if round(v, 2) != v:
            raise ValueError("Betrag darf maximal 2 Dezimalstellen haben")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Beschreibung bereinigen und validieren."""
        # Whitespace normalisieren
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("Beschreibung muss mindestens 3 Zeichen haben")
        return v


class CashEntryCreate(CashEntryBase):
    """Schema zum Erstellen einer Kassenbuchung.

    WICHTIG: Frontend sendet 'register_id', Backend verwendet intern 'cash_register_id'.
    Durch alias und populate_by_name werden beide Namen akzeptiert.
    """

    cash_register_id: uuid.UUID = Field(
        ...,
        alias="register_id",  # Frontend sendet register_id
        description="Kassen-ID"
    )
    entertainment_data: Optional[EntertainmentData] = Field(
        None,
        description="Bewirtungskosten-Daten (bei entertainment)"
    )

    model_config = ConfigDict(populate_by_name=True)  # Akzeptiert beide Namen

    @model_validator(mode="after")
    def validate_entertainment(self) -> "CashEntryCreate":
        """Bewirtungsdaten sind bei entertainment Pflicht."""
        if self.entry_type == CashEntryType.ENTERTAINMENT and not self.entertainment_data:
            raise ValueError("Bewirtungsdaten sind bei Bewirtungskosten Pflicht")
        return self


class CashEntryResponse(BaseModel):
    """Response-Schema für CashEntry - Frontend-kompatibel.

    WICHTIG: Feldnamen sind an Frontend angepasst (nicht an DB-Model)!
    Das Mapping erfolgt in der API-Schicht (cash.py).
    """

    id: uuid.UUID
    register_id: uuid.UUID  # Frontend erwartet register_id (nicht cash_register_id)
    entry_number: int
    entry_date: datetime
    entry_type: str
    amount: float
    net_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate: Optional[float] = None
    balance_after: float
    description: str
    category_id: Optional[uuid.UUID] = None
    category_name: Optional[str] = None  # Aus JOIN, nicht im DB-Model
    receipt_number: Optional[str] = None  # Frontend erwartet receipt_number (nicht reference_number)
    counterparty: Optional[str] = None  # Frontend erwartet counterparty (nicht counterparty_name)
    is_entertainment: bool = False  # Frontend erwartet is_entertainment (nicht is_tax_deductible)
    entertainment_data: Optional[Dict[str, Any]] = None
    is_cancelled: bool = False
    cancelled_by_id: Optional[uuid.UUID] = None  # Frontend erwartet cancelled_by_id (nicht cancelled_by_entry_id)
    cancels_entry_id: Optional[uuid.UUID] = None  # Für Storno-Referenz
    skr03_account: Optional[str] = None  # Frontend erwartet skr03_account (nicht debit_account)
    skr04_account: Optional[str] = None  # Frontend erwartet skr04_account (nicht credit_account)
    created_by_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CashEntryListResponse(BaseModel):
    """Response mit Liste von Kassenbuchungen."""

    entries: List[CashEntryResponse]  # Frontend erwartet 'entries' (nicht 'items')
    total: int
    page: int = 1
    page_size: int = 50


class CashEntryCancelRequest(BaseModel):
    """Request zum Stornieren einer Buchung (Gegenbuchung!)."""

    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Stornierungsgrund (Pflicht)"
    )


# =============================================================================
# KASSE-MODUL: CASH CATEGORY SCHEMAS
# =============================================================================


class CashCategoryBase(BaseModel):
    """Basis-Schema für CashCategory."""

    name: str = Field(..., min_length=1, max_length=100, description="Kategoriename")
    name_en: Optional[str] = Field(None, max_length=100, description="Englischer Name")
    description: Optional[str] = Field(None, description="Beschreibung")
    icon: Optional[str] = Field(None, max_length=50, description="Icon-Name")
    color: Optional[str] = Field(None, max_length=7, description="Farbe (Hex)")
    parent_id: Optional[uuid.UUID] = Field(None, description="Überkategorie")
    skr03_account: Optional[str] = Field(None, max_length=10, description="SKR03-Konto")
    skr04_account: Optional[str] = Field(None, max_length=10, description="SKR04-Konto")
    default_tax_rate: float = Field(19, ge=0, le=100, description="Standard-MwSt-Satz")
    is_entertainment: bool = Field(False, description="Bewirtungskosten?")
    is_travel_expense: bool = Field(False, description="Reisekosten?")
    deductible_percentage: int = Field(100, ge=0, le=100, description="Abzugsfähigkeit %")


class CashCategoryCreate(CashCategoryBase):
    """Schema zum Erstellen einer Kategorie."""
    pass


class CashCategoryUpdate(BaseModel):
    """Schema zum Aktualisieren einer Kategorie."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    name_en: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=7)
    parent_id: Optional[uuid.UUID] = None
    skr03_account: Optional[str] = Field(None, max_length=10)
    skr04_account: Optional[str] = Field(None, max_length=10)
    default_tax_rate: Optional[float] = Field(None, ge=0, le=100)
    is_entertainment: Optional[bool] = None
    is_travel_expense: Optional[bool] = None
    deductible_percentage: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CashCategoryResponse(CashCategoryBase):
    """Response-Schema für CashCategory."""

    id: uuid.UUID
    company_id: Optional[uuid.UUID] = None
    level: int
    path: Optional[str] = None
    category_type: Optional[str] = None
    allows_vat_deduction: bool
    is_active: bool
    is_system: bool
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CashCategoryListResponse(BaseModel):
    """Response mit Liste von Kategorien."""

    items: List[CashCategoryResponse]
    total: int


# =============================================================================
# KASSE-MODUL: CASH COUNT SCHEMAS (Kassensturz)
# =============================================================================


class CashCountCreate(BaseModel):
    """Schema zum Erstellen eines Zaehlprotokolls."""

    cash_register_id: uuid.UUID = Field(..., description="Kassen-ID")

    # Muenzen (Stückzahl)
    coins_1_cent: int = Field(0, ge=0)
    coins_2_cent: int = Field(0, ge=0)
    coins_5_cent: int = Field(0, ge=0)
    coins_10_cent: int = Field(0, ge=0)
    coins_20_cent: int = Field(0, ge=0)
    coins_50_cent: int = Field(0, ge=0)
    coins_1_euro: int = Field(0, ge=0)
    coins_2_euro: int = Field(0, ge=0)

    # Scheine (Stückzahl)
    notes_5_euro: int = Field(0, ge=0)
    notes_10_euro: int = Field(0, ge=0)
    notes_20_euro: int = Field(0, ge=0)
    notes_50_euro: int = Field(0, ge=0)
    notes_100_euro: int = Field(0, ge=0)
    notes_200_euro: int = Field(0, ge=0)
    notes_500_euro: int = Field(0, ge=0)

    notes: Optional[str] = Field(None, description="Notizen")


class CashCountResponse(BaseModel):
    """Response-Schema für CashCount."""

    id: uuid.UUID
    company_id: uuid.UUID
    cash_register_id: uuid.UUID
    count_date: datetime
    count_time: str

    # Muenzen
    coins_1_cent: int
    coins_2_cent: int
    coins_5_cent: int
    coins_10_cent: int
    coins_20_cent: int
    coins_50_cent: int
    coins_1_euro: int
    coins_2_euro: int

    # Scheine
    notes_5_euro: int
    notes_10_euro: int
    notes_20_euro: int
    notes_50_euro: int
    notes_100_euro: int
    notes_200_euro: int
    notes_500_euro: int

    # Berechnete Werte
    counted_total: float
    expected_total: float
    difference: float

    # Differenzbuchung
    difference_entry_id: Optional[uuid.UUID] = None
    difference_explanation: Optional[str] = None

    # Signatur
    counted_by_id: uuid.UUID
    verified_by_id: Optional[uuid.UUID] = None
    verified_at: Optional[datetime] = None

    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CashCountListResponse(BaseModel):
    """Response mit Liste von Zaehlprotokollen."""

    counts: List[CashCountResponse]  # Frontend erwartet 'counts', nicht 'items'
    total: int


# =============================================================================
# KASSE-MODUL: EXPENSE REPORT SCHEMAS
# =============================================================================


class ExpenseReportBase(BaseModel):
    """Basis-Schema für ExpenseReport."""

    title: str = Field(..., min_length=3, max_length=255, description="Titel")
    description: Optional[str] = Field(None, description="Beschreibung")
    period_start: datetime = Field(..., description="Zeitraum von")
    period_end: datetime = Field(..., description="Zeitraum bis")

    @model_validator(mode="after")
    def validate_period(self) -> "ExpenseReportBase":
        """Zeitraum validieren."""
        if self.period_end < self.period_start:
            raise ValueError("Enddatum muss nach Startdatum liegen")
        return self


class ExpenseReportCreate(ExpenseReportBase):
    """Schema zum Erstellen einer Spesenabrechnung."""

    employee_id: Optional[uuid.UUID] = Field(None, description="Mitarbeiter-ID (optional, sonst aktueller User)")


class ExpenseReportUpdate(BaseModel):
    """Schema zum Aktualisieren einer Spesenabrechnung."""

    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


class ExpenseReportResponse(ExpenseReportBase):
    """Response-Schema für ExpenseReport."""

    id: uuid.UUID
    company_id: uuid.UUID
    report_number: str
    employee_id: uuid.UUID
    employee_name: Optional[str] = None

    # Betraege
    total_amount: float
    total_vat: float
    total_deductible: float
    travel_days: int
    travel_allowance_total: float
    total_kilometers: float
    mileage_allowance_total: float

    # Status
    status: str

    # Workflow
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None

    cash_entry_id: Optional[uuid.UUID] = None
    datev_exported_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseReportListResponse(BaseModel):
    """Response mit Liste von Spesenabrechnungen."""

    items: List[ExpenseReportResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ExpenseReportSubmitRequest(BaseModel):
    """Request zum Einreichen einer Spesenabrechnung."""

    notes: Optional[str] = Field(None, description="Anmerkungen")


class ExpenseReportReviewRequest(BaseModel):
    """Request zum Review einer Spesenabrechnung."""

    approved: bool = Field(..., description="Genehmigt?")
    notes: Optional[str] = Field(None, description="Anmerkungen")
    rejection_reason: Optional[str] = Field(None, description="Ablehnungsgrund")


class ExpenseReportPayRequest(BaseModel):
    """Request zur Auszahlung einer Spesenabrechnung."""

    payment_method: str = Field(..., description="Zahlungsart (cash, transfer)")
    payment_reference: Optional[str] = Field(None, description="Zahlungsreferenz")
    cash_register_id: Optional[uuid.UUID] = Field(None, description="Kassen-ID (bei Barzahlung)")


# =============================================================================
# KASSE-MODUL: EXPENSE ITEM SCHEMAS
# =============================================================================


class ExpenseItemBase(BaseModel):
    """Basis-Schema für ExpenseItem."""

    expense_type: ExpenseType = Field(..., description="Typ")
    expense_date: datetime = Field(..., description="Datum")
    amount: float = Field(..., gt=0, description="Betrag")
    description: str = Field(..., min_length=3, max_length=500, description="Beschreibung")
    category_id: Optional[uuid.UUID] = Field(None, description="Kategorie")
    tax_rate: Optional[float] = Field(None, ge=0, le=100, description="MwSt-Satz")
    vendor_name: Optional[str] = Field(None, max_length=255, description="Lieferant")


class ExpenseItemCreate(ExpenseItemBase):
    """Schema zum Erstellen einer Spesenposition."""

    # Beleg
    document_id: Optional[uuid.UUID] = Field(None, description="Beleg-Dokument")
    receipt_number: Optional[str] = Field(None, max_length=100, description="Belegnummer")

    # Bewirtung
    entertainment_participants: Optional[List[str]] = Field(None, description="Teilnehmer")
    entertainment_occasion: Optional[str] = Field(None, description="Anlass")
    entertainment_location: Optional[str] = Field(None, description="Ort")

    # Kilometergeld
    mileage_from: Optional[str] = Field(None, description="Start")
    mileage_to: Optional[str] = Field(None, description="Ziel")
    mileage_kilometers: Optional[float] = Field(None, gt=0, description="Kilometer")
    mileage_vehicle_type: Optional[str] = Field(None, description="Fahrzeugtyp")
    mileage_license_plate: Optional[str] = Field(None, description="Kennzeichen")

    # Verpflegung
    per_diem_hours: Optional[float] = Field(None, gt=0, le=24, description="Stunden")
    per_diem_breakfast_provided: bool = Field(False, description="Frühstück gestellt")
    per_diem_lunch_provided: bool = Field(False, description="Mittagessen gestellt")
    per_diem_dinner_provided: bool = Field(False, description="Abendessen gestellt")

    # Buchhaltung
    cost_center: Optional[str] = Field(None, description="Kostenstelle")


class ExpenseItemUpdate(BaseModel):
    """Schema zum Aktualisieren einer Spesenposition."""

    expense_type: Optional[ExpenseType] = None
    expense_date: Optional[datetime] = None
    amount: Optional[float] = Field(None, gt=0)
    description: Optional[str] = Field(None, min_length=3, max_length=500)
    category_id: Optional[uuid.UUID] = None
    tax_rate: Optional[float] = Field(None, ge=0, le=100)
    vendor_name: Optional[str] = Field(None, max_length=255)
    document_id: Optional[uuid.UUID] = None
    receipt_number: Optional[str] = Field(None, max_length=100)
    entertainment_participants: Optional[List[str]] = None
    entertainment_occasion: Optional[str] = None
    entertainment_location: Optional[str] = None
    mileage_from: Optional[str] = None
    mileage_to: Optional[str] = None
    mileage_kilometers: Optional[float] = Field(None, gt=0)
    mileage_vehicle_type: Optional[str] = None
    mileage_license_plate: Optional[str] = None
    per_diem_hours: Optional[float] = Field(None, gt=0, le=24)
    per_diem_breakfast_provided: Optional[bool] = None
    per_diem_lunch_provided: Optional[bool] = None
    per_diem_dinner_provided: Optional[bool] = None
    cost_center: Optional[str] = None


class ExpenseItemResponse(BaseModel):
    """Response-Schema für ExpenseItem."""

    id: uuid.UUID
    expense_report_id: uuid.UUID
    expense_type: str
    expense_date: datetime
    amount: float
    currency: str
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    net_amount: Optional[float] = None
    is_deductible: bool
    deductible_percentage: int
    deductible_amount: Optional[float] = None
    description: str
    category_id: Optional[uuid.UUID] = None
    document_id: Optional[uuid.UUID] = None
    receipt_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_id: Optional[uuid.UUID] = None

    # Bewirtung
    entertainment_participants: Optional[List[str]] = None
    entertainment_occasion: Optional[str] = None
    entertainment_location: Optional[str] = None

    # Kilometergeld
    mileage_from: Optional[str] = None
    mileage_to: Optional[str] = None
    mileage_kilometers: Optional[float] = None
    mileage_rate: Optional[float] = None
    mileage_vehicle_type: Optional[str] = None
    mileage_license_plate: Optional[str] = None

    # Verpflegung
    per_diem_hours: Optional[float] = None
    per_diem_rate: Optional[float] = None
    per_diem_breakfast_provided: bool = False
    per_diem_lunch_provided: bool = False
    per_diem_dinner_provided: bool = False

    skr_account: Optional[str] = None
    cost_center: Optional[str] = None
    sort_order: int

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# KASSE-MODUL: SUMMARY SCHEMAS
# =============================================================================


class CashBookSummary(BaseModel):
    """Zusammenfassung eines Kassenbuches."""

    register_id: uuid.UUID
    register_name: str
    period_start: datetime
    period_end: datetime

    opening_balance: float
    closing_balance: float

    total_income: float
    total_expense: float
    net_change: float

    entry_count: int
    cancelled_count: int


class DailySummary(BaseModel):
    """Tageszusammenfassung."""

    date: datetime
    opening_balance: float
    closing_balance: float
    income: float
    expense: float
    net_change: float
    entry_count: int


class CashBookSummaryResponse(BaseModel):
    """Response mit Kassenbuch-Zusammenfassung."""

    summary: CashBookSummary
    daily_summaries: List[DailySummary]


# =============================================================================
# KASSE-MODUL: CALCULATOR SCHEMAS
# =============================================================================


class PerDiemCalculationRequest(BaseModel):
    """Request zur Berechnung der Verpflegungspauschale."""

    travel_date: datetime = Field(..., description="Reisetag")
    hours_away: float = Field(..., gt=0, le=24, description="Abwesenheitsstunden")
    breakfast_provided: bool = Field(False, description="Frühstück gestellt")
    lunch_provided: bool = Field(False, description="Mittagessen gestellt")
    dinner_provided: bool = Field(False, description="Abendessen gestellt")
    is_domestic: bool = Field(True, description="Inland?")
    country: Optional[str] = Field(None, description="Land (bei Ausland)")


class PerDiemCalculationResponse(BaseModel):
    """Response mit berechneter Verpflegungspauschale."""

    travel_start: datetime = Field(..., description="Reisebeginn")
    travel_end: datetime = Field(..., description="Reiseende")
    total_hours: Decimal = Field(..., description="Gesamtstunden")
    country: str = Field("DE", description="Ländercode")
    base_rate: Decimal = Field(..., description="Grundpauschale")
    rate_type: str = Field(..., description="Pauschale-Typ (full_day, partial_day, none)")
    meals_provided: Dict[str, bool] = Field(
        default_factory=dict,
        description="Gestellte Mahlzeiten"
    )
    meal_reductions: Decimal = Field(default=Decimal("0.00"), description="Kürzungen")
    total_amount: Decimal = Field(..., description="Endbetrag")


class MileageCalculationRequest(BaseModel):
    """Request zur Berechnung des Kilometergeldes."""

    kilometers: float = Field(..., gt=0, description="Gefahrene Kilometer")
    vehicle_type: str = Field("pkw", description="Fahrzeugtyp (pkw, motorrad)")


class MileageCalculationResponse(BaseModel):
    """Response mit berechnetem Kilometergeld."""

    kilometers: float
    rate_per_km: float
    total_amount: float


# ==================== Workflow Request Schemas ====================

class ExpenseReportApproveRequest(BaseModel):
    """Request für Spesenabrechnung-Genehmigung."""

    approved_amount: Optional[Decimal] = Field(
        None,
        description="Optional geänderter genehmigter Betrag"
    )
    notes: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optionale Notizen zur Genehmigung"
    )


class ExpenseReportRejectRequest(BaseModel):
    """Request für Spesenabrechnung-Ablehnung."""

    reason: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Grund für die Ablehnung"
    )


# ==================== Aliase für Rückwärtskompatibilität ====================

# Diese Aliase ermöglichen flexible Imports in Services und APIs
PerDiemCalculation = PerDiemCalculationResponse
MileageCalculation = MileageCalculationResponse
PerDiemCalculateRequest = PerDiemCalculationRequest
MileageCalculateRequest = MileageCalculationRequest


# =============================================================================
# PRIVAT-MODUL: ENUMS
# =============================================================================


class PrivatSpaceType(str, Enum):
    """Typ des privaten Bereichs."""
    PERSONAL = "personal"
    SHARED = "shared"


class PrivatAccessLevel(str, Enum):
    """Zugriffsebene für geteilte Bereiche."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class PrivatDocumentType(str, Enum):
    """Dokumententypen im Privat-Modul."""
    GENERAL = "general"
    CONTRACT = "contract"
    CERTIFICATE = "certificate"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    STATEMENT = "statement"
    LETTER = "letter"
    FORM = "form"
    TAX = "tax"
    INSURANCE = "insurance"
    MEDICAL = "medical"


class PrivatDeadlineType(str, Enum):
    """Fristentypen im Privat-Modul."""
    INSURANCE_PREMIUM = "insurance_premium"
    LOAN_PAYMENT = "loan_payment"
    RENT_DUE = "rent_due"
    TAX_DEADLINE = "tax_deadline"
    CONTRACT_RENEWAL = "contract_renewal"
    VEHICLE_SERVICE = "vehicle_service"
    VEHICLE_INSPECTION = "vehicle_inspection"
    CUSTOM = "custom"


class PrivatEmergencyAccessStatus(str, Enum):
    """Status für Notfallzugriff-Anfragen."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class InsuranceType(str, Enum):
    """Versicherungstypen."""
    LIABILITY = "liability"
    HEALTH = "health"
    LIFE = "life"
    PROPERTY = "property"
    VEHICLE = "vehicle"
    TRAVEL = "travel"
    LEGAL = "legal"
    DISABILITY = "disability"
    OTHER = "other"


class VehicleType(str, Enum):
    """Fahrzeugtypen."""
    CAR = "car"
    MOTORCYCLE = "motorcycle"
    TRUCK = "truck"
    TRAILER = "trailer"
    OTHER = "other"


class FuelType(str, Enum):
    """Kraftstofftypen."""
    PETROL = "petrol"
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    LPG = "lpg"
    CNG = "cng"
    OTHER = "other"


class LoanType(str, Enum):
    """Kredittypen."""
    MORTGAGE = "mortgage"
    PERSONAL = "personal"
    CAR = "car"
    BUSINESS = "business"
    STUDENT = "student"
    OTHER = "other"


class InvestmentType(str, Enum):
    """Anlagetypen."""
    SAVINGS = "savings"
    STOCKS = "stocks"
    BONDS = "bonds"
    FUNDS = "funds"
    ETF = "etf"
    REAL_ESTATE = "real_estate"
    CRYPTO = "crypto"
    INSURANCE = "insurance"
    OTHER = "other"


# =============================================================================
# PRIVAT-MODUL: SPACE SCHEMAS
# =============================================================================


class PrivatSpaceBase(BaseModel):
    """Basis-Schema für Privat-Space."""
    name: str = Field(..., min_length=1, max_length=200, description="Name des Bereichs")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    space_type: PrivatSpaceType = Field(PrivatSpaceType.PERSONAL, description="Bereichstyp")


class PrivatSpaceCreate(PrivatSpaceBase):
    """Schema zum Erstellen eines Privat-Space."""
    pass


class PrivatSpaceUpdate(BaseModel):
    """Schema zum Aktualisieren eines Privat-Space."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    is_active: Optional[bool] = None


class PrivatSpaceResponse(PrivatSpaceBase):
    """Response-Schema für Privat-Space."""
    id: uuid.UUID
    owner_id: Optional[uuid.UUID] = None
    company_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatSpaceWithStats(PrivatSpaceResponse):
    """Privat-Space mit Statistiken."""
    folder_count: int = 0
    document_count: int = 0
    total_size_bytes: int = 0
    pending_deadlines: int = 0


# =============================================================================
# PRIVAT-MODUL: ACCESS SCHEMAS
# =============================================================================


class PrivatSpaceAccessBase(BaseModel):
    """Basis-Schema für Space-Zugriff."""
    access_level: PrivatAccessLevel = Field(..., description="Zugriffsebene")


class PrivatSpaceAccessCreate(PrivatSpaceAccessBase):
    """Schema zum Erstellen eines Space-Zugriffs."""
    user_id: uuid.UUID = Field(..., description="Benutzer-ID")


class PrivatSpaceAccessUpdate(BaseModel):
    """Schema zum Aktualisieren eines Space-Zugriffs."""
    access_level: Optional[PrivatAccessLevel] = None


class PrivatSpaceAccessResponse(PrivatSpaceAccessBase):
    """Response-Schema für Space-Zugriff."""
    id: uuid.UUID
    space_id: uuid.UUID
    user_id: uuid.UUID
    granted_by: Optional[uuid.UUID] = None
    created_at: datetime
    expires_at: Optional[datetime] = None  # SECURITY: Ablaufdatum für zeitlich begrenzte Zugriffe
    is_active: bool = True  # Computed field - nur aktive Zugriffe werden zurückgegeben

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: FOLDER SCHEMAS
# =============================================================================


class PrivatFolderBase(BaseModel):
    """Basis-Schema für Privat-Ordner."""
    name: str = Field(..., min_length=1, max_length=200, description="Ordnername")
    description: Optional[str] = Field(None, max_length=1000, description="Beschreibung")
    color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$", description="Farbcode")
    icon: Optional[str] = Field(None, max_length=50, description="Icon-Name")


class PrivatFolderCreate(PrivatFolderBase):
    """Schema zum Erstellen eines Privat-Ordners."""
    parent_id: Optional[uuid.UUID] = Field(None, description="Übergeordneter Ordner")


class PrivatFolderUpdate(BaseModel):
    """Schema zum Aktualisieren eines Privat-Ordners."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    parent_id: Optional[uuid.UUID] = None


class PrivatFolderResponse(PrivatFolderBase):
    """Response-Schema für Privat-Ordner."""
    id: uuid.UUID
    space_id: uuid.UUID
    parent_id: Optional[uuid.UUID] = None
    path: str
    level: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatFolderTree(PrivatFolderResponse):
    """Ordner mit Unterordnern (Baum-Struktur)."""
    children: List["PrivatFolderTree"] = []
    document_count: int = 0


# =============================================================================
# PRIVAT-MODUL: DOCUMENT SCHEMAS
# =============================================================================


class PrivatDocumentBase(BaseModel):
    """Basis-Schema für Privat-Dokument."""
    title: str = Field(..., min_length=1, max_length=200, description="Dokumenttitel")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    document_type: PrivatDocumentType = Field(
        PrivatDocumentType.GENERAL,
        description="Dokumenttyp"
    )
    tags: Optional[List[str]] = Field(None, max_length=20, description="Tags")


class PrivatDocumentCreate(PrivatDocumentBase):
    """Schema zum Erstellen eines Privat-Dokuments."""
    folder_id: Optional[uuid.UUID] = Field(None, description="Ordner-ID")
    extra_encrypted: bool = Field(False, description="Extra-Verschluesselung aktivieren")
    password_hint: Optional[str] = Field(None, max_length=200, description="Passwort-Hinweis")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validiere Tags: max 50 Zeichen pro Tag."""
        if v is None:
            return v
        validated = []
        for tag in v:
            if len(tag) > 50:
                raise ValueError(f"Tag zu lang: max 50 Zeichen")
            validated.append(tag.strip().lower())
        return validated


class PrivatDocumentUpdate(BaseModel):
    """Schema zum Aktualisieren eines Privat-Dokuments."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    document_type: Optional[PrivatDocumentType] = None
    tags: Optional[List[str]] = None
    folder_id: Optional[uuid.UUID] = None


class PrivatDocumentResponse(PrivatDocumentBase):
    """Response-Schema für Privat-Dokument."""
    id: uuid.UUID
    space_id: uuid.UUID
    folder_id: Optional[uuid.UUID] = None
    file_path: str
    file_name: str
    file_size: int
    mime_type: str
    extra_encrypted: bool
    password_hint: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatDocumentUploadRequest(BaseModel):
    """Request zum Hochladen eines Privat-Dokuments."""
    space_id: uuid.UUID = Field(..., description="Space-ID")
    folder_id: Optional[uuid.UUID] = Field(None, description="Ordner-ID")
    title: Optional[str] = Field(None, max_length=200, description="Dokumenttitel")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    document_type: PrivatDocumentType = Field(PrivatDocumentType.GENERAL, description="Typ")
    tags: Optional[List[str]] = Field(None, description="Tags")
    extra_encrypted: bool = Field(False, description="Extra-Verschluesselung")
    extra_password: Optional[str] = Field(None, description="Extra-Passwort")
    password_hint: Optional[str] = Field(None, max_length=200, description="Passwort-Hinweis")


class PrivatDocumentDecryptRequest(BaseModel):
    """Request zum Entschluesseln eines Dokuments."""
    password: str = Field(..., min_length=1, description="Passwort für Extra-Verschluesselung")


# =============================================================================
# PRIVAT-MODUL: PROPERTY (IMMOBILIEN) SCHEMAS
# =============================================================================


class PrivatPropertyBase(BaseModel):
    """Basis-Schema für Immobilie."""
    name: str = Field(..., min_length=1, max_length=200, description="Bezeichnung")
    property_type: str = Field(..., max_length=50, description="Immobilientyp")
    # Adresse (alle Optional wie im Model)
    street: Optional[str] = Field(None, max_length=255, description="Strasse")
    street_number: Optional[str] = Field(None, max_length=20, description="Hausnummer")
    postal_code: Optional[str] = Field(None, max_length=10, description="PLZ")
    city: Optional[str] = Field(None, max_length=100, description="Stadt")
    country: str = Field("DE", max_length=2, description="Ländercode")
    # Kaufdaten
    purchase_date: Optional[date_type] = Field(None, description="Kaufdatum")
    purchase_price: Optional[Decimal] = Field(None, ge=0, description="Kaufpreis")
    notary_costs: Optional[Decimal] = Field(None, ge=0, description="Notarkosten")
    land_transfer_tax: Optional[Decimal] = Field(None, ge=0, description="Grunderwerbsteuer")
    # Laufende Daten
    current_value: Optional[Decimal] = Field(None, ge=0, description="Aktueller Wert")
    value_date: Optional[date_type] = Field(None, description="Bewertungsdatum")
    # Grundbuch
    land_register_entry: Optional[str] = Field(None, max_length=100, description="Grundbucheintrag")
    cadastral_district: Optional[str] = Field(None, max_length=100, description="Gemarkung")
    parcel_number: Optional[str] = Field(None, max_length=50, description="Flurstücknummer")
    # Flaeche
    living_area_sqm: Optional[Decimal] = Field(None, ge=0, description="Wohnflaeche in qm")
    plot_area_sqm: Optional[Decimal] = Field(None, ge=0, description="Grundstücksflaeche in qm")
    # Status
    is_rented: bool = Field(False, description="Vermietet?")
    is_active: bool = Field(True, description="Aktiv?")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatPropertyCreate(PrivatPropertyBase):
    """Schema zum Erstellen einer Immobilie."""
    pass


class PrivatPropertyUpdate(BaseModel):
    """Schema zum Aktualisieren einer Immobilie."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    property_type: Optional[str] = Field(None, max_length=50)
    # Adresse
    street: Optional[str] = Field(None, max_length=255)
    street_number: Optional[str] = Field(None, max_length=20)
    postal_code: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)
    # Kaufdaten
    purchase_date: Optional[date_type] = None
    purchase_price: Optional[Decimal] = Field(None, ge=0)
    notary_costs: Optional[Decimal] = Field(None, ge=0)
    land_transfer_tax: Optional[Decimal] = Field(None, ge=0)
    # Laufende Daten
    current_value: Optional[Decimal] = Field(None, ge=0)
    value_date: Optional[date_type] = None
    # Grundbuch
    land_register_entry: Optional[str] = Field(None, max_length=100)
    cadastral_district: Optional[str] = Field(None, max_length=100)
    parcel_number: Optional[str] = Field(None, max_length=50)
    # Flaeche
    living_area_sqm: Optional[Decimal] = Field(None, ge=0)
    plot_area_sqm: Optional[Decimal] = Field(None, ge=0)
    # Status
    is_rented: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatPropertyResponse(PrivatPropertyBase):
    """Response-Schema für Immobilie."""
    id: uuid.UUID
    space_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatPropertyWithTenants(PrivatPropertyResponse):
    """Immobilie mit Mieterliste."""
    tenants: List["PrivatTenantResponse"] = []
    total_rental_income: Decimal = Decimal("0.00")
    pending_payments: int = 0


# Alias for backward compatibility
PrivatPropertyWithDetails = PrivatPropertyWithTenants


# =============================================================================
# PRIVAT-MODUL: TENANT (MIETER) SCHEMAS
# =============================================================================


class PrivatTenantBase(BaseModel):
    """Basis-Schema für Mieter."""
    first_name: str = Field(..., min_length=1, max_length=100, description="Vorname")
    last_name: str = Field(..., min_length=1, max_length=100, description="Nachname")
    email: Optional[EmailStr] = Field(None, description="E-Mail")
    phone: Optional[str] = Field(None, max_length=50, description="Telefon")
    unit_number: Optional[str] = Field(None, max_length=50, description="Wohnungsnummer")
    lease_start: date_type = Field(..., description="Mietbeginn")
    lease_end: Optional[date_type] = Field(None, description="Mietende")
    monthly_rent: Decimal = Field(..., ge=0, description="Monatliche Miete")
    deposit: Optional[Decimal] = Field(None, ge=0, description="Kaution")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatTenantCreate(PrivatTenantBase):
    """Schema zum Erstellen eines Mieters."""
    property_id: uuid.UUID = Field(..., description="Immobilien-ID")


class PrivatTenantUpdate(BaseModel):
    """Schema zum Aktualisieren eines Mieters."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    unit_number: Optional[str] = Field(None, max_length=50)
    lease_start: Optional[date_type] = None
    lease_end: Optional[date_type] = None
    monthly_rent: Optional[Decimal] = Field(None, ge=0)
    deposit: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatTenantResponse(PrivatTenantBase):
    """Response-Schema für Mieter."""
    id: uuid.UUID
    property_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: RENTAL INCOME (MIETEINNAHMEN) SCHEMAS
# =============================================================================


class PrivatRentalIncomeBase(BaseModel):
    """Basis-Schema für Mieteinnahme."""
    amount: Decimal = Field(..., description="Betrag")
    payment_date: date_type = Field(..., description="Zahlungsdatum")
    period_start: date_type = Field(..., description="Zeitraum Beginn")
    period_end: date_type = Field(..., description="Zeitraum Ende")
    payment_method: Optional[str] = Field(None, max_length=50, description="Zahlungsart")
    notes: Optional[str] = Field(None, max_length=1000, description="Notizen")


class PrivatRentalIncomeCreate(PrivatRentalIncomeBase):
    """Schema zum Erstellen einer Mieteinnahme."""
    tenant_id: uuid.UUID = Field(..., description="Mieter-ID")


class PrivatRentalIncomeUpdate(BaseModel):
    """Schema zum Aktualisieren einer Mieteinnahme."""
    amount: Optional[Decimal] = None
    payment_date: Optional[date_type] = None
    period_start: Optional[date_type] = None
    period_end: Optional[date_type] = None
    payment_method: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class PrivatRentalIncomeResponse(PrivatRentalIncomeBase):
    """Response-Schema für Mieteinnahme."""
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: UTILITY STATEMENT (NEBENKOSTEN) SCHEMAS
# =============================================================================


class PrivatUtilityStatementBase(BaseModel):
    """Basis-Schema für Nebenkostenabrechnung."""
    year: int = Field(..., ge=2000, le=2100, description="Abrechnungsjahr")
    total_amount: Decimal = Field(..., description="Gesamtbetrag")
    prepayments: Decimal = Field(default=Decimal("0.00"), description="Vorauszahlungen")
    balance: Decimal = Field(..., description="Saldo (Nachzahlung/Guthaben)")
    due_date: Optional[date_type] = Field(None, description="Fälligkeitsdatum")
    is_paid: bool = Field(False, description="Bezahlt?")
    notes: Optional[str] = Field(None, max_length=2000, description="Notizen")


class PrivatUtilityStatementCreate(PrivatUtilityStatementBase):
    """Schema zum Erstellen einer Nebenkostenabrechnung."""
    property_id: uuid.UUID = Field(..., description="Immobilien-ID")
    tenant_id: Optional[uuid.UUID] = Field(None, description="Mieter-ID")


class PrivatUtilityStatementUpdate(BaseModel):
    """Schema zum Aktualisieren einer Nebenkostenabrechnung."""
    year: Optional[int] = Field(None, ge=2000, le=2100)
    total_amount: Optional[Decimal] = None
    prepayments: Optional[Decimal] = None
    balance: Optional[Decimal] = None
    due_date: Optional[date_type] = None
    is_paid: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=2000)


class PrivatUtilityStatementResponse(PrivatUtilityStatementBase):
    """Response-Schema für Nebenkostenabrechnung."""
    id: uuid.UUID
    property_id: uuid.UUID
    tenant_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: VEHICLE (FAHRZEUG) SCHEMAS
# =============================================================================


class PrivatVehicleBase(BaseModel):
    """Basis-Schema für Fahrzeug."""
    name: str = Field(..., min_length=1, max_length=200, description="Bezeichnung")
    vehicle_type: VehicleType = Field(VehicleType.CAR, description="Fahrzeugtyp")
    make: str = Field(..., min_length=1, max_length=100, description="Marke")
    model: str = Field(..., min_length=1, max_length=100, description="Modell")
    year: int = Field(..., ge=1900, le=2100, description="Baujahr")
    license_plate: Optional[str] = Field(None, max_length=20, description="Kennzeichen")
    vin: Optional[str] = Field(None, max_length=50, description="FIN")
    fuel_type: FuelType = Field(FuelType.PETROL, description="Kraftstoffart")
    mileage: Optional[int] = Field(None, ge=0, description="Kilometerstand")
    purchase_date: Optional[date_type] = Field(None, description="Kaufdatum")
    purchase_price: Optional[Decimal] = Field(None, ge=0, description="Kaufpreis")
    current_value: Optional[Decimal] = Field(None, ge=0, description="Aktueller Wert")
    next_inspection: Optional[date_type] = Field(None, description="Nächste HU/AU")
    next_service: Optional[date_type] = Field(None, description="Nächster Service")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatVehicleCreate(PrivatVehicleBase):
    """Schema zum Erstellen eines Fahrzeugs."""
    pass


class PrivatVehicleUpdate(BaseModel):
    """Schema zum Aktualisieren eines Fahrzeugs."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    vehicle_type: Optional[VehicleType] = None
    make: Optional[str] = Field(None, min_length=1, max_length=100)
    model: Optional[str] = Field(None, min_length=1, max_length=100)
    year: Optional[int] = Field(None, ge=1900, le=2100)
    license_plate: Optional[str] = Field(None, max_length=20)
    vin: Optional[str] = Field(None, max_length=50)
    fuel_type: Optional[FuelType] = None
    mileage: Optional[int] = Field(None, ge=0)
    purchase_date: Optional[date_type] = None
    purchase_price: Optional[Decimal] = Field(None, ge=0)
    current_value: Optional[Decimal] = Field(None, ge=0)
    next_inspection: Optional[date_type] = None
    next_service: Optional[date_type] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatVehicleResponse(PrivatVehicleBase):
    """Response-Schema für Fahrzeug."""
    id: uuid.UUID
    space_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatVehicleWithLogs(PrivatVehicleResponse):
    """Fahrzeug mit Tankbelegen."""
    recent_fuel_logs: List["PrivatFuelLogResponse"] = []
    total_fuel_cost_year: Decimal = Decimal("0.00")
    average_consumption: Optional[Decimal] = None


# Alias for backward compatibility
PrivatVehicleWithStats = PrivatVehicleWithLogs


# =============================================================================
# PRIVAT-MODUL: FUEL LOG (TANKBELEG) SCHEMAS
# =============================================================================


class PrivatFuelLogBase(BaseModel):
    """Basis-Schema für Tankbeleg."""
    date: date_type = Field(..., description="Tankdatum")
    mileage: int = Field(..., ge=0, description="Kilometerstand")
    liters: Decimal = Field(..., gt=0, description="Liter")
    price_per_liter: Decimal = Field(..., gt=0, description="Preis pro Liter")
    total_price: Decimal = Field(..., gt=0, description="Gesamtpreis")
    fuel_type: FuelType = Field(FuelType.PETROL, description="Kraftstoffart")
    station_name: Optional[str] = Field(None, max_length=200, description="Tankstelle")
    is_full_tank: bool = Field(True, description="Vollgetankt?")
    notes: Optional[str] = Field(None, max_length=1000, description="Notizen")


class PrivatFuelLogCreate(PrivatFuelLogBase):
    """Schema zum Erstellen eines Tankbelegs."""
    vehicle_id: uuid.UUID = Field(..., description="Fahrzeug-ID")


class PrivatFuelLogUpdate(BaseModel):
    """Schema zum Aktualisieren eines Tankbelegs."""
    date: Optional[date_type] = None
    mileage: Optional[int] = Field(None, ge=0)
    liters: Optional[Decimal] = Field(None, gt=0)
    price_per_liter: Optional[Decimal] = Field(None, gt=0)
    total_price: Optional[Decimal] = Field(None, gt=0)
    fuel_type: Optional[FuelType] = None
    station_name: Optional[str] = Field(None, max_length=200)
    is_full_tank: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=1000)


class PrivatFuelLogResponse(PrivatFuelLogBase):
    """Response-Schema für Tankbeleg."""
    id: uuid.UUID
    vehicle_id: uuid.UUID
    consumption: Optional[Decimal] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatFuelStatisticsResponse(BaseModel):
    """Response-Schema für Kraftstoff-Statistiken."""
    fill_ups: int = Field(..., description="Anzahl Tankfuellungen")
    total_liters: Decimal = Field(..., description="Gesamtliter")
    total_cost: Decimal = Field(..., description="Gesamtkosten")
    avg_price_per_liter: Decimal = Field(..., description="Durchschnittspreis pro Liter")
    total_kilometers: int = Field(..., description="Gefahrene Kilometer")
    avg_consumption_per_100km: Optional[Decimal] = Field(
        None, description="Durchschnittsverbrauch pro 100km"
    )

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: INSURANCE (VERSICHERUNG) SCHEMAS
# =============================================================================


class PrivatInsuranceBase(BaseModel):
    """Basis-Schema für Versicherung."""
    name: str = Field(..., min_length=1, max_length=200, description="Bezeichnung")
    insurance_type: InsuranceType = Field(..., description="Versicherungstyp")
    provider: str = Field(..., min_length=1, max_length=200, description="Anbieter")
    policy_number: Optional[str] = Field(None, max_length=100, description="Policennummer")
    premium: Decimal = Field(..., ge=0, description="Praemie")
    premium_interval: str = Field(
        "monthly",
        pattern="^(monthly|quarterly|semi_annual|annual)$",
        description="Zahlungsintervall"
    )
    coverage_amount: Optional[Decimal] = Field(None, ge=0, description="Deckungssumme")
    deductible: Optional[Decimal] = Field(None, ge=0, description="Selbstbeteiligung")
    start_date: date_type = Field(..., description="Vertragsbeginn")
    end_date: Optional[date_type] = Field(None, description="Vertragsende")
    cancellation_period: Optional[int] = Field(
        None,
        ge=0,
        description="Kündigungsfrist in Tagen"
    )
    auto_renewal: bool = Field(True, description="Automatische Verlängerung")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatInsuranceCreate(PrivatInsuranceBase):
    """Schema zum Erstellen einer Versicherung."""
    pass


class PrivatInsuranceUpdate(BaseModel):
    """Schema zum Aktualisieren einer Versicherung."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    insurance_type: Optional[InsuranceType] = None
    provider: Optional[str] = Field(None, min_length=1, max_length=200)
    policy_number: Optional[str] = Field(None, max_length=100)
    premium: Optional[Decimal] = Field(None, ge=0)
    premium_interval: Optional[str] = Field(None, pattern="^(monthly|quarterly|semi_annual|annual)$")
    coverage_amount: Optional[Decimal] = Field(None, ge=0)
    deductible: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    cancellation_period: Optional[int] = Field(None, ge=0)
    auto_renewal: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatInsuranceResponse(PrivatInsuranceBase):
    """Response-Schema für Versicherung."""
    id: uuid.UUID
    space_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatInsuranceWithDeadlines(PrivatInsuranceResponse):
    """Versicherung mit Fristen."""
    upcoming_payment: Optional[date_type] = None
    days_until_payment: Optional[int] = None
    annual_cost: Decimal = Decimal("0.00")


# =============================================================================
# PRIVAT-MODUL: LOAN (KREDIT) SCHEMAS
# =============================================================================


class PrivatLoanBase(BaseModel):
    """Basis-Schema für Kredit."""
    name: str = Field(..., min_length=1, max_length=200, description="Bezeichnung")
    loan_type: LoanType = Field(..., description="Kredittyp")
    lender: str = Field(..., min_length=1, max_length=200, description="Kreditgeber")
    principal_amount: Decimal = Field(..., gt=0, description="Darlehensbetrag")
    current_balance: Decimal = Field(..., ge=0, description="Aktuelle Restschuld")
    interest_rate: Decimal = Field(..., ge=0, le=100, description="Zinssatz in %")
    monthly_payment: Decimal = Field(..., ge=0, description="Monatliche Rate")
    start_date: date_type = Field(..., description="Vertragsbeginn")
    end_date: Optional[date_type] = Field(None, description="Vertragsende")
    next_payment_date: Optional[date_type] = Field(None, description="Nächste Zahlung")
    account_number: Optional[str] = Field(None, max_length=50, description="Kontonummer")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatLoanCreate(PrivatLoanBase):
    """Schema zum Erstellen eines Kredits."""
    pass


class PrivatLoanUpdate(BaseModel):
    """Schema zum Aktualisieren eines Kredits."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    loan_type: Optional[LoanType] = None
    lender: Optional[str] = Field(None, min_length=1, max_length=200)
    principal_amount: Optional[Decimal] = Field(None, gt=0)
    current_balance: Optional[Decimal] = Field(None, ge=0)
    interest_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    monthly_payment: Optional[Decimal] = Field(None, ge=0)
    start_date: Optional[date_type] = None
    end_date: Optional[date_type] = None
    next_payment_date: Optional[date_type] = None
    account_number: Optional[str] = Field(None, max_length=50)
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatLoanResponse(PrivatLoanBase):
    """Response-Schema für Kredit."""
    id: uuid.UUID
    space_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatLoanWithStats(PrivatLoanResponse):
    """Kredit mit Statistiken."""
    total_paid: Decimal = Decimal("0.00")
    total_interest_paid: Decimal = Decimal("0.00")
    remaining_months: Optional[int] = None
    payoff_date: Optional[date_type] = None


# =============================================================================
# PRIVAT-MODUL: INVESTMENT (GELDANLAGE) SCHEMAS
# =============================================================================


class PrivatInvestmentBase(BaseModel):
    """Basis-Schema für Geldanlage."""
    name: str = Field(..., min_length=1, max_length=200, description="Bezeichnung")
    investment_type: InvestmentType = Field(..., description="Anlagetyp")
    institution: str = Field(..., min_length=1, max_length=200, description="Institut")
    account_number: Optional[str] = Field(None, max_length=50, description="Kontonummer")
    initial_amount: Decimal = Field(..., ge=0, description="Anfangsbetrag")
    current_value: Decimal = Field(..., ge=0, description="Aktueller Wert")
    interest_rate: Optional[Decimal] = Field(None, ge=0, le=100, description="Zinssatz in %")
    start_date: date_type = Field(..., description="Beginn")
    maturity_date: Optional[date_type] = Field(None, description="Fälligkeit")
    is_taxable: bool = Field(True, description="Steuerpflichtig?")
    notes: Optional[str] = Field(None, max_length=5000, description="Notizen")


class PrivatInvestmentCreate(PrivatInvestmentBase):
    """Schema zum Erstellen einer Geldanlage."""
    pass


class PrivatInvestmentUpdate(BaseModel):
    """Schema zum Aktualisieren einer Geldanlage."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    investment_type: Optional[InvestmentType] = None
    institution: Optional[str] = Field(None, min_length=1, max_length=200)
    account_number: Optional[str] = Field(None, max_length=50)
    initial_amount: Optional[Decimal] = Field(None, ge=0)
    current_value: Optional[Decimal] = Field(None, ge=0)
    interest_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    start_date: Optional[date_type] = None
    maturity_date: Optional[date_type] = None
    is_taxable: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=5000)


class PrivatInvestmentResponse(PrivatInvestmentBase):
    """Response-Schema für Geldanlage."""
    id: uuid.UUID
    space_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrivatInvestmentWithStats(PrivatInvestmentResponse):
    """Geldanlage mit Statistiken."""
    total_return: Decimal = Decimal("0.00")
    return_percentage: Decimal = Decimal("0.00")
    annual_return: Optional[Decimal] = None


# =============================================================================
# PRIVAT-MODUL: PORTFOLIO SNAPSHOT SCHEMAS
# =============================================================================


class PortfolioSnapshotBase(BaseModel):
    """Basis-Schema für Portfolio-Snapshot."""
    snapshot_date: date_type = Field(..., description="Datum des Snapshots")
    total_real_estate: Decimal = Field(default=Decimal("0"), description="Immobilienwerte")
    total_vehicles: Decimal = Field(default=Decimal("0"), description="Fahrzeugwerte")
    total_investments: Decimal = Field(default=Decimal("0"), description="Anlagewerte")
    total_cash: Decimal = Field(default=Decimal("0"), description="Bargeld/Konten")
    total_other_assets: Decimal = Field(default=Decimal("0"), description="Sonstige Vermögenswerte")
    total_mortgages: Decimal = Field(default=Decimal("0"), description="Hypotheken")
    total_loans: Decimal = Field(default=Decimal("0"), description="Sonstige Kredite")
    total_other_liabilities: Decimal = Field(default=Decimal("0"), description="Sonstige Verbindlichkeiten")
    total_assets: Decimal = Field(default=Decimal("0"), description="Summe Vermögenswerte")
    total_liabilities: Decimal = Field(default=Decimal("0"), description="Summe Verbindlichkeiten")
    net_worth: Decimal = Field(default=Decimal("0"), description="Nettovermoegen")
    net_worth_change_absolute: Optional[Decimal] = Field(None, description="Absolute Änderung")
    net_worth_change_percent: Optional[Decimal] = Field(None, description="Prozentuale Änderung")
    debt_to_assets_ratio: Decimal = Field(default=Decimal("0"), description="Schuldenquote")
    liquidity_ratio: Decimal = Field(default=Decimal("0"), description="Liquiditaetsquote")
    asset_allocation: Optional[Dict[str, Decimal]] = Field(None, description="Asset Allocation")


class PortfolioSnapshotResponse(PortfolioSnapshotBase):
    """Response-Schema für Portfolio-Snapshot."""
    id: UUID
    space_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioSnapshotListResponse(BaseModel):
    """Liste von Portfolio-Snapshots."""
    snapshots: List[PortfolioSnapshotResponse]
    total: int


class PortfolioDashboardResponse(BaseModel):
    """Vollständige Portfolio-Dashboard Response."""
    current_snapshot: Optional[PortfolioSnapshotResponse] = None
    historical_snapshots: List[PortfolioSnapshotResponse] = Field(default_factory=list)
    net_worth_trend: List[Dict[str, Any]] = Field(default_factory=list, description="Trend-Daten")
    goals: List["FinancialGoalResponse"] = Field(default_factory=list, description="Finanzielle Ziele")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: FINANCIAL GOAL SCHEMAS
# =============================================================================


class FinancialGoalType(str, Enum):
    """Typen von finanziellen Zielen."""
    retirement = "retirement"
    education = "education"
    property = "property"
    debt_free = "debt_free"
    emergency_fund = "emergency_fund"
    custom = "custom"


class FinancialGoalStatus(str, Enum):
    """Status eines finanziellen Ziels."""
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class FinancialGoalBase(BaseModel):
    """Basis-Schema für finanzielles Ziel."""
    name: str = Field(..., min_length=1, max_length=200, description="Name des Ziels")
    goal_type: FinancialGoalType = Field(..., description="Art des Ziels")
    target_value: Decimal = Field(..., gt=0, description="Zielwert")
    target_date: date_type = Field(..., description="Zieldatum")
    current_value: Decimal = Field(default=Decimal("0"), ge=0, description="Aktueller Wert")
    priority: int = Field(default=1, ge=1, le=10, description="Priorität (1=hoechste)")
    status: FinancialGoalStatus = Field(default=FinancialGoalStatus.active, description="Status")


class FinancialGoalCreate(FinancialGoalBase):
    """Schema zum Erstellen eines finanziellen Ziels."""
    linked_assets: Optional[Dict[str, Any]] = Field(None, description="Verknüpfte Assets")


class FinancialGoalUpdate(BaseModel):
    """Schema zum Aktualisieren eines finanziellen Ziels."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    target_value: Optional[Decimal] = Field(None, gt=0)
    target_date: Optional[date_type] = None
    current_value: Optional[Decimal] = Field(None, ge=0)
    priority: Optional[int] = Field(None, ge=1, le=10)
    status: Optional[FinancialGoalStatus] = None
    linked_assets: Optional[Dict[str, Any]] = None


class FinancialGoalResponse(FinancialGoalBase):
    """Response-Schema für finanzielles Ziel."""
    id: UUID
    space_id: UUID
    progress_percent: Decimal = Field(default=Decimal("0"), description="Fortschritt in %")
    monthly_savings_required: Optional[Decimal] = Field(None, description="Benötigte monatliche Sparrate")
    months_remaining: Optional[int] = Field(None, description="Verbleibende Monate")
    is_on_track: bool = Field(default=True, description="Auf Kurs?")
    projected_completion_date: Optional[date_type] = Field(None, description="Voraussichtliches Abschlussdatum")
    linked_assets: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FinancialGoalListResponse(BaseModel):
    """Liste von finanziellen Zielen."""
    goals: List[FinancialGoalResponse]
    total: int
    active_count: int = 0
    completed_count: int = 0
    on_track_count: int = 0


class FinancialGoalProgressUpdate(BaseModel):
    """Schema für Fortschritts-Update."""
    new_value: Decimal = Field(..., ge=0, description="Neuer aktueller Wert")


class FinancialGoalSummary(BaseModel):
    """Zusammenfassung aller Ziele."""
    total_goals: int = 0
    active_goals: int = 0
    completed_goals: int = 0
    on_track_count: int = 0
    total_target_value: Decimal = Decimal("0")
    total_current_value: Decimal = Decimal("0")


class PrivatPortfolioItem(BaseModel):
    """Ein Element in der Portfolio-Verteilung."""
    value: Decimal = Field(..., description="Wert der Anlage")
    percentage: Decimal = Field(..., description="Prozentualer Anteil")


class PrivatPortfolioBreakdownResponse(BaseModel):
    """Response-Schema für Portfolio-Verteilung."""
    breakdown: Dict[str, PrivatPortfolioItem] = Field(
        ..., description="Verteilung nach Anlagetyp"
    )
    total: Decimal = Field(..., description="Gesamtwert des Portfolios")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: DEADLINE (FRIST) SCHEMAS
# =============================================================================


class PrivatDeadlineBase(BaseModel):
    """Basis-Schema für Frist."""
    title: str = Field(..., min_length=1, max_length=200, description="Titel")
    description: Optional[str] = Field(None, max_length=2000, description="Beschreibung")
    deadline_type: PrivatDeadlineType = Field(
        PrivatDeadlineType.CUSTOM,
        description="Fristentyp"
    )
    due_date: date_type = Field(..., description="Fälligkeitsdatum")
    reminder_days: List[int] = Field(
        default=[7, 3, 1],
        description="Erinnerung X Tage vorher"
    )
    is_recurring: bool = Field(False, description="Wiederkehrend?")
    recurrence_interval: Optional[str] = Field(
        None,
        pattern="^(daily|weekly|monthly|quarterly|semi_annual|annual)$",
        description="Wiederholungsintervall"
    )
    priority: str = Field(
        "medium",
        pattern="^(low|medium|high|critical)$",
        description="Priorität"
    )


class PrivatDeadlineCreate(PrivatDeadlineBase):
    """Schema zum Erstellen einer Frist."""
    related_entity_type: Optional[str] = Field(
        None,
        max_length=50,
        description="Verknüpfter Entity-Typ"
    )
    related_entity_id: Optional[uuid.UUID] = Field(
        None,
        description="Verknüpfte Entity-ID"
    )


class PrivatDeadlineUpdate(BaseModel):
    """Schema zum Aktualisieren einer Frist."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    deadline_type: Optional[PrivatDeadlineType] = None
    due_date: Optional[date_type] = None
    reminder_days: Optional[List[int]] = None
    is_recurring: Optional[bool] = None
    recurrence_interval: Optional[str] = Field(
        None,
        pattern="^(daily|weekly|monthly|quarterly|semi_annual|annual)$"
    )
    priority: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    is_completed: Optional[bool] = None


class PrivatDeadlineResponse(PrivatDeadlineBase):
    """Response-Schema für Frist."""
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: uuid.UUID
    space_id: uuid.UUID
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[uuid.UUID] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PrivatDeadlineWithStatus(PrivatDeadlineResponse):
    """Frist mit Status-Informationen."""
    days_remaining: int = 0
    is_overdue: bool = False
    next_reminder: Optional[date_type] = None
    related_entity_name: Optional[str] = None


class PrivatDeadlineCalendarExport(BaseModel):
    """iCal Export Schema."""
    deadlines: List[PrivatDeadlineResponse]
    format: str = Field("ical", pattern="^(ical|json)$")


# =============================================================================
# PRIVAT-MODUL: EMERGENCY CONTACT (NOTFALLKONTAKT) SCHEMAS
# =============================================================================


class PrivatEmergencyContactBase(BaseModel):
    """Basis-Schema für Notfallkontakt."""
    first_name: str = Field(..., min_length=1, max_length=100, description="Vorname")
    last_name: str = Field(..., min_length=1, max_length=100, description="Nachname")
    email: EmailStr = Field(..., description="E-Mail")
    phone: Optional[str] = Field(None, max_length=50, description="Telefon")
    relationship: Optional[str] = Field(None, max_length=100, description="Beziehung")
    waiting_period_days: int = Field(
        30,
        ge=1,
        le=365,
        description="Wartezeit in Tagen"
    )
    notes: Optional[str] = Field(None, max_length=2000, description="Notizen")


class PrivatEmergencyContactCreate(PrivatEmergencyContactBase):
    """Schema zum Erstellen eines Notfallkontakts."""
    pass


class PrivatEmergencyContactUpdate(BaseModel):
    """Schema zum Aktualisieren eines Notfallkontakts."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=50)
    relationship: Optional[str] = Field(None, max_length=100)
    waiting_period_days: Optional[int] = Field(None, ge=1, le=365)
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=2000)


class PrivatEmergencyContactResponse(PrivatEmergencyContactBase):
    """Response-Schema für Notfallkontakt."""
    id: uuid.UUID
    space_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# PRIVAT-MODUL: EMERGENCY ACCESS REQUEST SCHEMAS
# =============================================================================


class PrivatEmergencyAccessRequestCreate(BaseModel):
    """Schema zum Erstellen einer Notfallzugriff-Anfrage."""
    space_id: uuid.UUID = Field(..., description="Space-ID")
    reason: str = Field(..., min_length=10, max_length=2000, description="Begruendung")


class PrivatEmergencyAccessRequestResponse(BaseModel):
    """Response-Schema für Notfallzugriff-Anfrage."""
    id: uuid.UUID
    space_id: uuid.UUID
    contact_id: uuid.UUID
    status: PrivatEmergencyAccessStatus
    reason: str
    requested_at: datetime
    waiting_until: datetime
    approved_at: Optional[datetime] = None
    denied_at: Optional[datetime] = None
    denied_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PrivatEmergencyAccessDenyRequest(BaseModel):
    """Schema zum Ablehnen einer Notfallzugriff-Anfrage."""
    reason: str = Field(..., min_length=1, max_length=1000, description="Ablehnungsgrund")


# =============================================================================
# PRIVAT-MODUL: DASHBOARD & STATISTICS SCHEMAS
# =============================================================================


class PrivatDashboardStats(BaseModel):
    """Dashboard-Statistiken."""
    total_documents: int = 0
    total_properties: int = 0
    total_vehicles: int = 0
    total_insurances: int = 0
    total_loans: int = 0
    total_investments: int = 0
    upcoming_deadlines: int = 0
    overdue_deadlines: int = 0
    total_property_value: Decimal = Decimal("0.00")
    total_loan_balance: Decimal = Decimal("0.00")
    total_investment_value: Decimal = Decimal("0.00")
    net_worth: Decimal = Decimal("0.00")


class PrivatDeadlineWidget(BaseModel):
    """Dashboard-Widget für Fristen."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
    today: List[PrivatDeadlineWithStatus] = []
    this_week: List[PrivatDeadlineWithStatus] = []
    this_month: List[PrivatDeadlineWithStatus] = []
    overdue: List[PrivatDeadlineWithStatus] = []


class PrivatFinancialSummary(BaseModel):
    """Finanzübersicht."""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
    net_worth: float = 0.0
    total_investments: float = 0.0
    total_loans: float = 0.0
    monthly_loan_payments: float = 0.0
    annual_insurance_cost: float = 0.0
    investment_return_percentage: float = 0.0


# =============================================================================
# PRIVAT-MODUL: LIST RESPONSE SCHEMAS
# =============================================================================


class PrivatSpaceListResponse(BaseModel):
    """Paginierte Liste von Privat-Spaces."""
    items: List[PrivatSpaceWithStats]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatDocumentListResponse(BaseModel):
    """Paginierte Liste von Privat-Dokumenten."""
    items: List[PrivatDocumentResponse]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatPropertyListResponse(BaseModel):
    """Paginierte Liste von Immobilien."""
    items: List[PrivatPropertyWithTenants]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatVehicleListResponse(BaseModel):
    """Paginierte Liste von Fahrzeugen."""
    items: List[PrivatVehicleWithLogs]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatInsuranceListResponse(BaseModel):
    """Paginierte Liste von Versicherungen."""
    items: List[PrivatInsuranceWithDeadlines]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatLoanListResponse(BaseModel):
    """Paginierte Liste von Krediten."""
    items: List[PrivatLoanWithStats]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatInvestmentListResponse(BaseModel):
    """Paginierte Liste von Geldanlagen."""
    items: List[PrivatInvestmentWithStats]
    total: int
    page: int
    page_size: int
    pages: int


class PrivatDeadlineListResponse(BaseModel):
    """Paginierte Liste von Fristen."""
    items: List[PrivatDeadlineWithStatus]
    total: int
    page: int
    page_size: int
    pages: int


# Forward references for recursive models
PrivatFolderTree.model_rebuild()
PrivatPropertyWithTenants.model_rebuild()
PrivatVehicleWithLogs.model_rebuild()


# =============================================================================
# VALIDATION QUEUE SYSTEM SCHEMAS
# Enterprise-Grade Validierungssystem für OCR-Ergebnisse und extrahierte Daten
# =============================================================================

class ValidationStatusEnum(str, Enum):
    """Validierungs-Status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class SampleSourceEnum(str, Enum):
    """Quelle der Stichproben-Auswahl."""
    AUTOMATIC = "automatic"
    RULE_BASED = "rule_based"
    MANUAL = "manual"
    LOW_CONFIDENCE = "low_confidence"


class ValidationRuleTypeEnum(str, Enum):
    """Typ der Validierungsregel."""
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    FIELD_PATTERN = "field_pattern"
    DOCUMENT_TYPE = "document_type"
    FIRST_OCCURRENCE = "first_occurrence"
    ERROR_PATTERN = "error_pattern"


class RejectionCategoryEnum(str, Enum):
    """Kategorie des Ablehnungsgrunds."""
    OCR_ERROR = "ocr_error"
    MISSING_DATA = "missing_data"
    WRONG_FORMAT = "wrong_format"
    UNREADABLE = "unreadable"
    DUPLICATE = "duplicate"
    WRONG_DOCUMENT_TYPE = "wrong_document_type"
    OTHER = "other"


# -----------------------------------------------------------------------------
# VALIDATION FIELD REVIEW SCHEMAS
# -----------------------------------------------------------------------------

class ValidationFieldBase(BaseModel):
    """Basis-Schema für Validierungsfelder."""
    field_key: str = Field(..., description="Technischer Feldname z.B. 'invoice_number'")
    field_label: str = Field(..., description="Deutscher Anzeigename")
    field_type: Optional[str] = Field(None, description="Feldtyp z.B. 'text', 'currency', 'date'")
    original_value: Optional[str] = None
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class ValidationFieldCreate(ValidationFieldBase):
    """Schema zum Erstellen eines Validierungsfelds."""
    bounding_box: Optional[Dict[str, Any]] = Field(
        None,
        description="PDF-Koordinaten: {x, y, width, height, page}"
    )
    ocr_backend: Optional[str] = None


class ValidationFieldUpdate(BaseModel):
    """Schema zum Aktualisieren eines Validierungsfelds."""
    corrected_value: Optional[str] = None
    validation_status: Optional[str] = None


class ValidationFieldResponse(ValidationFieldBase):
    """Antwort-Schema für ein Validierungsfeld."""
    id: UUID
    queue_item_id: UUID
    corrected_value: Optional[str] = None
    was_corrected: bool = False
    confidence_threshold: float = 0.85
    is_below_threshold: bool = False
    validation_status: str = "pending"
    validation_errors: List[Dict[str, Any]] = []
    umlaut_issues: List[Dict[str, Any]] = []
    format_issues: List[Dict[str, Any]] = []
    bounding_box: Optional[Dict[str, Any]] = None
    ocr_backend: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ValidationFieldValidateResult(BaseModel):
    """Ergebnis einer Feld-Validierung."""
    field_id: UUID
    field_key: str
    is_valid: bool
    errors: List[Dict[str, Any]] = []
    umlaut_issues: List[Dict[str, Any]] = []
    format_issues: List[Dict[str, Any]] = []
    suggested_correction: Optional[str] = None


# -----------------------------------------------------------------------------
# VALIDATION QUEUE ITEM SCHEMAS
# -----------------------------------------------------------------------------

class ValidationQueueItemBase(BaseModel):
    """Basis-Schema für Validierungs-Queue-Items."""
    priority: int = Field(5, ge=1, le=10, description="Priorität 1-10, 1 = hoechste")
    sample_source: SampleSourceEnum = SampleSourceEnum.AUTOMATIC


class ValidationQueueItemCreate(ValidationQueueItemBase):
    """Schema zum Erstellen eines Queue-Items."""
    document_id: UUID


class ValidationQueueItemUpdate(BaseModel):
    """Schema zum Aktualisieren eines Queue-Items."""
    priority: Optional[int] = Field(None, ge=1, le=10)
    validation_notes: Optional[str] = Field(None, max_length=2000)


class ValidationQueueItemAssign(BaseModel):
    """Schema für die Zuweisung eines Queue-Items."""
    editor_id: UUID
    priority: Optional[int] = Field(None, ge=1, le=10)


class ValidationQueueItemApprove(BaseModel):
    """Schema für die Genehmigung eines Queue-Items."""
    notes: Optional[str] = Field(None, max_length=2000)


class ValidationQueueItemReject(BaseModel):
    """Schema für die Ablehnung eines Queue-Items."""
    reason: str = Field(..., min_length=5, max_length=2000)
    category: RejectionCategoryEnum = RejectionCategoryEnum.OTHER


class ValidationQueueItemResponse(ValidationQueueItemBase):
    """Antwort-Schema für ein Queue-Item."""
    id: UUID
    document_id: UUID
    status: ValidationStatusEnum
    assigned_to_id: Optional[UUID] = None
    assigned_at: Optional[datetime] = None
    sample_rule_id: Optional[UUID] = None

    # Confidence Metriken
    overall_confidence: Optional[float] = None
    min_field_confidence: Optional[float] = None
    fields_below_threshold: int = 0
    total_fields: int = 0

    # Dokumentinfo
    document_type: Optional[str] = None
    document_name: Optional[str] = None

    # Validierungsergebnis
    validation_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejection_category: Optional[str] = None
    validated_by_id: Optional[UUID] = None
    validated_at: Optional[datetime] = None

    # Zeit-Tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    validation_duration_seconds: Optional[int] = None

    # Korrekturen
    corrections_made: int = 0
    umlaut_corrections: int = 0
    format_corrections: int = 0

    # Audit
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class ValidationQueueItemDetail(ValidationQueueItemResponse):
    """Detailiertes Queue-Item mit Feld-Reviews."""
    field_reviews: List[ValidationFieldResponse] = []
    assigned_to_name: Optional[str] = None
    validated_by_name: Optional[str] = None


class ValidationQueueListResponse(BaseModel):
    """Paginierte Liste von Queue-Items."""
    items: List[ValidationQueueItemResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


# -----------------------------------------------------------------------------
# VALIDATION RULE SCHEMAS
# -----------------------------------------------------------------------------

class ValidationRuleBase(BaseModel):
    """Basis-Schema für Validierungsregeln."""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    rule_type: ValidationRuleTypeEnum
    conditions: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(5, ge=1, le=10)
    is_active: bool = True


class ValidationRuleCreate(ValidationRuleBase):
    """Schema zum Erstellen einer Validierungsregel."""
    pass


class ValidationRuleUpdate(BaseModel):
    """Schema zum Aktualisieren einer Validierungsregel."""
    name: Optional[str] = Field(None, min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    conditions: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    is_active: Optional[bool] = None


class ValidationRuleResponse(ValidationRuleBase):
    """Antwort-Schema für eine Validierungsregel."""
    id: UUID
    is_system: bool = False
    documents_matched: int = 0
    last_triggered_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class ValidationRuleListResponse(BaseModel):
    """Liste von Validierungsregeln."""
    rules: List[ValidationRuleResponse]
    total: int


# -----------------------------------------------------------------------------
# VALIDATION SAMPLE CONFIG SCHEMAS
# -----------------------------------------------------------------------------

class ValidationSampleConfigBase(BaseModel):
    """Basis-Schema für Stichproben-Konfiguration."""
    name: str = Field("Standard", max_length=100)
    description: Optional[str] = None
    sample_percentage: int = Field(10, ge=0, le=100)
    stratify_by_document_type: bool = True
    stratify_by_ocr_backend: bool = False
    min_confidence_threshold: float = Field(0.85, ge=0.0, le=1.0)


class ValidationSampleConfigUpdate(BaseModel):
    """Schema zum Aktualisieren der Stichproben-Konfiguration."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    sample_percentage: Optional[int] = Field(None, ge=0, le=100)
    stratify_by_document_type: Optional[bool] = None
    stratify_by_ocr_backend: Optional[bool] = None
    min_confidence_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None


class ValidationSampleConfigResponse(ValidationSampleConfigBase):
    """Antwort-Schema für Stichproben-Konfiguration."""
    id: UUID
    is_active: bool
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    documents_sampled: int = 0
    last_sample_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------------------------------------------
# BATCH OPERATION SCHEMAS
# -----------------------------------------------------------------------------

class BatchApproveRequest(BaseModel):
    """Schema für Batch-Genehmigung."""
    item_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class BatchRejectRequest(BaseModel):
    """Schema für Batch-Ablehnung."""
    item_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    reason: str = Field(..., min_length=5, max_length=2000)
    category: RejectionCategoryEnum = RejectionCategoryEnum.OTHER


class BatchAssignRequest(BaseModel):
    """Schema für Batch-Zuweisung."""
    item_ids: List[UUID] = Field(..., min_length=1, max_length=100)
    editor_id: UUID


class ValidationBatchOperationResult(BaseModel):
    """Ergebnis einer Batch-Operation für Validation Queue."""
    success_count: int
    failed_count: int
    failed_items: List[Dict[str, Any]] = []
    message: str


# -----------------------------------------------------------------------------
# ANALYTICS SCHEMAS
# -----------------------------------------------------------------------------

class ValidationAnalyticsOverview(BaseModel):
    """Übersichts-Statistiken."""
    # Queue-Status
    pending_count: int = 0
    in_progress_count: int = 0
    approved_today: int = 0
    rejected_today: int = 0

    # Zeitraum
    validated_this_week: int = 0
    validated_this_month: int = 0

    # Durchschnitte
    avg_validation_time_seconds: Optional[int] = None
    avg_corrections_per_item: Optional[float] = None

    # Confidence
    avg_confidence_before: Optional[float] = None
    avg_confidence_after: Optional[float] = None
    confidence_improvement_percent: Optional[float] = None

    # Top-Fehler
    top_rejection_categories: List[Dict[str, Any]] = []


class EditorStats(BaseModel):
    """Statistiken pro Editor."""
    editor_id: UUID
    editor_name: str
    items_validated: int = 0
    items_approved: int = 0
    items_rejected: int = 0
    avg_validation_time_seconds: Optional[int] = None
    corrections_made: int = 0
    accuracy_rate: Optional[float] = None


class EditorStatsListResponse(BaseModel):
    """Liste von Editor-Statistiken."""
    editors: List[EditorStats]
    period_start: Optional[date_type] = None
    period_end: Optional[date_type] = None


class TrendDataPoint(BaseModel):
    """Datenpunkt für Trend-Charts."""
    date: date_type
    validated: int = 0
    approved: int = 0
    rejected: int = 0
    avg_time_seconds: Optional[int] = None


class TrendDataResponse(BaseModel):
    """Trend-Daten für Charts."""
    data_points: List[TrendDataPoint]
    group_by: str = "day"


class DocumentTypeStats(BaseModel):
    """Statistiken pro Dokumenttyp."""
    document_type: str
    total_validated: int = 0
    approved: int = 0
    rejected: int = 0
    avg_confidence: Optional[float] = None
    correction_rate: Optional[float] = None


class DocumentTypeStatsResponse(BaseModel):
    """Liste von Dokumenttyp-Statistiken."""
    document_types: List[DocumentTypeStats]


class ConfidenceDistribution(BaseModel):
    """Konfidenz-Verteilung."""
    ranges: List[Dict[str, Any]] = []
    avg_confidence: Optional[float] = None
    median_confidence: Optional[float] = None


# -----------------------------------------------------------------------------
# QUEUE FILTER SCHEMAS
# -----------------------------------------------------------------------------

class ValidationQueueFilters(BaseModel):
    """Filter-Parameter für Queue-Abfragen."""
    status: Optional[List[ValidationStatusEnum]] = None
    assigned_to_id: Optional[UUID] = None
    document_type: Optional[List[str]] = None
    sample_source: Optional[List[SampleSourceEnum]] = None
    confidence_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    priority_min: Optional[int] = Field(None, ge=1, le=10)
    priority_max: Optional[int] = Field(None, ge=1, le=10)
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    search: Optional[str] = Field(None, max_length=200)


class ValidationQueueSortOptions(str, Enum):
    """Sortieroptionen für Queue."""
    PRIORITY_ASC = "priority_asc"
    PRIORITY_DESC = "priority_desc"
    CONFIDENCE_ASC = "confidence_asc"
    CONFIDENCE_DESC = "confidence_desc"
    CREATED_ASC = "created_at_asc"
    CREATED_DESC = "created_at_desc"
    DOCUMENT_NAME = "document_name"


# -----------------------------------------------------------------------------
# QUEUE FOR VALIDATION (from Documents list)
# -----------------------------------------------------------------------------

class QueueDocumentForValidation(BaseModel):
    """Schema zum manuellen Hinzufuegen eines Dokuments zur Validierungsqueue."""
    document_id: UUID
    priority: int = Field(5, ge=1, le=10)
    notes: Optional[str] = Field(None, max_length=500)


class QueueDocumentResponse(BaseModel):
    """Antwort beim Hinzufuegen zur Queue."""
    queue_item_id: UUID
    document_id: UUID
    status: str
    message: str


# =============================================================================
# COLLABORATION: COMMENTS, ACTIVITIES, NOTIFICATIONS
# =============================================================================


class MentionSchema(BaseModel):
    """Mention in einem Kommentar.

    Validation:
    - userId muss gültige UUID sein
    - userName max 200 Zeichen (wie User.full_name), HTML-escaped
    - startIndex und endIndex müssen BEIDE oder KEINER angegeben sein
    - startIndex < endIndex wenn angegeben
    """
    userId: UUID = Field(..., description="UUID des erwahnten Users")
    userName: str = Field(..., min_length=1, max_length=200, description="Anzeigename")
    startIndex: Optional[int] = Field(None, ge=0, description="Start-Position im Text")
    endIndex: Optional[int] = Field(None, ge=0, description="End-Position im Text")

    @field_validator('userName')
    @classmethod
    def escape_username(cls, v: str) -> str:
        """Escape HTML-Zeichen im userName um XSS zu verhindern."""
        import html
        return html.escape(v)

    @model_validator(mode='after')
    def validate_indices(self) -> 'MentionSchema':
        """Prüft Index-Konsistenz:
        - Beide oder keiner
        - startIndex < endIndex
        """
        has_start = self.startIndex is not None
        has_end = self.endIndex is not None

        # Beide oder keiner
        if has_start != has_end:
            raise ValueError(
                "startIndex und endIndex müssen beide angegeben werden oder beide fehlen"
            )

        # Wenn beide angegeben: startIndex < endIndex
        if has_start and has_end:
            if self.startIndex >= self.endIndex:
                raise ValueError("startIndex muss kleiner als endIndex sein")

        return self


# Emoji Unicode Pattern - erlaubt Standard-Emojis und gängige Varianten
# Basiert auf Unicode Emoji Ranges: Emoji, Dingbats, Misc Symbols
EMOJI_PATTERN = r'^[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FA6F\U0001FAD0-\U0001FAE8]+$'


class ReactionSchema(BaseModel):
    """Reaktion auf einen Kommentar.

    Hinweis: userIds sind UUID-Strings für JSON-Kompatibilität mit Frontend.
    """
    emoji: str = Field(..., min_length=1, max_length=10, description="Unicode Emoji")
    count: int = Field(..., ge=0, description="Anzahl Reaktionen")
    userIds: List[str] = Field(..., description="Liste der User-UUIDs als Strings")


def _validate_content_not_whitespace(value: str) -> str:
    """Stellt sicher dass content nicht nur Whitespace ist."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("Inhalt darf nicht nur aus Leerzeichen bestehen")
    return value


class CommentCreate(BaseModel):
    """Kommentar erstellen.

    Validation:
    - content: Nicht leer, nicht nur Whitespace, max 10000 Zeichen
    - mentions: Optional, mit validen UUIDs
    - fieldReference: Optional, max 100 Zeichen, nur alphanumerisch + underscore
    """
    content: str = Field(..., min_length=1, max_length=10000)
    mentions: Optional[List[MentionSchema]] = None
    parentId: Optional[UUID] = None
    fieldReference: Optional[str] = Field(
        None,
        max_length=100,
        pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$',
        description="Feldname für Inline-Kommentare (z.B. 'invoice_number', 'total_amount')"
    )

    @field_validator('content')
    @classmethod
    def content_not_whitespace(cls, v: str) -> str:
        return _validate_content_not_whitespace(v)


class CommentUpdate(BaseModel):
    """Kommentar aktualisieren."""
    content: str = Field(..., min_length=1, max_length=10000)
    mentions: Optional[List[MentionSchema]] = None

    @field_validator('content')
    @classmethod
    def content_not_whitespace(cls, v: str) -> str:
        return _validate_content_not_whitespace(v)


class CommentResponse(BaseModel):
    """Kommentar-Antwort.

    Erweitert um:
    - companyId: Multi-Tenant Isolation
    - fieldReference: Feld-Referenz für Inline-Kommentare
    - deletedAt: Soft-Delete Timestamp
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    documentId: str
    userId: str
    userName: str
    userAvatar: Optional[str] = None
    companyId: Optional[str] = None  # Multi-Tenant (Migration 103)
    fieldReference: Optional[str] = None  # Inline-Kommentar Feld
    content: str
    mentions: List[MentionSchema] = []
    parentId: Optional[str] = None
    createdAt: str
    updatedAt: Optional[str] = None
    isEdited: bool
    deletedAt: Optional[str] = None  # Soft-Delete Timestamp
    reactions: List[ReactionSchema] = []


class CommentsListResponse(BaseModel):
    """Liste von Kommentaren."""
    comments: List[CommentResponse]
    total: int
    hasMore: bool


class CommentStatistics(BaseModel):
    """Statistiken für Dokument-Kommentare.

    Liefert aggregierte Metriken zu Kommentaren eines Dokuments.
    """
    totalComments: int = Field(..., ge=0, description="Gesamtanzahl der Kommentare")
    totalReplies: int = Field(..., ge=0, description="Anzahl der Antworten")
    uniqueCommenters: int = Field(..., ge=0, description="Anzahl verschiedener Kommentatoren")
    totalMentions: int = Field(..., ge=0, description="Gesamtanzahl der @Mentions")
    commentsLast7Days: int = Field(..., ge=0, description="Kommentare der letzten 7 Tage")
    commentsLast30Days: int = Field(..., ge=0, description="Kommentare der letzten 30 Tage")
    fieldComments: int = Field(..., ge=0, description="Anzahl der Feld-Kommentare")


class ActivityTypeEnum(str, Enum):
    """Aktivitaetstypen."""
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_VIEWED = "document_viewed"
    DOCUMENT_DOWNLOADED = "document_downloaded"
    COMMENT_ADDED = "comment_added"
    COMMENT_REPLIED = "comment_replied"
    STATUS_CHANGED = "status_changed"
    TAGS_CHANGED = "tags_changed"
    METADATA_UPDATED = "metadata_updated"
    DOCUMENT_SHARED = "document_shared"


class ActivityResponse(BaseModel):
    """Activity-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    documentId: str
    userId: str
    userName: str
    userAvatar: Optional[str] = None
    type: str
    description: str
    metadata: Optional[Dict[str, Any]] = None
    createdAt: str


class ActivitiesListResponse(BaseModel):
    """Liste von Activities."""
    activities: List[ActivityResponse]
    total: int
    hasMore: bool


class NotificationTypeEnum(str, Enum):
    """Benachrichtigungstypen."""
    MENTION = "mention"
    COMMENT_REPLY = "comment_reply"
    DOCUMENT_SHARED = "document_shared"
    TASK_ASSIGNED = "task_assigned"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"


class NotificationResponse(BaseModel):
    """Notification-Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    message: str
    documentId: Optional[str] = None
    documentName: Optional[str] = None
    fromUserId: str
    fromUserName: str
    fromUserAvatar: Optional[str] = None
    isRead: bool
    createdAt: str
    actionUrl: Optional[str] = Field(None, max_length=500)

    @field_validator('actionUrl')
    @classmethod
    def validate_action_url(cls, v: Optional[str]) -> Optional[str]:
        """Validiert actionUrl gegen XSS-Angriffe.

        Erlaubt:
        - Relative Pfade (/documents/123) - MUSS mit einzelnem / starten
        - HTTPS URLs
        - HTTP URLs (nur localhost für Dev)

        Blockiert:
        - javascript: URLs (inkl. Varianten mit Whitespace/Newlines)
        - data: URLs
        - vbscript: URLs
        - Protocol-relative URLs (//evil.com)
        - Andere gefaehrliche Protokolle
        - Steuerzeichen (Null-Bytes, Newlines, etc.)
        """
        if v is None:
            return None

        # KRITISCH: Entferne alle Whitespace und Steuerzeichen für Sicherheits-Check
        # Dies verhindert Bypasses wie "java\nscript:" oder "java\tscript:"
        import re
        v_normalized = re.sub(r'[\s\x00-\x1f\x7f-\x9f]', '', v.lower())

        # Blockiere gefaehrliche Protokolle (nach Normalisierung!)
        dangerous_protocols = [
            'javascript:', 'data:', 'vbscript:', 'file:',
            'blob:', 'about:', 'ws:', 'wss:', 'mhtml:',
            'livescript:', 'mocha:', 'view-source:'
        ]
        for protocol in dangerous_protocols:
            if v_normalized.startswith(protocol):
                raise ValueError(f"Ungültige URL: Protokoll '{protocol}' nicht erlaubt")

        # Blockiere Steuerzeichen im Original-String
        if re.search(r'[\x00-\x1f\x7f-\x9f]', v):
            raise ValueError("URL darf keine Steuerzeichen enthalten")

        # Blockiere Protocol-Relative URLs (//evil.com) - Open Redirect Gefahr!
        if v.startswith('//'):
            raise ValueError("Protocol-relative URLs (//) sind nicht erlaubt")

        # Relative URLs erlauben (müssen mit EINEM / starten, nicht //)
        if v.startswith('/') and not v.startswith('//'):
            # Zusätzlich: Blockiere Path-Traversal
            if '..' in v:
                raise ValueError("Path-Traversal (..) ist nicht erlaubt")
            return v

        # Absolute URLs: nur http/https erlauben
        v_lower = v.lower().strip()
        if v_lower.startswith('http://') or v_lower.startswith('https://'):
            return v

        # Alles andere blockieren
        raise ValueError("URL muss relativ (/) oder http(s):// sein")


class NotificationsListResponse(BaseModel):
    """Liste von Notifications."""
    notifications: List[NotificationResponse]
    unreadCount: int
    total: int


class ReactionAdd(BaseModel):
    """Reaktion hinzufuegen.

    Validation:
    - emoji muss ein gültiges Unicode Emoji sein
    - Akzeptiert Standard-Emojis (1F300-1F9FF), Dingbats (2600-27BF), etc.
    - Variation Selectors sind nur NACH einem echten Emoji erlaubt
    """
    emoji: str = Field(..., min_length=1, max_length=10)

    @field_validator('emoji')
    @classmethod
    def validate_emoji(cls, v: str) -> str:
        import re

        # Definiere echte Emoji-Ranges (OHNE Variation Selector!)
        emoji_base_ranges = (
            r'\U0001F300-\U0001F9FF'   # Misc Symbols & Pictographs, Emoticons, etc.
            r'\U00002600-\U000027BF'   # Dingbats, Misc Symbols
            r'\U0001FA00-\U0001FA6F'   # Chess, Extended-A
            r'\U0001FAD0-\U0001FAE8'   # Food, Face Symbols
            r'\U0001F600-\U0001F64F'   # Emoticons
            r'\U0001F680-\U0001F6FF'   # Transport & Map Symbols
            r'\U0001F1E0-\U0001F1FF'   # Flags
            r'\U00002702-\U000027B0'   # Dingbats
            r'\U0001FAF0-\U0001FAF8'   # Hand Gestures Extended
        )

        # Pattern: Mindestens 1 echtes Emoji, optional gefolgt von Variation Selectors
        # Variation Selector (FE0F) darf nur NACH einem echten Emoji kommen
        emoji_pattern = re.compile(
            r'^(?:[' + emoji_base_ranges + r']'      # Ein echtes Emoji
            r'[\U0000FE0F\U0000200D]?'               # Optional: Variation Selector oder ZWJ
            r')+'                                    # Erlaubt mehrere Emojis
            r'$'
        )

        if not emoji_pattern.match(v):
            raise ValueError("Ungültiges Emoji-Format")

        # Zusätzlich: Prüfe dass nicht NUR Variation Selectors/ZWJ
        base_chars = re.sub(r'[\U0000FE0F\U0000200D]', '', v)
        if not base_chars:
            raise ValueError("Emoji darf nicht nur aus Variation Selectors bestehen")

        return v


# =============================================================================
# TASK SCHEMAS - Aufgaben-Zuweisung für Collaboration
# =============================================================================


class TaskStatusEnum(str, Enum):
    """Status einer Aufgabe."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriorityEnum(str, Enum):
    """Priorität einer Aufgabe."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskTypeEnum(str, Enum):
    """Vordefinierte Aufgabentypen."""
    REVIEW = "review"       # Dokument prüfen
    APPROVE = "approve"     # Genehmigung erteilen
    PROCESS = "process"     # Verarbeiten
    CLASSIFY = "classify"   # Klassifizieren
    VERIFY = "verify"       # Verifizieren
    OTHER = "other"         # Sonstiges


class TaskCreate(BaseModel):
    """Aufgabe erstellen.

    Validation:
    - title: Pflichtfeld, 1-200 Zeichen
    - documentId: Muss valide UUID sein
    - assignedToId: Optional, muss valide UUID sein
    - dueDate: Optional, muss in der Zukunft liegen
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    documentId: uuid.UUID = Field(..., description="ID des zugehoerigen Dokuments")
    title: str = Field(..., min_length=1, max_length=200, description="Titel der Aufgabe")
    description: Optional[str] = Field(None, max_length=5000, description="Ausführliche Beschreibung")
    taskType: TaskTypeEnum = Field(TaskTypeEnum.REVIEW, description="Art der Aufgabe")
    assignedToId: Optional[uuid.UUID] = Field(None, description="ID des zugewiesenen Benutzers")
    priority: TaskPriorityEnum = Field(TaskPriorityEnum.NORMAL, description="Priorität")
    dueDate: Optional[datetime] = Field(None, description="Fälligkeitsdatum")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Zusätzliche Metadaten")

    @field_validator('title')
    @classmethod
    def title_not_whitespace(cls, v: str) -> str:
        """Titel darf nicht nur aus Whitespace bestehen."""
        if not v.strip():
            raise ValueError("Titel darf nicht leer sein")
        return v.strip()

    @field_validator('dueDate')
    @classmethod
    def due_date_in_future(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Due Date muss in der Zukunft liegen."""
        if v is not None:
            # Erlaube Daten die mindestens jetzt sind (nicht strikt in Zukunft)
            # Dies ermöglicht "heute fällig"
            from datetime import timezone
            now = datetime.now(timezone.utc) if v.tzinfo else datetime.utcnow()
            if v < now - timedelta(minutes=5):  # 5 Minuten Toleranz
                raise ValueError("Fälligkeitsdatum muss in der Zukunft liegen")
        return v


class TaskUpdate(BaseModel):
    """Aufgabe aktualisieren.

    Alle Felder sind optional - nur übergebene Felder werden aktualisiert.
    """
    model_config = ConfigDict(str_strip_whitespace=True)

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=5000)
    taskType: Optional[TaskTypeEnum] = None
    assignedToId: Optional[uuid.UUID] = None
    priority: Optional[TaskPriorityEnum] = None
    status: Optional[TaskStatusEnum] = None
    dueDate: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    @field_validator('title')
    @classmethod
    def title_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Titel darf nicht leer sein")
        return v.strip() if v else v


class TaskCompleteRequest(BaseModel):
    """Aufgabe als erledigt markieren."""
    completionNotes: Optional[str] = Field(None, max_length=2000, description="Notizen zur Erledigung")


class TaskAssignRequest(BaseModel):
    """Aufgabe einem Benutzer zuweisen."""
    assignedToId: uuid.UUID = Field(..., description="ID des neuen Bearbeiters")
    notifyAssignee: bool = Field(True, description="Benachrichtigung an neuen Bearbeiter senden")


class TaskResponse(BaseModel):
    """Aufgaben-Antwort mit allen Details."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    documentId: uuid.UUID
    documentName: Optional[str] = None
    companyId: uuid.UUID

    title: str
    description: Optional[str] = None
    taskType: str

    # Benutzer-Informationen
    createdById: Optional[uuid.UUID] = None
    createdByName: Optional[str] = None
    assignedToId: Optional[uuid.UUID] = None
    assignedToName: Optional[str] = None

    # Status
    status: str
    priority: str

    # Deadlines
    dueDate: Optional[datetime] = None
    isOverdue: bool = False
    reminderSent: bool = False
    escalated: bool = False
    escalatedAt: Optional[datetime] = None
    escalatedToId: Optional[uuid.UUID] = None
    escalatedToName: Optional[str] = None

    # Completion
    completedAt: Optional[datetime] = None
    completedById: Optional[uuid.UUID] = None
    completedByName: Optional[str] = None
    completionNotes: Optional[str] = None

    # Metadaten
    metadata: Optional[Dict[str, Any]] = None
    createdAt: datetime
    updatedAt: datetime


class TasksListResponse(BaseModel):
    """Liste von Aufgaben mit Pagination."""
    tasks: List[TaskResponse]
    total: int
    hasMore: bool


class TaskStatistics(BaseModel):
    """Statistiken über Aufgaben."""
    totalTasks: int = 0
    openTasks: int = 0
    inProgressTasks: int = 0
    completedTasks: int = 0
    overdueTasks: int = 0
    averageCompletionTimeHours: Optional[float] = None


# =============================================================================
# NOTIFICATION PREFERENCE SCHEMAS
# =============================================================================


class NotificationChannelEnum(str, Enum):
    """Verfügbare Benachrichtigungskanaele."""
    IN_APP = "in_app"
    EMAIL = "email"
    WEBSOCKET = "websocket"
    SLACK = "slack"
    SMS = "sms"


class DigestFrequencyEnum(str, Enum):
    """Häufigkeit für Email-Digest."""
    IMMEDIATE = "immediate"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    DISABLED = "disabled"


class NotificationPreferenceCreate(BaseModel):
    """Benachrichtigungs-Praeferenz erstellen."""
    notificationType: str = Field(..., min_length=1, max_length=50)
    enabledChannels: Dict[str, bool] = Field(
        default_factory=lambda: {
            "in_app": True,
            "email": True,
            "websocket": True,
            "slack": False,
            "sms": False
        }
    )
    digestFrequency: DigestFrequencyEnum = DigestFrequencyEnum.IMMEDIATE


class NotificationPreferenceUpdate(BaseModel):
    """Benachrichtigungs-Praeferenz aktualisieren."""
    enabledChannels: Optional[Dict[str, bool]] = None
    digestFrequency: Optional[DigestFrequencyEnum] = None


class NotificationPreferenceResponse(BaseModel):
    """Benachrichtigungs-Praeferenz Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    userId: uuid.UUID
    notificationType: str
    enabledChannels: Dict[str, bool]
    digestFrequency: str
    createdAt: datetime
    updatedAt: datetime


class NotificationPreferencesListResponse(BaseModel):
    """Liste aller Praeferenzen eines Benutzers."""
    preferences: List[NotificationPreferenceResponse]


class NotificationPreferencesBulkUpdate(BaseModel):
    """Mehrere Praeferenzen gleichzeitig aktualisieren."""
    preferences: List[NotificationPreferenceCreate]


# =============================================================================
# ESCALATION RULE SCHEMAS
# =============================================================================


class EscalationRuleCreate(BaseModel):
    """Eskalationsregel erstellen."""
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    taskType: Optional[TaskTypeEnum] = Field(None, description="Gilt für diesen Aufgabentyp (null = alle)")
    priority: Optional[TaskPriorityEnum] = Field(None, description="Gilt für diese Priorität (null = alle)")
    timeoutHours: int = Field(24, ge=1, le=720, description="Stunden bis zur Eskalation")
    escalateToUserId: Optional[uuid.UUID] = Field(None, description="Eskalation an bestimmten Benutzer")
    escalateToRole: Optional[str] = Field(None, max_length=50, description="Eskalation an Rolle (z.B. 'manager')")
    notifyOriginalAssignee: bool = Field(True)
    notifyEscalationTarget: bool = Field(True)
    notifyTaskCreator: bool = Field(False)
    isActive: bool = Field(True)
    rulePriority: int = Field(100, ge=1, le=1000, description="Niedrigere Zahl = höhere Priorität")


class EscalationRuleUpdate(BaseModel):
    """Eskalationsregel aktualisieren."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    taskType: Optional[TaskTypeEnum] = None
    priority: Optional[TaskPriorityEnum] = None
    timeoutHours: Optional[int] = Field(None, ge=1, le=720)
    escalateToUserId: Optional[uuid.UUID] = None
    escalateToRole: Optional[str] = Field(None, max_length=50)
    notifyOriginalAssignee: Optional[bool] = None
    notifyEscalationTarget: Optional[bool] = None
    notifyTaskCreator: Optional[bool] = None
    isActive: Optional[bool] = None
    rulePriority: Optional[int] = Field(None, ge=1, le=1000)


class EscalationRuleResponse(BaseModel):
    """Eskalationsregel Antwort."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    companyId: uuid.UUID
    name: str
    description: Optional[str] = None
    taskType: Optional[str] = None
    priority: Optional[str] = None
    timeoutHours: int
    escalateToUserId: Optional[uuid.UUID] = None
    escalateToUserName: Optional[str] = None
    escalateToRole: Optional[str] = None
    notifyOriginalAssignee: bool
    notifyEscalationTarget: bool
    notifyTaskCreator: bool
    isActive: bool
    rulePriority: int
    createdAt: datetime
    updatedAt: datetime


class EscalationRulesListResponse(BaseModel):
    """Liste von Eskalationsregeln."""
    rules: List[EscalationRuleResponse]
    total: int


# =============================================================================
# RISK SCORING SCHEMAS
# Risiko-Bewertung von Geschäftspartnern
# =============================================================================

class RiskLevel(str, Enum):
    """Risiko-Stufe für Geschäftspartner."""
    NIEDRIG = "niedrig"     # 0-30
    MITTEL = "mittel"       # 31-60
    ERHOEHT = "erhöht"     # 61-80
    HOCH = "hoch"           # 81-100
    UNBEKANNT = "unbekannt" # Keine Daten


class RiskFactorsResponse(BaseModel):
    """Detaillierte Risikofaktoren eines Geschäftspartners."""

    # Zahlungsverzögerung
    payment_delay_days: float = Field(0.0, ge=0, description="Durchschnittliche Zahlungsverzögerung in Tagen")

    # Ausfallrate
    default_rate: float = Field(0.0, ge=0, le=100, description="Prozent ausgefallener Zahlungen")

    # Rechnungsvolumen
    invoice_volume: float = Field(0.0, ge=0, description="Gesamtes Rechnungsvolumen in EUR")

    # Dokumentenfrequenz
    document_frequency: float = Field(0.0, ge=0, description="Dokumente pro Monat")

    # Beziehungsdauer
    relationship_months: float = Field(0.0, ge=0, description="Beziehungsdauer in Monaten")

    # Rechnungsstatistiken
    total_invoices: int = Field(0, ge=0, description="Gesamtanzahl Rechnungen")
    paid_invoices: int = Field(0, ge=0, description="Bezahlte Rechnungen")
    overdue_invoices: int = Field(0, ge=0, description="Überfällige Rechnungen")
    open_invoices: int = Field(0, ge=0, description="Offene Rechnungen")


class EntityRiskResponse(BaseModel):
    """Vollständige Risiko-Bewertung eines Geschäftspartners."""
    model_config = ConfigDict(from_attributes=True)

    entity_id: uuid.UUID
    entity_name: str

    # Scores
    risk_score: Optional[float] = Field(
        None, ge=0, le=100,
        description="Gesamt-Risiko-Score 0-100 (100 = hoechstes Risiko)"
    )
    payment_behavior_score: Optional[float] = Field(
        None, ge=0, le=100,
        description="Zahlungsverhalten-Score 0-100 (100 = bester Zahler)"
    )

    # Detaillierte Faktoren
    risk_factors: RiskFactorsResponse

    # Metadaten
    calculated_at: Optional[datetime] = None
    risk_level: RiskLevel = Field(
        RiskLevel.UNBEKANNT,
        description="Kategorisiertes Risiko-Level"
    )

    @classmethod
    def from_entity(cls, entity: "BusinessEntity", factors: Optional[Dict[str, Any]] = None) -> "EntityRiskResponse":
        """Erstellt EntityRiskResponse aus BusinessEntity."""
        risk_factors = RiskFactorsResponse(**(factors or entity.risk_factors or {}))

        # Risk Level bestimmen
        risk_level = RiskLevel.UNBEKANNT
        if entity.risk_score is not None:
            if entity.risk_score <= 30:
                risk_level = RiskLevel.NIEDRIG
            elif entity.risk_score <= 60:
                risk_level = RiskLevel.MITTEL
            elif entity.risk_score <= 80:
                risk_level = RiskLevel.ERHOEHT
            else:
                risk_level = RiskLevel.HOCH

        return cls(
            entity_id=entity.id,
            entity_name=entity.name,
            risk_score=entity.risk_score,
            payment_behavior_score=entity.payment_behavior_score,
            risk_factors=risk_factors,
            calculated_at=entity.risk_calculated_at,
            risk_level=risk_level,
        )


class EntityRiskCalculateRequest(BaseModel):
    """Anfrage zur Neuberechnung des Risiko-Scores."""
    force_recalculate: bool = Field(
        False,
        description="Erzwingt Neuberechnung auch wenn kürzlich berechnet"
    )


class EntityRiskBatchResponse(BaseModel):
    """Antwort auf Batch-Risiko-Berechnung."""
    updated_count: int = Field(0, description="Anzahl aktualisierter Entities")
    failed_count: int = Field(0, description="Anzahl fehlgeschlagener Updates")
    entity_type: Optional[str] = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int


# NOTE: InvoiceTracking Schemas sind definiert bei:
# - InvoiceStatusEnum (ca. Zeile 3015)
# - InvoiceTrackingBase, InvoiceTrackingCreate, InvoiceTrackingUpdate, InvoiceTrackingResponse (ca. Zeile 3026-3070)
# - InvoiceStatisticsResponse (ca. Zeile 3165)
# Diese duplizierten Definitionen wurden entfernt um Konsistenz zu gewährleisten.


# ==================== Business Contact Schemas ====================


class ContactTypeEnum(str, Enum):
    """Kontakttyp Enum für API."""
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    PARTNER = "partner"
    PROSPECT = "prospect"
    OTHER = "other"


class ContactRoleEnum(str, Enum):
    """Kontaktrolle bei Dokumenten."""
    SENDER = "sender"
    RECIPIENT = "recipient"
    MENTIONED = "mentioned"
    CC = "cc"


class ContactPersonSchema(BaseModel):
    """Ansprechpartner eines Kontakts."""
    name: str = Field(..., min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    department: Optional[str] = Field(None, max_length=100)
    is_primary: bool = False


class BusinessContactBase(BaseModel):
    """Basis-Schema für BusinessContact."""
    name: str = Field(..., min_length=1, max_length=255, description="Firmenname")
    contact_type: Optional[ContactTypeEnum] = ContactTypeEnum.CUSTOMER
    company_form: Optional[str] = Field(None, max_length=50, description="Rechtsform (GmbH, AG, etc.)")

    # Tax identifiers
    tax_id: Optional[str] = Field(None, max_length=30, description="Steuernummer")
    vat_id: Optional[str] = Field(None, max_length=20, description="USt-IdNr")
    registration_number: Optional[str] = Field(None, max_length=50, description="HRB")

    # Business numbers
    customer_number: Optional[str] = Field(None, max_length=50, description="Kundennummer")
    supplier_number: Optional[str] = Field(None, max_length=50, description="Lieferantennummer")

    # Address
    street: Optional[str] = Field(None, max_length=255)
    house_number: Optional[str] = Field(None, max_length=20)
    address_addition: Optional[str] = Field(None, max_length=100, description="c/o, Gebaeude, etc.")
    postal_code: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field("Deutschland", max_length=100)

    # Contact details
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    fax: Optional[str] = Field(None, max_length=30)
    website: Optional[str] = Field(None, max_length=255)

    # Banking
    bank_name: Optional[str] = Field(None, max_length=100)
    iban: Optional[str] = Field(None, max_length=34)
    bic: Optional[str] = Field(None, max_length=11)

    # Additional data
    contact_persons: Optional[List[ContactPersonSchema]] = None
    parent_company_id: Optional[UUID] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    is_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class BusinessContactCreate(BusinessContactBase):
    """Schema zum Erstellen eines Kontakts."""
    pass


class BusinessContactUpdate(BaseModel):
    """Schema zum Aktualisieren eines Kontakts."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    contact_type: Optional[ContactTypeEnum] = None
    company_form: Optional[str] = Field(None, max_length=50)
    tax_id: Optional[str] = Field(None, max_length=30)
    vat_id: Optional[str] = Field(None, max_length=20)
    registration_number: Optional[str] = Field(None, max_length=50)
    customer_number: Optional[str] = Field(None, max_length=50)
    supplier_number: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=255)
    house_number: Optional[str] = Field(None, max_length=20)
    address_addition: Optional[str] = Field(None, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=10)
    city: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=30)
    fax: Optional[str] = Field(None, max_length=30)
    website: Optional[str] = Field(None, max_length=255)
    bank_name: Optional[str] = Field(None, max_length=100)
    iban: Optional[str] = Field(None, max_length=34)
    bic: Optional[str] = Field(None, max_length=11)
    contact_persons: Optional[List[ContactPersonSchema]] = None
    parent_company_id: Optional[UUID] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class BusinessContactResponse(BaseModel):
    """Vollständige Kontakt-Antwort."""
    id: UUID
    name: str
    name_normalized: Optional[str] = None
    contact_type: ContactTypeEnum
    company_form: Optional[str] = None

    # Tax identifiers
    tax_id: Optional[str] = None
    vat_id: Optional[str] = None
    registration_number: Optional[str] = None

    # Business numbers
    customer_number: Optional[str] = None
    supplier_number: Optional[str] = None

    # Address
    street: Optional[str] = None
    house_number: Optional[str] = None
    address_addition: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None

    # Contact details
    email: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    website: Optional[str] = None

    # Banking
    bank_name: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None

    # Additional data
    contact_persons: List[Dict[str, Any]] = []
    parent_company_id: Optional[UUID] = None
    notes: Optional[str] = None
    tags: List[str] = []
    custom_fields: Dict[str, Any] = {}

    # Ownership
    owner_id: UUID
    source: str = "manual"
    auto_detected: bool = False
    auto_detection_confidence: Optional[float] = None
    first_document_id: Optional[UUID] = None

    # Status
    is_active: bool = True
    is_verified: bool = False
    merged_into_id: Optional[UUID] = None

    # Statistics
    document_count: int = 0
    total_invoice_amount: float = 0.0
    last_document_date: Optional[datetime] = None

    # Audit
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Computed
    formatted_address: Optional[str] = None
    display_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class BusinessContactListFilters(BaseModel):
    """Filter für Kontaktliste."""
    search: Optional[str] = None
    contact_type: Optional[ContactTypeEnum] = None
    is_verified: Optional[bool] = None
    is_active: Optional[bool] = True
    has_documents: Optional[bool] = None
    city: Optional[str] = None
    postal_code_prefix: Optional[str] = None
    tags: Optional[List[str]] = None
    min_invoice_amount: Optional[float] = None
    auto_detected: Optional[bool] = None


class BusinessContactListResponse(BaseModel):
    """Paginierte Kontaktliste."""
    contacts: List[BusinessContactResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ContactDocumentInfo(BaseModel):
    """Dokument-Info für Kontaktansicht."""
    id: UUID
    filename: str
    document_type: Optional[str] = None
    role: ContactRoleEnum
    confidence: Optional[float] = None
    created_at: datetime


class ContactDocumentsResponse(BaseModel):
    """Dokumente eines Kontakts."""
    contact_id: UUID
    contact_name: str
    documents: List[ContactDocumentInfo]
    total: int


class MergeContactsRequest(BaseModel):
    """Anfrage zum Zusammenführen von Kontakten."""
    source_id: UUID = Field(..., description="Kontakt der zusammengeführt wird")
    target_id: UUID = Field(..., description="Zielkontakt der uebrig bleibt")


class MergeContactsResponse(BaseModel):
    """Antwort auf Zusammenführung."""
    success: bool
    target_contact: BusinessContactResponse
    merged_document_links: int
    message: str


class DetectContactsRequest(BaseModel):
    """Anfrage zur Kontakterkennung."""
    document_id: UUID = Field(..., description="Dokument zur Analyse")
    auto_create: bool = Field(False, description="Kontakte automatisch erstellen")


class DetectedContactInfo(BaseModel):
    """Erkannter Kontakt aus Dokument."""
    existing_contact_id: Optional[UUID] = None
    suggested_name: str
    suggested_type: ContactTypeEnum
    confidence: float
    match_reason: str
    extracted_data: Dict[str, Any] = {}


class DetectContactsResponse(BaseModel):
    """Antwort auf Kontakterkennung."""
    document_id: UUID
    detected_contacts: List[Dict[str, Any]]
    new_contacts_created: int
    existing_contacts_matched: int


class ContactStatsResponse(BaseModel):
    """Statistiken zu Kontakten."""
    total_contacts: int
    by_type: Dict[str, int]
    verified_count: int
    auto_detected_count: int
    top_customers_by_invoice: List[Dict[str, Any]]
    recent_contacts: List[BusinessContactResponse]
    avg_documents_per_contact: float
