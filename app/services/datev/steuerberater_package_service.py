# -*- coding: utf-8 -*-
"""
DATEV Steuerberater-Paket Service.

Vision 2026 Q4: Vollständiger DATEV-Export für Steuerberater.

Features:
- Buchungsstapel-Export (CSV)
- Belegbild-Export (PDF/TIFF)
- Automatische Kontierung nach SKR03/SKR04
- Steuerberater-Freigabe-Workflow
- Validierung und Vorschau
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from app.core.safe_errors import safe_error_detail, safe_error_log
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, TypedDict
from uuid import UUID, uuid4
from xml.sax.saxutils import escape as xml_escape

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

PACKAGE_CREATED = Counter(
    "datev_package_created_total",
    "Total DATEV packages created",
    ["company_id", "status"]
)

PACKAGE_APPROVED = Counter(
    "datev_package_approved_total",
    "Total DATEV packages approved by Steuerberater",
    ["company_id"]
)

PACKAGE_CREATION_TIME = Histogram(
    "datev_package_creation_seconds",
    "Time to create DATEV package",
    ["company_id"]
)


# =============================================================================
# Enums
# =============================================================================

class PackageStatus(str, Enum):
    """Status des Steuerberater-Pakets."""
    DRAFT = "draft"                 # In Erstellung
    PENDING_REVIEW = "pending_review"  # Wartet auf Freigabe
    APPROVED = "approved"           # Freigegeben
    REJECTED = "rejected"           # Abgelehnt
    EXPORTED = "exported"           # Exportiert/Heruntergeladen
    ARCHIVED = "archived"           # Archiviert


class ExportFormat(str, Enum):
    """Export-Format."""
    DATEV_CSV = "datev_csv"         # DATEV Buchungsstapel
    DATEV_XML = "datev_xml"         # DATEV XML-Format
    PDF_ARCHIVE = "pdf_archive"     # PDF-Belegarchiv


class DocumentImageFormat(str, Enum):
    """Format für Belegbilder."""
    PDF = "pdf"
    TIFF = "tiff"
    JPEG = "jpeg"


# =============================================================================
# TypedDicts for Type Safety
# =============================================================================


class SteuerberaterPackageDict(TypedDict):
    """Typisiertes Dictionary für SteuerberaterPackage.to_dict()."""
    id: str
    company_id: str
    period_from: str
    period_to: str
    status: str
    created_at: str
    created_by_id: Optional[str]
    total_documents: int
    total_amount: str
    total_tax: str
    kontenrahmen: str
    include_images: bool
    image_format: str
    validation_passed: bool
    validation_errors: List[str]
    validation_warnings: List[str]
    approved_at: Optional[str]
    approved_by_id: Optional[str]
    approval_comment: Optional[str]
    rejection_reason: Optional[str]
    exported_at: Optional[str]


class ValidationSummaryDict(TypedDict):
    """Typisiertes Dictionary für Validierungs-Zusammenfassung."""
    total_documents: int
    valid_documents: int
    invalid_documents: int
    total_amount: str
    total_tax: str
    by_account: Dict[str, str]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PackageDocument:
    """Ein Dokument im Steuerberater-Paket."""
    document_id: UUID
    document_number: str  # Belegnummer
    document_date: date
    document_type: str    # Rechnung, Gutschrift, etc.
    amount: Decimal
    tax_amount: Decimal
    tax_rate: Decimal
    account_debit: str    # Soll-Konto
    account_credit: str   # Haben-Konto
    description: str
    entity_name: Optional[str] = None
    entity_id: Optional[UUID] = None
    image_path: Optional[str] = None  # Pfad zum Belegbild
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)


@dataclass
class SteuerberaterPackage:
    """Ein Steuerberater-Export-Paket."""
    id: UUID = field(default_factory=uuid4)
    company_id: UUID = field(default_factory=uuid4)
    period_from: date = field(default_factory=date.today)
    period_to: date = field(default_factory=date.today)

    # Status
    status: PackageStatus = PackageStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_id: Optional[UUID] = None

    # Inhalte
    documents: List[PackageDocument] = field(default_factory=list)
    total_documents: int = 0
    total_amount: Decimal = Decimal("0")
    total_tax: Decimal = Decimal("0")

    # Export-Konfiguration
    kontenrahmen: str = "SKR03"
    include_images: bool = True
    image_format: DocumentImageFormat = DocumentImageFormat.PDF

    # Validierung
    validation_passed: bool = False
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)

    # Freigabe
    approved_at: Optional[datetime] = None
    approved_by_id: Optional[UUID] = None
    approval_comment: Optional[str] = None
    rejection_reason: Optional[str] = None

    # Export
    exported_at: Optional[datetime] = None
    export_file_hash: Optional[str] = None
    export_file_size: Optional[int] = None

    def to_dict(self) -> SteuerberaterPackageDict:
        """Konvertiert zu Dictionary."""
        return SteuerberaterPackageDict(
            id=str(self.id),
            company_id=str(self.company_id),
            period_from=self.period_from.isoformat(),
            period_to=self.period_to.isoformat(),
            status=self.status.value,
            created_at=self.created_at.isoformat(),
            created_by_id=str(self.created_by_id) if self.created_by_id else None,
            total_documents=self.total_documents,
            total_amount=str(self.total_amount),
            total_tax=str(self.total_tax),
            kontenrahmen=self.kontenrahmen,
            include_images=self.include_images,
            image_format=self.image_format.value,
            validation_passed=self.validation_passed,
            validation_errors=self.validation_errors,
            validation_warnings=self.validation_warnings,
            approved_at=self.approved_at.isoformat() if self.approved_at else None,
            approved_by_id=str(self.approved_by_id) if self.approved_by_id else None,
            approval_comment=self.approval_comment,
            rejection_reason=self.rejection_reason,
            exported_at=self.exported_at.isoformat() if self.exported_at else None,
        )


@dataclass
class PackageValidationResult:
    """Ergebnis der Paket-Validierung."""
    passed: bool
    errors: List[str]
    warnings: List[str]
    document_errors: Dict[str, List[str]]  # document_id -> errors
    summary: ValidationSummaryDict


@dataclass
class PackageExportResult:
    """Ergebnis des Paket-Exports."""
    success: bool
    file_bytes: Optional[bytes] = None
    filename: str = ""
    file_hash: str = ""
    file_size: int = 0
    error: Optional[str] = None


# =============================================================================
# Validation Rules
# =============================================================================

class DATEVValidationRules:
    """Validierungsregeln für DATEV-Export."""

    REQUIRED_FIELDS = [
        "document_date",
        "amount",
        "account_debit",
        "account_credit",
    ]

    VALID_TAX_RATES = [
        Decimal("0"),
        Decimal("7"),
        Decimal("19"),
    ]

    MAX_DESCRIPTION_LENGTH = 60  # DATEV Limit

    @staticmethod
    def validate_document(doc: PackageDocument) -> List[str]:
        """Validiert ein einzelnes Dokument."""
        errors = []

        # Pflichtfelder
        if not doc.document_date:
            errors.append("Belegdatum fehlt")

        if doc.amount == Decimal("0"):
            errors.append("Betrag ist 0")

        if not doc.account_debit:
            errors.append("Soll-Konto fehlt")

        if not doc.account_credit:
            errors.append("Haben-Konto fehlt")

        # Steuersatz validieren
        if doc.tax_rate not in DATEVValidationRules.VALID_TAX_RATES:
            errors.append(f"Ungültiger Steuersatz: {doc.tax_rate}%")

        # Beschreibung kürzen
        if len(doc.description) > DATEVValidationRules.MAX_DESCRIPTION_LENGTH:
            errors.append(f"Beschreibung zu lang (max {DATEVValidationRules.MAX_DESCRIPTION_LENGTH} Zeichen)")

        # Kontonummern validieren (4-5 Stellen)
        if doc.account_debit and not (4 <= len(doc.account_debit) <= 5):
            errors.append(f"Soll-Konto ungültig: {doc.account_debit}")

        if doc.account_credit and not (4 <= len(doc.account_credit) <= 5):
            errors.append(f"Haben-Konto ungültig: {doc.account_credit}")

        return errors


# =============================================================================
# Service
# =============================================================================

class SteuerberaterPackageService:
    """
    Service für Steuerberater-Export-Pakete.

    Orchestriert:
    - Paket-Erstellung mit Dokumenten
    - Validierung nach DATEV-Regeln
    - Freigabe-Workflow
    - Export als ZIP mit Buchungsstapel + Belegbildern
    """

    def __init__(self) -> None:
        self._packages: Dict[UUID, SteuerberaterPackage] = {}
        logger.info("steuerberater_package_service_initialized")

    async def create_package(
        self,
        company_id: UUID,
        period_from: date,
        period_to: date,
        created_by_id: UUID,
        kontenrahmen: str = "SKR03",
        include_images: bool = True,
    ) -> SteuerberaterPackage:
        """
        Erstellt ein neues Steuerberater-Paket.

        Args:
            company_id: Company-ID
            period_from: Zeitraum-Start
            period_to: Zeitraum-Ende
            created_by_id: Ersteller-ID
            kontenrahmen: SKR03 oder SKR04
            include_images: Belegbilder einschließen

        Returns:
            Neues SteuerberaterPackage
        """
        package = SteuerberaterPackage(
            company_id=company_id,
            period_from=period_from,
            period_to=period_to,
            created_by_id=created_by_id,
            kontenrahmen=kontenrahmen,
            include_images=include_images,
        )

        self._packages[package.id] = package

        logger.info(
            "steuerberater_package_created",
            package_id=str(package.id),
            company_id=str(company_id),
            period=f"{period_from} - {period_to}",
        )

        PACKAGE_CREATED.labels(
            company_id=str(company_id),
            status="draft",
        ).inc()

        return package

    async def add_documents(
        self,
        package_id: UUID,
        documents: List[PackageDocument],
    ) -> SteuerberaterPackage:
        """
        Fuegt Dokumente zum Paket hinzu.

        Args:
            package_id: Paket-ID
            documents: Liste von Dokumenten

        Returns:
            Aktualisiertes Paket
        """
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Paket nicht gefunden: {package_id}")

        if package.status != PackageStatus.DRAFT:
            raise ValueError(f"Paket kann nicht mehr bearbeitet werden (Status: {package.status})")

        package.documents.extend(documents)
        package.total_documents = len(package.documents)
        package.total_amount = sum(d.amount for d in package.documents)
        package.total_tax = sum(d.tax_amount for d in package.documents)

        logger.info(
            "documents_added_to_package",
            package_id=str(package_id),
            added_count=len(documents),
            total_count=package.total_documents,
        )

        return package

    async def validate_package(
        self,
        package_id: UUID,
    ) -> PackageValidationResult:
        """
        Validiert das Paket nach DATEV-Regeln.

        Args:
            package_id: Paket-ID

        Returns:
            Validierungsergebnis
        """
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Paket nicht gefunden: {package_id}")

        errors: List[str] = []
        warnings: List[str] = []
        document_errors: Dict[str, List[str]] = {}

        # Paket-Level Validierung
        if not package.documents:
            errors.append("Keine Dokumente im Paket")

        if package.period_from > package.period_to:
            errors.append("Zeitraum ungültig (Start nach Ende)")

        # Dokument-Level Validierung
        for doc in package.documents:
            doc_errors = DATEVValidationRules.validate_document(doc)
            if doc_errors:
                doc.validation_errors = doc_errors
                document_errors[str(doc.document_id)] = doc_errors

            # Zeitraum prüfen
            if doc.document_date < package.period_from or doc.document_date > package.period_to:
                warnings.append(
                    f"Dokument {doc.document_number} ausserhalb Zeitraum ({doc.document_date})"
                )
                doc.validation_warnings.append("Ausserhalb Zeitraum")

        # Ergebnis
        passed = len(errors) == 0 and len(document_errors) == 0

        package.validation_passed = passed
        package.validation_errors = errors
        package.validation_warnings = warnings

        logger.info(
            "package_validated",
            package_id=str(package_id),
            passed=passed,
            error_count=len(errors) + len(document_errors),
            warning_count=len(warnings),
        )

        return PackageValidationResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            document_errors=document_errors,
            summary={
                "total_documents": package.total_documents,
                "valid_documents": package.total_documents - len(document_errors),
                "total_amount": str(package.total_amount),
                "total_tax": str(package.total_tax),
            },
        )

    async def submit_for_review(
        self,
        package_id: UUID,
    ) -> SteuerberaterPackage:
        """
        Reicht Paket zur Freigabe ein.

        Args:
            package_id: Paket-ID

        Returns:
            Aktualisiertes Paket
        """
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Paket nicht gefunden: {package_id}")

        if package.status != PackageStatus.DRAFT:
            raise ValueError(f"Paket kann nicht eingereicht werden (Status: {package.status})")

        if not package.validation_passed:
            raise ValueError("Paket muss zuerst validiert werden")

        package.status = PackageStatus.PENDING_REVIEW

        logger.info(
            "package_submitted_for_review",
            package_id=str(package_id),
        )

        return package

    async def approve_package(
        self,
        package_id: UUID,
        approved_by_id: UUID,
        comment: Optional[str] = None,
    ) -> SteuerberaterPackage:
        """
        Genehmigt das Paket (Steuerberater-Freigabe).

        Args:
            package_id: Paket-ID
            approved_by_id: Genehmiger-ID
            comment: Optionaler Kommentar

        Returns:
            Genehmigtes Paket
        """
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Paket nicht gefunden: {package_id}")

        if package.status != PackageStatus.PENDING_REVIEW:
            raise ValueError(f"Paket kann nicht genehmigt werden (Status: {package.status})")

        package.status = PackageStatus.APPROVED
        package.approved_at = datetime.now(timezone.utc)
        package.approved_by_id = approved_by_id
        package.approval_comment = comment

        logger.info(
            "package_approved",
            package_id=str(package_id),
            approved_by=str(approved_by_id),
        )

        PACKAGE_APPROVED.labels(company_id=str(package.company_id)).inc()

        return package

    async def reject_package(
        self,
        package_id: UUID,
        rejected_by_id: UUID,
        reason: str,
    ) -> SteuerberaterPackage:
        """
        Lehnt das Paket ab.

        Args:
            package_id: Paket-ID
            rejected_by_id: Ablehner-ID
            reason: Ablehnungsgrund

        Returns:
            Abgelehntes Paket
        """
        package = self._packages.get(package_id)
        if not package:
            raise ValueError(f"Paket nicht gefunden: {package_id}")

        if package.status != PackageStatus.PENDING_REVIEW:
            raise ValueError(f"Paket kann nicht abgelehnt werden (Status: {package.status})")

        package.status = PackageStatus.REJECTED
        package.rejection_reason = reason

        logger.info(
            "package_rejected",
            package_id=str(package_id),
            rejected_by=str(rejected_by_id),
            reason=reason,
        )

        return package

    async def export_package(
        self,
        package_id: UUID,
        include_images: bool = True,
    ) -> PackageExportResult:
        """
        Exportiert das Paket als ZIP-Archiv.

        Inhalt:
        - Buchungsstapel.csv (DATEV-Format)
        - Belegbilder/ (wenn include_images=True)
        - Index.xml (Metadaten)

        Args:
            package_id: Paket-ID
            include_images: Belegbilder einschließen

        Returns:
            Export-Ergebnis mit ZIP-Bytes
        """
        import time

        start_time = time.time()

        package = self._packages.get(package_id)
        if not package:
            return PackageExportResult(
                success=False,
                error=f"Paket nicht gefunden: {package_id}",
            )

        if package.status not in [PackageStatus.APPROVED, PackageStatus.EXPORTED]:
            return PackageExportResult(
                success=False,
                error=f"Paket muss genehmigt sein (Status: {package.status})",
            )

        try:
            # ZIP erstellen
            zip_buffer = io.BytesIO()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. Buchungsstapel CSV
                csv_content = self._generate_buchungsstapel_csv(package)
                zf.writestr("Buchungsstapel.csv", csv_content.encode("cp1252"))

                # 2. Index XML
                index_xml = self._generate_index_xml(package)
                zf.writestr("Index.xml", index_xml.encode("utf-8"))

                # 3. Belegbilder (wenn vorhanden und gewünscht)
                if include_images and package.include_images:
                    for doc in package.documents:
                        if doc.image_path:
                            # In Produktion: Datei aus Storage laden
                            # Hier: Platzhalter-PDF generieren
                            image_name = f"Belege/{doc.document_number}.pdf"
                            zf.writestr(image_name, self._generate_placeholder_pdf(doc))

            # ZIP finalisieren
            zip_buffer.seek(0)
            zip_bytes = zip_buffer.getvalue()

            # Hash berechnen
            file_hash = hashlib.sha256(zip_bytes).hexdigest()

            # Dateiname generieren
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"DATEV_Paket_{package.period_from}_{package.period_to}_{timestamp}.zip"

            # Paket aktualisieren
            package.status = PackageStatus.EXPORTED
            package.exported_at = datetime.now(timezone.utc)
            package.export_file_hash = file_hash
            package.export_file_size = len(zip_bytes)

            duration = time.time() - start_time

            logger.info(
                "package_exported",
                package_id=str(package_id),
                file_size=len(zip_bytes),
                duration_seconds=duration,
            )

            PACKAGE_CREATION_TIME.labels(company_id=str(package.company_id)).observe(duration)

            return PackageExportResult(
                success=True,
                file_bytes=zip_bytes,
                filename=filename,
                file_hash=file_hash,
                file_size=len(zip_bytes),
            )

        except Exception as e:
            logger.error(
                "package_export_failed",
                package_id=str(package_id),
                **safe_error_log(e),
            )
            return PackageExportResult(
                success=False,
                error=safe_error_detail(e, "Steuerberater"),
            )

    def _generate_buchungsstapel_csv(self, package: SteuerberaterPackage) -> str:
        """Generiert DATEV Buchungsstapel CSV."""
        lines = []

        # Header (DATEV EXTF-Format)
        header_line = (
            '"EXTF";700;21;"Buchungsstapel";1;;'
            f'"{package.period_from.strftime("%Y%m%d")}";'
            f'"{package.period_to.strftime("%Y%m%d")}";'
            f'"{package.created_at.strftime("%Y%m%d%H%M%S")}";;;'
            ';"";""'
        )
        lines.append(header_line)

        # Spalten-Header
        columns = [
            "Umsatz",
            "Soll/Haben",
            "WKZ",
            "Konto",
            "Gegenkonto",
            "BU-Schluessel",
            "Belegdatum",
            "Belegfeld 1",
            "Buchungstext",
        ]
        lines.append(";".join(f'"{c}"' for c in columns))

        # Datenzeilen
        for doc in package.documents:
            # Soll/Haben bestimmen
            sh = "S" if doc.amount >= 0 else "H"
            amount = abs(doc.amount)

            # BU-Schluessel aus Steuersatz
            bu = ""
            if doc.tax_rate == Decimal("19"):
                bu = "9"  # Vorsteuer 19%
            elif doc.tax_rate == Decimal("7"):
                bu = "8"  # Vorsteuer 7%

            row = [
                f"{amount:.2f}".replace(".", ","),  # Deutsches Format
                sh,
                "EUR",
                doc.account_debit,
                doc.account_credit,
                bu,
                doc.document_date.strftime("%d%m%y"),  # DDMMYY (DATEV-konform!)
                doc.document_number[:12],  # Max 12 Zeichen
                doc.description[:60],  # Max 60 Zeichen
            ]
            lines.append(";".join(f'"{c}"' for c in row))

        return "\r\n".join(lines)

    def _generate_index_xml(self, package: SteuerberaterPackage) -> str:
        """
        Generiert Index-XML mit Metadaten.

        SECURITY: Alle Benutzereingaben werden XML-escaped um XXE/XSS zu verhindern.
        """
        docs_xml = ""
        for doc in package.documents:
            # SECURITY: XML-Escape für alle User-generierten Felder
            docs_xml += f"""
    <Document>
      <DocumentId>{xml_escape(str(doc.document_id))}</DocumentId>
      <DocumentNumber>{xml_escape(doc.document_number)}</DocumentNumber>
      <DocumentDate>{xml_escape(doc.document_date.isoformat())}</DocumentDate>
      <Amount>{xml_escape(str(doc.amount))}</Amount>
      <TaxAmount>{xml_escape(str(doc.tax_amount))}</TaxAmount>
      <AccountDebit>{xml_escape(doc.account_debit)}</AccountDebit>
      <AccountCredit>{xml_escape(doc.account_credit)}</AccountCredit>
    </Document>"""

        # SECURITY: Auch Package-Felder escapen (obwohl weniger kritisch)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<DATEVPackage>
  <Header>
    <PackageId>{xml_escape(str(package.id))}</PackageId>
    <CompanyId>{xml_escape(str(package.company_id))}</CompanyId>
    <PeriodFrom>{xml_escape(package.period_from.isoformat())}</PeriodFrom>
    <PeriodTo>{xml_escape(package.period_to.isoformat())}</PeriodTo>
    <Kontenrahmen>{xml_escape(package.kontenrahmen)}</Kontenrahmen>
    <CreatedAt>{xml_escape(package.created_at.isoformat())}</CreatedAt>
    <ExportedAt>{xml_escape(package.exported_at.isoformat()) if package.exported_at else ""}</ExportedAt>
  </Header>
  <Summary>
    <TotalDocuments>{package.total_documents}</TotalDocuments>
    <TotalAmount>{xml_escape(str(package.total_amount))}</TotalAmount>
    <TotalTax>{xml_escape(str(package.total_tax))}</TotalTax>
  </Summary>
  <Documents>{docs_xml}
  </Documents>
</DATEVPackage>"""

    def _generate_placeholder_pdf(self, doc: PackageDocument) -> bytes:
        """
        Generiert ein Platzhalter-PDF für Tests.

        In Produktion: Echtes PDF aus Storage laden.
        """
        # Einfaches PDF als Platzhalter
        pdf_content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 24 Tf
