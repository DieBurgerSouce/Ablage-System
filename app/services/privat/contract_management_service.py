# -*- coding: utf-8 -*-
"""
Service fuer die Verwaltung von privaten Vertraegen im Privat-Modul.

P5.1: Vertragsmanagement mit automatischer Erkennung und Erinnerungssystem.

Features:
- OCR-basierte Vertragserkennung (Regex-Patterns fuer deutsche Vertraege)
- Automatische Kuendigungsfrist-Berechnung
- Erinnerungen via Alert Center
- CRUD-Operationen mit Space-basiertem Zugriff

Feinpoliert und durchdacht.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.datetime_utils import utc_now
from app.db.models_privat_contracts import (
    PrivatContract,
    PrivatContractCategory,
    PrivatContractReminder,
    PrivatContractStatus,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ContractInfo:
    """Extrahierte Vertragsinformationen aus OCR-Text."""
    partner_name: str
    start_date: Optional[date]
    duration_months: Optional[int]
    cancellation_notice_days: Optional[int]
    next_cancellation_date: Optional[date]
    monthly_cost: Optional[Decimal]
    yearly_cost: Optional[Decimal]
    category: str
    confidence: float
    raw_fields: Dict[str, str] = field(default_factory=dict)


# =============================================================================
# German Date/Period Regex Patterns
# =============================================================================

# Date patterns: DD.MM.YYYY, DD.MM.YY, DD. Monat YYYY
_DATE_PATTERNS = [
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})",
    r"(\d{1,2})\.(\d{1,2})\.(\d{2})\b",
    r"(\d{1,2})\.\s*(Januar|Februar|Maerz|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{4})",
]

_MONTH_MAP = {
    "januar": 1, "februar": 2, "maerz": 3, "märz": 3,
    "april": 4, "mai": 5, "juni": 6, "juli": 7,
    "august": 8, "september": 9, "oktober": 10,
    "november": 11, "dezember": 12,
}

# Period patterns
_PERIOD_PATTERNS = {
    "months": [
        r"(\d+)\s*Monat(?:e|en)?",
        r"Laufzeit[:\s]+(\d+)\s*Monat",
        r"Vertragslaufzeit[:\s]+(\d+)\s*Monat",
        r"Mindestlaufzeit[:\s]+(\d+)\s*Monat",
    ],
    "years": [
        r"(\d+)\s*Jahr(?:e|en)?",
        r"Laufzeit[:\s]+(\d+)\s*Jahr",
        r"Vertragslaufzeit[:\s]+(\d+)\s*Jahr",
    ],
}

# Cancellation notice patterns
_CANCELLATION_PATTERNS = [
    r"K(?:ü|ue)ndigungsfrist[:\s]+(\d+)\s*Monat",
    r"K(?:ü|ue)ndigungsfrist[:\s]+(\d+)\s*Woch",
    r"K(?:ü|ue)ndigungsfrist[:\s]+(\d+)\s*Tag",
    r"(\d+)\s*Monat(?:e|en)?\s+(?:vor|zum)\s+(?:Vertragsende|Laufzeitende)",
    r"(\d+)\s*Woch(?:e|en)?\s+(?:vor|zum)\s+(?:Vertragsende|Laufzeitende)",
]

# Cost patterns
_COST_PATTERNS = {
    "monthly": [
        r"(\d+[.,]\d{2})\s*(?:EUR|€)\s*/\s*Monat",
        r"monatlich[:\s]+(\d+[.,]\d{2})\s*(?:EUR|€)?",
        r"mtl\.\s*(\d+[.,]\d{2})\s*(?:EUR|€)?",
        r"(\d+[.,]\d{2})\s*(?:EUR|€)\s*(?:pro\s+Monat|monatlich|mtl\.)",
        r"Monatsbeitrag[:\s]+(\d+[.,]\d{2})",
        r"Grundgeb(?:ü|ue)hr[:\s]+(\d+[.,]\d{2})",
    ],
    "yearly": [
        r"(\d+[.,]\d{2})\s*(?:EUR|€)\s*/\s*Jahr",
        r"j(?:ä|ae)hrlich[:\s]+(\d+[.,]\d{2})\s*(?:EUR|€)?",
        r"(\d+[.,]\d{2})\s*(?:EUR|€)\s*(?:pro\s+Jahr|j(?:ä|ae)hrlich)",
        r"Jahresbeitrag[:\s]+(\d+[.,]\d{2})",
    ],
}

# Category detection keywords
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    PrivatContractCategory.MOBILFUNK.value: [
        "mobilfunk", "handy", "smartphone", "sim", "telefon",
        "telekom", "vodafone", "o2", "congstar", "aldi talk",
    ],
    PrivatContractCategory.INTERNET.value: [
        "internet", "dsl", "glasfaser", "breitband", "router",
        "wlan", "wifi",
    ],
    PrivatContractCategory.STROM.value: [
        "strom", "elektrizit", "kwh", "kilowattstunde",
        "stromlieferung", "energieversorgung",
    ],
    PrivatContractCategory.GAS.value: [
        "gas", "erdgas", "gasversorgung", "gaslieferung",
    ],
    PrivatContractCategory.VERSICHERUNG.value: [
        "versicherung", "police", "praemie", "prämie",
        "deckungssumme", "selbstbeteiligung", "schadenfall",
    ],
    PrivatContractCategory.MIETE.value: [
        "mietvertrag", "miete", "kaltmiete", "warmmiete",
        "nebenkosten", "vermieter", "mieter", "wohnung",
    ],
    PrivatContractCategory.FITNESS.value: [
        "fitness", "fitnessstudio", "gym", "sportstudio",
        "mitgliedschaft", "training",
    ],
    PrivatContractCategory.STREAMING.value: [
        "streaming", "netflix", "disney", "spotify", "amazon prime",
        "dazn", "sky", "apple music", "youtube premium",
    ],
    PrivatContractCategory.ZEITSCHRIFT.value: [
        "zeitschrift", "abonnement", "abo", "magazin", "zeitung",
    ],
    PrivatContractCategory.VEREIN.value: [
        "verein", "mitgliedsbeitrag", "vereinsbeitrag",
    ],
    PrivatContractCategory.CLOUD_SPEICHER.value: [
        "cloud", "speicher", "icloud", "dropbox", "onedrive",
        "google drive",
    ],
    PrivatContractCategory.SOFTWARE.value: [
        "software", "lizenz", "saas", "microsoft 365", "office",
        "adobe", "antivirus",
    ],
    PrivatContractCategory.LEASING.value: [
        "leasing", "leasingvertrag", "leasingrate",
        "fahrzeugleasing",
    ],
    PrivatContractCategory.WARTUNG.value: [
        "wartung", "wartungsvertrag", "service", "instandhaltung",
    ],
}


# =============================================================================
# Service
# =============================================================================


class PrivatContractManagementService:
    """Service fuer private Vertragsverwaltung."""

    # -------------------------------------------------------------------------
    # OCR Extraction
    # -------------------------------------------------------------------------

    def extract_contract_fields(self, ocr_text: str) -> ContractInfo:
        """Extrahiert Vertragsfelder aus OCR-Text.

        Analysiert den Text mit Regex-Patterns fuer deutsche Vertraege
        und gibt strukturierte Vertragsinformationen zurueck.

        Args:
            ocr_text: Der OCR-extrahierte Text

        Returns:
            ContractInfo mit extrahierten Feldern
        """
        text_lower = ocr_text.lower()
        raw_fields: Dict[str, str] = {}
        confidence_factors: List[float] = []

        # 1. Kategorie erkennen
        category = self._detect_category(text_lower)
        if category != PrivatContractCategory.SONSTIGE.value:
            confidence_factors.append(0.3)
        raw_fields["kategorie"] = category

        # 2. Vertragspartner extrahieren
        partner = self._extract_partner_name(ocr_text)
        if partner:
            confidence_factors.append(0.2)
            raw_fields["vertragspartner"] = partner

        # 3. Startdatum
        start_date = self._extract_date_near_keyword(
            ocr_text, ["vertragsbeginn", "beginn", "ab dem", "gueltig ab", "gültig ab", "startdatum"]
        )
        if start_date:
            confidence_factors.append(0.1)
            raw_fields["vertragsbeginn"] = start_date.isoformat()

        # 4. Laufzeit
        duration_months = self._extract_duration_months(ocr_text)
        if duration_months:
            confidence_factors.append(0.1)
            raw_fields["laufzeit_monate"] = str(duration_months)

        # 5. Kuendigungsfrist
        cancel_days = self._extract_cancellation_notice(ocr_text)
        if cancel_days:
            confidence_factors.append(0.15)
            raw_fields["kuendigungsfrist_tage"] = str(cancel_days)

        # 6. Kosten
        monthly_cost = self._extract_cost(ocr_text, "monthly")
        yearly_cost = self._extract_cost(ocr_text, "yearly")

        if monthly_cost and not yearly_cost:
            yearly_cost = monthly_cost * 12
        elif yearly_cost and not monthly_cost:
            monthly_cost = yearly_cost / 12

        if monthly_cost:
            confidence_factors.append(0.15)
            raw_fields["monatliche_kosten"] = str(monthly_cost)
        if yearly_cost:
            raw_fields["jaehrliche_kosten"] = str(yearly_cost)

        # 7. Naechstes Kuendigungsdatum berechnen
        next_cancel = self._calculate_next_cancellation_date(
            start_date, duration_months, cancel_days
        )
        if next_cancel:
            raw_fields["naechstes_kuendigungsdatum"] = next_cancel.isoformat()

        # Gesamtvertrauen
        confidence = min(sum(confidence_factors), 1.0)

        return ContractInfo(
            partner_name=partner or "",
            start_date=start_date,
            duration_months=duration_months,
            cancellation_notice_days=cancel_days,
            next_cancellation_date=next_cancel,
            monthly_cost=monthly_cost,
            yearly_cost=yearly_cost,
            category=category,
            confidence=confidence,
            raw_fields=raw_fields,
        )

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    async def create_contract(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        title: str,
        partner_name: str,
        category: str = PrivatContractCategory.SONSTIGE.value,
        status: str = PrivatContractStatus.AKTIV.value,
        contract_number: Optional[str] = None,
        description: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        duration_months: Optional[int] = None,
        cancellation_notice_days: Optional[int] = None,
        auto_renewal: bool = False,
        renewal_period_months: Optional[int] = None,
        monthly_cost: Optional[Decimal] = None,
        yearly_cost: Optional[Decimal] = None,
        document_id: Optional[uuid.UUID] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> PrivatContract:
        """Erstellt einen neuen privaten Vertrag.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            title: Vertragstitel
            partner_name: Vertragspartner
            category: Vertragskategorie
            ... (weitere optionale Felder)

        Returns:
            Erstellter Vertrag
        """
        # Kosten synchronisieren
        if monthly_cost and not yearly_cost:
            yearly_cost = monthly_cost * 12
        elif yearly_cost and not monthly_cost:
            monthly_cost = yearly_cost / 12

        # Naechstes Kuendigungsdatum berechnen
        next_cancel = self._calculate_next_cancellation_date(
            start_date, duration_months, cancellation_notice_days
        )

        # End-Datum berechnen wenn nicht angegeben
        if start_date and duration_months and not end_date:
            end_date = _add_months(start_date, duration_months)

        contract = PrivatContract(
            id=uuid.uuid4(),
            space_id=space_id,
            title=title,
            partner_name=partner_name,
            contract_number=contract_number,
            category=category,
            status=status,
            description=description,
            start_date=start_date,
            end_date=end_date,
            duration_months=duration_months,
            cancellation_notice_days=cancellation_notice_days,
            next_cancellation_date=next_cancel,
            auto_renewal=auto_renewal,
            renewal_period_months=renewal_period_months,
            monthly_cost=monthly_cost,
            yearly_cost=yearly_cost,
            document_id=document_id,
            notes=notes,
            tags=tags or [],
            is_active=True,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db.add(contract)
        await db.commit()
        await db.refresh(contract)

        logger.info(
            "privat_contract_created",
            contract_id=str(contract.id),
            space_id=str(space_id),
            category=category,
            partner=partner_name,
        )

        return contract

    async def create_from_extraction(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        document_id: uuid.UUID,
        ocr_text: str,
        title: Optional[str] = None,
    ) -> Tuple[PrivatContract, ContractInfo]:
        """Erstellt Vertrag aus OCR-Extraktion.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            document_id: Dokument-ID
            ocr_text: OCR-extrahierter Text
            title: Optionaler Titel (sonst automatisch)

        Returns:
            Tuple aus erstelltem Vertrag und Extraktionsergebnis
        """
        info = self.extract_contract_fields(ocr_text)

        auto_title = title or f"Vertrag {info.partner_name}" if info.partner_name else "Neuer Vertrag"

        contract = await self.create_contract(
            db=db,
            space_id=space_id,
            title=auto_title,
            partner_name=info.partner_name or "Unbekannt",
            category=info.category,
            start_date=info.start_date,
            duration_months=info.duration_months,
            cancellation_notice_days=info.cancellation_notice_days,
            auto_renewal=bool(info.duration_months),
            monthly_cost=info.monthly_cost,
            yearly_cost=info.yearly_cost,
            document_id=document_id,
        )

        # Speichere Extraktionsergebnis
        contract.extraction_confidence = Decimal(str(round(info.confidence, 4)))
        contract.raw_extracted_fields = info.raw_fields
        await db.commit()
        await db.refresh(contract)

        logger.info(
            "privat_contract_extracted",
            contract_id=str(contract.id),
            confidence=info.confidence,
            category=info.category,
        )

        return contract, info

    async def get_by_id(
        self,
        db: AsyncSession,
        contract_id: uuid.UUID,
    ) -> Optional[PrivatContract]:
        """Holt einen Vertrag nach ID.

        WARNUNG: Kein Access-Check! Fuer API immer Space-Check verwenden.
        """
        result = await db.execute(
            select(PrivatContract).where(
                PrivatContract.id == contract_id,
                PrivatContract.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def update_contract(
        self,
        db: AsyncSession,
        contract_id: uuid.UUID,
        space_id: uuid.UUID,
        **updates: object,
    ) -> Optional[PrivatContract]:
        """Aktualisiert einen Vertrag.

        SECURITY: Row Lock mit with_for_update() gegen TOCTOU.

        Args:
            db: Datenbank-Session
            contract_id: Vertrags-ID
            space_id: Space-ID (Zugriffspruefung)
            **updates: Zu aktualisierende Felder

        Returns:
            Aktualisierter Vertrag oder None
        """
        result = await db.execute(
            select(PrivatContract)
            .where(
                PrivatContract.id == contract_id,
                PrivatContract.space_id == space_id,
                PrivatContract.is_active == True,
            )
            .with_for_update()
        )
        contract = result.scalar_one_or_none()
        if not contract:
            return None

        allowed_fields = {
            "title", "partner_name", "contract_number", "category",
            "status", "description", "start_date", "end_date",
            "duration_months", "cancellation_notice_days", "auto_renewal",
            "renewal_period_months", "monthly_cost", "yearly_cost",
            "notes", "tags",
        }

        for key, value in updates.items():
            if key in allowed_fields and value is not None:
                setattr(contract, key, value)

        # Kosten synchronisieren
        if "monthly_cost" in updates and updates["monthly_cost"] and "yearly_cost" not in updates:
            contract.yearly_cost = contract.monthly_cost * 12
        elif "yearly_cost" in updates and updates["yearly_cost"] and "monthly_cost" not in updates:
            contract.monthly_cost = contract.yearly_cost / 12

        # Kuendigungsdatum neu berechnen
        contract.next_cancellation_date = self._calculate_next_cancellation_date(
            contract.start_date,
            contract.duration_months,
            contract.cancellation_notice_days,
        )

        contract.updated_at = utc_now()
        await db.commit()
        await db.refresh(contract)

        logger.info(
            "privat_contract_updated",
            contract_id=str(contract_id),
        )

        return contract

    async def delete_contract(
        self,
        db: AsyncSession,
        contract_id: uuid.UUID,
        space_id: uuid.UUID,
    ) -> bool:
        """Loescht einen Vertrag (Soft-Delete).

        SECURITY: Row Lock gegen TOCTOU.
        """
        result = await db.execute(
            select(PrivatContract)
            .where(
                PrivatContract.id == contract_id,
                PrivatContract.space_id == space_id,
                PrivatContract.is_active == True,
            )
            .with_for_update()
        )
        contract = result.scalar_one_or_none()
        if not contract:
            return False

        contract.is_active = False
        contract.deleted_at = utc_now()
        contract.updated_at = utc_now()
        await db.commit()

        logger.info(
            "privat_contract_deleted",
            contract_id=str(contract_id),
        )

        return True

    async def list_contracts(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        category: Optional[str] = None,
        status_filter: Optional[str] = None,
        expiring_within_days: Optional[int] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[PrivatContract], int]:
        """Listet Vertraege eines Spaces.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            category: Filter nach Kategorie
            status_filter: Filter nach Status
            expiring_within_days: Nur Vertraege die innerhalb X Tagen ablaufen
            page: Seitennummer
            page_size: Eintraege pro Seite

        Returns:
            Tuple aus Vertragsliste und Gesamtanzahl
        """
        conditions = [
            PrivatContract.space_id == space_id,
            PrivatContract.is_active == True,
        ]

        if category:
            conditions.append(PrivatContract.category == category)
        if status_filter:
            conditions.append(PrivatContract.status == status_filter)
        if expiring_within_days is not None:
            target = date.today() + timedelta(days=expiring_within_days)
            conditions.append(PrivatContract.next_cancellation_date.isnot(None))
            conditions.append(PrivatContract.next_cancellation_date <= target)
            conditions.append(PrivatContract.next_cancellation_date >= date.today())

        # Count
        count_result = await db.execute(
            select(func.count(PrivatContract.id)).where(and_(*conditions))
        )
        total = count_result.scalar() or 0

        # Fetch
        offset = (page - 1) * page_size
        result = await db.execute(
            select(PrivatContract)
            .where(and_(*conditions))
            .order_by(PrivatContract.next_cancellation_date.asc().nullslast())
            .offset(offset)
            .limit(page_size)
        )
        contracts = list(result.scalars().all())

        return contracts, total

    async def get_expiring_contracts(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
        days: int = 90,
    ) -> List[PrivatContract]:
        """Holt Vertraege mit bevorstehender Kuendigungsfrist.

        Args:
            db: Datenbank-Session
            space_id: Space-ID
            days: Tage voraus

        Returns:
            Liste ablaufender Vertraege
        """
        today = date.today()
        target = today + timedelta(days=days)

        result = await db.execute(
            select(PrivatContract)
            .where(
                PrivatContract.space_id == space_id,
                PrivatContract.is_active == True,
                PrivatContract.status == PrivatContractStatus.AKTIV.value,
                PrivatContract.next_cancellation_date.isnot(None),
                PrivatContract.next_cancellation_date >= today,
                PrivatContract.next_cancellation_date <= target,
            )
            .order_by(PrivatContract.next_cancellation_date.asc())
        )

        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # Reminder System
    # -------------------------------------------------------------------------

    async def schedule_reminders(
        self,
        db: AsyncSession,
        contract_id: uuid.UUID,
        reminder_days: Optional[List[int]] = None,
    ) -> List[PrivatContractReminder]:
        """Plant Erinnerungen fuer einen Vertrag.

        Erstellt Erinnerungen X Tage vor dem Kuendigungsdatum.

        Args:
            db: Datenbank-Session
            contract_id: Vertrags-ID
            reminder_days: Tage vor Kuendigungsfrist (Standard: [30, 14, 7])

        Returns:
            Liste erstellter Erinnerungen
        """
        contract = await self.get_by_id(db, contract_id)
        if not contract or not contract.next_cancellation_date:
            return []

        days_list = reminder_days or contract.reminder_days_before or [30, 14, 7]
        today = date.today()

        # Bestehende ungesendete Erinnerungen loeschen
        existing = await db.execute(
            select(PrivatContractReminder).where(
                PrivatContractReminder.contract_id == contract_id,
                PrivatContractReminder.is_sent == False,
            )
        )
        for reminder in existing.scalars().all():
            await db.delete(reminder)

        # Neue Erinnerungen erstellen
        created: List[PrivatContractReminder] = []
        for days_before in sorted(days_list, reverse=True):
            reminder_date = contract.next_cancellation_date - timedelta(days=days_before)
            if reminder_date >= today:
                reminder = PrivatContractReminder(
                    id=uuid.uuid4(),
                    contract_id=contract_id,
                    reminder_date=reminder_date,
                    days_before_deadline=days_before,
                    reminder_type="kuendigungsfrist",
                    is_sent=False,
                    created_at=utc_now(),
                )
                db.add(reminder)
                created.append(reminder)

        # Aktualisiere reminder_days am Vertrag
        contract.reminder_days_before = days_list
        contract.updated_at = utc_now()

        await db.commit()

        logger.info(
            "privat_contract_reminders_scheduled",
            contract_id=str(contract_id),
            reminders_count=len(created),
        )

        return created

    async def check_and_send_reminders(
        self,
        db: AsyncSession,
    ) -> int:
        """Prueft und sendet faellige Erinnerungen.

        Wird taeglich als Celery-Task aufgerufen.
        Findet alle ungesendeten Erinnerungen mit reminder_date <= heute
        und erstellt Alerts ueber den Alert Center Service.

        Args:
            db: Datenbank-Session

        Returns:
            Anzahl gesendeter Erinnerungen
        """
        today = date.today()

        result = await db.execute(
            select(PrivatContractReminder)
            .where(
                PrivatContractReminder.is_sent == False,
                PrivatContractReminder.reminder_date <= today,
            )
        )
        due_reminders = list(result.scalars().all())

        sent_count = 0
        for reminder in due_reminders:
            contract = await self.get_by_id(db, reminder.contract_id)
            if not contract:
                continue

            # Alert erstellen
            try:
                alert_id = await self._create_reminder_alert(
                    db, contract, reminder
                )
                reminder.is_sent = True
                reminder.sent_at = utc_now()
                reminder.alert_id = alert_id
                sent_count += 1

                logger.info(
                    "privat_contract_reminder_sent",
                    contract_id=str(contract.id),
                    reminder_id=str(reminder.id),
                    days_before=reminder.days_before_deadline,
                )
            except Exception:
                logger.exception(
                    "privat_contract_reminder_failed",
                    contract_id=str(contract.id),
                    reminder_id=str(reminder.id),
                )

        # Aktualisiere last_reminder_sent_at
        if sent_count > 0:
            await db.commit()

        return sent_count

    async def get_contract_cost_summary(
        self,
        db: AsyncSession,
        space_id: uuid.UUID,
    ) -> Dict[str, Decimal]:
        """Berechnet Kostenuebersicht aller aktiven Vertraege.

        Args:
            db: Datenbank-Session
            space_id: Space-ID

        Returns:
            Dict mit monthly_total, yearly_total, by_category
        """
        result = await db.execute(
            select(PrivatContract)
            .where(
                PrivatContract.space_id == space_id,
                PrivatContract.is_active == True,
                PrivatContract.status == PrivatContractStatus.AKTIV.value,
            )
        )
        contracts = result.scalars().all()

        monthly_total = Decimal("0.00")
        yearly_total = Decimal("0.00")
        by_category: Dict[str, Decimal] = {}

        for c in contracts:
            m_cost = c.monthly_cost or Decimal("0.00")
            monthly_total += m_cost

            y_cost = c.yearly_cost or (m_cost * 12)
            yearly_total += y_cost

            cat = c.category or "sonstige"
            by_category[cat] = by_category.get(cat, Decimal("0.00")) + m_cost

        return {
            "monthly_total": monthly_total,
            "yearly_total": yearly_total,
            "by_category": by_category,
        }

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    async def _create_reminder_alert(
        self,
        db: AsyncSession,
        contract: PrivatContract,
        reminder: PrivatContractReminder,
    ) -> Optional[uuid.UUID]:
        """Erstellt einen Alert fuer eine Vertragserinnerung.

        Nutzt den Alert Center Service wenn verfuegbar,
        sonst loggt die Erinnerung.
        """
        try:
            from app.services.alert_center_service import AlertCenterService
            from app.db.models_alert import AlertCategory, AlertSeverity

            alert_service = AlertCenterService()

            severity = AlertSeverity.LOW
            if reminder.days_before_deadline <= 7:
                severity = AlertSeverity.HIGH
            elif reminder.days_before_deadline <= 14:
                severity = AlertSeverity.MEDIUM

            cancel_date = contract.next_cancellation_date
            cancel_str = cancel_date.strftime("%d.%m.%Y") if cancel_date else "unbekannt"

            alert = await alert_service.create_alert(
                db=db,
                company_id=None,
                alert_code="PRIVAT_CONTRACT_REMINDER",
                category=AlertCategory.DEADLINE,
                severity=severity,
                title=f"Vertragserinnerung: {contract.title}",
                message=(
                    f"Der Vertrag '{contract.title}' mit {contract.partner_name} "
                    f"hat eine Kuendigungsfrist am {cancel_str}. "
                    f"Noch {reminder.days_before_deadline} Tage bis zur Frist."
                ),
                source="privat_contract_management",
                metadata={
                    "contract_id": str(contract.id),
                    "space_id": str(contract.space_id),
                    "partner": contract.partner_name,
                    "category": contract.category,
                    "days_before": reminder.days_before_deadline,
                },
            )
            return alert.id if alert else None
        except Exception:
            logger.warning(
                "alert_center_unavailable_for_reminder",
                contract_id=str(contract.id),
            )
            return None

    def _detect_category(self, text_lower: str) -> str:
        """Erkennt die Vertragskategorie aus dem Text."""
        scores: Dict[str, int] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score

        if not scores:
            return PrivatContractCategory.SONSTIGE.value

        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def _extract_partner_name(self, text: str) -> Optional[str]:
        """Extrahiert den Vertragspartner aus dem Text."""
        patterns = [
            r"(?:Vertragspartner|Anbieter|Vermieter|Versicherer)[:\s]+([A-Z][A-Za-zäöüÄÖÜß\s&.,-]+)",
            r"zwischen\s+(?:Ihnen|dem Kunden)\s+und\s+(?:der\s+)?([A-Z][A-Za-zäöüÄÖÜß\s&.,-]+?)(?:\s*,|\s+im\s|\s+wird)",
            r"^([A-Z][A-Za-zäöüÄÖÜß\s&.]+(?:GmbH|AG|SE|KG|OHG|e\.V\.|UG))",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                name = match.group(1).strip().rstrip(",.")
                if len(name) >= 3:
                    return name

        return None

    def _extract_date_near_keyword(
        self, text: str, keywords: List[str]
    ) -> Optional[date]:
        """Extrahiert ein Datum in der Naehe eines Keywords."""
        for keyword in keywords:
            pattern = rf"(?i){re.escape(keyword)}[:\s]*"
            match = re.search(pattern, text)
            if not match:
                continue

            # Suche Datum in den naechsten 80 Zeichen
            search_area = text[match.end():match.end() + 80]
            extracted = self._parse_first_date(search_area)
            if extracted:
                return extracted

        return None

    def _parse_first_date(self, text: str) -> Optional[date]:
        """Parst das erste Datum aus einem Textabschnitt."""
        # DD.MM.YYYY
        match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
        if match:
            try:
                return date(
                    int(match.group(3)),
                    int(match.group(2)),
                    int(match.group(1)),
                )
            except ValueError:
                pass

        # DD.MM.YY
        match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{2})\b", text)
        if match:
            try:
                year = int(match.group(3))
                year = year + 2000 if year < 50 else year + 1900
                return date(year, int(match.group(2)), int(match.group(1)))
            except ValueError:
                pass

        # DD. Monat YYYY
        match = re.search(
            r"(\d{1,2})\.\s*(Januar|Februar|Maerz|März|April|Mai|Juni|Juli|"
            r"August|September|Oktober|November|Dezember)\s+(\d{4})",
            text,
            re.IGNORECASE,
        )
        if match:
            try:
                month = _MONTH_MAP.get(match.group(2).lower())
                if month:
                    return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                pass

        return None

    def _extract_duration_months(self, text: str) -> Optional[int]:
        """Extrahiert die Vertragslaufzeit in Monaten."""
        # Monate
        for pattern in _PERIOD_PATTERNS["months"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    pass

        # Jahre -> Monate
        for pattern in _PERIOD_PATTERNS["years"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1)) * 12
                except (ValueError, IndexError):
                    pass

        return None

    def _extract_cancellation_notice(self, text: str) -> Optional[int]:
        """Extrahiert die Kuendigungsfrist in Tagen."""
        for i, pattern in enumerate(_CANCELLATION_PATTERNS):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = int(match.group(1))
                    # Pattern 0, 3: Monate
                    if i in (0, 3):
                        return value * 30
                    # Pattern 1, 4: Wochen
                    if i in (1, 4):
                        return value * 7
                    # Pattern 2: Tage
                    return value
                except (ValueError, IndexError):
                    pass

        return None

    def _extract_cost(self, text: str, period: str) -> Optional[Decimal]:
        """Extrahiert Kosten aus dem Text."""
        patterns = _COST_PATTERNS.get(period, [])
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value_str = match.group(1).replace(",", ".")
                    return Decimal(value_str)
                except (InvalidOperation, IndexError):
                    pass

        return None

    def _calculate_next_cancellation_date(
        self,
        start_date: Optional[date],
        duration_months: Optional[int],
        cancellation_notice_days: Optional[int],
    ) -> Optional[date]:
        """Berechnet das naechste Kuendigungsdatum.

        Berechnung:
        1. Vertragsende = start_date + duration_months
        2. Kuendigungsdatum = Vertragsende - cancellation_notice_days

        Falls auto_renewal aktiv, wird das naechste zukuenftige
        Kuendigungsdatum berechnet.
        """
        if not start_date:
            return None

        if not duration_months:
            # Kein definiertes Ende - nur Kuendigungsfrist relevant
            if cancellation_notice_days:
                # Setze auf 30 Tage ab heute als Fallback
                return date.today() + timedelta(days=cancellation_notice_days)
            return None

        # Berechne Vertragsende
        contract_end = _add_months(start_date, duration_months)

        if not cancellation_notice_days:
            # Kein Kuendigungsfrist definiert - Vertragsende ist relevant
            if contract_end > date.today():
                return contract_end
            return None

        # Berechne Kuendigungsdatum
        cancel_date = contract_end - timedelta(days=cancellation_notice_days)

        # Falls in der Vergangenheit und auto_renewal, berechne naechste Periode
        today = date.today()
        while cancel_date < today:
            contract_end = _add_months(contract_end, duration_months)
            cancel_date = contract_end - timedelta(days=cancellation_notice_days)

        return cancel_date


# =============================================================================
# Helpers
# =============================================================================


def _add_months(d: date, months: int) -> date:
    """Addiert Monate zu einem Datum."""
    import calendar

    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(d.day, max_day)
    return date(year, month, day)


# =============================================================================
# Service Singleton
# =============================================================================


_service_instance: Optional[PrivatContractManagementService] = None


def get_contract_management_service() -> PrivatContractManagementService:
    """Gibt die Service-Instanz zurueck."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PrivatContractManagementService()
    return _service_instance
