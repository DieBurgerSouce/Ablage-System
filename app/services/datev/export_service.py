# -*- coding: utf-8 -*-
"""
DATEV Export Service.

Hauptservice fuer den DATEV Buchungsstapel-Export.
Orchestriert Mapping, Validierung und CSV-Generierung.
"""

import hashlib
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    def __init__(self) -> None:
        self.writer = BuchungsstapelWriter()
        self.mapper = DATEVInvoiceMapper()
        self._kontenrahmen_registry: Dict[str, BaseKontenrahmen] = {
            "SKR03": SKR03(),
            "SKR04": SKR04(),
        }

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

        # Buchungen mappen
        buchungen: List[DATEVBuchung] = []
        included_docs: List[uuid.UUID] = []
        skipped_docs: List[uuid.UUID] = []
        all_warnings: List[str] = []

        for doc in documents:
            result = self._map_document(doc, kontenrahmen, config, vendor_mappings)

            if result is None:
                skipped_docs.append(doc.id)
                all_warnings.append(f"Dokument {doc.id}: Keine Rechnungsdaten")
            elif result[0] is None:
                skipped_docs.append(doc.id)
                all_warnings.append(f"Dokument {doc.id}: {result[1]}")
            else:
                buchungen.append(result[0])
                included_docs.append(doc.id)
                if result[2]:
                    all_warnings.extend([f"Dokument {doc.id}: {w}" for w in result[2]])

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
            warnings=all_warnings[:50],  # Max 50 Warnungen speichern
        )

        db.add(export_record)

        logger.info(
            "datev_export_completed",
            export_id=str(export_record.id),
            document_count=len(included_docs),
            skipped_count=len(skipped_docs),
            file_size=len(csv_bytes),
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

        # Buchungen mappen (Vorschau)
        buchungen: List[DATEVBuchung] = []
        warnings: List[str] = []
        skipped_reasons: Dict[str, int] = {}
        total_amount = Decimal("0")

        for doc in documents:
            result = self._map_document(doc, kontenrahmen, config, vendor_mappings)

            if result is None:
                reason = "Keine Rechnungsdaten"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            elif result[0] is None:
                reason = result[1] or "Unbekannter Fehler"
                skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1
            else:
                buchungen.append(result[0])
                total_amount += result[0].umsatz

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
            result = await db.execute(
                select(models.DATEVConfiguration).where(
                    models.DATEVConfiguration.id == config_id,
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
        mapping_dict: Dict[str, models.DATEVVendorMapping] = {}
        for m in mappings:
            if m.vendor_vat_id:
                mapping_dict[f"vat:{m.vendor_vat_id}"] = m
            if m.vendor_iban:
                mapping_dict[f"iban:{m.vendor_iban}"] = m
            if m.vendor_name:
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

        result = await db.execute(query.limit(1000))  # Sicherheitslimit
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
        """Liefert Kontenrahmen-Instanz."""
        return self._kontenrahmen_registry.get(
            kontenrahmen_name,
            self._kontenrahmen_registry["SKR03"]
        )

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
        """Sucht passendes Vendor-Mapping."""
        # Nur bei Eingangsrechnungen
        if invoice.invoice_direction != InvoiceDirection.INCOMING:
            return None

        if not invoice.sender:
            return None

        # 1. Exakter Match: USt-IdNr
        if invoice.sender_vat_id:
            key = f"vat:{invoice.sender_vat_id}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        # 2. Exakter Match: IBAN
        if invoice.sender_bank and invoice.sender_bank.iban:
            key = f"iban:{invoice.sender_bank.iban}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        # 3. Fuzzy Match: Firmenname
        if invoice.sender.company:
            name_lower = invoice.sender.company.lower()
            key = f"name:{name_lower}"
            if key in vendor_mappings:
                return vendor_mappings[key]

        return None


# Singleton-Pattern
_datev_export_service: Optional[DATEVExportService] = None


def get_datev_export_service() -> DATEVExportService:
    """Factory-Funktion fuer DATEVExportService."""
    global _datev_export_service
    if _datev_export_service is None:
        _datev_export_service = DATEVExportService()
    return _datev_export_service
