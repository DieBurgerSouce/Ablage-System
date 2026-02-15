# -*- coding: utf-8 -*-
"""
Core Type Definitions for Ablage-System.

Provides TypedDicts and type aliases to replace Any types throughout the codebase.
This improves type safety and enables better static analysis.

Phase 1 der Enterprise Quality Initiative (Januar 2026).
"""

from datetime import datetime, date
from decimal import Decimal
from typing import (
    TYPE_CHECKING,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Union,
)
from typing_extensions import TypedDict  # Required for Pydantic v2 on Python < 3.12
from uuid import UUID

# =============================================================================
# Logging Types (logging_config.py)
# =============================================================================


class SystemMetricsDict(TypedDict, total=False):
    """System metrics for performance logging."""

    cpu_prozent: float
    speicher_prozent: float
    festplatte_prozent: float


class GPUMetricsDict(TypedDict, total=False):
    """GPU metrics for logging."""

    verfuegbar: bool
    speicher_verwendet: float
    speicher_gesamt: float


class RequestContextDict(TypedDict, total=False):
    """HTTP request context for logging."""

    methode: str
    pfad: str
    ip: Optional[str]
    user_agent: str


class LogEventDict(TypedDict, total=False):
    """Structured log event dictionary.

    This represents the full structure of a log event as processed
    by structlog processors.
    """

    # Core log fields
    event: str
    level: str
    stufe: str  # German log level
    timestamp: str
    zeitstempel: str
    logger: str

    # Correlation
    korrelations_id: Optional[str]

    # Context
    anfrage: RequestContextDict
    system: SystemMetricsDict
    gpu: GPUMetricsDict

    # Callsite info
    filename: str
    func_name: str
    lineno: int

    # Error info
    exc_info: Optional[str]
    stack_info: Optional[str]


class WrappedLoggerProtocol(Protocol):
    """Protocol for structlog wrapped loggers."""

    def debug(self, event: str, **kwargs: object) -> None: ...
    def info(self, event: str, **kwargs: object) -> None: ...
    def warning(self, event: str, **kwargs: object) -> None: ...
    def error(self, event: str, **kwargs: object) -> None: ...
    def critical(self, event: str, **kwargs: object) -> None: ...
    def exception(self, event: str, **kwargs: object) -> None: ...
    def bind(self, **kwargs: object) -> "WrappedLoggerProtocol": ...
    def unbind(self, *keys: str) -> "WrappedLoggerProtocol": ...
    def new(self, **kwargs: object) -> "WrappedLoggerProtocol": ...


# =============================================================================
# OCR Task Types (workers/tasks/ocr_tasks.py)
# =============================================================================


class OCRExtractionResult(TypedDict, total=False):
    """Result of OCR text extraction."""

    text: str
    confidence: float
    language: str
    pages: int
    processing_time_ms: int


class OCRExtractedData(TypedDict, total=False):
    """Extracted structured data from OCR."""

    invoice_number: Optional[str]
    invoice_date: Optional[str]
    supplier_name: Optional[str]
    creditor_name: Optional[str]
    total_amount: Optional[str]
    net_amount: Optional[str]
    vat_amount: Optional[str]
    vat_rate: Optional[str]
    currency: Optional[str]
    iban: Optional[str]
    bic: Optional[str]


class OCRTaskResult(TypedDict, total=False):
    """Result of an OCR processing task.

    Matches the actual return structure from process_document_task.
    All fields are optional (total=False) since different code paths
    return different subsets of fields.

    On error, process_document_task raises exceptions (OCRProcessingError,
    GPUOutOfMemoryError, OCRBackendTimeoutError) rather than returning
    an error dict.
    """

    success: bool
    document_id: str
    text: str
    confidence: float
    backend_used: str
    processing_time_ms: float
    word_count: int
    german_validation: Optional[Dict[str, object]]
    completed_at: str
    embedding_task_id: Optional[str]
    extraction_task_id: Optional[str]
    rag_chunking_task_id: Optional[str]
    fallback_reason: Optional[str]
    skipped_reason: Optional[str]
    # Error fields (used in batch error results)
    error: Optional[str]
    error_type: Optional[str]


class OCRBatchResult(TypedDict, total=False):
    """Result of a batch OCR processing task.

    Matches the actual return structure from batch_process_task.
    """

    success: bool
    batch_job_id: Optional[str]
    total_documents: int
    successful: int
    failed: int
    gpu_oom_failures: int
    results: List[OCRTaskResult]
    processing_time_seconds: float
    completed_at: str
    gpu_recovery_stats: Optional[Dict[str, object]]


# =============================================================================
# GPU Lock Types (workers/celery_app.py)
# =============================================================================


class GPULockHealthDict(TypedDict):
    """Health status of GPU lock system."""

    lock_available: bool
    current_holder: Optional[str]
    queue_depth: int
    last_release_time: Optional[str]
    vram_usage_gb: Optional[float]
    vram_total_gb: Optional[float]
    vram_percentage: Optional[float]


class GPUTaskStatus(TypedDict, total=False):
    """Status of a GPU-bound task."""

    task_id: str
    status: str
    backend: Optional[str]
    vram_reserved_gb: Optional[float]
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]


# =============================================================================
# Business Rules Types (services/rules/business_rules_engine.py)
# =============================================================================

# Type alias for nested values from rule context
NestedValue = Union[str, int, float, bool, list, dict, Decimal, datetime, date, None]


class RuleConditionDict(TypedDict, total=False):
    """Dictionary representation of a rule condition."""

    field: str
    op: str
    value: NestedValue
    case_sensitive: bool
    negate: bool


