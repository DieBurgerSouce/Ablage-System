"""
Celery Tasks fuer Stammdaten-Hygiene.

Automatische Erkennung und Korrektur von Stammdaten-Problemen.
"""

import asyncio
from typing import Any, Dict, List, Optional

import structlog
from celery import shared_task

from app.core.database import get_async_session
from app.core.safe_errors import safe_error_log
from app.db.models import EntityType

logger = structlog.get_logger(__name__)


# ============================================================================
# HYGIENE SCAN TASKS
# ============================================================================


@shared_task(
    name="app.workers.tasks.hygiene_tasks.run_full_hygiene_scan",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def run_full_hygiene_scan(
    self,
    entity_types: Optional[List[str]] = None,
    notify_admin: bool = True,
) -> Dict[str, Any]:
    """
    Fuehrt vollstaendigen Hygiene-Scan durch.

    Wird woechentlich ausgefuehrt (Sonntag 03:00).

    Args:
        entity_types: Optional - nur bestimmte Entity-Typen
        notify_admin: Admin per E-Mail benachrichtigen

    Returns:
        Scan-Ergebnis mit Statistiken
    """
    logger.info(
        "hygiene_scan_task_started",
        entity_types=entity_types,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_run_full_scan(entity_types, notify_admin)
        )
        return result

    except RuntimeError:
        # Kein Event Loop vorhanden
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_run_full_scan(entity_types, notify_admin)
            )
            return result
        finally:
            loop.close()


async def _async_run_full_scan(
    entity_types: Optional[List[str]],
    notify_admin: bool,
) -> Dict[str, Any]:
    """Async Implementierung des Hygiene-Scans."""
    from app.services.master_data_hygiene_service import get_master_data_hygiene_service
    from app.services.notification_service import NotificationService

    async with get_async_session() as db:
        service = get_master_data_hygiene_service(db)

        # Entity-Typen parsen
        types_filter = None
        if entity_types:
            types_filter = [EntityType(t) for t in entity_types if t]

        # Scan durchfuehren
        report = await service.run_full_scan(entity_types=types_filter)

        # Admin benachrichtigen wenn Issues gefunden
        if notify_admin and report.issues_found > 0:
            try:
                # High/Critical Issues zaehlen
                critical_count = report.by_severity.get("critical", 0)
                high_count = report.by_severity.get("high", 0)

                if critical_count > 0 or high_count > 0:
                    notification_service = NotificationService(db)
                    await notification_service.send_admin_notification(
                        title="Stammdaten-Hygiene: Probleme gefunden",
                        message=(
                            f"Der automatische Hygiene-Scan hat {report.issues_found} Probleme gefunden.\n\n"
                            f"Kritisch: {critical_count}\n"
                            f"Hoch: {high_count}\n"
                            f"Mittel: {report.by_severity.get('medium', 0)}\n"
                            f"Niedrig: {report.by_severity.get('low', 0)}\n\n"
                            f"Bitte pruefen Sie die Stammdaten im Admin-Bereich."
                        ),
                        notification_type="hygiene_scan",
                    )
            except Exception as e:
                logger.error("hygiene_notification_failed", **safe_error_log(e))

        logger.info(
            "hygiene_scan_task_completed",
            total_checked=report.total_entities_checked,
            issues_found=report.issues_found,
            by_severity=report.by_severity,
        )

        return {
            "success": True,
            "total_entities_checked": report.total_entities_checked,
            "issues_found": report.issues_found,
            "auto_correctable_count": report.auto_correctable_count,
            "by_severity": report.by_severity,
            "by_type": report.by_type,
        }


@shared_task(
    name="app.workers.tasks.hygiene_tasks.check_entity_after_document",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="metadata",
)
def check_entity_after_document(
    self,
    document_id: str,
    entity_id: str,
) -> Dict[str, Any]:
    """
    Prueft Entity-Daten nach Dokumentenverarbeitung.

    Wird nach OCR-Completion ausgefuehrt wenn Dokument
    mit Entity verknuepft ist.

    Args:
        document_id: Dokument-ID
        entity_id: Entity-ID

    Returns:
        Gefundene Issues
    """
    logger.info(
        "entity_check_after_document_started",
        document_id=document_id,
        entity_id=entity_id,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_check_entity_document(document_id, entity_id)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_check_entity_document(document_id, entity_id)
            )
            return result
        finally:
            loop.close()


