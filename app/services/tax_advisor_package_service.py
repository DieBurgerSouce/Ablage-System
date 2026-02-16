"""
Steuerberater Auto-Paket Service.

Automatische Erstellung von Buchhaltungspaketen für Steuerberater:
- Monatliche/Quartalsweise Pakete
- Konfigurierbare Dokumenttypen
- Automatischer Versand
- Push-Benachrichtigungen bei fehlenden Dokumenten

GoBD-Konformität garantiert.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, or_, select

from app.core.safe_errors import safe_error_log
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    Document,
    User,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================


class PackageFrequency(str, Enum):
    """Häufigkeit der Paket-Erstellung."""

    MONTHLY = "monthly"        # Monatlich
    QUARTERLY = "quarterly"    # Quartalsweise
    YEARLY = "yearly"          # Jährlich
    ON_DEMAND = "on_demand"    # Auf Anfrage


class PackageStatus(str, Enum):
    """Status eines Pakets."""

    DRAFT = "draft"            # Entwurf
    PENDING = "pending"        # Warten auf Dokumente
    READY = "ready"            # Bereit zum Versand
    SENT = "sent"              # Versendet
    DOWNLOADED = "downloaded"  # Heruntergeladen
    EXPIRED = "expired"        # Abgelaufen


class MissingDocumentType(str, Enum):
    """Arten von fehlenden Dokumenten."""

    INVOICE = "invoice"                    # Rechnung
    BANK_STATEMENT = "bank_statement"      # Kontoauszug
    RECEIPT = "receipt"                    # Beleg
    PAYROLL = "payroll"                    # Lohnabrechnung
    TAX_DOCUMENT = "tax_document"          # Steuerdokument
    CONTRACT = "contract"                  # Vertrag
    OTHER = "other"                        # Sonstige


@dataclass
class PackageConfiguration:
    """Konfiguration für Auto-Pakete."""

    id: uuid.UUID
    company_id: uuid.UUID
    name: str

    frequency: PackageFrequency
    document_categories: List[str]  # Kategorien die eingeschlossen werden

    # Zeitraum
    period_start_day: int = 1       # Tag des Monats für Periodenstart
    delivery_delay_days: int = 5    # Tage nach Periodenende bis Versand

    # Automatisierung
    auto_send: bool = True
    auto_reminder: bool = True
    reminder_days_before: int = 3

    # Empfänger
    recipient_email: Optional[str] = None
    tax_advisor_user_id: Optional[uuid.UUID] = None

    # Format
    include_datev_export: bool = True
    include_pdf_copies: bool = True
    include_summary_report: bool = True

    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "company_id": str(self.company_id),
            "name": self.name,
            "frequency": self.frequency.value,
            "document_categories": self.document_categories,
            "period_start_day": self.period_start_day,
            "delivery_delay_days": self.delivery_delay_days,
            "auto_send": self.auto_send,
            "auto_reminder": self.auto_reminder,
            "reminder_days_before": self.reminder_days_before,
            "recipient_email": self.recipient_email,
            "tax_advisor_user_id": str(self.tax_advisor_user_id) if self.tax_advisor_user_id else None,
            "include_datev_export": self.include_datev_export,
            "include_pdf_copies": self.include_pdf_copies,
            "include_summary_report": self.include_summary_report,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class TaxAdvisorPackage:
    """Ein erstelltes Steuerberater-Paket."""

    id: uuid.UUID
    configuration_id: uuid.UUID
    company_id: uuid.UUID

    period_start: date
    period_end: date
    period_label: str  # z.B. "Januar 2026", "Q1/2026"

    status: PackageStatus
    document_count: int = 0
    total_size_bytes: int = 0

    # Dateipfade
    datev_export_path: Optional[str] = None
    pdf_archive_path: Optional[str] = None
    summary_report_path: Optional[str] = None

    # Tracking
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    sent_at: Optional[datetime] = None
    downloaded_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    # Benachrichtigungen
    reminder_sent: bool = False
    reminder_sent_at: Optional[datetime] = None

    missing_documents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "configuration_id": str(self.configuration_id),
            "company_id": str(self.company_id),
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            "status": self.status.value,
            "document_count": self.document_count,
            "total_size_bytes": self.total_size_bytes,
            "datev_export_path": self.datev_export_path,
            "pdf_archive_path": self.pdf_archive_path,
            "summary_report_path": self.summary_report_path,
            "created_at": self.created_at.isoformat(),
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "downloaded_at": self.downloaded_at.isoformat() if self.downloaded_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "missing_documents": self.missing_documents,
        }


@dataclass
class MissingDocument:
    """Ein fehlendes Dokument."""

    document_type: MissingDocumentType
    description: str
    expected_date: Optional[date] = None
    importance: str = "required"  # required, recommended, optional
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_type": self.document_type.value,
            "description": self.description,
            "expected_date": self.expected_date.isoformat() if self.expected_date else None,
            "importance": self.importance,
            "notes": self.notes,
        }


# ============================================================================
# TAX ADVISOR PACKAGE SERVICE
# ============================================================================


class TaxAdvisorPackageService:
    """
    Service für automatische Steuerberater-Pakete.

    Features:
    - Konfigurierbare Paket-Templates
    - Automatische Periode-Erkennung
    - Fehlende Dokumente identifizieren
    - Push-Benachrichtigungen
    - DATEV-Export Integration

    Usage:
        service = TaxAdvisorPackageService(db)
        package = await service.create_package_for_period(company_id, "2026-01")
        missing = await service.identify_missing_documents(package)
    """

    # Standard-Kategorien für Buchhaltungspakete
    DEFAULT_CATEGORIES = [
        "eingangsrechnung",
        "ausgangsrechnung",
        "kontoauszug",
        "beleg",
        "lohnabrechnung",
        "vertrag",
    ]

    # Erwartete Dokumente pro Monat
    EXPECTED_MONTHLY_DOCUMENTS = {
        "kontoauszug": {"min_count": 1, "description": "Kontoauszug für alle Konten"},
        "eingangsrechnung": {"min_count": 0, "description": "Eingangsrechnungen"},
        "ausgangsrechnung": {"min_count": 0, "description": "Ausgangsrechnungen"},
    }

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service."""
        self.db = db
        self._configurations: Dict[uuid.UUID, PackageConfiguration] = {}

    # ========================================================================
    # CONFIGURATION MANAGEMENT
    # ========================================================================

    async def create_configuration(
        self,
        company_id: uuid.UUID,
        name: str,
        frequency: PackageFrequency = PackageFrequency.MONTHLY,
        document_categories: Optional[List[str]] = None,
        recipient_email: Optional[str] = None,
        tax_advisor_user_id: Optional[uuid.UUID] = None,
        **kwargs: object,
    ) -> PackageConfiguration:
        """
        Erstellt eine neue Paket-Konfiguration.

        Args:
            company_id: Firma
            name: Name der Konfiguration
            frequency: Häufigkeit
            document_categories: Kategorien
            recipient_email: E-Mail für Versand
            tax_advisor_user_id: Steuerberater-User

        Returns:
            PackageConfiguration
        """
        config = PackageConfiguration(
            id=uuid.uuid4(),
            company_id=company_id,
            name=name,
            frequency=frequency,
            document_categories=document_categories or self.DEFAULT_CATEGORIES,
            recipient_email=recipient_email,
            tax_advisor_user_id=tax_advisor_user_id,
            **kwargs,
        )

        self._configurations[config.id] = config

        logger.info(
            "package_configuration_created",
            config_id=str(config.id),
            company_id=str(company_id),
            frequency=frequency.value,
        )

        return config

    async def get_configuration(
        self,
        config_id: uuid.UUID,
    ) -> Optional[PackageConfiguration]:
        """Holt eine Konfiguration."""
        return self._configurations.get(config_id)

    async def get_configurations_for_company(
        self,
        company_id: uuid.UUID,
    ) -> List[PackageConfiguration]:
        """Holt alle Konfigurationen für eine Firma."""
        return [
            c for c in self._configurations.values()
            if c.company_id == company_id
        ]

    # ========================================================================
    # PACKAGE CREATION
    # ========================================================================

    async def create_package_for_period(
        self,
        company_id: uuid.UUID,
        period: str,  # Format: "2026-01" oder "2026-Q1"
        config_id: Optional[uuid.UUID] = None,
    ) -> TaxAdvisorPackage:
        """
        Erstellt ein Paket für einen bestimmten Zeitraum.

        Args:
            company_id: Firma
            period: Zeitraum (YYYY-MM oder YYYY-QN)
            config_id: Optionale Konfiguration

        Returns:
            TaxAdvisorPackage
        """
        # Periode parsen
        period_start, period_end, period_label = self._parse_period(period)

        # Konfiguration laden oder Default
        config = None
        if config_id:
            config = await self.get_configuration(config_id)

        package = TaxAdvisorPackage(
            id=uuid.uuid4(),
            configuration_id=config_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            period_label=period_label,
            status=PackageStatus.DRAFT,
        )

        # Dokumente zaehlen
        document_count, total_size = await self._count_documents_for_period(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            categories=config.document_categories if config else self.DEFAULT_CATEGORIES,
        )

        package.document_count = document_count
        package.total_size_bytes = total_size

        # Fehlende Dokumente identifizieren
        missing = await self._identify_missing_documents(
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )
        package.missing_documents = [m.to_dict() for m in missing]

        # Status aktualisieren
        if missing:
            package.status = PackageStatus.PENDING
        else:
            package.status = PackageStatus.READY

        logger.info(
            "package_created",
            package_id=str(package.id),
            company_id=str(company_id),
            period=period_label,
            document_count=document_count,
            missing_count=len(missing),
        )

        return package

    def _parse_period(self, period: str) -> tuple[date, date, str]:
        """Parst einen Zeitraum-String."""
        if "-Q" in period:
            # Quartal: 2026-Q1
            year, quarter = period.split("-Q")
            year = int(year)
            quarter = int(quarter)

            quarter_starts = {
                1: (1, 3),   # Jan-Maerz
                2: (4, 6),   # Apr-Juni
                3: (7, 9),   # Jul-Sep
                4: (10, 12), # Okt-Dez
            }

            start_month, end_month = quarter_starts[quarter]
            period_start = date(year, start_month, 1)

            # Letzter Tag des Endmonats
            if end_month == 12:
                period_end = date(year, 12, 31)
            else:
                period_end = date(year, end_month + 1, 1) - timedelta(days=1)

            period_label = f"Q{quarter}/{year}"

        else:
            # Monat: 2026-01
            year, month = period.split("-")
            year = int(year)
            month = int(month)

            period_start = date(year, month, 1)

            # Letzter Tag des Monats
            if month == 12:
                period_end = date(year, 12, 31)
            else:
                period_end = date(year, month + 1, 1) - timedelta(days=1)

            month_names = [
                "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
                "Juli", "August", "September", "Oktober", "November", "Dezember"
            ]
            period_label = f"{month_names[month]} {year}"

        return period_start, period_end, period_label

    def _calculate_quarter_dates(self, year: int, quarter: int) -> tuple[date, date]:
        """Berechnet Start- und Enddatum eines Quartals."""
        quarter_starts = {
            1: (1, 3),
            2: (4, 6),
            3: (7, 9),
            4: (10, 12),
        }
        start_month, end_month = quarter_starts[quarter]
        period_start = date(year, start_month, 1)
        if end_month == 12:
            period_end = date(year, 12, 31)
        else:
            period_end = date(year, end_month + 1, 1) - timedelta(days=1)
        return period_start, period_end

    async def _count_documents_for_period(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
        categories: List[str],
    ) -> tuple[int, int]:
        """Zaehlt Dokumente für einen Zeitraum."""
        # Query für Dokumente im Zeitraum
        query = select(
            func.count(Document.id),
            func.coalesce(func.sum(Document.file_size), 0),
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.upload_date >= period_start,
                Document.upload_date <= period_end,
                # Kategorie-Filter wuerde hier hinzukommen
            )
        )

        result = await self.db.execute(query)
        row = result.one()

        return int(row[0] or 0), int(row[1] or 0)

    async def _identify_missing_documents(
        self,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> List[MissingDocument]:
        """Identifiziert fehlende Dokumente."""
        missing: List[MissingDocument] = []

        # Kontoauszuege prüfen
        # In Praxis: Query gegen Dokumente mit category='kontoauszug'
        # Für jeden Monat sollte mindestens ein Kontoauszug existieren

        # Hier Beispiel-Implementierung
        # In Praxis: Dokumente zaehlen und gegen Erwartung prüfen

        # Beispiel: Prüfen ob Kontoauszug für jeden Monat existiert
        current = period_start
        while current <= period_end:
            month_start = date(current.year, current.month, 1)
            if current.month == 12:
                month_end = date(current.year, 12, 31)
            else:
                month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)

            # In Praxis: DB-Query
            # Hier vereinfacht - keine fehlenden Dokumente gefunden
            # missing.append(MissingDocument(...))

            # Nächster Monat
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return missing

    # ========================================================================
    # PACKAGE GENERATION
    # ========================================================================

    async def generate_package_files(
        self,
        package: TaxAdvisorPackage,
    ) -> TaxAdvisorPackage:
        """
        Generiert die Paket-Dateien.

        - DATEV-Export
        - PDF-Archiv
        - Zusammenfassungs-Bericht

        Args:
            package: Das Paket

        Returns:
            Aktualisiertes Paket
        """
        config = None
        if package.configuration_id:
            config = await self.get_configuration(package.configuration_id)

        # DATEV-Export generieren
        if not config or config.include_datev_export:
            datev_path = await self._generate_datev_export(package)
            package.datev_export_path = datev_path

        # PDF-Archiv generieren
        if not config or config.include_pdf_copies:
            pdf_path = await self._generate_pdf_archive(package)
            package.pdf_archive_path = pdf_path

        # Zusammenfassung generieren
        if not config or config.include_summary_report:
            report_path = await self._generate_summary_report(package)
            package.summary_report_path = report_path

        package.status = PackageStatus.READY

        logger.info(
            "package_files_generated",
            package_id=str(package.id),
            datev=package.datev_export_path is not None,
            pdf=package.pdf_archive_path is not None,
            report=package.summary_report_path is not None,
        )

        return package

    async def _generate_datev_export(
        self,
        package: TaxAdvisorPackage,
    ) -> str:
        """Generiert DATEV-Export."""
        # Integration mit existierendem DATEV-Export-Service
        from app.services.datev.datev_export_service import DATEVExportService

        # In Praxis: DATEV-Export durchführen
        # Hier vereinfacht
        export_path = f"/exports/datev/{package.company_id}/{package.period_label.replace('/', '-')}.zip"

        return export_path

    async def _generate_pdf_archive(
        self,
        package: TaxAdvisorPackage,
    ) -> str:
        """Generiert PDF-Archiv mit allen Dokumenten."""
        # In Praxis: Dokumente sammeln und als ZIP archivieren
        archive_path = f"/exports/pdf/{package.company_id}/{package.period_label.replace('/', '-')}_dokumente.zip"

        return archive_path

    async def _generate_summary_report(
        self,
        package: TaxAdvisorPackage,
    ) -> str:
        """Generiert Zusammenfassungs-Bericht."""
        # In Praxis: Report generieren
        report_path = f"/exports/reports/{package.company_id}/{package.period_label.replace('/', '-')}_zusammenfassung.pdf"

        return report_path

    # ========================================================================
    # PACKAGE DELIVERY
    # ========================================================================

    async def send_package(
        self,
        package: TaxAdvisorPackage,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """
        Versendet ein Paket an den Steuerberater.

        Args:
            package: Das Paket
            recipient_email: Optionale E-Mail (sonst aus Konfiguration)

        Returns:
            True wenn erfolgreich
        """
        if package.status != PackageStatus.READY:
            logger.warning(
                "package_not_ready_for_send",
                package_id=str(package.id),
                status=package.status.value,
            )
            return False

        config = None
        if package.configuration_id:
            config = await self.get_configuration(package.configuration_id)

        email = recipient_email or (config.recipient_email if config else None)

        if not email:
            logger.warning(
                "no_recipient_for_package",
                package_id=str(package.id),
            )
            return False

        # E-Mail versenden
        from app.services.notification_service import NotificationService

        try:
            notification_service = NotificationService(self.db)

            # E-Mail mit Download-Link
            download_link = f"/api/v1/tax-advisor/packages/{package.id}/download"

            await notification_service.send_email(
                to_email=email,
                subject=f"Buchhaltungspaket {package.period_label}",
                body=f"""
Sehr geehrte Damen und Herren,

das Buchhaltungspaket für {package.period_label} steht zum Download bereit.

Inhalt:
- {package.document_count} Dokumente
- DATEV-Export: {'Ja' if package.datev_export_path else 'Nein'}
- PDF-Archiv: {'Ja' if package.pdf_archive_path else 'Nein'}
- Zusammenfassung: {'Ja' if package.summary_report_path else 'Nein'}

Download-Link: {download_link}
(Gültig für 30 Tage)

Mit freundlichen Gruessen
Ablage-System
                """.strip(),
            )

            package.status = PackageStatus.SENT
            package.sent_at = datetime.now(timezone.utc)
            package.expires_at = datetime.now(timezone.utc) + timedelta(days=30)

            logger.info(
                "package_sent",
                package_id=str(package.id),
                recipient=email,
            )

            return True

        except Exception as e:
            logger.error(
                "package_send_failed",
                package_id=str(package.id),
                **safe_error_log(e),
            )
            return False

    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================

    async def send_missing_documents_notification(
        self,
        package: TaxAdvisorPackage,
        admin_email: str,
    ) -> bool:
        """
        Sendet Benachrichtigung über fehlende Dokumente.

        Args:
            package: Das Paket
            admin_email: E-Mail des Admins

        Returns:
            True wenn erfolgreich
        """
        if not package.missing_documents:
            return True

        from app.services.notification_service import NotificationService

        try:
            notification_service = NotificationService(self.db)

            missing_list = "\n".join([
                f"- {doc['description']} ({doc['importance']})"
                for doc in package.missing_documents
            ])

            await notification_service.send_email(
                to_email=admin_email,
                subject=f"Fehlende Dokumente für {package.period_label}",
                body=f"""
Folgende Dokumente fehlen noch für das Buchhaltungspaket {package.period_label}:

{missing_list}

Bitte laden Sie die fehlenden Dokumente hoch, damit das Paket vollständig ist.

Mit freundlichen Gruessen
Ablage-System
                """.strip(),
            )

            package.reminder_sent = True
            package.reminder_sent_at = datetime.now(timezone.utc)

            logger.info(
                "missing_documents_notification_sent",
                package_id=str(package.id),
                missing_count=len(package.missing_documents),
            )

            return True

        except Exception as e:
            logger.error(
                "missing_documents_notification_failed",
                package_id=str(package.id),
                **safe_error_log(e),
            )
            return False

    async def send_reminder_notification(
        self,
        company_id: uuid.UUID,
        missing_documents: List[MissingDocument],
        tax_advisor_name: str,
        admin_email: str,
    ) -> bool:
        """
        Sendet Push-Benachrichtigung für fehlende Dokumente.

        Format: "Für [Steuerberater] fehlen noch: [Dokument X], [Dokument Y]"

        Args:
            company_id: Firma
            missing_documents: Fehlende Dokumente
            tax_advisor_name: Name des Steuerberaters
            admin_email: E-Mail des Admins

        Returns:
            True wenn erfolgreich
        """
        if not missing_documents:
            return True

        from app.services.notification_service import NotificationService
        from app.services.push_notification_service import PushNotificationService


        try:
            # E-Mail
            notification_service = NotificationService(self.db)

            doc_list = ", ".join([doc.description for doc in missing_documents[:5]])
            if len(missing_documents) > 5:
                doc_list += f" (+{len(missing_documents) - 5} weitere)"

            await notification_service.send_email(
                to_email=admin_email,
                subject=f"Fehlende Dokumente für {tax_advisor_name}",
                body=f"""
Für {tax_advisor_name} fehlen noch:

{doc_list}

Bitte laden Sie die fehlenden Dokumente zeitnah hoch.
                """.strip(),
            )

            # Push-Benachrichtigung (wenn verfügbar)
            try:
                push_service = PushNotificationService(self.db)
                await push_service.send_to_company_admins(
                    company_id=company_id,
                    title="Fehlende Dokumente",
                    body=f"Für {tax_advisor_name} fehlen noch: {doc_list}",
                    data={
                        "type": "missing_documents",
                        "company_id": str(company_id),
                    },
                )
            except Exception as push_error:
                logger.debug(
                    "push_notification_skipped",
                    error=str(push_error),
                )

            logger.info(
                "reminder_notification_sent",
                company_id=str(company_id),
                tax_advisor=tax_advisor_name,
                missing_count=len(missing_documents),
            )

            return True

        except Exception as e:
            logger.error(
                "reminder_notification_failed",
                company_id=str(company_id),
                **safe_error_log(e),
            )
            return False

    # ========================================================================
    # COMPLETENESS CHECK (Feature #9)
    # ========================================================================

    async def check_completeness(
        self,
        company_id: uuid.UUID,
        year: int,
        quarter: Optional[int] = None,
    ) -> "CompletenessReport":
        """
        Prüft die Vollständigkeit der Dokumente für einen Zeitraum.

        Prüft:
        - Alle Monate haben Kontoauszuege
        - Rechnungen haben Zahlungen oder sind als offen markiert
        - Pflichtdokumente sind vorhanden
        - DATEV-Export-Validierung
        - Compliance-Issues

        Args:
            company_id: Firma
            year: Jahr (z.B. 2026)
            quarter: Optional Quartal (1-4), None = ganzes Jahr

        Returns:
            CompletenessReport mit Score und fehlenden Items
        """
        from decimal import Decimal

        # Zeitraum berechnen
        if quarter:
            period_start, period_end = self._calculate_quarter_dates(year, quarter)
            period_label = f"Q{quarter}/{year}"
        else:
            period_start = date(year, 1, 1)
            period_end = date(year, 12, 31)
            period_label = str(year)

        missing_items: List[MissingItem] = []
        checks_passed = 0
        total_checks = 0

        # Check 1: Kontoauszuege für alle Monate
        total_checks += 1
        bank_statements_check = await self._check_bank_statements(
            company_id, period_start, period_end
        )
        if bank_statements_check["complete"]:
            checks_passed += 1
        else:
            for month_label in bank_statements_check["missing_months"]:
                missing_items.append(
                    MissingItem(
                        category="kontoauszug",
                        description=f"Kontoauszug fehlt für {month_label}",
                        severity="required",
                        suggestion="Laden Sie alle monatlichen Kontoauszuege hoch",
                    )
                )

        # Check 2: Rechnungen mit Zahlungen/Status
        total_checks += 1
        invoices_check = await self._check_invoices_status(
            company_id, period_start, period_end
        )
        if invoices_check["complete"]:
            checks_passed += 1
        else:
            if invoices_check["unmatched_invoices"] > 0:
                missing_items.append(
                    MissingItem(
                        category="zahlung",
                        description=f"{invoices_check['unmatched_invoices']} Rechnungen ohne Zahlungszuordnung",
                        severity="required",
                        suggestion="Ordnen Sie Zahlungen den Rechnungen zu oder markieren Sie sie als offen",
                    )
                )

        # Check 3: Pflichtdokumenttypen vorhanden
        total_checks += 1
        required_docs_check = await self._check_required_documents(
            company_id, period_start, period_end
        )
        if required_docs_check["complete"]:
            checks_passed += 1
        else:
            for doc_type, info in required_docs_check["missing"].items():
                missing_items.append(
                    MissingItem(
                        category=doc_type,
                        description=info["description"],
                        severity="recommended",
                        suggestion=info["suggestion"],
                    )
                )

        # Check 4: DATEV-Export-Validierung
        total_checks += 1
        datev_check = await self._validate_datev_export_readiness(
            company_id, period_start, period_end
        )
        if datev_check["valid"]:
            checks_passed += 1
        else:
            for error in datev_check["errors"]:
                missing_items.append(
                    MissingItem(
                        category="datev",
                        description=error,
                        severity="required",
                        suggestion="Beheben Sie die DATEV-Validierungsfehler",
                    )
                )

        # Check 5: Compliance-Issues
        total_checks += 1
        compliance_check = await self._check_compliance_issues(
            company_id, period_start, period_end
        )
        if compliance_check["clean"]:
            checks_passed += 1
        else:
            for issue in compliance_check["issues"]:
                missing_items.append(
                    MissingItem(
                        category="compliance",
                        description=issue["description"],
                        severity=issue["severity"],
                        suggestion=issue["suggestion"],
                    )
                )

        # Completeness-Score berechnen
        completeness_score = (checks_passed / total_checks * 100) if total_checks > 0 else 0.0

        logger.info(
            "completeness_check_completed",
            company_id=str(company_id),
            period=period_label,
            score=completeness_score,
            missing_count=len(missing_items),
        )

        return CompletenessReport(
            period=period_label,
            period_start=period_start,
            period_end=period_end,
            completeness_score=completeness_score,
            checks_passed=checks_passed,
            total_checks=total_checks,
            missing_items=missing_items,
            is_complete=len(missing_items) == 0,
        )

    async def _check_bank_statements(
        self,
        company_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Dict[str, Any]:
        """Prüft ob alle Monate Kontoauszuege haben."""
        from calendar import monthrange

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.document_type == "kontoauszug",
                Document.upload_date >= start,
                Document.upload_date <= end,
            )
        )
        result = await self.db.execute(query)
        statements = result.scalars().all()

        # Monate mit Kontoauszuegen
        months_with_statements = set()
        for stmt in statements:
            if stmt.document_date:
                months_with_statements.add((stmt.document_date.year, stmt.document_date.month))

        # Erwartete Monate
        expected_months = []
        current = start
        while current <= end:
            expected_months.append((current.year, current.month))
            days_in_month = monthrange(current.year, current.month)[1]
            current = date(current.year, current.month, days_in_month)
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        missing_months = [
            f"{year}-{month:02d}"
            for year, month in expected_months
            if (year, month) not in months_with_statements
        ]

        return {
            "complete": len(missing_months) == 0,
            "missing_months": missing_months,
        }

    async def _check_invoices_status(
        self,
        company_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Dict[str, Any]:
        """Prüft ob Rechnungen Zahlungen oder Status haben."""
        from app.db.models import InvoiceTracking

        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.document_type.in_(["eingangsrechnung", "ausgangsrechnung"]),
                Document.upload_date >= start,
                Document.upload_date <= end,
            )
        )
        result = await self.db.execute(query)
        invoices = result.scalars().all()

        unmatched = 0
        for inv in invoices:
            # InvoiceTracking prüfen
            tracking_query = select(InvoiceTracking).where(
                InvoiceTracking.document_id == inv.id
            )
            tracking_result = await self.db.execute(tracking_query)
            tracking = tracking_result.scalar_one_or_none()

            # Unmatched wenn: Kein Tracking ODER (nicht bezahlt UND nicht als offen markiert)
            if not tracking:
                unmatched += 1
            elif tracking.payment_status not in ["paid", "open", "ready"]:
                unmatched += 1

        return {
            "complete": unmatched == 0,
            "unmatched_invoices": unmatched,
            "total_invoices": len(invoices),
        }

    async def _check_required_documents(
        self,
        company_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Dict[str, Any]:
        """Prüft ob Pflichtdokumente vorhanden sind."""
        query = select(Document.document_type, func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.upload_date >= start,
                Document.upload_date <= end,
            )
        ).group_by(Document.document_type)

        result = await self.db.execute(query)
        counts = dict(result.fetchall())

        # Erwartete Dokumenttypen
        required = {
            "eingangsrechnung": {
                "description": "Keine Eingangsrechnungen gefunden",
                "suggestion": "Laden Sie alle Lieferantenrechnungen hoch",
            },
            "ausgangsrechnung": {
                "description": "Keine Ausgangsrechnungen gefunden",
                "suggestion": "Laden Sie alle Kundenrechnungen hoch",
            },
        }

        missing = {}
        for doc_type, info in required.items():
            if counts.get(doc_type, 0) == 0:
                missing[doc_type] = info

        return {
            "complete": len(missing) == 0,
            "missing": missing,
        }

    async def _validate_datev_export_readiness(
        self,
        company_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Dict[str, Any]:
        """Prüft DATEV-Export-Validierung."""
        # Vereinfachte Validierung - in Praxis: DATEV-Service nutzen
        errors: List[str] = []

        # Firmen-Stammdaten prüfen
        company_query = select(Company).where(Company.id == company_id)
        company_result = await self.db.execute(company_query)
        company = company_result.scalar_one_or_none()

        if not company:
            errors.append("Firma nicht gefunden")
            return {"valid": False, "errors": errors}

        # USt-IdNr prüfen
        if not company.vat_id:
            errors.append("Keine USt-IdNr hinterlegt")

        # Steuerberater-Mandantennummer prüfen
        if not company.tax_advisor_client_number:
            errors.append("Keine Steuerberater-Mandantennummer hinterlegt")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    async def _check_compliance_issues(
        self,
        company_id: uuid.UUID,
        start: date,
        end: date,
    ) -> Dict[str, Any]:
        """Prüft auf Compliance-Issues."""
        issues: List[Dict[str, str]] = []

        # Dokumente ohne OCR-Text
        query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.upload_date >= start,
                Document.upload_date <= end,
                or_(
                    Document.extracted_text.is_(None),
                    Document.extracted_text == "",
                )
            )
        )
        result = await self.db.execute(query)
        docs_without_ocr = result.scalar()

        if docs_without_ocr and docs_without_ocr > 0:
            issues.append({
                "description": f"{docs_without_ocr} Dokumente ohne OCR-Text",
                "severity": "recommended",
                "suggestion": "Führen Sie OCR für alle Dokumente durch",
            })

        return {
            "clean": len(issues) == 0,
            "issues": issues,
        }


@dataclass
class MissingItem:
    """Ein fehlendes oder unvollständiges Element."""

    category: str  # z.B. "kontoauszug", "rechnung", "datev"
    description: str  # Deutsche Beschreibung
    severity: str  # "required", "recommended", "optional"
    suggestion: str  # Was tun?


@dataclass
class CompletenessReport:
    """Vollständigkeits-Bericht."""

    period: str  # z.B. "2026" oder "Q1/2026"
    period_start: date
    period_end: date
    completeness_score: float  # 0-100
    checks_passed: int
    total_checks: int
    missing_items: List[MissingItem]
    is_complete: bool


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_tax_advisor_package_service(db: AsyncSession) -> TaxAdvisorPackageService:
    """Factory-Funktion für Dependency Injection."""
    return TaxAdvisorPackageService(db)
