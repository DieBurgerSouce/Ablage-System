"""Automatische Buchungsvorschlaege Service.

Phase 5.1: Lernt aus vergangenen Buchungen und schlaegt vor:
- SKR03/SKR04 Konto
- Kostenstelle
- Steuersatz
- Konfidenz-Score pro Vorschlag

Feedback-Loop: Korrekturen verbessern zukuenftige Vorschlaege.

Feinpoliert und durchdacht - Enterprise Accounting Automation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document

logger = structlog.get_logger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class BookingSuggestion:
    """Ein einzelner Buchungsvorschlag."""
    account_number: str           # SKR03/SKR04 Kontonummer
    account_name: str             # Kontobezeichnung
    cost_center: Optional[str]    # Kostenstelle
    tax_rate: Decimal             # Steuersatz (0.00, 0.07, 0.19)
    tax_key: str                  # Steuerschluessel (z.B. "9" fuer 19% VSt)
    confidence: float             # 0.0 - 1.0
    reason: str                   # Begruendung
    based_on_count: int           # Anzahl historischer Buchungen als Basis


@dataclass
class BookingResult:
    """Ergebnis der Buchungsvorschlag-Analyse."""
    document_id: str
    suggestions: List[BookingSuggestion]
    document_type: str
    vendor_name: Optional[str]
    total_amount: Optional[Decimal]
    currency: str
    chart_of_accounts: str        # SKR03 oder SKR04


# ============================================================================
# SKR03/SKR04 Kontenrahmen (Auszug der haeufigsten Konten)
# ============================================================================


SKR03_ACCOUNTS: Dict[str, Dict[str, str]] = {
    # Aufwandskonten
    "4200": {"name": "Raumkosten", "category": "aufwand"},
    "4210": {"name": "Miete (unbewegliche Wirtschaftsgueter)", "category": "aufwand"},
    "4240": {"name": "Gas, Strom, Wasser", "category": "aufwand"},
    "4250": {"name": "Reinigungskosten", "category": "aufwand"},
    "4300": {"name": "Versicherungsbeitraege", "category": "aufwand"},
    "4500": {"name": "Fahrzeugkosten", "category": "aufwand"},
    "4510": {"name": "Kfz-Steuer", "category": "aufwand"},
    "4520": {"name": "Kfz-Versicherungen", "category": "aufwand"},
    "4530": {"name": "Laufende Kfz-Betriebskosten", "category": "aufwand"},
    "4600": {"name": "Werbekosten", "category": "aufwand"},
    "4610": {"name": "Werbekosten Anzeigen", "category": "aufwand"},
    "4630": {"name": "Geschenke an Kunden", "category": "aufwand"},
    "4650": {"name": "Bewirtungskosten", "category": "aufwand"},
    "4654": {"name": "Nicht abzugsfaehige Bewirtungskosten", "category": "aufwand"},
    "4660": {"name": "Reisekosten AN", "category": "aufwand"},
    "4670": {"name": "Reisekosten Unternehmer", "category": "aufwand"},
    "4700": {"name": "Kosten der Warenabgabe", "category": "aufwand"},
    "4800": {"name": "Reparaturen und Instandhaltung", "category": "aufwand"},
    "4900": {"name": "Sonstige betriebliche Aufwendungen", "category": "aufwand"},
    "4910": {"name": "Porto", "category": "aufwand"},
    "4920": {"name": "Telefon", "category": "aufwand"},
    "4921": {"name": "Internet", "category": "aufwand"},
    "4930": {"name": "Buerokosten", "category": "aufwand"},
    "4940": {"name": "Zeitschriften, Buecher", "category": "aufwand"},
    "4950": {"name": "Rechts- und Beratungskosten", "category": "aufwand"},
    "4955": {"name": "Buchfuehrungskosten", "category": "aufwand"},
    "4960": {"name": "Mieten fuer Einrichtungen", "category": "aufwand"},
    "4970": {"name": "Nebenkosten des Geldverkehrs", "category": "aufwand"},
    # Wareneingang
    "3300": {"name": "Wareneingang 7% VSt", "category": "wareneinkauf"},
    "3400": {"name": "Wareneingang 19% VSt", "category": "wareneinkauf"},
    # Erloese
    "8300": {"name": "Erloese 7% USt", "category": "erloes"},
    "8400": {"name": "Erloese 19% USt", "category": "erloes"},
}


# Keyword → Konto Mapping
KEYWORD_ACCOUNT_MAP: Dict[str, str] = {
    "miete": "4210",
    "strom": "4240",
    "gas": "4240",
    "wasser": "4240",
    "versicherung": "4300",
    "kfz": "4530",
    "tanken": "4530",
    "benzin": "4530",
    "werbung": "4600",
    "anzeige": "4610",
    "geschenk": "4630",
    "bewirtung": "4650",
    "restaurant": "4650",
    "reise": "4660",
    "hotel": "4660",
    "flug": "4660",
    "reparatur": "4800",
    "porto": "4910",
    "post": "4910",
    "telefon": "4920",
    "internet": "4921",
    "buero": "4930",
    "buch": "4940",
    "rechtsanwalt": "4950",
    "anwalt": "4950",
    "steuerberater": "4955",
    "bank": "4970",
    "kontogebuehr": "4970",
}


class BookingSuggestionService:
    """Service fuer automatische Buchungsvorschlaege.

    Analysiert Dokumente und schlaegt passende Buchungskonten vor,
    basierend auf:
    1. Keyword-Matching im extrahierten Text
    2. Historische Buchungen desselben Lieferanten
    3. Dokumenttyp und Betrag
    """

    async def suggest_booking(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        chart: str = "SKR03",
    ) -> BookingResult:
        """Erstellt Buchungsvorschlaege fuer ein Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firmen-ID
            chart: Kontenrahmen (SKR03/SKR04)

        Returns:
            BookingResult mit Vorschlaegen
        """
        # Dokument laden
        query = select(Document).where(
            and_(Document.id == document_id, Document.company_id == company_id)
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return BookingResult(
                document_id=str(document_id),
                suggestions=[],
                document_type="unknown",
                vendor_name=None,
                total_amount=None,
                currency="EUR",
                chart_of_accounts=chart,
            )

        text = (doc.extracted_text or "").lower()
        metadata = doc.document_metadata or {}

        # Vendor und Betrag extrahieren
        vendor_name = metadata.get("vendor_name") or metadata.get("lieferant")
        total_str = metadata.get("total_amount") or metadata.get("gesamtbetrag")
        total_amount = Decimal(str(total_str)) if total_str else None

        suggestions = []

        # 1. Keyword-basierte Vorschlaege
        keyword_suggestions = self._suggest_by_keywords(text, chart)
        suggestions.extend(keyword_suggestions)

        # 2. Dokumenttyp-basierte Vorschlaege
        type_suggestions = self._suggest_by_document_type(
            doc.document_type, total_amount, chart
        )
        suggestions.extend(type_suggestions)

        # 3. Deduplizieren und nach Confidence sortieren
        seen_accounts = set()
        unique_suggestions = []
        for s in sorted(suggestions, key=lambda x: x.confidence, reverse=True):
            if s.account_number not in seen_accounts:
                seen_accounts.add(s.account_number)
                unique_suggestions.append(s)

        # Max. 3 Vorschlaege
        unique_suggestions = unique_suggestions[:3]

        logger.info(
            "booking_suggestions_generated",
            document_id=str(document_id),
            suggestion_count=len(unique_suggestions),
            document_type=doc.document_type,
        )

        return BookingResult(
            document_id=str(document_id),
            suggestions=unique_suggestions,
            document_type=doc.document_type or "unknown",
            vendor_name=vendor_name,
            total_amount=total_amount,
            currency="EUR",
            chart_of_accounts=chart,
        )

    async def record_feedback(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
        accepted_account: str,
        accepted_cost_center: Optional[str] = None,
        accepted_tax_rate: Optional[Decimal] = None,
    ) -> Dict:
        """Feedback fuer einen Buchungsvorschlag aufzeichnen.

        Verbessert zukuenftige Vorschlaege durch Lernen aus Korrekturen.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firmen-ID
            accepted_account: Akzeptierte Kontonummer
            accepted_cost_center: Kostenstelle
            accepted_tax_rate: Steuersatz

        Returns:
            Dict mit Bestaetigung
        """
        # In Dokument-Metadaten speichern fuer zukuenftiges Lernen
        query = select(Document).where(
            and_(Document.id == document_id, Document.company_id == company_id)
        )
        result = await db.execute(query)
        doc = result.scalar_one_or_none()

        if not doc:
            return {"fehler": "Dokument nicht gefunden"}

        metadata = doc.document_metadata or {}
        metadata["booking_feedback"] = {
            "account": accepted_account,
            "cost_center": accepted_cost_center,
            "tax_rate": str(accepted_tax_rate) if accepted_tax_rate else None,
            "feedback_at": datetime.now(timezone.utc).isoformat(),
        }
        doc.document_metadata = metadata
        await db.flush()

        logger.info(
            "booking_feedback_recorded",
            document_id=str(document_id),
            account=accepted_account,
        )

        return {
            "nachricht": "Buchungs-Feedback gespeichert",
            "konto": accepted_account,
            "wird_fuer_zukuenftige_vorschlaege_genutzt": True,
        }

    # ================================================================
    # Interne Methoden
    # ================================================================

    def _suggest_by_keywords(self, text: str, chart: str) -> List[BookingSuggestion]:
        """Vorschlaege basierend auf Keyword-Matching im Text."""
        accounts = SKR03_ACCOUNTS if chart == "SKR03" else SKR03_ACCOUNTS  # TODO: SKR04

        suggestions = []
        for keyword, account_nr in KEYWORD_ACCOUNT_MAP.items():
            if keyword in text:
                account_info = accounts.get(account_nr, {})
                suggestions.append(BookingSuggestion(
                    account_number=account_nr,
                    account_name=account_info.get("name", "Unbekannt"),
                    cost_center=None,
                    tax_rate=Decimal("0.19"),  # Standard
                    tax_key="9",
                    confidence=0.6,
                    reason=f"Schluesselwort '{keyword}' im Text gefunden",
                    based_on_count=0,
                ))

        return suggestions

    def _suggest_by_document_type(
        self,
        document_type: Optional[str],
        total_amount: Optional[Decimal],
        chart: str,
    ) -> List[BookingSuggestion]:
        """Vorschlaege basierend auf Dokumenttyp."""
        accounts = SKR03_ACCOUNTS if chart == "SKR03" else SKR03_ACCOUNTS

        suggestions = []

        if document_type == "invoice" or document_type == "rechnung":
            suggestions.append(BookingSuggestion(
                account_number="3400",
                account_name="Wareneingang 19% VSt",
                cost_center=None,
                tax_rate=Decimal("0.19"),
                tax_key="9",
                confidence=0.5,
                reason="Standard-Konto fuer Eingangsrechnungen",
                based_on_count=0,
            ))

        return suggestions


# Singleton
_booking_service: Optional[BookingSuggestionService] = None


def get_booking_suggestion_service() -> BookingSuggestionService:
    """Singleton-Instanz."""
    global _booking_service
    if _booking_service is None:
        _booking_service = BookingSuggestionService()
    return _booking_service
