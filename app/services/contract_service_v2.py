# -*- coding: utf-8 -*-
"""
Contract Service V2 - Erweiterte Vertragsverwaltung für Ablage-System.

Vision 2.0 Features:
- Automatische Datumserkennung aus OCR-Text
- Kalendar-Integration (iCal Export)
- Erweiterte Erinnerungs-Workflows
- Vertragskettenverknüpfung
- Dokumenten-Linking (Many-to-Many)

SECURITY:
- NIEMALS Vertragsdetails oder Parteinamen in Logs (PII/Geschäftsgeheimnisse)
- Multi-Tenant via company_id Filter
- Sichere OCR-Text-Extraktion

Feinpoliert und durchdacht - Enterprise Contract Management V2.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Pattern
from uuid import UUID
import hashlib

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.safe_errors import safe_error_log
from app.core.datetime_utils import utc_now
from app.db.models import Document
from app.db.models_contract import (
    Contract,
    ContractDeadline,
    ContractObligation,
    ContractStatus,
    ContractType,
    ObligationStatus,
    RecurrencePattern,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants and Patterns
# =============================================================================


class DeadlineType(str, Enum):
    """Typen von Vertragsfristen."""

    TERMINATION_NOTICE = "termination_notice"  # Kündigungsfrist
    CONTRACT_EXPIRY = "contract_expiry"  # Vertragsablauf
    RENEWAL_DECISION = "renewal_decision"  # Verlängerungsentscheidung
    PRICE_ADJUSTMENT = "price_adjustment"  # Preisanpassung
    WARRANTY_EXPIRY = "warranty_expiry"  # Gewährleistungsende
    AUDIT_DUE = "audit_due"  # Audit fällig
    REVIEW_DUE = "review_due"  # Prüfung fällig
    CUSTOM = "custom"  # Benutzerdefiniert


class ReminderPriority(str, Enum):
    """Priorität von Erinnerungen."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Standard-Erinnerungstage vor Fristablauf
DEFAULT_REMINDER_DAYS = [90, 60, 30, 14, 7, 3, 1]

# Regex-Pattern für Datumserkennung (German Format)
DATE_PATTERNS: List[Tuple[Pattern, str]] = [
    # DD.MM.YYYY
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b"), "%d.%m.%Y"),
    # DD.MM.YY
    (re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{2})\b"), "%d.%m.%y"),
    # YYYY-MM-DD (ISO)
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "%Y-%m-%d"),
    # DD/MM/YYYY
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "%d/%m/%Y"),
    # Written German: "1. Januar 2026"
    (re.compile(r"\b(\d{1,2})\.\s*(Januar|Februar|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{4})\b", re.IGNORECASE), None),
]

# Monate für deutsche Datumserkennung
GERMAN_MONTHS = {
    "januar": 1, "februar": 2, "maerz": 3, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "dezember": 12,
}

