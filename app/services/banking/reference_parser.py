"""Reference Text Parser.

Extrahiert strukturierte Daten aus Verwendungszweck (Referenztext):
- Rechnungsnummern
- Kundennummern
- Auftragsnummern
- SEPA-Mandate
- End-to-End-IDs
- Datumsangaben
- Zahlungsreferenzen
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Pattern
from datetime import date, datetime
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ParsedReference:
    """Ergebnis der Referenztext-Analyse."""
    # Rechnungsbezogene Referenzen
    invoice_numbers: List[str] = field(default_factory=list)
    order_numbers: List[str] = field(default_factory=list)
    customer_numbers: List[str] = field(default_factory=list)
    contract_numbers: List[str] = field(default_factory=list)

    # SEPA-spezifisch
    end_to_end_id: Optional[str] = None
    mandate_id: Optional[str] = None
    creditor_id: Optional[str] = None

    # Datumsangaben
    dates: List[date] = field(default_factory=list)
    period_from: Optional[date] = None
    period_to: Optional[date] = None

    # Sonstige
    payment_purpose: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    raw_text: str = ""


class ReferenceParser:
    """Parser fuer Verwendungszweck-Texte."""

    # Rechnungsnummer-Muster
    INVOICE_PATTERNS: List[Pattern] = [
        # Explizite Praefixe
        re.compile(r"(?:RE(?:CH(?:NUNG)?)?|RG|INV(?:OICE)?|FAKTURA?)[\s.\-:/#]*(\d{4,}[-/]?\d*)", re.IGNORECASE),
        # Rechnungsnummer mit Jahr
        re.compile(r"(?:RECHN(?:UNG)?|RE)[\s.\-:/#]*NR[\s.\-:/#]*([A-Z0-9]{2,}[-/]?\d{2,})", re.IGNORECASE),
        # ISO-Format
        re.compile(r"\b([A-Z]{2,4}[-]?\d{4}[-]?\d{4,})\b"),
        # Datum-basierte Nummern
        re.compile(r"\b(20\d{2}[-/]\d{4,})\b"),
    ]

    # Kundennummer-Muster
    CUSTOMER_PATTERNS: List[Pattern] = [
        re.compile(r"(?:KD|KUND(?:EN)?|KUNDEN?)[\s.\-:/#]*(?:NR|NUMMER)?[\s.\-:/#]*(\d{4,})", re.IGNORECASE),
        re.compile(r"(?:DEBITOREN?)[\s.\-:/#]*(?:NR)?[\s.\-:/#]*(\d{4,})", re.IGNORECASE),
        re.compile(r"(?:KTNR|KTO)[\s.\-:/#]*(\d{4,})", re.IGNORECASE),
    ]

    # Auftragsnummer-Muster
    ORDER_PATTERNS: List[Pattern] = [
        re.compile(r"(?:AUFTR(?:AG)?|BESTELL(?:UNG)?|ORDER|PO)[\s.\-:/#]*(?:NR)?[\s.\-:/#]*([A-Z0-9]{4,})", re.IGNORECASE),
        re.compile(r"(?:BESTELLUNG|AUFTRAG)[\s.\-:/#]*(\d{4,})", re.IGNORECASE),
    ]

    # Vertragsnummer-Muster
    CONTRACT_PATTERNS: List[Pattern] = [
        re.compile(r"(?:VERTR(?:AG)?|CONTR(?:ACT)?)[\s.\-:/#]*(?:NR)?[\s.\-:/#]*([A-Z0-9]{4,})", re.IGNORECASE),
        re.compile(r"(?:VTR|VNR)[\s.\-:/#]*(\d{4,})", re.IGNORECASE),
    ]

    # SEPA-Referenzen
    # Hinweis: _normalize_text wandelt + in Leerzeichen um, daher [\s+]* fuer beide Faelle
    E2E_PATTERN = re.compile(r"(?:EREF[\s+]*|END[\s-]*TO[\s-]*END[\s-]*ID[\s.:]*|E2E[\s.:]*|KREF[\s+]*)([A-Z0-9+/\-]+)", re.IGNORECASE)
    MANDATE_PATTERN = re.compile(r"(?:MREF[\s+]*|MANDAT[\s-]*(?:ID|REF)?[\s.:]*|MAND[\s.:]*|MANDATSREF[\s.:]*|MNDTID[\s+:]+)([A-Z0-9+/\-]+)", re.IGNORECASE)
    CREDITOR_PATTERN = re.compile(r"(?:CRED[\s+]*|CREDITOR[\s-]*ID[\s.:]*|GLAUB[\s.:]*ID[\s.:]*|CI[\s.:]*|CREDITORID[\s+:]+)([A-Z]{2}\d{2}[A-Z0-9]+)", re.IGNORECASE)

    # Datums-Muster
    DATE_PATTERNS: List[Pattern] = [
        re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b"),  # DD.MM.YYYY
        re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),  # YYYY-MM-DD
        re.compile(r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{2})\b"),    # DD-MM-YY
    ]

    # Perioden-Muster
    PERIOD_PATTERN = re.compile(
        r"(?:ZEITRAUM|PERIODE|MONAT|VON[\s-]*BIS|FÜR)[\s.:]*"
        r"(\d{1,2}[./]\d{1,2}[./]?\d{2,4}?)[\s-]*(?:BIS|[-–]|/)[\s-]*"
        r"(\d{1,2}[./]\d{1,2}[./]?\d{2,4}?)",
        re.IGNORECASE
    )

    # Zahlungszweck-Keywords
    PURPOSE_KEYWORDS = {
        "miete": ["MIETE", "MIETZA", "PACHT", "WARMMIETE", "KALTMIETE"],
        "gehalt": ["GEHALT", "LOHN", "VERGÜTUNG", "ENTGELT", "SALARY"],
        "rechnung": ["RECHNUNG", "FAKTURA", "INVOICE", "BELEG"],
        "versicherung": ["VERSICHERUNG", "VERS", "BEITRAG", "PRÄMIE"],
        "strom": ["STROM", "ENERGIE", "ABSCHLAG", "STADTWERKE"],
        "telefon": ["TELEFON", "TELEKOM", "VODAFONE", "O2", "MOBILFUNK"],
        "mitgliedschaft": ["MITGLIED", "BEITRAG", "VEREIN", "CLUB"],
        "kredit": ["RATE", "TILGUNG", "KREDIT", "DARLEHEN", "ZINSEN"],
        "lastschrift": ["SEPA", "LASTSCHRIFT", "EINZUG", "MANDATE"],
    }

    def parse(self, text: str) -> ParsedReference:
        """Parse Referenztext und extrahiere strukturierte Daten.

        Args:
            text: Verwendungszweck/Referenztext

        Returns:
            ParsedReference mit extrahierten Daten
        """
        if not text:
            return ParsedReference(raw_text="")

        # Normalisiere Text
        normalized = self._normalize_text(text)
        result = ParsedReference(raw_text=text)

        # Extrahiere verschiedene Referenztypen
        result.invoice_numbers = self._extract_patterns(normalized, self.INVOICE_PATTERNS)
        result.customer_numbers = self._extract_patterns(normalized, self.CUSTOMER_PATTERNS)
        result.order_numbers = self._extract_patterns(normalized, self.ORDER_PATTERNS)
        result.contract_numbers = self._extract_patterns(normalized, self.CONTRACT_PATTERNS)

        # SEPA-Referenzen
        result.end_to_end_id = self._extract_single_pattern(normalized, self.E2E_PATTERN)
        result.mandate_id = self._extract_single_pattern(normalized, self.MANDATE_PATTERN)
        result.creditor_id = self._extract_single_pattern(normalized, self.CREDITOR_PATTERN)

        # Datumsangaben
        result.dates = self._extract_dates(normalized)
        period = self._extract_period(normalized)
        if period:
            result.period_from, result.period_to = period

        # Zahlungszweck und Keywords
        result.payment_purpose = self._detect_purpose(normalized)
        result.keywords = self._extract_keywords(normalized)

        return result

    def _normalize_text(self, text: str) -> str:
        """Normalisiere Text fuer bessere Pattern-Erkennung."""
        # Uppercase fuer einfacheres Matching
        text = text.upper()
        # Mehrfache Leerzeichen reduzieren
        text = re.sub(r"\s+", " ", text)
        # SEPA-Trennzeichen normalisieren
        text = text.replace("++", " ").replace("+", " ")
        return text.strip()

    def _extract_patterns(self, text: str, patterns: List[Pattern]) -> List[str]:
        """Extrahiere alle Matches fuer gegebene Patterns."""
        results = []
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = match.group(1).strip()
                if value and value not in results:
                    results.append(value)
        return results

    def _extract_single_pattern(self, text: str, pattern: Pattern) -> Optional[str]:
        """Extrahiere ersten Match fuer Pattern."""
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
        return None

    def _extract_dates(self, text: str) -> List[date]:
        """Extrahiere Datumsangaben aus Text."""
        dates = []
        for pattern in self.DATE_PATTERNS:
            for match in pattern.finditer(text):
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        # Bestimme Format basierend auf erstem Wert
                        if int(groups[0]) > 31:  # YYYY-MM-DD
                            year = int(groups[0])
                            month = int(groups[1])
                            day = int(groups[2])
                        else:  # DD.MM.YYYY oder DD-MM-YY
                            day = int(groups[0])
                            month = int(groups[1])
                            year = int(groups[2])
                            if year < 100:
                                year += 2000

                        if 1 <= month <= 12 and 1 <= day <= 31:
                            parsed_date = date(year, month, day)
                            if parsed_date not in dates:
                                dates.append(parsed_date)
                except (ValueError, IndexError):
                    continue
        return sorted(dates)

    def _extract_period(self, text: str) -> Optional[tuple]:
        """Extrahiere Zeitraum (von-bis)."""
        match = self.PERIOD_PATTERN.search(text)
        if match:
            try:
                from_str, to_str = match.groups()
                # Einfache Datumsextraktion
                from_date = self._parse_simple_date(from_str)
                to_date = self._parse_simple_date(to_str)
                if from_date and to_date:
                    return (from_date, to_date)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_simple_date(self, date_str: str) -> Optional[date]:
        """Parse einfaches Datum."""
        parts = re.split(r"[./]", date_str.strip())
        if len(parts) >= 2:
            try:
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2]) if len(parts) > 2 else datetime.now().year
                if year < 100:
                    year += 2000
                return date(year, month, day)
            except (ValueError, IndexError):
                pass
        return None

    def _detect_purpose(self, text: str) -> Optional[str]:
        """Erkenne Zahlungszweck anhand Keywords."""
        for purpose, keywords in self.PURPOSE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    return purpose
        return None

    def _extract_keywords(self, text: str) -> List[str]:
        """Extrahiere relevante Keywords."""
        keywords = []
        for purpose, purpose_keywords in self.PURPOSE_KEYWORDS.items():
            for keyword in purpose_keywords:
                if keyword in text and keyword not in keywords:
                    keywords.append(keyword)
        return keywords

    def to_dict(self, result: ParsedReference) -> Dict[str, Any]:
        """Konvertiere ParsedReference zu Dictionary."""
        return {
            "invoice_numbers": result.invoice_numbers,
            "order_numbers": result.order_numbers,
            "customer_numbers": result.customer_numbers,
            "contract_numbers": result.contract_numbers,
            "end_to_end_id": result.end_to_end_id,
            "mandate_id": result.mandate_id,
            "creditor_id": result.creditor_id,
            "dates": [d.isoformat() for d in result.dates],
            "period_from": result.period_from.isoformat() if result.period_from else None,
            "period_to": result.period_to.isoformat() if result.period_to else None,
            "payment_purpose": result.payment_purpose,
            "keywords": result.keywords,
        }


# Singleton-Instanz
reference_parser = ReferenceParser()


def parse_reference_text(text: str) -> ParsedReference:
    """Convenience-Funktion fuer Reference Parsing."""
    return reference_parser.parse(text)


def extract_invoice_numbers(text: str) -> List[str]:
    """Extrahiere nur Rechnungsnummern."""
    result = reference_parser.parse(text)
    return result.invoice_numbers


def extract_sepa_references(text: str) -> Dict[str, Optional[str]]:
    """Extrahiere SEPA-Referenzen (E2E, Mandat, Creditor ID)."""
    result = reference_parser.parse(text)
    return {
        "end_to_end_id": result.end_to_end_id,
        "mandate_id": result.mandate_id,
        "creditor_id": result.creditor_id,
    }
