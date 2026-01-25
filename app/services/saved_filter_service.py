# -*- coding: utf-8 -*-
"""Saved Filter Service - Server-side Filter Persistence with Sharing.

Phase 4.5: Frontend UX Enhancement - Saved Filters

Dieses Modul implementiert:
- CRUD-Operationen fuer gespeicherte Filter
- Sharing-Funktionalitaet innerhalb einer Company
- Usage-Tracking fuer Sortierung nach Haeufigkeit
- Default-Filter pro User/Feature
"""
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedFilter
from app.core.exceptions import NotFoundError, ForbiddenError, ValidationError


# Erlaubte Features fuer Filter
ALLOWED_FEATURES = {
    "documents",
    "invoices",
    "entities",
    "transactions",
    "contracts",
    "shipments",
    "approvals",
    "validation",
    "ocr-training",
    "banking",
    "dunning",
}


class SavedFilterService:
    """Service fuer Server-seitige Filter-Persistenz.

    Bietet:
    - Speichern und Abrufen von Filtern pro Feature
    - Sharing innerhalb einer Company
    - Default-Filter-Verwaltung
    - Usage-Tracking
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_filters_for_feature(
        self,
        user_id: UUID,
        company_id: UUID,
        feature: str,
        include_shared: bool = True,
    ) -> List[SavedFilter]:
        """Hole alle Filter fuer ein Feature (eigene + geteilte).

        Args:
            user_id: ID des aktuellen Users
            company_id: ID der Company
            feature: Feature-Name (documents, invoices, etc.)
            include_shared: Ob geteilte Filter eingeschlossen werden sollen

        Returns:
            Liste von SavedFilter sortiert nach: Default > Own > Shared, dann use_count
        """
        self._validate_feature(feature)

        conditions = [
            SavedFilter.feature == feature,
            SavedFilter.deleted_at.is_(None),
        ]

        if include_shared:
            # Eigene Filter ODER geteilte Filter der gleichen Company
            conditions.append(
                or_(
                    SavedFilter.user_id == user_id,
                    and_(
                        SavedFilter.company_id == company_id,
                        SavedFilter.is_shared == True,  # noqa: E712
                    )
                )
            )
        else:
            # Nur eigene Filter
            conditions.append(SavedFilter.user_id == user_id)

        query = (
            select(SavedFilter)
            .where(and_(*conditions))
            .order_by(
                SavedFilter.is_default.desc(),  # Default zuerst
                (SavedFilter.user_id == user_id).desc(),  # Eigene vor geteilten
                SavedFilter.use_count.desc(),  # Haeufig genutzte zuerst
                SavedFilter.last_used_at.desc().nullslast(),  # Zuletzt genutzte
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_filter_by_id(
        self,
        filter_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> SavedFilter:
        """Hole einen Filter by ID (mit Zugriffspr\u00fcfung).

        Args:
            filter_id: Filter-ID
            user_id: ID des aktuellen Users
            company_id: ID der Company

        Returns:
            SavedFilter wenn gefunden und Zugriff erlaubt

        Raises:
            NotFoundError: Filter nicht gefunden
            ForbiddenError: Kein Zugriff (weder Eigentuemer noch geteilt)
        """
        query = select(SavedFilter).where(
            and_(
                SavedFilter.id == filter_id,
                SavedFilter.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        saved_filter = result.scalar_one_or_none()

        if not saved_filter:
            raise NotFoundError(f"Filter mit ID {filter_id} nicht gefunden")

        # Zugriffspruefung: Eigentuemer ODER geteilt in der gleichen Company
        is_owner = saved_filter.user_id == user_id
        is_shared_in_company = (
            saved_filter.is_shared and saved_filter.company_id == company_id
        )

        if not is_owner and not is_shared_in_company:
            raise ForbiddenError("Kein Zugriff auf diesen Filter")

        return saved_filter

    async def create_filter(
        self,
        user_id: UUID,
        company_id: UUID,
        name: str,
        feature: str,
        filter_config: dict,
        description: Optional[str] = None,
        is_shared: bool = False,
        is_default: bool = False,
    ) -> SavedFilter:
        """Erstelle einen neuen gespeicherten Filter.

        Args:
            user_id: ID des Users (Eigentuemer)
            company_id: ID der Company
            name: Anzeigename des Filters
            feature: Feature-Name (documents, invoices, etc.)
            filter_config: Filter-Konfiguration als Dict
            description: Optionale Beschreibung
            is_shared: Ob der Filter geteilt werden soll
            is_default: Ob dies der Standard-Filter sein soll

        Returns:
            Erstellter SavedFilter

        Raises:
            ValidationError: Ungueltige Eingabedaten
        """
        self._validate_feature(feature)
        self._validate_filter_config(filter_config)

        if not name or not name.strip():
            raise ValidationError("Filtername darf nicht leer sein")

        if len(name) > 255:
            raise ValidationError("Filtername darf maximal 255 Zeichen haben")

        # Wenn default, alle anderen defaults fuer diesen User/Feature zuruecksetzen
        if is_default:
            await self._reset_default_filters(user_id, feature)

        saved_filter = SavedFilter(
            user_id=user_id,
            company_id=company_id,
            name=name.strip(),
            feature=feature,
            filter_config=filter_config,
            description=description.strip() if description else None,
            is_shared=is_shared,
            is_default=is_default,
        )

        self.db.add(saved_filter)
        await self.db.flush()
        return saved_filter

    async def update_filter(
        self,
        filter_id: UUID,
        user_id: UUID,
        company_id: UUID,
        name: Optional[str] = None,
        filter_config: Optional[dict] = None,
        description: Optional[str] = None,
        is_shared: Optional[bool] = None,
        is_default: Optional[bool] = None,
    ) -> SavedFilter:
        """Aktualisiere einen gespeicherten Filter.

        Args:
            filter_id: Filter-ID
            user_id: ID des aktuellen Users
            company_id: ID der Company
            name: Neuer Name (optional)
            filter_config: Neue Konfiguration (optional)
            description: Neue Beschreibung (optional)
            is_shared: Neuer Sharing-Status (optional)
            is_default: Neuer Default-Status (optional)

        Returns:
            Aktualisierter SavedFilter

        Raises:
            NotFoundError: Filter nicht gefunden
            ForbiddenError: Kein Schreibzugriff (nicht Eigentuemer)
        """
        saved_filter = await self._get_owned_filter(filter_id, user_id)

        if name is not None:
            if not name.strip():
                raise ValidationError("Filtername darf nicht leer sein")
            if len(name) > 255:
                raise ValidationError("Filtername darf maximal 255 Zeichen haben")
            saved_filter.name = name.strip()

        if filter_config is not None:
            self._validate_filter_config(filter_config)
            saved_filter.filter_config = filter_config

        if description is not None:
            saved_filter.description = description.strip() if description else None

        if is_shared is not None:
            saved_filter.is_shared = is_shared

        if is_default is not None:
            if is_default:
                await self._reset_default_filters(user_id, saved_filter.feature)
            saved_filter.is_default = is_default

        saved_filter.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return saved_filter

    async def delete_filter(
        self,
        filter_id: UUID,
        user_id: UUID,
        hard_delete: bool = False,
    ) -> None:
        """Loesche einen gespeicherten Filter (soft delete).

        Args:
            filter_id: Filter-ID
            user_id: ID des aktuellen Users
            hard_delete: Wenn True, permanentes Loeschen statt Soft-Delete

        Raises:
            NotFoundError: Filter nicht gefunden
            ForbiddenError: Kein Loeschzugriff (nicht Eigentuemer)
        """
        saved_filter = await self._get_owned_filter(filter_id, user_id)

        if hard_delete:
            await self.db.delete(saved_filter)
        else:
            saved_filter.deleted_at = datetime.now(timezone.utc)

        await self.db.flush()

    async def record_filter_usage(
        self,
        filter_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> None:
        """Zeichne Nutzung eines Filters auf.

        Erhoeht use_count und aktualisiert last_used_at.

        Args:
            filter_id: Filter-ID
            user_id: ID des aktuellen Users
            company_id: ID der Company
        """
        # Zugriffspruefung (wirft Exception bei fehlendem Zugriff)
        await self.get_filter_by_id(filter_id, user_id, company_id)

        stmt = (
            update(SavedFilter)
            .where(SavedFilter.id == filter_id)
            .values(
                use_count=SavedFilter.use_count + 1,
                last_used_at=datetime.now(timezone.utc),
            )
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def get_default_filter(
        self,
        user_id: UUID,
        feature: str,
    ) -> Optional[SavedFilter]:
        """Hole den Standard-Filter eines Users fuer ein Feature.

        Args:
            user_id: User-ID
            feature: Feature-Name

        Returns:
            SavedFilter oder None wenn kein Default gesetzt
        """
        self._validate_feature(feature)

        query = select(SavedFilter).where(
            and_(
                SavedFilter.user_id == user_id,
                SavedFilter.feature == feature,
                SavedFilter.is_default == True,  # noqa: E712
                SavedFilter.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def set_default_filter(
        self,
        filter_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> SavedFilter:
        """Setze einen Filter als Standard fuer das Feature.

        Args:
            filter_id: Filter-ID
            user_id: User-ID
            company_id: Company-ID

        Returns:
            Aktualisierter Filter

        Raises:
            NotFoundError: Filter nicht gefunden
            ForbiddenError: Kein Zugriff
        """
        saved_filter = await self.get_filter_by_id(filter_id, user_id, company_id)

        # Reset alle anderen defaults fuer dieses Feature
        await self._reset_default_filters(user_id, saved_filter.feature)

        # Setze diesen als default
        saved_filter.is_default = True
        await self.db.flush()

        return saved_filter

    async def clear_default_filter(
        self,
        user_id: UUID,
        feature: str,
    ) -> None:
        """Entferne den Standard-Filter fuer ein Feature.

        Args:
            user_id: User-ID
            feature: Feature-Name
        """
        self._validate_feature(feature)
        await self._reset_default_filters(user_id, feature)

    async def duplicate_filter(
        self,
        filter_id: UUID,
        user_id: UUID,
        company_id: UUID,
        new_name: Optional[str] = None,
    ) -> SavedFilter:
        """Dupliziere einen Filter (auch geteilte).

        Args:
            filter_id: Quell-Filter-ID
            user_id: ID des neuen Eigent\u00fcmers
            company_id: Company-ID
            new_name: Neuer Name (optional, sonst "Kopie von {name}")

        Returns:
            Neuer SavedFilter als Kopie
        """
        source = await self.get_filter_by_id(filter_id, user_id, company_id)

        name = new_name or f"Kopie von {source.name}"

        return await self.create_filter(
            user_id=user_id,
            company_id=company_id,
            name=name,
            feature=source.feature,
            filter_config=source.filter_config.copy(),
            description=source.description,
            is_shared=False,  # Kopien sind initial privat
            is_default=False,  # Kopien sind nicht default
        )

    # -------------------------------------------------------------------------
    # Private Helper Methods
    # -------------------------------------------------------------------------

    async def _get_owned_filter(
        self,
        filter_id: UUID,
        user_id: UUID,
    ) -> SavedFilter:
        """Hole einen Filter nur wenn der User Eigentuemer ist.

        Raises:
            NotFoundError: Filter nicht gefunden
            ForbiddenError: User ist nicht Eigentuemer
        """
        query = select(SavedFilter).where(
            and_(
                SavedFilter.id == filter_id,
                SavedFilter.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(query)
        saved_filter = result.scalar_one_or_none()

        if not saved_filter:
            raise NotFoundError(f"Filter mit ID {filter_id} nicht gefunden")

        if saved_filter.user_id != user_id:
            raise ForbiddenError("Nur der Eigentuemer kann diesen Filter bearbeiten")

        return saved_filter

    async def _reset_default_filters(
        self,
        user_id: UUID,
        feature: str,
    ) -> None:
        """Setze alle default-Filter eines Users fuer ein Feature zurueck."""
        stmt = (
            update(SavedFilter)
            .where(
                and_(
                    SavedFilter.user_id == user_id,
                    SavedFilter.feature == feature,
                    SavedFilter.is_default == True,  # noqa: E712
                )
            )
            .values(is_default=False)
        )
        await self.db.execute(stmt)

    def _validate_feature(self, feature: str) -> None:
        """Validiere Feature-Namen."""
        if not feature:
            raise ValidationError("Feature darf nicht leer sein")

        if feature not in ALLOWED_FEATURES:
            raise ValidationError(
                f"Ungueltiges Feature: {feature}. "
                f"Erlaubt: {', '.join(sorted(ALLOWED_FEATURES))}"
            )

    def _validate_filter_config(self, config: dict) -> None:
        """Validiere Filter-Konfiguration."""
        if not isinstance(config, dict):
            raise ValidationError("filter_config muss ein Objekt sein")

        # Maximale Groesse fuer JSONB (ca. 64KB)
        import json
        config_str = json.dumps(config)
        if len(config_str) > 65536:
            raise ValidationError("Filter-Konfiguration ist zu gross (max 64KB)")


# Factory Function fuer Dependency Injection
def get_saved_filter_service(db: AsyncSession) -> SavedFilterService:
    """Factory fuer SavedFilterService."""
    return SavedFilterService(db)