# Keywords für Vertragsklauseln
CONTRACT_KEYWORDS = {
    "notice_period": [
        r"kündigungsfrist\s*(?:von\s*)?(\d+)\s*(tage|wochen|monate)",
        r"kündigungsfrist\s*(?:von\s*)?(\d+)\s*(tage|wochen|monate)",
        r"notice\s*period\s*(?:of\s*)?(\d+)\s*(days|weeks|months)",
        r"mit\s*einer\s*frist\s*von\s*(\d+)\s*(tagen|wochen|monaten)",
    ],
    "auto_renewal": [
        r"verlängert\s*sich\s*automatisch",
        r"verlängert\s*sich\s*automatisch",
        r"automatische\s*verlängerung",
        r"automatische\s*verlängerung",
        r"auto[- ]?renewal",
        r"stillschweigend[e]?\s*verlängerung",
    ],
    "duration": [
        r"laufzeit\s*(?:von\s*)?(\d+)\s*(monate|jahre)",
        r"vertragsdauer\s*(?:von\s*)?(\d+)\s*(monate|jahre)",
        r"gültig\s*(?:für\s*)?(\d+)\s*(monate|jahre)",
        r"gültig\s*(?:für\s*)?(\d+)\s*(monate|jahre)",
    ],
    "effective_date": [
        r"(?:gültig|gültig|wirksam)\s*(?:ab|vom)\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
        r"(?:in\s*kraft|inkrafttreten)\s*(?:ab|am|zum)\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
        r"beginn[t]?\s*(?:ab|am|zum)\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
    ],
    "expiration_date": [
        r"(?:endet|laeuft\s*(?:ab|aus)|gültig\s*bis)\s*(?:am|zum)?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
        r"(?:läuft\s*(?:ab|aus)|gültig\s*bis)\s*(?:am|zum)?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
        r"(?:vertragsende|ablaufdatum)\s*(?:am|ist|:)?\s*(\d{1,2}\.\d{1,2}\.\d{2,4})",
    ],
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ExtractedContractDates:
    """Aus OCR-Text extrahierte Vertragsdaten."""

    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    notice_period_days: Optional[int] = None
    notice_deadline: Optional[date] = None
    auto_renewal: bool = False
    renewal_period_months: Optional[int] = None
    duration_months: Optional[int] = None
    all_dates_found: List[date] = field(default_factory=list)
    confidence: float = 0.0
    extraction_notes: List[str] = field(default_factory=list)


@dataclass
class ICalEvent:
    """Event-Daten für iCal-Export."""

    uid: str
    summary: str
    description: str
    start_date: date
    end_date: Optional[date] = None
    location: Optional[str] = None
    alarm_days_before: List[int] = field(default_factory=lambda: [7, 1])
    categories: List[str] = field(default_factory=list)
    url: Optional[str] = None


@dataclass
class ContractWithDocuments:
    """Vertrag mit verknüpften Dokumenten."""

    contract: Contract
    primary_document: Optional[Document]
    linked_documents: List[Document]
    document_count: int


@dataclass
class ContractSearchResult:
    """Suchergebnis für Verträge."""

    contracts: List[Contract]
    total_count: int
    page: int
    page_size: int


# =============================================================================
# Contract Service V2
# =============================================================================


class ContractServiceV2:
    """
    Erweiterter Contract Service mit V2-Features.

    Features:
    - Automatische Datumserkennung aus OCR-Text
    - iCal-Export für Kalender-Integration
    - Erweiterte Erinnerungs-Workflows
    - Document-Linking (Many-to-Many)
    - Vertragskettenverknüpfung

    SECURITY:
    - Multi-Tenant via company_id Filter
    - Keine PII/Geschäftsgeheimnisse in Logs
    - Sichere OCR-Text-Verarbeitung
    """

    VERSION = "2.0"

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service mit Datenbankverbindung.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db

    # =========================================================================
    # Contract CRUD (Enhanced)
    # =========================================================================

    async def create_contract(
        self,
        company_id: UUID,
        title: str,
        contract_type: ContractType = ContractType.OTHER,
        document_id: Optional[UUID] = None,
        contract_number: Optional[str] = None,
        effective_date: Optional[date] = None,
        expiration_date: Optional[date] = None,
        notice_period_days: Optional[int] = None,
        auto_renewal: bool = False,
        renewal_period_months: Optional[int] = None,
        total_value: Optional[Decimal] = None,
        counterparty_entity_id: Optional[UUID] = None,
        our_role: Optional[str] = None,
        parties: Optional[List[Dict[str, Any]]] = None,
        clauses: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        created_by_id: Optional[UUID] = None,
        extract_from_document: bool = True,
    ) -> Contract:
        """
        Erstellt einen neuen Vertrag.

        Args:
            company_id: Mandanten-ID
            title: Vertragstitel
            contract_type: Vertragstyp
            document_id: Optional - Verknüpftes Dokument
            contract_number: Vertragsnummer
            effective_date: Startdatum
            expiration_date: Enddatum
            notice_period_days: Kündigungsfrist in Tagen
            auto_renewal: Automatische Verlängerung
            renewal_period_months: Verlängerungszeitraum
            total_value: Vertragswert
            counterparty_entity_id: Vertragspartner-ID
            our_role: Unsere Rolle (buyer, seller, etc.)
            parties: Liste der Vertragsparteien
            clauses: Extrahierte Klauseln
            tags: Tags zur Kategorisierung
            notes: Notizen
            created_by_id: Ersteller-ID
            extract_from_document: Daten aus Dokument extrahieren

        Returns:
            Erstellter Vertrag
        """
        # Optional: Daten aus verknüpftem Dokument extrahieren
        extracted_data = None
        if extract_from_document and document_id:
            extracted_data = await self.extract_dates_from_document(document_id, company_id)

            # Extrahierte Daten verwenden wenn keine expliziten Werte
            if extracted_data:
                if not effective_date and extracted_data.effective_date:
                    effective_date = extracted_data.effective_date
                if not expiration_date and extracted_data.expiration_date:
                    expiration_date = extracted_data.expiration_date
                if not notice_period_days and extracted_data.notice_period_days:
                    notice_period_days = extracted_data.notice_period_days
                if not auto_renewal and extracted_data.auto_renewal:
                    auto_renewal = extracted_data.auto_renewal
                if not renewal_period_months and extracted_data.renewal_period_months:
                    renewal_period_months = extracted_data.renewal_period_months

        contract = Contract(
            company_id=company_id,
            title=title,
            contract_type=contract_type.value if isinstance(contract_type, ContractType) else contract_type,
            status=ContractStatus.DRAFT.value,
            document_id=document_id,
            contract_number=contract_number,
            effective_date=effective_date,
            expiration_date=expiration_date,
            notice_period_days=notice_period_days,
            auto_renewal=auto_renewal,
            renewal_period_months=renewal_period_months,
            total_value=total_value,
            counterparty_entity_id=counterparty_entity_id,
            our_role=our_role,
            parties=parties or [],
            clauses=clauses or {},
            tags=tags or [],
            notes=notes,
            created_by_id=created_by_id,
            extraction_confidence=Decimal(str(extracted_data.confidence)) if extracted_data else None,
        )

        self.db.add(contract)
        await self.db.flush()

        # Standard-Deadlines erstellen
        if expiration_date:
            await self._create_standard_deadlines(contract)

        await self.db.commit()
        await self.db.refresh(contract)

        logger.info(
            "contract_created_v2",
            contract_id=str(contract.id),
            has_document=bool(document_id),
            extracted_data=bool(extracted_data),
        )

        return contract

    async def get_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
        include_documents: bool = False,
        include_deadlines: bool = False,
        include_obligations: bool = False,
    ) -> Optional[Contract]:
        """
        Ruft einen Vertrag ab.

        Args:
            contract_id: Vertrags-ID
            company_id: Mandanten-ID
            include_documents: Dokumente laden
            include_deadlines: Deadlines laden
            include_obligations: Pflichten laden

        Returns:
            Vertrag oder None
        """
        query = select(Contract).where(
            and_(
                Contract.id == contract_id,
                Contract.company_id == company_id,
            )
        )

        if include_deadlines:
            query = query.options(selectinload(Contract.deadlines))

        if include_obligations:
            query = query.options(selectinload(Contract.obligations))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
        updated_by_id: Optional[UUID] = None,
        **updates: object,
    ) -> Optional[Contract]:
        """
        Aktualisiert einen Vertrag.

        Args:
            contract_id: Vertrags-ID
            company_id: Mandanten-ID
            updated_by_id: ID des aktualisierenden Benutzers
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierter Vertrag oder None
        """
        contract = await self.get_contract(contract_id, company_id)
        if not contract:
            return None

        # Erlaubte Update-Felder
        allowed_fields = {
            "title", "contract_type", "status", "contract_number",
            "effective_date", "expiration_date", "notice_period_days",
            "auto_renewal", "renewal_period_months", "total_value",
            "counterparty_entity_id", "our_role", "parties", "clauses",
            "tags", "notes", "currency", "payment_terms",
        }

        for field_name, value in updates.items():
            if field_name in allowed_fields and value is not None:
                setattr(contract, field_name, value)

        contract.updated_at = utc_now()
        contract.updated_by_id = updated_by_id

        # Deadlines aktualisieren wenn Enddatum geändert
        if "expiration_date" in updates:
            await self._update_deadlines_for_expiration_change(contract)

        await self.db.commit()
        await self.db.refresh(contract)

        logger.info(
            "contract_updated_v2",
            contract_id=str(contract_id),
            updated_fields=list(updates.keys()),
        )

        return contract

    async def activate_contract(
        self,
        contract_id: UUID,
        company_id: UUID,
        signed_date: Optional[date] = None,
    ) -> Optional[Contract]:
        """
        Aktiviert einen Vertrag (DRAFT -> ACTIVE).

        Args:
            contract_id: Vertrags-ID
            company_id: Mandanten-ID
            signed_date: Unterschriftsdatum

        Returns:
            Aktivierter Vertrag oder None
        """
        contract = await self.get_contract(contract_id, company_id)
        if not contract:
            return None

        if contract.status != ContractStatus.DRAFT.value:
            logger.warning(
                "contract_activate_invalid_status",
                contract_id=str(contract_id),
                current_status=contract.status,
            )
            return None

        contract.status = ContractStatus.ACTIVE.value
        contract.signed_date = signed_date or date.today()
        contract.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(contract)

        logger.info(
            "contract_activated",
            contract_id=str(contract_id),
        )

        return contract

    # =========================================================================
    # OCR Date Extraction
    # =========================================================================

    async def extract_dates_from_document(
        self,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[ExtractedContractDates]:
        """
        Extrahiert Vertragsdaten aus OCR-Text eines Dokuments.

        Args:
            document_id: Dokument-ID
            company_id: Mandanten-ID

        Returns:
            Extrahierte Vertragsdaten oder None
        """
        # Dokument laden
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        document = result.scalar_one_or_none()

        if not document or not document.ocr_text:
            return None

        return self._extract_dates_from_text(document.ocr_text)

    def _extract_dates_from_text(self, text: str) -> ExtractedContractDates:
        """
        Extrahiert Vertragsdaten aus OCR-Text.

        Args:
            text: OCR-Text des Dokuments

        Returns:
            Extrahierte Vertragsdaten
        """
        extracted = ExtractedContractDates()
        text_lower = text.lower()

        # 1. Alle Daten im Text finden
        all_dates = self._find_all_dates(text)
        extracted.all_dates_found = all_dates

        # 2. Spezifische Daten extrahieren
        # Startdatum
        for pattern in CONTRACT_KEYWORDS["effective_date"]:
            match = re.search(pattern, text_lower)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_german_date(date_str)
                if parsed_date:
                    extracted.effective_date = parsed_date
                    extracted.extraction_notes.append(f"Startdatum gefunden: {date_str}")
                    break

        # Enddatum
        for pattern in CONTRACT_KEYWORDS["expiration_date"]:
            match = re.search(pattern, text_lower)
            if match:
                date_str = match.group(1)
                parsed_date = self._parse_german_date(date_str)
                if parsed_date:
                    extracted.expiration_date = parsed_date
                    extracted.extraction_notes.append(f"Enddatum gefunden: {date_str}")
                    break

        # 3. Kündigungsfrist
        for pattern in CONTRACT_KEYWORDS["notice_period"]:
            match = re.search(pattern, text_lower)
            if match:
                value = int(match.group(1))
                unit = match.group(2).lower()

                # In Tage umrechnen
                if "woche" in unit:
                    extracted.notice_period_days = value * 7
                elif "monat" in unit or "month" in unit:
                    extracted.notice_period_days = value * 30
                else:
                    extracted.notice_period_days = value

                extracted.extraction_notes.append(f"Kündigungsfrist: {value} {unit}")
                break

        # 4. Automatische Verlängerung
        for pattern in CONTRACT_KEYWORDS["auto_renewal"]:
            if re.search(pattern, text_lower):
                extracted.auto_renewal = True
                extracted.extraction_notes.append("Automatische Verlängerung erkannt")
                break

        # 5. Laufzeit/Dauer
        for pattern in CONTRACT_KEYWORDS["duration"]:
            match = re.search(pattern, text_lower)
            if match:
                value = int(match.group(1))
                unit = match.group(2).lower()

                if "jahr" in unit or "year" in unit:
                    extracted.duration_months = value * 12
                else:
                    extracted.duration_months = value

                extracted.extraction_notes.append(f"Laufzeit: {value} {unit}")

                # Wenn Startdatum vorhanden, Enddatum berechnen
                if extracted.effective_date and not extracted.expiration_date:
                    extracted.expiration_date = self._add_months(
                        extracted.effective_date,
                        extracted.duration_months
                    )
                    extracted.extraction_notes.append("Enddatum aus Laufzeit berechnet")
                break

        # 6. Kündigungsfrist berechnen
        if extracted.expiration_date and extracted.notice_period_days:
            extracted.notice_deadline = (
                extracted.expiration_date - timedelta(days=extracted.notice_period_days)
            )

        # 7. Konfidenz berechnen
        confidence_factors = 0
        if extracted.effective_date:
            confidence_factors += 0.25
        if extracted.expiration_date:
            confidence_factors += 0.25
        if extracted.notice_period_days:
            confidence_factors += 0.2
        if extracted.auto_renewal:
            confidence_factors += 0.15
        if extracted.duration_months:
            confidence_factors += 0.15

        extracted.confidence = min(1.0, confidence_factors)

        logger.debug(
            "contract_dates_extracted",
            effective_date=str(extracted.effective_date) if extracted.effective_date else None,
            expiration_date=str(extracted.expiration_date) if extracted.expiration_date else None,
            notice_days=extracted.notice_period_days,
            auto_renewal=extracted.auto_renewal,
            confidence=extracted.confidence,
        )

        return extracted

    def _find_all_dates(self, text: str) -> List[date]:
        """Findet alle Daten im Text."""
        dates: List[date] = []

        for pattern, date_format in DATE_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    if date_format:
                        # Standard-Format
                        parsed = datetime.strptime(match.group(0), date_format).date()
                    else:
                        # Deutsches geschriebenes Format
                        day = int(match.group(1))
                        month_name = match.group(2).lower()
                        year = int(match.group(3))
                        month = GERMAN_MONTHS.get(month_name, 1)
                        parsed = date(year, month, day)

                    # Plausibilitaetsprüfung
                    if date(1990, 1, 1) <= parsed <= date(2100, 12, 31):
                        dates.append(parsed)
                except (ValueError, KeyError):
                    continue

        return sorted(set(dates))

    def _parse_german_date(self, date_str: str) -> Optional[date]:
        """Parst deutsches Datumsformat."""
        for pattern, date_format in DATE_PATTERNS[:3]:  # Nur numerische Formate
            if pattern.match(date_str):
                try:
                    if date_format:
                        return datetime.strptime(date_str, date_format).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _add_months(d: date, months: int) -> date:
        """Addiert Monate zu einem Datum."""
        month = d.month - 1 + months
        year = d.year + month // 12
        month = month % 12 + 1

        # Korrektur für Tage die im Zielmonat nicht existieren
        import calendar
        max_day = calendar.monthrange(year, month)[1]
        day = min(d.day, max_day)

        return date(year, month, day)

    # =========================================================================
    # Deadlines & Reminders
    # =========================================================================

    async def _create_standard_deadlines(self, contract: Contract) -> List[ContractDeadline]:
        """Erstellt Standard-Deadlines für einen Vertrag."""
        deadlines: List[ContractDeadline] = []

        if not contract.expiration_date:
            return deadlines

        # 1. Vertragsablauf-Deadline
        expiry_deadline = ContractDeadline(
            contract_id=contract.id,
            company_id=contract.company_id,
            deadline_type=DeadlineType.CONTRACT_EXPIRY.value,
            title="Vertragsablauf",
            description=f"Der Vertrag laeuft am {contract.expiration_date.strftime('%d.%m.%Y')} ab.",
            deadline_date=contract.expiration_date,
            priority="high",
            reminder_days_before=DEFAULT_REMINDER_DAYS,
        )
        self.db.add(expiry_deadline)
        deadlines.append(expiry_deadline)

        # 2. Kündigungsfrist-Deadline
        if contract.notice_period_days:
            notice_date = contract.expiration_date - timedelta(days=contract.notice_period_days)

            if notice_date > date.today():
                notice_deadline = ContractDeadline(
                    contract_id=contract.id,
                    company_id=contract.company_id,
                    deadline_type=DeadlineType.TERMINATION_NOTICE.value,
                    title="Kündigungsfrist",
                    description=f"Kündigung muss bis {notice_date.strftime('%d.%m.%Y')} erfolgen.",
                    deadline_date=notice_date,
                    priority="critical",
                    reminder_days_before=[30, 14, 7, 3, 1],
                )
                self.db.add(notice_deadline)
                deadlines.append(notice_deadline)

        # 3. Verlängerungsentscheidung-Deadline (wenn auto_renewal)
        if contract.auto_renewal and contract.notice_period_days:
            decision_date = contract.expiration_date - timedelta(
                days=contract.notice_period_days + 14  # 2 Wochen vor Kündigungsfrist
            )

            if decision_date > date.today():
                decision_deadline = ContractDeadline(
                    contract_id=contract.id,
                    company_id=contract.company_id,
                    deadline_type=DeadlineType.RENEWAL_DECISION.value,
                    title="Verlängerungsentscheidung",
                    description="Entscheidung über Kündigung oder Verlängerung erforderlich.",
                    deadline_date=decision_date,
                    priority="high",
                    reminder_days_before=[14, 7, 3],
                )
                self.db.add(decision_deadline)
                deadlines.append(decision_deadline)

        await self.db.flush()

        logger.debug(
            "contract_deadlines_created",
            contract_id=str(contract.id),
            deadline_count=len(deadlines),
        )

        return deadlines

    async def _update_deadlines_for_expiration_change(self, contract: Contract) -> None:
        """Aktualisiert Deadlines nach Änderung des Enddatums."""
        # Bestehende automatische Deadlines löschen
        await self.db.execute(
            update(ContractDeadline)
            .where(
                and_(
                    ContractDeadline.contract_id == contract.id,
                    ContractDeadline.deadline_type.in_([
                        DeadlineType.CONTRACT_EXPIRY.value,
                        DeadlineType.TERMINATION_NOTICE.value,
                        DeadlineType.RENEWAL_DECISION.value,
                    ]),
                    ContractDeadline.is_completed == False,
                )
            )
            .values(is_completed=True)
        )

        # Neue Deadlines erstellen
        await self._create_standard_deadlines(contract)

    async def get_upcoming_deadlines(
        self,
        company_id: UUID,
        days_ahead: int = 90,
        deadline_types: Optional[List[str]] = None,
    ) -> List[ContractDeadline]:
        """
        Ruft bevorstehende Vertragsfristen ab.

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen
            deadline_types: Filter für Fristtypen

        Returns:
            Liste von Deadlines
        """
        today = date.today()
        cutoff_date = today + timedelta(days=days_ahead)

        query = (
            select(ContractDeadline)
            .join(Contract)
            .where(
                and_(
                    ContractDeadline.company_id == company_id,
                    ContractDeadline.is_completed == False,
                    ContractDeadline.deadline_date >= today,
                    ContractDeadline.deadline_date <= cutoff_date,
                    Contract.status.in_([
                        ContractStatus.ACTIVE.value,
                        ContractStatus.DRAFT.value,
                    ]),
                )
            )
            .order_by(ContractDeadline.deadline_date.asc())
        )

        if deadline_types:
            query = query.where(ContractDeadline.deadline_type.in_(deadline_types))

        query = query.options(selectinload(ContractDeadline.contract))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def complete_deadline(
        self,
        deadline_id: UUID,
        company_id: UUID,
        completed_by_id: Optional[UUID] = None,
        action_taken: Optional[str] = None,
    ) -> Optional[ContractDeadline]:
        """
        Markiert eine Deadline als erledigt.

        Args:
            deadline_id: Deadline-ID
            company_id: Mandanten-ID
            completed_by_id: ID des abschließenden Benutzers
            action_taken: Beschreibung der durchgeführten Aktion

        Returns:
            Aktualisierte Deadline oder None
        """
        result = await self.db.execute(
            select(ContractDeadline).where(
                and_(
                    ContractDeadline.id == deadline_id,
                    ContractDeadline.company_id == company_id,
                )
            )
        )
        deadline = result.scalar_one_or_none()

        if not deadline:
            return None

        deadline.is_completed = True
        deadline.completed_at = utc_now()
        deadline.completed_by_id = completed_by_id
        deadline.action_taken = action_taken

        await self.db.commit()
        await self.db.refresh(deadline)

        logger.info(
            "deadline_completed",
            deadline_id=str(deadline_id),
            contract_id=str(deadline.contract_id),
        )

        return deadline

    # =========================================================================
    # iCal Export
    # =========================================================================

    async def export_deadlines_to_ical(
        self,
        company_id: UUID,
        days_ahead: int = 365,
        contract_ids: Optional[List[UUID]] = None,
    ) -> str:
        """
        Exportiert Vertragsfristen als iCal-Datei.

        Args:
            company_id: Mandanten-ID
            days_ahead: Vorausschau in Tagen
            contract_ids: Optional - nur bestimmte Verträge

        Returns:
            iCal-String
        """
        # Deadlines laden
        query = (
            select(ContractDeadline)
            .join(Contract)
            .where(
                and_(
                    ContractDeadline.company_id == company_id,
                    ContractDeadline.is_completed == False,
                    ContractDeadline.deadline_date >= date.today(),
                    ContractDeadline.deadline_date <= date.today() + timedelta(days=days_ahead),
                )
            )
            .options(selectinload(ContractDeadline.contract))
        )

        if contract_ids:
            query = query.where(ContractDeadline.contract_id.in_(contract_ids))

        result = await self.db.execute(query)
        deadlines = result.scalars().all()

        # iCal generieren
        events: List[ICalEvent] = []

        for deadline in deadlines:
            contract_title = deadline.contract.title[:50] if deadline.contract.title else "Vertrag"

            # Erinnerungstage aus Deadline
            alarm_days = deadline.reminder_days_before or [7, 1]

            event = ICalEvent(
                uid=self._generate_ical_uid(deadline),
                summary=f"[Vertrag] {deadline.title}",
                description=f"Vertrag: {contract_title}\n\n{deadline.description or ''}",
                start_date=deadline.deadline_date,
                alarm_days_before=alarm_days[:3],  # Max 3 Alarme
                categories=["Vertragsmanagement", deadline.deadline_type],
            )
            events.append(event)

        return self._generate_ical_string(events, "Ablage-System Vertragsfristen")

    def _generate_ical_uid(self, deadline: ContractDeadline) -> str:
        """Generiert eindeutige UID für iCal-Event."""
        data = f"{deadline.id}_{deadline.contract_id}_{deadline.deadline_date}"
        return f"{hashlib.md5(data.encode()).hexdigest()}@ablage-system"

    def _generate_ical_string(self, events: List[ICalEvent], calendar_name: str) -> str:
        """Generiert iCal-String aus Events."""
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Ablage-System//Contract Management V2//DE",
            f"X-WR-CALNAME:{calendar_name}",
            "METHOD:PUBLISH",
            "CALSCALE:GREGORIAN",
        ]

        for event in events:
            lines.extend([
                "BEGIN:VEVENT",
                f"UID:{event.uid}",
                f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART;VALUE=DATE:{event.start_date.strftime('%Y%m%d')}",
                f"SUMMARY:{self._escape_ical_text(event.summary)}",
                f"DESCRIPTION:{self._escape_ical_text(event.description)}",
            ])

            if event.categories:
                lines.append(f"CATEGORIES:{','.join(event.categories)}")

            if event.url:
                lines.append(f"URL:{event.url}")

            # Alarme
            for days in event.alarm_days_before:
                lines.extend([
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"TRIGGER:-P{days}D",
                    f"DESCRIPTION:Erinnerung: {event.summary}",
                    "END:VALARM",
                ])

            lines.append("END:VEVENT")

        lines.append("END:VCALENDAR")

        return "\r\n".join(lines)

    @staticmethod
    def _escape_ical_text(text: str) -> str:
        """Escaped Text für iCal-Format."""
        return (
            text.replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    # =========================================================================
    # Document Linking
    # =========================================================================

    async def link_document(
        self,
        contract_id: UUID,
        document_id: UUID,
        company_id: UUID,
        is_primary: bool = False,
    ) -> bool:
        """
        Verknüpft ein Dokument mit einem Vertrag.

        Args:
            contract_id: Vertrags-ID
            document_id: Dokument-ID
            company_id: Mandanten-ID
            is_primary: Als Hauptdokument setzen

        Returns:
            True bei Erfolg
        """
        # Vertrag und Dokument prüfen
        contract = await self.get_contract(contract_id, company_id)
        if not contract:
            return False

        doc_result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        document = doc_result.scalar_one_or_none()

        if not document:
            return False

        if is_primary:
            contract.document_id = document_id
        else:
            # Zu zusätzlichen Dokumenten hinzufuegen (via JSONB)
            linked_docs = contract.clauses.get("linked_documents", []) if contract.clauses else []
            if str(document_id) not in linked_docs:
                linked_docs.append(str(document_id))
                if contract.clauses:
                    contract.clauses["linked_documents"] = linked_docs
                else:
                    contract.clauses = {"linked_documents": linked_docs}

        await self.db.commit()

        logger.info(
            "document_linked_to_contract",
            contract_id=str(contract_id),
            document_id=str(document_id),
            is_primary=is_primary,
        )

        return True

    async def get_linked_documents(
        self,
        contract_id: UUID,
        company_id: UUID,
    ) -> List[Document]:
        """
        Ruft alle verknüpften Dokumente eines Vertrags ab.

        Args:
            contract_id: Vertrags-ID
            company_id: Mandanten-ID

        Returns:
            Liste von Dokumenten
        """
        contract = await self.get_contract(contract_id, company_id)
        if not contract:
            return []

        document_ids: List[UUID] = []

        # Hauptdokument
        if contract.document_id:
            document_ids.append(contract.document_id)

        # Zusätzliche Dokumente aus clauses
        if contract.clauses:
            linked_docs = contract.clauses.get("linked_documents", [])
            for doc_id_str in linked_docs:
                try:
                    document_ids.append(UUID(doc_id_str))
                except ValueError:
                    continue

        if not document_ids:
            return []

        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id.in_(document_ids),
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )

        return list(result.scalars().all())

    # =========================================================================
    # Search & Filtering
    # =========================================================================

    async def search_contracts(
        self,
        company_id: UUID,
        query: Optional[str] = None,
        status: Optional[List[ContractStatus]] = None,
        contract_type: Optional[List[ContractType]] = None,
        counterparty_id: Optional[UUID] = None,
        expiring_within_days: Optional[int] = None,
        min_value: Optional[Decimal] = None,
        max_value: Optional[Decimal] = None,
        tags: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 20,
        order_by: str = "expiration_date",
        order_desc: bool = False,
    ) -> ContractSearchResult:
        """
        Sucht Verträge mit erweiterten Filteroptionen.

        Args:
            company_id: Mandanten-ID
            query: Volltextsuche in Titel und Nummer
            status: Status-Filter
            contract_type: Vertragstyp-Filter
            counterparty_id: Vertragspartner-Filter
            expiring_within_days: Ablauffilter
            min_value: Mindestwert
            max_value: Maximalwert
            tags: Tag-Filter
            page: Seitennummer
            page_size: Einträge pro Seite
            order_by: Sortierfeld
            order_desc: Absteigende Sortierung

        Returns:
            Suchergebnis
        """
        base_query = select(Contract).where(Contract.company_id == company_id)

        # Filter anwenden
        if query:
            search_pattern = f"%{query}%"
            base_query = base_query.where(
                or_(
                    Contract.title.ilike(search_pattern),
                    Contract.contract_number.ilike(search_pattern),
                )
            )

        if status:
            status_values = [s.value if isinstance(s, ContractStatus) else s for s in status]
            base_query = base_query.where(Contract.status.in_(status_values))

        if contract_type:
            type_values = [t.value if isinstance(t, ContractType) else t for t in contract_type]
            base_query = base_query.where(Contract.contract_type.in_(type_values))

        if counterparty_id:
            base_query = base_query.where(Contract.counterparty_entity_id == counterparty_id)

        if expiring_within_days:
            cutoff = date.today() + timedelta(days=expiring_within_days)
            base_query = base_query.where(
                and_(
                    Contract.expiration_date.isnot(None),
                    Contract.expiration_date <= cutoff,
                    Contract.expiration_date >= date.today(),
                )
            )

        if min_value is not None:
            base_query = base_query.where(Contract.total_value >= min_value)

        if max_value is not None:
            base_query = base_query.where(Contract.total_value <= max_value)

        if tags:
            for tag in tags:
                base_query = base_query.where(Contract.tags.contains([tag]))

        # Gesamtanzahl
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await self.db.execute(count_query)
        total_count = total_result.scalar() or 0

        # Sortierung
        order_column = getattr(Contract, order_by, Contract.expiration_date)
        if order_desc:
            base_query = base_query.order_by(order_column.desc())
        else:
            base_query = base_query.order_by(order_column.asc())

        # Pagination
        offset = (page - 1) * page_size
        base_query = base_query.offset(offset).limit(page_size)

        result = await self.db.execute(base_query)
        contracts = list(result.scalars().all())

        return ContractSearchResult(
            contracts=contracts,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )

    # =========================================================================
    # Statistics
    # =========================================================================

    async def get_contract_statistics(
        self,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Ruft Vertragsstatistiken ab.

        Args:
            company_id: Mandanten-ID

        Returns:
            Statistiken
        """
        today = date.today()

        # Grundstatistiken
        stats_query = select(
            func.count(Contract.id).label("total"),
            func.sum(
                func.case(
                    (Contract.status == ContractStatus.ACTIVE.value, 1),
                    else_=0
                )
            ).label("active"),
            func.sum(Contract.total_value).label("total_value"),
        ).where(
            and_(
                Contract.company_id == company_id,
                Contract.status != ContractStatus.TERMINATED.value,
            )
        )

        result = await self.db.execute(stats_query)
        row = result.one()

        # Ablaufende in 30/60/90 Tagen
        expiring_query = select(
            func.count(Contract.id)
        ).where(
            and_(
                Contract.company_id == company_id,
                Contract.status == ContractStatus.ACTIVE.value,
                Contract.expiration_date.isnot(None),
                Contract.expiration_date >= today,
            )
        )

        expiring_30_result = await self.db.execute(
            expiring_query.where(Contract.expiration_date <= today + timedelta(days=30))
        )
        expiring_60_result = await self.db.execute(
            expiring_query.where(Contract.expiration_date <= today + timedelta(days=60))
        )
        expiring_90_result = await self.db.execute(
            expiring_query.where(Contract.expiration_date <= today + timedelta(days=90))
        )

        return {
            "total_contracts": row.total or 0,
            "active_contracts": row.active or 0,
            "total_value": float(row.total_value or 0),
            "expiring_30_days": expiring_30_result.scalar() or 0,
            "expiring_60_days": expiring_60_result.scalar() or 0,
            "expiring_90_days": expiring_90_result.scalar() or 0,
            "currency": "EUR",
            "generated_at": utc_now().isoformat(),
        }


# =============================================================================
# Factory Function
# =============================================================================


def get_contract_service_v2(db: AsyncSession) -> ContractServiceV2:
    """Factory-Funktion für ContractServiceV2."""
    return ContractServiceV2(db)


# Alias für Kompatibilität
ContractService = ContractServiceV2
get_contract_service = get_contract_service_v2