async def _async_check_entity_document(
    document_id: str,
    entity_id: str,
) -> Dict[str, Any]:
    """Async Implementierung der Entity-Pruefung."""
    import uuid
    from sqlalchemy import select
    from app.db.models import Document
    from app.services.master_data_hygiene_service import get_master_data_hygiene_service

    async with get_async_session() as db:
        # Dokument laden
        result = await db.execute(
            select(Document).where(
                Document.id == uuid.UUID(document_id),
                Document.deleted_at.is_(None),
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            logger.warning(
                "document_not_found_for_hygiene_check",
                document_id=document_id,
            )
            return {"success": False, "error": "Dokument nicht gefunden"}

        ocr_text = document.ocr_full_text or ""
        if not ocr_text:
            return {"success": True, "issues_found": 0, "issues": []}

        service = get_master_data_hygiene_service(db)

        issues = await service.extract_updates_from_document(
            document_id=uuid.UUID(document_id),
            entity_id=uuid.UUID(entity_id),
            ocr_text=ocr_text,
        )

        logger.info(
            "entity_check_after_document_completed",
            document_id=document_id,
            entity_id=entity_id,
            issues_found=len(issues),
        )

        return {
            "success": True,
            "issues_found": len(issues),
            "issues": [issue.to_dict() for issue in issues],
        }


@shared_task(
    name="app.workers.tasks.hygiene_tasks.auto_apply_corrections",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    queue="maintenance",
)
def auto_apply_corrections(
    self,
    confidence_threshold: float = 0.98,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Wendet automatisch Korrekturen mit hoher Confidence an.

    Nur fuer nicht-kritische Felder mit sehr hoher Confidence.

    Args:
        confidence_threshold: Mindest-Confidence fuer Auto-Korrektur
        dry_run: Nur simulieren, keine Aenderungen

    Returns:
        Anzahl angewendeter Korrekturen
    """
    logger.info(
        "auto_apply_corrections_started",
        confidence_threshold=confidence_threshold,
        dry_run=dry_run,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_auto_apply_corrections(confidence_threshold, dry_run)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_auto_apply_corrections(confidence_threshold, dry_run)
            )
            return result
        finally:
            loop.close()


async def _async_auto_apply_corrections(
    confidence_threshold: float,
    dry_run: bool,
) -> Dict[str, Any]:
    """Async Implementierung der Auto-Korrekturen."""
    from app.services.master_data_hygiene_service import (
        get_master_data_hygiene_service,
        HygieneIssueSeverity,
    )

    async with get_async_session() as db:
        service = get_master_data_hygiene_service(db)

        # Erst Scan durchfuehren
        report = await service.run_full_scan()

        applied_count = 0
        skipped_count = 0

        # Nur auto_correctable Issues mit hoher Confidence
        for issue in report.issues:
            if not issue.auto_correctable:
                continue

            if issue.confidence < confidence_threshold:
                skipped_count += 1
                continue

            # Kritische Felder nie automatisch aendern
            if issue.severity in (HygieneIssueSeverity.CRITICAL, HygieneIssueSeverity.HIGH):
                skipped_count += 1
                continue

            if not issue.suggested_value:
                continue

            if dry_run:
                applied_count += 1
                logger.info(
                    "auto_correction_would_apply",
                    entity_id=str(issue.entity_id),
                    field_name=issue.field_name,
                    current=issue.current_value,
                    suggested=issue.suggested_value,
                )
                continue

            # Korrektur anwenden
            import uuid
            success = await service.apply_correction(
                issue_id=issue.id,
                entity_id=issue.entity_id,
                field_name=issue.field_name,
                new_value=issue.suggested_value,
                approved_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),  # System-User
            )

            if success:
                applied_count += 1
            else:
                skipped_count += 1

        logger.info(
            "auto_apply_corrections_completed",
            applied_count=applied_count,
            skipped_count=skipped_count,
            dry_run=dry_run,
        )

        return {
            "success": True,
            "applied_count": applied_count,
            "skipped_count": skipped_count,
            "dry_run": dry_run,
        }


@shared_task(
    name="app.workers.tasks.hygiene_tasks.check_inactive_entities",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def check_inactive_entities(
    self,
    inactivity_days: int = 365,
) -> Dict[str, Any]:
    """
    Prueft auf inaktive Entities.

    Wird monatlich ausgefuehrt.

    Args:
        inactivity_days: Tage ohne Aktivitaet = inaktiv

    Returns:
        Gefundene inaktive Entities
    """
    logger.info(
        "check_inactive_entities_started",
        inactivity_days=inactivity_days,
    )

    try:
        result = asyncio.get_event_loop().run_until_complete(
            _async_check_inactive(inactivity_days)
        )
        return result

    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _async_check_inactive(inactivity_days)
            )
            return result
        finally:
            loop.close()


async def _async_check_inactive(inactivity_days: int) -> Dict[str, Any]:
    """Async Implementierung der Inaktivitaets-Pruefung."""
    from app.services.master_data_hygiene_service import (
        MasterDataHygieneService,
        HygieneIssueType,
    )

    async with get_async_session() as db:
        service = MasterDataHygieneService(db, inactivity_days=inactivity_days)

        issues = await service._scan_inactive_entities()

        # Nach Typ gruppieren
        customers_inactive = len([
            i for i in issues
            if i.issue_type == HygieneIssueType.INACTIVE_CUSTOMER
        ])
        suppliers_inactive = len([
            i for i in issues
            if i.issue_type == HygieneIssueType.INACTIVE_SUPPLIER
        ])

        logger.info(
            "check_inactive_entities_completed",
            total_inactive=len(issues),
            customers_inactive=customers_inactive,
            suppliers_inactive=suppliers_inactive,
        )

        return {
            "success": True,
            "total_inactive": len(issues),
            "customers_inactive": customers_inactive,
            "suppliers_inactive": suppliers_inactive,
            "inactivity_days": inactivity_days,
        }
