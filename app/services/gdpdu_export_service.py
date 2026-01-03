# -*- coding: utf-8 -*-
"""
GDPdU Export Service - Datenexport fuer Betriebspruefungen.

Implementiert den Export nach GDPdU (Grundsaetze zum Datenzugriff und zur
Pruefbarkeit digitaler Unterlagen) gemaess BMF-Schreiben vom 28.11.2019.

Das GDPdU-Format besteht aus:
1. index.xml - Strukturbeschreibung der Daten
2. gdpdu-01-09-2004.dtd - DTD-Datei (Version 1.9)
3. CSV/XML-Datendateien - Die eigentlichen Daten

Dieses Modul erstellt einen vollstaendigen Export fuer Pruefungszwecke.
"""

import csv
import io
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO, Optional, Union
from xml.etree import ElementTree as ET
from xml.dom import minidom

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Document,
    DocumentArchive,
    Company,
    RetentionCategory,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# GDPdU KONSTANTEN
# =============================================================================

GDPDU_VERSION = "1.0"
GDPDU_DTD_VERSION = "gdpdu-01-09-2004.dtd"

# GDPdU DTD (vereinfachte Version fuer Kompatibilitaet)
GDPDU_DTD_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!ELEMENT DataSet (Version, DataSupplier?, Media+)>
<!ELEMENT Version (#PCDATA)>
<!ELEMENT DataSupplier (Name, Location?, Comment?)>
<!ELEMENT Name (#PCDATA)>
<!ELEMENT Location (#PCDATA)>
<!ELEMENT Comment (#PCDATA)>
<!ELEMENT Media (Name, Table+)>
<!ELEMENT Table (URL, Name?, Description?, Validity?, Range?, DigitalSignatures?, UTF8?, DecimalSymbol?, ThousandsSeparator?, VariableLength?)>
<!ELEMENT URL (#PCDATA)>
<!ELEMENT Description (#PCDATA)>
<!ELEMENT Validity (Range, Format?)>
<!ELEMENT Range (From?, To?)>
<!ELEMENT From (#PCDATA)>
<!ELEMENT To (#PCDATA)>
<!ELEMENT Format (#PCDATA)>
<!ELEMENT DigitalSignatures (Text?)>
<!ELEMENT Text (#PCDATA)>
<!ELEMENT UTF8 EMPTY>
<!ELEMENT DecimalSymbol (#PCDATA)>
<!ELEMENT ThousandsSeparator (#PCDATA)>
<!ELEMENT VariableLength (ColumnDelimiter?, RecordDelimiter?, TextEncapsulator?, VariableColumn+, ForeignKey*)>
<!ELEMENT ColumnDelimiter (#PCDATA)>
<!ELEMENT RecordDelimiter (#PCDATA)>
<!ELEMENT TextEncapsulator (#PCDATA)>
<!ELEMENT VariableColumn (Name, Description?, Numeric?, AlphaNumeric?, Date?, MaxLength?)>
<!ELEMENT Numeric (ImpliedAccuracy?, Accuracy?)>
<!ELEMENT ImpliedAccuracy (#PCDATA)>
<!ELEMENT Accuracy (#PCDATA)>
<!ELEMENT AlphaNumeric EMPTY>
<!ELEMENT Date (Format?)>
<!ELEMENT MaxLength (#PCDATA)>
<!ELEMENT ForeignKey (Name, References)>
<!ELEMENT References (#PCDATA)>
"""


# =============================================================================
# DATENKLASSEN
# =============================================================================

@dataclass
class GDPdUExportOptions:
    """Optionen fuer den GDPdU-Export."""
    company_id: uuid.UUID
    start_date: date
    end_date: date
    include_documents: bool = True
    include_archives: bool = True
    include_invoices: bool = True
    include_contracts: bool = True
    comment: Optional[str] = None


@dataclass
class GDPdUColumn:
    """Definition einer GDPdU-Spalte."""
    name: str
    description: str
    data_type: str  # "AlphaNumeric", "Numeric", "Date"
    max_length: Optional[int] = None
    date_format: Optional[str] = None
    accuracy: Optional[int] = None


@dataclass
class GDPdUTable:
    """Definition einer GDPdU-Tabelle."""
    name: str
    description: str
    filename: str
    columns: list[GDPdUColumn] = field(default_factory=list)


# =============================================================================
# TABELLENDEFINITIONEN
# =============================================================================

DOCUMENT_TABLE = GDPdUTable(
    name="Dokumente",
    description="Archivierte Dokumente mit GoBD-Signatur",
    filename="dokumente.csv",
    columns=[
        GDPdUColumn("DokumentID", "Eindeutige Dokument-ID (UUID)", "AlphaNumeric", 36),
        GDPdUColumn("Dateiname", "Originaler Dateiname", "AlphaNumeric", 255),
        GDPdUColumn("MIMETyp", "MIME-Typ des Dokuments", "AlphaNumeric", 100),
        GDPdUColumn("Dateigroesse", "Groesse in Bytes", "Numeric", accuracy=0),
        GDPdUColumn("Hochgeladen", "Zeitpunkt des Uploads", "Date", date_format="YYYY-MM-DD HH:MM:SS"),
        GDPdUColumn("Status", "Dokumentenstatus", "AlphaNumeric", 50),
        GDPdUColumn("Pruefsumme", "SHA-256 Pruefsumme der Originaldatei", "AlphaNumeric", 64),
    ]
)

ARCHIVE_TABLE = GDPdUTable(
    name="Archive",
    description="GoBD-konforme Archivierungsinformationen",
    filename="archive.csv",
    columns=[
        GDPdUColumn("ArchivID", "Eindeutige Archiv-ID (UUID)", "AlphaNumeric", 36),
        GDPdUColumn("DokumentID", "Referenz auf Dokument", "AlphaNumeric", 36),
        GDPdUColumn("ContentHash", "SHA-256 Hash des archivierten Inhalts", "AlphaNumeric", 64),
        GDPdUColumn("HashAlgorithmus", "Verwendeter Hash-Algorithmus", "AlphaNumeric", 20),
        GDPdUColumn("Signaturzeit", "Zeitpunkt der Signierung", "Date", date_format="YYYY-MM-DD HH:MM:SS"),
        GDPdUColumn("Aufbewahrungskategorie", "GoBD-Kategorie", "AlphaNumeric", 50),
        GDPdUColumn("Aufbewahrungsjahre", "Aufbewahrungsdauer in Jahren", "Numeric", accuracy=0),
        GDPdUColumn("AblaufDatum", "Datum des Fristablaufs", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("Verifiziert", "Verifikationsstatus (1=Ja, 0=Nein)", "Numeric", accuracy=0),
        GDPdUColumn("ArchivierungsDatum", "Datum der Archivierung", "Date", date_format="YYYY-MM-DD HH:MM:SS"),
    ]
)

INVOICE_TABLE = GDPdUTable(
    name="Rechnungen",
    description="Extrahierte Rechnungsdaten",
    filename="rechnungen.csv",
    columns=[
        GDPdUColumn("DokumentID", "Referenz auf Dokument", "AlphaNumeric", 36),
        GDPdUColumn("Rechnungsnummer", "Rechnungsnummer", "AlphaNumeric", 100),
        GDPdUColumn("Rechnungsdatum", "Datum der Rechnung", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("Faelligkeitsdatum", "Faelligkeitsdatum", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("AbsenderFirma", "Name des Absenders", "AlphaNumeric", 255),
        GDPdUColumn("AbsenderStrasse", "Strasse des Absenders", "AlphaNumeric", 255),
        GDPdUColumn("AbsenderPLZ", "PLZ des Absenders", "AlphaNumeric", 20),
        GDPdUColumn("AbsenderOrt", "Ort des Absenders", "AlphaNumeric", 100),
        GDPdUColumn("EmpfaengerFirma", "Name des Empfaengers", "AlphaNumeric", 255),
        GDPdUColumn("UStIdNr", "Umsatzsteuer-ID des Absenders", "AlphaNumeric", 30),
        GDPdUColumn("IBAN", "IBAN des Absenders", "AlphaNumeric", 34),
        GDPdUColumn("Nettobetrag", "Nettobetrag in EUR", "Numeric", accuracy=2),
        GDPdUColumn("MwStSatz", "Mehrwertsteuersatz in Prozent", "Numeric", accuracy=2),
        GDPdUColumn("MwStBetrag", "Mehrwertsteuerbetrag in EUR", "Numeric", accuracy=2),
        GDPdUColumn("Bruttobetrag", "Bruttobetrag in EUR", "Numeric", accuracy=2),
        GDPdUColumn("Waehrung", "Waehrungscode (z.B. EUR)", "AlphaNumeric", 3),
    ]
)

CONTRACT_TABLE = GDPdUTable(
    name="Vertraege",
    description="Extrahierte Vertragsdaten",
    filename="vertraege.csv",
    columns=[
        GDPdUColumn("DokumentID", "Referenz auf Dokument", "AlphaNumeric", 36),
        GDPdUColumn("Vertragsnummer", "Vertragsnummer", "AlphaNumeric", 100),
        GDPdUColumn("Vertragsdatum", "Datum des Vertragsschlusses", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("Vertragsbeginn", "Startdatum", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("Vertragsende", "Enddatum", "Date", date_format="YYYY-MM-DD"),
        GDPdUColumn("ParteiA", "Name der ersten Partei", "AlphaNumeric", 255),
        GDPdUColumn("ParteiB", "Name der zweiten Partei", "AlphaNumeric", 255),
        GDPdUColumn("Vertragswert", "Gesamtwert des Vertrags in EUR", "Numeric", accuracy=2),
        GDPdUColumn("Vertragstyp", "Art des Vertrags", "AlphaNumeric", 100),
    ]
)


# =============================================================================
# GDPDU EXPORT SERVICE
# =============================================================================

class GDPdUExportService:
    """Service fuer GDPdU-konforme Datenexporte."""

    def __init__(self) -> None:
        """Initialisiert den GDPdU Export Service."""
        self._tables: list[GDPdUTable] = []

    async def create_export(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
        output_path: Optional[Path] = None,
    ) -> Union[bytes, Path]:
        """Erstellt einen vollstaendigen GDPdU-Export als ZIP-Archiv.

        MEMORY-OPTIMIERT: Bei grossen Exporten wird empfohlen, output_path zu
        verwenden, um das ZIP direkt auf die Festplatte zu schreiben und OOM
        zu vermeiden.

        Args:
            db: Datenbank-Session
            options: Export-Optionen
            output_path: Optionaler Pfad fuer die ZIP-Datei (Streaming-Modus).
                        Wenn nicht angegeben, wird das ZIP im Speicher erstellt.

        Returns:
            bytes: ZIP-Archiv als Bytes (wenn output_path nicht angegeben)
            Path: Pfad zur ZIP-Datei (wenn output_path angegeben)

        Raises:
            ValueError: Bei ungueltigen Optionen
        """
        logger.info(
            "gdpdu_export_started",
            company_id=str(options.company_id),
            start_date=str(options.start_date),
            end_date=str(options.end_date),
            streaming_mode=output_path is not None,
        )

        # Firmeninfo laden
        company = await self._get_company(db, options.company_id)
        if not company:
            raise ValueError(f"Firma mit ID {options.company_id} nicht gefunden")

        # =======================================================================
        # MEMORY-OPTIMIERUNG: Streaming-Modus fuer grosse Exporte
        # =======================================================================
        if output_path:
            # Streaming: Direkt auf Festplatte schreiben (verhindert OOM)
            zip_path = output_path
        else:
            # Legacy: Temporaere Datei verwenden statt BytesIO (reduziert Peak-Memory)
            temp_dir = tempfile.mkdtemp(prefix="gdpdu_export_")
            zip_path = Path(temp_dir) / "export.zip"

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Reset Tabellenliste
                self._tables = []

                # Dokumente exportieren
                if options.include_documents:
                    doc_data = await self._export_documents(db, options)
                    if doc_data:
                        zf.writestr(DOCUMENT_TABLE.filename, doc_data)
                        self._tables.append(DOCUMENT_TABLE)

                # Archive exportieren
                if options.include_archives:
                    archive_data = await self._export_archives(db, options)
                    if archive_data:
                        zf.writestr(ARCHIVE_TABLE.filename, archive_data)
                        self._tables.append(ARCHIVE_TABLE)

                # Rechnungen exportieren
                if options.include_invoices:
                    invoice_data = await self._export_invoices(db, options)
                    if invoice_data:
                        zf.writestr(INVOICE_TABLE.filename, invoice_data)
                        self._tables.append(INVOICE_TABLE)

                # Vertraege exportieren
                if options.include_contracts:
                    contract_data = await self._export_contracts(db, options)
                    if contract_data:
                        zf.writestr(CONTRACT_TABLE.filename, contract_data)
                        self._tables.append(CONTRACT_TABLE)

                # Index.xml erstellen
                index_xml = self._generate_index_xml(company, options)
                zf.writestr("index.xml", index_xml)

                # DTD-Datei hinzufuegen
                zf.writestr(GDPDU_DTD_VERSION, GDPDU_DTD_CONTENT)

                # README hinzufuegen
                readme = self._generate_readme(company, options)
                zf.writestr("README.txt", readme)

            zip_size = zip_path.stat().st_size

            logger.info(
                "gdpdu_export_completed",
                company_id=str(options.company_id),
                tables_exported=len(self._tables),
                zip_size_bytes=zip_size,
                streaming_mode=output_path is not None,
            )

            if output_path:
                # Streaming-Modus: Pfad zurueckgeben
                return zip_path
            else:
                # Legacy-Modus: Bytes zurueckgeben und temp-Datei aufraeuumen
                with open(zip_path, 'rb') as f:
                    result = f.read()
                return result

        finally:
            # Temp-Verzeichnis aufraeuumen (nur im Legacy-Modus)
            if not output_path and zip_path.exists():
                try:
                    os.remove(zip_path)
                    os.rmdir(zip_path.parent)
                except OSError:
                    pass  # Ignoriere Fehler beim Aufraeuumen

    async def get_export_preview(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
    ) -> dict:
        """Gibt eine Vorschau des Exports zurueck (ohne Datengenerierung).

        Args:
            db: Datenbank-Session
            options: Export-Optionen

        Returns:
            Dictionary mit Export-Statistiken
        """
        # Dokumente zaehlen
        doc_count = 0
        if options.include_documents:
            result = await db.execute(
                select(func.count(Document.id))
                .where(
                    and_(
                        Document.company_id == options.company_id,
                        Document.created_at >= datetime.combine(options.start_date, datetime.min.time()),
                        Document.created_at <= datetime.combine(options.end_date, datetime.max.time()),
                        Document.is_archived == True,
                    )
                )
            )
            doc_count = result.scalar() or 0

        # Archive zaehlen
        archive_count = 0
        if options.include_archives:
            result = await db.execute(
                select(func.count(DocumentArchive.id))
                .where(
                    and_(
                        DocumentArchive.company_id == options.company_id,
                        DocumentArchive.archived_at >= datetime.combine(options.start_date, datetime.min.time()),
                        DocumentArchive.archived_at <= datetime.combine(options.end_date, datetime.max.time()),
                    )
                )
            )
            archive_count = result.scalar() or 0

        return {
            "zeitraum": {
                "von": options.start_date.isoformat(),
                "bis": options.end_date.isoformat(),
            },
            "anzahl": {
                "dokumente": doc_count,
                "archive": archive_count,
            },
            "tabellen": [
                DOCUMENT_TABLE.name if options.include_documents else None,
                ARCHIVE_TABLE.name if options.include_archives else None,
                INVOICE_TABLE.name if options.include_invoices else None,
                CONTRACT_TABLE.name if options.include_contracts else None,
            ],
            "geschaetzte_groesse_kb": (doc_count * 0.5 + archive_count * 0.3) * 10,
        }

    # =========================================================================
    # EXPORT-METHODEN
    # =========================================================================

    async def _export_documents(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
    ) -> str:
        """Exportiert Dokumente als CSV."""
        result = await db.execute(
            select(Document)
            .where(
                and_(
                    Document.company_id == options.company_id,
                    Document.created_at >= datetime.combine(options.start_date, datetime.min.time()),
                    Document.created_at <= datetime.combine(options.end_date, datetime.max.time()),
                    Document.is_archived == True,
                )
            )
            .order_by(Document.created_at)
        )
        documents = result.scalars().all()

        if not documents:
            return ""

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow([col.name for col in DOCUMENT_TABLE.columns])

        # Daten
        for doc in documents:
            writer.writerow([
                str(doc.id),
                doc.original_filename or doc.filename,
                doc.mime_type or "",
                doc.file_size or 0,
                self._format_datetime(doc.created_at),
                doc.status or "",
                doc.checksum or "",
            ])

        return output.getvalue()

    async def _export_archives(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
    ) -> str:
        """Exportiert Archiv-Informationen als CSV."""
        result = await db.execute(
            select(DocumentArchive)
            .where(
                and_(
                    DocumentArchive.company_id == options.company_id,
                    DocumentArchive.archived_at >= datetime.combine(options.start_date, datetime.min.time()),
                    DocumentArchive.archived_at <= datetime.combine(options.end_date, datetime.max.time()),
                )
            )
            .order_by(DocumentArchive.archived_at)
        )
        archives = result.scalars().all()

        if not archives:
            return ""

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow([col.name for col in ARCHIVE_TABLE.columns])

        # Daten
        for archive in archives:
            writer.writerow([
                str(archive.id),
                str(archive.document_id),
                archive.content_hash,
                archive.hash_algorithm,
                self._format_datetime(archive.signature_timestamp),
                self._translate_category(archive.retention_category),
                archive.retention_years,
                self._format_date(archive.retention_expires_at),
                1 if archive.is_verified else 0,
                self._format_datetime(archive.archived_at),
            ])

        return output.getvalue()

    async def _export_invoices(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
    ) -> str:
        """Exportiert Rechnungsdaten als CSV."""
        # Nur archivierte Dokumente mit Rechnungsdaten
        result = await db.execute(
            select(Document)
            .where(
                and_(
                    Document.company_id == options.company_id,
                    Document.created_at >= datetime.combine(options.start_date, datetime.min.time()),
                    Document.created_at <= datetime.combine(options.end_date, datetime.max.time()),
                    Document.is_archived == True,
                    Document.extracted_data.isnot(None),
                )
            )
            .order_by(Document.created_at)
        )
        documents = result.scalars().all()

        invoices = []
        for doc in documents:
            extracted = doc.extracted_data or {}
            invoice_data = extracted.get("invoice", {})
            if invoice_data:
                invoices.append((doc, invoice_data))

        if not invoices:
            return ""

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow([col.name for col in INVOICE_TABLE.columns])

        # Daten
        for doc, invoice in invoices:
            sender = invoice.get("sender", {}) or {}
            recipient = invoice.get("recipient", {}) or {}
            bank = invoice.get("sender_bank", {}) or {}

            writer.writerow([
                str(doc.id),
                invoice.get("invoice_number", ""),
                self._format_date_str(invoice.get("invoice_date")),
                self._format_date_str(invoice.get("due_date")),
                sender.get("company", ""),
                sender.get("street", ""),
                sender.get("zip_code", ""),
                sender.get("city", ""),
                recipient.get("company", ""),
                invoice.get("sender_vat_id", ""),
                bank.get("iban", ""),
                self._format_decimal(invoice.get("net_amount")),
                self._format_decimal(invoice.get("vat_rate")),
                self._format_decimal(invoice.get("vat_amount")),
                self._format_decimal(invoice.get("gross_amount")),
                invoice.get("currency", "EUR"),
            ])

        return output.getvalue()

    async def _export_contracts(
        self,
        db: AsyncSession,
        options: GDPdUExportOptions,
    ) -> str:
        """Exportiert Vertragsdaten als CSV."""
        result = await db.execute(
            select(Document)
            .where(
                and_(
                    Document.company_id == options.company_id,
                    Document.created_at >= datetime.combine(options.start_date, datetime.min.time()),
                    Document.created_at <= datetime.combine(options.end_date, datetime.max.time()),
                    Document.is_archived == True,
                    Document.extracted_data.isnot(None),
                )
            )
            .order_by(Document.created_at)
        )
        documents = result.scalars().all()

        contracts = []
        for doc in documents:
            extracted = doc.extracted_data or {}
            contract_data = extracted.get("contract", {})
            if contract_data:
                contracts.append((doc, contract_data))

        if not contracts:
            return ""

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

        # Header
        writer.writerow([col.name for col in CONTRACT_TABLE.columns])

        # Daten
        for doc, contract in contracts:
            party_a = contract.get("party_a", {}) or {}
            party_b = contract.get("party_b", {}) or {}

            writer.writerow([
                str(doc.id),
                contract.get("contract_number", ""),
                self._format_date_str(contract.get("contract_date")),
                self._format_date_str(contract.get("start_date")),
                self._format_date_str(contract.get("end_date")),
                party_a.get("company", ""),
                party_b.get("company", ""),
                self._format_decimal(contract.get("contract_value")),
                contract.get("contract_type", ""),
            ])

        return output.getvalue()

    # =========================================================================
    # XML-GENERIERUNG
    # =========================================================================

    def _generate_index_xml(
        self,
        company: Company,
        options: GDPdUExportOptions,
    ) -> str:
        """Generiert die index.xml Datei nach GDPdU-Standard."""
        root = ET.Element("DataSet")

        # Version
        version = ET.SubElement(root, "Version")
        version.text = GDPDU_VERSION

        # DataSupplier (Datenlieferant)
        supplier = ET.SubElement(root, "DataSupplier")
        name = ET.SubElement(supplier, "Name")
        name.text = company.name
        if company.address:
            location = ET.SubElement(supplier, "Location")
            location.text = company.address
        if options.comment:
            comment = ET.SubElement(supplier, "Comment")
            comment.text = options.comment

        # Media (Datentraeger)
        media = ET.SubElement(root, "Media")
        media_name = ET.SubElement(media, "Name")
        media_name.text = f"GDPdU-Export {options.start_date.strftime('%Y-%m-%d')} bis {options.end_date.strftime('%Y-%m-%d')}"

        # Tabellen hinzufuegen
        for table in self._tables:
            self._add_table_element(media, table, options)

        # XML formatieren
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml(indent="  ", encoding="UTF-8")

        # XML-Deklaration mit DTD-Referenz
        xml_header = f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE DataSet SYSTEM "{GDPDU_DTD_VERSION}">\n'
        xml_body = pretty_xml.decode('UTF-8').split('?>', 1)[1].strip()

        return xml_header + xml_body

    def _add_table_element(
        self,
        media: ET.Element,
        table: GDPdUTable,
        options: GDPdUExportOptions,
    ) -> None:
        """Fuegt ein Table-Element zur index.xml hinzu."""
        table_el = ET.SubElement(media, "Table")

        # URL (Dateiname)
        url = ET.SubElement(table_el, "URL")
        url.text = table.filename

        # Name
        name = ET.SubElement(table_el, "Name")
        name.text = table.name

        # Description
        desc = ET.SubElement(table_el, "Description")
        desc.text = table.description

        # Validity (Gueltigkeitszeitraum)
        validity = ET.SubElement(table_el, "Validity")
        range_el = ET.SubElement(validity, "Range")
        from_el = ET.SubElement(range_el, "From")
        from_el.text = options.start_date.isoformat()
        to_el = ET.SubElement(range_el, "To")
        to_el.text = options.end_date.isoformat()

        # UTF8
        ET.SubElement(table_el, "UTF8")

        # DecimalSymbol (deutsches Format)
        decimal = ET.SubElement(table_el, "DecimalSymbol")
        decimal.text = ","

        # ThousandsSeparator
        thousands = ET.SubElement(table_el, "ThousandsSeparator")
        thousands.text = "."

        # VariableLength (CSV-Format)
        var_length = ET.SubElement(table_el, "VariableLength")

        column_delim = ET.SubElement(var_length, "ColumnDelimiter")
        column_delim.text = ";"

        record_delim = ET.SubElement(var_length, "RecordDelimiter")
        record_delim.text = "\\n"

        text_encap = ET.SubElement(var_length, "TextEncapsulator")
        text_encap.text = '"'

        # Spalten definieren
        for col in table.columns:
            self._add_column_element(var_length, col)

    def _add_column_element(
        self,
        parent: ET.Element,
        column: GDPdUColumn,
    ) -> None:
        """Fuegt ein VariableColumn-Element hinzu."""
        col_el = ET.SubElement(parent, "VariableColumn")

        name = ET.SubElement(col_el, "Name")
        name.text = column.name

        desc = ET.SubElement(col_el, "Description")
        desc.text = column.description

        # Datentyp
        if column.data_type == "Numeric":
            numeric = ET.SubElement(col_el, "Numeric")
            if column.accuracy is not None:
                accuracy = ET.SubElement(numeric, "Accuracy")
                accuracy.text = str(column.accuracy)
        elif column.data_type == "Date":
            date_el = ET.SubElement(col_el, "Date")
            if column.date_format:
                format_el = ET.SubElement(date_el, "Format")
                format_el.text = column.date_format
        else:  # AlphaNumeric
            ET.SubElement(col_el, "AlphaNumeric")

        # MaxLength
        if column.max_length:
            max_len = ET.SubElement(col_el, "MaxLength")
            max_len.text = str(column.max_length)

    def _generate_readme(
        self,
        company: Company,
        options: GDPdUExportOptions,
    ) -> str:
        """Generiert eine README-Datei fuer den Export."""
        readme_lines = [
            "=" * 70,
            "GDPdU-EXPORT FUER BETRIEBSPRUEFUNG",
            "=" * 70,
            "",
            f"Firma:           {company.name}",
            f"Export-Zeitraum: {options.start_date.strftime('%d.%m.%Y')} bis {options.end_date.strftime('%d.%m.%Y')}",
            f"Erstellt am:     {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
            "",
            "-" * 70,
            "INHALT",
            "-" * 70,
            "",
            "index.xml           - GDPdU-Strukturbeschreibung",
            f"{GDPDU_DTD_VERSION}  - Dokumenttyp-Definition",
            "",
        ]

        for table in self._tables:
            readme_lines.append(f"{table.filename:20} - {table.description}")

        readme_lines.extend([
            "",
            "-" * 70,
            "RECHTLICHE GRUNDLAGEN",
            "-" * 70,
            "",
            "Dieser Export entspricht den Grundsaetzen zum Datenzugriff und zur",
            "Pruefbarkeit digitaler Unterlagen (GDPdU) gemaess BMF-Schreiben.",
            "",
            "Gesetzliche Basis:",
            "  - §147 AO (Abgabenordnung)",
            "  - §257 HGB (Handelsgesetzbuch)",
            "  - §14b UStG (Umsatzsteuergesetz)",
            "",
            "-" * 70,
            "HINWEISE ZUR VERWENDUNG",
            "-" * 70,
            "",
            "1. Die CSV-Dateien verwenden Semikolon (;) als Trennzeichen",
            "2. Dezimalzahlen verwenden Komma als Dezimaltrennzeichen",
            "3. Datumsformat: YYYY-MM-DD oder YYYY-MM-DD HH:MM:SS",
            "4. Alle Texte sind UTF-8 kodiert",
            "",
            "-" * 70,
            "GoBD-KONFORMITAET",
            "-" * 70,
            "",
            "Die exportierten Daten erfuellen die GoBD-Kriterien:",
            "  - Nachvollziehbarkeit: Vollstaendiger Audit-Trail",
            "  - Nachpruefbarkeit: Alle Daten sind strukturiert und validiert",
            "  - Unveraenderbarkeit: SHA-256 Hash-Signaturen fuer Archive",
            "  - Vollstaendigkeit: Alle relevanten Daten enthalten",
            "  - Ordnung: Kategorisierung nach Dokumenttyp",
            "",
            "=" * 70,
            "ABLAGE-SYSTEM - Feinpoliert und durchdacht",
            "=" * 70,
        ])

        return "\n".join(readme_lines)

    # =========================================================================
    # HILFSMETHODEN
    # =========================================================================

    async def _get_company(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> Optional[Company]:
        """Holt Firmeninformationen aus der Datenbank."""
        result = await db.execute(
            select(Company).where(Company.id == company_id)
        )
        return result.scalar_one_or_none()

    def _format_datetime(self, dt: Optional[datetime]) -> str:
        """Formatiert ein DateTime-Objekt."""
        if not dt:
            return ""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _format_date(self, d: Optional[date]) -> str:
        """Formatiert ein Date-Objekt."""
        if not d:
            return ""
        return d.strftime("%Y-%m-%d")

    def _format_date_str(self, date_str: Optional[str]) -> str:
        """Formatiert einen Datums-String (falls vorhanden)."""
        if not date_str:
            return ""
        # Versuchen, das Datum zu parsen und zu formatieren
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            return date_str
        except (ValueError, AttributeError):
            return str(date_str) if date_str else ""

    def _format_decimal(self, value: Optional[float | Decimal | str]) -> str:
        """Formatiert einen Dezimalwert."""
        if value is None:
            return ""
        try:
            decimal_value = Decimal(str(value))
            # Deutsches Format: Komma als Dezimaltrennzeichen
            return str(decimal_value).replace(".", ",")
        except (ValueError, TypeError):
            return ""

    def _translate_category(self, category: str) -> str:
        """Uebersetzt Kategorie-Keys in deutsche Bezeichnungen."""
        translations = {
            RetentionCategory.INVOICE.value: "Rechnungen",
            RetentionCategory.CONTRACT.value: "Vertraege",
            RetentionCategory.CORRESPONDENCE.value: "Geschaeftsbriefe",
            RetentionCategory.BOOKING_DOCUMENT.value: "Buchungsbelege",
            RetentionCategory.ANNUAL_REPORT.value: "Jahresabschluesse",
            RetentionCategory.TAX_DOCUMENT.value: "Steuerbelege",
            RetentionCategory.EMPLOYEE_DOCUMENT.value: "Personalakten",
            RetentionCategory.OTHER.value: "Sonstiges",
        }
        return translations.get(category, category)


# Singleton-Instanz
gdpdu_export_service = GDPdUExportService()
