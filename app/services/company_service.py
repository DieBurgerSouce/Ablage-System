# -*- coding: utf-8 -*-
"""
CompanyService - Multi-Tenant Company Management.

Zentraler Service für Firmen-bezogene Operationen:
- Dynamisches Laden von Firmen (ersetzt hardcoded "folie"/"messer")
- Company-Lookups per short_name, name, oder ID
- Firmen-spezifische Konfigurationen
- Legacy-Kompatibilität für Altdaten

Feinpoliert und durchdacht - Enterprise Multi-Tenant Support.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from uuid import UUID
from functools import lru_cache

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, UserCompany

logger = structlog.get_logger(__name__)


# =============================================================================
# LEGACY MAPPING (für Migration von hardcoded Werten)
# =============================================================================

# Legacy short_names die in Altdaten verwendet wurden
LEGACY_COMPANY_ALIASES: Dict[str, str] = {
    "folie": "folie",
    "messer": "messer",
    "spargelmesser": "messer",  # Alias
}

# Legacy Display-Namen für UI
LEGACY_DISPLAY_NAMES: Dict[str, str] = {
    "folie": "Folie",
    "messer": "Spargelmesser",
}


# =============================================================================
# COMPANY SERVICE
# =============================================================================

class CompanyService:
    """
    Service für Multi-Tenant Firmen-Operationen.

    Bietet:
    - Dynamische Firmen-Abfragen statt hardcoded Werte
    - Legacy-Kompatibilität für "folie"/"messer" Altdaten
    - Caching für Performance
    - Firmen-spezifische Konfigurationen
    """

    async def get_all_companies(
        self,
        db: AsyncSession,
        include_inactive: bool = False
    ) -> List[Company]:
        """
        Laedt alle verfügbaren Firmen.

        Args:
            db: Datenbank-Session
            include_inactive: Auch inaktive Firmen laden

        Returns:
            Liste aller Firmen
        """
        query = select(Company).where(Company.deleted_at.is_(None))

        if not include_inactive:
            query = query.where(Company.is_active == True)

        query = query.order_by(Company.name)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_company_by_id(
        self,
        db: AsyncSession,
        company_id: UUID
    ) -> Optional[Company]:
        """
        Laedt eine Firma per UUID.

        Args:
            db: Datenbank-Session
            company_id: UUID der Firma

        Returns:
            Company oder None
        """
        result = await db.execute(
            select(Company)
            .where(Company.id == company_id)
            .where(Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_company_by_short_name(
        self,
        db: AsyncSession,
        short_name: str
    ) -> Optional[Company]:
        """
        Laedt eine Firma per short_name.

        Berücksichtigt Legacy-Aliase (z.B. "spargelmesser" -> "messer").

        Args:
            db: Datenbank-Session
            short_name: Kurzname der Firma

        Returns:
            Company oder None
        """
        # Normalisiere und prüfe Legacy-Aliase
        normalized = short_name.lower().strip()
        actual_short_name = LEGACY_COMPANY_ALIASES.get(normalized, normalized)

        result = await db.execute(
            select(Company)
            .where(Company.short_name == actual_short_name)
            .where(Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_company_by_name(
        self,
        db: AsyncSession,
        name: str
    ) -> Optional[Company]:
        """
        Laedt eine Firma per Name (exact match).

        Args:
            db: Datenbank-Session
            name: Name der Firma

        Returns:
            Company oder None
        """
        result = await db.execute(
            select(Company)
            .where(Company.name == name)
            .where(Company.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def resolve_company_identifier(
        self,
        db: AsyncSession,
        identifier: str
    ) -> Optional[Company]:
        """
        Loeest einen beliebigen Firmen-Identifier auf.

        Versucht in dieser Reihenfolge:
        1. UUID
        2. short_name (mit Legacy-Alias-Support)
        3. name (exact match)

        Args:
            db: Datenbank-Session
            identifier: UUID, short_name, oder name

        Returns:
            Company oder None
        """
        # 1. UUID versuchen
        try:
            company_id = UUID(identifier)
            company = await self.get_company_by_id(db, company_id)
            if company:
                return company
        except ValueError as e:
            logger.debug("company_identifier_uuid_parse_failed", identifier=identifier, error_type=type(e).__name__)

        # 2. short_name versuchen
        company = await self.get_company_by_short_name(db, identifier)
        if company:
            return company

        # 3. name versuchen
        return await self.get_company_by_name(db, identifier)

    async def get_user_companies(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[Company]:
        """
        Laedt alle Firmen eines Benutzers.

        Args:
            db: Datenbank-Session
            user_id: UUID des Benutzers

        Returns:
            Liste der Firmen
        """
        result = await db.execute(
            select(Company)
            .join(UserCompany, UserCompany.company_id == Company.id)
            .where(UserCompany.user_id == user_id)
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active == True)
            .order_by(Company.name)
        )
        return list(result.scalars().all())

    async def get_company_short_names(
        self,
        db: AsyncSession
    ) -> List[str]:
        """
        Gibt alle verfügbaren Firmen-short_names zurück.

        Ersetzt hardcoded ["folie", "messer"] Listen.

        Args:
            db: Datenbank-Session

        Returns:
            Liste der short_names
        """
        result = await db.execute(
            select(Company.short_name)
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active == True)
            .where(Company.short_name.isnot(None))
            .order_by(Company.name)
        )
        return [row[0] for row in result.all() if row[0]]

    async def get_company_display_map(
        self,
        db: AsyncSession
    ) -> Dict[str, str]:
        """
        Gibt ein Mapping von short_name -> display_name zurück.

        Ersetzt hardcoded FOLDER_NAMES Dictionaries.

        Args:
            db: Datenbank-Session

        Returns:
            Dict mit {short_name: display_name}
        """
        result = await db.execute(
            select(Company.short_name, Company.name)
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active == True)
            .where(Company.short_name.isnot(None))
        )
        return {
            row.short_name: row.name
            for row in result.all()
            if row.short_name
        }

    async def get_company_count(self, db: AsyncSession) -> int:
        """
        Zaehlt alle aktiven Firmen.

        Args:
            db: Datenbank-Session

        Returns:
            Anzahl der Firmen
        """
        result = await db.execute(
            select(func.count(Company.id))
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active == True)
        )
        return result.scalar() or 0

    def get_legacy_display_name(self, short_name: str) -> str:
        """
        Gibt den Legacy Display-Namen für einen short_name zurück.

        Fallback für Faelle wo keine DB-Abfrage möglich ist.

        Args:
            short_name: Kurzname der Firma

        Returns:
            Display-Name (oder short_name.title() als Fallback)
        """
        normalized = short_name.lower()
        return LEGACY_DISPLAY_NAMES.get(normalized, short_name.title())

    def normalize_company_short_name(self, short_name: str) -> str:
        """
        Normalisiert einen short_name (Legacy-Alias-Support).

        Args:
            short_name: Zu normalisierender short_name

        Returns:
            Normalisierter short_name
        """
        normalized = short_name.lower().strip()
        return LEGACY_COMPANY_ALIASES.get(normalized, normalized)

    async def validate_company_presence(
        self,
        db: AsyncSession,
        company_presence: List[str],
    ) -> Tuple[List[str], List[str]]:
        """
        Validiert eine Liste von company_presence Werten.

        Prüft ob alle short_names existieren und gibt valide/invalide zurück.

        Args:
            db: Datenbank-Session
            company_presence: Liste von short_names

        Returns:
            Tuple von (valide_short_names, invalide_short_names)
        """
        if not company_presence:
            return [], []

        # Alle verfügbaren short_names laden
        valid_short_names = set(await self.get_company_short_names(db))

        valid = []
        invalid = []

        for short_name in company_presence:
            normalized = self.normalize_company_short_name(short_name)
            if normalized in valid_short_names:
                valid.append(normalized)
            else:
                invalid.append(short_name)

        return valid, invalid

    async def ensure_companies_exist(
        self,
        db: AsyncSession,
        short_names: List[str],
    ) -> Dict[str, Optional[Company]]:
        """
        Stellt sicher dass Firmen existieren und gibt ein Mapping zurück.

        Args:
            db: Datenbank-Session
            short_names: Liste von short_names

        Returns:
            Dict mit {short_name: Company oder None}
        """
        result: Dict[str, Optional[Company]] = {}

        for short_name in short_names:
            normalized = self.normalize_company_short_name(short_name)
            company = await self.get_company_by_short_name(db, normalized)
            result[short_name] = company

        return result

    async def get_default_company(self, db: AsyncSession) -> Optional[Company]:
        """
        Gibt die Standard-Firma zurück.

        Args:
            db: Datenbank-Session

        Returns:
            Default Company oder None
        """
        from sqlalchemy import select

        result = await db.execute(
            select(Company)
            .where(Company.is_default == True)
            .where(Company.deleted_at.is_(None))
            .where(Company.is_active == True)
        )
        return result.scalar_one_or_none()


# =============================================================================
# SINGLETON
# =============================================================================

_company_service: Optional[CompanyService] = None


def get_company_service() -> CompanyService:
    """Gibt die Singleton-Instanz des CompanyService zurück."""
    global _company_service
    if _company_service is None:
        _company_service = CompanyService()
    return _company_service
