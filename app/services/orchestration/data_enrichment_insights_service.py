# -*- coding: utf-8 -*-
"""
Data Enrichment Insights Service.

Enterprise Feature: Proaktive Erkennung von Datenanreicherungsmöglichkeiten.

Dieses Modul analysiert Stammdaten und erkennt:

- Fehlende Stammdaten: "Lieferant XY hat keine IBAN hinterlegt"
- Duplikate: "2 Lieferanten mit ähnlichem Namen gefunden"
- Inkonsistenzen: "Adresse weicht in 3 Dokumenten ab"
- Veraltete Daten: "Kontaktdaten nicht seit 2 Jahren aktualisiert"

Integration mit: EntitySearchService, LexwareImportService, MasterDataHygieneService
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.orchestration.proactive_insights_service import (
    ExtractedEntity,
    EntityType,
    InsightPriority,
    InsightType,
    ProactiveInsight,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class DataIssueType(str, Enum):
    """Typ des Datenproblems."""
    MISSING_FIELD = "missing_field"           # Feld fehlt
    DUPLICATE = "duplicate"                    # Duplikat erkannt
    INCONSISTENT = "inconsistent"             # Inkonsistente Daten
    OUTDATED = "outdated"                     # Veraltete Daten
    INVALID_FORMAT = "invalid_format"         # Unguelitges Format
    UNLINKED = "unlinked"                     # Nicht verknüpft


class DataQualitySeverity(str, Enum):
    """Schweregrad des Datenproblems."""
    CRITICAL = "critical"   # Verhindert Geschäftsprozesse
    HIGH = "high"           # Kann zu Fehlern führen
    MEDIUM = "medium"       # Sollte korrigiert werden
    LOW = "low"             # Nice-to-have


@dataclass
class DataIssue:
    """Ein Datenproblem mit Details."""
    issue_type: DataIssueType
    severity: DataQualitySeverity
    entity_id: UUID
    entity_name: str
    field_name: Optional[str] = None
    description: str = ""
    suggestion: Optional[str] = None
    related_entities: List[UUID] = field(default_factory=list)
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        severity_priority_map = {
            DataQualitySeverity.CRITICAL: InsightPriority.CRITICAL,
            DataQualitySeverity.HIGH: InsightPriority.HIGH,
            DataQualitySeverity.MEDIUM: InsightPriority.MEDIUM,
            DataQualitySeverity.LOW: InsightPriority.LOW,
        }

        issue_type_map = {
            DataIssueType.MISSING_FIELD: InsightType.WARNING,
            DataIssueType.DUPLICATE: InsightType.WARNING,
            DataIssueType.INCONSISTENT: InsightType.WARNING,
            DataIssueType.OUTDATED: InsightType.INFORMATION,
            DataIssueType.INVALID_FORMAT: InsightType.WARNING,
            DataIssueType.UNLINKED: InsightType.INFORMATION,
        }

        return ProactiveInsight(
            insight_type=issue_type_map.get(self.issue_type, InsightType.INFORMATION),
            priority=severity_priority_map.get(self.severity, InsightPriority.MEDIUM),
            title=self._generate_title(),
            message=self.description,
            detail=self.suggestion or "",
            action_url=self.action_url,
            action_label=self.action_label,
            source_rule=f"data_{self.issue_type.value}",
            related_entities=[
                ExtractedEntity(
                    entity_type=EntityType.SUPPLIER,
                    entity_id=self.entity_id,
                    entity_name=self.entity_name,
                    confidence=1.0,
                )
            ],
        )

    def _generate_title(self) -> str:
        """Generiert Titel basierend auf Issue-Typ."""
        title_templates = {
            DataIssueType.MISSING_FIELD: f"Fehlende Daten: {self.entity_name}",
            DataIssueType.DUPLICATE: f"Mögliches Duplikat: {self.entity_name}",
            DataIssueType.INCONSISTENT: f"Inkonsistente Daten: {self.entity_name}",
            DataIssueType.OUTDATED: f"Veraltete Daten: {self.entity_name}",
            DataIssueType.INVALID_FORMAT: f"Unguelitges Format: {self.entity_name}",
            DataIssueType.UNLINKED: f"Nicht verknüpft: {self.entity_name}",
        }
        return title_templates.get(self.issue_type, f"Datenproblem: {self.entity_name}")


@dataclass
class DataEnrichmentResult:
    """Ergebnis einer Datenanreicherungs-Prüfung."""
    issue_type: DataIssueType
    title: str
    message: str
    detail: str = ""
    severity: str = "medium"
    affected_field: Optional[str] = None
    suggested_value: Optional[str] = None
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    confidence: float = 0.0

    def to_insight(self) -> ProactiveInsight:
        """Konvertiert zu ProactiveInsight."""
        priority_map = {"critical": InsightPriority.CRITICAL, "high": InsightPriority.HIGH,
                        "medium": InsightPriority.MEDIUM, "low": InsightPriority.LOW}
        return ProactiveInsight(
            insight_type=InsightType.WARNING if self.severity in ("critical", "high") else InsightType.SUGGESTION,
            priority=priority_map.get(self.severity, InsightPriority.MEDIUM),
            title=self.title,
            message=self.message,
            detail=self.detail,
            confidence=self.confidence,
        )


@dataclass
class DataQualitySummary:
    """Zusammenfassung der Datenqualität."""
    total_entities: int = 0
    entities_with_issues: int = 0
    total_issues: int = 0
    issues_by_type: Dict[DataIssueType, int] = field(default_factory=dict)
    quality_score: float = 100.0
    grade: str = "A"


class DataEnrichmentInsightsService:
    """
    Service für proaktive Daten-Anreicherungsvorschläge.

    Analysiert Stammdaten und erkennt Verbesserungsmöglichkeiten
    für die Datenqualität.
    """

    def __init__(self) -> None:
        # Wichtige Felder pro Entity-Typ
        self._required_fields = {
            "supplier": ["name", "iban", "vat_id", "address_street", "address_city"],
            "customer": ["name", "customer_number", "address_street", "address_city"],
        }

        # Schwellwerte
        self._outdated_threshold_days = 365  # 1 Jahr ohne Update = veraltet
        self._similarity_threshold = 0.85    # 85% Ähnlichkeit = potentielles Duplikat

        logger.info("data_enrichment_insights_service_initialized")

    async def check_all_data_issues(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Prüft alle Datenprobleme und generiert Insights.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für alle Datenprobleme
        """
        logger.info(
            "checking_all_data_issues",
            company_id=str(company_id),
        )

        all_insights: List[ProactiveInsight] = []

        # Parallel alle Data-Checks ausführen
        results = await asyncio.gather(
            self.detect_missing_master_data(db, company_id),
            self.detect_duplicates(db, company_id),
            self.detect_inconsistencies(db, company_id),
            self.detect_outdated_data(db, company_id),
            self.detect_unlinked_documents(db, company_id),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                logger.warning(
                    "data_check_failed",
                    error=str(result),
                )
            elif isinstance(result, list):
                all_insights.extend(result)

        # Nach Priorität sortieren
        priority_order = {
            InsightPriority.CRITICAL: 0,
            InsightPriority.HIGH: 1,
            InsightPriority.MEDIUM: 2,
            InsightPriority.LOW: 3,
        }
        all_insights.sort(key=lambda i: priority_order.get(i.priority, 4))

        logger.info(
            "all_data_issues_checked",
            total_insights=len(all_insights),
        )

        return all_insights

    async def detect_missing_master_data(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt fehlende Stammdaten bei Entitäten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für fehlende Daten
        """
        from app.db.models import BusinessEntity

        try:
            # Alle aktiven Entitäten laden
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active.is_(True),
                )
            )

            result = await db.execute(query)
            entities: Sequence[BusinessEntity] = result.scalars().all()

            issues: List[DataIssue] = []

            for entity in entities:
                entity_type = entity.entity_type or "supplier"
                required = self._required_fields.get(entity_type, [])

                missing_fields = []
                for field_name in required:
                    value = getattr(entity, field_name, None)
                    if value is None or (isinstance(value, str) and not value.strip()):
                        missing_fields.append(field_name)

                if missing_fields:
                    # Schweregrad bestimmen
                    critical_fields = {"iban", "vat_id", "customer_number"}
                    has_critical = any(f in critical_fields for f in missing_fields)

                    severity = DataQualitySeverity.HIGH if has_critical else DataQualitySeverity.MEDIUM

                    field_labels = {
                        "iban": "IBAN",
                        "vat_id": "USt-IdNr.",
                        "customer_number": "Kundennummer",
                        "address_street": "Strasse",
                        "address_city": "Stadt",
                        "name": "Name",
                    }
                    missing_labels = [field_labels.get(f, f) for f in missing_fields]

                    issue = DataIssue(
                        issue_type=DataIssueType.MISSING_FIELD,
                        severity=severity,
                        entity_id=entity.id,
                        entity_name=entity.name or "Unbekannt",
                        field_name=", ".join(missing_fields),
                        description=f"Fehlende Felder: {', '.join(missing_labels)}",
                        suggestion="Bitte vervollständigen Sie die Stammdaten.",
                        action_url=f"/entities/{entity.id}/edit",
                        action_label="Daten ergaenzen",
                        metadata={
                            "missing_fields": missing_fields,
                            "entity_type": entity_type,
                        },
                    )
                    issues.append(issue)

            insights = [issue.to_insight() for issue in issues]

            logger.info(
                "missing_data_detected",
                company_id=str(company_id),
                issues_count=len(issues),
            )

            return insights

        except Exception as e:
            logger.warning(
                "missing_data_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_duplicates(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt potenzielle Duplikate bei Entitäten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Duplikate
        """
        from app.db.models import BusinessEntity

        try:
            # Alle aktiven Entitäten laden
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active.is_(True),
                    BusinessEntity.name.isnot(None),
                )
            )

            result = await db.execute(query)
            entities: Sequence[BusinessEntity] = result.scalars().all()

            issues: List[DataIssue] = []
            processed_pairs: Set[Tuple[UUID, UUID]] = set()

            for i, entity1 in enumerate(entities):
                for entity2 in entities[i + 1:]:
                    # Bereits verarbeitete Paare überspringen
                    pair_key = tuple(sorted([entity1.id, entity2.id]))
                    if pair_key in processed_pairs:
                        continue

                    similarity = self._calculate_name_similarity(
                        entity1.name or "",
                        entity2.name or "",
                    )

                    if similarity >= self._similarity_threshold:
                        processed_pairs.add(pair_key)

                        # Zusätzliche Prüfungen
                        same_iban = (
                            entity1.iban and entity2.iban and
                            entity1.iban == entity2.iban
                        )
                        same_vat = (
                            entity1.vat_id and entity2.vat_id and
                            entity1.vat_id == entity2.vat_id
                        )

                        if same_iban or same_vat:
                            severity = DataQualitySeverity.CRITICAL
                            reason = "Gleiche IBAN" if same_iban else "Gleiche USt-IdNr."
                        elif similarity >= 0.95:
                            severity = DataQualitySeverity.HIGH
                            reason = f"{similarity * 100:.0f}% Namensähnlichkeit"
                        else:
                            severity = DataQualitySeverity.MEDIUM
                            reason = f"{similarity * 100:.0f}% Namensähnlichkeit"

                        issue = DataIssue(
                            issue_type=DataIssueType.DUPLICATE,
                            severity=severity,
                            entity_id=entity1.id,
                            entity_name=entity1.name or "Unbekannt",
                            description=f"Ähnlich zu '{entity2.name}': {reason}",
                            suggestion="Prüfen Sie, ob diese Einträge zusammengeführt werden sollten.",
                            related_entities=[entity2.id],
                            action_url=f"/entities/merge?ids={entity1.id},{entity2.id}",
                            action_label="Zusammenführen prüfen",
                            metadata={
                                "similarity": similarity,
                                "other_entity_id": str(entity2.id),
                                "other_entity_name": entity2.name,
                                "same_iban": same_iban,
                                "same_vat": same_vat,
                            },
                        )
                        issues.append(issue)

            insights = [issue.to_insight() for issue in issues]

            logger.info(
                "duplicates_detected",
                company_id=str(company_id),
                issues_count=len(issues),
            )

            return insights

        except Exception as e:
            logger.warning(
                "duplicate_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_inconsistencies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt Inkonsistenzen in den Daten.

        Vergleicht Stammdaten mit extrahierten Dokumentdaten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für Inkonsistenzen
        """
        from app.db.models import BusinessEntity, Document

        try:
            # Entitäten mit verknüpften Dokumenten finden
            query = select(
                BusinessEntity.id,
                BusinessEntity.name,
                BusinessEntity.address_street,
                BusinessEntity.address_city,
                BusinessEntity.address_postal_code,
                func.count(Document.id).label("doc_count"),
            ).outerjoin(
                Document, Document.linked_entity_id == BusinessEntity.id
            ).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active.is_(True),
                )
            ).group_by(
                BusinessEntity.id,
                BusinessEntity.name,
                BusinessEntity.address_street,
                BusinessEntity.address_city,
                BusinessEntity.address_postal_code,
            ).having(func.count(Document.id) > 0)

            result = await db.execute(query)
            entity_data = result.fetchall()

            issues: List[DataIssue] = []

            for row in entity_data:
                entity_id, name, street, city, postal_code, doc_count = row

                # Extrahierte Adressen aus Dokumenten laden
                doc_query = select(
                    Document.extracted_data,
                ).where(
                    and_(
                        Document.company_id == company_id,
                        Document.linked_entity_id == entity_id,
                        Document.extracted_data.isnot(None),
                    )
                ).limit(10)  # Nur die letzten 10 prüfen

                doc_result = await db.execute(doc_query)
                documents = doc_result.fetchall()

                address_variations: Set[str] = set()
                for doc_row in documents:
                    extracted = doc_row[0] or {}
                    if isinstance(extracted, dict):
                        doc_address = extracted.get("supplier_address") or extracted.get("address", "")
                        if doc_address and isinstance(doc_address, str):
                            address_variations.add(doc_address.strip().lower())

                # Vergleiche mit Stammdaten
                master_address = " ".join(filter(None, [street, postal_code, city])).strip().lower()

                # Wenn verschiedene Adressen in Dokumenten gefunden wurden
                if len(address_variations) > 1:
                    issue = DataIssue(
                        issue_type=DataIssueType.INCONSISTENT,
                        severity=DataQualitySeverity.MEDIUM,
                        entity_id=entity_id,
                        entity_name=name or "Unbekannt",
                        field_name="Adresse",
                        description=f"{len(address_variations)} verschiedene Adressen in Dokumenten gefunden.",
                        suggestion="Prüfen Sie welche Adresse korrekt ist.",
                        action_url=f"/entities/{entity_id}/documents",
                        action_label="Dokumente prüfen",
                        metadata={
                            "variation_count": len(address_variations),
                            "master_address": master_address,
                            "doc_count": doc_count,
                        },
                    )
                    issues.append(issue)

            insights = [issue.to_insight() for issue in issues]

            logger.info(
                "inconsistencies_detected",
                company_id=str(company_id),
                issues_count=len(issues),
            )

            return insights

        except Exception as e:
            logger.warning(
                "inconsistency_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_outdated_data(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt veraltete Stammdaten.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für veraltete Daten
        """
        from app.db.models import BusinessEntity

        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=self._outdated_threshold_days)

            # Entitäten ohne kürzliche Updates finden
            query = select(BusinessEntity).where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active.is_(True),
                    or_(
                        BusinessEntity.updated_at < cutoff,
                        BusinessEntity.updated_at.is_(None),
                    ),
                )
            )

            result = await db.execute(query)
            entities: Sequence[BusinessEntity] = result.scalars().all()

            issues: List[DataIssue] = []

            for entity in entities:
                last_update = entity.updated_at or entity.created_at
                if last_update:
                    days_since_update = (datetime.now(timezone.utc) - last_update).days
                else:
                    days_since_update = self._outdated_threshold_days + 1

                if days_since_update > self._outdated_threshold_days:
                    # Prüfe ob es kürzlich Dokumente gab
                    from app.db.models import Document
                    recent_doc_query = select(func.count()).where(
                        and_(
                            Document.company_id == company_id,
                            Document.linked_entity_id == entity.id,
                            Document.created_at >= cutoff,
                        )
                    )
                    recent_result = await db.execute(recent_doc_query)
                    recent_doc_count = recent_result.scalar() or 0

                    # Nur warnen wenn es aktive Geschäftsbeziehung gibt
                    if recent_doc_count > 0:
                        issue = DataIssue(
                            issue_type=DataIssueType.OUTDATED,
                            severity=DataQualitySeverity.LOW,
                            entity_id=entity.id,
                            entity_name=entity.name or "Unbekannt",
                            description=f"Stammdaten nicht aktualisiert seit {days_since_update} Tagen, aber {recent_doc_count} neue Dokumente.",
                            suggestion="Prüfen Sie ob die Stammdaten noch aktuell sind.",
                            action_url=f"/entities/{entity.id}/edit",
                            action_label="Daten prüfen",
                            metadata={
                                "days_since_update": days_since_update,
                                "recent_documents": recent_doc_count,
                                "last_update": last_update.isoformat() if last_update else None,
                            },
                        )
                        issues.append(issue)

            insights = [issue.to_insight() for issue in issues]

            logger.info(
                "outdated_data_detected",
                company_id=str(company_id),
                issues_count=len(issues),
            )

            return insights

        except Exception as e:
            logger.warning(
                "outdated_data_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    async def detect_unlinked_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[ProactiveInsight]:
        """
        Erkennt Dokumente ohne Entity-Verknüpfung.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Liste von ProactiveInsights für nicht verknüpfte Dokumente
        """
        from app.db.models import Document


        try:
            # Dokumente ohne Entity-Link zaehlen
            query = select(
                Document.document_type,
                func.count().label("count"),
            ).where(
                and_(
                    Document.company_id == company_id,
                    Document.linked_entity_id.is_(None),
                    Document.is_deleted.is_(False),
                    Document.document_type.in_(["invoice", "contract", "quote"]),
                )
            ).group_by(Document.document_type)

            result = await db.execute(query)
            unlinked_counts = result.fetchall()

            issues: List[DataIssue] = []

            for row in unlinked_counts:
                doc_type, count = row

                if count >= 5:  # Nur bei relevanter Anzahl warnen
                    type_labels = {
                        "invoice": "Rechnungen",
                        "contract": "Verträge",
                        "quote": "Angebote",
                    }
                    type_label = type_labels.get(doc_type, doc_type)

                    issue = DataIssue(
                        issue_type=DataIssueType.UNLINKED,
                        severity=DataQualitySeverity.MEDIUM if count > 20 else DataQualitySeverity.LOW,
                        entity_id=company_id,
                        entity_name=f"{count} {type_label}",
                        description=f"{count} {type_label} sind nicht mit einem Geschäftspartner verknüpft.",
                        suggestion="Verknüpfen Sie die Dokumente für bessere Auswertungen.",
                        action_url=f"/documents?type={doc_type}&unlinked=true",
                        action_label="Dokumente verknüpfen",
                        metadata={
                            "document_type": doc_type,
                            "unlinked_count": count,
                        },
                    )
                    issues.append(issue)

            insights = [issue.to_insight() for issue in issues]

            logger.info(
                "unlinked_documents_detected",
                company_id=str(company_id),
                issues_count=len(issues),
            )

            return insights

        except Exception as e:
            logger.warning(
                "unlinked_documents_detection_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return []

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Berechnet die Ähnlichkeit zweier Namen.

        Verwendet eine Kombination aus:
        - Levenshtein-Distanz
        - Token-Set-Ratio

        Args:
            name1: Erster Name
            name2: Zweiter Name

        Returns:
            Ähnlichkeit zwischen 0.0 und 1.0
        """
        if not name1 or not name2:
            return 0.0

        # Normalisierung
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        if n1 == n2:
            return 1.0

        # Einfache Token-basierte Ähnlichkeit
        tokens1 = set(n1.split())
        tokens2 = set(n2.split())

        if not tokens1 or not tokens2:
            return 0.0

        # Jaccard-Ähnlichkeit
        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        jaccard = len(intersection) / len(union) if union else 0.0

        # Containment (ist einer im anderen enthalten)
        containment = max(
            len(intersection) / len(tokens1) if tokens1 else 0,
            len(intersection) / len(tokens2) if tokens2 else 0,
        )

        # Gewichteter Durchschnitt
        return 0.6 * jaccard + 0.4 * containment

    async def get_data_quality_summary(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Erstellt eine Zusammenfassung der Datenqualität.

        Args:
            db: Datenbank-Session
            company_id: ID der Company

        Returns:
            Zusammenfassung mit Scores und Issues
        """
        insights = await self.check_all_data_issues(db, company_id)

        # Zaehle Issues nach Typ und Schweregrad
        by_type: Dict[str, int] = defaultdict(int)
        by_severity: Dict[str, int] = defaultdict(int)

        for insight in insights:
            rule_type = insight.source_rule or "unknown"
            by_type[rule_type] += 1
            by_severity[insight.priority.value] += 1

        # Berechne Qualitäts-Score (100 = perfekt)
        penalty = (
            by_severity.get("critical", 0) * 20 +
            by_severity.get("high", 0) * 10 +
            by_severity.get("medium", 0) * 5 +
            by_severity.get("low", 0) * 2
        )
        quality_score = max(0, 100 - penalty)

        return {
            "quality_score": quality_score,
            "total_issues": len(insights),
            "by_type": dict(by_type),
            "by_severity": dict(by_severity),
            "grade": self._score_to_grade(quality_score),
        }

    def _score_to_grade(self, score: float) -> str:
        """Konvertiert Score zu Note."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"


# Singleton-Instanz
_data_enrichment_instance: Optional[DataEnrichmentInsightsService] = None


def get_data_enrichment_insights_service() -> DataEnrichmentInsightsService:
    """Gibt die Singleton-Instanz des Data Enrichment Insights Service zurück."""
    global _data_enrichment_instance
    if _data_enrichment_instance is None:
        _data_enrichment_instance = DataEnrichmentInsightsService()
    return _data_enrichment_instance
