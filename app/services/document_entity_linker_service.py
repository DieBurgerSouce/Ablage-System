"""
Document Entity Linker Service.

Verknüpft bestehende Dokumente automatisch mit importierten BusinessEntities.

Matching-Strategien (nach Priorität):
1. Exakte Kundennummer im OCR-Text (99% confidence)
2. Exakter Matchcode im OCR-Text (95% confidence)
3. IBAN/VAT-ID Match (90% confidence)
4. Firmenname Fuzzy-Match (>85% Ähnlichkeit, 80% confidence)
5. Adress-Match (PLZ + Straße, 75% confidence)
"""

import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, BusinessEntity, EntityType
from app.services.entity_search_service import (
    EntitySearchService,
    normalize_text,
    calculate_similarity,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class LinkingResult:
    """Ergebnis eines Linking-Vorgangs."""

    linked_count: int = 0
    unlinked_count: int = 0
    low_confidence_count: int = 0
    error_count: int = 0
    already_linked_count: int = 0
    details: list[dict] = field(default_factory=list)


@dataclass
class MatchResult:
    """Ergebnis eines Entity-Matches."""

    entity: BusinessEntity
    confidence: float
    match_type: str
    match_details: str


# ============================================================================
# PATTERN EXTRACTION
# ============================================================================


def extract_customer_numbers(text: str) -> list[str]:
    """
    Extrahiert mögliche Kundennummern aus Text.

    Sucht nach Mustern wie:
    - Kd-Nr: 12345
    - Kundennummer: 12345
    - Kunden-Nr.: 12345
    - KdNr 12345
    """
    patterns = [
        r"(?:Kd\.?-?Nr\.?|Kundennummer|Kunden-?Nr\.?|KdNr\.?)[\s:]*(\d{3,8})",
        r"Ihre\s+(?:Kunden)?nummer[\s:]*(\d{3,8})",
        r"Kundenkonto[\s:]*(\d{3,8})",
    ]

    numbers = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            numbers.add(match.group(1))

    return list(numbers)


def extract_supplier_numbers(text: str) -> list[str]:
    """
    Extrahiert mögliche Lieferantennummern aus Text.

    Sucht nach Mustern wie:
    - Lief-Nr: 12345
    - Lieferantennummer: 12345
    - Kreditor-Nr.: 12345
    """
    patterns = [
        r"(?:Lief\.?-?Nr\.?|Lieferantennummer|Lieferanten-?Nr\.?|LiefNr\.?)[\s:]*(\d{3,8})",
        r"(?:Kreditor\.?-?Nr\.?|Kreditoren-?Nr\.?)[\s:]*(\d{3,8})",
    ]

    numbers = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            numbers.add(match.group(1))

    return list(numbers)


def extract_matchcodes(text: str) -> list[str]:
    """
    Extrahiert mögliche Matchcodes aus Text.

    Matchcodes sind typischerweise:
    - Großgeschriebene Wörter nach "Firma:", "An:", etc.
    - Kurze Bezeichner in Kopfzeilen
    """
    patterns = [
        r"(?:Firma|An|Kunde|Lieferant)[\s:]+([A-ZÄÖÜ][A-Za-zäöüÄÖÜß\s&\-\.]+)",
        r"^([A-ZÄÖÜ][A-Za-zäöüÄÖÜß]{2,}(?:\s+[A-ZÄÖÜ][A-Za-zäöüÄÖÜß]+)*)$",
    ]

    codes = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.MULTILINE):
            code = match.group(1).strip()
            if len(code) >= 3 and len(code) <= 50:
                codes.add(code)

    return list(codes)


def extract_ibans(text: str) -> list[str]:
    """Extrahiert IBANs aus Text."""
    pattern = r"\b([A-Z]{2}\d{2}[\s]?(?:\d{4}[\s]?){3,7}\d{1,4})\b"
    ibans = []
    for match in re.finditer(pattern, text.upper()):
        iban = re.sub(r"\s+", "", match.group(1))
        if 15 <= len(iban) <= 34:
            ibans.append(iban)
    return ibans


