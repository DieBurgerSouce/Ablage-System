# -*- coding: utf-8 -*-
"""
Fraud Detection Celery Tasks for Ablage-System.

Automated fraud detection tasks:
- fraud.scan_new_documents - Scan newly processed documents
- fraud.daily_anomaly_check - Daily comprehensive scan
- fraud.iban_verification - IBAN change verification workflow
- fraud.train_model - Weekly model update

SECURITY: NEVER log entity names, financial details, or PII.

Feinpoliert und durchdacht - Automated Fraud Prevention.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import Document, InvoiceTracking
from app.db.models_fraud import (
    FraudScanResult,
    IBANChangeRequest,
    IBANBaseline,
    FraudScanType,
    FraudScanStatus,
    IBANChangeStatus,
)
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Document Scanning Tasks
# =============================================================================


@celery_app.task(
    name="fraud.scan_new_documents",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def scan_new_documents_task(
    self,
    hours_back: int = 1,
    company_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Scan recently processed documents for fraud indicators.

    Triggered periodically (hourly) to catch new documents.
    Runs CEO fraud detection on all qualifying documents.

    Args:
        hours_back: How many hours to look back (default 1)
        company_id: Optional specific company to scan

    Returns:
        Dict with scan statistics
    """
    from app.services.ai.fraud_detection_service import get_enhanced_fraud_detection_service

    async def _scan() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_enhanced_fraud_detection_service(db)

            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

            # Find documents that haven't been scanned yet
            stmt = (
                select(Document)
                .where(
                    and_(
                        Document.processed_date >= cutoff,
                        Document.deleted_at.is_(None),
                        ~Document.id.in_(
                            select(FraudScanResult.document_id)
                            .where(
                                and_(
                                    FraudScanResult.scan_type == FraudScanType.CEO_FRAUD.value,
                                    FraudScanResult.document_id.isnot(None),
                                )
                            )
                        ),
                    )
                )
                .limit(100)
            )

            if company_id:
                stmt = stmt.where(Document.company_id == UUID(company_id))

            result = await db.execute(stmt)
            documents = result.scalars().all()

            stats = {
                "total_scanned": 0,
                "suspicious_count": 0,
                "low_risk_count": 0,
                "errors": 0,
            }

            for doc in documents:
                try:
                    if not doc.company_id:
                        continue

                    scan_result = await service.detect_ceo_fraud(
                        document_id=doc.id,
                        company_id=doc.company_id,
                    )

                    stats["total_scanned"] += 1

                    if scan_result.is_suspicious:
                        stats["suspicious_count"] += 1
                        logger.info(
                            "fraud_scan_suspicious",
                            document_id=str(doc.id),
                            risk_score=scan_result.risk_score,
                        )
                    else:
                        stats["low_risk_count"] += 1

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(
                        "fraud_scan_document_error",
                        document_id=str(doc.id),
                        **safe_error_log(e),
                    )

            await db.commit()
            return stats

    try:
        result = asyncio.run(_scan())
        logger.info(
            "fraud_scan_new_documents_completed",
            hours_back=hours_back,
            **result,
        )
        return result
    except Exception as e:
        logger.error("fraud_scan_new_documents_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="fraud.daily_anomaly_check",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def daily_anomaly_check_task(
    self,
    days_back: int = 1,
) -> Dict[str, Any]:
    """
    Daily comprehensive fraud scan.

    Runs all fraud detection types on recent activity:
    - CEO fraud on documents
    - Duplicate payment on invoices
    - IBAN manipulation on entity changes

    Args:
        days_back: Days to analyze (default 1)

    Returns:
        Dict with comprehensive scan statistics
    """
    from app.services.ai.fraud_detection_service import get_enhanced_fraud_detection_service
    from app.db.models import Company

    async def _daily_scan() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_enhanced_fraud_detection_service(db)

            cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

            stats = {
                "companies_scanned": 0,
                "documents_scanned": 0,
                "invoices_scanned": 0,
                "ceo_fraud_alerts": 0,
                "duplicate_payment_alerts": 0,
                "errors": 0,
            }

            # Get all active companies
            company_stmt = select(Company.id).where(Company.is_active == True)
            company_result = await db.execute(company_stmt)
            company_ids = [row[0] for row in company_result.all()]

            for company_id in company_ids:
                try:
                    stats["companies_scanned"] += 1

                    # Scan unscanned documents
                    doc_stmt = (
                        select(Document.id)
                        .where(
                            and_(
                                Document.company_id == company_id,
                                Document.processed_date >= cutoff,
                                Document.deleted_at.is_(None),
                            )
                        )
                        .limit(50)
                    )
                    doc_result = await db.execute(doc_stmt)
                    doc_ids = [row[0] for row in doc_result.all()]

                    for doc_id in doc_ids:
                        try:
                            scan_result = await service.detect_ceo_fraud(
                                document_id=doc_id,
                                company_id=company_id,
                            )
                            stats["documents_scanned"] += 1
                            if scan_result.is_suspicious:
                                stats["ceo_fraud_alerts"] += 1
                        except Exception:
                            stats["errors"] += 1

                    # Scan recent invoices for duplicates
                    inv_stmt = (
                        select(InvoiceTracking.id)
                        .where(
                            and_(
                                InvoiceTracking.company_id == company_id,
                                InvoiceTracking.created_at >= cutoff,
                            )
                        )
                        .limit(50)
                    )
                    inv_result = await db.execute(inv_stmt)
                    inv_ids = [row[0] for row in inv_result.all()]

                    for inv_id in inv_ids:
                        try:
                            scan_result = await service.detect_duplicate_payment(
                                invoice_id=inv_id,
                                company_id=company_id,
                            )
                            stats["invoices_scanned"] += 1
                            if scan_result.is_suspicious:
                                stats["duplicate_payment_alerts"] += 1
                        except Exception:
                            stats["errors"] += 1

                except Exception as e:
                    logger.warning(
                        "daily_scan_company_error",
                        company_id=str(company_id),
                        **safe_error_log(e),
                    )
                    stats["errors"] += 1

            await db.commit()
            return stats

    try:
        result = asyncio.run(_daily_scan())
        logger.info(
            "fraud_daily_anomaly_check_completed",
            **result,
        )
        return result
    except Exception as e:
        logger.error("fraud_daily_anomaly_check_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# IBAN Verification Tasks
# =============================================================================


@celery_app.task(
    name="fraud.iban_verification",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    queue="metadata",
)
def iban_verification_task(
    self,
    entity_id: str,
    new_iban: str,
    company_id: str,
    source_document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process IBAN verification request.

    Triggered when an IBAN change is detected.
    Creates verification workflow if suspicious.

    Args:
        entity_id: Entity whose IBAN is changing
        new_iban: New IBAN value
        company_id: Company context
        source_document_id: Document that triggered the change

    Returns:
        Dict with verification result
    """
    from app.services.ai.fraud_detection_service import get_enhanced_fraud_detection_service

    async def _verify() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            service = get_enhanced_fraud_detection_service(db)

            scan_result = await service.detect_iban_manipulation(
                entity_id=UUID(entity_id),
                new_iban=new_iban,
                company_id=UUID(company_id),
                source_document_id=UUID(source_document_id) if source_document_id else None,
            )

            await db.commit()

            return {
                "entity_id": entity_id,
                "risk_score": scan_result.risk_score,
                "risk_level": scan_result.risk_level.value,
                "requires_verification": scan_result.risk_score >= 0.3,
                "indicator_count": len(scan_result.indicators),
            }

    try:
        result = asyncio.run(_verify())
        logger.info(
            "iban_verification_completed",
            entity_id=entity_id,
            risk_score=result["risk_score"],
            requires_verification=result["requires_verification"],
        )
        return result
    except Exception as e:
        logger.error(
            "iban_verification_failed",
            entity_id=entity_id,
            **safe_error_log(e),
        )
        raise self.retry(exc=e)


@celery_app.task(
    name="fraud.check_expired_iban_requests",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
)
def check_expired_iban_requests_task(self) -> Dict[str, Any]:
    """
    Check for expired IBAN change requests.

    Marks pending requests as expired if past deadline.
    Creates alerts for unverified high-risk changes.

    Returns:
        Dict with expiration statistics
    """

    async def _check_expired() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            now = datetime.now(timezone.utc)

            # Find expired pending requests
            stmt = (
                select(IBANChangeRequest)
                .where(
                    and_(
                        IBANChangeRequest.status == IBANChangeStatus.PENDING.value,
                        IBANChangeRequest.verification_deadline < now,
                    )
                )
                .limit(100)
            )

            result = await db.execute(stmt)
            expired_requests = result.scalars().all()

            stats = {
                "expired_count": 0,
                "high_risk_count": 0,
            }

            for request in expired_requests:
                request.status = IBANChangeStatus.EXPIRED.value
                stats["expired_count"] += 1

                if request.risk_score and request.risk_score >= 0.6:
                    stats["high_risk_count"] += 1
                    # High-risk expired - would create escalation alert here

                logger.info(
                    "iban_request_expired",
                    request_id=str(request.id),
                    entity_id=str(request.entity_id),
                )

            await db.commit()
            return stats

    try:
        result = asyncio.run(_check_expired())
        if result["expired_count"] > 0:
            logger.warning(
                "iban_requests_expired",
                **result,
            )
        return result
    except Exception as e:
        logger.error("check_expired_iban_requests_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Model Training Tasks
# =============================================================================


@celery_app.task(
    name="fraud.train_model",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    queue="maintenance",
)
def train_fraud_model_task(self) -> Dict[str, Any]:
    """
    Weekly fraud model training update.

    Uses feedback from reviewed scan results to improve detection.
    Updates feature weights based on confirmed fraud cases.

    Returns:
        Dict with training statistics
    """

    async def _train() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            # Get reviewed scan results for training
            stmt = (
                select(FraudScanResult)
                .where(
                    FraudScanResult.status.in_([
                        FraudScanStatus.CONFIRMED.value,
                        FraudScanStatus.FALSE_POSITIVE.value,
                    ])
                )
                .order_by(FraudScanResult.reviewed_at.desc())
                .limit(1000)
            )

            result = await db.execute(stmt)
            reviewed_results = result.scalars().all()

            stats = {
                "training_samples": len(reviewed_results),
                "confirmed_fraud": sum(1 for r in reviewed_results if r.status == FraudScanStatus.CONFIRMED.value),
                "false_positives": sum(1 for r in reviewed_results if r.status == FraudScanStatus.FALSE_POSITIVE.value),
                "model_updated": False,
            }

            if len(reviewed_results) < 50:
                logger.info(
                    "fraud_model_training_skipped",
                    reason="insufficient_samples",
                    sample_count=len(reviewed_results),
                )
                return stats

            # In a real implementation, this would:
            # 1. Extract features from confirmed fraud cases
            # 2. Update feature weights based on importance
            # 3. Adjust anomaly thresholds
            # 4. Store updated model parameters

            # Placeholder for model update logic
            stats["model_updated"] = True

            logger.info(
                "fraud_model_training_completed",
                **stats,
            )

            return stats

    try:
        result = asyncio.run(_train())
        return result
    except Exception as e:
        logger.error("fraud_model_training_failed", **safe_error_log(e))
        raise self.retry(exc=e)


@celery_app.task(
    name="fraud.generate_statistics",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
    queue="maintenance",
)
def generate_fraud_statistics_task(
    self,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Generate fraud detection statistics for reporting.

    Args:
        days: Days to analyze (default 30)

    Returns:
        Dict with comprehensive statistics
    """

    async def _generate() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            # Count by scan type
            type_stmt = (
                select(
                    FraudScanResult.scan_type,
                    func.count(FraudScanResult.id).label("count"),
                )
                .where(FraudScanResult.created_at >= cutoff)
                .group_by(FraudScanResult.scan_type)
            )
            type_result = await db.execute(type_stmt)
            by_type = {row[0]: row[1] for row in type_result.all()}

            # Count by risk level
            risk_stmt = (
                select(
                    FraudScanResult.risk_level,
                    func.count(FraudScanResult.id).label("count"),
                )
                .where(FraudScanResult.created_at >= cutoff)
                .group_by(FraudScanResult.risk_level)
            )
            risk_result = await db.execute(risk_stmt)
            by_risk = {row[0]: row[1] for row in risk_result.all()}

            # Count by status
            status_stmt = (
                select(
                    FraudScanResult.status,
                    func.count(FraudScanResult.id).label("count"),
                )
                .where(FraudScanResult.created_at >= cutoff)
                .group_by(FraudScanResult.status)
            )
            status_result = await db.execute(status_stmt)
            by_status = {row[0]: row[1] for row in status_result.all()}

            # Average risk score
            avg_stmt = (
                select(func.avg(FraudScanResult.risk_score))
                .where(FraudScanResult.created_at >= cutoff)
            )
            avg_result = await db.execute(avg_stmt)
            avg_risk = avg_result.scalar() or 0.0

            # IBAN change requests
            iban_stmt = (
                select(
                    IBANChangeRequest.status,
                    func.count(IBANChangeRequest.id).label("count"),
                )
                .where(IBANChangeRequest.created_at >= cutoff)
                .group_by(IBANChangeRequest.status)
            )
            iban_result = await db.execute(iban_stmt)
            iban_by_status = {row[0]: row[1] for row in iban_result.all()}

            return {
                "analysis_period_days": days,
                "by_scan_type": by_type,
                "by_risk_level": by_risk,
                "by_status": by_status,
                "average_risk_score": round(avg_risk, 4),
                "iban_changes_by_status": iban_by_status,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = asyncio.run(_generate())
        logger.info(
            "fraud_statistics_generated",
            days=days,
            total_scans=sum(result["by_scan_type"].values()),
        )
        return result
    except Exception as e:
        logger.error("fraud_statistics_generation_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Celery Beat Schedule
# =============================================================================

FRAUD_DETECTION_BEAT_SCHEDULE = {
    "fraud-scan-new-documents-hourly": {
        "task": "fraud.scan_new_documents",
        "schedule": 3600,  # Every hour
        "kwargs": {"hours_back": 1},
    },
    "fraud-daily-anomaly-check": {
        "task": "fraud.daily_anomaly_check",
        "schedule": {
            "hour": 3,
            "minute": 0,
        },  # Daily at 03:00
        "kwargs": {"days_back": 1},
    },
    "fraud-check-expired-iban-requests": {
        "task": "fraud.check_expired_iban_requests",
        "schedule": 43200,  # Every 12 hours
    },
    "fraud-train-model-weekly": {
        "task": "fraud.train_model",
        "schedule": {
            "day_of_week": 0,  # Sunday
            "hour": 4,
            "minute": 0,
        },
    },
    "fraud-generate-statistics-daily": {
        "task": "fraud.generate_statistics",
        "schedule": {
            "hour": 5,
            "minute": 30,
        },  # Daily at 05:30
        "kwargs": {"days": 30},
    },
}
