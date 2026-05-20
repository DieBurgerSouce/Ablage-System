# -*- coding: utf-8 -*-
"""
CDC Consumer Base - Abstrakte Basisklasse fuer CDC Event-Consumer.

Jeder Consumer implementiert `process_event()` und definiert,
welche Tabellen er ueberwacht. Die `run()`-Methode steuert die
Batch-Verarbeitung mit automatischem Offset-Tracking.

Beispiel-Implementierung:
    class DATEVSyncConsumer(CDCConsumer):
        consumer_name = "datev_sync"
        watched_tables = ["documents", "invoice_tracking"]

        async def process_event(self, event: ChangeDataCaptureLog) -> bool:
            # DATEV-Synchronisation durchfuehren
            return True
"""

from abc import ABC, abstractmethod
from typing import List

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_cdc import ChangeDataCaptureLog
from app.services.cdc.cdc_service import CDCService
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class CDCConsumer(ABC):
    """
    Basis-Klasse fuer CDC Event-Consumer.

    Unterklassen muessen `consumer_name`, `watched_tables` und
    `process_event()` implementieren.
    """

    consumer_name: str  # Eindeutiger Name (z.B. 'datev_sync')
    watched_tables: List[str]  # Ueberwachte Tabellen

    @abstractmethod
    async def process_event(self, event: ChangeDataCaptureLog) -> bool:
        """
        Verarbeitet ein einzelnes CDC Event.

        Args:
            event: Das zu verarbeitende CDC-Event

        Returns:
            True bei erfolgreicher Verarbeitung, False bei Fehler
        """
        ...

    async def run(
        self,
        session: AsyncSession,
        batch_size: int = 100,
    ) -> int:
        """
        Verarbeitet ausstehende Events in Batches.

        Holt unverarbeitete Events fuer diesen Consumer,
        filtert auf die ueberwachten Tabellen und verarbeitet
        sie einzeln. Erfolgreich verarbeitete Events werden
        als verarbeitet markiert.

        Args:
            session: Async Database Session
            batch_size: Maximale Anzahl Events pro Batch

        Returns:
            Anzahl erfolgreich verarbeiteter Events
        """
        service = CDCService(session)

        # Consumer registrieren (idempotent)
        consumer = await service.register_consumer(self.consumer_name)
        if consumer.status != "active":
            logger.info(
                "cdc_consumer_uebersprungen",
                consumer_name=self.consumer_name,
                status=consumer.status,
            )
            return 0

        # Unverarbeitete Events abrufen
        events = await service.get_unprocessed_events(
            consumer_name=self.consumer_name,
            limit=batch_size,
        )

        if not events:
            return 0

        # Auf ueberwachte Tabellen filtern
        relevant_events = [
            e for e in events
            if e.source_table in self.watched_tables
        ]

        processed_ids: List[object] = []
        error_count = 0

        for event in relevant_events:
            try:
                success = await self.process_event(event)
                if success:
                    processed_ids.append(event.id)
                else:
                    error_count += 1
                    logger.warning(
                        "cdc_event_verarbeitung_fehlgeschlagen",
                        consumer_name=self.consumer_name,
                        event_id=str(event.id),
                        source_table=event.source_table,
                        operation=event.operation,
                    )
            except Exception as e:
                error_count += 1
                logger.error(
                    "cdc_event_verarbeitung_fehler",
                    consumer_name=self.consumer_name,
                    event_id=str(event.id),
                    **safe_error_log(e),
                )

        # Auch nicht-relevante Events (andere Tabellen) als verarbeitet
        # markieren, damit der Offset weiterbewegt wird
        non_relevant_ids = [
            e.id for e in events
            if e.source_table not in self.watched_tables
        ]
        all_processed_ids = processed_ids + non_relevant_ids

        if all_processed_ids:
            await service.mark_processed(
                event_ids=all_processed_ids,
                consumer_name=self.consumer_name,
            )

        processed_count = len(processed_ids)
        logger.info(
            "cdc_batch_verarbeitet",
            consumer_name=self.consumer_name,
            processed=processed_count,
            skipped=len(non_relevant_ids),
            errors=error_count,
            total_events=len(events),
        )

        return processed_count
