"""
Entity Search Service.

Erweiterte Suchfunktionen für BusinessEntity mit Lexware-Integration:
- Suche nach Kundennummer
- Suche nach Lieferantennummer
- Suche nach Matchcode
- Fuzzy-Name-Suche
- IBAN/VAT-ID Suche
"""

import re
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID

import structlog
from sqlalchemy import select, or_, and_, func, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BusinessEntity, EntityType
from app.core.security.sensitive_data_filter import get_pii_safe_logger

# SECURITY: Use PII-safe logger for GDPR compliance
# Never log customer numbers, IBANs, VAT-IDs, or other PII
logger = get_pii_safe_logger(__name__)


def normalize_text(text: str) -> str:
    """Normalisiert Text für Vergleiche."""
    if not text:
        return ""
    text = str(text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def calculate_similarity(text1: str, text2: str) -> float:
    """Berechnet Ähnlichkeit zwischen zwei Texten (0.0-1.0)."""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(
        None, normalize_text(text1), normalize_text(text2)
    ).ratio()


class EntitySearchService:
    """Service für erweiterte Entity-Suche mit Lexware-Integration."""

    DEFAULT_SIMILARITY_THRESHOLD = 0.7

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db

    # ========================================================================
    # KUNDENNUMMER-SUCHE
    # ========================================================================

    async def find_by_customer_number(
        self,
        kd_nr: str,
        company: Optional[str] = None,
    ) -> Optional[BusinessEntity]:
        """
        Sucht Kunde nach Kundennummer.

        Sucht in:
        1. primary_customer_number (exakt)
        2. lexware_ids->folie->kd_nr
        3. lexware_ids->messer->kd_nr

        Args:
            kd_nr: Kundennummer
            company: Optional 'folie' oder 'messer' für spezifische Suche

        Returns:
            BusinessEntity oder None
        """
        kd_nr_clean = str(kd_nr).strip()
        if not kd_nr_clean:
            return None

        # 1. Suche in primary_customer_number
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.primary_customer_number == kd_nr_clean,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity:
            return entity

        # 2. Suche in lexware_ids JSONB
        if company:
            # Spezifische Firma
            jsonb_path = f"lexware_ids->'{company}'->>'kd_nr'"
            stmt = select(BusinessEntity).where(
                and_(
                    func.json_extract_path_text(
                        BusinessEntity.lexware_ids, company, "kd_nr"
                    ) == kd_nr_clean,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        else:
            # Beide Firmen durchsuchen
            stmt = select(BusinessEntity).where(
                and_(
                    or_(
                        func.json_extract_path_text(
                            BusinessEntity.lexware_ids, "folie", "kd_nr"
                        ) == kd_nr_clean,
                        func.json_extract_path_text(
                            BusinessEntity.lexware_ids, "messer", "kd_nr"
                        ) == kd_nr_clean,
                    ),
                    BusinessEntity.deleted_at.is_(None),
                )
            )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_customers_by_number_pattern(
        self,
        pattern: str,
        limit: int = 20,
    ) -> list[BusinessEntity]:
        """
        Sucht Kunden nach Kundennummer-Muster (LIKE-Suche).

        Args:
            pattern: Suchmuster (z.B. "123%" für alle die mit 123 beginnen)
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von BusinessEntity
        """
        stmt = (
            select(BusinessEntity)
            .where(
                and_(
                    BusinessEntity.primary_customer_number.ilike(pattern),
                    BusinessEntity.entity_type == EntityType.CUSTOMER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ========================================================================
    # LIEFERANTENNUMMER-SUCHE
    # ========================================================================

    async def find_by_supplier_number(
        self,
        lief_nr: str,
        company: Optional[str] = None,
    ) -> Optional[BusinessEntity]:
        """
        Sucht Lieferant nach Lieferantennummer.

        Args:
            lief_nr: Lieferantennummer
            company: Optional 'folie' oder 'messer'

        Returns:
            BusinessEntity oder None
        """
        lief_nr_clean = str(lief_nr).strip()
        if not lief_nr_clean:
            return None

        # Suche in primary_supplier_number
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.primary_supplier_number == lief_nr_clean,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        entity = result.scalar_one_or_none()
        if entity:
            return entity

        # Suche in lexware_ids
        if company:
            stmt = select(BusinessEntity).where(
                and_(
                    func.json_extract_path_text(
                        BusinessEntity.lexware_ids, company, "lief_nr"
                    ) == lief_nr_clean,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        else:
            stmt = select(BusinessEntity).where(
                and_(
                    or_(
                        func.json_extract_path_text(
                            BusinessEntity.lexware_ids, "folie", "lief_nr"
                        ) == lief_nr_clean,
                        func.json_extract_path_text(
                            BusinessEntity.lexware_ids, "messer", "lief_nr"
                        ) == lief_nr_clean,
                    ),
                    BusinessEntity.deleted_at.is_(None),
                )
            )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # MATCHCODE-SUCHE
    # ========================================================================

    async def find_by_matchcode(
        self,
        matchcode: str,
        entity_type: Optional[EntityType] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> list[tuple[BusinessEntity, float]]:
        """
        Sucht Entities nach Matchcode mit Fuzzy-Matching.

        Durchsucht:
        1. name (exakt)
        2. short_name (exakt)
        3. name_aliases (enthält)
        4. lexware_ids->*->matchcode

        Args:
            matchcode: Matchcode zum Suchen
            entity_type: Optional CUSTOMER oder SUPPLIER Filter
            similarity_threshold: Minimale Ähnlichkeit (0.0-1.0)

        Returns:
            Liste von (BusinessEntity, similarity) Tupeln, sortiert nach Ähnlichkeit
        """
        matchcode_clean = normalize_text(matchcode)
        if not matchcode_clean:
            return []

        # Query bauen
        stmt = select(BusinessEntity).where(BusinessEntity.deleted_at.is_(None))

        if entity_type:
            stmt = stmt.where(BusinessEntity.entity_type == entity_type.value)

        result = await self.db.execute(stmt)
        entities = result.scalars().all()

        # Ähnlichkeit berechnen
        matches: list[tuple[BusinessEntity, float]] = []

        for entity in entities:
            best_similarity = 0.0

            # Name prüfen
            if entity.name:
                sim = calculate_similarity(matchcode, entity.name)
                best_similarity = max(best_similarity, sim)

            # Short name prüfen
            if entity.short_name:
                sim = calculate_similarity(matchcode, entity.short_name)
                best_similarity = max(best_similarity, sim)

            # Display name prüfen
            if entity.display_name:
                sim = calculate_similarity(matchcode, entity.display_name)
                best_similarity = max(best_similarity, sim)

            # Aliases prüfen
            if entity.name_aliases:
                for alias in entity.name_aliases:
                    sim = calculate_similarity(matchcode, alias)
                    best_similarity = max(best_similarity, sim)

            # Lexware matchcodes prüfen
            if entity.lexware_ids:
                for company_data in entity.lexware_ids.values():
                    if isinstance(company_data, dict):
                        lw_matchcode = company_data.get("matchcode", "")
                        if lw_matchcode:
                            sim = calculate_similarity(matchcode, lw_matchcode)
                            best_similarity = max(best_similarity, sim)

            if best_similarity >= similarity_threshold:
                matches.append((entity, best_similarity))

        # Nach Ähnlichkeit sortieren
        matches.sort(key=lambda x: x[1], reverse=True)

        return matches

    # ========================================================================
    # IDENTIFIER-SUCHE (IBAN, VAT-ID)
    # ========================================================================

    async def find_by_iban(self, iban: str) -> Optional[BusinessEntity]:
        """
        Sucht Entity nach IBAN.

        Args:
            iban: IBAN (wird normalisiert)

        Returns:
            BusinessEntity oder None
        """
        # IBAN normalisieren (Leerzeichen entfernen, Großbuchstaben)
        iban_clean = re.sub(r"\s+", "", iban.upper())
        if not iban_clean or len(iban_clean) < 15:
            return None

        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.iban == iban_clean,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_vat_id(self, vat_id: str) -> Optional[BusinessEntity]:
        """
        Sucht Entity nach USt-IdNr.

        Args:
            vat_id: USt-IdNr (wird normalisiert)

        Returns:
            BusinessEntity oder None
        """
        # VAT ID normalisieren
        vat_clean = re.sub(r"\s+", "", vat_id.upper())
        if not vat_clean or len(vat_clean) < 9:
            return None

        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.vat_id == vat_clean,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # ========================================================================
    # KOMBINIERTE SUCHE
    # ========================================================================

    async def smart_search(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        company: Optional[str] = None,
        limit: int = 20,
    ) -> list[tuple[BusinessEntity, float, str]]:
        """
        Intelligente Suche über alle Felder.

        Erkennt automatisch:
        - Kundennummer (nur Ziffern)
        - IBAN (beginnt mit Ländercode)
        - VAT-ID (DE + 9 Ziffern)
        - Name/Matchcode (alles andere)

        Args:
            query: Suchbegriff
            entity_type: Optional CUSTOMER oder SUPPLIER
            company: Optional 'folie' oder 'messer'
            limit: Maximale Ergebnisse

        Returns:
            Liste von (BusinessEntity, confidence, match_type) Tupeln
        """
        query_clean = query.strip()
        if not query_clean:
            return []

        results: list[tuple[BusinessEntity, float, str]] = []

        # 1. Prüfe auf Kundennummer (nur Ziffern)
        if query_clean.isdigit():
            entity = await self.find_by_customer_number(query_clean, company)
            if entity:
                results.append((entity, 1.0, "customer_number"))
                return results[:limit]

            # Auch als Lieferantennummer versuchen
            entity = await self.find_by_supplier_number(query_clean, company)
            if entity:
                results.append((entity, 1.0, "supplier_number"))
                return results[:limit]

        # 2. Prüfe auf IBAN
        if re.match(r"^[A-Z]{2}\d", query_clean.upper()):
            entity = await self.find_by_iban(query_clean)
            if entity:
                results.append((entity, 1.0, "iban"))
                return results[:limit]

        # 3. Prüfe auf VAT-ID
        if re.match(r"^DE\s*\d{9}$", query_clean.upper().replace(" ", "")):
            entity = await self.find_by_vat_id(query_clean)
            if entity:
                results.append((entity, 1.0, "vat_id"))
                return results[:limit]

        # 4. Fuzzy Matchcode/Name Suche
        matches = await self.find_by_matchcode(
            query_clean,
            entity_type=entity_type,
            similarity_threshold=0.5,  # Niedrigerer Threshold für Suche
        )

        for entity, similarity in matches[:limit]:
            # Optional nach Company filtern
            if company and entity.company_presence:
                if company not in entity.company_presence:
                    continue
            results.append((entity, similarity, "matchcode"))

        return results[:limit]

    # ========================================================================
    # FILTER-METHODEN
    # ========================================================================

    async def find_by_company(
        self,
        company: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BusinessEntity]:
        """
        Findet alle Entities einer bestimmten Firma.

        Args:
            company: 'folie' oder 'messer'
            entity_type: Optional CUSTOMER oder SUPPLIER
            limit: Maximale Ergebnisse
            offset: Pagination Offset

        Returns:
            Liste von BusinessEntity
        """
        # JSONB contains check
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.company_presence.contains([company]),
                BusinessEntity.deleted_at.is_(None),
            )
        )

        if entity_type:
            stmt = stmt.where(BusinessEntity.entity_type == entity_type.value)

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_in_multiple_companies(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
        min_companies: int = 2,
    ) -> list[BusinessEntity]:
        """
        Findet Entities die in mehreren Firmen existieren.

        Ersetzt die hardcoded 'find_in_both_companies' Methode mit dynamischer
        Abfrage basierend auf der Anzahl der Firmen im company_presence Array.

        Args:
            entity_type: Optional CUSTOMER oder SUPPLIER
            limit: Maximale Ergebnisse
            min_companies: Minimale Anzahl an Firmen (default: 2)

        Returns:
            Liste von BusinessEntity
        """
        stmt = select(BusinessEntity).where(
            and_(
                func.jsonb_array_length(BusinessEntity.company_presence) >= min_companies,
                BusinessEntity.deleted_at.is_(None),
            )
        )

        if entity_type:
            stmt = stmt.where(BusinessEntity.entity_type == entity_type.value)

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # Legacy alias for backwards compatibility
    async def find_in_both_companies(
        self,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
    ) -> list[BusinessEntity]:
        """
        Legacy-Methode: Findet Entities die in mehreren Firmen existieren.

        DEPRECATED: Bitte find_in_multiple_companies verwenden.
        """
        return await self.find_in_multiple_companies(
            entity_type=entity_type,
            limit=limit,
            min_companies=2,
        )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_entity_search_service(db: AsyncSession) -> EntitySearchService:
    """Factory-Funktion für Dependency Injection."""
    return EntitySearchService(db)
