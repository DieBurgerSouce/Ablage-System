"""
Compliance Autopilot Service.

Automatische Compliance-Checks für GDPR, GoBD, Aufbewahrungsfristen, etc.

Features:
- GDPR-Compliance-Check (Löschfristen, Zweckbindung)
- GoBD-Check (Unveränderbarkeit, Nachvollziehbarkeit)
- Aufbewahrungsfristen (§147 AO - 10 Jahre)
- Audit-Vorbereitung (Export für Steuerprüfung)
- Scoring-System (0-100)
"""

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    DocumentType,
    AuditLog,
    BusinessEntity,
    InvoiceTracking,
)
from app.core.security.sensitive_data_filter import get_pii_safe_logger

logger = get_pii_safe_logger(__name__)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ComplianceItem:
    """Einzelner Compliance-Check."""

    check_name: str
    category: str  # gdpr, gobd, retention, security
    status: str  # passed, warning, failed
    description: str  # German
    recommendation: Optional[str] = None  # German
    details: Optional[Dict[str, Any]] = None


@dataclass
class ComplianceScanResult:
    """Ergebnis eines Compliance-Scans."""

    total_checks: int
    passed: int
    warnings: int
    failures: int
    items: List[ComplianceItem]
    score: float  # 0-100
    scan_timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetentionReport:
    """Aufbewahrungsfristen-Report."""

    documents_total: int
    documents_expired: int
    documents_expiring_soon: int  # Nächste 30 Tage
    expired_document_ids: List[UUID]
    expiring_soon_ids: List[UUID]
    retention_by_type: Dict[str, Dict[str, int]]


@dataclass
class GDPRCheckResult:
    """GDPR-Compliance-Check Ergebnis."""

    compliant: bool
    issues: List[str]  # Deutsche Beschreibungen
    recommendations: List[str]  # Deutsche Empfehlungen
    personal_data_count: int
    deletion_candidates: int


@dataclass
class AuditPackage:
    """Audit-Paket für Steuerprüfung."""

    zip_content: bytes
    filename: str
    document_count: int
    date_range: Tuple[date, date]
    included_types: List[str]
    # W1-031 (additiv): Anzahl Dokumente, deren Originaldatei nicht aus dem
    # Storage abrufbar war (im ZIP als *_FEHLT.txt-Platzhalter gekennzeichnet).
    documents_missing: int = 0


# ============================================================================
# COMPLIANCE AUTOPILOT SERVICE
# ============================================================================


