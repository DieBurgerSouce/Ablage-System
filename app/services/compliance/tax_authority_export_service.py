# -*- coding: utf-8 -*-
"""
Tax Authority Export Service (§90 III AO).

Strukturierter Export für Steuerprüfer:
- GDPdU-konformer Export (XML + CSV)
- Audit-Trail im vorgeschriebenen Format
- Index-Datei für Prüfsoftware (IDEA, ACL)
- Datenträgerüberlassung nach BMF-Schreiben

Feature 20: Tax Authority Export Format

HINWEIS: Dieser Export ermöglicht die Datenträgerüberlassung
nach §147 Abs. 6 AO für Außenprüfungen.

Feinpoliert und durchdacht - Steuerkonformer Datenexport.
"""

from __future__ import annotations

import csv
import io
import os
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID
import hashlib
import xml.etree.ElementTree as ET
from xml.dom import minidom

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (

    AuditLog,
    Company,
    Document,
    InvoiceTracking,
    BankTransaction,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

# GDPdU XML Namespace
GDPDU_NAMESPACE = "http://gdpdu.de/2019/schema"

# Standard-Zeichensatz für Export
ENCODING = "UTF-8"

# Maximale Feldlängen für IDEA-Kompatibilität
MAX_FIELD_LENGTH = 255


# =============================================================================
# Enums
# =============================================================================


class ExportFormat(str, Enum):
    """Unterstützte Export-Formate."""
    GDPDU = "gdpdu"           # GDPdU XML mit CSV-Daten
    CSV = "csv"               # Nur CSV
    IDEA = "idea"             # IDEA-kompatibel
    DATEV = "datev"           # DATEV-Format


class DataCategory(str, Enum):
    """Kategorien der exportierbaren Daten."""
    INVOICES_OUTGOING = "invoices_outgoing"      # Ausgangsrechnungen
    INVOICES_INCOMING = "invoices_incoming"      # Eingangsrechnungen
    BANK_TRANSACTIONS = "bank_transactions"      # Bankbewegungen
    DOCUMENTS = "documents"                       # Dokumente
    AUDIT_LOG = "audit_log"                      # Änderungsprotokoll
    MASTER_DATA = "master_data"                  # Stammdaten


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExportField:
    """Definition eines Export-Feldes."""
    name: str
    description: str
    data_type: str  # "text", "numeric", "date", "datetime"
    max_length: Optional[int] = None
    decimal_places: Optional[int] = None
    required: bool = False


@dataclass
class ExportTable:
    """Definition einer Export-Tabelle."""
    name: str
    description: str
    fields: List[ExportField]
    primary_key: str
    category: DataCategory


@dataclass
class ExportStatistics:
    """Statistiken des Exports."""
    total_records: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    export_duration_seconds: float = 0.0
    file_sizes_bytes: Dict[str, int] = field(default_factory=dict)
    checksum_md5: Optional[str] = None


@dataclass
class ExportResult:
    """Ergebnis des Exports."""
    success: bool
    export_id: str
    format: ExportFormat
    period_start: date
    period_end: date
    company_name: str
    created_at: datetime
    statistics: ExportStatistics
    files: List[str]
    archive_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary."""
        return {
            "success": self.success,
            "export_id": self.export_id,
            "format": self.format.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "company_name": self.company_name,
            "created_at": self.created_at.isoformat(),
            "statistics": {
                "total_records": self.statistics.total_records,
                "by_category": self.statistics.by_category,
                "export_duration_seconds": self.statistics.export_duration_seconds,
                "file_sizes_bytes": self.statistics.file_sizes_bytes,
                "checksum_md5": self.statistics.checksum_md5,
            },
            "files": self.files,
            "archive_path": self.archive_path,
            "error": self.error,
        }


# =============================================================================
# Table Definitions
# =============================================================================


def get_invoice_table_definition() -> ExportTable:
    """Definition für Rechnungstabelle."""
    return ExportTable(
        name="rechnungen",
        description="Ausgangs- und Eingangsrechnungen",
        category=DataCategory.INVOICES_OUTGOING,
        primary_key="rechnungsnummer",
        fields=[
            ExportField("rechnungsnummer", "Rechnungsnummer", "text", 50, required=True),
            ExportField("rechnungsart", "Art (E=Eingang, A=Ausgang)", "text", 1, required=True),
            ExportField("rechnungsdatum", "Rechnungsdatum", "date", required=True),
            ExportField("fälligkeitsdatum", "Fälligkeitsdatum", "date"),
            ExportField("buchungsdatum", "Buchungsdatum", "date"),
            ExportField("lieferant_kunde", "Lieferant/Kunde", "text", 100),
            ExportField("nettobetrag", "Nettobetrag EUR", "numeric", decimal_places=2),
            ExportField("mwst_satz", "MwSt-Satz %", "numeric", decimal_places=2),
            ExportField("mwst_betrag", "MwSt-Betrag EUR", "numeric", decimal_places=2),
            ExportField("bruttobetrag", "Bruttobetrag EUR", "numeric", decimal_places=2),
            ExportField("währung", "Währung", "text", 3),
            ExportField("status", "Status", "text", 20),
            ExportField("dokument_id", "Dokument-ID", "text", 36),
            ExportField("buchungstext", "Buchungstext", "text", MAX_FIELD_LENGTH),
        ],
    )


def get_bank_transaction_table_definition() -> ExportTable:
    """Definition für Banktransaktionen."""
    return ExportTable(
        name="bankbewegungen",
        description="Kontobewegungen",
        category=DataCategory.BANK_TRANSACTIONS,
        primary_key="transaktions_id",
        fields=[
            ExportField("transaktions_id", "Transaktions-ID", "text", 36, required=True),
            ExportField("kontonummer", "Kontonummer", "text", 22),
            ExportField("bankleitzahl", "BLZ/BIC", "text", 11),
            ExportField("buchungsdatum", "Buchungsdatum", "date", required=True),
            ExportField("wertstellungsdatum", "Wertstellung", "date"),
            ExportField("betrag", "Betrag EUR", "numeric", decimal_places=2, required=True),
            ExportField("währung", "Währung", "text", 3),
            ExportField("verwendungszweck", "Verwendungszweck", "text", MAX_FIELD_LENGTH),
            ExportField("gegenkonto_name", "Gegenkonto Name", "text", 100),
            ExportField("gegenkonto_iban", "Gegenkonto IBAN", "text", 34),
            ExportField("buchungsart", "Buchungsart", "text", 50),
        ],
    )


def get_document_table_definition() -> ExportTable:
    """Definition für Dokumententabelle."""
    return ExportTable(
        name="belege",
        description="Digitalisierte Belege",
        category=DataCategory.DOCUMENTS,
        primary_key="dokument_id",
        fields=[
            ExportField("dokument_id", "Dokument-ID", "text", 36, required=True),
            ExportField("dokumenttyp", "Dokumenttyp", "text", 50),
            ExportField("erfassungsdatum", "Erfassungsdatum", "datetime", required=True),
            ExportField("belegdatum", "Belegdatum", "date"),
            ExportField("dateiname", "Originaldateiname", "text", MAX_FIELD_LENGTH),
            ExportField("dateipfad", "Archivpfad", "text", MAX_FIELD_LENGTH),
            ExportField("dateigröße", "Dateigröße Bytes", "numeric"),
            ExportField("prüfsumme_sha256", "Prüfsumme SHA256", "text", 64),
            ExportField("ocr_text", "OCR-Text (Auszug)", "text", MAX_FIELD_LENGTH),
            ExportField("status", "Verarbeitungsstatus", "text", 20),
        ],
    )


def get_audit_log_table_definition() -> ExportTable:
    """Definition für Änderungsprotokoll."""
    return ExportTable(
        name="änderungsprotokoll",
        description="Protokoll aller Änderungen (§146 AO)",
        category=DataCategory.AUDIT_LOG,
        primary_key="log_id",
        fields=[
            ExportField("log_id", "Protokoll-ID", "text", 36, required=True),
            ExportField("zeitstempel", "Zeitstempel", "datetime", required=True),
            ExportField("benutzer", "Benutzer", "text", 100),
            ExportField("aktion", "Aktion", "text", 50, required=True),
            ExportField("tabelle", "Betroffene Tabelle", "text", 50),
            ExportField("datensatz_id", "Betroffener Datensatz", "text", 36),
            ExportField("änderung_vorher", "Wert vorher", "text", MAX_FIELD_LENGTH),
            ExportField("änderung_nachher", "Wert nachher", "text", MAX_FIELD_LENGTH),
            ExportField("ip_adresse", "IP-Adresse", "text", 45),
        ],
    )


# =============================================================================
# Service Implementation
# =============================================================================


class TaxAuthorityExportService:
    """Service für steuerkonformen Datenexport."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiere Service mit Datenbankverbindung."""
        self.db = db

    async def create_gdpdu_export(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        categories: Optional[List[DataCategory]] = None,
        output_dir: Optional[str] = None,
    ) -> ExportResult:
        """
        Erstelle GDPdU-konformen Export.

        Args:
            company_id: ID der Firma
            period_start: Beginn des Exportzeitraums
            period_end: Ende des Exportzeitraums
            categories: Zu exportierende Kategorien (default: alle)
            output_dir: Ausgabeverzeichnis

        Returns:
            ExportResult mit Exportdetails
        """
        import time
        start_time = time.time()

        # Hole Firmendaten
        company = await self._get_company(company_id)
        if not company:
            return ExportResult(
                success=False,
                export_id="",
                format=ExportFormat.GDPDU,
                period_start=period_start,
                period_end=period_end,
                company_name="",
                created_at=datetime.now(timezone.utc),
                statistics=ExportStatistics(),
                files=[],
                error="Firma nicht gefunden",
            )

        # Generiere Export-ID
        export_id = self._generate_export_id(company_id, period_start)

        # Erstelle Ausgabeverzeichnis
        if output_dir is None:
            output_dir = f"/tmp/gdpdu_export_{export_id}"
        os.makedirs(output_dir, exist_ok=True)

        # Default: Alle Kategorien
        if categories is None:
            categories = list(DataCategory)

        statistics = ExportStatistics()
        files: List[str] = []

        try:
            # Exportiere Daten nach Kategorie
            for category in categories:
                if category == DataCategory.INVOICES_OUTGOING or category == DataCategory.INVOICES_INCOMING:
                    count, file_path = await self._export_invoices(
                        company_id, period_start, period_end, output_dir
                    )
                    if count > 0:
                        statistics.by_category["rechnungen"] = count
                        statistics.total_records += count
                        files.append(file_path)

                elif category == DataCategory.BANK_TRANSACTIONS:
                    count, file_path = await self._export_bank_transactions(
                        company_id, period_start, period_end, output_dir
                    )
                    if count > 0:
                        statistics.by_category["bankbewegungen"] = count
                        statistics.total_records += count
                        files.append(file_path)

                elif category == DataCategory.DOCUMENTS:
                    count, file_path = await self._export_documents(
                        company_id, period_start, period_end, output_dir
                    )
                    if count > 0:
                        statistics.by_category["belege"] = count
                        statistics.total_records += count
                        files.append(file_path)

                elif category == DataCategory.AUDIT_LOG:
                    count, file_path = await self._export_audit_log(
                        company_id, period_start, period_end, output_dir
                    )
                    if count > 0:
                        statistics.by_category["änderungsprotokoll"] = count
                        statistics.total_records += count
                        files.append(file_path)

            # Erstelle index.xml (GDPdU-Beschreibungsdatei)
            index_path = self._create_gdpdu_index(
                output_dir, company.name, period_start, period_end, files
            )
            files.append(index_path)

            # Erstelle gdpdu-01-09-2004.dtd (Schema-Datei)
            dtd_path = self._create_gdpdu_dtd(output_dir)
            files.append(dtd_path)

            # Berechne Dateigrößen
            for file_path in files:
                if os.path.exists(file_path):
                    statistics.file_sizes_bytes[os.path.basename(file_path)] = os.path.getsize(file_path)

            # Erstelle ZIP-Archiv
            archive_path = f"{output_dir}.zip"
            self._create_archive(output_dir, archive_path)

            # Berechne Prüfsumme
            statistics.checksum_md5 = self._calculate_checksum(archive_path)

            statistics.export_duration_seconds = time.time() - start_time

            logger.info(
                "GDPdU-Export erstellt",
                export_id=export_id,
                company=company.name,
                records=statistics.total_records,
            )

            return ExportResult(
                success=True,
                export_id=export_id,
                format=ExportFormat.GDPDU,
                period_start=period_start,
                period_end=period_end,
                company_name=company.name,
                created_at=datetime.now(timezone.utc),
                statistics=statistics,
                files=files,
                archive_path=archive_path,
            )

        except Exception as e:
            logger.error("GDPdU-Export fehlgeschlagen", **safe_error_log(e))
            return ExportResult(
                success=False,
                export_id=export_id,
                format=ExportFormat.GDPDU,
                period_start=period_start,
                period_end=period_end,
                company_name=company.name if company else "",
                created_at=datetime.now(timezone.utc),
                statistics=statistics,
                files=[],
                **safe_error_log(e),
            )

    # =========================================================================
    # Private Export Methods
    # =========================================================================

    async def _get_company(self, company_id: UUID) -> Optional[Company]:
        """Hole Firmendaten."""
        result = await self.db.execute(
            select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    def _generate_export_id(self, company_id: UUID, period_start: date) -> str:
        """Generiere eindeutige Export-ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"GDPDU_{str(company_id)[:8]}_{period_start.year}_{timestamp}"

    async def _export_invoices(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        output_dir: str,
    ) -> Tuple[int, str]:
        """Exportiere Rechnungen als CSV."""
        table_def = get_invoice_table_definition()
        file_path = os.path.join(output_dir, f"{table_def.name}.csv")

        # Query invoices
        result = await self.db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= period_start,
                    InvoiceTracking.invoice_date <= period_end,
                )
            )
        )
        invoices = result.scalars().all()

        # Write CSV
        with open(file_path, "w", newline="", encoding=ENCODING) as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            # Header row
            writer.writerow([field.name for field in table_def.fields])

            # Data rows
            for inv in invoices:
                row = [
                    inv.invoice_number or "",
                    "E" if inv.invoice_type == "incoming" else "A",
                    inv.invoice_date.strftime("%Y-%m-%d") if inv.invoice_date else "",
                    inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "",
                    "",  # buchungsdatum
                    "",  # lieferant_kunde (würde Entity-Lookup benötigen)
                    str(inv.net_amount) if inv.net_amount else "",
                    str(inv.vat_rate) if hasattr(inv, 'vat_rate') else "",
                    str(inv.vat_amount) if hasattr(inv, 'vat_amount') else "",
                    str(inv.total_amount) if inv.total_amount else "",
                    "EUR",
                    inv.status.value if inv.status else "",
                    str(inv.document_id) if inv.document_id else "",
                    "",  # buchungstext
                ]
                writer.writerow(row)

        return len(invoices), file_path

    async def _export_bank_transactions(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        output_dir: str,
    ) -> Tuple[int, str]:
        """Exportiere Bankbewegungen als CSV."""
        table_def = get_bank_transaction_table_definition()
        file_path = os.path.join(output_dir, f"{table_def.name}.csv")

        # Query bank transactions
        result = await self.db.execute(
            select(BankTransaction).where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.booking_date >= period_start,
                    BankTransaction.booking_date <= period_end,
                )
            )
        )
        transactions = result.scalars().all()

        # Write CSV
        with open(file_path, "w", newline="", encoding=ENCODING) as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            # Header row
            writer.writerow([field.name for field in table_def.fields])

            # Data rows
            for tx in transactions:
                row = [
                    str(tx.id),
                    tx.account_number or "",
                    tx.bank_code or "",
                    tx.booking_date.strftime("%Y-%m-%d") if tx.booking_date else "",
                    tx.value_date.strftime("%Y-%m-%d") if tx.value_date else "",
                    str(tx.amount) if tx.amount else "",
                    tx.currency or "EUR",
                    (tx.reference or "")[:MAX_FIELD_LENGTH],
                    (tx.counterparty_name or "")[:100],
                    tx.counterparty_iban or "",
                    tx.transaction_type or "",
                ]
                writer.writerow(row)

        return len(transactions), file_path

    async def _export_documents(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        output_dir: str,
    ) -> Tuple[int, str]:
        """Exportiere Dokumentenverzeichnis als CSV."""
        table_def = get_document_table_definition()
        file_path = os.path.join(output_dir, f"{table_def.name}.csv")

        # Query documents
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= datetime.combine(period_start, datetime.min.time()),
                    Document.created_at <= datetime.combine(period_end, datetime.max.time()),
                )
            )
        )
        documents = result.scalars().all()

        # Write CSV
        with open(file_path, "w", newline="", encoding=ENCODING) as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            # Header row
            writer.writerow([field.name for field in table_def.fields])

            # Data rows
            for doc in documents:
                row = [
                    str(doc.id),
                    doc.document_type or "",
                    doc.created_at.strftime("%Y-%m-%d %H:%M:%S") if doc.created_at else "",
                    doc.document_date.strftime("%Y-%m-%d") if doc.document_date else "",
                    (doc.original_filename or "")[:MAX_FIELD_LENGTH],
                    (doc.storage_path or "")[:MAX_FIELD_LENGTH],
                    str(doc.file_size) if doc.file_size else "",
                    doc.file_hash or "",
                    (doc.ocr_text or "")[:MAX_FIELD_LENGTH] if doc.ocr_text else "",
                    doc.status.value if doc.status else "",
                ]
                writer.writerow(row)

        return len(documents), file_path

    async def _export_audit_log(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
        output_dir: str,
    ) -> Tuple[int, str]:
        """Exportiere Änderungsprotokoll als CSV."""
        table_def = get_audit_log_table_definition()
        file_path = os.path.join(output_dir, f"{table_def.name}.csv")

        # Query audit logs
        result = await self.db.execute(
            select(AuditLog).where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= datetime.combine(period_start, datetime.min.time()),
                    AuditLog.created_at <= datetime.combine(period_end, datetime.max.time()),
                )
            ).order_by(AuditLog.created_at)
        )
        logs = result.scalars().all()

        # Write CSV
        with open(file_path, "w", newline="", encoding=ENCODING) as f:
            writer = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)

            # Header row
            writer.writerow([field.name for field in table_def.fields])

            # Data rows
            for log in logs:
                row = [
                    str(log.id),
                    log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else "",
                    log.user_email or "",
                    log.action or "",
                    log.resource_type or "",
                    str(log.resource_id) if log.resource_id else "",
                    str(log.old_value)[:MAX_FIELD_LENGTH] if log.old_value else "",
                    str(log.new_value)[:MAX_FIELD_LENGTH] if log.new_value else "",
                    log.ip_address or "",
                ]
                writer.writerow(row)

        return len(logs), file_path

    def _create_gdpdu_index(
        self,
        output_dir: str,
        company_name: str,
        period_start: date,
        period_end: date,
        data_files: List[str],
    ) -> str:
        """Erstelle GDPdU index.xml."""
        # Create XML structure
        root = ET.Element("DataSet")
        root.set("xmlns", GDPDU_NAMESPACE)

        # Version info
        version = ET.SubElement(root, "Version")
        version.text = "3.0"

        # Data supplier info
        data_supplier = ET.SubElement(root, "DataSupplier")
        name = ET.SubElement(data_supplier, "Name")
        name.text = company_name
        location = ET.SubElement(data_supplier, "Location")
        location.text = "Deutschland"

        # Period
        period = ET.SubElement(root, "Period")
        from_elem = ET.SubElement(period, "From")
        from_elem.text = period_start.strftime("%Y-%m-%d")
        to_elem = ET.SubElement(period, "To")
        to_elem.text = period_end.strftime("%Y-%m-%d")

        # Media info
        media = ET.SubElement(root, "Media")
        media_name = ET.SubElement(media, "Name")
        media_name.text = "GDPdU-Export"

        # Tables
        for file_path in data_files:
            if file_path.endswith(".csv"):
                table_name = os.path.basename(file_path).replace(".csv", "")
                table = ET.SubElement(media, "Table")
                url = ET.SubElement(table, "URL")
                url.text = os.path.basename(file_path)
                name_elem = ET.SubElement(table, "Name")
                name_elem.text = table_name
                description = ET.SubElement(table, "Description")
                description.text = f"Tabelle {table_name}"
                encoding_elem = ET.SubElement(table, "Encoding")
                encoding_elem.text = ENCODING
                decimal = ET.SubElement(table, "DecimalSymbol")
                decimal.text = ","
                thousands = ET.SubElement(table, "ThousandsSeparator")
                thousands.text = "."
                delimiter = ET.SubElement(table, "ColumnDelimiter")
                delimiter.text = ";"

        # Write XML file
        file_path = os.path.join(output_dir, "index.xml")
        xml_string = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
        with open(file_path, "w", encoding=ENCODING) as f:
            f.write(xml_string)

        return file_path

    def _create_gdpdu_dtd(self, output_dir: str) -> str:
        """Erstelle GDPdU DTD-Datei."""
        dtd_content = """<?xml version="1.0" encoding="UTF-8"?>
<!-- GDPdU DTD Version 3.0 -->
<!ELEMENT DataSet (Version, DataSupplier, Period, Media+)>
<!ELEMENT Version (#PCDATA)>
<!ELEMENT DataSupplier (Name, Location)>
<!ELEMENT Name (#PCDATA)>
<!ELEMENT Location (#PCDATA)>
<!ELEMENT Period (From, To)>
<!ELEMENT From (#PCDATA)>
<!ELEMENT To (#PCDATA)>
<!ELEMENT Media (Name, Table+)>
<!ELEMENT Table (URL, Name, Description?, Encoding?, DecimalSymbol?, ThousandsSeparator?, ColumnDelimiter?)>
<!ELEMENT URL (#PCDATA)>
<!ELEMENT Description (#PCDATA)>
<!ELEMENT Encoding (#PCDATA)>
<!ELEMENT DecimalSymbol (#PCDATA)>
<!ELEMENT ThousandsSeparator (#PCDATA)>
<!ELEMENT ColumnDelimiter (#PCDATA)>
"""
        file_path = os.path.join(output_dir, "gdpdu-01-09-2004.dtd")
        with open(file_path, "w", encoding=ENCODING) as f:
            f.write(dtd_content)

        return file_path

    def _create_archive(self, source_dir: str, archive_path: str) -> None:
        """Erstelle ZIP-Archiv."""
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)

    def _calculate_checksum(self, file_path: str) -> str:
        """Berechne MD5-Prüfsumme."""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    async def count_records_by_category(
        self,
        company_id: UUID,
        period_start: date,
        period_end: date,
    ) -> Dict[str, int]:
        """
        Zähle Datensätze pro Kategorie für die Export-Vorschau.

        Args:
            company_id: ID der Firma
            period_start: Beginn des Exportzeitraums
            period_end: Ende des Exportzeitraums

        Returns:
            Dictionary mit Kategorie → Anzahl
        """
        counts: Dict[str, int] = {}

        # Rechnungen zählen
        invoice_count = await self.db.execute(
            select(func.count(InvoiceTracking.id)).where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= period_start,
                    InvoiceTracking.invoice_date <= period_end,
                )
            )
        )
        counts["rechnungen"] = invoice_count.scalar() or 0

        # Bankbewegungen zählen
        transaction_count = await self.db.execute(
            select(func.count(BankTransaction.id)).where(
                and_(
                    BankTransaction.company_id == company_id,
                    BankTransaction.booking_date >= period_start,
                    BankTransaction.booking_date <= period_end,
                )
            )
        )
        counts["bankbewegungen"] = transaction_count.scalar() or 0

        # Dokumente zählen
        document_count = await self.db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= datetime.combine(period_start, datetime.min.time()),
                    Document.created_at <= datetime.combine(period_end, datetime.max.time()),
                )
            )
        )
        counts["belege"] = document_count.scalar() or 0

        # Audit-Logs zählen
        audit_count = await self.db.execute(
            select(func.count(AuditLog.id)).where(
                and_(
                    AuditLog.company_id == company_id,
                    AuditLog.created_at >= datetime.combine(period_start, datetime.min.time()),
                    AuditLog.created_at <= datetime.combine(period_end, datetime.max.time()),
                )
            )
        )
        counts["änderungsprotokoll"] = audit_count.scalar() or 0

        return counts


# =============================================================================
# Factory Function
# =============================================================================


def get_tax_authority_export_service(db: AsyncSession) -> TaxAuthorityExportService:
    """Factory-Funktion für TaxAuthorityExportService."""
    return TaxAuthorityExportService(db)