class CompositeConditionDict(TypedDict, total=False):
    """Dictionary representation of composite conditions."""

    and_: List["RuleConditionDict | CompositeConditionDict"]
    or_: List["RuleConditionDict | CompositeConditionDict"]
    not_: "RuleConditionDict | CompositeConditionDict"


class RuleActionDict(TypedDict, total=False):
    """Dictionary representation of a rule action."""

    type: str
    params: Dict[str, NestedValue]


class RuleContextDict(TypedDict, total=False):
    """Context passed to rule evaluation.

    This contains document data and additional context for rule matching.
    """

    # Document fields
    id: str
    filename: str
    document_type: Optional[str]
    status: Optional[str]
    tags: List[str]
    created_at: Optional[str]
    company_id: str

    # Extracted data fields (common)
    amount: Optional[Decimal]
    total_amount: Optional[Decimal]
    net_amount: Optional[Decimal]
    vat_amount: Optional[Decimal]
    invoice_number: Optional[str]
    invoice_date: Optional[str]
    supplier_name: Optional[str]
    confidence: Optional[float]

    # Entity linking
    entity_id: Optional[str]
    entity_type: Optional[str]
    entity_risk_score: Optional[int]

    # Metadata
    source: Optional[str]
    ocr_backend: Optional[str]


class ConditionEvaluationDetails(TypedDict, total=False):
    """Details from evaluating a single condition."""

    field: str
    operator: str
    expected: NestedValue
    actual: NestedValue
    matched: bool
    error: Optional[str]


class CompositeEvaluationDetails(TypedDict):
    """Details from evaluating a composite condition."""

    type: str
    logic: str
    sub_conditions: List["ConditionEvaluationDetails | CompositeEvaluationDetails"]
    matched: bool


# =============================================================================
# Entity Search Types (services/entity_search_service.py)
# =============================================================================


class LexwareCompanyData(TypedDict, total=False):
    """Lexware data for a single company (folie/messer)."""

    kd_nr: Optional[str]
    lief_nr: Optional[str]
    matchcode: Optional[str]
    debitor_konto: Optional[str]
    kreditor_konto: Optional[str]


class LexwareIdsDict(TypedDict, total=False):
    """Lexware IDs dictionary structure."""

    folie: LexwareCompanyData
    messer: LexwareCompanyData


class EntitySearchResult(TypedDict):
    """Result of an entity search operation."""

    entity_id: str
    entity_name: str
    entity_type: str
    confidence: float
    match_type: str
    company_presence: List[str]


# =============================================================================
# Parsing Types (accounting services)
# =============================================================================


class ParsedAmountResult(TypedDict, total=False):
    """Result of parsing an amount string."""

    value: Decimal
    currency: Optional[str]
    original: str
    confidence: float


class ParsedDateResult(TypedDict, total=False):
    """Result of parsing a date string."""

    value: date
    format_detected: str
    original: str
    confidence: float


class VATParseResult(TypedDict, total=False):
    """Result of parsing VAT rate."""

    rate: str  # "0", "7", "19"
    original: str
    detection_method: str  # "explicit", "calculated", "default"


# =============================================================================
# API Response Types
# =============================================================================


class ErrorResponseDict(TypedDict):
    """Standard error response structure."""

    error_code: str
    message: str
    user_message_de: str
    details: Dict[str, object]


class PaginationDict(TypedDict):
    """Pagination metadata for list responses."""

    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool


class PaginatedResponseDict(TypedDict):
    """Generic paginated response structure."""

    items: List[Dict[str, object]]
    pagination: PaginationDict


# =============================================================================
# Type Aliases for Common Patterns
# =============================================================================

# JSON-serializable types
# Note: Recursive type aliases cause RecursionError with Pydantic v2 + Python 3.12.
# Use non-recursive definition for Pydantic compatibility.
JSONValue = Union[str, int, float, bool, None, List[object], Dict[str, object]]
JSONDict = Dict[str, JSONValue]

# Callback types
AsyncCallback = Callable[..., "Coroutine[object, object, object]"]
SyncCallback = Callable[..., object]

# ID types
DocumentID = Union[UUID, str]
EntityID = Union[UUID, str]
UserID = Union[UUID, str]
CompanyID = Union[UUID, str]

# Import Coroutine only for type checking to avoid circular imports
if TYPE_CHECKING:
    from collections.abc import Coroutine


# =============================================================================
# Export all types
# =============================================================================

__all__ = [
    # Logging
    "SystemMetricsDict",
    "GPUMetricsDict",
    "RequestContextDict",
    "LogEventDict",
    "WrappedLoggerProtocol",
    # OCR
    "OCRExtractionResult",
    "OCRExtractedData",
    "OCRTaskResult",
    "OCRBatchResult",
    # GPU
    "GPULockHealthDict",
    "GPUTaskStatus",
    # Rules
    "NestedValue",
    "RuleConditionDict",
    "CompositeConditionDict",
    "RuleActionDict",
    "RuleContextDict",
    "ConditionEvaluationDetails",
    "CompositeEvaluationDetails",
    # Entity Search
    "LexwareCompanyData",
    "LexwareIdsDict",
    "EntitySearchResult",
    # Parsing
    "ParsedAmountResult",
    "ParsedDateResult",
    "VATParseResult",
    # API
    "ErrorResponseDict",
    "PaginationDict",
    "PaginatedResponseDict",
    # Aliases
    "JSONValue",
    "JSONDict",
    "AsyncCallback",
    "SyncCallback",
    "DocumentID",
    "EntityID",
    "UserID",
    "CompanyID",
]