def extract_vat_ids(text: str) -> list[str]:
    """Extrahiert USt-IdNr aus Text."""
    patterns = [
        # DE gefolgt von 9 Ziffern mit optionalen Leerzeichen dazwischen
        r"\b(DE(?:\s*\d){9})\b",
        # USt-Id, VAT, oder Steuernummer als Prefix
        r"(?:USt-?Id\.?(?:-?Nr\.?)?|VAT|Steuern(?:ummer)?)[\s:]*([A-Z]{2}(?:\s*\d){9,11})",
    ]

    vat_ids = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            vat_id = re.sub(r"\s+", "", match.group(1).upper())
            vat_ids.append(vat_id)

    return list(set(vat_ids))  # Deduplizieren


# ============================================================================
# DOCUMENT ENTITY LINKER SERVICE
# ============================================================================


class DocumentEntityLinkerService:
    """Service zum automatischen Verknüpfen von Dokumenten mit Entities."""

    # Confidence Thresholds
    CUSTOMER_NUMBER_CONFIDENCE = 0.99
    MATCHCODE_EXACT_CONFIDENCE = 0.95
    IBAN_CONFIDENCE = 0.90
    VAT_ID_CONFIDENCE = 0.90
    NAME_FUZZY_CONFIDENCE = 0.80
    ADDRESS_CONFIDENCE = 0.75

    MIN_LINK_CONFIDENCE = 0.75  # Minimum für automatische Verknüpfung

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db
        self.search_service = EntitySearchService(db)

    async def link_all_documents(
        self,
        min_confidence: float = MIN_LINK_CONFIDENCE,
        batch_size: int = 100,
        only_unlinked: bool = True,
    ) -> LinkingResult:
        """
        Verknüpft alle Dokumente mit BusinessEntities.

        Args:
            min_confidence: Minimale Confidence für automatische Verknüpfung
            batch_size: Anzahl Dokumente pro Batch
            only_unlinked: Nur Dokumente ohne business_entity_id

        Returns:
            LinkingResult mit Statistiken
        """
        result = LinkingResult()

        logger.info(
            "document_linking_started",
            min_confidence=min_confidence,
            only_unlinked=only_unlinked,
        )

        # Dokumente laden (mit OCR-Text)
        stmt = select(Document).where(
            and_(
                Document.extracted_text.isnot(None),
                Document.extracted_text != "",
                Document.deleted_at.is_(None),
            )
        )

        if only_unlinked:
            stmt = stmt.where(Document.business_entity_id.is_(None))

        # Zählen
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = await self.db.scalar(count_stmt)

        logger.info("documents_to_process", count=total_count)

        # In Batches verarbeiten
        offset = 0
        while True:
            batch_stmt = stmt.offset(offset).limit(batch_size)
            batch_result = await self.db.execute(batch_stmt)
            documents = batch_result.scalars().all()

            if not documents:
                break

            for doc in documents:
                try:
                    match = await self.link_document(
                        doc.id, min_confidence=min_confidence
                    )

                    if match:
                        if match.confidence >= min_confidence:
                            result.linked_count += 1
                            result.details.append(
                                {
                                    "document_id": str(doc.id),
                                    "entity_id": str(match.entity.id),
                                    "confidence": match.confidence,
                                    "match_type": match.match_type,
                                }
                            )
                        else:
                            result.low_confidence_count += 1
                    else:
                        result.unlinked_count += 1

                except Exception as e:
                    result.error_count += 1
                    logger.error(
                        "document_linking_error",
                        document_id=str(doc.id),
                        error=str(e),
                    )

            offset += batch_size

            # Zwischenspeichern
            await self.db.commit()
            logger.info(
                "document_linking_progress",
                processed=offset,
                total=total_count,
                linked=result.linked_count,
            )

        logger.info(
            "document_linking_completed",
            linked=result.linked_count,
            unlinked=result.unlinked_count,
            low_confidence=result.low_confidence_count,
            errors=result.error_count,
        )

        return result

    async def link_document(
        self,
        document_id: UUID,
        min_confidence: float = MIN_LINK_CONFIDENCE,
    ) -> Optional[MatchResult]:
        """
        Verknüpft ein einzelnes Dokument mit der besten Entity.

        Args:
            document_id: Dokument-ID
            min_confidence: Minimale Confidence

        Returns:
            MatchResult oder None
        """
        # Dokument laden
        stmt = select(Document).where(Document.id == document_id)
        result = await self.db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            logger.warning("document_not_found", document_id=str(document_id))
            return None

        if not doc.extracted_text:
            return None

        text = doc.extracted_text

        # Matching versuchen (nach Priorität)
        match = await self._try_customer_number_match(text)
        if match and match.confidence >= min_confidence:
            await self._apply_match(doc, match)
            return match

        match = await self._try_iban_match(text)
        if match and match.confidence >= min_confidence:
            await self._apply_match(doc, match)
            return match

        match = await self._try_vat_id_match(text)
        if match and match.confidence >= min_confidence:
            await self._apply_match(doc, match)
            return match

        match = await self._try_matchcode_match(text)
        if match and match.confidence >= min_confidence:
            await self._apply_match(doc, match)
            return match

        return match  # Kann auch low-confidence sein

    async def _apply_match(self, doc: Document, match: MatchResult) -> None:
        """Wendet Match auf Dokument an."""
        doc.business_entity_id = match.entity.id
        logger.info(
            "document_linked",
            document_id=str(doc.id),
            entity_id=str(match.entity.id),
            confidence=match.confidence,
            match_type=match.match_type,
        )

    # ========================================================================
    # MATCHING STRATEGIES
    # ========================================================================

    async def _try_customer_number_match(self, text: str) -> Optional[MatchResult]:
        """Versucht Match über Kundennummer."""
        kd_nrs = extract_customer_numbers(text)

        for kd_nr in kd_nrs:
            entity = await self.search_service.find_by_customer_number(kd_nr)
            if entity:
                return MatchResult(
                    entity=entity,
                    confidence=self.CUSTOMER_NUMBER_CONFIDENCE,
                    match_type="customer_number",
                    match_details=f"Kundennummer {kd_nr} gefunden",
                )

        # Auch Lieferantennummer versuchen
        lief_nrs = extract_supplier_numbers(text)
        for lief_nr in lief_nrs:
            entity = await self.search_service.find_by_supplier_number(lief_nr)
            if entity:
                return MatchResult(
                    entity=entity,
                    confidence=self.CUSTOMER_NUMBER_CONFIDENCE,
                    match_type="supplier_number",
                    match_details=f"Lieferantennummer {lief_nr} gefunden",
                )

        return None

    async def _try_iban_match(self, text: str) -> Optional[MatchResult]:
        """Versucht Match über IBAN."""
        ibans = extract_ibans(text)

        for iban in ibans:
            entity = await self.search_service.find_by_iban(iban)
            if entity:
                return MatchResult(
                    entity=entity,
                    confidence=self.IBAN_CONFIDENCE,
                    match_type="iban",
                    match_details=f"IBAN {iban[:8]}... gefunden",
                )

        return None

    async def _try_vat_id_match(self, text: str) -> Optional[MatchResult]:
        """Versucht Match über USt-IdNr."""
        vat_ids = extract_vat_ids(text)

        for vat_id in vat_ids:
            entity = await self.search_service.find_by_vat_id(vat_id)
            if entity:
                return MatchResult(
                    entity=entity,
                    confidence=self.VAT_ID_CONFIDENCE,
                    match_type="vat_id",
                    match_details=f"USt-IdNr {vat_id} gefunden",
                )

        return None

    async def _try_matchcode_match(self, text: str) -> Optional[MatchResult]:
        """Versucht Match über Matchcode/Firmenname."""
        matchcodes = extract_matchcodes(text)

        best_match: Optional[MatchResult] = None
        best_confidence = 0.0

        for code in matchcodes:
            matches = await self.search_service.find_by_matchcode(
                code, similarity_threshold=0.7
            )

            for entity, similarity in matches:
                # Confidence basierend auf Ähnlichkeit
                if similarity >= 0.95:
                    confidence = self.MATCHCODE_EXACT_CONFIDENCE
                elif similarity >= 0.85:
                    confidence = self.NAME_FUZZY_CONFIDENCE
                else:
                    confidence = similarity * 0.8  # Reduzierte Confidence

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = MatchResult(
                        entity=entity,
                        confidence=confidence,
                        match_type="matchcode",
                        match_details=f"Matchcode '{code}' ähnlich zu '{entity.name}' ({similarity:.0%})",
                    )

        return best_match


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_document_entity_linker_service(
    db: AsyncSession,
) -> DocumentEntityLinkerService:
    """Factory-Funktion für Dependency Injection."""
    return DocumentEntityLinkerService(db)
