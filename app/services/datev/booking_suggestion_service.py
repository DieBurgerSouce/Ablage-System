# -*- coding: utf-8 -*-
"""
DATEV Booking Suggestion Service.

Generiert Buchungsvorschläge basierend auf OCR-Extraktion:
- SKR03/04 Konten-Vorschläge
- Steuercode-Erkennung
- Kostenstellen-Zuordnung
- Belegart-Klassifikation

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

import structlog
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class Kontenrahmen(str, Enum):
    """Unterstützte Kontenrahmen."""
    SKR03 = "skr03"
    SKR04 = "skr04"


class Belegart(str, Enum):
    """Belegarten für DATEV."""
    EINGANGSRECHNUNG = "ER"      # Eingangsrechnung
    AUSGANGSRECHNUNG = "AR"      # Ausgangsrechnung
    GUTSCHRIFT_EINGANG = "GE"    # Gutschrift Eingang
    GUTSCHRIFT_AUSGANG = "GA"    # Gutschrift Ausgang
    BANK = "BK"                   # Bankbeleg
    KASSE = "KS"                  # Kassenbeleg
    SONSTIGES = "SO"              # Sonstiger Beleg


class Steuercode(str, Enum):
    """DATEV Steuercodes."""
    UST_19 = "9"          # 19% USt
    UST_7 = "8"           # 7% USt
    VST_19 = "9"          # 19% VSt
    VST_7 = "8"           # 7% VSt
    EU_ERWERB = "91"      # EU-Erwerb
    REVERSE_CHARGE = "94" # Reverse Charge
    STEUERFREI = "0"      # Steuerfrei
    INNERGEMEINSCHAFTLICH = "41"  # Innergemeinschaftliche Lieferung


class BookingSuggestion(BaseModel):
    """Schema für Buchungsvorschlag."""
    # Pflichtfelder
    belegart: str = Field(..., description="Belegart (ER, AR, etc.)")
    belegdatum: date = Field(..., description="Belegdatum")
    buchungstext: str = Field(..., max_length=60, description="Buchungstext")
    betrag: Decimal = Field(..., description="Bruttobetrag")

    # Konten
    sollkonto: str = Field(..., description="Sollkonto")
    habenkonto: str = Field(..., description="Habenkonto")
    sollkonto_name: Optional[str] = None
    habenkonto_name: Optional[str] = None

    # Steuer
    steuercode: Optional[str] = None
    steuersatz: Optional[float] = None
    steuerbetrag: Optional[Decimal] = None
    nettobetrag: Optional[Decimal] = None

    # Zusätzliche Felder
    belegnummer: Optional[str] = Field(None, max_length=12)
    rechnungsnummer: Optional[str] = Field(None, max_length=36)
    gegenkonto_name: Optional[str] = None  # Lieferant/Kunde Name

    # Kostenstelle
    kostenstelle: Optional[str] = None
    kostentraeger: Optional[str] = None

    # Confidence
    confidence: float = Field(..., ge=0, le=1, description="Gesamt-Confidence")
    confidence_details: Dict[str, float] = Field(default_factory=dict)

    # Warnungen
    warnings: List[str] = Field(default_factory=list)
    requires_review: bool = False


class AccountMapping(BaseModel):
    """Konto-Zuordnung."""
    konto: str
    name: str
    typ: str  # aufwand, ertrag, aktiv, passiv
    steuercode: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)


class BookingSuggestionService:
    """
    Service für DATEV Buchungsvorschläge.

    Analysiert OCR-Text und generiert Buchungsvorschläge
    nach SKR03 oder SKR04.
    """

    # SKR03 Konten-Mappings (häufig verwendete)
    SKR03_ACCOUNTS = {
        # Aufwandskonten
        "buero": AccountMapping(
            konto="4930", name="Bürobedarf", typ="aufwand", steuercode="9",
            keywords=["büro", "schreibwaren", "drucker", "papier", "toner"]
        ),
        "telefon": AccountMapping(
            konto="4920", name="Telefon", typ="aufwand", steuercode="9",
            keywords=["telefon", "telekom", "vodafone", "mobil", "handy"]
        ),
        "internet": AccountMapping(
            konto="4925", name="Internet", typ="aufwand", steuercode="9",
            keywords=["internet", "hosting", "domain", "server", "cloud"]
        ),
        "versicherung": AccountMapping(
            konto="4360", name="Versicherungen", typ="aufwand", steuercode="0",
            keywords=["versicherung", "allianz", "axa", "haftpflicht"]
        ),
        "miete": AccountMapping(
            konto="4210", name="Miete", typ="aufwand", steuercode="9",
            keywords=["miete", "büro", "gewerbe", "pacht"]
        ),
        "software": AccountMapping(
            konto="4964", name="Software/Wartung", typ="aufwand", steuercode="9",
            keywords=["software", "lizenz", "wartung", "microsoft", "adobe"]
        ),
        "beratung": AccountMapping(
            konto="4950", name="Rechts- und Beratungskosten", typ="aufwand", steuercode="9",
            keywords=["beratung", "rechtsanwalt", "steuerberater", "notar"]
        ),
        "werbung": AccountMapping(
            konto="4600", name="Werbekosten", typ="aufwand", steuercode="9",
            keywords=["werbung", "marketing", "google", "facebook", "anzeige"]
        ),
        "reise": AccountMapping(
            konto="4660", name="Reisekosten", typ="aufwand", steuercode="9",
            keywords=["reise", "fahrt", "hotel", "flug", "bahn"]
        ),
        "bewirtung": AccountMapping(
            konto="4650", name="Bewirtung", typ="aufwand", steuercode="9",
            keywords=["bewirtung", "restaurant", "essen", "geschäftsessen"]
        ),
        "kfz": AccountMapping(
            konto="4510", name="Kfz-Kosten", typ="aufwand", steuercode="9",
            keywords=["tankstelle", "benzin", "diesel", "werkstatt", "reparatur"]
        ),
        "porto": AccountMapping(
            konto="4910", name="Porto", typ="aufwand", steuercode="0",
            keywords=["porto", "briefmarke", "dhl", "ups", "versand"]
        ),
        "material": AccountMapping(
            konto="3400", name="Wareneinkauf", typ="aufwand", steuercode="9",
            keywords=["material", "ware", "einkauf", "lager"]
        ),
        "fremdleistung": AccountMapping(
            konto="4780", name="Fremdleistungen", typ="aufwand", steuercode="9",
            keywords=["fremdleistung", "subunternehmer", "dienstleistung"]
        ),

        # Ertragskonten
        "umsatz_19": AccountMapping(
            konto="8400", name="Erlöse 19%", typ="ertrag", steuercode="9",
            keywords=[]
        ),
        "umsatz_7": AccountMapping(
            konto="8300", name="Erlöse 7%", typ="ertrag", steuercode="8",
            keywords=[]
        ),

        # Kreditorenkonten
        "kreditor": AccountMapping(
            konto="70000", name="Kreditoren", typ="passiv",
            keywords=[]
        ),
        # Debitorenkonten
        "debitor": AccountMapping(
            konto="10000", name="Debitoren", typ="aktiv",
            keywords=[]
        ),

        # Bank
        "bank": AccountMapping(
            konto="1200", name="Bank", typ="aktiv",
            keywords=[]
        ),
    }

    # SKR04 Konten-Mappings
    SKR04_ACCOUNTS = {
        "buero": AccountMapping(
            konto="6815", name="Bürobedarf", typ="aufwand", steuercode="9",
            keywords=["büro", "schreibwaren", "drucker", "papier", "toner"]
        ),
        "telefon": AccountMapping(
            konto="6805", name="Telefon", typ="aufwand", steuercode="9",
            keywords=["telefon", "telekom", "vodafone", "mobil", "handy"]
        ),
        # ... weitere SKR04 Mappings analog
        "kreditor": AccountMapping(
            konto="70000", name="Kreditoren", typ="passiv",
            keywords=[]
        ),
        "debitor": AccountMapping(
            konto="10000", name="Debitoren", typ="aktiv",
            keywords=[]
        ),
        "bank": AccountMapping(
            konto="1800", name="Bank", typ="aktiv",
            keywords=[]
        ),
    }

    # USt-Sätze
    TAX_RATES = {
        19: ("9", Decimal("0.19")),
        7: ("8", Decimal("0.07")),
        0: ("0", Decimal("0")),
    }

    def __init__(self, kontenrahmen: str = "skr03"):
        """
        Initialisiere Service.

        Args:
            kontenrahmen: SKR03 oder SKR04
        """
        self.kontenrahmen = Kontenrahmen(kontenrahmen.lower())
        self.accounts = (
            self.SKR03_ACCOUNTS if self.kontenrahmen == Kontenrahmen.SKR03
            else self.SKR04_ACCOUNTS
        )

    def suggest_booking(
        self,
        ocr_text: str,
        extracted_data: Dict[str, Any],
        document_type: Optional[str] = None,
        entity_name: Optional[str] = None,
        entity_id: Optional[UUID] = None,
        custom_account_mappings: Optional[Dict[str, str]] = None,
    ) -> BookingSuggestion:
        """
        Generiere Buchungsvorschlag aus OCR-Daten.

        Args:
            ocr_text: Volltext aus OCR
            extracted_data: Strukturierte Daten (Betrag, Datum, etc.)
            document_type: Dokumenttyp (eingangsrechnung, ausgangsrechnung, etc.)
            entity_name: Name des Geschäftspartners
            entity_id: ID des Geschäftspartners (für Kontoaufloesung)
            custom_account_mappings: Benutzerdefinierte Konto-Zuordnungen

        Returns:
            BookingSuggestion mit Vorschlag
        """
        warnings = []
        confidence_details = {}

        # 1. Belegart bestimmen
        belegart, belegart_conf = self._detect_document_type(document_type, ocr_text)
        confidence_details["belegart"] = belegart_conf

        # 2. Betrag extrahieren
        betrag, betrag_conf = self._extract_amount(extracted_data, ocr_text)
        confidence_details["betrag"] = betrag_conf
        if betrag is None:
            warnings.append("Betrag konnte nicht ermittelt werden")
            betrag = Decimal("0")

        # 3. Datum extrahieren
        belegdatum, datum_conf = self._extract_date(extracted_data, ocr_text)
        confidence_details["datum"] = datum_conf
        if belegdatum is None:
            warnings.append("Belegdatum konnte nicht ermittelt werden")
            belegdatum = date.today()

        # 4. Steuersatz ermitteln
        steuersatz, steuercode, steuer_conf = self._detect_tax_rate(extracted_data, ocr_text)
        confidence_details["steuer"] = steuer_conf

        # 5. Netto/Brutto berechnen
        if steuersatz and steuersatz > 0:
            nettobetrag = betrag / (1 + Decimal(str(steuersatz / 100)))
            steuerbetrag = betrag - nettobetrag
        else:
            nettobetrag = betrag
            steuerbetrag = Decimal("0")

        # 6. Aufwandskonto ermitteln
        aufwandskonto, aufwand_name, aufwand_conf = self._suggest_expense_account(
            ocr_text, entity_name, custom_account_mappings
        )
        confidence_details["konto"] = aufwand_conf

        # 7. Gegenkonto ermitteln
        gegenkonto, gegen_name = self._get_counter_account(belegart, entity_id)

        # 8. Soll/Haben zuordnen
        if belegart in [Belegart.EINGANGSRECHNUNG.value, Belegart.GUTSCHRIFT_AUSGANG.value]:
            sollkonto = aufwandskonto
            sollkonto_name = aufwand_name
            habenkonto = gegenkonto
            habenkonto_name = gegen_name
        else:
            sollkonto = gegenkonto
            sollkonto_name = gegen_name
            habenkonto = aufwandskonto
            habenkonto_name = aufwand_name

        # 9. Buchungstext generieren
        buchungstext = self._generate_booking_text(
            entity_name=entity_name,
            rechnungsnummer=extracted_data.get("invoice_number"),
            aufwand_name=aufwand_name,
        )

        # 10. Rechnungsnummer
        rechnungsnummer = extracted_data.get("invoice_number")
        if rechnungsnummer and len(rechnungsnummer) > 36:
            rechnungsnummer = rechnungsnummer[:36]

        # 11. Kostenstelle (falls vorhanden)
        kostenstelle = self._detect_cost_center(ocr_text, extracted_data)

        # Gesamt-Confidence
        total_confidence = sum(confidence_details.values()) / len(confidence_details)

        # Prüfe ob Review erforderlich
        requires_review = total_confidence < 0.7 or len(warnings) > 0

        return BookingSuggestion(
            belegart=belegart,
            belegdatum=belegdatum,
            buchungstext=buchungstext[:60],
            betrag=betrag.quantize(Decimal("0.01")),
            sollkonto=sollkonto,
            habenkonto=habenkonto,
            sollkonto_name=sollkonto_name,
            habenkonto_name=habenkonto_name,
            steuercode=steuercode,
            steuersatz=steuersatz,
            steuerbetrag=steuerbetrag.quantize(Decimal("0.01")) if steuerbetrag else None,
            nettobetrag=nettobetrag.quantize(Decimal("0.01")) if nettobetrag else None,
            rechnungsnummer=rechnungsnummer,
            gegenkonto_name=entity_name,
            kostenstelle=kostenstelle,
            confidence=round(total_confidence, 4),
            confidence_details=confidence_details,
            warnings=warnings,
            requires_review=requires_review,
        )

    def _detect_document_type(
        self,
        document_type: Optional[str],
        ocr_text: str,
    ) -> Tuple[str, float]:
        """Erkenne Belegart."""
        text_lower = ocr_text.lower()

        # Wenn bereits klassifiziert
        if document_type:
            doc_map = {
                "eingangsrechnung": (Belegart.EINGANGSRECHNUNG.value, 0.95),
                "ausgangsrechnung": (Belegart.AUSGANGSRECHNUNG.value, 0.95),
                "gutschrift": (Belegart.GUTSCHRIFT_EINGANG.value, 0.90),
                "bank": (Belegart.BANK.value, 0.95),
                "kasse": (Belegart.KASSE.value, 0.95),
            }
            for key, (belegart, conf) in doc_map.items():
                if key in document_type.lower():
                    return belegart, conf

        # Textbasierte Erkennung
        if "gutschrift" in text_lower:
            return Belegart.GUTSCHRIFT_EINGANG.value, 0.85

        if any(word in text_lower for word in ["rechnung", "invoice", "faktura"]):
            # Unterscheide Eingang/Ausgang
            if any(word in text_lower for word in ["bitte überweisen", "zahlbar bis", "zahlung an"]):
                return Belegart.EINGANGSRECHNUNG.value, 0.80
            return Belegart.AUSGANGSRECHNUNG.value, 0.70

        return Belegart.SONSTIGES.value, 0.50

    def _extract_amount(
        self,
        extracted_data: Dict[str, Any],
        ocr_text: str,
    ) -> Tuple[Optional[Decimal], float]:
        """Extrahiere Betrag."""
        # Aus strukturierten Daten
        for field in ["total_amount", "gross_amount", "amount", "betrag"]:
            if field in extracted_data and extracted_data[field]:
                try:
                    amount = Decimal(str(extracted_data[field]))
                    return amount, 0.95
                except (InvalidOperation, ValueError):
                    pass

        # Aus OCR-Text
        patterns = [
            r"gesamtbetrag[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            r"brutto[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            r"endbetrag[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            r"summe[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
            r"total[:\s]*([0-9.,]+)\s*(?:€|EUR)?",
        ]

        for pattern in patterns:
            match = re.search(pattern, ocr_text.lower())
            if match:
                try:
                    amount_str = match.group(1).replace(".", "").replace(",", ".")
                    amount = Decimal(amount_str)
                    return amount, 0.75
                except (InvalidOperation, ValueError):
                    continue

        return None, 0.0

    def _extract_date(
        self,
        extracted_data: Dict[str, Any],
        ocr_text: str,
    ) -> Tuple[Optional[date], float]:
        """Extrahiere Belegdatum."""
        # Aus strukturierten Daten
        for field in ["invoice_date", "document_date", "date", "datum"]:
            if field in extracted_data and extracted_data[field]:
                if isinstance(extracted_data[field], date):
                    return extracted_data[field], 0.95
                try:
                    parsed = datetime.fromisoformat(str(extracted_data[field]))
                    return parsed.date(), 0.90
                except ValueError:
                    pass

        # Aus OCR-Text
        patterns = [
            (r"(\d{2})[./](\d{2})[./](\d{4})", "%d.%m.%Y"),
            (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
        ]

        for pattern, fmt in patterns:
            match = re.search(pattern, ocr_text)
            if match:
                try:
                    date_str = match.group(0)
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed.date(), 0.70
                except ValueError:
                    continue

        return None, 0.0

    def _detect_tax_rate(
        self,
        extracted_data: Dict[str, Any],
        ocr_text: str,
    ) -> Tuple[Optional[float], Optional[str], float]:
        """Erkenne Steuersatz."""
        # Aus strukturierten Daten
        for field in ["tax_rate", "vat_rate", "mwst"]:
            if field in extracted_data and extracted_data[field] is not None:
                rate = float(extracted_data[field])
                if rate in [19, 0.19]:
                    return 19, "9", 0.95
                elif rate in [7, 0.07]:
                    return 7, "8", 0.95
                elif rate == 0:
                    return 0, "0", 0.95

        # Aus OCR-Text
        text_lower = ocr_text.lower()

        if "19%" in text_lower or "19 %" in text_lower:
            return 19, "9", 0.85
        elif "7%" in text_lower or "7 %" in text_lower:
            return 7, "8", 0.85
        elif "steuerfrei" in text_lower or "mwst-frei" in text_lower:
            return 0, "0", 0.80

        # Reverse Charge / EU
        if "reverse charge" in text_lower or "steuerschuldnerschaft" in text_lower:
            return 0, "94", 0.80

        # Default: 19%
        return 19, "9", 0.60

    def _suggest_expense_account(
        self,
        ocr_text: str,
        entity_name: Optional[str],
        custom_mappings: Optional[Dict[str, str]],
    ) -> Tuple[str, str, float]:
        """Ermittle passendes Aufwandskonto."""
        text_lower = ocr_text.lower()
        entity_lower = (entity_name or "").lower()

        # Benutzerdefinierte Mappings zuerst
        if custom_mappings:
            for keyword, konto in custom_mappings.items():
                if keyword.lower() in text_lower or keyword.lower() in entity_lower:
                    return konto, f"Benutzerdefiniert ({keyword})", 0.90

        # Standard-Mappings
        best_match = None
        best_score = 0

        for key, account in self.accounts.items():
            if account.typ != "aufwand":
                continue

            score = 0
            for keyword in account.keywords:
                if keyword in text_lower:
                    score += 1
                if keyword in entity_lower:
                    score += 2

            if score > best_score:
                best_score = score
                best_match = account

        if best_match and best_score > 0:
            confidence = min(0.90, 0.5 + (best_score * 0.1))
            return best_match.konto, best_match.name, confidence

        # Fallback: Sonstige Aufwendungen
        fallback = self.accounts.get("fremdleistung", self.accounts["buero"])
        return fallback.konto, fallback.name, 0.40

    def _get_counter_account(
        self,
        belegart: str,
        entity_id: Optional[UUID],
    ) -> Tuple[str, str]:
        """Ermittle Gegenkonto (Kreditor/Debitor)."""
        if belegart in [Belegart.EINGANGSRECHNUNG.value, Belegart.GUTSCHRIFT_AUSGANG.value]:
            # Kreditor
            if entity_id:
                # Personenkonto basierend auf Entity-ID
                konto = f"70{str(entity_id)[:3].replace('-', '')}"
            else:
                konto = self.accounts["kreditor"].konto
            return konto, "Verbindlichkeiten aus L+L"
        else:
            # Debitor
            if entity_id:
                konto = f"10{str(entity_id)[:3].replace('-', '')}"
            else:
                konto = self.accounts["debitor"].konto
            return konto, "Forderungen aus L+L"

    def _generate_booking_text(
        self,
        entity_name: Optional[str],
        rechnungsnummer: Optional[str],
        aufwand_name: Optional[str],
    ) -> str:
        """Generiere Buchungstext (max 60 Zeichen)."""
        parts = []

        if entity_name:
            # Kürze langen Namen
            name = entity_name[:25] if len(entity_name) > 25 else entity_name
            parts.append(name)

        if rechnungsnummer:
            parts.append(f"RE {rechnungsnummer[:15]}")
        elif aufwand_name:
            parts.append(aufwand_name[:20])

        text = " / ".join(parts)
        return text[:60] if len(text) > 60 else text

    def _detect_cost_center(
        self,
        ocr_text: str,
        extracted_data: Dict[str, Any],
    ) -> Optional[str]:
        """Erkenne Kostenstelle."""
        # Aus strukturierten Daten
        for field in ["cost_center", "kostenstelle", "kst"]:
            if field in extracted_data and extracted_data[field]:
                return str(extracted_data[field])

        # Aus OCR-Text
        patterns = [
            r"kostenstelle[:\s]*([0-9]+)",
            r"kst[:\s]*([0-9]+)",
            r"projekt[:\s]*([0-9]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, ocr_text.lower())
            if match:
                return match.group(1)

        return None

    def batch_suggest(
        self,
        documents: List[Dict[str, Any]],
    ) -> List[BookingSuggestion]:
        """
        Batch-Vorschläge für mehrere Dokumente.

        Args:
            documents: Liste von Dokumenten mit ocr_text und extracted_data

        Returns:
            Liste von Buchungsvorschlägen
        """
        suggestions = []

        for doc in documents:
            try:
                suggestion = self.suggest_booking(
                    ocr_text=doc.get("ocr_text", ""),
                    extracted_data=doc.get("extracted_data", {}),
                    document_type=doc.get("document_type"),
                    entity_name=doc.get("entity_name"),
                    entity_id=doc.get("entity_id"),
                )
                suggestions.append(suggestion)
            except Exception as e:
                logger.error(f"Booking suggestion failed: {e}")
                # Erstelle Fehler-Vorschlag
                suggestions.append(
                    BookingSuggestion(
                        belegart=Belegart.SONSTIGES.value,
                        belegdatum=date.today(),
                        buchungstext="FEHLER - Manuelle Prüfung",
                        betrag=Decimal("0"),
                        sollkonto="9999",
                        habenkonto="9999",
                        confidence=0,
                        warnings=[f"Verarbeitung fehlgeschlagen: {str(e)}"],
                        requires_review=True,
                    )
                )

        return suggestions

    def export_to_datev_format(
        self,
        suggestions: List[BookingSuggestion],
        mandant_nr: str,
        berater_nr: str,
        wirtschaftsjahr: int,
    ) -> str:
        """
        Exportiere Vorschläge im DATEV-Format.

        Args:
            suggestions: Liste von Buchungsvorschlägen
            mandant_nr: Mandantennummer
            berater_nr: Beraternummer
            wirtschaftsjahr: Wirtschaftsjahr

        Returns:
            DATEV-formatierter String
        """
        lines = []

        # Header
        header = (
            f'"EXTF";700;21;"Buchungsstapel";'
            f'"{berater_nr}";"{mandant_nr}";{wirtschaftsjahr};'
            f'"";"";"";"";"";"";"";"";"";""'
        )
        lines.append(header)

        # Buchungen
        for sugg in suggestions:
            if sugg.requires_review and sugg.confidence < 0.5:
                continue  # Überspringe unsichere Buchungen

            line = (
                f'"{sugg.belegart}";'
                f'{float(sugg.betrag):.2f};'
                f'"S";"";'
                f'"{sugg.sollkonto}";"{sugg.habenkonto}";'
                f'{sugg.steuercode or ""};'
                f'{sugg.belegdatum.strftime("%d%m")};'
                f'"{sugg.buchungstext}";'
                f'"{sugg.rechnungsnummer or ""}";'
                f'"{sugg.kostenstelle or ""}"'
            )
            lines.append(line)

        return "\n".join(lines)
