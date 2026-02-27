# -*- coding: utf-8 -*-
"""
Auto-Booking Service für Ablage-System.

ML-gestuetzte automatische Buchungsvorschläge:
- Kontierung basierend auf historischen Buchungen
- Lieferanten-spezifische Muster
- Dokumenttyp-basierte Regeln
- Betrags-basierte Klassifikation

Phase 5.1 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from enum import Enum
from decimal import Decimal
import re
import structlog
from collections import Counter, defaultdict

from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, User
from app.services.datev.kontenrahmen import SKR03, SKR04, BaseKontenrahmen

logger = structlog.get_logger(__name__)


# =============================================================================
# Enums & Constants
# =============================================================================


class BookingConfidence(str, Enum):
    """Confidence-Level für Buchungsvorschläge."""
    HIGH = "high"        # >90% - Auto-Booking möglich
    MEDIUM = "medium"    # 70-90% - Vorschlag mit Bestätigung
    LOW = "low"          # 50-70% - Vorschlag mit Warnung
    UNCERTAIN = "uncertain"  # <50% - Manuelle Kontierung erforderlich


class BookingType(str, Enum):
    """Buchungstyp."""
    EXPENSE = "expense"       # Aufwand (Eingangsrechnung)
    REVENUE = "revenue"       # Ertrag (Ausgangsrechnung)
    ASSET = "asset"           # Anlage
    LIABILITY = "liability"   # Verbindlichkeit
    TRANSFER = "transfer"     # Umbuchung


class TaxCode(str, Enum):
    """Steuerschluessel für DATEV."""
    VST_19 = "9"      # Vorsteuer 19%
    VST_7 = "8"       # Vorsteuer 7%
    UST_19 = "3"      # Umsatzsteuer 19%
    UST_7 = "2"       # Umsatzsteuer 7%
    VST_EU = "94"     # Vorsteuer innergemeinschaftlicher Erwerb
    STEUERFREI = "0"  # Steuerfrei


# Kategorie-Mapping zu Konten
EXPENSE_CATEGORY_MAPPING = {
    # Buero & IT
    "bueromaterial": "4930",
    "buero": "4930",
    "druckerkosten": "4930",
    "schreibwaren": "4930",
    "software": "4964",
    "edv": "4964",
    "it_service": "4964",
    "hardware": "0650",  # Aktivierung bei >800 EUR
    "hardware_gwa": "4964",  # GWA unter 800 EUR

    # Kommunikation
    "telefon": "4920",
    "internet": "4920",
    "porto": "4910",
    "versand": "4910",

    # Miete & Raum
    "miete": "4210",
    "nebenkosten": "4211",
    "strom": "4240",
    "heizung": "4240",
    "reinigung": "4250",

    # Fahrzeuge
    "tanken": "4530",
    "benzin": "4530",
    "diesel": "4530",
    "kfz_reparatur": "4540",
    "kfz_versicherung": "4520",
    "parkgebühr": "4590",

    # Personal (wenn keine Lohnbuchhaltung)
    "bewirtung": "4650",
    "geschenke": "4630",
    "reisekosten": "4660",
    "fortbildung": "4945",

    # Versicherungen & Gebühren
    "versicherung": "4360",
    "gebühren": "4970",
    "bankgebühren": "4970",
    "mitgliedsbeitrag": "4380",

    # Beratung
    "rechtsberatung": "4950",
    "steuerberatung": "4955",
    "buchführung": "4955",
    "beratung": "4960",

    # Werbung & Marketing
    "werbung": "4600",
    "marketing": "4600",
    "messe": "4610",

    # Waren
    "wareneinkauf": "3200",
    "material": "3200",
    "rohstoffe": "3000",
    "fremdleistung": "4900",
}


# =============================================================================
# Models
# =============================================================================


class BookingSuggestion(BaseModel):
    """Ein Buchungsvorschlag."""
    debit_account: str = Field(..., description="Soll-Konto")
    debit_account_name: str = Field(..., description="Soll-Kontobezeichnung")
    credit_account: str = Field(..., description="Haben-Konto")
    credit_account_name: str = Field(..., description="Haben-Kontobezeichnung")

    amount: Decimal = Field(..., description="Buchungsbetrag (brutto)")
    net_amount: Optional[Decimal] = Field(default=None, description="Nettobetrag")
    tax_amount: Optional[Decimal] = Field(default=None, description="Steuerbetrag")
    tax_code: Optional[TaxCode] = Field(default=None, description="Steuerschluessel")
    tax_rate: Optional[Decimal] = Field(default=None, description="Steuersatz")

    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz 0-1")
    confidence_level: BookingConfidence = Field(..., description="Konfidenz-Stufe")
    booking_type: BookingType = Field(..., description="Buchungstyp")

    explanation: str = Field(..., description="Erklärung für den Vorschlag")
    similar_bookings_count: int = Field(default=0, description="Anzahl ähnlicher Buchungen")
    alternative_suggestions: List["BookingSuggestion"] = Field(
        default_factory=list, description="Alternative Vorschläge"
    )

    # Metadaten
    source_factors: Dict[str, float] = Field(
        default_factory=dict, description="Faktoren die zur Entscheidung beitrugen"
    )
    warnings: List[str] = Field(default_factory=list, description="Warnungen")

    class Config:
        from_attributes = True


class BookingPattern(BaseModel):
    """Ein gelerntes Buchungsmuster."""
    entity_name: Optional[str] = None
    entity_id: Optional[UUID] = None
    document_type: Optional[str] = None
    amount_range: Optional[Tuple[Decimal, Decimal]] = None
    typical_account: str
    frequency: int
    last_used: datetime
    confidence_boost: float = 0.1


class AutoBookingResult(BaseModel):
    """Ergebnis der Auto-Booking-Analyse."""
    document_id: UUID
    suggestions: List[BookingSuggestion]
    primary_suggestion: Optional[BookingSuggestion] = None
    requires_manual_review: bool
    analysis_time_ms: int
    patterns_used: List[str] = Field(default_factory=list)


# =============================================================================
# Auto-Booking Service
# =============================================================================


class AutoBookingService:
    """Service für automatische Buchungsvorschläge.

    Analysiert Dokumente und schlaegt Kontierungen vor basierend auf:
    - Historischen Buchungen des gleichen Lieferanten
    - Ähnlichen Dokumenttypen
    - Betragskategorien
    - Text-Analyse (Schluesselwoerter)
    """

    def __init__(
        self,
        db: AsyncSession,
        kontenrahmen: Optional[BaseKontenrahmen] = None,
    ):
        self.db = db
        self.kontenrahmen = kontenrahmen or SKR03()
        self._pattern_cache: Dict[UUID, List[BookingPattern]] = {}

    # =========================================================================
    # Main API
    # =========================================================================

    async def suggest_booking(
        self,
        document_id: UUID,
        company_id: UUID,
        include_alternatives: bool = True,
        max_alternatives: int = 3,
    ) -> AutoBookingResult:
        """Erstellt Buchungsvorschlag für ein Dokument.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID für Multi-Tenant
            include_alternatives: Alternative Vorschläge einbeziehen
            max_alternatives: Maximale Anzahl Alternativen

        Returns:
            AutoBookingResult mit Vorschlägen
        """
        import time
        start_time = time.time()

        # Dokument laden
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Extrahierte Daten holen
        extracted_data = document.extracted_data or {}

        # Analyse durchführen
        suggestions = []
        patterns_used = []

        # 1. Lieferanten-basierte Analyse
        supplier_suggestion = await self._analyze_by_supplier(
            document, extracted_data, company_id
        )
        if supplier_suggestion:
            suggestions.append(supplier_suggestion)
            patterns_used.append("supplier_history")

        # 2. Dokumenttyp-basierte Analyse
        doctype_suggestion = await self._analyze_by_document_type(
            document, extracted_data
        )
        if doctype_suggestion and doctype_suggestion not in suggestions:
            suggestions.append(doctype_suggestion)
            patterns_used.append("document_type")

        # 3. Betrags-basierte Analyse
        amount_suggestion = await self._analyze_by_amount(
            document, extracted_data, company_id
        )
        if amount_suggestion and amount_suggestion not in suggestions:
            suggestions.append(amount_suggestion)
            patterns_used.append("amount_pattern")

        # 4. Text-basierte Analyse (Schluesselwoerter)
        text_suggestion = await self._analyze_by_text(
            document, extracted_data
        )
        if text_suggestion and text_suggestion not in suggestions:
            suggestions.append(text_suggestion)
            patterns_used.append("text_analysis")

        # Sortieren nach Konfidenz
        suggestions.sort(key=lambda s: s.confidence, reverse=True)

        # Primary Suggestion bestimmen
        primary = suggestions[0] if suggestions else None

        # Alternatives begrenzen
        if include_alternatives and primary:
            primary.alternative_suggestions = [
                s for s in suggestions[1:max_alternatives + 1]
            ]

        # Fallback wenn keine Vorschläge
        if not suggestions:
            suggestions.append(self._create_fallback_suggestion(document, extracted_data))
            patterns_used.append("fallback")

        # Ergebnis erstellen
        execution_time_ms = int((time.time() - start_time) * 1000)

        return AutoBookingResult(
            document_id=document_id,
            suggestions=suggestions[:max_alternatives + 1],
            primary_suggestion=primary,
            requires_manual_review=not primary or primary.confidence < 0.7,
            analysis_time_ms=execution_time_ms,
            patterns_used=patterns_used,
        )

    async def learn_from_booking(
        self,
        document_id: UUID,
        company_id: UUID,
        debit_account: str,
        credit_account: str,
        user_id: UUID,
    ) -> None:
        """Lernt aus einer manuellen Buchung.

        Speichert das Muster für zukünftige Vorschläge.

        Args:
            document_id: Dokument-ID
            company_id: Company-ID
            debit_account: Gewaehltes Soll-Konto
            credit_account: Gewaehltes Haben-Konto
            user_id: User der die Buchung durchführt
        """
        # Dokument laden
        result = await self.db.execute(
            select(Document).where(
                and_(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
        )
        document = result.scalar_one_or_none()

        if not document:
            return

        extracted_data = document.extracted_data or {}

        # Pattern-Daten aufbauen
        pattern_data = {
            "document_id": str(document_id),
            "document_type": document.document_type,
            "supplier_name": extracted_data.get("supplier_name"),
            "entity_id": str(extracted_data.get("entity_id")) if extracted_data.get("entity_id") else None,
            "amount": float(extracted_data.get("amount", 0)),
            "debit_account": debit_account,
            "credit_account": credit_account,
            "booked_by": str(user_id),
            "booked_at": datetime.utcnow().isoformat(),
        }

        # In Dokument-Metadata speichern
        metadata = document.metadata_json or {}
        booking_history = metadata.get("booking_history", [])
        booking_history.append(pattern_data)
        metadata["booking_history"] = booking_history[-50:]  # Letzte 50 behalten
        metadata["last_booking"] = pattern_data

        document.metadata_json = metadata
        await self.db.commit()

        logger.info(
            "booking_pattern_learned",
            document_id=str(document_id),
            debit_account=debit_account,
            credit_account=credit_account,
        )

    async def get_supplier_patterns(
        self,
        company_id: UUID,
        supplier_name: Optional[str] = None,
        entity_id: Optional[UUID] = None,
    ) -> List[BookingPattern]:
        """Holt gelernte Muster für einen Lieferanten.

        Args:
            company_id: Company-ID
            supplier_name: Lieferantenname (optional)
            entity_id: Entity-ID (optional)

        Returns:
            Liste von BookingPattern
        """
        patterns = []

        # Dokumente mit Buchungshistorie laden
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.metadata_json.isnot(None),
            )
        )

        if entity_id:
            # JSON-Filterung (PostgreSQL spezifisch)
            query = query.where(
                Document.extracted_data["entity_id"].astext == str(entity_id)
            )
        elif supplier_name:
            query = query.where(
                func.lower(Document.extracted_data["supplier_name"].astext).contains(
                    supplier_name.lower()
                )
            )

        query = query.order_by(desc(Document.created_at)).limit(100)

        result = await self.db.execute(query)
        documents = result.scalars().all()

        # Muster aggregieren
        account_counts: Dict[str, int] = Counter()
        last_used: Dict[str, datetime] = {}

        for doc in documents:
            metadata = doc.metadata_json or {}
            if "last_booking" in metadata:
                booking = metadata["last_booking"]
                account = booking.get("debit_account", "")
                if account:
                    account_counts[account] += 1
                    booked_at = datetime.fromisoformat(booking.get("booked_at", "2020-01-01"))
                    if account not in last_used or booked_at > last_used[account]:
                        last_used[account] = booked_at

        # Patterns erstellen
        for account, count in account_counts.most_common(5):
            patterns.append(BookingPattern(
                entity_name=supplier_name,
                entity_id=entity_id,
                typical_account=account,
                frequency=count,
                last_used=last_used.get(account, datetime.utcnow()),
                confidence_boost=min(0.3, count * 0.05),  # Max 30% Boost
            ))

        return patterns

    # =========================================================================
    # Analysis Methods
    # =========================================================================

    async def _analyze_by_supplier(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> Optional[BookingSuggestion]:
        """Analysiert basierend auf Lieferanten-Historie."""
        supplier_name = extracted_data.get("supplier_name")
        entity_id = extracted_data.get("entity_id")

        if not supplier_name and not entity_id:
            return None

        patterns = await self.get_supplier_patterns(
            company_id=company_id,
            supplier_name=supplier_name,
            entity_id=entity_id,
        )

        if not patterns:
            return None

        # Bestes Muster nehmen
        best_pattern = patterns[0]

        # Betrag und Steuer extrahieren
        amount, net_amount, tax_amount, tax_rate = self._extract_amounts(extracted_data)

        confidence = 0.65 + best_pattern.confidence_boost
        confidence = min(0.95, confidence)  # Max 95%

        return BookingSuggestion(
            debit_account=best_pattern.typical_account,
            debit_account_name=self._get_account_name(best_pattern.typical_account),
            credit_account=self._get_default_credit_account(extracted_data),
            credit_account_name=self._get_account_name(
                self._get_default_credit_account(extracted_data)
            ),
            amount=amount,
            net_amount=net_amount,
            tax_amount=tax_amount,
            tax_code=self._determine_tax_code(tax_rate),
            tax_rate=tax_rate,
            confidence=confidence,
            confidence_level=self._get_confidence_level(confidence),
            booking_type=BookingType.EXPENSE,
            explanation=f"Basierend auf {best_pattern.frequency} früheren Buchungen von {supplier_name or 'diesem Lieferanten'}",
            similar_bookings_count=best_pattern.frequency,
            source_factors={
                "supplier_history": best_pattern.confidence_boost,
                "frequency": min(0.2, best_pattern.frequency * 0.02),
            },
        )

    async def _analyze_by_document_type(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
    ) -> Optional[BookingSuggestion]:
        """Analysiert basierend auf Dokumenttyp."""
        doc_type = document.document_type

        # Mapping von Dokumenttypen zu typischen Konten
        doctype_mapping = {
            "rechnung": ("3200", "Wareneinkauf"),
            "eingangsrechnung": ("3200", "Wareneinkauf"),
            "ausgangsrechnung": ("8400", "Erloese"),
            "gutschrift": ("8400", "Erloese/Gutschrift"),
            "miete": ("4210", "Miete"),
            "versicherung": ("4360", "Versicherungen"),
            "telefon": ("4920", "Telefon/Internet"),
            "strom": ("4240", "Energiekosten"),
        }

        if doc_type not in doctype_mapping:
            return None

        account, account_name = doctype_mapping[doc_type]
        amount, net_amount, tax_amount, tax_rate = self._extract_amounts(extracted_data)

        confidence = 0.55  # Basis-Konfidenz für Dokumenttyp

        # Booking Type basierend auf Dokumenttyp
        booking_type = BookingType.REVENUE if doc_type in ["ausgangsrechnung", "gutschrift"] else BookingType.EXPENSE

        return BookingSuggestion(
            debit_account=account,
            debit_account_name=account_name,
            credit_account=self._get_default_credit_account(extracted_data),
            credit_account_name=self._get_account_name(
                self._get_default_credit_account(extracted_data)
            ),
            amount=amount,
            net_amount=net_amount,
            tax_amount=tax_amount,
            tax_code=self._determine_tax_code(tax_rate),
            tax_rate=tax_rate,
            confidence=confidence,
            confidence_level=self._get_confidence_level(confidence),
            booking_type=booking_type,
            explanation=f"Typisches Konto für Dokumenttyp '{doc_type}'",
            source_factors={"document_type": 0.55},
        )

    async def _analyze_by_amount(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
        company_id: UUID,
    ) -> Optional[BookingSuggestion]:
        """Analysiert basierend auf Betragsmuster."""
        amount, _, _, tax_rate = self._extract_amounts(extracted_data)

        if amount <= 0:
            return None

        # Betragskategorien
        if amount < Decimal("50"):
            category = "kleinbetrag"
            typical_account = "4930"  # Buerokosten
            explanation = "Kleinbetrag - typischerweise Buerokosten"
        elif amount < Decimal("250"):
            category = "mittlerer_betrag"
            typical_account = "4930"
            explanation = "Mittlerer Betrag"
        elif amount < Decimal("1000"):
            category = "größerer_betrag"
            typical_account = "3200"  # Wareneinkauf
            explanation = "Größerer Betrag - möglicherweise Wareneinkauf"
        else:
            category = "hoher_betrag"
            typical_account = "3200"
            explanation = "Hoher Betrag - Wareneinkauf oder Anlage"

        confidence = 0.35  # Niedrige Basis-Konfidenz für reine Betragsanalyse

        return BookingSuggestion(
            debit_account=typical_account,
            debit_account_name=self._get_account_name(typical_account),
            credit_account=self._get_default_credit_account(extracted_data),
            credit_account_name=self._get_account_name(
                self._get_default_credit_account(extracted_data)
            ),
            amount=amount,
            net_amount=amount / (1 + (tax_rate or Decimal("0.19"))) if tax_rate else None,
            tax_amount=None,
            tax_code=self._determine_tax_code(tax_rate),
            tax_rate=tax_rate,
            confidence=confidence,
            confidence_level=BookingConfidence.UNCERTAIN,
            booking_type=BookingType.EXPENSE,
            explanation=explanation,
            source_factors={"amount_category": 0.35},
            warnings=["Nur betragsbasierte Analyse - manuelle Prüfung empfohlen"],
        )

    async def _analyze_by_text(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
    ) -> Optional[BookingSuggestion]:
        """Analysiert basierend auf Schluesselwoertern im Text."""
        # Text aus verschiedenen Quellen sammeln
        text_sources = [
            extracted_data.get("description", ""),
            extracted_data.get("text", ""),
            extracted_data.get("line_items_text", ""),
            document.original_filename or "",
        ]
        full_text = " ".join(str(s) for s in text_sources if s).lower()

        if not full_text:
            return None

        # Schluesselwort-Suche
        keyword_matches: Dict[str, int] = {}

        for category, account in EXPENSE_CATEGORY_MAPPING.items():
            # Kategorie-Schluesselwoerter
            keywords = category.split("_")
            for keyword in keywords:
                if keyword in full_text:
                    if account not in keyword_matches:
                        keyword_matches[account] = 0
                    keyword_matches[account] += 1

        if not keyword_matches:
            return None

        # Bestes Match
        best_account = max(keyword_matches, key=keyword_matches.get)
        match_count = keyword_matches[best_account]

        confidence = min(0.6, 0.3 + match_count * 0.1)
        amount, net_amount, tax_amount, tax_rate = self._extract_amounts(extracted_data)

        return BookingSuggestion(
            debit_account=best_account,
            debit_account_name=self._get_account_name(best_account),
            credit_account=self._get_default_credit_account(extracted_data),
            credit_account_name=self._get_account_name(
                self._get_default_credit_account(extracted_data)
            ),
            amount=amount,
            net_amount=net_amount,
            tax_amount=tax_amount,
            tax_code=self._determine_tax_code(tax_rate),
            tax_rate=tax_rate,
            confidence=confidence,
            confidence_level=self._get_confidence_level(confidence),
            booking_type=BookingType.EXPENSE,
            explanation=f"Schluesselwort-Analyse: {match_count} Treffer",
            source_factors={"text_keywords": confidence},
        )

    def _create_fallback_suggestion(
        self,
        document: Document,
        extracted_data: Dict[str, Any],
    ) -> BookingSuggestion:
        """Erstellt einen Fallback-Vorschlag wenn keine Analyse möglich."""
        amount, net_amount, tax_amount, tax_rate = self._extract_amounts(extracted_data)

        return BookingSuggestion(
            debit_account="4900",  # Fremdleistungen als Fallback
            debit_account_name="Fremdleistungen",
            credit_account="1600",  # Verbindlichkeiten
            credit_account_name="Verbindlichkeiten",
            amount=amount if amount > 0 else Decimal("0"),
            net_amount=net_amount,
            tax_amount=tax_amount,
            tax_code=TaxCode.VST_19,
            tax_rate=Decimal("0.19"),
            confidence=0.2,
            confidence_level=BookingConfidence.UNCERTAIN,
            booking_type=BookingType.EXPENSE,
            explanation="Keine spezifische Analyse möglich - Fallback auf Fremdleistungen",
            warnings=[
                "Manuelle Kontierung erforderlich",
                "Automatische Analyse konnte kein Muster erkennen",
            ],
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_amounts(
        self,
        extracted_data: Dict[str, Any],
    ) -> Tuple[Decimal, Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Extrahiert Betraege aus den extrahierten Daten."""
        amount = Decimal(str(extracted_data.get("amount", 0) or 0))
        net_amount = extracted_data.get("net_amount")
        tax_amount = extracted_data.get("tax_amount")
        tax_rate = extracted_data.get("tax_rate")

        if net_amount:
            net_amount = Decimal(str(net_amount))
        if tax_amount:
            tax_amount = Decimal(str(tax_amount))
        if tax_rate:
            tax_rate = Decimal(str(tax_rate))
        elif amount > 0 and net_amount:
            # Tax Rate berechnen
            tax_rate = (amount - net_amount) / net_amount

        return amount, net_amount, tax_amount, tax_rate

    def _get_default_credit_account(self, extracted_data: Dict[str, Any]) -> str:
        """Ermittelt das Standard-Gegen-Konto."""
        doc_type = extracted_data.get("document_type", "")

        if doc_type in ["ausgangsrechnung"]:
            return "1400"  # Forderungen
        else:
            return "1600"  # Verbindlichkeiten

    def _get_account_name(self, account: str) -> str:
        """Holt Kontobezeichnung."""
        # Aus Kontenrahmen holen wenn verfügbar
        account_names = {
            "1400": "Forderungen aus Lieferungen und Leistungen",
            "1600": "Verbindlichkeiten aus Lieferungen und Leistungen",
            "1200": "Bank",
            "1000": "Kasse",
            "3200": "Wareneingang 19% Vorsteuer",
            "3300": "Wareneingang 7% Vorsteuer",
            "4210": "Miete",
            "4211": "Nebenkosten",
            "4240": "Energiekosten",
            "4360": "Versicherungen",
            "4500": "Fahrzeugkosten",
            "4520": "Kfz-Versicherungen",
            "4530": "Treibstoff",
            "4540": "Kfz-Reparaturen",
            "4590": "Sonstige Kfz-Kosten",
            "4600": "Werbekosten",
            "4650": "Bewirtungskosten",
            "4660": "Reisekosten",
            "4900": "Fremdleistungen",
            "4910": "Porto",
            "4920": "Telefon/Internet",
            "4930": "Buerokosten",
            "4950": "Rechtsberatungskosten",
            "4955": "Buchführungskosten",
            "4960": "Beratungskosten",
            "4964": "EDV-Kosten",
            "4970": "Nebenkosten des Geldverkehrs",
            "8400": "Erloese 19% USt",
        }
        return account_names.get(account, f"Konto {account}")

    def _determine_tax_code(self, tax_rate: Optional[Decimal]) -> TaxCode:
        """Bestimmt den Steuerschluessel."""
        if not tax_rate:
            return TaxCode.VST_19  # Default

        rate = float(tax_rate)
        if rate >= 0.18 and rate <= 0.20:
            return TaxCode.VST_19
        elif rate >= 0.06 and rate <= 0.08:
            return TaxCode.VST_7
        elif rate == 0:
            return TaxCode.STEUERFREI
        else:
            return TaxCode.VST_19  # Default

    def _get_confidence_level(self, confidence: float) -> BookingConfidence:
        """Konvertiert Konfidenz-Wert zu Level."""
        if confidence >= 0.9:
            return BookingConfidence.HIGH
        elif confidence >= 0.7:
            return BookingConfidence.MEDIUM
        elif confidence >= 0.5:
            return BookingConfidence.LOW
        else:
            return BookingConfidence.UNCERTAIN


# =============================================================================
# Factory Function
# =============================================================================


def get_auto_booking_service(
    db: AsyncSession,
    kontenrahmen_type: str = "SKR03",
) -> AutoBookingService:
    """Factory für AutoBookingService.

    Args:
        db: Database Session
        kontenrahmen_type: "SKR03" oder "SKR04"

    Returns:
        AutoBookingService Instanz
    """
    kontenrahmen = SKR03() if kontenrahmen_type == "SKR03" else SKR04()
    return AutoBookingService(db=db, kontenrahmen=kontenrahmen)
