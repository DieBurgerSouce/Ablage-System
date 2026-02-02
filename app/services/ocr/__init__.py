"""OCR Services Package."""

from app.services.ocr.self_learning_service import (
    SelfLearningOCRService,
    LearningMode,
    ModelVersion,
    CorrectionFeedback,
    ModelPerformanceMetrics,
    ABTestConfig,
    ABTestResult,
    get_self_learning_service,
    CONFIDENCE_ADJUSTMENTS_KEY,
)
from app.services.ocr.table_extraction_service import (
    TableExtractionService,
    TableExportFormat,
    TableType,
    CellDataType,
    EnhancedTableCell,
    TableColumn,
    ExtractedTable,
    TableExtractionResult,
    get_table_extraction_service,
    parse_german_decimal,
    detect_cell_data_type,
    detect_table_type,
)
from app.services.ocr.cross_backend_consistency_service import (
    CrossBackendConsistencyService,
    ConsistencyLevel,
    ReviewPriority,
    RegionType,
    InconsistentRegion,
    ConsistencyReport,
    ConsistencyConfig,
    get_cross_backend_consistency_service,
    check_backend_consistency,
    calculate_backend_agreement,
)
from app.services.ocr.feedback_service import (
    EnhancedOCRFeedbackService,
    CorrectionFeedback as FeedbackCorrectionFeedback,
    CorrectionResult,
    QueueItem,
    LeaderboardEntry,
    UserStats,
    BatchCorrectionResult,
    LeaderboardPeriod,
    QueuePriority,
    CorrectionStatus,
    get_feedback_service,
    POINTS_CONFIG,
    LEADERBOARD_CONFIG,
    LOW_CONFIDENCE_THRESHOLD,
)

# Re-export quick_ocr_preview from the ocr.py module (legacy)
# Note: app/services/ocr.py coexists with app/services/ocr/ package
# This import resolves the naming conflict by explicitly exporting the function
import importlib.util
import os

_ocr_module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ocr.py")
_spec = importlib.util.spec_from_file_location("ocr_module", _ocr_module_path)
_ocr_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ocr_module)
quick_ocr_preview = _ocr_module.quick_ocr_preview

__all__ = [
    # Self-Learning Service
    "SelfLearningOCRService",
    "LearningMode",
    "ModelVersion",
    "CorrectionFeedback",
    "ModelPerformanceMetrics",
    "ABTestConfig",
    "ABTestResult",
    "get_self_learning_service",
    "CONFIDENCE_ADJUSTMENTS_KEY",
    # Table Extraction Service
    "TableExtractionService",
    "TableExportFormat",
    "TableType",
    "CellDataType",
    "EnhancedTableCell",
    "TableColumn",
    "ExtractedTable",
    "TableExtractionResult",
    "get_table_extraction_service",
    "parse_german_decimal",
    "detect_cell_data_type",
    "detect_table_type",
    # Cross-Backend Consistency Service
    "CrossBackendConsistencyService",
    "ConsistencyLevel",
    "ReviewPriority",
    "RegionType",
    "InconsistentRegion",
    "ConsistencyReport",
    "ConsistencyConfig",
    "get_cross_backend_consistency_service",
    "check_backend_consistency",
    "calculate_backend_agreement",
    # Legacy
    "quick_ocr_preview",
    # Enhanced Feedback Service
    "EnhancedOCRFeedbackService",
    "FeedbackCorrectionFeedback",
    "CorrectionResult",
    "QueueItem",
    "LeaderboardEntry",
    "UserStats",
    "BatchCorrectionResult",
    "LeaderboardPeriod",
    "QueuePriority",
    "CorrectionStatus",
    "get_feedback_service",
    "POINTS_CONFIG",
    "LEADERBOARD_CONFIG",
    "LOW_CONFIDENCE_THRESHOLD",
]
