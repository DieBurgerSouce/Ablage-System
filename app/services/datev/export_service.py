# -*- coding: utf-8 -*-
"""
DATEV Export Service.

Hauptservice fuer den DATEV Buchungsstapel-Export.
Orchestriert Mapping, Validierung und CSV-Generierung.
"""

import atexit
import asyncio
import hashlib
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from functools import partial
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# =============================================================================
# KONSTANTEN (vermeidet Magic Numbers)
# =============================================================================

MAX_WARNINGS_PER_EXPORT = 50
"""Maximale Anzahl an Warnungen die pro Export gespeichert werden."""

MAX_DOCUMENTS_PER_QUERY = 1000
"""Sicherheitslimit fuer Dokumente pro Query."""

THREADPOOL_MAX_WORKERS = 4
"""Maximale Anzahl an Worker-Threads fuer paralleles Mapping."""

ASYNC_THRESHOLD_DOCUMENTS = 20
"""Ab dieser Anzahl wird async mit ThreadPool verarbeitet."""

CHUNK_SIZE_DOCUMENTS = 50
"""Chunk-Groesse fuer ThreadPool-Verarbeitung (Memory Leak Prevention)."""

from app.api.schemas.datev import (
    DATEVExportPreview,
    DATEVExportResponse,
    DATEVExportStatus,
    DATEVExportType,
    Kontenrahmen,
)
from app.api.schemas.extracted_data import ExtractedInvoiceData, InvoiceDirection
from app.db import models

from .buchungsstapel_writer import BuchungsstapelWriter
from .kontenrahmen import SKR03, SKR04, BaseKontenrahmen
from .mapping.invoice_mapper import DATEVBuchung, DATEVInvoiceMapper
from .metrics import get_datev_metrics_service

logger = structlog.get_logger(__name__)


