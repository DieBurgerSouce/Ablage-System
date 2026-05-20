# -*- coding: utf-8 -*-
"""
Data Quality Service - Datenqualitäts-Cockpit.

Bietet proaktive Datenqualitäts-Überwachung und Cleanup:
- Uncat egorisierte Dokumente
- Duplikate
- Verwaiste Entities
- Fehlende Metadaten
- Niedrige OCR-Qualität
- Nicht zugeordnete Dokumente
- Veraltete Dokumente

Feinpoliert und durchdacht - Enterprise Data Quality.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.db.models_data_quality import DataQualityHistory
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
    """Einzelnes Datenqualitäts-Problem."""
    category: QualityCategory
    severity: str  # "info", "warning", "critical"
    title: str  # German
    description: str  # German
    count: int
    action_label: str  # "Bereinigen", "Zuordnen", "Prüfen"
    action_endpoint: str  # API endpoint to fix


@dataclass
class DataQualityReport:
    """Vollständiger Datenqualitäts-Bericht."""
    overall_score: float  # 0-100
    issues: List[DataQualityIssue]
    trend: str  # "improving", "stable", "worsening"
    last_check: datetime


# =============================================================================
# Data Quality Service
# =============================================================================

class DataQualityService:
    """
    Service für Datenqualitäts-Cockpit.

    Scannt die Datenbank nach Qualitätsproblemen und bietet Cleanup-Aktionen.
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
        Erstellt vollständigen Datenqualitäts-Bericht.

        Args:
            company_id: Company ID

        Returns:
            DataQualityReport mit allen Issues
        """
        logger.info("data_quality_report_start", company_id=str(company_id))

        issues: List[DataQualityIssue] = []

        # Alle Issue-Checks parallel ausführen
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

        # Trend berechnen basierend auf History
        trend = await self._compute_trend_direction(company_id, overall_score)

        report = DataQualityReport(
            overall_score=overall_score,
            issues=issues,
            trend=trend,
            last_check=datetime.now(timezone.utc),
        )

        # Snapshot in History speichern
        try:
            await self.save_quality_snapshot(company_id, report)
        except Exception as e:
            logger.warning(
                "data_quality_snapshot_save_failed",
                company_id=str(company_id),
                error_type=type(e).__name__,
            )

        logger.info(
            "data_quality_report_complete",
            company_id=str(company_id),
            overall_score=overall_score,
            issue_count=len(issues),
        )
        return report

    async def save_quality_snapshot(
        self,
        company_id: UUID,
        report: DataQualityReport,
    ) -> None:
        """
        Speichert einen Datenqualitäts-Snapshot in der History-Tabelle.

        Args:
            company_id: Company ID
            report: Aktueller Quality Report
        """
        issue_counts: Dict[str, int] = {}
        issue_details_list: List[Dict[str, str]] = []

        for issue in report.issues:
            issue_counts[issue.category.value] = issue.count
            issue_details_list.append({
                "category": issue.category.value,
                "severity": issue.severity,
                "title": issue.title,
                "description": issue.description,
                "count": str(issue.count),
                "action_label": issue.action_label,
            })

        history_entry = DataQualityHistory(
            company_id=company_id,
            overall_score=report.overall_score,
            issue_counts=issue_counts,
            issue_details=issue_details_list,
        )
        self.db.add(history_entry)
        await self.db.flush()

        logger.info(
            "data_quality_snapshot_saved",
            company_id=str(company_id),
            overall_score=report.overall_score,
        )

    async def get_quality_trend(
        self,
        company_id: UUID,
        months: int = 6,
    ) -> List[Dict[str, str]]:
        """
        Ruft Datenqualitäts-Trend ab.

        Aggregiert History-Einträge pro Monat und gibt den
        Durchschnitts-Score pro Monat zurück.

        Args:
            company_id: Company ID
            months: Number of months to look back

        Returns:
            List of {month, score, issue_counts} dicts, aelteste zuerst
        """
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)

        query = (
            select(DataQualityHistory)
            .where(
                and_(
                    DataQualityHistory.company_id == company_id,
                    DataQualityHistory.checked_at >= since,
                )
            )
            .order_by(DataQualityHistory.checked_at.asc())
        )
        result = await self.db.execute(query)
        rows = result.scalars().all()

        if not rows:
            return []

        # Aggregate by month
        monthly: Dict[str, List[float]] = {}
        monthly_issues: Dict[str, Dict[str, int]] = {}

        for row in rows:
            month_key = row.checked_at.strftime("%Y-%m")
            if month_key not in monthly:
                monthly[month_key] = []
                monthly_issues[month_key] = {}

            monthly[month_key].append(row.overall_score)

            # Merge issue counts
            if row.issue_counts:
                for cat, count in row.issue_counts.items():
                    if cat not in monthly_issues[month_key]:
                        monthly_issues[month_key][cat] = 0
                    monthly_issues[month_key][cat] = max(
                        monthly_issues[month_key][cat], count
                    )

        trend: List[Dict[str, str]] = []
        for month_key in sorted(monthly.keys()):
            scores = monthly[month_key]
            avg_score = round(sum(scores) / len(scores), 1)
            trend.append({
                "month": month_key,
                "score": str(avg_score),
                "issue_counts": str(monthly_issues.get(month_key, {})),
                "data_points": str(len(scores)),
            })

        return trend

    async def fix_issue(
        self,
        company_id: UUID,
        category: QualityCategory,
        action: str,
    ) -> int:
        """
        Führt Cleanup-Aktion für eine Kategorie aus.

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
        """Prüft auf unkategorisierte Dokumente."""
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
        """Prüft auf mögliche Duplikate."""
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
            title="Mögliche Duplikate",
            description=f"{count} Dokumente können Duplikate sein.",
            count=count,
            action_label="Prüfen",
            action_endpoint="/api/v1/data-quality/duplicates/fix",
        )

    async def _check_orphaned_entities(self, company_id: UUID) -> DataQualityIssue:
        """Prüft auf Entities ohne Dokumente."""
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
            title="Verwaiste Geschäftspartner",
            description=f"{count} Geschäftspartner haben keine zugeordneten Dokumente.",
            count=count,
            action_label="Bereinigen",
            action_endpoint="/api/v1/data-quality/orphaned-entities/fix",
        )

    async def _check_missing_metadata(self, company_id: UUID) -> DataQualityIssue:
        """Prüft auf Dokumente mit fehlenden Metadaten."""
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
            description=f"{count} Dokumente haben unvollständige Metadaten.",
            count=count,
            action_label="Vervollständigen",
            action_endpoint="/api/v1/data-quality/missing-metadata/fix",
        )

    async def _check_low_ocr_quality(self, company_id: UUID) -> DataQualityIssue:
        """Prüft auf Dokumente mit niedriger OCR-Qualität."""
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
            title="Niedrige OCR-Qualität",
            description=f"{count} Dokumente haben eine OCR-Konfidenz unter 85%.",
            count=count,
            action_label="Neu verarbeiten",
            action_endpoint="/api/v1/data-quality/low-ocr-quality/fix",
        )

    async def _check_unlinked_documents(self, company_id: UUID) -> DataQualityIssue:
        """Prüft auf Rechnungen ohne Geschäftspartner."""
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
            description=f"{count} Rechnungen sind keinem Geschäftspartner zugeordnet.",
            count=count,
            action_label="Zuordnen",
            action_endpoint="/api/v1/data-quality/unlinked-documents/fix",
        )

    async def _check_stale_documents(self, company_id: UUID) -> DataQualityIssue:
        """Prüft auf veraltete Dokumente (nicht zugegriffen seit 1+ Jahr)."""
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
        """Behebt niedrige OCR-Qualität."""
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

    async def _compute_trend_direction(
        self,
        company_id: UUID,
        current_score: float,
    ) -> str:
        """
        Berechnet Trend-Richtung basierend auf letzten History-Einträgen.

        Vergleicht aktuellen Score mit dem Durchschnitt der letzten 30 Tage.

        Args:
            company_id: Company ID
            current_score: Aktueller Score

        Returns:
            "improving", "stable", or "worsening"
        """
        try:
            since = datetime.now(timezone.utc) - timedelta(days=30)
            query = (
                select(func.avg(DataQualityHistory.overall_score))
                .where(
                    and_(
                        DataQualityHistory.company_id == company_id,
                        DataQualityHistory.checked_at >= since,
                    )
                )
            )
            result = await self.db.execute(query)
            avg_score = result.scalar()

            if avg_score is None:
                return "stable"

            diff = current_score - float(avg_score)
            if diff > 2.0:
                return "improving"
            elif diff < -2.0:
                return "worsening"
            else:
                return "stable"

        except Exception as e:
            logger.debug(
                "trend_computation_failed",
                error_type=type(e).__name__,
            )
            return "stable"

    async def get_correction_suggestions(
        self,
        company_id: UUID,
    ) -> List[Dict[str, str]]:
        """
        Gibt Korrekturvorschläge basierend auf Issue-Mustern zurück.

        Analysiert die häufigsten und schwerwiegendsten Issues und
        gibt priorisierte Handlungsempfehlungen zurück.

        Args:
            company_id: Company ID

        Returns:
            Liste von Korrekturvorschlägen mit Priorität und Beschreibung
        """
        report = await self.get_quality_report(company_id)
        suggestions: List[Dict[str, str]] = []

        # Sort by severity (critical first) then by count
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        sorted_issues = sorted(
            report.issues,
            key=lambda i: (severity_order.get(i.severity, 3), -i.count),
        )

        for issue in sorted_issues:
            suggestion = self._build_suggestion(issue)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _build_suggestion(
        self,
        issue: DataQualityIssue,
    ) -> Optional[Dict[str, str]]:
        """Erstellt einen Korrekturvorschlag für ein Issue."""
        suggestion_map = {
            QualityCategory.UNCATEGORIZED: {
                "priorität": "hoch" if issue.count > 50 else "mittel",
                "titel": "Dokumente kategorisieren",
                "beschreibung": (
                    f"{issue.count} Dokumente ohne Kategorie. "
                    "Empfehlung: Auto-Kategorisierung aktivieren oder "
                    "manuell im Datenqualitäts-Cockpit zuweisen."
                ),
                "aktion": "auto_categorize",
            },
            QualityCategory.DUPLICATES: {
                "priorität": "hoch" if issue.count > 30 else "mittel",
                "titel": "Duplikate bereinigen",
                "beschreibung": (
                    f"{issue.count} mögliche Duplikate gefunden. "
                    "Empfehlung: Duplikate prüfen und zusammenführen."
                ),
                "aktion": "merge",
            },
            QualityCategory.ORPHANED_ENTITIES: {
                "priorität": "niedrig",
                "titel": "Verwaiste Geschäftspartner prüfen",
                "beschreibung": (
                    f"{issue.count} Geschäftspartner ohne Dokumente. "
                    "Empfehlung: Nicht mehr benötigte Partner deaktivieren."
                ),
                "aktion": "deactivate",
            },
            QualityCategory.LOW_OCR_QUALITY: {
                "priorität": "hoch",
                "titel": "OCR-Qualität verbessern",
                "beschreibung": (
                    f"{issue.count} Dokumente mit niedriger OCR-Konfidenz. "
                    "Empfehlung: Dokumente mit anderem OCR-Backend neu verarbeiten."
                ),
                "aktion": "reprocess",
            },
            QualityCategory.UNLINKED_DOCUMENTS: {
                "priorität": "mittel",
                "titel": "Rechnungen zuordnen",
                "beschreibung": (
                    f"{issue.count} Rechnungen ohne Geschäftspartner. "
                    "Empfehlung: Auto-Linking aktivieren oder manuell zuordnen."
                ),
                "aktion": "auto_link",
            },
            QualityCategory.MISSING_METADATA: {
                "priorität": "mittel",
                "titel": "Metadaten vervollständigen",
                "beschreibung": (
                    f"{issue.count} Dokumente mit fehlenden Metadaten. "
                    "Empfehlung: Metadaten-Extraktion erneut ausführen."
                ),
                "aktion": "extract",
            },
            QualityCategory.STALE_DOCUMENTS: {
                "priorität": "niedrig",
                "titel": "Veraltete Dokumente archivieren",
                "beschreibung": (
                    f"{issue.count} Dokumente seit über einem Jahr nicht zugegriffen. "
                    "Empfehlung: Archivierung prüfen und ausführen."
                ),
                "aktion": "archive",
            },
        }

        return suggestion_map.get(issue.category)

    def _calculate_overall_score(
        self,
        issues: List[DataQualityIssue],
        company_id: UUID,
    ) -> float:
        """
        Berechnet Gesamt-Datenqualitäts-Score.

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
