# -*- coding: utf-8 -*-
"""
Document Timeline Service.

Zeigt kompletten Lebenszyklus eines Dokuments:
- Upload -> OCR -> Korrektur -> Kategorisierung -> Entity Linking -> Approval -> Archive

Feinpoliert und durchdacht - Enterprise-Grade Document Timeline.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    AuditLog,
    ProcessingJob,
)
from app.db.models_ocr_feedback import OCRCorrectionFeedback
from app.db.models_versioning import DocumentVersion
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class TimelineEventType:
    """Timeline Event Types."""
    UPLOAD = "upload"
    OCR_START = "ocr_start"
    OCR_COMPLETE = "ocr_complete"
    OCR_FAILED = "ocr_failed"
    CORRECTION = "correction"
    CATEGORIZATION = "categorization"
    ENTITY_LINKED = "entity_linked"
    APPROVAL = "approval"
    REJECTION = "rejection"
    EXPORT = "export"
    SHARE = "share"
    VERSION_CREATE = "version_create"
    ARCHIVE = "archive"
    DELETE = "delete"


class DocumentTimelineService:
    """
    Service für Document Timeline.

    Aggregiert alle Events eines Dokuments in chronologischer Reihenfolge.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize service."""
        self.session = session

    async def get_document_timeline(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """
        Erstellt vollständige Timeline eines Dokuments.

        Args:
            document_id: Document ID
            company_id: Company ID (für Multi-Tenant Isolation)

        Returns:
            Liste von Timeline-Events
        """
        # Prüfe Document-Existenz und Company-Zugehörigkeit
        doc_query = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id
            )
        )
        doc_result = await self.session.execute(doc_query)
        document = doc_result.scalar_one_or_none()

        if not document:
            return []

        timeline = []

        # 1. Upload Event
        timeline.append({
            "event_type": TimelineEventType.UPLOAD,
            "timestamp": document.upload_date.isoformat() if document.upload_date else None,
            "user_id": str(document.owner_id) if document.owner_id else None,
            "details": {
                "filename": document.original_filename,
                "file_size": document.file_size,
                "mime_type": document.mime_type,
            },
            "description": f"Dokument hochgeladen: {document.original_filename}",
        })

        # 2. Processing Jobs (OCR)
        jobs = await self._get_processing_jobs(document_id)
        for job in jobs:
            if job["status"] == "processing":
                timeline.append({
                    "event_type": TimelineEventType.OCR_START,
                    "timestamp": job["started_at"],
                    "details": {
                        "backend": job["backend"],
                        "job_type": job["job_type"],
                    },
                    "description": f"OCR gestartet mit {job['backend']}",
                })
            elif job["status"] == "completed":
                timeline.append({
                    "event_type": TimelineEventType.OCR_COMPLETE,
                    "timestamp": job["completed_at"],
                    "details": {
                        "backend": job["backend"],
                        "duration_ms": job.get("duration_ms"),
                        "confidence": document.ocr_confidence,
                    },
                    "description": f"OCR abgeschlossen ({document.ocr_confidence*100:.1f}% Konfidenz)" if document.ocr_confidence else "OCR abgeschlossen",
                })
            elif job["status"] == "failed":
                timeline.append({
                    "event_type": TimelineEventType.OCR_FAILED,
                    "timestamp": job["completed_at"],
                    "details": {
                        "backend": job["backend"],
                        "error": job.get("error_message"),
                    },
                    "description": f"OCR fehlgeschlagen: {job.get('error_message', 'Unbekannter Fehler')}",
                })

        # 3. OCR Corrections
        corrections = await self._get_corrections(document_id)
        for corr in corrections:
            timeline.append({
                "event_type": TimelineEventType.CORRECTION,
                "timestamp": corr["timestamp"],
                "user_id": corr["user_id"],
                "details": {
                    "field_name": corr["field_name"],
                    "original_value": corr["original_value"][:100],  # Limit
                    "corrected_value": corr["corrected_value"][:100],
                    "correction_type": corr["correction_type"],
                },
                "description": f"Korrektur: {corr['field_name']}",
            })

        # 4. Categorization (from processed_date)
        if document.processed_date:
            timeline.append({
                "event_type": TimelineEventType.CATEGORIZATION,
                "timestamp": document.processed_date.isoformat(),
                "details": {
                    "document_type": document.document_type,
                    "confidence": document.ocr_confidence,
                },
                "description": f"Kategorisiert als: {document.document_type}",
            })

        # 5. Entity Linking
        if document.business_entity_id:
            timeline.append({
                "event_type": TimelineEventType.ENTITY_LINKED,
                "timestamp": document.updated_at.isoformat() if document.updated_at else None,
                "details": {
                    "entity_id": str(document.business_entity_id),
                },
                "description": "Geschäftspartner verknüpft",
            })

        # 6. Audit Logs (Approval, Export, etc.)
        audit_events = await self._get_audit_events(document_id, company_id)
        timeline.extend(audit_events)

        # 7. Shares
        shares = await self._get_shares(document_id)
        for share in shares:
            timeline.append({
                "event_type": TimelineEventType.SHARE,
                "timestamp": share["shared_at"],
                "user_id": share["shared_by_id"],
                "details": {
                    "shared_with_id": share["shared_with_id"],
                    "permission": share["permission"],
                },
                "description": f"Geteilt mit Benutzer (Berechtigung: {share['permission']})",
            })

        # 8. Versions
        versions = await self._get_versions(document_id)
        for version in versions:
            timeline.append({
                "event_type": TimelineEventType.VERSION_CREATE,
                "timestamp": version["created_at"],
                "user_id": version["created_by_id"],
                "details": {
                    "version_number": version["version_number"],
                    "change_type": version["change_type"],
                },
                "description": f"Version {version['version_number']} erstellt",
            })

        # 9. Archive
        if document.is_archived:
            timeline.append({
                "event_type": TimelineEventType.ARCHIVE,
                "timestamp": document.archived_at.isoformat() if document.archived_at else None,
                "details": {
                    "reason": "GoBD Archivierung",
                },
                "description": "Dokument archiviert (GoBD)",
            })

        # 10. Soft Delete
        if document.deleted_at:
            timeline.append({
                "event_type": TimelineEventType.DELETE,
                "timestamp": document.deleted_at.isoformat(),
                "user_id": str(document.deleted_by_id) if document.deleted_by_id else None,
                "details": {},
                "description": "Dokument gelöscht (GDPR Soft-Delete)",
            })

        # Sortiere Timeline chronologisch
        timeline.sort(key=lambda x: x["timestamp"] or "")

        return timeline

    async def _get_processing_jobs(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Hole Processing Jobs."""
        query = (
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.created_at)
        )

        result = await self.session.execute(query)
        jobs = result.scalars().all()

        return [
            {
                "job_type": job.job_type,
                "backend": job.backend,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "duration_ms": int((job.completed_at - job.started_at).total_seconds() * 1000)
                if job.completed_at and job.started_at else None,
                "error_message": job.error_message,
            }
            for job in jobs
        ]

    async def _get_corrections(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Hole OCR Corrections."""
        query = (
            select(OCRCorrectionFeedback)
            .where(OCRCorrectionFeedback.document_id == document_id)
            .order_by(OCRCorrectionFeedback.created_at)
        )

        result = await self.session.execute(query)
        corrections = result.scalars().all()

        return [
            {
                "field_name": corr.field_name,
                "original_value": corr.original_value,
                "corrected_value": corr.corrected_value,
                "correction_type": corr.correction_type,
                "user_id": str(corr.user_id) if corr.user_id else None,
                "timestamp": corr.created_at.isoformat(),
            }
            for corr in corrections
        ]

    async def _get_audit_events(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Hole Audit Events."""
        query = (
            select(AuditLog)
            .where(
                and_(
                    AuditLog.resource_id == document_id,
                    AuditLog.company_id == company_id,
                    AuditLog.action.in_([
                        "document_approve",
                        "document_reject",
                        "document_export",
                        "document_download",
                    ])
                )
            )
            .order_by(AuditLog.created_at)
        )

        result = await self.session.execute(query)
        logs = result.scalars().all()

        events = []
        for log in logs:
            event_type = None
            description = ""

            if log.action == "document_approve":
                event_type = TimelineEventType.APPROVAL
                description = "Dokument genehmigt"
            elif log.action == "document_reject":
                event_type = TimelineEventType.REJECTION
                description = "Dokument abgelehnt"
            elif log.action == "document_export":
                event_type = TimelineEventType.EXPORT
                export_format = (log.audit_metadata or {}).get("format", "unknown")
                description = f"Dokument exportiert ({export_format})"

            if event_type:
                events.append({
                    "event_type": event_type,
                    "timestamp": log.created_at.isoformat(),
                    "user_id": str(log.user_id) if log.user_id else None,
                    "details": log.audit_metadata or {},
                    "description": description,
                })

        return events

    async def _get_shares(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Hole Document Shares aus Audit-Logs."""
        try:
            query = (
                select(AuditLog)
                .where(
                    and_(
                        AuditLog.resource_id == document_id,
                        AuditLog.action == "document_share",
                    )
                )
                .order_by(AuditLog.created_at)
            )

            result = await self.session.execute(query)
            logs = result.scalars().all()

            return [
                {
                    "shared_by_id": str(log.user_id) if log.user_id else None,
                    "shared_with_id": (log.audit_metadata or {}).get("shared_with_id"),
                    "permission": (log.audit_metadata or {}).get("permission", "view"),
                    "shared_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
        except Exception as e:
            logger.debug("document_shares_query_failed", **safe_error_log(e))
            return []

    async def _get_versions(self, document_id: UUID) -> List[Dict[str, Any]]:
        """Hole Document Versions (falls Tabelle existiert)."""
        try:
            query = (
                select(DocumentVersion)
                .where(DocumentVersion.document_id == document_id)
                .order_by(DocumentVersion.version_number)
            )

            result = await self.session.execute(query)
            versions = result.scalars().all()

            return [
                {
                    "version_number": ver.version_number,
                    "change_type": ver.change_type,
                    "created_by_id": str(ver.created_by_id) if ver.created_by_id else None,
                    "created_at": ver.created_at.isoformat() if ver.created_at else None,
                }
                for ver in versions
            ]
        except Exception as e:
            # Table might not exist yet
            logger.debug("document_versions_table_not_found", **safe_error_log(e))
            return []


def get_document_timeline_service(session: AsyncSession) -> DocumentTimelineService:
    """Factory function für DocumentTimelineService."""
    return DocumentTimelineService(session)
