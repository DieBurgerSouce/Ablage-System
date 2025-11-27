"""
GDPR Compliance Logging Patterns
Art. 17 (Right to Erasure), Art. 20 (Data Portability), Art. 30 (Records of Processing)
"""

import structlog
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


logger = structlog.get_logger(__name__)


# ============================================================================
# GDPR Article References
# ============================================================================

class GDPRArticle(str, Enum):
    """GDPR Articles relevant to document processing."""
    ART_17_ERASURE = "Art. 17 DSGVO (Recht auf Löschung)"
    ART_20_PORTABILITY = "Art. 20 DSGVO (Datenübertragbarkeit)"
    ART_30_RECORDS = "Art. 30 DSGVO (Verzeichnis von Verarbeitungstätigkeiten)"
    ART_32_SECURITY = "Art. 32 DSGVO (Sicherheit der Verarbeitung)"


class DataOperation(str, Enum):
    """Types of data operations requiring GDPR logging."""
    COLLECTION = "collection"
    ACCESS = "access"
    MODIFICATION = "modification"
    DELETION = "deletion"
    EXPORT = "export"
    ANONYMIZATION = "anonymization"
    RETENTION_CHECK = "retention_check"


# ============================================================================
# Pattern 1: Structured GDPR Log Entry
# ============================================================================

