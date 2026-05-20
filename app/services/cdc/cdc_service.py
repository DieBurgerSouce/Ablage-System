# -*- coding: utf-8 -*-
"""
CDC Service - Change Data Capture Kernlogik.

Verwaltet CDC-Events und Consumer-Offsets fuer die Echtzeit-
Aenderungserfassung und -verarbeitung.

SECURITY: Keine PII in Logs. Keine sensitiven Daten in Fehlermeldungen.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict

import structlog
from sqlalchemy import select, update, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_cdc import ChangeDataCaptureLog, CDCConsumerOffset
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class CDCService:
    """
    Service fuer Change Data Capture Event-Verwaltung.

    Stellt Methoden bereit fuer:
    - Abrufen unverarbeiteter Events
    - Markieren als verarbeitet
    - Consumer-Verwaltung (Registrierung, Status)
    - Entity-Aenderungshistorie
    - Bereinigung alter Events
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den CDC Service.

        Args:
            db: Async Database Session
        """
        self._db = db

    # -------------------------------------------------------------------------
    # EVENT-VERARBEITUNG
    # -------------------------------------------------------------------------

    async def get_unprocessed_events(
        self,
        consumer_name: str,
        limit: int = 100,
    ) -> List[ChangeDataCaptureLog]:
        """
        Holt unverarbeitete CDC-Events fuer einen Consumer.

        Liest Events ab dem letzten Offset des Consumers,
        gefiltert auf die vom Consumer ueberwachten Tabellen.

        Args:
            consumer_name: Name des Consumers
            limit: Maximale Anzahl Events pro Abruf

        Returns:
            Liste unverarbeiteter CDC-Events, sortiert nach sequence_number
        """
        # Consumer-Offset ermitteln
        consumer = await self.get_consumer_status(consumer_name)
        if not consumer:
            logger.warning(
                "cdc_consumer_nicht_registriert",
                consumer_name=consumer_name,
            )
            return []

        if consumer.status != "active":
            logger.info(
                "cdc_consumer_nicht_aktiv",
                consumer_name=consumer_name,
                status=consumer.status,
            )
            return []

        last_seq = consumer.last_sequence_number or 0

        stmt = (
            select(ChangeDataCaptureLog)
            .where(
                and_(
                    ChangeDataCaptureLog.sequence_number > last_seq,
                    ChangeDataCaptureLog.processed == False,  # noqa: E712
                )
            )
            .order_by(ChangeDataCaptureLog.sequence_number.asc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        events = list(result.scalars().all())

        logger.info(
            "cdc_events_abgerufen",
            consumer_name=consumer_name,
            event_count=len(events),
            from_sequence=last_seq,
        )

        return events

    async def mark_processed(
        self,
        event_ids: List[uuid.UUID],
        consumer_name: str,
    ) -> int:
        """
        Markiert CDC-Events als verarbeitet und aktualisiert den Consumer-Offset.

        Args:
            event_ids: Liste der Event-IDs zum Markieren
            consumer_name: Name des Consumers

        Returns:
            Anzahl der markierten Events
        """
        if not event_ids:
            return 0

        now = datetime.now(timezone.utc)

        # Events als verarbeitet markieren
        stmt = (
            update(ChangeDataCaptureLog)
            .where(ChangeDataCaptureLog.id.in_(event_ids))
            .values(
                processed=True,
                processed_at=now,
                consumer_id=consumer_name,
            )
        )
        result = await self._db.execute(stmt)
        marked_count = result.rowcount

        # Hoechste Sequenznummer der markierten Events ermitteln
        max_seq_stmt = (
            select(func.max(ChangeDataCaptureLog.sequence_number))
            .where(ChangeDataCaptureLog.id.in_(event_ids))
        )
        max_seq_result = await self._db.execute(max_seq_stmt)
        max_sequence = max_seq_result.scalar()

        # Consumer-Offset aktualisieren
        if max_sequence is not None:
            await self._db.execute(
                update(CDCConsumerOffset)
                .where(CDCConsumerOffset.consumer_name == consumer_name)
                .values(
                    last_sequence_number=max_sequence,
                    last_processed_at=now,
                    updated_at=now,
                )
            )

        await self._db.flush()

        logger.info(
            "cdc_events_verarbeitet",
            consumer_name=consumer_name,
            marked_count=marked_count,
            max_sequence=max_sequence,
        )

        return marked_count

    # -------------------------------------------------------------------------
    # CONSUMER-VERWALTUNG
    # -------------------------------------------------------------------------

    async def get_consumer_status(
        self,
        consumer_name: str,
    ) -> Optional[CDCConsumerOffset]:
        """
        Holt den aktuellen Status eines CDC-Consumers.

        Args:
            consumer_name: Name des Consumers

        Returns:
            Consumer-Offset oder None falls nicht registriert
        """
        stmt = select(CDCConsumerOffset).where(
            CDCConsumerOffset.consumer_name == consumer_name
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_consumers(self) -> List[CDCConsumerOffset]:
        """
        Holt alle registrierten CDC-Consumer.

        Returns:
            Liste aller Consumer-Offsets
        """
        stmt = (
            select(CDCConsumerOffset)
            .order_by(CDCConsumerOffset.consumer_name.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def register_consumer(
        self,
        consumer_name: str,
        config: Optional[Dict[str, str]] = None,
    ) -> CDCConsumerOffset:
        """
        Registriert einen neuen CDC-Consumer oder gibt existierenden zurueck.

        Args:
            consumer_name: Eindeutiger Name des Consumers
            config: Optionale Consumer-Konfiguration

        Returns:
            Der Consumer-Offset (neu oder bestehend)
        """
        # Pruefen ob schon vorhanden
        existing = await self.get_consumer_status(consumer_name)
        if existing:
            logger.info(
                "cdc_consumer_existiert_bereits",
                consumer_name=consumer_name,
            )
            return existing

        consumer = CDCConsumerOffset(
            id=uuid.uuid4(),
            consumer_name=consumer_name,
            last_sequence_number=0,
            status="active",
            config=config or {},
        )

        self._db.add(consumer)
        await self._db.flush()

        logger.info(
            "cdc_consumer_registriert",
            consumer_name=consumer_name,
        )

        return consumer

    async def pause_consumer(self, consumer_name: str) -> bool:
        """
        Pausiert einen CDC-Consumer.

        Args:
            consumer_name: Name des Consumers

        Returns:
            True bei Erfolg, False falls Consumer nicht gefunden
        """
        result = await self._db.execute(
            update(CDCConsumerOffset)
            .where(CDCConsumerOffset.consumer_name == consumer_name)
            .values(
                status="paused",
                updated_at=datetime.now(timezone.utc),
            )
        )

        if result.rowcount == 0:
            return False

        await self._db.flush()
        logger.info("cdc_consumer_pausiert", consumer_name=consumer_name)
        return True

    async def resume_consumer(self, consumer_name: str) -> bool:
        """
        Setzt einen pausierten CDC-Consumer fort.

        Args:
            consumer_name: Name des Consumers

        Returns:
            True bei Erfolg, False falls Consumer nicht gefunden
        """
        result = await self._db.execute(
            update(CDCConsumerOffset)
            .where(CDCConsumerOffset.consumer_name == consumer_name)
            .values(
                status="active",
                error_message=None,
                updated_at=datetime.now(timezone.utc),
            )
        )

        if result.rowcount == 0:
            return False

        await self._db.flush()
        logger.info("cdc_consumer_fortgesetzt", consumer_name=consumer_name)
        return True

    # -------------------------------------------------------------------------
    # ENTITY-HISTORIE
    # -------------------------------------------------------------------------

    async def get_changes_for_entity(
        self,
        source_table: str,
        source_id: uuid.UUID,
        limit: int = 50,
    ) -> List[ChangeDataCaptureLog]:
        """
        Holt die Aenderungshistorie fuer eine bestimmte Entity.

        Args:
            source_table: Name der Quell-Tabelle
            source_id: ID des Datensatzes
            limit: Maximale Anzahl Events

        Returns:
            Liste der CDC-Events, neueste zuerst
        """
        stmt = (
            select(ChangeDataCaptureLog)
            .where(
                and_(
                    ChangeDataCaptureLog.source_table == source_table,
                    ChangeDataCaptureLog.source_id == source_id,
                )
            )
            .order_by(ChangeDataCaptureLog.sequence_number.desc())
            .limit(limit)
        )

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # BEREINIGUNG
    # -------------------------------------------------------------------------

    async def cleanup_old_events(self, days: int = 90) -> int:
        """
        Loescht verarbeitete CDC-Events, die aelter als N Tage sind.

        Args:
            days: Mindestalter in Tagen (Standard: 90)

        Returns:
            Anzahl geloeschter Events
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            delete(ChangeDataCaptureLog)
            .where(
                and_(
                    ChangeDataCaptureLog.processed == True,  # noqa: E712
                    ChangeDataCaptureLog.created_at < cutoff,
                )
            )
        )

        result = await self._db.execute(stmt)
        deleted_count = result.rowcount

        await self._db.flush()

        logger.info(
            "cdc_bereinigung_abgeschlossen",
            deleted_count=deleted_count,
            cutoff_days=days,
        )

        return deleted_count

    # -------------------------------------------------------------------------
    # STATISTIKEN
    # -------------------------------------------------------------------------

    async def get_event_count(
        self,
        source_table: Optional[str] = None,
        processed: Optional[bool] = None,
    ) -> int:
        """
        Zaehlt CDC-Events mit optionalen Filtern.

        Args:
            source_table: Optional - nur Events fuer diese Tabelle
            processed: Optional - nur verarbeitete/unverarbeitete Events

        Returns:
            Anzahl der Events
        """
        stmt = select(func.count(ChangeDataCaptureLog.id))

        if source_table is not None:
            stmt = stmt.where(
                ChangeDataCaptureLog.source_table == source_table
            )

        if processed is not None:
            stmt = stmt.where(
                ChangeDataCaptureLog.processed == processed
            )

        result = await self._db.execute(stmt)
        return result.scalar() or 0