class DATEVExportService:
    """
    DATEV Buchungsstapel Export Service.

    Verwendung:
        service = DATEVExportService()

        # Export mit Standardkonfiguration
        csv_bytes, export = await service.export_buchungsstapel(
            db=session,
            user_id=user_uuid,
            document_ids=[uuid1, uuid2]
        )

        # Vorschau ohne Export
        preview = await service.preview_export(
            db=session,
            document_ids=[uuid1, uuid2]
        )
    """

    # Thread-Pool fuer CPU-intensive Operationen (Mapping, CSV-Generierung)
    _executor: Optional[ThreadPoolExecutor] = None
    _executor_lock: threading.Lock = threading.Lock()

    # MEDIUM-13 FIX: Kontenrahmen-Registry als Klassen-Konstante
    # Da SKR03/SKR04 stateless sind, kann eine einzige Instanz
    # sicher von allen Threads geteilt werden. Dict-Reads sind atomar.
    _KONTENRAHMEN_REGISTRY: Dict[str, BaseKontenrahmen] = {
        "SKR03": SKR03(),
        "SKR04": SKR04(),
    }

    def __init__(self) -> None:
        self.writer = BuchungsstapelWriter()
        self.mapper = DATEVInvoiceMapper()

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        """
        Lazy-initialisiert ThreadPoolExecutor (Thread-Safe Singleton).

        Verwendet Double-Checked Locking Pattern fuer Performance
        bei gleichzeitiger Thread-Safety.
        """
        if cls._executor is None:
            with cls._executor_lock:
                # Double-check nach Lock-Acquisition
                if cls._executor is None:
                    cls._executor = ThreadPoolExecutor(
                        max_workers=THREADPOOL_MAX_WORKERS,
                        thread_name_prefix="datev_"
                    )
        return cls._executor

    @classmethod
    def shutdown_executor(cls) -> None:
        """
        Beendet den ThreadPoolExecutor ordnungsgemaess.

        Wird automatisch via atexit aufgerufen beim Prozess-Ende.
        Kann auch manuell fuer Tests aufgerufen werden.
        """
        with cls._executor_lock:
            if cls._executor is not None:
                cls._executor.shutdown(wait=True)
                cls._executor = None
                logger.info("datev_executor_shutdown")

    async def export_buchungsstapel(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        document_ids: Optional[List[uuid.UUID]] = None,
        period_from: Optional[date] = None,
        period_to: Optional[date] = None,
        config_id: Optional[uuid.UUID] = None,
        include_already_exported: bool = False,
    ) -> Tuple[bytes, models.DATEVExport]:
        """
        Exportiert Buchungsstapel als DATEV-CSV.

        Args:
            db: Async-Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Spezifische Dokument-IDs (optional)
            period_from: Zeitraum-Start (optional)
            period_to: Zeitraum-Ende (optional)
            config_id: Konfiguration (sonst Standard)
            include_already_exported: Bereits exportierte einschliessen

        Returns:
            Tuple aus CSV-Bytes (CP1252) und Export-Record

        Raises:
            ValueError: Bei fehlender Konfiguration oder Daten
        """
        import time
        start_time = time.perf_counter()
        metrics = get_datev_metrics_service()
        export_date = datetime.now()

        # Konfiguration laden
        config = await self._get_config(db, config_id, user_id)
        if not config:
            raise ValueError("Keine DATEV-Konfiguration gefunden. Bitte zuerst konfigurieren.")

        # Kontenrahmen bestimmen
        kontenrahmen = self._get_kontenrahmen(config.kontenrahmen)

        # Vendor-Mappings laden
        vendor_mappings = await self._get_vendor_mappings(db, config.id)

        # Exportierbare Dokumente laden
        documents = await self._get_exportable_documents(
            db=db,
            user_id=user_id,
            document_ids=document_ids,
            period_from=period_from,
            period_to=period_to,
            include_already_exported=include_already_exported,
        )

        if not documents:
            raise ValueError("Keine exportierbaren Dokumente gefunden.")

        # Buchungen mappen (async um Event Loop nicht zu blockieren)
        buchungen, included_docs, skipped_docs, all_warnings = await self._map_documents_async(
            documents=documents,
            kontenrahmen=kontenrahmen,
            config=config,
            vendor_mappings=vendor_mappings,
        )

        if not buchungen:
            raise ValueError("Keine Buchungen konnten erstellt werden.")

        # CSV generieren
        csv_bytes = self.writer.write(
            buchungen=buchungen,
            config=config,
            export_date=export_date,
        )

        # Hash berechnen
        content_hash = hashlib.sha256(csv_bytes).hexdigest()

        # Dateiname generieren
        timestamp = export_date.strftime("%Y%m%d_%H%M%S")
        filename = f"EXTF_Buchungsstapel_{timestamp}.csv"

        # Zeitraum aus Buchungen ermitteln
        actual_period_from = min(b.belegdatum for b in buchungen)
        actual_period_to = max(b.belegdatum for b in buchungen)

        # MEDIUM-9 FIX: Document Existence Check vor Export-Record Erstellung
        # Zwischen Document-Read und Export-Write koennen Dokumente geloescht werden
        if included_docs:
            existing_check = await db.execute(
                select(models.Document.id).where(
                    models.Document.id.in_(included_docs),
                    models.Document.deleted_at.is_(None),
                )
            )
            still_existing = set(existing_check.scalars().all())
            deleted_during_export = [doc_id for doc_id in included_docs if doc_id not in still_existing]

            if deleted_during_export:
                # Dokumente wurden waehrend des Exports geloescht
                logger.warning(
                    "datev_documents_deleted_during_export",
                    deleted_count=len(deleted_during_export),
                    deleted_ids=[str(d) for d in deleted_during_export],
                )
                # Aus included entfernen, zu skipped hinzufuegen
                included_docs = [d for d in included_docs if d in still_existing]
                skipped_docs.extend(deleted_during_export)
                all_warnings.extend([
                    f"Dokument {d}: Waehrend Export geloescht"
                    for d in deleted_during_export
                ])

                # Wenn keine Dokumente mehr uebrig, Fehler
                if not included_docs:
                    raise ValueError(
                        "Alle Dokumente wurden waehrend des Exports geloescht. "
                        "Bitte Export erneut starten."
                    )

        # Export-Status bestimmen
        if skipped_docs and included_docs:
            status = DATEVExportStatus.PARTIAL
        elif not included_docs:
            status = DATEVExportStatus.FAILED
        else:
            status = DATEVExportStatus.COMPLETED

        # Export-Record erstellen
        export_record = models.DATEVExport(
            id=uuid.uuid4(),
            config_id=config.id,
            exported_by_id=user_id,
            export_type="buchungsstapel",
            filename=filename,
            document_count=len(included_docs),
            period_from=actual_period_from,
            period_to=actual_period_to,
            content_hash=content_hash,
            file_size_bytes=len(csv_bytes),
            status=status.value,
            included_documents=[str(d) for d in included_docs],
            skipped_documents=[str(d) for d in skipped_docs],
            warnings=all_warnings[:MAX_WARNINGS_PER_EXPORT],
        )

        db.add(export_record)

        # Metriken aufzeichnen
        duration = time.perf_counter() - start_time
        metrics.record_export(
            status=status.value,
            kontenrahmen=config.kontenrahmen,
            document_count=len(included_docs),
            duration_seconds=duration,
        )

        logger.info(
            "datev_export_completed",
            export_id=str(export_record.id),
            document_count=len(included_docs),
            skipped_count=len(skipped_docs),
            file_size=len(csv_bytes),
            duration_seconds=round(duration, 3),
        )

        return csv_bytes, export_record

    async def preview_export(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        document_ids: Optional[List[uuid.UUID]] = None,
        period_from: Optional[date] = None,
        period_to: Optional[date] = None,
        config_id: Optional[uuid.UUID] = None,
    ) -> DATEVExportPreview:
        """
        Erstellt Vorschau des Exports ohne tatsaechlichen Download.

        Returns:
            DATEVExportPreview mit Statistiken und Beispiel-Buchungen
        """
        # Konfiguration laden
        config = await self._get_config(db, config_id, user_id)
        if not config:
            return DATEVExportPreview(
                document_count=0,
                total_amount=Decimal("0"),
                warnings=["Keine DATEV-Konfiguration gefunden"],
            )

        kontenrahmen = self._get_kontenrahmen(config.kontenrahmen)
        vendor_mappings = await self._get_vendor_mappings(db, config.id)

        # Dokumente laden
        documents = await self._get_exportable_documents(
            db=db,
            user_id=user_id,
            document_ids=document_ids,
            period_from=period_from,
            period_to=period_to,
            include_already_exported=True,
        )

        if not documents:
            return DATEVExportPreview(
                document_count=0,
                total_amount=Decimal("0"),
                warnings=["Keine exportierbaren Dokumente gefunden"],
            )

        # Buchungen mappen (async um Event Loop nicht zu blockieren)
        buchungen, _, _, warnings = await self._map_documents_async(
            documents=documents,
            kontenrahmen=kontenrahmen,
            config=config,
            vendor_mappings=vendor_mappings,
        )

        # Gesamtbetrag und Skip-Gruende berechnen
        total_amount = sum((b.umsatz for b in buchungen), Decimal("0"))
        skipped_reasons: Dict[str, int] = {}

        # Skip-Gruende aus Warnungen extrahieren
        for warning in warnings:
            if "Keine Rechnungsdaten" in warning:
                reason = "Keine Rechnungsdaten"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            elif ": " in warning:
                reason = warning.split(": ", 1)[1] if ": " in warning else "Unbekannter Fehler"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

        # Zeitraum ermitteln
        if buchungen:
            actual_from = min(b.belegdatum for b in buchungen)
            actual_to = max(b.belegdatum for b in buchungen)
        else:
            actual_from = period_from
            actual_to = period_to

        # Beispiel-Buchungen (max 10)
        sample_entries = []
        for buchung in buchungen[:10]:
            sample_entries.append({
                "belegdatum": buchung.belegdatum.isoformat(),
                "belegfeld_1": buchung.belegfeld_1,
                "umsatz": str(buchung.umsatz),
                "soll_haben": buchung.soll_haben,
                "konto": buchung.konto,
                "gegenkonto": buchung.gegenkonto,
                "bu_schluessel": buchung.bu_schluessel,
                "buchungstext": buchung.buchungstext,
            })

        return DATEVExportPreview(
            document_count=len(buchungen),
            period_from=actual_from,
            period_to=actual_to,
            total_amount=total_amount,
            sample_entries=sample_entries,
            warnings=warnings,
            skipped_count=sum(skipped_reasons.values()),
            skipped_reasons=skipped_reasons,
        )

    async def _get_config(
        self,
        db: AsyncSession,
        config_id: Optional[uuid.UUID],
        user_id: uuid.UUID
    ) -> Optional[models.DATEVConfiguration]:
        """Laedt Konfiguration (spezifisch oder Standard)."""
        if config_id:
            # SECURITY FIX: user_id MUSS geprueft werden (OWASP A07:2021)
            result = await db.execute(
                select(models.DATEVConfiguration).where(
                    models.DATEVConfiguration.id == config_id,
                    models.DATEVConfiguration.user_id == user_id,  # Authorization Check
                    models.DATEVConfiguration.is_active == True,
                )
            )
            return result.scalar_one_or_none()

        # Standard-Konfiguration suchen
        result = await db.execute(
            select(models.DATEVConfiguration).where(
                models.DATEVConfiguration.user_id == user_id,
                models.DATEVConfiguration.is_default == True,
                models.DATEVConfiguration.is_active == True,
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            # Erste aktive Konfiguration
            result = await db.execute(
                select(models.DATEVConfiguration).where(
                    models.DATEVConfiguration.user_id == user_id,
                    models.DATEVConfiguration.is_active == True,
                ).limit(1)
            )
            config = result.scalar_one_or_none()

        return config

    async def _get_vendor_mappings(
        self,
        db: AsyncSession,
        config_id: uuid.UUID
    ) -> Dict[str, models.DATEVVendorMapping]:
        """Laedt Vendor-Mappings als Dict (nach USt-IdNr, IBAN, Name)."""
        result = await db.execute(
            select(models.DATEVVendorMapping).where(
                models.DATEVVendorMapping.config_id == config_id
            )
        )
        mappings = result.scalars().all()

        # Index nach verschiedenen Kriterien
        # MEDIUM-14 DOC: Matching-Verhalten:
        # - USt-IdNr und IBAN: Exakter Match (case-preserved, bereits normalisiert durch Validator)
        # - Firmenname: Case-Insensitiver Match (beide Seiten werden zu lowercase)
        mapping_dict: Dict[str, models.DATEVVendorMapping] = {}
        for m in mappings:
            if m.vendor_vat_id:
                mapping_dict[f"vat:{m.vendor_vat_id}"] = m
            if m.vendor_iban:
                mapping_dict[f"iban:{m.vendor_iban}"] = m
            if m.vendor_name:
                # Case-Insensitiver Match: vendor_name wird zu lowercase konvertiert
                mapping_dict[f"name:{m.vendor_name.lower()}"] = m

        return mapping_dict

    async def _get_exportable_documents(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        document_ids: Optional[List[uuid.UUID]],
        period_from: Optional[date],
        period_to: Optional[date],
        include_already_exported: bool,
    ) -> List[models.Document]:
        """Laedt exportierbare Dokumente."""
        query = select(models.Document).where(
            models.Document.user_id == user_id,
            models.Document.deleted_at.is_(None),
        )

        if document_ids:
            query = query.where(models.Document.id.in_(document_ids))

        # Nur Dokumente mit extracted_data.invoice
        # (Filterung erfolgt spaeter beim Mappen)

        result = await db.execute(query.limit(MAX_DOCUMENTS_PER_QUERY))
        documents = list(result.scalars().all())

        # Filtern nach Zeitraum (aus extracted_data)
        if period_from or period_to:
            filtered = []
            for doc in documents:
                invoice_date = self._get_invoice_date(doc)
                if invoice_date:
                    if period_from and invoice_date < period_from:
                        continue
                    if period_to and invoice_date > period_to:
                        continue
                filtered.append(doc)
            documents = filtered

        return documents

    def _get_invoice_date(self, doc: models.Document) -> Optional[date]:
        """Extrahiert Rechnungsdatum aus extracted_data."""
        if not doc.extracted_data:
            return None
        invoice = doc.extracted_data.get("invoice", {})
        date_str = invoice.get("invoice_date")
        if date_str:
            try:
                return date.fromisoformat(date_str)
            except (ValueError, TypeError):
                pass
        return None

    def _get_kontenrahmen(self, kontenrahmen_name: str) -> BaseKontenrahmen:
        """
        Liefert Kontenrahmen-Instanz.

        Thread-Safe: Verwendet Klassen-Konstante statt Instanz-Variable.
        """
        return self._KONTENRAHMEN_REGISTRY.get(
            kontenrahmen_name,
            self._KONTENRAHMEN_REGISTRY["SKR03"]
        )

    async def _map_documents_async(
        self,
        documents: List[models.Document],
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
        vendor_mappings: Dict[str, models.DATEVVendorMapping],
    ) -> Tuple[List[DATEVBuchung], List[uuid.UUID], List[uuid.UUID], List[str]]:
        """
        Mappt Dokumente async zu DATEV-Buchungen.

        Verwendet ThreadPoolExecutor um den Event Loop nicht zu blockieren.
        Bei grossen Dokumentmengen werden Batches in Chunks verarbeitet.

        WICHTIG (Thread-Safety):
        - ORM-Objekte werden NICHT direkt an Worker-Threads uebergeben
        - Stattdessen werden serialisierte Daten-Dicts verwendet
        - Dies verhindert DetachedInstanceError bei Lazy-Loading

        WICHTIG (Memory Management):
        - Dokumente werden in Chunks verarbeitet (CHUNK_SIZE_DOCUMENTS)
        - Verhindert unbegrenztes Memory-Wachstum bei >500 Dokumenten

        Returns:
            Tuple aus (Buchungen, included_docs, skipped_docs, Warnungen)
        """
        buchungen: List[DATEVBuchung] = []
        included_docs: List[uuid.UUID] = []
        skipped_docs: List[uuid.UUID] = []
        all_warnings: List[str] = []

        # MEDIUM-6 FIX: ORM-Objekte zu Thread-Safe Dicts konvertieren
        # Verhindert DetachedInstanceError bei Lazy-Loading im Worker-Thread
        doc_data_list = [
            {
                "id": doc.id,
                "extracted_data": doc.extracted_data,  # Dict, nicht ORM
            }
            for doc in documents
        ]

        # Fuer kleine Mengen (<20) synchron mappen (Overhead vermeiden)
        if len(doc_data_list) < ASYNC_THRESHOLD_DOCUMENTS:
            for doc_data in doc_data_list:
                result = self._map_document_from_dict(
                    doc_data, kontenrahmen, config, vendor_mappings
                )
                self._process_mapping_result(
                    result, doc_data["id"], buchungen, included_docs, skipped_docs, all_warnings
                )
            return buchungen, included_docs, skipped_docs, all_warnings

        # Fuer groessere Mengen: async mit ThreadPoolExecutor in Chunks
        loop = asyncio.get_event_loop()
        executor = self._get_executor()

        # Mapping-Funktion fuer ThreadPool vorbereiten
        # MEDIUM-6 FIX: Arbeitet mit Dict statt ORM-Objekt
        def map_single_doc_from_dict(doc_data: Dict) -> Tuple[
            uuid.UUID,
            Optional[Tuple[Optional[DATEVBuchung], Optional[str], List[str]]]
        ]:
            result = self._map_document_from_dict(
                doc_data, kontenrahmen, config, vendor_mappings
            )
            return (doc_data["id"], result)

        # HIGH-5 FIX: Chunked Execution (Memory Leak Prevention)
        # Verhindert OOM bei 1000+ Dokumenten durch Verarbeitung in Chunks
        for chunk_start in range(0, len(doc_data_list), CHUNK_SIZE_DOCUMENTS):
            chunk_end = min(chunk_start + CHUNK_SIZE_DOCUMENTS, len(doc_data_list))
            chunk = doc_data_list[chunk_start:chunk_end]

            # Futures nur fuer aktuellen Chunk erstellen
            futures = [
                loop.run_in_executor(executor, map_single_doc_from_dict, doc_data)
                for doc_data in chunk
            ]

            # HIGH-6 FIX: return_exceptions=True verhindert Abbruch bei einzelnem Fehler
            chunk_results = await asyncio.gather(*futures, return_exceptions=True)

            # Ergebnisse verarbeiten (mit Exception-Handling)
            for i, result in enumerate(chunk_results):
                doc_id = chunk[i]["id"]

                # Exception-Handling fuer fehlgeschlagene Mappings
                if isinstance(result, Exception):
                    logger.error(
                        "datev_mapping_exception",
                        document_id=str(doc_id),
                        error_type=type(result).__name__,
                        error=str(result),
                    )
                    skipped_docs.append(doc_id)
                    all_warnings.append(f"Dokument {doc_id}: Mapping-Fehler ({type(result).__name__})")
                else:
                    # Normales Ergebnis: Tuple aus (doc_id, result)
                    _, mapping_result = result
                    self._process_mapping_result(
                        mapping_result, doc_id, buchungen, included_docs, skipped_docs, all_warnings
                    )

        return buchungen, included_docs, skipped_docs, all_warnings

    def _map_document_from_dict(
        self,
        doc_data: Dict,
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
        vendor_mappings: Dict[str, models.DATEVVendorMapping],
    ) -> Optional[Tuple[Optional[DATEVBuchung], Optional[str], List[str]]]:
        """
        Mappt ein Dokument aus Dict-Daten zu einer DATEV-Buchung.

        Thread-Safe Version die mit serialisierten Daten arbeitet
        statt mit ORM-Objekten.

        Args:
            doc_data: Dict mit 'id' und 'extracted_data'

        Returns:
            Tuple aus (Buchung, Fehler, Warnungen) oder None wenn keine Rechnungsdaten
        """
        extracted_data = doc_data.get("extracted_data")
        if not extracted_data:
            return None

        invoice_data = extracted_data.get("invoice")
        if not invoice_data:
            return None

        # ExtractedInvoiceData konstruieren
        try:
            invoice = ExtractedInvoiceData(**invoice_data)
        except Exception as e:
            logger.warning(
                "datev_invoice_parse_error",
                document_id=str(doc_data["id"]),
                error=str(e)
            )
            return (None, f"Fehler beim Parsen: {str(e)}", [])

        # Vendor-Mapping suchen
        vendor_mapping = self._find_vendor_mapping(invoice, vendor_mappings)

        # Mappen
        result = self.mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=kontenrahmen,
            config=config,
            vendor_mapping=vendor_mapping,
        )

        if result.success:
            return (result.buchung, None, result.warnings)
        else:
            return (None, result.error, result.warnings)

    def _process_mapping_result(
        self,
        result: Optional[Tuple[Optional[DATEVBuchung], Optional[str], List[str]]],
        doc_id: uuid.UUID,
        buchungen: List[DATEVBuchung],
        included_docs: List[uuid.UUID],
        skipped_docs: List[uuid.UUID],
        all_warnings: List[str],
    ) -> None:
        """Verarbeitet ein einzelnes Mapping-Ergebnis."""
        if result is None:
            skipped_docs.append(doc_id)
            all_warnings.append(f"Dokument {doc_id}: Keine Rechnungsdaten")
        elif result[0] is None:
            skipped_docs.append(doc_id)
            all_warnings.append(f"Dokument {doc_id}: {result[1]}")
        else:
            buchungen.append(result[0])
            included_docs.append(doc_id)
            if result[2]:
                all_warnings.extend([f"Dokument {doc_id}: {w}" for w in result[2]])

    def _map_document(
        self,
        doc: models.Document,
        kontenrahmen: BaseKontenrahmen,
        config: models.DATEVConfiguration,
        vendor_mappings: Dict[str, models.DATEVVendorMapping],
    ) -> Optional[Tuple[Optional[DATEVBuchung], Optional[str], List[str]]]:
        """
        Mappt ein Dokument zu einer DATEV-Buchung.

        Returns:
            Tuple aus (Buchung, Fehler, Warnungen) oder None wenn keine Rechnungsdaten
        """
        if not doc.extracted_data:
            return None

        invoice_data = doc.extracted_data.get("invoice")
        if not invoice_data:
            return None

        # ExtractedInvoiceData konstruieren
        try:
            invoice = ExtractedInvoiceData(**invoice_data)
        except Exception as e:
            logger.warning(
                "datev_invoice_parse_error",
                document_id=str(doc.id),
                error=str(e)
            )
            return (None, f"Fehler beim Parsen: {str(e)}", [])

        # Vendor-Mapping suchen
        vendor_mapping = self._find_vendor_mapping(invoice, vendor_mappings)

        # Mappen
        result = self.mapper.map_invoice(
            invoice=invoice,
            kontenrahmen=kontenrahmen,
            config=config,
            vendor_mapping=vendor_mapping,
        )

        if result.success:
            return (result.buchung, None, result.warnings)
        else:
            return (None, result.error, result.warnings)

    def _find_vendor_mapping(
        self,
        invoice: ExtractedInvoiceData,
        vendor_mappings: Dict[str, models.DATEVVendorMapping],
    ) -> Optional[models.DATEVVendorMapping]:
        """
        Sucht passendes Vendor-Mapping fuer eine Eingangsrechnung.

        Match-Prioritaet (erste Uebereinstimmung gewinnt):
        1. USt-IdNr (exakt, case-sensitive)
        2. IBAN (exakt, case-sensitive)
        3. Firmenname (case-insensitiv, exakter String-Vergleich nach lowercase)

        MEDIUM-14 DOC: Der Firmenname-Match ist CASE-INSENSITIV.
        "ACME GmbH", "acme gmbh" und "Acme GmbH" werden alle gematcht.
        Es findet jedoch KEIN Fuzzy-Matching statt (z.B. Tippfehler).
        """
        # Nur bei Eingangsrechnungen
        if invoice.invoice_direction != InvoiceDirection.INCOMING:
            return None

        if not invoice.sender:
            return None

        # 1. Exakter Match: USt-IdNr (case-sensitive, bereits normalisiert)
        if invoice.sender_vat_id:
            key = f"vat:{invoice.sender_vat_id}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        # 2. Exakter Match: IBAN (case-sensitive, bereits normalisiert)
        if invoice.sender_bank and invoice.sender_bank.iban:
            key = f"iban:{invoice.sender_bank.iban}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        # 3. Case-Insensitiver Match: Firmenname
        if invoice.sender.company:
            name_lower = invoice.sender.company.lower()
            key = f"name:{name_lower}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        return None


# =============================================================================
# SINGLETON-PATTERN (Thread-Safe)
# =============================================================================

_datev_export_service: Optional[DATEVExportService] = None
_service_lock: threading.Lock = threading.Lock()


def get_datev_export_service() -> DATEVExportService:
    """
    Factory-Funktion fuer DATEVExportService (Thread-Safe).

    Verwendet Double-Checked Locking Pattern fuer Performance
    bei gleichzeitiger Thread-Safety.
    """
    global _datev_export_service
    if _datev_export_service is None:
        with _service_lock:
            # Double-check nach Lock-Acquisition
            if _datev_export_service is None:
                _datev_export_service = DATEVExportService()
    return _datev_export_service


def _shutdown_datev_service() -> None:
    """
    Shutdown-Handler fuer sauberes Beenden.

    Wird automatisch beim Prozess-Ende via atexit aufgerufen.
    Stellt sicher dass ThreadPoolExecutor ordnungsgemaess beendet wird.
    """
    DATEVExportService.shutdown_executor()


# Registriere Shutdown-Handler
atexit.register(_shutdown_datev_service)
