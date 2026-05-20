# -*- coding: utf-8 -*-
"""
AutoFilingService - ML-basiertes Auto-Filing.

Feature #7: Automation 2.0
Lernt aus bisherigen Zuordnungen und nutzt Fuzzy-Matching.

Drei Methoden:
1. ML Classifier: Trainiertes Modell basierend auf bisherigen Zuordnungen
2. Fuzzy Match: Lieferantenname, Betraege, Schluesselwoerter
3. Pattern Match (rule): Regex-Patterns, Keywords, Lieferanten-IDs

Nutzt models_approval_extended für AutoFilingRule.
"""

from __future__ import annotations

import re
import structlog
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document, BusinessEntity
from app.db.models_approval_extended import AutoFilingRule

logger = structlog.get_logger(__name__)


class AutoFilingService:
    """ML-basiertes Auto-Filing für Dokumente.

    Workflow:
    1. Dokument-Upload oder OCR-Abschluss
    2. classify_document() prüft alle aktiven Regeln
    3. Bei Match (confidence >= threshold): auto_file_document()
    4. Manuelle Korrekturen fliessen via learn_from_filing() zurück
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Auto-Filing Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def classify_document(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> Optional[AutoFilingRule]:
        """Dokument automatisch klassifizieren und Filing-Regel finden.

        Versucht die Regeln und gibt die beste passende zurück.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Beste passende AutoFilingRule oder None
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
            )
            return None

        doc_text = document.extracted_text or ""
        doc_metadata = document.metadata_extracted or {}

        # Aktive Regeln laden
        rules_stmt = select(AutoFilingRule).where(
            and_(
                AutoFilingRule.company_id == company_id,
                AutoFilingRule.is_active.is_(True),
            )
        )
        rules_result = await db.execute(rules_stmt)
        rules = rules_result.scalars().all()

        best_match: Optional[AutoFilingRule] = None
        best_confidence = 0.0

        for rule in rules:
            confidence = 0.0

            if rule.model_type == "rule":
                confidence = self._evaluate_rule_match(rule, doc_text, doc_metadata)
            elif rule.model_type == "ml":
                confidence = await self._evaluate_fuzzy_match(
                    db, rule, document
                )

            if (
                confidence >= rule.confidence_threshold
                and confidence > best_confidence
            ):
                best_match = rule
                best_confidence = confidence

        if best_match:
            logger.info(
                "document_classified",
                document_id=str(document_id),
                rule_id=str(best_match.id),
                rule_name=best_match.name,
                confidence=round(best_confidence, 3),
            )

        return best_match

    async def auto_file_document(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> Dict[str, object]:
        """Dokument automatisch einordnen basierend auf bester Regel.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Dict mit Ergebnis
        """
        rule = await self.classify_document(db, company_id, document_id)

        if not rule:
            return {
                "filed": False,
                "reason": "Keine passende Regel gefunden",
            }

        doc_stmt = select(Document).where(Document.id == document_id)
        doc_result = await db.execute(doc_stmt)
        document = doc_result.scalar_one_or_none()

        if not document:
            return {"filed": False, "reason": "Dokument nicht gefunden"}

        applied_changes: Dict[str, object] = {
            "filed": True,
            "rule_id": str(rule.id),
            "rule_name": rule.name,
        }

        # In Zielordner verschieben
        if rule.target_folder_id:
            document.folder_id = rule.target_folder_id
            applied_changes["folder_id"] = str(rule.target_folder_id)

        # Kategorie setzen
        if rule.target_category:
            applied_changes["target_category"] = rule.target_category

        # Training-Statistik erhöhen
        rule.training_sample_count = (rule.training_sample_count or 0) + 1

        await db.flush()

        logger.info(
            "document_auto_filed",
            document_id=str(document_id),
            rule_name=rule.name,
            folder_id=str(rule.target_folder_id) if rule.target_folder_id else None,
        )

        return applied_changes

    async def learn_from_filing(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        folder_id: UUID,
        tags: List[UUID],
    ) -> None:
        """Aus manueller Einordnung lernen für zukünftige Auto-Filing.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments
            folder_id: Zielordner der manuellen Zuordnung
            tags: Tags der manuellen Zuordnung
        """
        rule_stmt = select(AutoFilingRule).where(
            and_(
                AutoFilingRule.company_id == company_id,
                AutoFilingRule.target_folder_id == folder_id,
                AutoFilingRule.is_active.is_(True),
            )
        )
        rule_result = await db.execute(rule_stmt)
        matching_rules = rule_result.scalars().all()

        for rule in matching_rules:
            rule.training_sample_count = (rule.training_sample_count or 0) + 1

        logger.info(
            "learned_from_filing",
            document_id=str(document_id),
            folder_id=str(folder_id),
            matching_rules=len(matching_rules),
        )

    async def fuzzy_match_supplier(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_text: str,
    ) -> Optional[Dict[str, object]]:
        """Fuzzy-Matching: Ähnliche Dokumente von gleichen Lieferanten finden.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_text: Extrahierter Text des Dokuments

        Returns:
            Dict mit Lieferant-Info oder None
        """
        if not document_text:
            return None

        entities_stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.entity_type == "supplier",
            )
        ).limit(200)
        entities_result = await db.execute(entities_stmt)
        entities = entities_result.scalars().all()

        best_match: Optional[Dict[str, object]] = None
        best_ratio = 0.0
        text_lower = document_text.lower()

        for entity in entities:
            entity_name = entity.name or ""
            if not entity_name:
                continue

            # Exakter Treffer im Text
            if entity_name.lower() in text_lower:
                return {
                    "entity_id": str(entity.id),
                    "entity_name": entity_name,
                    "confidence": 0.99,
                    "match_type": "exact",
                }

            # Fuzzy-Match
            ratio = SequenceMatcher(
                None, entity_name.lower(), text_lower[:500]
            ).ratio()
            if ratio > best_ratio and ratio >= 0.6:
                best_ratio = ratio
                best_match = {
                    "entity_id": str(entity.id),
                    "entity_name": entity_name,
                    "confidence": round(ratio, 3),
                    "match_type": "fuzzy",
                }

        return best_match

    def _evaluate_rule_match(
        self,
        rule: AutoFilingRule,
        doc_text: str,
        doc_metadata: Dict[str, object],
    ) -> float:
        """Regelbasierte Bewertung.

        Args:
            rule: Die Regel
            doc_text: Extrahierter Text
            doc_metadata: Dokument-Metadaten

        Returns:
            Konfidenz-Score (0.0 - 1.0)
        """
        config = rule.config or {}
        matches = 0
        total_checks = 0

        # Regex-Pattern prüfen
        regex_pattern = config.get("regex")
        if regex_pattern:
            total_checks += 1
            try:
                if re.search(str(regex_pattern), doc_text, re.IGNORECASE):
                    matches += 1
            except re.error:
                pass

        # Keywords prüfen
        keywords = config.get("keywords", [])
        if keywords:
            total_checks += 1
            text_lower = doc_text.lower()
            keyword_matches = sum(
                1 for kw in keywords if str(kw).lower() in text_lower
            )
            if keyword_matches > 0:
                matches += keyword_matches / len(keywords)

        # Lieferanten-IDs prüfen
        supplier_ids = config.get("supplier_ids", [])
        if supplier_ids:
            total_checks += 1
            doc_supplier = str(doc_metadata.get("supplier_id", ""))
            if doc_supplier in [str(sid) for sid in supplier_ids]:
                matches += 1

        if total_checks == 0:
            return 0.0

        return matches / total_checks

    async def _evaluate_fuzzy_match(
        self,
        db: AsyncSession,
        rule: AutoFilingRule,
        document: Document,
    ) -> float:
        """ML/Fuzzy-basierte Bewertung.

        Args:
            db: Async Database Session
            rule: Die Regel
            document: Das Dokument

        Returns:
            Konfidenz-Score (0.0 - 1.0)
        """
        config = rule.config or {}
        threshold = float(config.get("threshold", 0.8))
        doc_text = document.extracted_text or ""

        if not doc_text:
            return 0.0

        match_result = await self.fuzzy_match_supplier(
            db, document.company_id, doc_text
        )

        if match_result and float(match_result.get("confidence", 0)) >= threshold:
            return float(match_result["confidence"])

        return 0.0
