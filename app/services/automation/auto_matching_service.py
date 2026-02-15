# -*- coding: utf-8 -*-
"""
AutoMatchingService - Automatisches Dokumenten-Matching.

Feature #7: Automation 2.0
- Automatisches Matching von Bestellung <-> Lieferschein <-> Rechnung
- Confidence-Berechnung basierend auf Feldvergleichen
- Bestaetigung/Ablehnung von Matches
- Match-Statistiken

Nutzt models_approval_extended fuer AutoMatchResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Sequence
from uuid import UUID

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document
from app.db.models_approval_extended import AutoMatchResult

logger = structlog.get_logger(__name__)


# ============================================================================
# Konstanten
# ============================================================================

MATCH_TYPE_BESTELLUNG_LIEFERSCHEIN = "bestellung_lieferschein"
MATCH_TYPE_LIEFERSCHEIN_RECHNUNG = "lieferschein_rechnung"
MATCH_TYPE_BESTELLUNG_RECHNUNG = "bestellung_rechnung"

VALID_MATCH_TYPES = {
    MATCH_TYPE_BESTELLUNG_LIEFERSCHEIN,
    MATCH_TYPE_LIEFERSCHEIN_RECHNUNG,
    MATCH_TYPE_BESTELLUNG_RECHNUNG,
}


# ============================================================================
# Datenklassen
# ============================================================================


@dataclass
class MatchCandidate:
    """Einzelner Match-Kandidat."""

    document_id: UUID
    matched_document_id: UUID
    match_type: str
    confidence: float  # 0.0 - 1.0
    match_details: Dict[str, object] = field(default_factory=dict)


@dataclass
class MatchResult:
    """Ergebnis eines Matching-Durchlaufs."""

    total_documents_checked: int
    matches_found: int
    matches_above_threshold: int
    candidates: List[MatchCandidate] = field(default_factory=list)


@dataclass
class MatchStatistics:
    """Aggregierte Match-Statistiken."""

    total_matches: int
    confirmed_matches: int
    unconfirmed_matches: int
    avg_confidence: float
    matches_by_type: Dict[str, int] = field(default_factory=dict)
    confirmation_rate: float = 0.0


# ============================================================================
# Service
# ============================================================================


class AutoMatchingService:
    """Service fuer automatisches Dokumenten-Matching.

    Verknuepft zusammengehoerige Dokumente automatisch:
    Bestellung <-> Lieferschein <-> Rechnung basierend auf
    gemeinsamen Feldern wie PO-Nummer, Betrag, Lieferant.
    """

    DEFAULT_CONFIDENCE_THRESHOLD = 0.7

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def match_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        confidence_threshold: float = 0.7,
    ) -> MatchResult:
        """Findet Matching-Kandidaten fuer ein Dokument.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Quell-Dokuments
            confidence_threshold: Mindest-Confidence (0-1)

        Returns:
            MatchResult mit gefundenen Kandidaten
        """
        # Quell-Dokument laden
        doc_stmt = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        doc_result = await db.execute(doc_stmt)
        source_doc = doc_result.scalar_one_or_none()

        if not source_doc:
            logger.warning(
                "source_document_not_found",
                document_id=str(document_id),
            )
            return MatchResult(
                total_documents_checked=0,
                matches_found=0,
                matches_above_threshold=0,
            )

        # Potenzielle Match-Partner laden (gleiche Firma, anderer Dokumenttyp)
        candidates_stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.id != document_id,
                )
            )
            .limit(500)  # Performance-Limit
        )
        candidates_result = await db.execute(candidates_stmt)
        candidate_docs = candidates_result.scalars().all()

        result = MatchResult(
            total_documents_checked=len(candidate_docs),
            matches_found=0,
            matches_above_threshold=0,
        )

        for candidate_doc in candidate_docs:
            match_candidate = self._calculate_match(
                source_doc, candidate_doc
            )
            if match_candidate and match_candidate.confidence > 0.0:
                result.matches_found += 1
                if match_candidate.confidence >= confidence_threshold:
                    result.matches_above_threshold += 1
                    result.candidates.append(match_candidate)

        # Nach Confidence absteigend sortieren
        result.candidates.sort(
            key=lambda c: c.confidence, reverse=True
        )

        logger.info(
            "document_matching_completed",
            document_id=str(document_id),
            total_checked=result.total_documents_checked,
            matches_found=result.matches_found,
            above_threshold=result.matches_above_threshold,
        )

        return result

    async def auto_match_and_save(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
        confidence_threshold: float = 0.8,
    ) -> List[AutoMatchResult]:
        """Matched ein Dokument und speichert Ergebnisse.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments
            confidence_threshold: Mindest-Confidence fuer Speicherung

        Returns:
            Liste der gespeicherten AutoMatchResults
        """
        match_result = await self.match_documents(
            db, company_id, document_id, confidence_threshold
        )

        saved_results: List[AutoMatchResult] = []

        for candidate in match_result.candidates:
            # Pruefen ob Match bereits existiert
            existing = await self._check_existing_match(
                db, candidate.document_id, candidate.matched_document_id
            )
            if existing:
                continue

            match_record = AutoMatchResult(
                company_id=company_id,
                document_id=candidate.document_id,
                matched_document_id=candidate.matched_document_id,
                match_type=candidate.match_type,
                confidence=candidate.confidence,
                match_details=candidate.match_details,
            )

            db.add(match_record)
            saved_results.append(match_record)

        if saved_results:
            await db.flush()

            logger.info(
                "auto_matches_saved",
                document_id=str(document_id),
                matches_saved=len(saved_results),
            )

        return saved_results

    async def calculate_match_confidence(
        self,
        db: AsyncSession,
        document_id: UUID,
        candidate_id: UUID,
    ) -> Optional[MatchCandidate]:
        """Berechnet die Match-Confidence zwischen zwei Dokumenten.

        Args:
            db: Async Database Session
            document_id: ID des ersten Dokuments
            candidate_id: ID des zweiten Dokuments

        Returns:
            MatchCandidate oder None
        """
        doc_stmt = select(Document).where(Document.id == document_id)
        doc_result = await db.execute(doc_stmt)
        source = doc_result.scalar_one_or_none()

        cand_stmt = select(Document).where(Document.id == candidate_id)
        cand_result = await db.execute(cand_stmt)
        candidate = cand_result.scalar_one_or_none()

        if not source or not candidate:
            return None

        return self._calculate_match(source, candidate)

    async def get_unmatched_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, object]]:
        """Findet Dokumente ohne Matching-Partner.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_type: Optional: Nur bestimmter Dokumenttyp
            limit: Max. Anzahl Ergebnisse

        Returns:
            Liste von Dokumenten ohne Matches
        """
        # Dokumente mit mindestens einem Match
        matched_ids_stmt = select(AutoMatchResult.document_id).where(
            AutoMatchResult.company_id == company_id
        ).union(
            select(AutoMatchResult.matched_document_id).where(
                AutoMatchResult.company_id == company_id
            )
        )

        # Dokumente ohne Match
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.id.notin_(matched_ids_stmt),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        if document_type:
            stmt = stmt.where(Document.document_type == document_type)

        result = await db.execute(stmt)
        documents = result.scalars().all()

        unmatched: List[Dict[str, object]] = []
        for doc in documents:
            unmatched.append(
                {
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "document_type": getattr(doc, "document_type", None),
                    "category": doc.category,
                    "created_at": (
                        doc.created_at.isoformat()
                        if doc.created_at
                        else None
                    ),
                }
            )

        return unmatched

    async def confirm_match(
        self,
        db: AsyncSession,
        company_id: UUID,
        match_id: UUID,
        user_id: UUID,
    ) -> Optional[AutoMatchResult]:
        """Bestaetigt ein automatisches Match.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            match_id: ID des AutoMatchResult
            user_id: ID des bestaetigenden Users

        Returns:
            Aktualisiertes AutoMatchResult oder None
        """
        stmt = select(AutoMatchResult).where(
            and_(
                AutoMatchResult.id == match_id,
                AutoMatchResult.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        match = result.scalar_one_or_none()

        if not match:
            return None

        match.is_confirmed = True
        match.confirmed_by_user_id = user_id

        await db.flush()

        logger.info(
            "match_confirmed",
            match_id=str(match_id),
            confirmed_by=str(user_id),
            match_type=match.match_type,
            confidence=match.confidence,
        )

        return match

    async def reject_match(
        self,
        db: AsyncSession,
        company_id: UUID,
        match_id: UUID,
    ) -> bool:
        """Lehnt ein automatisches Match ab (loescht es).

        Args:
            db: Async Database Session
            company_id: ID der Firma
            match_id: ID des AutoMatchResult

        Returns:
            True wenn erfolgreich geloescht
        """
        stmt = select(AutoMatchResult).where(
            and_(
                AutoMatchResult.id == match_id,
                AutoMatchResult.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        match = result.scalar_one_or_none()

        if not match:
            return False

        await db.delete(match)
        await db.flush()

        logger.info(
            "match_rejected",
            match_id=str(match_id),
            company_id=str(company_id),
        )

        return True

    async def get_match_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> MatchStatistics:
        """Liefert aggregierte Match-Statistiken.

        Args:
            db: Async Database Session
            company_id: ID der Firma

        Returns:
            MatchStatistics mit aggregierten Daten
        """
        # Gesamtzahlen
        total_stmt = select(func.count(AutoMatchResult.id)).where(
            AutoMatchResult.company_id == company_id
        )
        total_result = await db.execute(total_stmt)
        total_matches = total_result.scalar() or 0

        # Bestaetigte
        confirmed_stmt = select(func.count(AutoMatchResult.id)).where(
            and_(
                AutoMatchResult.company_id == company_id,
                AutoMatchResult.is_confirmed.is_(True),
            )
        )
        confirmed_result = await db.execute(confirmed_stmt)
        confirmed_matches = confirmed_result.scalar() or 0

        # Durchschnittliche Confidence
        avg_stmt = select(func.avg(AutoMatchResult.confidence)).where(
            AutoMatchResult.company_id == company_id
        )
        avg_result = await db.execute(avg_stmt)
        avg_confidence = avg_result.scalar() or 0.0

        # Matches pro Typ
        type_stmt = (
            select(
                AutoMatchResult.match_type,
                func.count(AutoMatchResult.id),
            )
            .where(AutoMatchResult.company_id == company_id)
            .group_by(AutoMatchResult.match_type)
        )
        type_result = await db.execute(type_stmt)
        matches_by_type: Dict[str, int] = {}
        for row in type_result.all():
            matches_by_type[row[0]] = row[1]

        unconfirmed = total_matches - confirmed_matches
        confirmation_rate = (
            (confirmed_matches / total_matches * 100.0)
            if total_matches > 0
            else 0.0
        )

        return MatchStatistics(
            total_matches=total_matches,
            confirmed_matches=confirmed_matches,
            unconfirmed_matches=unconfirmed,
            avg_confidence=round(float(avg_confidence), 4),
            matches_by_type=matches_by_type,
            confirmation_rate=round(confirmation_rate, 1),
        )

    async def get_matches_for_document(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> Sequence[AutoMatchResult]:
        """Holt alle Matches fuer ein Dokument.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Liste der AutoMatchResults
        """
        stmt = (
            select(AutoMatchResult)
            .where(
                and_(
                    AutoMatchResult.company_id == company_id,
                    or_(
                        AutoMatchResult.document_id == document_id,
                        AutoMatchResult.matched_document_id == document_id,
                    ),
                )
            )
            .order_by(AutoMatchResult.confidence.desc())
        )

        result = await db.execute(stmt)
        return result.scalars().all()

    # ========================================================================
    # Private Hilfsmethoden
    # ========================================================================

    async def _check_existing_match(
        self,
        db: AsyncSession,
        doc_id: UUID,
        matched_id: UUID,
    ) -> bool:
        """Prueft ob ein Match bereits existiert."""
        stmt = select(func.count(AutoMatchResult.id)).where(
            or_(
                and_(
                    AutoMatchResult.document_id == doc_id,
                    AutoMatchResult.matched_document_id == matched_id,
                ),
                and_(
                    AutoMatchResult.document_id == matched_id,
                    AutoMatchResult.matched_document_id == doc_id,
                ),
            )
        )
        result = await db.execute(stmt)
        count = result.scalar() or 0
        return count > 0

    def _calculate_match(
        self,
        source: Document,
        candidate: Document,
    ) -> Optional[MatchCandidate]:
        """Berechnet Match-Confidence zwischen zwei Dokumenten.

        Vergleicht gemeinsame Felder und berechnet eine gewichtete
        Confidence.
        """
        # Match-Typ bestimmen
        match_type = self._determine_match_type(source, candidate)
        if not match_type:
            return None

        details: Dict[str, object] = {}
        scores: List[float] = []
        weights: List[float] = []

        # 1. Entity-Vergleich (Lieferant/Kunde)
        source_entity = getattr(source, "entity_id", None)
        candidate_entity = getattr(candidate, "entity_id", None)
        if source_entity and candidate_entity:
            entity_match = source_entity == candidate_entity
            details["entity_match"] = entity_match
            scores.append(1.0 if entity_match else 0.0)
            weights.append(0.3)

        # 2. Betragsvergleich
        source_amount = getattr(source, "amount", None)
        candidate_amount = getattr(candidate, "amount", None)
        if source_amount is not None and candidate_amount is not None:
            try:
                s_amount = Decimal(str(source_amount))
                c_amount = Decimal(str(candidate_amount))
                if s_amount > 0:
                    amount_ratio = float(
                        min(s_amount, c_amount) / max(s_amount, c_amount)
                    )
                    details["amount_similarity"] = round(amount_ratio, 3)
                    scores.append(amount_ratio)
                    weights.append(0.25)
            except (InvalidOperation, ValueError, ZeroDivisionError):
                pass

        # 3. PO-Nummer / Referenz-Vergleich
        source_ref = self._get_reference(source)
        candidate_ref = self._get_reference(candidate)
        if source_ref and candidate_ref:
            ref_match = source_ref.strip().lower() == candidate_ref.strip().lower()
            details["reference_match"] = ref_match
            scores.append(1.0 if ref_match else 0.0)
            weights.append(0.35)

        # 4. Zeitlicher Zusammenhang (innerhalb 90 Tagen)
        source_date = getattr(source, "document_date", None)
        candidate_date = getattr(candidate, "document_date", None)
        if source_date and candidate_date:
            day_diff = abs((source_date - candidate_date).days)
            if day_diff <= 90:
                time_score = max(0.0, 1.0 - (day_diff / 90.0))
                details["time_proximity"] = round(time_score, 3)
                scores.append(time_score)
                weights.append(0.1)

        # Gewichtete Confidence berechnen
        if not scores:
            return None

        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        confidence = weighted_sum / total_weight if total_weight > 0 else 0.0

        if confidence <= 0.0:
            return None

        return MatchCandidate(
            document_id=source.id,
            matched_document_id=candidate.id,
            match_type=match_type,
            confidence=round(confidence, 4),
            match_details=details,
        )

    def _determine_match_type(
        self,
        source: Document,
        candidate: Document,
    ) -> Optional[str]:
        """Bestimmt den Match-Typ basierend auf Dokumenttypen."""
        source_type = getattr(source, "document_type", None) or ""
        candidate_type = getattr(candidate, "document_type", None) or ""

        source_lower = source_type.lower()
        candidate_lower = candidate_type.lower()

        # Bestellung <-> Lieferschein
        if (
            ("bestellung" in source_lower or "order" in source_lower)
            and ("lieferschein" in candidate_lower or "delivery" in candidate_lower)
        ) or (
            ("lieferschein" in source_lower or "delivery" in source_lower)
            and ("bestellung" in candidate_lower or "order" in candidate_lower)
        ):
            return MATCH_TYPE_BESTELLUNG_LIEFERSCHEIN

        # Lieferschein <-> Rechnung
        if (
            ("lieferschein" in source_lower or "delivery" in source_lower)
            and ("rechnung" in candidate_lower or "invoice" in candidate_lower)
        ) or (
            ("rechnung" in source_lower or "invoice" in source_lower)
            and ("lieferschein" in candidate_lower or "delivery" in candidate_lower)
        ):
            return MATCH_TYPE_LIEFERSCHEIN_RECHNUNG

        # Bestellung <-> Rechnung
        if (
            ("bestellung" in source_lower or "order" in source_lower)
            and ("rechnung" in candidate_lower or "invoice" in candidate_lower)
        ) or (
            ("rechnung" in source_lower or "invoice" in source_lower)
            and ("bestellung" in candidate_lower or "order" in candidate_lower)
        ):
            return MATCH_TYPE_BESTELLUNG_RECHNUNG

        return None

    def _get_reference(self, document: Document) -> Optional[str]:
        """Extrahiert Referenznummer aus einem Dokument."""
        # Verschiedene moegliche Felder pruefen
        for field_name in (
            "po_number",
            "reference_number",
            "order_number",
            "external_reference",
        ):
            value = getattr(document, field_name, None)
            if value:
                return str(value)

        # Fallback: Metadaten pruefen
        metadata = getattr(document, "metadata_extracted", None)
        if metadata and isinstance(metadata, dict):
            for key in ("po_number", "reference", "order_number"):
                value = metadata.get(key)
                if value:
                    return str(value)

        return None
