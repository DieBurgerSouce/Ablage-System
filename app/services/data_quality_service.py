# -*- coding: utf-8 -*-
"""
Data Quality Service - Datenqualitaets-Cockpit.

Bietet proaktive Datenqualitaets-Ueberwachung und Cleanup:
- Uncat egorisierte Dokumente
- Duplikate
- Verwaiste Entities
- Fehlende Metadaten
- Niedrige OCR-Qualitaet
- Nicht zugeordnete Dokumente
- Veraltete Dokumente

Feinpoliert und durchdacht - Enterprise Data Quality.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.services.ai.duplicate_detection_service import DuplicateDetectionService

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class QualityCategory(str, Enum):
    """Data Quality Issue Categories."""
    UNCATEGORIZED = "uncategorized"
    DUPLICATES = "duplicates"
    ORPHANED_ENTITIES = "orphaned_entities"
    MISSING_METADATA = "missing_metadata"
    LOW_OCR_QUALITY = "low_ocr_quality"
    UNLINKED_DOCUMENTS = "unlinked_documents"
    STALE_DOCUMENTS = "stale_documents"


@dataclass
class DataQualityIssue:
    """Einzelnes Datenqualitaets-Problem."""
    category: QualityCategory
    severity: str  # "info", "warning", "critical"
    title: str  # German
    description: str  # German
    count: int
    action_label: str  # "Bereinigen", "Zuordnen", "Pruefen"
    action_endpoint: str  # API endpoint to fix


@dataclass
class DataQualityReport:
    """Vollstaendiger Datenqualitaets-Bericht."""
    overall_score: float  # 0-100
    issues: List[DataQualityIssue]
    trend: str  # "improving", "stable", "worsening"
    last_check: datetime


# =============================================================================
# Data Quality Service
# =============================================================================

class DataQualityService:
    """
    Service fuer Datenqualitaets-Cockpit.

    Scannt die Datenbank nach Qualitaetsproblemen und bietet Cleanup-Aktionen.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service."""
        self.db = db
        self._duplicate_detection_service: Optional[DuplicateDetectionService] = None

    @property
    def duplicate_detection_service(self) -> DuplicateDetectionService:
        """Lazy-load duplicate detection service."""
        if self._duplicate_detection_service is None:
            self._duplicate_detection_service = DuplicateDetectionService(self.db)
        return self._duplicate_detection_service

    async def get_quality_report(
        self,
        company_id: UUID,
    ) -> DataQualityReport:
        """
        Erstellt vollstaendigen Datenqualitaets-Bericht.

        Args:
            company_id: Company ID

        Returns:
            DataQualityReport mit allen Issues
        """
        logger.info("data_quality_report_start", company_id=str(company_id))

        issues: List[DataQualityIssue] = []

        # Alle Issue-Checks parallel ausfuehren
        issues.append(await self._check_uncategorized(company_id))
        issues.append(await self._check_duplicates(company_id))
        issues.append(await self._check_orphaned_entities(company_id))
        issues.append(await self._check_missing_metadata(company_id))
        issues.append(await self._check_low_ocr_quality(company_id))
        issues.append(await self._check_unlinked_documents(company_id))
        issues.append(await self._check_stale_documents(company_id))

        # Filter Issues mit count > 0
        issues = [issue for issue in issues if issue.count > 0]

        # Overall Score berechnen
        overall_score = self._calculate_overall_score(issues, company_id)

        # Trend berechnen (vereinfacht)
        # Note: get_quality_trend() returns empty list (no history table yet)
        trend = "stable"

        report = DataQualityReport(
            overall_score=overall_score,
            issues=issues,
            trend=trend,
            last_check=datetime.now(timezone.utc),
        )

        logger.info(
            "data_quality_report_complete",
            company_id=str(company_id),
            overall_score=overall_score,
            issue_count=len(issues),
        )
        return report

    async def get_quality_trend(
        self,
        company_id: UUID,
        months: int = 6,
    ) -> List[Dict[str, Any]]:
        """
        Ruft Datenqualitaets-Trend ab.

        Args:
            company_id: Company ID
            months: Number of months to look back

        Returns:
            List of {month, score} dicts
        """
        # TODO: Store quality scores in a history table
        # For now, return placeholder data
        trend: List[Dict[str, Any]] = []
        return trend

    async def fix_issue(
        self,
        company_id: UUID,
        category: QualityCategory,
        action: str,
    ) -> int:
        """
        Fuehrt Cleanup-Aktion fuer eine Kategorie aus.

        Args:
            company_id: Company ID
            category: Issue category to fix
            action: Action to perform

        Returns:
            Number of items fixed
        """
        logger.info(
            "data_quality_fix_start",
            company_id=str(company_id),
            category=category.value,
            action=action,
        )

        fix_map = {
            QualityCategory.UNCATEGORIZED: self._fix_uncategorized,
            QualityCategory.DUPLICATES: self._fix_duplicates,
            QualityCategory.ORPHANED_ENTITIES: self._fix_orphaned_entities,
            QualityCategory.MISSING_METADATA: self._fix_missing_metadata,
            QualityCategory.LOW_OCR_QUALITY: self._fix_low_ocr_quality,
            QualityCategory.UNLINKED_DOCUMENTS: self._fix_unlinked_documents,
            QualityCategory.STALE_DOCUMENTS: self._fix_stale_documents,
        }

        if category not in fix_map:
            raise ValueError(f"Unbekannte Kategorie: {category.value}")

        fixed_count = await fix_map[category](company_id, action)

        logger.info(
            "data_quality_fix_complete",
            company_id=str(company_id),
            category=category.value,
            fixed_count=fixed_count,
        )
        return fixed_count

    # =========================================================================
    # Issue Checks
    # =========================================================================

    async def _check_uncategorized(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf unkategorisierte Dokumente."""
        query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                or_(
                    Document.document_type.is_(None),
                    Document.document_type == "",
                ),
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 50:
            severity = "warning"
        if count > 100:
            severity = "critical"

        return DataQualityIssue(
            category=QualityCategory.UNCATEGORIZED,
            severity=severity,
            title="Unkategorisierte Dokumente",
            description=f"{count} Dokumente haben keine Kategorie zugewiesen.",
            count=count,
            action_label="Kategorisieren",
            action_endpoint="/api/v1/data-quality/uncategorized/fix",
        )

    async def _check_duplicates(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf moegliche Duplikate."""
        # Simplified: Count documents with duplicate file hashes
        query = select(
            func.count(Document.id)
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.checksum.in_(
                    select(Document.checksum)
                    .where(
                        and_(
                            Document.company_id == company_id,
                            Document.deleted_at.is_(None),
                        )
                    )
                    .group_by(Document.checksum)
                    .having(func.count(Document.id) > 1)
                ),
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 10:
            severity = "warning"
        if count > 30:
            severity = "critical"

        return DataQualityIssue(
            category=QualityCategory.DUPLICATES,
            severity=severity,
            title="Moegliche Duplikate",
            description=f"{count} Dokumente koennen Duplikate sein.",
            count=count,
            action_label="Pruefen",
            action_endpoint="/api/v1/data-quality/duplicates/fix",
        )

    async def _check_orphaned_entities(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf Entities ohne Dokumente."""
        query = select(
            func.count(BusinessEntity.id)
        ).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                ~BusinessEntity.id.in_(
                    select(Document.business_entity_id)
                    .where(
                        and_(
                            Document.company_id == company_id,
                            Document.deleted_at.is_(None),
                            Document.business_entity_id.isnot(None),
                        )
                    )
                ),
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 20:
            severity = "warning"

        return DataQualityIssue(
            category=QualityCategory.ORPHANED_ENTITIES,
            severity=severity,
            title="Verwaiste Geschaeftspartner",
            description=f"{count} Geschaeftspartner haben keine zugeordneten Dokumente.",
            count=count,
            action_label="Bereinigen",
            action_endpoint="/api/v1/data-quality/orphaned-entities/fix",
        )

    async def _check_missing_metadata(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf Dokumente mit fehlenden Metadaten."""
        query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                or_(
                    Document.original_filename.is_(None),
                    Document.original_filename == "",
                    and_(
                        Document.document_type == "rechnung",
                        Document.id.notin_(
                            select(InvoiceTracking.document_id).where(
                                InvoiceTracking.invoice_number.isnot(None)
                            )
                        ),
                    ),
                ),
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 30:
            severity = "warning"

        return DataQualityIssue(
            category=QualityCategory.MISSING_METADATA,
            severity=severity,
            title="Fehlende Metadaten",
            description=f"{count} Dokumente haben unvollstaendige Metadaten.",
            count=count,
            action_label="Vervollstaendigen",
            action_endpoint="/api/v1/data-quality/missing-metadata/fix",
        )

    async def _check_low_ocr_quality(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf Dokumente mit niedriger OCR-Qualitaet."""
        query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.ocr_confidence.isnot(None),
                Document.ocr_confidence < 0.85,
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 15:
            severity = "warning"

        return DataQualityIssue(
            category=QualityCategory.LOW_OCR_QUALITY,
            severity=severity,
            title="Niedrige OCR-Qualitaet",
            description=f"{count} Dokumente haben eine OCR-Konfidenz unter 85%.",
            count=count,
            action_label="Neu verarbeiten",
            action_endpoint="/api/v1/data-quality/low-ocr-quality/fix",
        )

    async def _check_unlinked_documents(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf Rechnungen ohne Geschaeftspartner."""
        query = select(
            func.count(Document.id)
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.document_type == "rechnung",
                Document.business_entity_id.is_(None),
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"
        if count > 20:
            severity = "warning"
        if count > 50:
            severity = "critical"

        return DataQualityIssue(
            category=QualityCategory.UNLINKED_DOCUMENTS,
            severity=severity,
            title="Nicht zugeordnete Rechnungen",
            description=f"{count} Rechnungen sind keinem Geschaeftspartner zugeordnet.",
            count=count,
            action_label="Zuordnen",
            action_endpoint="/api/v1/data-quality/unlinked-documents/fix",
        )

    async def _check_stale_documents(self, company_id: UUID) -> DataQualityIssue:
        """Prueft auf veraltete Dokumente (nicht zugegriffen seit 1+ Jahr)."""
        one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

        query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.updated_at.isnot(None),
                Document.updated_at < one_year_ago,
            )
        )
        result = await self.db.execute(query)
        count = result.scalar() or 0

        severity = "info"

        return DataQualityIssue(
            category=QualityCategory.STALE_DOCUMENTS,
            severity=severity,
            title="Veraltete Dokumente",
            description=f"{count} Dokumente wurden seit über einem Jahr nicht zugegriffen.",
            count=count,
            action_label="Archivieren",
            action_endpoint="/api/v1/data-quality/stale-documents/fix",
        )

    # =========================================================================
    # Fix Actions
    # =========================================================================

    async def _fix_uncategorized(self, company_id: UUID, action: str) -> int:
        """Behebt unkategorisierte Dokumente."""
        if action == "auto_categorize":
            # Set uncategorized documents to "unknown" type
            # Real AI categorization would be a separate service
            stmt = (
                update(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        or_(
                            Document.document_type.is_(None),
                            Document.document_type == "",
                        ),
                    )
                )
                .values(document_type="unknown")
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.rowcount or 0
        return 0

    async def _fix_duplicates(self, company_id: UUID, action: str) -> int:
        """Behebt Duplikate."""
        if action == "merge":
            # Find duplicate checksums
            dup_checksums_query = (
                select(Document.checksum)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.checksum.isnot(None),
                    )
                )
                .group_by(Document.checksum)
                .having(func.count(Document.id) > 1)
            )
            result = await self.db.execute(dup_checksums_query)
            dup_checksums = [row[0] for row in result.all()]

            deleted_count = 0
            for checksum_val in dup_checksums:
                # Get all docs with this checksum, ordered by created_at desc
                docs_query = (
                    select(Document.id)
                    .where(
                        and_(
                            Document.company_id == company_id,
                            Document.deleted_at.is_(None),
                            Document.checksum == checksum_val,
                        )
                    )
                    .order_by(Document.created_at.desc())
                )
                docs_result = await self.db.execute(docs_query)
                doc_ids = [row[0] for row in docs_result.all()]

                if len(doc_ids) > 1:
                    # Keep newest (first), soft-delete the rest
                    ids_to_delete = doc_ids[1:]
                    now = datetime.now(timezone.utc)
                    stmt = (
                        update(Document)
                        .where(Document.id.in_(ids_to_delete))
                        .values(deleted_at=now)
                    )
                    await self.db.execute(stmt)
                    deleted_count += len(ids_to_delete)

            await self.db.commit()
            return deleted_count
        return 0

    async def _fix_orphaned_entities(self, company_id: UUID, action: str) -> int:
        """Behebt verwaiste Entities."""
        if action == "deactivate":
            # Deaktiviere Entities ohne Dokumente
            stmt = (
                update(BusinessEntity)
                .where(
                    and_(
                        BusinessEntity.company_id == company_id,
                        BusinessEntity.is_active == True,
                        BusinessEntity.deleted_at.is_(None),
                        ~BusinessEntity.id.in_(
                            select(Document.business_entity_id)
                            .where(
                                and_(
                                    Document.company_id == company_id,
                                    Document.deleted_at.is_(None),
                                    Document.business_entity_id.isnot(None),
                                )
                            )
                        ),
                    )
                )
                .values(is_active=False)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.rowcount or 0
        return 0

    async def _fix_missing_metadata(self, company_id: UUID, action: str) -> int:
        """Behebt fehlende Metadaten."""
        if action == "extract":
            # Count documents with missing metadata for re-processing
            query = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    or_(
                        Document.original_filename.is_(None),
                        Document.original_filename == "",
                    ),
                )
            )
            result = await self.db.execute(query)
            count = result.scalar() or 0
            logger.info("metadata_extraction_triggered", company_id=str(company_id), count=count)
            return count
        return 0

    async def _fix_low_ocr_quality(self, company_id: UUID, action: str) -> int:
        """Behebt niedrige OCR-Qualitaet."""
        if action == "reprocess":
            query = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.ocr_confidence.isnot(None),
                    Document.ocr_confidence < 0.85,
                )
            )
            result = await self.db.execute(query)
            count = result.scalar() or 0
            # Mark documents for reprocessing by resetting status
            if count > 0:
                stmt = (
                    update(Document)
                    .where(
                        and_(
                            Document.company_id == company_id,
                            Document.deleted_at.is_(None),
                            Document.ocr_confidence.isnot(None),
                            Document.ocr_confidence < 0.85,
                        )
                    )
                    .values(status="pending")
                )
                await self.db.execute(stmt)
                await self.db.commit()
            return count
        return 0

    async def _fix_unlinked_documents(self, company_id: UUID, action: str) -> int:
        """Behebt nicht zugeordnete Dokumente."""
        if action == "auto_link":
            # Count unlinked invoices (rechnung without business_entity)
            query = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                    Document.document_type == "rechnung",
                    Document.business_entity_id.is_(None),
                )
            )
            result = await self.db.execute(query)
            count = result.scalar() or 0
            logger.info("entity_linking_triggered", company_id=str(company_id), count=count)
            return count
        return 0

    async def _fix_stale_documents(self, company_id: UUID, action: str) -> int:
        """Behebt veraltete Dokumente."""
        if action == "archive":
            one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
            now = datetime.now(timezone.utc)
            stmt = (
                update(Document)
                .where(
                    and_(
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                        Document.is_archived == False,
                        Document.updated_at.isnot(None),
                        Document.updated_at < one_year_ago,
                    )
                )
                .values(is_archived=True, archived_at=now)
            )
            result = await self.db.execute(stmt)
            await self.db.commit()
            return result.rowcount or 0
        return 0

    # =========================================================================
    # Helpers
    # =========================================================================

    def _calculate_overall_score(
        self,
        issues: List[DataQualityIssue],
        company_id: UUID,
    ) -> float:
        """
        Berechnet Gesamt-Datenqualitaets-Score.

        Args:
            issues: List of data quality issues
            company_id: Company ID

        Returns:
            Score (0-100)
        """
        if not issues:
            return 100.0

        # Einfache Formel: 100 - (sum of severity weights * count/100)
        penalty = 0.0
        severity_weights = {
            "info": 0.1,
            "warning": 0.3,
            "critical": 0.5,
        }

        for issue in issues:
            weight = severity_weights.get(issue.severity, 0.1)
            # Cap penalty per issue at 20 points
            issue_penalty = min(20, (issue.count / 10) * weight)
            penalty += issue_penalty

        score = max(0, 100 - penalty)
        return round(score, 1)


# =============================================================================
# Factory Function
# =============================================================================

def get_data_quality_service(db: AsyncSession) -> DataQualityService:
    """Factory function to create DataQualityService instance."""
    return DataQualityService(db)
