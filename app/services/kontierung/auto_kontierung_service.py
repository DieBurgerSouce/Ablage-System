# -*- coding: utf-8 -*-
"""
Auto-Kontierung Service.

Mappt extrahierte Dokumentdaten (aus OCR) auf DATEV SKR03/SKR04-Konten
und erstellt JournalEntry + JournalEntryLine Datensaetze.

Dies ist das kritische fehlende Stueck fuer die Zero-Touch-Pipeline:
Vollautomatische Kontierung von Eingangs- und Ausgangsrechnungen.

GoBD-Hinweis:
- NIEMALS Rechnungsdetails (Betrag, Lieferant) in Produktionslogs schreiben
- Korrekturen werden als Lernmuster gespeichert, nicht rueckwirkend geaendert
- Alle Journal Entries als DRAFT erstellt; Auto-Post nur bei hoher Confidence

DATEV-BU-Schluessel (Steuerkennung):
- 40: Vorsteuer 19%
- 41: Vorsteuer 7%
- 51: Umsatzsteuer 19%
- 52: Umsatzsteuer 7%
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import BusinessEntity
from app.db.models_gl_posting import (
    GLAccount,
    JournalEntry,
    JournalEntryLine,
    JournalEntrySource,
    JournalEntryStatus,
)
from app.services.datev.kontenrahmen.base import BaseKontenrahmen
from app.services.datev.kontenrahmen.skr03 import SKR03
from app.services.datev.kontenrahmen.skr04 import SKR04

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

KONTIERUNG_TOTAL = Counter(
    "kontierung_total",
    "Kontierungen gesamt",
    ["result", "method"],
)

KONTIERUNG_CONFIDENCE = Histogram(
    "kontierung_confidence",
    "Confidence-Verteilung der automatischen Kontierung",
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 1.0],
)


# =============================================================================
# Konfiguration: Keyword-Mappings fuer Aufwandskonten-Erkennung
# =============================================================================

# Mapping: Schluesselwoerter -> Aufwandstyp (wird dann an Kontenrahmen gegeben)
# Format: (schluesselwort_lower, aufwandstyp, confidence_bonus)
# Konvention: Typen entsprechen den Keys in BaseKontenrahmen.expense_accounts
_KEYWORD_RULES: List[Tuple[str, str, float]] = [
    # Stark eindeutige Begriffe (confidence 0.90)
    ("miete", "miete", 0.90),
    ("nebenkosten", "nebenkosten", 0.90),
    ("leasing", "leasing", 0.90),
    ("versicherung", "versicherung", 0.90),
    ("versicherungsbeitrag", "versicherung", 0.90),
    ("rechtsanwalt", "rechtsberatung", 0.90),
    ("rechtsberatung", "rechtsberatung", 0.90),
    ("steuerberater", "buchführung", 0.90),
    ("buchführung", "buchführung", 0.90),
    ("buchhaltung", "buchführung", 0.90),
    ("reparatur", "reparatur", 0.90),
    ("instandhaltung", "reparatur", 0.90),
    ("wartung", "reparatur", 0.90),
    ("tankstelle", "kfz_betrieb", 0.90),
    ("benzin", "kfz_betrieb", 0.90),
    ("diesel", "kfz_betrieb", 0.90),
    ("kraftstoff", "kfz_betrieb", 0.90),
    # Mittlere Eindeutigkeit (confidence 0.85)
    ("beratung", "rechtsberatung", 0.85),
    ("gutachten", "rechtsberatung", 0.85),
    ("werbung", "werbung", 0.85),
    ("marketing", "werbung", 0.85),
    ("anzeige", "werbung", 0.85),
    ("bürobedarf", "buero", 0.85),
    ("buerobedarf", "buero", 0.85),
    ("bueroartikel", "buero", 0.85),
    ("bueromaterial", "buero", 0.85),
    ("porto", "telefon", 0.85),
    ("telefon", "telefon", 0.85),
    ("mobilfunk", "telefon", 0.85),
    ("internet", "telefon", 0.85),
    ("telekommunikation", "telefon", 0.85),
    ("reise", "reise", 0.85),
    ("hotel", "reise", 0.85),
    ("flug", "reise", 0.85),
    ("fahrt", "reise", 0.85),
    ("bewirtung", "bewirtung", 0.85),
    ("restaurant", "bewirtung", 0.85),
    ("gastronomie", "bewirtung", 0.85),
    ("kfz", "kfz", 0.85),
    ("kraftfahrzeug", "kfz", 0.85),
    ("fahrzeug", "kfz", 0.85),
    ("fremdleistung", "fremdleistung", 0.85),
    ("subunternehmer", "fremdleistung", 0.85),
    ("dienstleistung", "dienstleistung", 0.80),
]

# Confidence-Werte fuer verschiedene Erkennungsquellen
_CONFIDENCE_ENTITY_KNOWN = 0.95       # Entity hat bekanntes Aufwandskonto
_CONFIDENCE_KEYWORD_STRONG = 0.90     # Eindeutiger Keyword-Treffer
_CONFIDENCE_KEYWORD_WEAK = 0.80       # Schwacher Keyword-Treffer
_CONFIDENCE_FALLBACK = 0.60           # Kein Signal, Standard-Konto

# DATEV BU-Schluessel
_BU_VORSTEUER_19 = "40"
_BU_VORSTEUER_7 = "41"
_BU_UMSATZSTEUER_19 = "51"
_BU_UMSATZSTEUER_7 = "52"

# Auto-Post Schwellwert
_AUTO_POST_MIN_CONFIDENCE = 0.85


# =============================================================================
# Data Transfer Objects
# =============================================================================

@dataclass
class KontierungSuggestion:
    """
    Vorgeschlagene Kontierung ohne Datenbankoperation.

    Wird von suggest_kontierung() zurueckgegeben und kann anschliessend
    von create_journal_entry() in einen echten Buchungssatz umgewandelt werden.
    """
    debit_account: str
    debit_account_name: str
    credit_account: str
    credit_account_name: str
    amount: Decimal
    tax_code: Optional[str]
    tax_rate: Optional[Decimal]
    tax_amount: Optional[Decimal]
    net_amount: Optional[Decimal]
    confidence: float
    explanation: str
    method: str = "keyword"       # "entity_known", "keyword", "fallback"
    raw_expense_type: Optional[str] = None


@dataclass
class KontierungResult:
    """
    Ergebnis einer vollstaendigen Kontierungsoperation inkl. Datenbankschreibung.
    """
    success: bool
    journal_entry_id: Optional[UUID]
    debit_account: str
    credit_account: str
    amount: Decimal
    tax_code: Optional[str]
    tax_rate: Optional[Decimal]
    tax_amount: Optional[Decimal]
    confidence: float
    explanation: str
    error: Optional[str] = None
    entry_number: Optional[str] = None


# =============================================================================
# Hilfsfunktionen (Modul-intern)
# =============================================================================

def _extract_amount(field_value: object) -> Optional[Decimal]:
    """
    Extrahiert Decimal-Betrag aus einem extracted_fields-Eintrags-Wert.

    extracted_fields hat das Format: {field_name: {"value": ..., "confidence": ...}}
    Diese Funktion akzeptiert sowohl das innere Dict als auch einen direkten Wert.
    """
    if field_value is None:
        return None
    if isinstance(field_value, dict):
        raw = field_value.get("value")
    else:
        raw = field_value

    if raw is None:
        return None
    try:
        return Decimal(str(raw)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _get_field_confidence(field_value: object) -> float:
    """Gibt die Confidence eines einzelnen extracted_fields-Wertes zurueck."""
    if isinstance(field_value, dict):
        conf = field_value.get("confidence", 1.0)
        try:
            return float(conf)
        except (TypeError, ValueError):
            return 1.0
    return 1.0


def _extract_text_for_keyword_search(
    extracted_fields: Dict[str, Dict[str, object]]
) -> str:
    """
    Aggregiert alle Textwerte aus extracted_fields fuer Keyword-Suche.

    Beruecksichtigt Felder: description, vendor_category, invoice_subject,
    document_type, notes, line_items (als Stringdarstellung).
    """
    text_fields = [
        "description",
        "vendor_category",
        "invoice_subject",
        "document_type",
        "notes",
        "category",
        "subject",
        "betreff",
        "beschreibung",
    ]
    parts: List[str] = []
    for field_name in text_fields:
        entry = extracted_fields.get(field_name)
        if entry is None:
            continue
        if isinstance(entry, dict):
            val = entry.get("value", "")
        else:
            val = entry
        if val and isinstance(val, str):
            parts.append(val)

    # line_items falls vorhanden als rohes Feld
    line_items = extracted_fields.get("line_items")
    if line_items:
        if isinstance(line_items, dict):
            val = line_items.get("value")
        else:
            val = line_items
        if val:
            parts.append(str(val))

    return " ".join(parts).lower()


def _detect_vat_rate(
    extracted_fields: Dict[str, Dict[str, object]]
) -> Tuple[Optional[Decimal], Optional[str]]:
    """
    Erkennt MwSt-Satz aus extrahierten Feldern.

    Gibt (vat_rate, bu_schluessel) zurueck.
    Fallback: 19% / BU 40 (Vorsteuer 19%).
    """
    # Explizites Steuerfeld
    tax_rate_raw = extracted_fields.get("tax_rate") or extracted_fields.get("vat_rate")
    if tax_rate_raw:
        rate_val = _extract_amount(tax_rate_raw)
        if rate_val is not None:
            if rate_val == Decimal("7") or rate_val == Decimal("7.00"):
                return Decimal("7.00"), _BU_VORSTEUER_7
            if rate_val == Decimal("19") or rate_val == Decimal("19.00"):
                return Decimal("19.00"), _BU_VORSTEUER_19
            # Sonstiger Satz (z.B. 0 fuer steuerfreie Leistungen)
            return rate_val, None

    # Indirekte Erkennung: Netto + MwSt vorhanden -> Satz berechnen
    gross = _extract_amount(extracted_fields.get("total_amount") or extracted_fields.get("gross_amount"))
    net = _extract_amount(extracted_fields.get("net_amount"))
    tax = _extract_amount(extracted_fields.get("tax_amount") or extracted_fields.get("vat_amount"))

    if net and tax and net > Decimal("0"):
        computed_rate = (tax / net * Decimal("100")).quantize(Decimal("0.01"))
        if Decimal("6.5") <= computed_rate <= Decimal("7.5"):
            return Decimal("7.00"), _BU_VORSTEUER_7
        if Decimal("18.5") <= computed_rate <= Decimal("19.5"):
            return Decimal("19.00"), _BU_VORSTEUER_19

    # Fallback: 19%
    return Decimal("19.00"), _BU_VORSTEUER_19


def _compute_tax_amount(
    gross: Optional[Decimal],
    net: Optional[Decimal],
    tax: Optional[Decimal],
    vat_rate: Decimal,
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Berechnet (gross, net, tax) aus verfuegbaren Werten.

    Gibt immer ein vollstaendiges Tripel zurueck, auch wenn Eingaben unvollstaendig sind.
    """
    zero = Decimal("0")

    if gross and net and not tax:
        tax = (gross - net).quantize(Decimal("0.01"))
    elif gross and tax and not net:
        net = (gross - tax).quantize(Decimal("0.01"))
    elif net and tax and not gross:
        gross = (net + tax).quantize(Decimal("0.01"))
    elif gross and not net and not tax:
        factor = vat_rate / Decimal("100")
        net = (gross / (Decimal("1") + factor)).quantize(Decimal("0.01"))
        tax = (gross - net).quantize(Decimal("0.01"))
    elif net and not gross and not tax:
        factor = vat_rate / Decimal("100")
        tax = (net * factor).quantize(Decimal("0.01"))
        gross = (net + tax).quantize(Decimal("0.01"))

    return (
        gross or zero,
        net or zero,
        tax or zero,
    )


