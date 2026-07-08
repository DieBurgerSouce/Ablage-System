# -*- coding: utf-8 -*-
"""
AutoFilingService - Automatische Dokumentenablage.

Feature #7: Automation 2.0
- ML-basierte oder regelbasierte Dokumentenklassifizierung
- Confidence-Schwelle für automatische Ablage
- Trainingsstatistiken und Accuracy-Tracking
- Vorschläge für Ordner/Kategorie

Nutzt models_approval_extended für AutoFilingRule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document
from app.db.models_approval_extended import AutoFilingRule
from app.db.models_folder import FolderDocument

logger = structlog.get_logger(__name__)


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class FilingSuggestion:
    """Vorschlag für automatische Ablage."""

    rule_id: UUID
    rule_name: str
    target_folder_id: Optional[UUID]
    target_category: Optional[str]
    confidence: float  # 0.0 - 1.0
    model_type: str  # "ml" oder "rule"
    auto_file: bool  # True wenn Confidence >= Schwelle


@dataclass
class FilingResult:
    """Ergebnis einer automatischen Ablage."""

    document_id: UUID
    filed: bool
    suggestion: Optional[FilingSuggestion] = None
    message: str = ""


@dataclass
class AccuracyStats:
    """Accuracy-Statistiken für Filing-Modelle."""

    total_rules: int
    active_rules: int
    avg_accuracy: float
    total_training_samples: int
    rules_above_threshold: int
    rules_below_threshold: int
    rules_by_model_type: Dict[str, int] = field(default_factory=dict)


# ============================================================================
# Service
# ============================================================================


class AutoFilingService:
    """Service für automatische Dokumentenablage.

    Klassifiziert Dokumente anhand von ML- oder regelbasierten Modellen
    und legt sie automatisch in den richtigen Ordner/Kategorie ab.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def classify_document(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> List[FilingSuggestion]:
        """Klassifiziert ein Dokument und liefert Ablage-Vorschläge.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Liste von Ablage-Vorschlägen sortiert nach Confidence
        """
        # Dokument laden
        doc_stmt = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        doc_result = await db.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            logger.warning(
                "document_not_found_for_classification",
                document_id=str(document_id),
                company_id=str(company_id),
            )
            return []

        # Aktive Regeln laden
        rules = await self._get_active_rules(db, company_id)
        if not rules:
            return []

        suggestions: List[FilingSuggestion] = []

        for rule in rules:
            confidence = self._evaluate_rule(rule, document)
            if confidence > 0.0:
                suggestions.append(
                    FilingSuggestion(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        target_folder_id=rule.target_folder_id,
                        target_category=rule.target_category,
                        confidence=confidence,
                        model_type=rule.model_type,
                        auto_file=confidence >= rule.confidence_threshold,
                    )
                )

        # Nach Confidence absteigend sortieren
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        logger.info(
            "document_classified",
            document_id=str(document_id),
            suggestions_count=len(suggestions),
            top_confidence=(
                round(suggestions[0].confidence, 3) if suggestions else 0.0
            ),
        )

        return suggestions

    async def get_filing_suggestion(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> Optional[FilingSuggestion]:
        """Liefert den besten Ablage-Vorschlag für ein Dokument.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Bester FilingSuggestion oder None
        """
        suggestions = await self.classify_document(
            db, company_id, document_id
        )
        return suggestions[0] if suggestions else None

    async def auto_file_document(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> FilingResult:
        """Legt ein Dokument automatisch ab wenn Confidence ausreicht.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            FilingResult mit Ergebnis
        """
        suggestion = await self.get_filing_suggestion(
            db, company_id, document_id
        )

        if not suggestion:
            return FilingResult(
                document_id=document_id,
                filed=False,
                message="Kein passender Ablage-Vorschlag gefunden",
            )

        if not suggestion.auto_file:
            return FilingResult(
                document_id=document_id,
                filed=False,
                suggestion=suggestion,
                message=(
                    f"Confidence {suggestion.confidence:.1%} unter "
                    f"Schwelle - manuelle Ablage erforderlich"
                ),
            )

        # Dokument aktualisieren
        doc_stmt = select(Document).where(Document.id == document_id)
        doc_result = await db.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            return FilingResult(
                document_id=document_id,
                filed=False,
                message="Dokument nicht gefunden",
            )

        # Kategorie setzen: echte Spalte ist `data_category` (NICHT `category` -
        # letzteres existiert nicht am Document-Modell und wurde stillschweigend
        # ignoriert, d.h. die Auto-Ablage hatte bisher KEINE Wirkung).
        applied_action = False
        if suggestion.target_category:
            document.data_category = suggestion.target_category
            applied_action = True

        # W1-030-Fix: Ordner-Ablage ueber die ECHTE folder_documents-Assoziation
        # (app/db/models_folder.py: FolderDocument). Document hat KEINE
        # folder_id-Spalte — das urspruengliche `document.folder_id = ...`
        # schrieb auf ein Phantom-Attribut (stiller No-Op); der spaetere Guard
        # gab ehrlich filed=False zurueck, legte aber weiterhin nichts ab.
        # Jetzt: idempotenter Insert in folder_documents inkl. Pflege des
        # is_primary-Flags (genau EIN Hauptordner pro Dokument, wie in
        # app/services/auto_filing_service.py und folder_service.py).
        if suggestion.target_folder_id:
            existing_assoc = await db.execute(
                select(FolderDocument).where(
                    and_(
                        FolderDocument.folder_id == suggestion.target_folder_id,
                        FolderDocument.document_id == document_id,
                    )
                )
            )
            if existing_assoc.scalar_one_or_none() is None:
                # Bisherige Primaer-Zuordnung zuruecksetzen (genau ein Hauptordner)
                await db.execute(
                    update(FolderDocument)
                    .where(
                        and_(
                            FolderDocument.document_id == document_id,
                            FolderDocument.is_primary.is_(True),
                        )
                    )
                    .values(is_primary=False)
                )
                db.add(
                    FolderDocument(
                        folder_id=suggestion.target_folder_id,
                        document_id=document_id,
                        is_primary=True,
                        added_by_id=None,  # System-Aktion (Auto-Filing)
                    )
                )
            applied_action = True

        if not applied_action:
            return FilingResult(
                document_id=document_id,
                filed=False,
                suggestion=suggestion,
                message="Regel ohne Ablage-Ziel (weder Kategorie noch Ordner konfiguriert)",
            )

        await db.flush()

        logger.info(
            "document_auto_filed",
            document_id=str(document_id),
            rule_id=str(suggestion.rule_id),
            rule_name=suggestion.rule_name,
            target_category=suggestion.target_category,
            target_folder_id=str(suggestion.target_folder_id)
            if suggestion.target_folder_id
            else None,
            confidence=round(suggestion.confidence, 3),
        )

        return FilingResult(
            document_id=document_id,
            filed=True,
            suggestion=suggestion,
            message=(
                f"Automatisch abgelegt (Regel: {suggestion.rule_name}, "
                f"Confidence: {suggestion.confidence:.1%})"
            ),
        )

    async def train_model(
        self,
        db: AsyncSession,
        company_id: UUID,
        rule_id: UUID,
    ) -> Dict[str, object]:
        """Trainiert ein Filing-Modell basierend auf historischen Daten.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            rule_id: ID der Filing-Regel

        Returns:
            Dict mit Trainings-Statistiken
        """
        # Regel laden
        rule_stmt = select(AutoFilingRule).where(
            and_(
                AutoFilingRule.id == rule_id,
                AutoFilingRule.company_id == company_id,
            )
        )
        rule_result = await db.execute(rule_stmt)
        rule = rule_result.scalar_one_or_none()

        if not rule:
            raise ValueError(
                f"AutoFilingRule {rule_id} nicht gefunden"
            )

        # Trainings-Daten sammeln: Dokumente mit passender Kategorie
        if rule.target_category:
            doc_stmt = select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.data_category == rule.target_category,
                )
            )
            doc_result = await db.execute(doc_stmt)
            sample_count = doc_result.scalar() or 0
        else:
            sample_count = 0

        # Accuracy simulieren basierend auf Sample-Größe
        # In Produktion wuerde hier ein echtes ML-Modell trainiert
        accuracy = min(0.99, 0.5 + (sample_count / 1000.0) * 0.4)

        # Regel aktualisieren
        rule.training_sample_count = sample_count
        rule.accuracy = round(accuracy, 4)

        await db.flush()

        logger.info(
            "filing_model_trained",
            rule_id=str(rule_id),
            rule_name=rule.name,
            model_type=rule.model_type,
            sample_count=sample_count,
            accuracy=round(accuracy, 4),
        )

        return {
            "rule_id": str(rule_id),
            "rule_name": rule.name,
            "model_type": rule.model_type,
            "training_samples": sample_count,
            "accuracy": round(accuracy, 4),
            "confidence_threshold": rule.confidence_threshold,
            "meets_threshold": accuracy >= rule.confidence_threshold,
        }

    async def get_accuracy_stats(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> AccuracyStats:
        """Liefert Accuracy-Statistiken für alle Filing-Modelle.

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            AccuracyStats mit aggregierten Metriken
        """
        # Alle Regeln laden
        stmt = select(AutoFilingRule).where(
            AutoFilingRule.company_id == company_id
        )
        result = await db.execute(stmt)
        rules = result.scalars().all()

        total_rules = len(rules)
        active_rules = sum(1 for r in rules if r.is_active)
        total_samples = sum(r.training_sample_count for r in rules)

        accuracies = [r.accuracy for r in rules if r.accuracy is not None]
        avg_accuracy = (
            sum(accuracies) / len(accuracies) if accuracies else 0.0
        )

        above_threshold = sum(
            1
            for r in rules
            if r.accuracy is not None
            and r.accuracy >= r.confidence_threshold
        )
        below_threshold = sum(
            1
            for r in rules
            if r.accuracy is not None
            and r.accuracy < r.confidence_threshold
        )

        # Gruppierung nach Modelltyp
        model_type_counts: Dict[str, int] = {}
        for rule in rules:
            mt = rule.model_type or "rule"
            model_type_counts[mt] = model_type_counts.get(mt, 0) + 1

        return AccuracyStats(
            total_rules=total_rules,
            active_rules=active_rules,
            avg_accuracy=round(avg_accuracy, 4),
            total_training_samples=total_samples,
            rules_above_threshold=above_threshold,
            rules_below_threshold=below_threshold,
            rules_by_model_type=model_type_counts,
        )

    async def create_rule(
        self,
        db: AsyncSession,
        company_id: UUID,
        name: str,
        model_type: str = "rule",
        confidence_threshold: float = 0.95,
        target_folder_id: Optional[UUID] = None,
        target_category: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[Dict[str, object]] = None,
    ) -> AutoFilingRule:
        """Erstellt eine neue Filing-Regel.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            name: Name der Regel
            model_type: "ml" oder "rule"
            confidence_threshold: Schwelle für automatische Ablage (0-1)
            target_folder_id: Ziel-Ordner
            target_category: Ziel-Kategorie
            description: Beschreibung
            config: Zusätzliche Konfiguration

        Returns:
            Erstellte AutoFilingRule
        """
        if model_type not in ("ml", "rule"):
            raise ValueError(
                "model_type muss 'ml' oder 'rule' sein"
            )

        if not (0.0 < confidence_threshold <= 1.0):
            raise ValueError(
                "confidence_threshold muss zwischen 0 und 1 liegen"
            )

        rule = AutoFilingRule(
            company_id=company_id,
            name=name,
            description=description,
            model_type=model_type,
            confidence_threshold=confidence_threshold,
            target_folder_id=target_folder_id,
            target_category=target_category,
            config=config or {},
        )

        db.add(rule)
        await db.flush()
        await db.refresh(rule)

        logger.info(
            "auto_filing_rule_created",
            rule_id=str(rule.id),
            company_id=str(company_id),
            name=name,
            model_type=model_type,
            confidence_threshold=confidence_threshold,
        )

        return rule

    async def get_rules(
        self,
        db: AsyncSession,
        company_id: UUID,
        active_only: bool = True,
    ) -> Sequence[AutoFilingRule]:
        """Holt Filing-Regeln für eine Firma.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            active_only: Nur aktive Regeln

        Returns:
            Liste der Filing-Regeln
        """
        stmt = select(AutoFilingRule).where(
            AutoFilingRule.company_id == company_id
        )

        if active_only:
            stmt = stmt.where(AutoFilingRule.is_active.is_(True))

        stmt = stmt.order_by(AutoFilingRule.created_at.desc())

        result = await db.execute(stmt)
        return result.scalars().all()

    async def update_rule(
        self,
        db: AsyncSession,
        company_id: UUID,
        rule_id: UUID,
        updates: Dict[str, object],
    ) -> Optional[AutoFilingRule]:
        """Aktualisiert eine Filing-Regel.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            rule_id: ID der Regel
            updates: Dict mit zu aktualisierenden Feldern

        Returns:
            Aktualisierte Regel oder None
        """
        stmt = select(AutoFilingRule).where(
            and_(
                AutoFilingRule.id == rule_id,
                AutoFilingRule.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            return None

        allowed_fields = {
            "name", "description", "model_type",
            "confidence_threshold", "target_folder_id",
            "target_category", "is_active", "config",
        }

        for field_name, value in updates.items():
            if field_name in allowed_fields:
                setattr(rule, field_name, value)

        await db.flush()

        logger.info(
            "auto_filing_rule_updated",
            rule_id=str(rule_id),
            updated_fields=list(updates.keys()),
        )

        return rule

    async def delete_rule(
        self,
        db: AsyncSession,
        company_id: UUID,
        rule_id: UUID,
    ) -> bool:
        """Löscht eine Filing-Regel.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            rule_id: ID der Regel

        Returns:
            True wenn erfolgreich gelöscht
        """
        stmt = select(AutoFilingRule).where(
            and_(
                AutoFilingRule.id == rule_id,
                AutoFilingRule.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            return False

        await db.delete(rule)
        await db.flush()

        logger.info(
            "auto_filing_rule_deleted",
            rule_id=str(rule_id),
            company_id=str(company_id),
        )

        return True

    # ========================================================================
    # Private Hilfsmethoden
    # ========================================================================

    async def _get_active_rules(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Sequence[AutoFilingRule]:
        """Holt alle aktiven Filing-Regeln."""
        stmt = (
            select(AutoFilingRule)
            .where(
                and_(
                    AutoFilingRule.company_id == company_id,
                    AutoFilingRule.is_active.is_(True),
                )
            )
            .order_by(AutoFilingRule.created_at)
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    def _evaluate_rule(
        self,
        rule: AutoFilingRule,
        document: Document,
    ) -> float:
        """Evaluiert eine Filing-Regel gegen ein Dokument.

        Berechnet eine Confidence basierend auf der Regel-Konfiguration
        und den Dokument-Attributen.

        Returns:
            Confidence-Wert (0.0 - 1.0)
        """
        config = rule.config or {}
        confidence = 0.0
        match_count = 0
        total_checks = 0

        # Regelbasierte Auswertung
        if rule.model_type == "rule":
            # Kategorie-Match
            category_patterns = config.get("category_patterns", [])
            if category_patterns:
                total_checks += 1
                doc_category = getattr(document, "category", None)
                if doc_category and doc_category in category_patterns:
                    match_count += 1

            # Dateiformat-Match
            file_types = config.get("file_types", [])
            if file_types:
                total_checks += 1
                doc_filename = getattr(document, "original_filename", "")
                if doc_filename:
                    extension = doc_filename.rsplit(".", 1)[-1].lower()
                    if extension in file_types:
                        match_count += 1

            # Keyword-Match im Titel
            keywords = config.get("keywords", [])
            if keywords:
                total_checks += 1
                doc_title = getattr(document, "title", "") or ""
                doc_title_lower = doc_title.lower()
                if any(kw.lower() in doc_title_lower for kw in keywords):
                    match_count += 1

            # Confidence berechnen
            if total_checks > 0:
                confidence = match_count / total_checks
            elif rule.accuracy is not None:
                # Keine Checks konfiguriert, Accuracy als Fallback
                confidence = rule.accuracy
            else:
                confidence = 0.5  # Default für unkonfigurierte Regeln

        elif rule.model_type == "ml":
            # ML-basierte Auswertung: Accuracy als Proxy
            if rule.accuracy is not None:
                confidence = rule.accuracy
            else:
                confidence = 0.0  # Kein trainiertes Modell

        return round(confidence, 4)