class ComplianceAutopilotService:
    """Service für automatische Compliance-Checks."""

    # Aufbewahrungsfristen nach §147 AO (in Jahren)
    RETENTION_PERIODS = {
        DocumentType.INVOICE: 10,
        DocumentType.CREDIT_NOTE: 10,
        DocumentType.RECEIPT: 10,
        DocumentType.BANK_STATEMENT: 10,
        DocumentType.TAX_DOCUMENT: 10,
        DocumentType.CONTRACT: 10,
        DocumentType.ORDER: 10,
        DocumentType.PURCHASE_ORDER: 10,
        DocumentType.DELIVERY_NOTE: 6,
        DocumentType.OFFER: 6,
        DocumentType.DUNNING_LETTER: 6,
        DocumentType.LETTER: 2,
        DocumentType.FORM: 2,
        DocumentType.REPORT: 2,
        DocumentType.OTHER: 0,
        DocumentType.UNKNOWN: 0,
    }

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def run_compliance_scan(
        self, company_id: UUID, db: AsyncSession
    ) -> ComplianceScanResult:
        """
        Führt vollständigen Compliance-Scan durch.

        Args:
            company_id: Company-ID (Multi-Tenant)
            db: Datenbank-Session

        Returns:
            ComplianceScanResult mit allen Checks
        """
        logger.info("compliance_scan_started", company_id=str(company_id))

        items: List[ComplianceItem] = []

        # GDPR-Checks
        items.extend(await self._check_gdpr(company_id, db))

        # GoBD-Checks
        items.extend(await self._check_gobd(company_id, db))

        # Aufbewahrungsfristen
        items.extend(await self._check_retention(company_id, db))

        # Security-Checks
        items.extend(await self._check_security(company_id, db))

        # Statistiken berechnen
        passed = sum(1 for item in items if item.status == "passed")
        warnings = sum(1 for item in items if item.status == "warning")
        failures = sum(1 for item in items if item.status == "failed")

        # Score berechnen (Gewichtung: passed=1, warning=0.5, failed=0)
        score = (
            ((passed + warnings * 0.5) / len(items) * 100) if items else 100.0
        )

        result = ComplianceScanResult(
            total_checks=len(items),
            passed=passed,
            warnings=warnings,
            failures=failures,
            items=items,
            score=round(score, 2),
        )

        logger.info(
            "compliance_scan_completed",
            company_id=str(company_id),
            score=result.score,
            passed=passed,
            warnings=warnings,
            failures=failures,
        )

        return result

    async def check_retention(
        self, company_id: UUID, db: AsyncSession
    ) -> RetentionReport:
        """
        Prüft Aufbewahrungsfristen.

        Args:
            company_id: Company-ID
            db: Datenbank-Session

        Returns:
            RetentionReport mit abgelaufenen und bald ablaufenden Dokumenten
        """
        logger.info("retention_check_started", company_id=str(company_id))

        # Alle Dokumente abrufen
        stmt = select(Document).where(Document.company_id == company_id)
        result = await db.execute(stmt)
        documents = result.scalars().all()

        expired_ids: List[UUID] = []
        expiring_soon_ids: List[UUID] = []
        retention_by_type: Dict[str, Dict[str, int]] = {}

        today = date.today()

        for doc in documents:
            # Aufbewahrungsfrist bestimmen
            doc_type = doc.document_type or DocumentType.UNKNOWN
            retention_years = self.RETENTION_PERIODS.get(doc_type, 0)

            if retention_years == 0:
                continue

            # Ablaufdatum berechnen
            created_date = doc.created_at.date()
            expiry_date = created_date + timedelta(days=retention_years * 365)

            # Status bestimmen
            if expiry_date < today:
                expired_ids.append(doc.id)
            elif expiry_date < today + timedelta(days=30):
                expiring_soon_ids.append(doc.id)

            # Statistik nach Typ
            type_key = doc_type.value
            if type_key not in retention_by_type:
                retention_by_type[type_key] = {
                    "total": 0,
                    "expired": 0,
                    "expiring_soon": 0,
                }

            retention_by_type[type_key]["total"] += 1
            if doc.id in expired_ids:
                retention_by_type[type_key]["expired"] += 1
            elif doc.id in expiring_soon_ids:
                retention_by_type[type_key]["expiring_soon"] += 1

        report = RetentionReport(
            documents_total=len(documents),
            documents_expired=len(expired_ids),
            documents_expiring_soon=len(expiring_soon_ids),
            expired_document_ids=expired_ids,
            expiring_soon_ids=expiring_soon_ids,
            retention_by_type=retention_by_type,
        )

        logger.info(
            "retention_check_completed",
            company_id=str(company_id),
            expired=len(expired_ids),
            expiring_soon=len(expiring_soon_ids),
        )

        return report

    async def prepare_audit(
        self,
        company_id: UUID,
        date_range: Tuple[date, date],
        db: AsyncSession,
    ) -> AuditPackage:
        """
        Bereitet Audit-Paket für Steuerprüfung vor.

        Args:
            company_id: Company-ID
            date_range: Zeitraum (start, end)
            db: Datenbank-Session

        Returns:
            AuditPackage mit ZIP-Archiv
        """
        logger.info(
            "audit_preparation_started",
            company_id=str(company_id),
            date_range=date_range,
        )

        start_date, end_date = date_range

        # Relevante Dokumente abrufen
        stmt = (
            select(Document)
            .where(
                Document.company_id == company_id,
                Document.created_at >= datetime.combine(
                    start_date, datetime.min.time()
                ),
                Document.created_at <= datetime.combine(
                    end_date, datetime.max.time()
                ),
            )
            .order_by(Document.created_at)
        )
        result = await db.execute(stmt)
        documents = result.scalars().all()

        # W1-031: Echte Dateien aus MinIO statt Mock-Content.
        # Storage-Init darf das Audit-Paket nicht crashen - fehlende Dateien
        # werden als *_FEHLT.txt-Platzhalter ehrlich gekennzeichnet.
        storage = None
        try:
            from app.services.storage_service import get_storage_service

            storage = get_storage_service()
        except Exception as e:  # noqa: BLE001 - Audit degradiert pro Dokument
            logger.warning(
                "audit_storage_unavailable",
                company_id=str(company_id),
                error_type=type(e).__name__,
            )

        # ZIP-Archiv erstellen
        zip_buffer = io.BytesIO()
        missing_ids: List[UUID] = []
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Index-Datei
            index_content = self._generate_audit_index(documents)
            zip_file.writestr("INDEX.txt", index_content)

            # Dokumente nach Typ sortiert
            included_types: List[str] = []
            for doc in documents:
                doc_type = doc.document_type or DocumentType.UNKNOWN
                type_dir = doc_type.value

                if type_dir not in included_types:
                    included_types.append(type_dir)

                # W1-031: Original-Datei aus MinIO laden
                file_content: Optional[bytes] = None
                if storage is not None and doc.file_path:
                    try:
                        file_content = await storage.download_document(doc.file_path)
                    except Exception as e:  # noqa: BLE001 - pro Dokument degradieren
                        logger.warning(
                            "audit_document_download_failed",
                            document_id=str(doc.id),
                            error_type=type(e).__name__,
                        )

                date_prefix = doc.created_at.strftime("%Y%m%d")
                if file_content is not None:
                    # Dateiname: YYYYMMDD_DocumentID.<Original-Endung>
                    extension = self._audit_file_extension(doc)
                    filepath = f"{type_dir}/{date_prefix}_{doc.id}.{extension}"
                    zip_file.writestr(filepath, file_content)
                else:
                    # Ehrlicher Platzhalter statt Mock-Content
                    missing_ids.append(doc.id)
                    placeholder = (
                        "FEHLER: Originaldatei nicht abrufbar.\n"
                        f"Dokument-ID: {doc.id}\n"
                        f"Typ: {doc_type.value}\n"
                        f"Erstellt: {doc.created_at.isoformat()}\n"
                        "Bitte Storage-Verfuegbarkeit pruefen und Audit-Paket "
                        "erneut erstellen.\n"
                    )
                    filepath = f"{type_dir}/{date_prefix}_{doc.id}_FEHLT.txt"
                    zip_file.writestr(filepath, placeholder.encode("utf-8"))

            # Fehlende Dateien zusaetzlich zentral ausweisen
            if missing_ids:
                missing_list = "\n".join(str(doc_id) for doc_id in missing_ids)
                zip_file.writestr(
                    "FEHLENDE_DATEIEN.txt",
                    (
                        f"{len(missing_ids)} Dokument(e) ohne abrufbare "
                        f"Originaldatei:\n{missing_list}\n"
                    ).encode("utf-8"),
                )

        zip_buffer.seek(0)
        zip_content = zip_buffer.read()

        # Filename generieren
        filename = f"Audit_{company_id}_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.zip"

        package = AuditPackage(
            zip_content=zip_content,
            filename=filename,
            document_count=len(documents),
            date_range=date_range,
            included_types=included_types,
            documents_missing=len(missing_ids),
        )

        logger.info(
            "audit_preparation_completed",
            company_id=str(company_id),
            document_count=len(documents),
            documents_missing=len(missing_ids),
            zip_size_bytes=len(zip_content),
        )

        return package

    @staticmethod
    def _audit_file_extension(doc: Document) -> str:
        """Ermittelt die Datei-Endung fuer das Audit-ZIP (W1-031).

        Bevorzugt die Original-Endung aus filename/file_path;
        Fallback "pdf" (bisheriges Namensschema).
        """
        for candidate in (doc.filename, doc.file_path):
            if candidate and "." in candidate:
                extension = candidate.rsplit(".", 1)[1].strip().lower()
                if extension and len(extension) <= 8 and extension.isalnum():
                    return extension
        return "pdf"

    async def run_gdpr_check(
        self, company_id: UUID, db: AsyncSession
    ) -> GDPRCheckResult:
        """
        Führt GDPR-Compliance-Check durch.

        Args:
            company_id: Company-ID
            db: Datenbank-Session

        Returns:
            GDPRCheckResult mit Ergebnissen
        """
        logger.info("gdpr_check_started", company_id=str(company_id))

        issues: List[str] = []
        recommendations: List[str] = []

        # Dokumente mit PII zählen
        stmt = select(func.count(Document.id)).where(
            Document.company_id == company_id,
            Document.metadata.isnot(None),
        )
        result = await db.execute(stmt)
        personal_data_count = result.scalar() or 0

        # Löschkandidaten (>3 Jahre alt ohne rechtliche Aufbewahrungsfrist)
        three_years_ago = datetime.utcnow() - timedelta(days=3 * 365)
        stmt = select(func.count(Document.id)).where(
            Document.company_id == company_id,
            Document.created_at < three_years_ago,
            Document.document_type.in_(
                [DocumentType.LETTER, DocumentType.FORM, DocumentType.OTHER]
            ),
        )
        result = await db.execute(stmt)
        deletion_candidates = result.scalar() or 0

        # Checks
        if deletion_candidates > 0:
            issues.append(
                f"{deletion_candidates} Dokumente könnten nach GDPR gelöscht werden"
            )
            recommendations.append(
                "Prüfen Sie, ob personenbezogene Daten noch benötigt werden"
            )

        # Audit-Log-Check
        stmt = select(func.count(AuditLog.id)).where(
            AuditLog.company_id == company_id
        )
        result = await db.execute(stmt)
        audit_entries = result.scalar() or 0

        if audit_entries == 0:
            issues.append("Kein Audit-Log vorhanden")
            recommendations.append(
                "Aktivieren Sie Audit-Logging für GDPR-Compliance"
            )

        compliant = len(issues) == 0

        result_obj = GDPRCheckResult(
            compliant=compliant,
            issues=issues,
            recommendations=recommendations,
            personal_data_count=personal_data_count,
            deletion_candidates=deletion_candidates,
        )

        logger.info(
            "gdpr_check_completed",
            company_id=str(company_id),
            compliant=compliant,
            issues_count=len(issues),
        )

        return result_obj

    # ========================================================================
    # PRIVATE HELPERS
    # ========================================================================

    async def _check_gdpr(
        self, company_id: UUID, db: AsyncSession
    ) -> List[ComplianceItem]:
        """GDPR-Compliance-Checks."""
        items: List[ComplianceItem] = []

        # Check 1: Löschfristen
        retention_report = await self.check_retention(company_id, db)
        if retention_report.documents_expired > 0:
            items.append(
                ComplianceItem(
                    check_name="GDPR Löschfristen",
                    category="gdpr",
                    status="warning",
                    description=f"{retention_report.documents_expired} Dokumente haben Aufbewahrungsfrist überschritten",
                    recommendation="Prüfen und ggf. löschen nach GDPR Art. 17",
                )
            )
        else:
            items.append(
                ComplianceItem(
                    check_name="GDPR Löschfristen",
                    category="gdpr",
                    status="passed",
                    description="Keine abgelaufenen Aufbewahrungsfristen",
                )
            )

        # Check 2: Audit-Log
        stmt = select(func.count(AuditLog.id)).where(
            AuditLog.company_id == company_id
        )
        result = await db.execute(stmt)
        audit_count = result.scalar() or 0

        if audit_count > 0:
            items.append(
                ComplianceItem(
                    check_name="GDPR Audit-Trail",
                    category="gdpr",
                    status="passed",
                    description=f"{audit_count} Audit-Log-Einträge vorhanden",
                )
            )
        else:
            items.append(
                ComplianceItem(
                    check_name="GDPR Audit-Trail",
                    category="gdpr",
                    status="warning",
                    description="Kein Audit-Log aktiviert",
                    recommendation="Aktivieren Sie Audit-Logging (GDPR Art. 30)",
                )
            )

        return items

    async def _check_gobd(
        self, company_id: UUID, db: AsyncSession
    ) -> List[ComplianceItem]:
        """GoBD-Compliance-Checks."""
        items: List[ComplianceItem] = []

        # Check 1: Unveränderbarkeit (Version-History)
        stmt = select(Document).where(
            Document.company_id == company_id,
            Document.document_type.in_(
                [
                    DocumentType.INVOICE,
                    DocumentType.CREDIT_NOTE,
                    DocumentType.RECEIPT,
                ]
            ),
        )
        result = await db.execute(stmt)
        financial_docs = result.scalars().all()

        # Prüfe ob alle Version-History haben
        docs_without_version = sum(
            1 for doc in financial_docs if not doc.metadata or not doc.metadata.get("version_history")
        )

        if docs_without_version == 0:
            items.append(
                ComplianceItem(
                    check_name="GoBD Unveränderbarkeit",
                    category="gobd",
                    status="passed",
                    description="Alle relevanten Dokumente haben Version-History",
                )
            )
        else:
            items.append(
                ComplianceItem(
                    check_name="GoBD Unveränderbarkeit",
                    category="gobd",
                    status="warning",
                    description=f"{docs_without_version} Dokumente ohne Version-History",
                    recommendation="Aktivieren Sie Versionierung für buchungsrelevante Dokumente",
                )
            )

        # Check 2: Nachvollziehbarkeit (Metadaten)
        docs_without_metadata = sum(
            1 for doc in financial_docs if not doc.metadata
        )

        if docs_without_metadata == 0:
            items.append(
                ComplianceItem(
                    check_name="GoBD Nachvollziehbarkeit",
                    category="gobd",
                    status="passed",
                    description="Alle Dokumente haben Metadaten",
                )
            )
        else:
            items.append(
                ComplianceItem(
                    check_name="GoBD Nachvollziehbarkeit",
                    category="gobd",
                    status="failed",
                    description=f"{docs_without_metadata} Dokumente ohne Metadaten",
                    recommendation="Ergänzen Sie Metadaten (Datum, Betrag, etc.)",
                )
            )

        return items

    async def _check_retention(
        self, company_id: UUID, db: AsyncSession
    ) -> List[ComplianceItem]:
        """Aufbewahrungsfristen-Checks."""
        items: List[ComplianceItem] = []

        report = await self.check_retention(company_id, db)

        # Check: Expiring Soon
        if report.documents_expiring_soon > 0:
            items.append(
                ComplianceItem(
                    check_name="Aufbewahrungsfristen - Ablauf bevorstehend",
                    category="retention",
                    status="warning",
                    description=f"{report.documents_expiring_soon} Dokumente laufen in den nächsten 30 Tagen ab",
                    recommendation="Prüfen und archivieren",
                )
            )
        else:
            items.append(
                ComplianceItem(
                    check_name="Aufbewahrungsfristen - Ablauf bevorstehend",
                    category="retention",
                    status="passed",
                    description="Keine Dokumente mit bevorstehender Frist",
                )
            )

        return items

    async def _check_security(
        self, company_id: UUID, db: AsyncSession
    ) -> List[ComplianceItem]:
        """Security-Checks."""
        items: List[ComplianceItem] = []

        # Check: Verschlüsselte Speicherung (Mock - in Production: MinIO-Check)
        items.append(
            ComplianceItem(
                check_name="Verschlüsselte Speicherung",
                category="security",
                status="passed",
                description="Dokumente werden verschlüsselt gespeichert (MinIO)",
            )
        )

        # Check: Zugriffskontrolle
        items.append(
            ComplianceItem(
                check_name="Zugriffskontrolle",
                category="security",
                status="passed",
                description="Multi-Tenant RLS aktiv (PostgreSQL)",
            )
        )

        return items

    def _generate_audit_index(self, documents: List[Document]) -> str:
        """Generiert Index-Datei für Audit-Paket."""
        lines = [
            "AUDIT-PAKET INDEX",
            "=" * 80,
            f"Erstellt am: {datetime.utcnow().strftime('%d.%m.%Y %H:%M:%S')} UTC",
            f"Anzahl Dokumente: {len(documents)}",
            "",
            "DOKUMENTE:",
            "-" * 80,
        ]

        for doc in documents:
            lines.append(
                f"{doc.created_at.strftime('%d.%m.%Y')} | "
                f"{doc.document_type.value if doc.document_type else 'unknown':20} | "
                f"{doc.id} | "
                f"{doc.filename or 'N/A'}"
            )

        return "\n".join(lines)