def _build_kontenrahmen(kontenrahmen_type: str) -> BaseKontenrahmen:
    """Instanziiert den korrekten Kontenrahmen anhand des Typnamens."""
    if kontenrahmen_type.upper() == "SKR04":
        return SKR04()
    return SKR03()


def _get_account_name(kontenrahmen: BaseKontenrahmen, account_number: str) -> str:
    """
    Gibt den menschenlesbaren Kontonamen fuer eine Kontonummer zurueck.

    Sucht in allen Accounts des Kontenrahmens; Fallback ist der Typname.
    """
    all_accounts = kontenrahmen.get_all_accounts()
    for _category, accounts in all_accounts.items():
        if isinstance(accounts, dict):
            for acc_type, acc_num in accounts.items():
                if acc_num == account_number:
                    return acc_type.replace("_", " ").title()

    # Bekannte Konten als Klartext
    known_names: Dict[str, str] = {
        kontenrahmen.sammelkonto_kreditoren: "Verbindlichkeiten aus Lieferungen und Leistungen",
        kontenrahmen.sammelkonto_debitoren: "Forderungen aus Lieferungen und Leistungen",
        kontenrahmen.vorsteuer_19: "Abziehbare Vorsteuer 19%",
        kontenrahmen.vorsteuer_7: "Abziehbare Vorsteuer 7%",
        kontenrahmen.umsatzsteuer_19: "Umsatzsteuer 19%",
        kontenrahmen.umsatzsteuer_7: "Umsatzsteuer 7%",
    }
    return known_names.get(account_number, f"Konto {account_number}")


