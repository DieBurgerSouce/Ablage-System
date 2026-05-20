# -*- coding: utf-8 -*-
"""
Tune Service für Dokument-Kontext-Management.

Verwaltet Tunes (Dokumentkontext-Definitionen) für kontextspezifische
OCR-Verarbeitung und Backend-Auswahl.

Alle Fehlermeldungen auf Deutsch.
"""

from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

import structlog
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.models import Tune
from app.api.schemas.tunes import TuneCreate, TuneUpdate, TuneResponse
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class TuneService:
    """Service für Tune-Verwaltung mit CRUD-Operationen."""

    @staticmethod
    async def get_all(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False,
        include_system: bool = True
    ) -> List[Tune]:
        """
        Alle Tunes abrufen mit optionaler Filterung.

        Args:
            db: Async Datenbank-Session
            skip: Anzahl zu überspringender Einträge (Pagination)
            limit: Maximale Anzahl zurückzugebender Einträge
            active_only: Nur aktive Tunes zurückgeben
            include_system: System-Tunes einbeziehen

        Returns:
            Liste von Tune-Objekten
        """
        query = select(Tune)

        if active_only:
            query = query.where(Tune.is_active == True)

        if not include_system:
            query = query.where(Tune.is_system == False)

        query = query.offset(skip).limit(limit).order_by(Tune.name)
        result = await db.execute(query)

        logger.debug("tunes_fetched", count=result.rowcount, active_only=active_only)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(db: AsyncSession, tune_id: UUID) -> Optional[Tune]:
        """
        Tune nach ID abrufen.

        Args:
            db: Async Datenbank-Session
            tune_id: UUID des Tunes

        Returns:
            Tune-Objekt oder None wenn nicht gefunden
        """
        query = select(Tune).where(Tune.id == tune_id)
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def get_by_name(db: AsyncSession, name: str) -> Optional[Tune]:
        """
        Tune nach Name abrufen.

        Args:
            db: Async Datenbank-Session
            name: Name des Tunes

        Returns:
            Tune-Objekt oder None wenn nicht gefunden
        """
        query = select(Tune).where(Tune.name == name)
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def create(db: AsyncSession, tune_data: TuneCreate) -> Tune:
        """
        Neuen Tune erstellen.

        Args:
            db: Async Datenbank-Session
            tune_data: Tune-Erstellungsdaten

        Returns:
            Erstelltes Tune-Objekt

        Raises:
            ValueError: Wenn Name bereits existiert
        """
        # Prüfe auf Duplikate
        existing = await TuneService.get_by_name(db, tune_data.name)
        if existing:
            logger.warning("tune_creation_duplicate", name=tune_data.name)
            raise ValueError(f"Ein Tune mit dem Namen '{tune_data.name}' existiert bereits.")

        tune = Tune(**tune_data.model_dump())
        db.add(tune)

        try:
            await db.commit()
            await db.refresh(tune)
            logger.info("tune_created", tune_id=str(tune.id), name=tune.name)
            return tune
        except IntegrityError as e:
            await db.rollback()
            logger.error("tune_creation_failed", **safe_error_log(e))
            raise ValueError("Fehler beim Erstellen des Tunes. Name möglicherweise bereits vergeben.")

    @staticmethod
    async def update(
        db: AsyncSession,
        tune_id: UUID,
        tune_data: TuneUpdate
    ) -> Optional[Tune]:
        """
        Tune aktualisieren.

        Args:
            db: Async Datenbank-Session
            tune_id: UUID des zu aktualisierenden Tunes
            tune_data: Aktualisierungsdaten

        Returns:
            Aktualisiertes Tune-Objekt oder None wenn nicht gefunden

        Raises:
            ValueError: Wenn Name bereits von anderem Tune verwendet wird
        """
        tune = await TuneService.get_by_id(db, tune_id)
        if not tune:
            return None

        # Prüfe auf Name-Duplikat (falls Name geändert wird)
        update_dict = tune_data.model_dump(exclude_unset=True)
        if "name" in update_dict and update_dict["name"] != tune.name:
            existing = await TuneService.get_by_name(db, update_dict["name"])
            if existing:
                raise ValueError(f"Ein Tune mit dem Namen '{update_dict['name']}' existiert bereits.")

        for field, value in update_dict.items():
            setattr(tune, field, value)

        try:
            await db.commit()
            await db.refresh(tune)
            logger.info("tune_updated", tune_id=str(tune_id), fields=list(update_dict.keys()))
            return tune
        except IntegrityError as e:
            await db.rollback()
            logger.error("tune_update_failed", tune_id=str(tune_id), **safe_error_log(e))
            raise ValueError("Fehler beim Aktualisieren des Tunes.")

    @staticmethod
    async def delete(db: AsyncSession, tune_id: UUID) -> bool:
        """
        Tune löschen.

        System-Tunes können nicht gelöscht werden.

        Args:
            db: Async Datenbank-Session
            tune_id: UUID des zu löschenden Tunes

        Returns:
            True wenn erfolgreich gelöscht

        Raises:
            ValueError: Wenn System-Tune oder Tune nicht gefunden
        """
        tune = await TuneService.get_by_id(db, tune_id)
        if not tune:
            raise ValueError("Tune nicht gefunden.")

        if tune.is_system:
            logger.warning("tune_delete_system_attempt", tune_id=str(tune_id))
            raise ValueError("System-Tunes können nicht gelöscht werden.")

        await db.delete(tune)
        await db.commit()

        logger.info("tune_deleted", tune_id=str(tune_id), name=tune.name)
        return True

    @staticmethod
    async def get_active_count(db: AsyncSession) -> int:
        """Anzahl aktiver Tunes abrufen."""
        from sqlalchemy import func
        query = select(func.count(Tune.id)).where(Tune.is_active == True)
        result = await db.execute(query)
        return result.scalar() or 0

    @staticmethod
    async def get_default_tune(db: AsyncSession) -> Optional[Tune]:
        """
        Standard-Tune für allgemeinen Schriftverkehr abrufen.

        Returns:
            Allgemeiner Schriftverkehr Tune oder erster aktiver Tune
        """
        # Versuche "Allgemeiner Schriftverkehr" zu finden
        tune = await TuneService.get_by_name(db, "Allgemeiner Schriftverkehr")
        if tune and tune.is_active:
            return tune

        # Fallback: Erster aktiver Tune
        query = select(Tune).where(Tune.is_active == True).limit(1)
        result = await db.execute(query)
        return result.scalars().first()

    @staticmethod
    async def get_backend_for_tune(db: AsyncSession, tune_id: UUID) -> Optional[str]:
        """
        Standard-Backend für einen Tune abrufen.

        Args:
            db: Async Datenbank-Session
            tune_id: UUID des Tunes

        Returns:
            Backend-Name oder None für Auto-Auswahl
        """
        tune = await TuneService.get_by_id(db, tune_id)
        if tune:
            return tune.default_backend
        return None


# Singleton-Accessor für Dependency Injection
_tune_service: Optional[TuneService] = None


def get_tune_service() -> TuneService:
    """Get Tune Service instance."""
    global _tune_service
    if _tune_service is None:
        _tune_service = TuneService()
    return _tune_service