class GDPRLogEntry(BaseModel):
    """Structured log entry for GDPR compliance."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operation: DataOperation
    data_type: str  # e.g., "document", "user_profile", "ocr_result"
    data_id: str
    user_id: str
    legal_basis: GDPRArticle
    reason: Optional[str] = None
    metadata: Dict = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


def log_gdpr_operation(entry: GDPRLogEntry) -> None:
    """
    Log GDPR-relevant operation with structured data.

    Usage:
        log_gdpr_operation(GDPRLogEntry(
            operation=DataOperation.DELETION,
            data_type="document",
            data_id="doc_123",
            user_id="user_456",
            legal_basis=GDPRArticle.ART_17_ERASURE,
            reason="User requested deletion"
        ))
    """
    logger.info(
        "gdpr_operation",
        timestamp=entry.timestamp.isoformat(),
        operation=entry.operation,
        data_type=entry.data_type,
        data_id=entry.data_id,
        user_id=entry.user_id,
        legal_basis=entry.legal_basis,
        reason=entry.reason,
        **entry.metadata
    )


# ============================================================================
# Pattern 2: Right to Erasure (Art. 17)
# ============================================================================

async def handle_deletion_request(
    user_id: str,
    data_type: str,
    data_id: str,
    reason: str,
    db_session,
    storage_service,
    cache_service
) -> Dict[str, any]:
    """
    Handle GDPR Art. 17 deletion request with comprehensive logging.

    Steps:
    1. Log deletion request
    2. Delete from database
    3. Delete from object storage
    4. Clear cache
    5. Log completion
    6. Schedule deletion verification (30 days)

    Returns dict with deletion status and confirmation.
    """
    deletion_id = f"del_{datetime.utcnow().timestamp()}"

    # Step 1: Log deletion request
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.DELETION,
        data_type=data_type,
        data_id=data_id,
        user_id=user_id,
        legal_basis=GDPRArticle.ART_17_ERASURE,
        reason=reason,
        metadata={
            "deletion_id": deletion_id,
            "status": "initiated"
        }
    ))

    errors = []

    try:
        # Step 2: Delete from database
        await db_session.delete(data_type, data_id)
        logger.info("gdpr_deletion_database_complete", data_id=data_id)

    except Exception as e:
        errors.append({"location": "database", "error": str(e)})
        logger.error("gdpr_deletion_database_failed", data_id=data_id, error=str(e))

    try:
        # Step 3: Delete from object storage
        file_path = await storage_service.get_file_path(data_id)
        if file_path:
            await storage_service.delete(file_path)
            logger.info("gdpr_deletion_storage_complete", data_id=data_id)

    except Exception as e:
        errors.append({"location": "storage", "error": str(e)})
        logger.error("gdpr_deletion_storage_failed", data_id=data_id, error=str(e))

    try:
        # Step 4: Clear cache
        await cache_service.delete(f"{data_type}:{data_id}")
        logger.info("gdpr_deletion_cache_complete", data_id=data_id)

    except Exception as e:
        errors.append({"location": "cache", "error": str(e)})
        logger.error("gdpr_deletion_cache_failed", data_id=data_id, error=str(e))

    # Step 5: Log completion
    deletion_status = "complete" if len(errors) == 0 else "partial"

    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.DELETION,
        data_type=data_type,
        data_id=data_id,
        user_id=user_id,
        legal_basis=GDPRArticle.ART_17_ERASURE,
        reason=reason,
        metadata={
            "deletion_id": deletion_id,
            "status": deletion_status,
            "errors": errors,
            "completion_timestamp": datetime.utcnow().isoformat()
        }
    ))

    # Step 6: Schedule deletion verification (30 days)
    from app.workers.celery_app import celery_app
    verification_date = datetime.utcnow() + timedelta(days=30)

    celery_app.send_task(
        'verify_gdpr_deletion',
        args=[deletion_id, data_type, data_id],
        eta=verification_date
    )

    return {
        "deletion_id": deletion_id,
        "status": deletion_status,
        "errors": errors,
        "verification_scheduled": verification_date.isoformat()
    }


# ============================================================================
# Pattern 3: Data Portability (Art. 20)
# ============================================================================

async def handle_data_export_request(
    user_id: str,
    export_format: str = "json"
) -> Dict[str, any]:
    """
    Handle GDPR Art. 20 data portability request.

    Exports all user data in machine-readable format.

    Returns dict with export location and metadata.
    """
    export_id = f"export_{datetime.utcnow().timestamp()}"

    # Log export request
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.EXPORT,
        data_type="user_data",
        data_id=user_id,
        user_id=user_id,
        legal_basis=GDPRArticle.ART_20_PORTABILITY,
        reason="User requested data export",
        metadata={
            "export_id": export_id,
            "format": export_format,
            "status": "initiated"
        }
    ))

    # Collect all user data
    from app.services.export_service import ExportService
    export_service = ExportService()

    export_data = await export_service.collect_user_data(
        user_id=user_id,
        include_documents=True,
        include_ocr_results=True,
        include_metadata=True
    )

    # Create export file
    export_path = await export_service.create_export_file(
        data=export_data,
        format=export_format,
        export_id=export_id
    )

    # Log completion
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.EXPORT,
        data_type="user_data",
        data_id=user_id,
        user_id=user_id,
        legal_basis=GDPRArticle.ART_20_PORTABILITY,
        metadata={
            "export_id": export_id,
            "status": "complete",
            "file_path": export_path,
            "file_size_bytes": await export_service.get_file_size(export_path),
            "completion_timestamp": datetime.utcnow().isoformat()
        }
    ))

    # Schedule auto-deletion of export file (7 days)
    from app.workers.celery_app import celery_app
    deletion_date = datetime.utcnow() + timedelta(days=7)

    celery_app.send_task(
        'delete_export_file',
        args=[export_path],
        eta=deletion_date
    )

    return {
        "export_id": export_id,
        "status": "complete",
        "download_url": f"/api/v1/gdpr/exports/{export_id}",
        "expires_at": deletion_date.isoformat(),
        "format": export_format
    }


# ============================================================================
# Pattern 4: Data Access Logging (Audit Trail)
# ============================================================================

def log_data_access(
    user_id: str,
    data_type: str,
    data_id: str,
    access_reason: str,
    metadata: Optional[Dict] = None
) -> None:
    """
    Log data access for audit trail.

    Required for GDPR Art. 30 (Records of Processing Activities).

    Usage:
        log_data_access(
            user_id="user_123",
            data_type="document",
            data_id="doc_456",
            access_reason="User viewed document",
            metadata={"ip_address": "192.168.1.1", "user_agent": "..."}
        )
    """
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.ACCESS,
        data_type=data_type,
        data_id=data_id,
        user_id=user_id,
        legal_basis=GDPRArticle.ART_30_RECORDS,
        reason=access_reason,
        metadata=metadata or {}
    ))


# ============================================================================
# Pattern 5: Data Retention Check
# ============================================================================

async def check_data_retention(
    data_type: str,
    retention_days: int = 365
) -> List[str]:
    """
    Check for data exceeding retention period.

    Returns list of data IDs that should be deleted.

    Usage:
        expired_docs = await check_data_retention(
            data_type="document",
            retention_days=365
        )
    """
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    logger.info(
        "gdpr_retention_check_started",
        data_type=data_type,
        retention_days=retention_days,
        cutoff_date=cutoff_date.isoformat()
    )

    # Query database for old data
    from app.db.database import get_db
    async with get_db() as db:
        old_data = await db.query(data_type).filter(
            created_at < cutoff_date
        ).all()

    expired_ids = [item.id for item in old_data]

    # Log retention check
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.RETENTION_CHECK,
        data_type=data_type,
        data_id=f"retention_check_{datetime.utcnow().timestamp()}",
        user_id="system",
        legal_basis=GDPRArticle.ART_30_RECORDS,
        metadata={
            "retention_days": retention_days,
            "expired_count": len(expired_ids),
            "cutoff_date": cutoff_date.isoformat()
        }
    ))

    return expired_ids


# ============================================================================
# Pattern 6: Anonymization Logging
# ============================================================================

async def anonymize_sensitive_data(
    data_type: str,
    data_id: str,
    fields_to_anonymize: List[str]
) -> Dict[str, any]:
    """
    Anonymize sensitive fields in data.

    Logs anonymization for GDPR compliance.

    Usage:
        result = await anonymize_sensitive_data(
            data_type="document",
            data_id="doc_123",
            fields_to_anonymize=["owner_name", "email", "phone"]
        )
    """
    logger.info(
        "gdpr_anonymization_started",
        data_type=data_type,
        data_id=data_id,
        fields=fields_to_anonymize
    )

    # Perform anonymization
    from app.services.anonymization_service import AnonymizationService
    anon_service = AnonymizationService()

    anonymized_data = await anon_service.anonymize(
        data_type=data_type,
        data_id=data_id,
        fields=fields_to_anonymize
    )

    # Log anonymization
    log_gdpr_operation(GDPRLogEntry(
        operation=DataOperation.ANONYMIZATION,
        data_type=data_type,
        data_id=data_id,
        user_id="system",
        legal_basis=GDPRArticle.ART_32_SECURITY,
        metadata={
            "anonymized_fields": fields_to_anonymize,
            "completion_timestamp": datetime.utcnow().isoformat()
        }
    ))

    return {
        "status": "anonymized",
        "data_id": data_id,
        "fields_anonymized": fields_to_anonymize
    }


# ============================================================================
# Pattern 7: GDPR Compliance Report Generation
# ============================================================================

async def generate_gdpr_compliance_report(
    start_date: datetime,
    end_date: datetime
) -> Dict[str, any]:
    """
    Generate GDPR compliance report for specified period.

    Includes:
    - Total data operations
    - Deletion requests handled
    - Export requests handled
    - Average response time
    - Compliance rate

    Usage:
        report = await generate_gdpr_compliance_report(
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31)
        )
    """
    # Query GDPR logs from database
    from app.db.database import get_db
    async with get_db() as db:
        logs = await db.query_gdpr_logs(
            start_date=start_date,
            end_date=end_date
        )

    # Aggregate statistics
    stats = {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "operations": {
            "total": len(logs),
            "by_type": {},
            "by_article": {}
        },
        "deletion_requests": {
            "total": 0,
            "completed": 0,
            "avg_completion_days": 0
        },
        "export_requests": {
            "total": 0,
            "completed": 0,
            "avg_file_size_mb": 0
        }
    }

    # Calculate statistics
    for log in logs:
        # By operation type
        op_type = log.operation
        stats["operations"]["by_type"][op_type] = \
            stats["operations"]["by_type"].get(op_type, 0) + 1

        # By legal basis
        article = log.legal_basis
        stats["operations"]["by_article"][article] = \
            stats["operations"]["by_article"].get(article, 0) + 1

        # Deletion metrics
        if log.operation == DataOperation.DELETION:
            stats["deletion_requests"]["total"] += 1
            if log.metadata.get("status") == "complete":
                stats["deletion_requests"]["completed"] += 1

        # Export metrics
        if log.operation == DataOperation.EXPORT:
            stats["export_requests"]["total"] += 1
            if log.metadata.get("status") == "complete":
                stats["export_requests"]["completed"] += 1

    # Compliance rate
    total_requests = (stats["deletion_requests"]["total"] +
                      stats["export_requests"]["total"])
    completed_requests = (stats["deletion_requests"]["completed"] +
                          stats["export_requests"]["completed"])

    stats["compliance_rate"] = (
        completed_requests / total_requests * 100
        if total_requests > 0 else 100
    )

    logger.info(
        "gdpr_compliance_report_generated",
        **stats
    )

    return stats


# ============================================================================
# Usage Examples
# ============================================================================

if __name__ == "__main__":
    # Example 1: Log data access
    log_data_access(
        user_id="user_123",
        data_type="document",
        data_id="doc_456",
        access_reason="User downloaded document",
        metadata={"ip_address": "192.168.1.1"}
    )

    # Example 2: Handle deletion request
    # result = await handle_deletion_request(
    #     user_id="user_123",
    #     data_type="document",
    #     data_id="doc_456",
    #     reason="User requested deletion via UI",
    #     db_session=db,
    #     storage_service=storage,
    #     cache_service=cache
    # )

    # Example 3: Data export
    # export = await handle_data_export_request(
    #     user_id="user_123",
    #     export_format="json"
    # )