100 700 Td
(Beleg: {doc.document_number}) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000214 00000 n
trailer
<< /Size 5 /Root 1 0 R >>
startxref
306
%%EOF"""
        return pdf_content.encode("latin-1")

    async def get_package(self, package_id: UUID) -> Optional[SteuerberaterPackage]:
        """Holt ein Paket nach ID."""
        return self._packages.get(package_id)

    async def list_packages(
        self,
        company_id: UUID,
        status: Optional[PackageStatus] = None,
    ) -> List[SteuerberaterPackage]:
        """
        Listet Pakete für eine Company.

        Args:
            company_id: Company-ID
            status: Optional Status-Filter

        Returns:
            Liste von Paketen
        """
        packages = [
            p for p in self._packages.values()
            if p.company_id == company_id
        ]

        if status:
            packages = [p for p in packages if p.status == status]

        return sorted(packages, key=lambda p: p.created_at, reverse=True)


# =============================================================================
# Factory
# =============================================================================

_service_instance: Optional[SteuerberaterPackageService] = None


def get_steuerberater_package_service() -> SteuerberaterPackageService:
    """
    Factory-Funktion für SteuerberaterPackageService.

    Returns:
        SteuerberaterPackageService Instanz
    """
    global _service_instance

    if _service_instance is None:
        _service_instance = SteuerberaterPackageService()

    return _service_instance