# =============================================================================
# Hauptservice
# =============================================================================

class AutoKontierungService:
    """
    Automatische Kontierung von Dokumenten auf DATEV-Konten (SKR03/SKR04).

    Implementiert die fehlende Bruecke zwischen OCR-Extraktion und
    Finanzbuchhaltung fuer die Zero-Touch-Pipeline.

    Reihenfolge der Kontierungslogik (Eingangsrechnung):
    1. Entity-Metadaten: Hat der Lieferant ein hinterlegtes Konto? -> 0.95
    2. Keyword-Matching: Erkennung aus Dokumenttext/-feldern -> 0.80-0.90
    3. Fallback: Standard-Wareneingang 19% -> 0.60

    Verwendung:
        service = AutoKontierungService(db, "SKR03")
        result = await service.kontiere_document(
            document_id=doc_id,
            company_id=company_id,
            classification_type="invoice",
            extracted_fields=ocr_fields,
            entity_id=entity_id,
            is_incoming=True,
        )
    """

    def __init__(
        self,
        db: AsyncSession,
        kontenrahmen_type: str = "SKR03",
    ) -> None:
        self.db = db
        self.kontenrahmen: BaseKontenrahmen = _build_kontenrahmen(kontenrahmen_type)
        self._log = logger.bind(
            service="AutoKontierungService",
            kontenrahmen=self.kontenrahmen.name,
        )

    # =========================================================================
    # Oeffentliche API
    # =========================================================================

    async def suggest_kontierung(
        self,
        document_id: UUID,
        company_id: UUID,
        classification_type: str,
        extracted_fields: Dict[str, Dict[str, object]],
        entity_id: Optional[UUID] = None,
        is_incoming: bool = True,
    ) -> KontierungSuggestion:
        """
        Schlaegt eine Kontierung vor, ohne einen Buchungssatz zu erstellen.

        Nuetzlich fuer UI-Vorschauen oder manuelle Pruefung vor dem Buchen.

        Args:
            document_id: Dokument-ID (fuer Logging)
            company_id: Firmen-ID (Multi-Tenancy)
            classification_type: Dokumenttyp ("invoice", "order", etc.)
            extracted_fields: OCR-Felder mit Wert und Confidence
            entity_id: Optionale Geschaeftspartner-ID fuer Entity-Lookup
            is_incoming: True = Eingangsrechnung, False = Ausgangsrechnung

        Returns:
            KontierungSuggestion mit Kontenzuordnung und Begruendung
        """
        self._log.info(
            "kontierung_suggestion_started",
            document_id=str(document_id),
            company_id=str(company_id),
            classification_type=classification_type,
            is_incoming=is_incoming,
        )

        if is_incoming:
            suggestion = await self._suggest_incoming(
                document_id=document_id,
                company_id=company_id,
                extracted_fields=extracted_fields,
                entity_id=entity_id,
            )
        else:
            suggestion = await self._suggest_outgoing(
                document_id=document_id,
                company_id=company_id,
                extracted_fields=extracted_fields,
                entity_id=entity_id,
            )

        KONTIERUNG_CONFIDENCE.observe(suggestion.confidence)
        self._log.info(
            "kontierung_suggestion_completed",
            document_id=str(document_id),
            confidence=suggestion.confidence,
            method=suggestion.method,
            debit_account=suggestion.debit_account,
            credit_account=suggestion.credit_account,
        )

        return suggestion

    async def create_journal_entry(
        self,
        document_id: UUID,
        company_id: UUID,
        suggestion: KontierungSuggestion,
        posting_date: Optional[date] = None,
        auto_post: bool = False,
    ) -> KontierungResult:
        """
        Erstellt JournalEntry + JournalEntryLines aus einem Kontierungsvorschlag.

        Args:
            document_id: Dokument-ID
            company_id: Firmen-ID (Multi-Tenancy - wird validiert)
            suggestion: Kontierungsvorschlag von suggest_kontierung()
            posting_date: Buchungsdatum (Fallback: heute)
            auto_post: True = direkt buchen wenn confidence >= 0.85

        Returns:
            KontierungResult mit Journal-Entry-ID und Buchungsdetails

        Raises:
            ValueError: Bei ungueltigen Betraegen oder fehlenden Pflichtfeldern
        """
        effective_date = posting_date or date.today()
        fiscal_year = effective_date.year
        fiscal_period = effective_date.month

        try:
            # Buchungsnummer generieren
            entry_number = await self._generate_entry_number(company_id, fiscal_year)

            # Beschreibungstext (max 60 Zeichen, DATEV-Konvention)
            description = self._build_description(
                suggestion=suggestion,
                document_id=document_id,
            )

            # Journal Entry anlegen
            entry = JournalEntry(
                id=uuid.uuid4(),
                company_id=company_id,
                document_id=document_id,
                posting_date=effective_date,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                entry_number=entry_number,
                description=description,
                total_amount=suggestion.amount,
                currency="EUR",
                status=JournalEntryStatus.DRAFT.value,
                source=JournalEntrySource.PIPELINE.value,
                confidence=Decimal(str(round(suggestion.confidence, 2))),
                metadata_json={
                    "kontierung_method": suggestion.method,
                    "expense_type": suggestion.raw_expense_type,
                    "auto_post_requested": auto_post,
                },
            )

            # Buchungszeilen erstellen
            lines = self._build_journal_lines(suggestion)
            for idx, line in enumerate(lines, start=1):
                line.entry_id = entry.id
                line.line_number = idx
                entry.lines.append(line)

            self.db.add(entry)
            await self.db.flush()

            # Auto-Posting bei ausreichender Confidence
            status_after = JournalEntryStatus.DRAFT.value
            if auto_post and suggestion.confidence >= _AUTO_POST_MIN_CONFIDENCE:
                entry.status = JournalEntryStatus.POSTED.value
                entry.posted_at = utc_now()
                status_after = JournalEntryStatus.POSTED.value
                await self.db.flush()
                self._log.info(
                    "journal_entry_auto_posted",
                    entry_id=str(entry.id),
                    company_id=str(company_id),
                    confidence=suggestion.confidence,
                )

            KONTIERUNG_TOTAL.labels(
                result="success",
                method=suggestion.method,
            ).inc()

            self._log.info(
                "journal_entry_created",
                entry_id=str(entry.id),
                entry_number=entry_number,
                company_id=str(company_id),
                status=status_after,
                confidence=suggestion.confidence,
            )

            return KontierungResult(
                success=True,
                journal_entry_id=entry.id,
                debit_account=suggestion.debit_account,
                credit_account=suggestion.credit_account,
                amount=suggestion.amount,
                tax_code=suggestion.tax_code,
                tax_rate=suggestion.tax_rate,
                tax_amount=suggestion.tax_amount,
                confidence=suggestion.confidence,
                explanation=suggestion.explanation,
                entry_number=entry_number,
            )

        except Exception as exc:
            KONTIERUNG_TOTAL.labels(
                result="error",
                method=suggestion.method,
            ).inc()
            self._log.error(
                "journal_entry_creation_failed",
                document_id=str(document_id),
                company_id=str(company_id),
                **safe_error_log(exc, context="JournalEntry-Erstellung"),
            )
            return KontierungResult(
                success=False,
                journal_entry_id=None,
                debit_account=suggestion.debit_account,
                credit_account=suggestion.credit_account,
                amount=suggestion.amount,
                tax_code=suggestion.tax_code,
                tax_rate=suggestion.tax_rate,
                tax_amount=suggestion.tax_amount,
                confidence=suggestion.confidence,
                explanation=suggestion.explanation,
                error=safe_error_detail(exc, "Buchungserstellung"),
            )

    async def kontiere_document(
        self,
        document_id: UUID,
        company_id: UUID,
        classification_type: str,
        extracted_fields: Dict[str, Dict[str, object]],
        entity_id: Optional[UUID] = None,
        is_incoming: bool = True,
    ) -> KontierungResult:
        """
        Vollstaendige Kontierungs-Pipeline: Vorschlag + Buchungserstellung.

        Haupteinstiegspunkt fuer die Zero-Touch-Pipeline.
        Auto-Post wird aktiviert wenn confidence >= 0.85.

        Args:
            document_id: Dokument-ID
            company_id: Firmen-ID
            classification_type: Dokumenttyp ("invoice", "order", etc.)
            extracted_fields: OCR-Felder {feld: {value, confidence}}
            entity_id: Optionale Entity-ID fuer bessere Kontierung
            is_incoming: True = Eingangsrechnung, False = Ausgangsrechnung

        Returns:
            KontierungResult mit Buchungssatz und Ergebnis
        """
        try:
            suggestion = await self.suggest_kontierung(
                document_id=document_id,
                company_id=company_id,
                classification_type=classification_type,
                extracted_fields=extracted_fields,
                entity_id=entity_id,
                is_incoming=is_incoming,
            )

            result = await self.create_journal_entry(
                document_id=document_id,
                company_id=company_id,
                suggestion=suggestion,
                auto_post=True,
            )
            return result

        except Exception as exc:
            KONTIERUNG_TOTAL.labels(result="error", method="pipeline").inc()
            self._log.error(
                "kontierung_pipeline_failed",
                document_id=str(document_id),
                company_id=str(company_id),
                **safe_error_log(exc, context="Kontierungs-Pipeline"),
            )
            return KontierungResult(
                success=False,
                journal_entry_id=None,
                debit_account="",
                credit_account="",
                amount=Decimal("0"),
                tax_code=None,
                tax_rate=None,
                tax_amount=None,
                confidence=0.0,
                explanation="Fehler in der Kontierungs-Pipeline",
                error=safe_error_detail(exc, "Kontierung"),
            )

    async def learn_from_correction(
        self,
        document_id: UUID,
        company_id: UUID,
        entity_id: Optional[UUID],
        corrected_debit_account: str,
        corrected_credit_account: str,
    ) -> None:
        """
        Speichert Korrekturen fuer zukuenftiges Lernen.

        Wenn entity_id angegeben ist und das korrigierte Konto ein Aufwandskonto
        ist, wird es als default_expense_account in den Entity-Metadaten gespeichert.
        Dies verbessert die Kontierung zukuenftiger Rechnungen dieses Lieferanten.

        GoBD-Hinweis: Die Korrektur aendert NICHT den bestehenden Buchungssatz.
        Der urspruengliche Entry bleibt unveraendert (nur Stornierung erlaubt).

        Args:
            document_id: Dokument-ID (fuer Audit-Log)
            company_id: Firmen-ID (Multi-Tenancy)
            entity_id: Optionale Geschaeftspartner-ID
            corrected_debit_account: Korrigierte Soll-Kontonummer
            corrected_credit_account: Korrigierte Haben-Kontonummer
        """
        self._log.info(
            "kontierung_correction_received",
            document_id=str(document_id),
            company_id=str(company_id),
            entity_id=str(entity_id) if entity_id else None,
            debit_account=corrected_debit_account,
            credit_account=corrected_credit_account,
        )

        if entity_id is None:
            return

        try:
            entity = await self._load_entity(entity_id, company_id)
            if entity is None:
                return

            # Metadaten aktualisieren
            current_meta: Dict[str, object] = entity.metadata_json or {}
            current_meta["default_expense_account"] = corrected_debit_account
            current_meta["default_expense_account_source"] = "user_correction"
            current_meta["default_expense_account_updated"] = str(utc_now().isoformat())

            entity.metadata_json = current_meta
            await self.db.flush()

            self._log.info(
                "entity_expense_account_updated",
                entity_id=str(entity_id),
                company_id=str(company_id),
                new_account=corrected_debit_account,
            )

        except Exception as exc:
            self._log.error(
                "learn_from_correction_failed",
                entity_id=str(entity_id) if entity_id else None,
                company_id=str(company_id),
                **safe_error_log(exc, context="Lernkorrektur"),
            )

    # =========================================================================
    # Interne Methoden: Kontierungslogik
    # =========================================================================

    async def _suggest_incoming(
        self,
        document_id: UUID,
        company_id: UUID,
        extracted_fields: Dict[str, Dict[str, object]],
        entity_id: Optional[UUID],
    ) -> KontierungSuggestion:
        """
        Erstellt Kontierungsvorschlag fuer Eingangsrechnungen.

        Buchungslogik:
            Soll: Aufwandskonto (z.B. 4900 Fremdleistungen)
            Soll: Vorsteuer (z.B. 1576 Vorsteuer 19%)
            Haben: Verbindlichkeiten (1600 Kreditoren-Sammelkonto)
        """
        # Betraege ermitteln
        gross = _extract_amount(
            extracted_fields.get("total_amount")
            or extracted_fields.get("gross_amount")
        )
        net = _extract_amount(extracted_fields.get("net_amount"))
        tax = _extract_amount(
            extracted_fields.get("tax_amount")
            or extracted_fields.get("vat_amount")
        )
        vat_rate, bu_schluessel = _detect_vat_rate(extracted_fields)
        gross, net, tax = _compute_tax_amount(gross, net, tax, vat_rate)

        # Aufwandskonto bestimmen (Prioritaet: Entity -> Keywords -> Fallback)
        debit_account, confidence, method, expense_type, explanation = \
            await self._determine_expense_account(
                company_id=company_id,
                entity_id=entity_id,
                extracted_fields=extracted_fields,
                vat_rate=vat_rate,
            )

        debit_name = _get_account_name(self.kontenrahmen, debit_account)
        credit_account = self.kontenrahmen.sammelkonto_kreditoren
        credit_name = _get_account_name(self.kontenrahmen, credit_account)

        return KontierungSuggestion(
            debit_account=debit_account,
            debit_account_name=debit_name,
            credit_account=credit_account,
            credit_account_name=credit_name,
            amount=gross,
            tax_code=bu_schluessel,
            tax_rate=vat_rate,
            tax_amount=tax,
            net_amount=net,
            confidence=confidence,
            explanation=explanation,
            method=method,
            raw_expense_type=expense_type,
        )

    async def _suggest_outgoing(
        self,
        document_id: UUID,
        company_id: UUID,
        extracted_fields: Dict[str, Dict[str, object]],
        entity_id: Optional[UUID],
    ) -> KontierungSuggestion:
        """
        Erstellt Kontierungsvorschlag fuer Ausgangsrechnungen.

        Buchungslogik:
            Soll: Forderungen (1400 Debitoren-Sammelkonto)
            Haben: Erloeskonto (z.B. 8400 Erloese 19%)
            Haben: Umsatzsteuer (z.B. 1776 USt 19%)
        """
        gross = _extract_amount(
            extracted_fields.get("total_amount")
            or extracted_fields.get("gross_amount")
        )
        net = _extract_amount(extracted_fields.get("net_amount"))
        tax = _extract_amount(
            extracted_fields.get("tax_amount")
            or extracted_fields.get("vat_amount")
        )
        vat_rate, _ = _detect_vat_rate(extracted_fields)
        gross, net, tax = _compute_tax_amount(gross, net, tax, vat_rate)

        # BU-Schluessel fuer Ausgangssteuer
        if vat_rate == Decimal("7"):
            bu_schluessel = _BU_UMSATZSTEUER_7
            credit_account = self.kontenrahmen.get_revenue_account("waren", 7)
        else:
            bu_schluessel = _BU_UMSATZSTEUER_19
            credit_account = self.kontenrahmen.get_revenue_account("waren", 19)

        debit_account = self.kontenrahmen.sammelkonto_debitoren
        debit_name = _get_account_name(self.kontenrahmen, debit_account)
        credit_name = _get_account_name(self.kontenrahmen, credit_account)

        explanation = (
            f"Ausgangsrechnung: Forderung {debit_account} im Soll, "
            f"Erloeskonto {credit_account} im Haben "
            f"({vat_rate}% USt)."
        )

        return KontierungSuggestion(
            debit_account=debit_account,
            debit_account_name=debit_name,
            credit_account=credit_account,
            credit_account_name=credit_name,
            amount=gross,
            tax_code=bu_schluessel,
            tax_rate=vat_rate,
            tax_amount=tax,
            net_amount=net,
            confidence=_CONFIDENCE_KEYWORD_STRONG,
            explanation=explanation,
            method="outgoing_standard",
            raw_expense_type="erloese",
        )

    async def _determine_expense_account(
        self,
        company_id: UUID,
        entity_id: Optional[UUID],
        extracted_fields: Dict[str, Dict[str, object]],
        vat_rate: Optional[Decimal],
    ) -> Tuple[str, float, str, Optional[str], str]:
        """
        Bestimmt das Aufwandskonto fuer Eingangsrechnungen.

        Returns:
            Tupel (account_number, confidence, method, expense_type, explanation)
        """
        # --- Schritt 1: Entity-Metadaten pruefen ---
        if entity_id is not None:
            entity = await self._load_entity(entity_id, company_id)
            if entity is not None:
                meta: Dict[str, object] = entity.metadata_json or {}
                entity_account = meta.get("default_expense_account")
                if entity_account and isinstance(entity_account, str):
                    explanation = (
                        f"Bekanntes Aufwandskonto des Lieferanten "
                        f"({entity_account}) aus Entitaets-Metadaten verwendet."
                    )
                    return (
                        entity_account,
                        _CONFIDENCE_ENTITY_KNOWN,
                        "entity_known",
                        entity_account,
                        explanation,
                    )

        # --- Schritt 2: Keyword-Matching ---
        search_text = _extract_text_for_keyword_search(extracted_fields)
        matched_account, matched_type, matched_confidence = \
            self._match_keywords(search_text, vat_rate)

        if matched_account is not None and matched_type is not None:
            account_name = _get_account_name(self.kontenrahmen, matched_account)
            explanation = (
                f"Aufwandskonto {matched_account} ({account_name}) "
                f"durch Texterkennung im Dokumentinhalt ermittelt "
                f"(Aufwandstyp: {matched_type})."
            )
            return (
                matched_account,
                matched_confidence,
                "keyword",
                matched_type,
                explanation,
            )

        # --- Schritt 3: Fallback ---
        vat_float = float(vat_rate) if vat_rate else 19.0
        fallback_account = self.kontenrahmen.get_expense_account(
            "waren", vat_float
        )
        fallback_name = _get_account_name(self.kontenrahmen, fallback_account)
        explanation = (
            f"Kein spezifischer Aufwandstyp erkennbar. "
            f"Standard-Wareneingang ({fallback_account} - {fallback_name}) "
            f"als Fallback verwendet."
        )
        return (
            fallback_account,
            _CONFIDENCE_FALLBACK,
            "fallback",
            "waren",
            explanation,
        )

    def _match_keywords(
        self,
        text: str,
        vat_rate: Optional[Decimal],
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Sucht nach Aufwandskonto-Schluesselbegriffen im Text.

        Gibt das erste, hochwertigste Match zurueck.

        Returns:
            (account_number, expense_type, confidence) oder (None, None, 0.0)
        """
        best_account: Optional[str] = None
        best_type: Optional[str] = None
        best_confidence: float = 0.0

        vat_float = float(vat_rate) if vat_rate else 19.0

        for keyword, expense_type, confidence in _KEYWORD_RULES:
            if keyword in text:
                account = self.kontenrahmen.get_expense_account(
                    expense_type, vat_float
                )
                if confidence > best_confidence:
                    best_account = account
                    best_type = expense_type
                    best_confidence = confidence

        return best_account, best_type, best_confidence

    # =========================================================================
    # Interne Methoden: Datenbankoperationen
    # =========================================================================

    async def _load_entity(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[BusinessEntity]:
        """
        Laedt BusinessEntity mit Multi-Tenancy-Pruefung.

        company_id-Filter verhindert Cross-Tenant-Datenlecks (Sicherheitsregel 9).
        """
        stmt = select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _generate_entry_number(
        self,
        company_id: UUID,
        fiscal_year: int,
    ) -> str:
        """
        Generiert eine eindeutige Buchungsnummer im Format JE-{year}-{seq:05d}.

        Sequenz ist pro Firma und Geschaeftsjahr aufsteigend.
        """
        stmt = select(func.max(JournalEntry.entry_number)).where(
            and_(
                JournalEntry.company_id == company_id,
                JournalEntry.fiscal_year == fiscal_year,
            )
        )
        result = await self.db.execute(stmt)
        max_number: Optional[str] = result.scalar_one_or_none()

        if max_number:
            try:
                seq = int(max_number.split("-")[-1])
                next_seq = seq + 1
            except (ValueError, IndexError):
                next_seq = 1
        else:
            next_seq = 1

        return f"JE-{fiscal_year}-{next_seq:05d}"

    def _build_journal_lines(
        self,
        suggestion: KontierungSuggestion,
    ) -> List[JournalEntryLine]:
        """
        Erstellt JournalEntryLine-Objekte aus einem Kontierungsvorschlag.

        Eingangsrechnung (is_incoming erkennbar an Kreditoren-Sammelkonto):
            Zeile 1: Aufwand im Soll (Nettobetrag)
            Zeile 2: Vorsteuer im Soll (Steuerbetrag, falls vorhanden)
            Zeile 3: Verbindlichkeit im Haben (Bruttobetrag)

        Ausgangsrechnung (Debitoren-Sammelkonto im Soll):
            Zeile 1: Forderung im Soll (Bruttobetrag)
            Zeile 2: Erloes im Haben (Nettobetrag)
            Zeile 3: Umsatzsteuer im Haben (Steuerbetrag, falls vorhanden)
        """
        lines: List[JournalEntryLine] = []
        zero = Decimal("0")
        gross = suggestion.amount
        net = suggestion.net_amount or gross
        tax = suggestion.tax_amount or zero

        debit_is_sammelkonto = (
            suggestion.debit_account == self.kontenrahmen.sammelkonto_debitoren
        )

        if debit_is_sammelkonto:
            # Ausgangsrechnung
            lines.append(JournalEntryLine(
                id=uuid.uuid4(),
                account_number=suggestion.debit_account,
                account_name=suggestion.debit_account_name[:100],
                debit_amount=gross,
                credit_amount=zero,
                text=f"Forderung {suggestion.debit_account}"[:60],
            ))
            lines.append(JournalEntryLine(
                id=uuid.uuid4(),
                account_number=suggestion.credit_account,
                account_name=suggestion.credit_account_name[:100],
                debit_amount=zero,
                credit_amount=net,
                tax_code=suggestion.tax_code,
                tax_rate=suggestion.tax_rate,
                tax_amount=tax if tax > zero else None,
                text=f"Erloes {suggestion.credit_account}"[:60],
            ))
            if tax > zero:
                ust_account = (
                    self.kontenrahmen.umsatzsteuer_7
                    if suggestion.tax_rate == Decimal("7")
                    else self.kontenrahmen.umsatzsteuer_19
                )
                lines.append(JournalEntryLine(
                    id=uuid.uuid4(),
                    account_number=ust_account,
                    account_name=_get_account_name(self.kontenrahmen, ust_account)[:100],
                    debit_amount=zero,
                    credit_amount=tax,
                    tax_code=suggestion.tax_code,
                    tax_rate=suggestion.tax_rate,
                    text="Umsatzsteuer"[:60],
                ))
        else:
            # Eingangsrechnung
            lines.append(JournalEntryLine(
                id=uuid.uuid4(),
                account_number=suggestion.debit_account,
                account_name=suggestion.debit_account_name[:100],
                debit_amount=net,
                credit_amount=zero,
                tax_code=suggestion.tax_code,
                tax_rate=suggestion.tax_rate,
                tax_amount=tax if tax > zero else None,
                text=f"Aufwand {suggestion.debit_account}"[:60],
            ))
            if tax > zero:
                vorsteuer_account = (
                    self.kontenrahmen.vorsteuer_7
                    if suggestion.tax_rate == Decimal("7")
                    else self.kontenrahmen.vorsteuer_19
                )
                lines.append(JournalEntryLine(
                    id=uuid.uuid4(),
                    account_number=vorsteuer_account,
                    account_name=_get_account_name(
                        self.kontenrahmen, vorsteuer_account
                    )[:100],
                    debit_amount=tax,
                    credit_amount=zero,
                    tax_code=suggestion.tax_code,
                    tax_rate=suggestion.tax_rate,
                    text="Vorsteuer"[:60],
                ))
            lines.append(JournalEntryLine(
                id=uuid.uuid4(),
                account_number=suggestion.credit_account,
                account_name=suggestion.credit_account_name[:100],
                debit_amount=zero,
                credit_amount=gross,
                text=f"Verbindlichkeit {suggestion.credit_account}"[:60],
            ))

        return lines

    def _build_description(
        self,
        suggestion: KontierungSuggestion,
        document_id: UUID,
    ) -> str:
        """
        Erstellt einen kurzen Buchungstext (max 60 Zeichen, DATEV-Konvention).

        Kein Log-Output mit Rechnungsdetails (GoBD).
        """
        doc_short = str(document_id)[:8]
        raw = f"Auto {suggestion.debit_account}/{suggestion.credit_account} Doc:{doc_short}"
        return raw[:60]


# =============================================================================
# Dependency Injection Helper
# =============================================================================

def get_auto_kontierung_service(
    db: AsyncSession,
    kontenrahmen_type: str = "SKR03",
) -> AutoKontierungService:
    """FastAPI Dependency fuer AutoKontierungService."""
    return AutoKontierungService(db, kontenrahmen_type)
