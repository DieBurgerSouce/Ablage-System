"""
Master Data Hygiene Service.

Erkennt und korrigiert veraltete Stammdaten:
- Delta-Vergleich bei Lexware-Import
- Neue Adressen/IBANs aus Dokumenten extrahieren
- Inaktive Kunden markieren
- Automatische Korrekturvorschläge

Für Enterprise-Niveau mit Human-in-the-Loop.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import structlog
from sqlalchemy import and_, func, or_, select, update, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BusinessEntity,
    Document,
    EntityType,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# ============================================================================
# ENUMS & DATA CLASSES
# ============================================================================


class HygieneIssueType(str, Enum):
    """Arten von Stammdaten-Problemen."""

    # Adress-Probleme
    ADDRESS_CHANGED = "address_changed"
    ADDRESS_MISSING = "address_missing"
    ADDRESS_INCOMPLETE = "address_incomplete"

    # Banking-Probleme
    IBAN_CHANGED = "iban_changed"
    IBAN_MISSING = "iban_missing"
    IBAN_INVALID = "iban_invalid"

    # Kontakt-Probleme
    EMAIL_CHANGED = "email_changed"
    EMAIL_MISSING = "email_missing"
    PHONE_CHANGED = "phone_changed"

    # Identifikations-Probleme
    VAT_ID_CHANGED = "vat_id_changed"
    VAT_ID_MISSING = "vat_id_missing"

    # Aktivitäts-Probleme
    INACTIVE_CUSTOMER = "inactive_customer"
    INACTIVE_SUPPLIER = "inactive_supplier"

    # Duplikat-Probleme
    POTENTIAL_DUPLICATE = "potential_duplicate"

    # Import-Deltas
    LEXWARE_DELTA = "lexware_delta"


class HygieneIssueSeverity(str, Enum):
    """Schweregrad von Stammdaten-Problemen."""

    INFO = "info"           # Nur zur Information
    LOW = "low"             # Geringe Priorität
    MEDIUM = "medium"       # Sollte korrigiert werden
    HIGH = "high"           # Wichtig zu korrigieren
    CRITICAL = "critical"   # Muss sofort korrigiert werden


@dataclass
class HygieneIssue:
    """Ein erkanntes Stammdaten-Problem."""

    id: uuid.UUID
    entity_id: uuid.UUID
    entity_name: str
    entity_type: str

    issue_type: HygieneIssueType
    severity: HygieneIssueSeverity

    field_name: str
    current_value: Optional[str]
    suggested_value: Optional[str]

    source: str  # "lexware_import", "document_ocr", "inactivity_check"
    source_document_id: Optional[uuid.UUID] = None

    confidence: float = 0.0
    auto_correctable: bool = False

    details: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "issue_type": self.issue_type.value,
            "severity": self.severity.value,
            "field_name": self.field_name,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "source": self.source,
            "source_document_id": str(self.source_document_id) if self.source_document_id else None,
            "confidence": self.confidence,
            "auto_correctable": self.auto_correctable,
            "details": self.details,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class HygieneReport:
    """Bericht über Stammdaten-Hygiene."""

    total_entities_checked: int = 0
    issues_found: int = 0
    auto_correctable_count: int = 0

    by_severity: Dict[str, int] = field(default_factory=dict)
    by_type: Dict[str, int] = field(default_factory=dict)

    issues: List[HygieneIssue] = field(default_factory=list)

    scan_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    scan_completed_at: Optional[datetime] = None

    def add_issue(self, issue: HygieneIssue) -> None:
        """Fuegt ein Issue hinzu und aktualisiert Statistiken."""
        self.issues.append(issue)
        self.issues_found += 1

        if issue.auto_correctable:
            self.auto_correctable_count += 1

        severity_key = issue.severity.value
        self.by_severity[severity_key] = self.by_severity.get(severity_key, 0) + 1

        type_key = issue.issue_type.value
        self.by_type[type_key] = self.by_type.get(type_key, 0) + 1


@dataclass
class LexwareDeltaResult:
    """Ergebnis eines Lexware-Delta-Vergleichs."""

    entity_id: uuid.UUID
    kd_nr: str
    changes: List[Dict[str, Any]] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False


# ============================================================================
# MASTER DATA HYGIENE SERVICE
# ============================================================================


class MasterDataHygieneService:
    """
    Service zur Erkennung und Korrektur von Stammdaten-Problemen.

    Features:
    - Delta-Vergleich bei Lexware-Import
    - Extraktion neuer Daten aus Dokumenten
    - Erkennung inaktiver Kunden
    - Automatische Korrekturvorschläge

    Usage:
        service = MasterDataHygieneService(db)
        report = await service.run_full_scan()

        # Oder gezielt:
        issues = await service.check_entity_data_from_document(entity_id, document_id)
    """

    # Konfigurations-Schwellenwerte
    DEFAULT_INACTIVITY_DAYS = 365  # 1 Jahr ohne Dokumente = inaktiv
    DEFAULT_AUTO_CORRECT_CONFIDENCE = 0.95  # 95%+ = automatisch korrigierbar
    DEFAULT_SUGGEST_CONFIDENCE = 0.75  # 75%+ = Vorschlag anzeigen

    # Felder die verglichen werden
    COMPARABLE_FIELDS = [
        "street", "street_number", "postal_code", "city",
        "email", "phone", "iban", "bic", "vat_id"
    ]

    def __init__(
        self,
        db: AsyncSession,
        inactivity_days: int = DEFAULT_INACTIVITY_DAYS,
        auto_correct_confidence: float = DEFAULT_AUTO_CORRECT_CONFIDENCE,
        suggest_confidence: float = DEFAULT_SUGGEST_CONFIDENCE,
    ) -> None:
        """
        Initialisiert den Service.

        Args:
            db: Async Database Session
            inactivity_days: Tage ohne Aktivität = inaktiv
            auto_correct_confidence: Schwelle für automatische Korrektur
            suggest_confidence: Schwelle für Korrekturvorschläge
        """
        self.db = db
        self.inactivity_days = inactivity_days
        self.auto_correct_confidence = auto_correct_confidence
        self.suggest_confidence = suggest_confidence

    # ========================================================================
    # MAIN SCAN METHODS
    # ========================================================================

    async def run_full_scan(
        self,
        company_id: Optional[uuid.UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> HygieneReport:
        """
        Führt vollständigen Hygiene-Scan durch.

        Args:
            company_id: Optional - nur für bestimmte Firma
            entity_types: Optional - nur bestimmte Entity-Typen

        Returns:
            HygieneReport mit allen gefundenen Problemen
        """
        report = HygieneReport()

        logger.info(
            "hygiene_scan_started",
            company_id=str(company_id) if company_id else None,
            entity_types=[t.value for t in entity_types] if entity_types else None,
        )

        try:
            # 1. Inaktive Entities finden
            inactive_issues = await self._scan_inactive_entities(
                company_id=company_id,
                entity_types=entity_types,
            )
            for issue in inactive_issues:
                report.add_issue(issue)

            # 2. Fehlende Pflichtdaten finden
            missing_issues = await self._scan_missing_data(
                company_id=company_id,
                entity_types=entity_types,
            )
            for issue in missing_issues:
                report.add_issue(issue)

            # 3. Potentielle Duplikate finden
            duplicate_issues = await self._scan_potential_duplicates(
                company_id=company_id,
                entity_types=entity_types,
            )
            for issue in duplicate_issues:
                report.add_issue(issue)

            # 4. Entities zaehlen
            report.total_entities_checked = await self._count_entities(
                company_id=company_id,
                entity_types=entity_types,
            )

            report.scan_completed_at = datetime.now(timezone.utc)

            logger.info(
                "hygiene_scan_completed",
                total_checked=report.total_entities_checked,
                issues_found=report.issues_found,
                auto_correctable=report.auto_correctable_count,
            )

        except Exception as e:
            logger.exception("hygiene_scan_failed", **safe_error_log(e))
            raise

        return report

    async def _count_entities(
        self,
        company_id: Optional[uuid.UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> int:
        """Zaehlt Entities basierend auf Filtern."""
        query = select(func.count(BusinessEntity.id)).where(
            BusinessEntity.deleted_at.is_(None)
        )

        if entity_types:
            query = query.where(
                BusinessEntity.entity_type.in_([t.value for t in entity_types])
            )

        result = await self.db.execute(query)
        return result.scalar() or 0

    # ========================================================================
    # LEXWARE DELTA DETECTION
    # ========================================================================

    async def compare_lexware_import(
        self,
        import_data: List[Dict[str, Any]],
        company: str,
        entity_type: EntityType = EntityType.CUSTOMER,
    ) -> List[HygieneIssue]:
        """
        Vergleicht Lexware-Import mit bestehenden Daten.

        Args:
            import_data: Liste von Import-Datensätzen
            company: Firma (folie/messer)
            entity_type: Entity-Typ

        Returns:
            Liste von erkannten Änderungen
        """
        issues: List[HygieneIssue] = []

        logger.info(
            "lexware_delta_started",
            company=company,
            entity_type=entity_type.value,
            import_count=len(import_data),
        )

        for record in import_data:
            try:
                # Kundennummer/Lieferantennummer extrahieren
                if entity_type == EntityType.CUSTOMER:
                    number = record.get("kd_nr") or record.get("Kd_Nr") or record.get("kd-nr")
                else:
                    number = record.get("lief_nr") or record.get("Lief_Nr") or record.get("lief-nr")

                if not number:
                    continue

                # Existierende Entity suchen
                entity = await self._find_entity_by_lexware_number(
                    number=str(number).strip(),
                    company=company,
                    entity_type=entity_type,
                )

                if not entity:
                    # Neue Entity - kein Delta
                    continue

                # Felder vergleichen
                field_mappings = {
                    "street": ["strasse", "Strasse", "street"],
                    "street_number": ["haus_nr", "HausNr", "hausnr"],
                    "postal_code": ["plz", "PLZ", "postal_code"],
                    "city": ["ort", "Ort", "city"],
                    "email": ["email", "Email", "E-Mail"],
                    "phone": ["tel1", "Tel1", "telefon", "Telefon"],
                    "iban": ["iban", "IBAN"],
                    "bic": ["bic", "BIC"],
                }

                for db_field, import_keys in field_mappings.items():
                    import_value = None
                    for key in import_keys:
                        if key in record and record[key]:
                            import_value = str(record[key]).strip()
                            break

                    if not import_value or import_value in (".", "-", ""):
                        continue

                    current_value = getattr(entity, db_field, None)
                    current_value = str(current_value).strip() if current_value else ""

                    # Normalisieren für Vergleich
                    if db_field == "iban":
                        import_value = re.sub(r"\s", "", import_value).upper()
                        current_value = re.sub(r"\s", "", current_value).upper()

                    # Änderung erkannt?
                    if import_value and import_value != current_value:
                        severity = self._determine_delta_severity(db_field, current_value, import_value)

                        issue = HygieneIssue(
                            id=uuid.uuid4(),
                            entity_id=entity.id,
                            entity_name=entity.display_name or entity.name,
                            entity_type=entity_type.value,
                            issue_type=HygieneIssueType.LEXWARE_DELTA,
                            severity=severity,
                            field_name=db_field,
                            current_value=current_value if current_value else None,
                            suggested_value=import_value,
                            source="lexware_import",
                            confidence=0.98,  # Lexware ist vertrauenswuerdige Quelle
                            auto_correctable=severity not in (HygieneIssueSeverity.CRITICAL, HygieneIssueSeverity.HIGH),
                            details={
                                "company": company,
                                "lexware_number": number,
                            },
                        )
                        issues.append(issue)

            except Exception as e:
                logger.error(
                    "lexware_delta_record_error",
                    **safe_error_log(e),
                    record_keys=list(record.keys()) if isinstance(record, dict) else None,
                )
                continue

        logger.info(
            "lexware_delta_completed",
            company=company,
            issues_found=len(issues),
        )

        return issues

    async def _find_entity_by_lexware_number(
        self,
        number: str,
        company: str,
        entity_type: EntityType,
    ) -> Optional[BusinessEntity]:
        """Findet Entity anhand Lexware-Nummer."""
        # Suche nach primary_customer_number oder primary_supplier_number
        if entity_type == EntityType.CUSTOMER:
            query = select(BusinessEntity).where(
                BusinessEntity.primary_customer_number == number,
                BusinessEntity.entity_type == entity_type.value,
                BusinessEntity.deleted_at.is_(None),
            )
        else:
            query = select(BusinessEntity).where(
                BusinessEntity.primary_supplier_number == number,
                BusinessEntity.entity_type == entity_type.value,
                BusinessEntity.deleted_at.is_(None),
            )

        result = await self.db.execute(query)
        entity = result.scalar_one_or_none()

        if entity:
            return entity

        # Fallback: Suche in lexware_ids JSONB
        # Hier müssen wir den JSONB-Pfad durchsuchen
        if entity_type == EntityType.CUSTOMER:
            key = "kd_nr"
        else:
            key = "lief_nr"

        # PostgreSQL JSONB Query: lexware_ids->'company'->>'key' = 'number'
        # SQLAlchemy: BusinessEntity.lexware_ids[company][key] == number
        query = select(BusinessEntity).where(
            cast(BusinessEntity.lexware_ids, JSONB)[company][key].astext == number,
            BusinessEntity.entity_type == entity_type.value,
            BusinessEntity.deleted_at.is_(None),
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _determine_delta_severity(
        self,
        field_name: str,
        current: Optional[str],
        new: str,
    ) -> HygieneIssueSeverity:
        """Bestimmt Schweregrad einer Änderung."""
        # IBAN-Änderung ist kritisch
        if field_name == "iban":
            return HygieneIssueSeverity.CRITICAL

        # VAT-ID Änderung ist hoch
        if field_name == "vat_id":
            return HygieneIssueSeverity.HIGH

        # Adress-Änderungen sind medium
        if field_name in ("street", "postal_code", "city"):
            return HygieneIssueSeverity.MEDIUM

        # Kontakt-Änderungen sind niedrig
        if field_name in ("email", "phone"):
            return HygieneIssueSeverity.LOW

        return HygieneIssueSeverity.INFO

    # ========================================================================
    # DOCUMENT-BASED DATA EXTRACTION
    # ========================================================================

    async def extract_updates_from_document(
        self,
        document_id: uuid.UUID,
        entity_id: uuid.UUID,
        ocr_text: str,
    ) -> List[HygieneIssue]:
        """
        Extrahiert mögliche Stammdaten-Updates aus einem Dokument.

        Args:
            document_id: Dokument-ID
            entity_id: Entity-ID die mit dem Dokument verknüpft ist
            ocr_text: OCR-extrahierter Text

        Returns:
            Liste von erkannten Änderungen
        """
        from app.services.entity_extraction_service import EntityExtractionService


        issues: List[HygieneIssue] = []

        # Entity laden
        result = await self.db.execute(
            select(BusinessEntity).where(
                BusinessEntity.id == entity_id,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning("entity_not_found", entity_id=str(entity_id))
            return issues

        # Entity Extraction durchführen
        extractor = EntityExtractionService(self.db)
        extraction = await extractor.extract_entities(ocr_text, document_id)

        # IBAN prüfen
        for identifier in extraction.identifiers:
            if identifier.identifier_type == "iban":
                extracted_iban = identifier.normalized_value
                current_iban = entity.iban

                # Nur wenn unterschiedlich und hohe Confidence
                if (
                    extracted_iban
                    and identifier.confidence >= self.suggest_confidence
                    and extracted_iban != (current_iban or "").upper().replace(" ", "")
                ):
                    issue = HygieneIssue(
                        id=uuid.uuid4(),
                        entity_id=entity.id,
                        entity_name=entity.display_name or entity.name,
                        entity_type=entity.entity_type,
                        issue_type=HygieneIssueType.IBAN_CHANGED,
                        severity=HygieneIssueSeverity.HIGH,
                        field_name="iban",
                        current_value=current_iban,
                        suggested_value=extracted_iban,
                        source="document_ocr",
                        source_document_id=document_id,
                        confidence=identifier.confidence,
                        auto_correctable=identifier.confidence >= self.auto_correct_confidence,
                        details={
                            "context": identifier.context[:100] if identifier.context else None,
                        },
                    )
                    issues.append(issue)

        # Adressen prüfen
        for address in extraction.addresses:
            # Nur Sender-Adressen sind relevant (Entity = Absender)
            if address.role == "sender" or address.confidence >= 0.85:
                # PLZ + Stadt vergleichen
                if address.postal_code and address.city:
                    current_plz = entity.postal_code or ""
                    current_city = (entity.city or "").lower()

                    extracted_plz = address.postal_code
                    extracted_city = address.city.lower()

                    # Unterschied erkannt?
                    if (
                        extracted_plz != current_plz
                        or not self._similar_text(extracted_city, current_city, 0.85)
                    ):
                        # Nur wenn signifikanter Unterschied
                        if current_plz and current_plz != extracted_plz:
                            issue = HygieneIssue(
                                id=uuid.uuid4(),
                                entity_id=entity.id,
                                entity_name=entity.display_name or entity.name,
                                entity_type=entity.entity_type,
                                issue_type=HygieneIssueType.ADDRESS_CHANGED,
                                severity=HygieneIssueSeverity.MEDIUM,
                                field_name="address",
                                current_value=f"{entity.street} {entity.street_number}, {current_plz} {entity.city}",
                                suggested_value=f"{address.street} {address.street_number}, {extracted_plz} {address.city}",
                                source="document_ocr",
                                source_document_id=document_id,
                                confidence=address.confidence,
                                auto_correctable=False,  # Adressen nie automatisch ändern
                                details={
                                    "extracted_street": address.street,
                                    "extracted_plz": extracted_plz,
                                    "extracted_city": address.city,
                                },
                            )
                            issues.append(issue)

        # E-Mail prüfen
        for email in extraction.emails:
            current_email = (entity.email or "").lower()
            extracted_email = email.lower()

            if extracted_email != current_email:
                # Domain muss zur Entity passen
                domain = extracted_email.split("@")[-1]
                entity_domains = entity.email_domains or []

                if domain in entity_domains or not current_email:
                    issue = HygieneIssue(
                        id=uuid.uuid4(),
                        entity_id=entity.id,
                        entity_name=entity.display_name or entity.name,
                        entity_type=entity.entity_type,
                        issue_type=HygieneIssueType.EMAIL_CHANGED,
                        severity=HygieneIssueSeverity.LOW,
                        field_name="email",
                        current_value=current_email if current_email else None,
                        suggested_value=extracted_email,
                        source="document_ocr",
                        source_document_id=document_id,
                        confidence=0.80,
                        auto_correctable=not current_email,  # Nur automatisch wenn vorher leer
                        details={
                            "domain": domain,
                        },
                    )
                    issues.append(issue)

        if issues:
            logger.info(
                "document_updates_extracted",
                document_id=str(document_id),
                entity_id=str(entity_id),
                issues_count=len(issues),
            )

        return issues

    def _similar_text(self, text1: str, text2: str, threshold: float) -> bool:
        """Prüft ob zwei Texte ähnlich genug sind."""
        if not text1 or not text2:
            return text1 == text2
        return SequenceMatcher(None, text1, text2).ratio() >= threshold

    # ========================================================================
    # INACTIVITY DETECTION
    # ========================================================================

    async def _scan_inactive_entities(
        self,
        company_id: Optional[uuid.UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> List[HygieneIssue]:
        """Findet inaktive Entities ohne Dokumente."""
        issues: List[HygieneIssue] = []

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.inactivity_days)

        # Query für Entities die:
        # 1. Aktiv sind (is_active = True)
        # 2. Kein letztes Dokument haben ODER letztes Dokument aelter als cutoff
        query = select(BusinessEntity).where(
            BusinessEntity.is_active == True,
            BusinessEntity.deleted_at.is_(None),
            or_(
                BusinessEntity.last_document_date.is_(None),
                BusinessEntity.last_document_date < cutoff_date,
            ),
        )

        if entity_types:
            query = query.where(
                BusinessEntity.entity_type.in_([t.value for t in entity_types])
            )

        result = await self.db.execute(query)
        inactive_entities = result.scalars().all()

        for entity in inactive_entities:
            # Tage seit letztem Dokument berechnen
            if entity.last_document_date:
                days_inactive = (datetime.now(timezone.utc) - entity.last_document_date).days
            else:
                # Kein Dokument jemals - seit Erstellung inaktiv
                created_at = entity.created_at or datetime.now(timezone.utc)
                days_inactive = (datetime.now(timezone.utc) - created_at).days

            # Schweregrad basierend auf Inaktivitätsdauer
            if days_inactive > 730:  # > 2 Jahre
                severity = HygieneIssueSeverity.HIGH
            elif days_inactive > 365:  # > 1 Jahr
                severity = HygieneIssueSeverity.MEDIUM
            else:
                severity = HygieneIssueSeverity.LOW

            issue_type = (
                HygieneIssueType.INACTIVE_CUSTOMER
                if entity.entity_type == EntityType.CUSTOMER.value
                else HygieneIssueType.INACTIVE_SUPPLIER
            )

            issue = HygieneIssue(
                id=uuid.uuid4(),
                entity_id=entity.id,
                entity_name=entity.display_name or entity.name,
                entity_type=entity.entity_type,
                issue_type=issue_type,
                severity=severity,
                field_name="activity",
                current_value=f"{days_inactive} Tage inaktiv",
                suggested_value="Deaktivieren oder Kontakt aufnehmen",
                source="inactivity_check",
                confidence=0.95,
                auto_correctable=False,
                details={
                    "days_inactive": days_inactive,
                    "last_document_date": entity.last_document_date.isoformat() if entity.last_document_date else None,
                    "document_count": entity.document_count or 0,
                },
            )
            issues.append(issue)

        logger.info(
            "inactive_entities_found",
            count=len(issues),
            cutoff_days=self.inactivity_days,
        )

        return issues

    # ========================================================================
    # MISSING DATA DETECTION
    # ========================================================================

    async def _scan_missing_data(
        self,
        company_id: Optional[uuid.UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> List[HygieneIssue]:
        """Findet Entities mit fehlenden Pflichtdaten."""
        issues: List[HygieneIssue] = []

        # Pflichtfelder definieren
        required_fields = {
            "postal_code": (HygieneIssueType.ADDRESS_INCOMPLETE, HygieneIssueSeverity.MEDIUM),
            "city": (HygieneIssueType.ADDRESS_INCOMPLETE, HygieneIssueSeverity.MEDIUM),
        }

        # Optional aber wichtig
        recommended_fields = {
            "email": (HygieneIssueType.EMAIL_MISSING, HygieneIssueSeverity.LOW),
            "iban": (HygieneIssueType.IBAN_MISSING, HygieneIssueSeverity.LOW),
        }

        # Entities mit fehlenden Feldern suchen
        for field_name, (issue_type, severity) in {**required_fields, **recommended_fields}.items():
            field_attr = getattr(BusinessEntity, field_name)

            query = select(BusinessEntity).where(
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                or_(
                    field_attr.is_(None),
                    field_attr == "",
                ),
            )

            if entity_types:
                query = query.where(
                    BusinessEntity.entity_type.in_([t.value for t in entity_types])
                )

            # Limit für Performance
            query = query.limit(100)

            result = await self.db.execute(query)
            entities = result.scalars().all()

            for entity in entities:
                issue = HygieneIssue(
                    id=uuid.uuid4(),
                    entity_id=entity.id,
                    entity_name=entity.display_name or entity.name,
                    entity_type=entity.entity_type,
                    issue_type=issue_type,
                    severity=severity,
                    field_name=field_name,
                    current_value=None,
                    suggested_value=None,
                    source="missing_data_check",
                    confidence=1.0,
                    auto_correctable=False,
                    details={
                        "document_count": entity.document_count or 0,
                    },
                )
                issues.append(issue)

        logger.info("missing_data_found", count=len(issues))

        return issues

    # ========================================================================
    # DUPLICATE DETECTION
    # ========================================================================

    async def _scan_potential_duplicates(
        self,
        company_id: Optional[uuid.UUID] = None,
        entity_types: Optional[List[EntityType]] = None,
    ) -> List[HygieneIssue]:
        """Findet potentielle Duplikate."""
        issues: List[HygieneIssue] = []
        seen_pairs: Set[Tuple[uuid.UUID, uuid.UUID]] = set()

        # Entities mit gleichem Namen oder ähnlicher Adresse suchen
        query = select(BusinessEntity).where(
            BusinessEntity.is_active == True,
            BusinessEntity.deleted_at.is_(None),
        )

        if entity_types:
            query = query.where(
                BusinessEntity.entity_type.in_([t.value for t in entity_types])
            )

        result = await self.db.execute(query)
        entities = result.scalars().all()

        # N^2 Vergleich - bei vielen Entities limitieren
        entities_to_compare = entities[:500]  # Max 500 Entities vergleichen

        for i, entity1 in enumerate(entities_to_compare):
            for entity2 in entities_to_compare[i+1:]:
                # Gleicher Typ?
                if entity1.entity_type != entity2.entity_type:
                    continue

                # Schon verglichen?
                pair_key = tuple(sorted([entity1.id, entity2.id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Ähnlichkeit prüfen
                similarity = self._calculate_entity_similarity(entity1, entity2)

                if similarity >= 0.85:
                    issue = HygieneIssue(
                        id=uuid.uuid4(),
                        entity_id=entity1.id,
                        entity_name=entity1.display_name or entity1.name,
                        entity_type=entity1.entity_type,
                        issue_type=HygieneIssueType.POTENTIAL_DUPLICATE,
                        severity=HygieneIssueSeverity.MEDIUM,
                        field_name="duplicate",
                        current_value=entity1.name,
                        suggested_value=f"Möglicherweise Duplikat von: {entity2.name}",
                        source="duplicate_check",
                        confidence=similarity,
                        auto_correctable=False,
                        details={
                            "duplicate_entity_id": str(entity2.id),
                            "duplicate_entity_name": entity2.name,
                            "similarity_score": similarity,
                        },
                    )
                    issues.append(issue)

        logger.info("potential_duplicates_found", count=len(issues))

        return issues

    def _calculate_entity_similarity(
        self,
        entity1: BusinessEntity,
        entity2: BusinessEntity,
    ) -> float:
        """Berechnet Ähnlichkeit zwischen zwei Entities."""
        scores: List[float] = []

        # Namen vergleichen (wichtigster Faktor)
        if entity1.name and entity2.name:
            name_sim = SequenceMatcher(
                None,
                entity1.name.lower(),
                entity2.name.lower()
            ).ratio()
            scores.append(name_sim * 2)  # Doppelte Gewichtung

        # PLZ vergleichen
        if entity1.postal_code and entity2.postal_code:
            if entity1.postal_code == entity2.postal_code:
                scores.append(1.0)
            else:
                scores.append(0.0)

        # IBAN vergleichen (wenn beide vorhanden)
        if entity1.iban and entity2.iban:
            iban1 = re.sub(r"\s", "", entity1.iban).upper()
            iban2 = re.sub(r"\s", "", entity2.iban).upper()
            if iban1 == iban2:
                scores.append(1.0)
            else:
                scores.append(0.0)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    # ========================================================================
    # CORRECTION METHODS
    # ========================================================================

    async def apply_correction(
        self,
        issue_id: uuid.UUID,
        entity_id: uuid.UUID,
        field_name: str,
        new_value: str,
        approved_by: uuid.UUID,
    ) -> bool:
        """
        Wendet eine Korrektur an.

        Args:
            issue_id: ID des Issues
            entity_id: ID der Entity
            field_name: Feldname
            new_value: Neuer Wert
            approved_by: User-ID der Genehmigung

        Returns:
            True wenn erfolgreich
        """
        try:
            # Entity laden
            result = await self.db.execute(
                select(BusinessEntity).where(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
            entity = result.scalar_one_or_none()

            if not entity:
                logger.warning(
                    "correction_entity_not_found",
                    entity_id=str(entity_id),
                )
                return False

            # Alten Wert speichern für Audit
            old_value = getattr(entity, field_name, None)

            # Korrektur anwenden
            setattr(entity, field_name, new_value)

            await self.db.commit()

            logger.info(
                "correction_applied",
                issue_id=str(issue_id),
                entity_id=str(entity_id),
                field_name=field_name,
                approved_by=str(approved_by),
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.exception(
                "correction_failed",
                issue_id=str(issue_id),
                **safe_error_log(e),
            )
            return False

    async def mark_entity_inactive(
        self,
        entity_id: uuid.UUID,
        reason: str,
        deactivated_by: uuid.UUID,
    ) -> bool:
        """
        Markiert eine Entity als inaktiv.

        Args:
            entity_id: Entity-ID
            reason: Grund
            deactivated_by: User-ID

        Returns:
            True wenn erfolgreich
        """
        try:
            await self.db.execute(
                update(BusinessEntity)
                .where(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.deleted_at.is_(None),
                )
                .values(
                    is_active=False,
                    updated_at=datetime.now(timezone.utc),
                )
            )

            await self.db.commit()

            logger.info(
                "entity_deactivated",
                entity_id=str(entity_id),
                reason=reason,
                deactivated_by=str(deactivated_by),
            )

            return True

        except Exception as e:
            await self.db.rollback()
            logger.exception(
                "entity_deactivation_failed",
                entity_id=str(entity_id),
                **safe_error_log(e),
            )
            return False


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def get_master_data_hygiene_service(
    db: AsyncSession,
    inactivity_days: int = MasterDataHygieneService.DEFAULT_INACTIVITY_DAYS,
) -> MasterDataHygieneService:
    """Factory-Funktion für Dependency Injection."""
    return MasterDataHygieneService(db, inactivity_days=inactivity_days)


async def get_hygiene_service_with_settings(
    db: AsyncSession,
) -> MasterDataHygieneService:
    """
    Factory mit Settings aus Admin-Konfiguration.

    Laedt Einstellungen aus der Datenbank falls vorhanden.
    FUTURE: Wenn eine AdminSettings-Tabelle erstellt wird, hier laden:
        settings = await db.execute(select(AdminSettings).where(...))
        config = settings.scalar_one_or_none()
        if config:
            return MasterDataHygieneService(
                db,
                inactivity_days=config.inactivity_days or DEFAULT,
                auto_correct_confidence=config.auto_correct or DEFAULT,
            )
    """
    # Verwende Service-Defaults (keine persistierte Konfiguration)
    return MasterDataHygieneService(db)
