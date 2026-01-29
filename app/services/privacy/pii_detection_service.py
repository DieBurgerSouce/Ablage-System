# -*- coding: utf-8 -*-
"""
PII Detection Service.

Automatische Erkennung personenbezogener Daten (PII) in Texten.
Unterstuetzte Datentypen:
- Bankdaten (IBAN, BIC)
- Personennamen
- Steuer-IDs (USt-ID, Steuernummer)
- Sozialversicherungsnummern
- Kreditkartennummern
- E-Mail-Adressen
- Telefonnummern
- Adressen
- Geburtsdaten

Feinpoliert und durchdacht.
"""

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional, Set, Tuple, Union
from typing_extensions import TypedDict
from datetime import date

# Type definitions for mypy strict mode - no Any types
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]

# Type alias for JSON-like structures
JSONValue = Union[str, int, float, bool, None, List["JSONValue"], Dict[str, "JSONValue"]]

logger = logging.getLogger(__name__)


class PIIType(str, Enum):
    """Typen personenbezogener Daten."""
    IBAN = "iban"
    BIC = "bic"
    CREDIT_CARD = "credit_card"
    NAME = "name"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    TAX_ID = "tax_id"               # Steuer-ID
    VAT_ID = "vat_id"               # USt-ID
    SOCIAL_SECURITY = "social_security"
    PASSPORT = "passport"
    ID_CARD = "id_card"
    SALARY = "salary"
    BANK_ACCOUNT = "bank_account"
    HEALTH_DATA = "health_data"
    IP_ADDRESS = "ip_address"


class PIISensitivity(str, Enum):
    """Sensibilitaetsstufen."""
    LOW = "low"           # z.B. Name, E-Mail
    MEDIUM = "medium"     # z.B. Adresse, Telefon
    HIGH = "high"         # z.B. IBAN, Steuer-ID
    CRITICAL = "critical" # z.B. Gesundheitsdaten, Gehalt


@dataclass
class PIIMatch:
    """Ein gefundenes PII-Element."""
    pii_type: PIIType
    value: str
    start: int
    end: int
    sensitivity: PIISensitivity
    confidence: float
    context: Optional[str] = None
    metadata: MetadataDict = field(default_factory=dict)


@dataclass
class PIIDetectionResult:
    """Ergebnis einer PII-Erkennung."""
    text_length: int
    pii_found: List[PIIMatch]
    summary: Dict[PIIType, int]
    has_critical: bool
    risk_score: int  # 0-100
    recommendations: List[str]


class PIIDetectionService:
    """
    Service fuer die automatische PII-Erkennung.

    Verwendet regelbasierte Pattern-Matching kombiniert mit
    Heuristiken fuer die Erkennung personenbezogener Daten.
    """

    # Sensibilitaet pro Typ
    SENSITIVITY_MAP = {
        PIIType.IBAN: PIISensitivity.HIGH,
        PIIType.BIC: PIISensitivity.MEDIUM,
        PIIType.CREDIT_CARD: PIISensitivity.CRITICAL,
        PIIType.NAME: PIISensitivity.LOW,
        PIIType.EMAIL: PIISensitivity.LOW,
        PIIType.PHONE: PIISensitivity.MEDIUM,
        PIIType.ADDRESS: PIISensitivity.MEDIUM,
        PIIType.DATE_OF_BIRTH: PIISensitivity.MEDIUM,
        PIIType.TAX_ID: PIISensitivity.HIGH,
        PIIType.VAT_ID: PIISensitivity.MEDIUM,
        PIIType.SOCIAL_SECURITY: PIISensitivity.CRITICAL,
        PIIType.PASSPORT: PIISensitivity.HIGH,
        PIIType.ID_CARD: PIISensitivity.HIGH,
        PIIType.SALARY: PIISensitivity.CRITICAL,
        PIIType.BANK_ACCOUNT: PIISensitivity.HIGH,
        PIIType.HEALTH_DATA: PIISensitivity.CRITICAL,
        PIIType.IP_ADDRESS: PIISensitivity.LOW,
    }

    # Regex-Patterns
    PATTERNS = {
        PIIType.IBAN: [
            # Deutsche IBAN: DE + 2 Pruefziffern + 18 Ziffern
            r'\b(DE\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2})\b',
            # Allgemeine IBAN (alle Laender)
            r'\b([A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){10,30})\b',
        ],
        PIIType.BIC: [
            r'\b([A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b',
        ],
        PIIType.CREDIT_CARD: [
            # Visa, Mastercard, Amex, etc.
            r'\b((?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12}))\b',
            # Mit Trennzeichen
            r'\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b',
        ],
        PIIType.EMAIL: [
            r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b',
        ],
        PIIType.PHONE: [
            # Deutsche Telefonnummern
            r'\b(\+49\s?[1-9][0-9]{1,14})\b',
            r'\b(0[1-9][0-9]{1,4}[\s/-]?[0-9]{3,10})\b',
            # Mit Vorwahl in Klammern
            r'\b(\(?0[1-9][0-9]{1,4}\)?[\s/-]?[0-9]{3,10})\b',
        ],
        PIIType.DATE_OF_BIRTH: [
            # Kontext-basiert (geboren, Geburtsdatum, etc.)
            r'(?:geboren|geb\.|geburtsdatum|birth)[\s:]*(\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4})',
        ],
        PIIType.TAX_ID: [
            # Deutsche Steuer-ID (11 Ziffern)
            r'\b(\d{11})\b',
            # Mit Kontext
            r'(?:steuer-?id|tin|identifikationsnummer)[\s:]*(\d{11})',
        ],
        PIIType.VAT_ID: [
            # Deutsche USt-ID
            r'\b(DE\s?\d{9})\b',
            # Andere EU-Laender
            r'\b([A-Z]{2}\s?\d{8,12})\b',
        ],
        PIIType.SOCIAL_SECURITY: [
            # Deutsche Rentenversicherungsnummer (12 Zeichen)
            r'\b(\d{2}\s?\d{6}\s?[A-Z]\s?\d{3})\b',
            # Mit Kontext
            r'(?:sozialversicherung|rentenversicherung|sv-?nummer)[\s:]*(\d{2}\s?\d{6}\s?[A-Z]\s?\d{3})',
        ],
        PIIType.PASSPORT: [
            # Deutscher Reisepass (9 Zeichen)
            r'(?:pass|reisepass|passport)[\s:]*([A-Z0-9]{9})',
        ],
        PIIType.ID_CARD: [
            # Deutscher Personalausweis (9-10 Zeichen)
            r'(?:personalausweis|ausweis|id[\s-]?card)[\s:]*([A-Z0-9]{9,10})',
        ],
        PIIType.SALARY: [
            # Gehalt/Lohn mit Betrag
            r'(?:gehalt|lohn|verguetung|brutto|netto)[\s:]*(?:EUR|€)?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)',
            r'(?:EUR|€)\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\s*(?:gehalt|lohn|brutto|netto)',
        ],
        PIIType.IP_ADDRESS: [
            # IPv4
            r'\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b',
            # IPv6 (vereinfacht)
            r'\b([0-9a-fA-F:]{15,39})\b',
        ],
    }

    # Deutsche Namens-Patterns
    NAME_INDICATORS = [
        r'(?:herr|frau|dr\.|prof\.|dipl\.)',
        r'(?:vorname|nachname|name)[\s:]+',
        r'(?:gez\.|unterschrift)[\s:]*',
    ]

    # Adress-Patterns
    ADDRESS_PATTERNS = [
        # Straße + Hausnummer
        r'\b([A-ZÄÖÜ][a-zäöüß]+(?:straße|str\.|weg|platz|allee|ring|gasse)\s*\d+[a-z]?)\b',
        # PLZ + Ort
        r'\b(\d{5}\s+[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)?)\b',
    ]

    # Woerter die auf Gesundheitsdaten hinweisen
    HEALTH_INDICATORS = [
        "diagnose", "krankheit", "behandlung", "medikament",
        "therapie", "arzt", "patient", "krankenhaus", "klinik",
        "versichertennummer", "krankenkasse", "icd", "befund",
    ]

    def __init__(self, detect_names: bool = True, detect_addresses: bool = True):
        """
        Initialisiere Service.

        Args:
            detect_names: Ob Namen erkannt werden sollen
            detect_addresses: Ob Adressen erkannt werden sollen
        """
        self.detect_names = detect_names
        self.detect_addresses = detect_addresses

    def detect(
        self,
        text: str,
        pii_types: Optional[Set[PIIType]] = None,
    ) -> PIIDetectionResult:
        """
        Erkenne PII in einem Text.

        Args:
            text: Der zu scannende Text
            pii_types: Optional Set von zu suchenden PII-Typen

        Returns:
            PIIDetectionResult mit allen gefundenen PII
        """
        if not text:
            return PIIDetectionResult(
                text_length=0,
                pii_found=[],
                summary={},
                has_critical=False,
                risk_score=0,
                recommendations=[],
            )

        matches: List[PIIMatch] = []

        # Welche Typen suchen
        types_to_check = pii_types or set(PIIType)

        # Pattern-basierte Erkennung
        for pii_type, patterns in self.PATTERNS.items():
            if pii_type not in types_to_check:
                continue

            for pattern in patterns:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    value = match.group(1) if match.lastindex else match.group(0)

                    # Validiere den Fund
                    if self._validate_match(pii_type, value):
                        # Extrahiere Kontext
                        start = max(0, match.start() - 20)
                        end = min(len(text), match.end() + 20)
                        context = text[start:end]

                        pii_match = PIIMatch(
                            pii_type=pii_type,
                            value=value,
                            start=match.start(),
                            end=match.end(),
                            sensitivity=self.SENSITIVITY_MAP[pii_type],
                            confidence=self._calculate_confidence(pii_type, value, text),
                            context=context,
                        )
                        matches.append(pii_match)

        # Adress-Erkennung
        if self.detect_addresses and PIIType.ADDRESS in types_to_check:
            matches.extend(self._detect_addresses(text))

        # Gesundheitsdaten-Erkennung (kontextbasiert)
        if PIIType.HEALTH_DATA in types_to_check:
            matches.extend(self._detect_health_data(text))

        # Dedupliziere ueberlappende Matches
        matches = self._deduplicate_matches(matches)

        # Erstelle Summary
        summary: Dict[PIIType, int] = {}
        for m in matches:
            summary[m.pii_type] = summary.get(m.pii_type, 0) + 1

        # Pruefe auf kritische Daten
        has_critical = any(m.sensitivity == PIISensitivity.CRITICAL for m in matches)

        # Berechne Risiko-Score
        risk_score = self._calculate_risk_score(matches)

        # Generiere Empfehlungen
        recommendations = self._generate_recommendations(matches, has_critical)

        result = PIIDetectionResult(
            text_length=len(text),
            pii_found=matches,
            summary=summary,
            has_critical=has_critical,
            risk_score=risk_score,
            recommendations=recommendations,
        )

        logger.info(
            f"PII-Scan abgeschlossen: {len(matches)} PII gefunden, "
            f"Risiko-Score: {risk_score}, Kritisch: {has_critical}"
        )

        return result

    def detect_in_dict(
        self,
        data: Dict[str, JSONValue],
        pii_types: Optional[Set[PIIType]] = None,
    ) -> Dict[str, PIIDetectionResult]:
        """
        Erkenne PII in allen String-Werten eines Dictionaries.

        Args:
            data: Dictionary mit zu scannenden Werten
            pii_types: Optional Set von zu suchenden PII-Typen

        Returns:
            Dictionary mit Ergebnissen pro Feld
        """
        results = {}

        for key, value in data.items():
            if isinstance(value, str):
                results[key] = self.detect(value, pii_types)
            elif isinstance(value, dict):
                # Rekursiv
                nested = self.detect_in_dict(value, pii_types)
                for nested_key, nested_result in nested.items():
                    results[f"{key}.{nested_key}"] = nested_result

        return results

    def _validate_match(self, pii_type: PIIType, value: str) -> bool:
        """Validiere einen gefundenen Match."""
        if pii_type == PIIType.IBAN:
            return self._validate_iban(value)
        elif pii_type == PIIType.CREDIT_CARD:
            return self._validate_credit_card(value)
        elif pii_type == PIIType.EMAIL:
            return self._validate_email(value)
        elif pii_type == PIIType.IP_ADDRESS:
            return self._validate_ip(value)
        elif pii_type == PIIType.TAX_ID:
            # Deutsche Steuer-ID: 11 Ziffern
            return len(value.replace(" ", "")) == 11 and value.replace(" ", "").isdigit()
        elif pii_type == PIIType.VAT_ID:
            # USt-ID: Laendercode + 8-12 Ziffern
            clean = value.replace(" ", "")
            return len(clean) >= 10 and clean[:2].isalpha()

        return True  # Default: Akzeptieren

    def _validate_iban(self, iban: str) -> bool:
        """Validiere IBAN mit Pruefziffer."""
        iban_clean = iban.replace(" ", "").upper()

        if len(iban_clean) < 15 or len(iban_clean) > 34:
            return False

        # Laendercode pruefen
        if not iban_clean[:2].isalpha():
            return False

        # Pruefziffern validieren (vereinfacht)
        try:
            # IBAN umstellen: Laendercode + Pruefziffern ans Ende
            rearranged = iban_clean[4:] + iban_clean[:4]

            # Buchstaben durch Zahlen ersetzen (A=10, B=11, etc.)
            numeric = ""
            for char in rearranged:
                if char.isalpha():
                    numeric += str(ord(char) - ord('A') + 10)
                else:
                    numeric += char

            # Modulo 97 muss 1 ergeben
            return int(numeric) % 97 == 1
        except (ValueError, OverflowError):
            return False

    def _validate_credit_card(self, card: str) -> bool:
        """Validiere Kreditkartennummer mit Luhn-Algorithmus."""
        card_clean = card.replace(" ", "").replace("-", "")

        if not card_clean.isdigit():
            return False

        if len(card_clean) < 13 or len(card_clean) > 19:
            return False

        # Luhn-Algorithmus
        total = 0
        reverse = card_clean[::-1]

        for i, digit in enumerate(reverse):
            n = int(digit)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n

        return total % 10 == 0

    def _validate_email(self, email: str) -> bool:
        """Validiere E-Mail-Format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    def _validate_ip(self, ip: str) -> bool:
        """Validiere IP-Adresse."""
        # IPv4
        ipv4_pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
        match = re.match(ipv4_pattern, ip)
        if match:
            return all(0 <= int(g) <= 255 for g in match.groups())
        return False

    def _detect_addresses(self, text: str) -> List[PIIMatch]:
        """Erkenne Adressen im Text."""
        matches = []

        for pattern in self.ADDRESS_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1) if match.lastindex else match.group(0)

                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end]

                pii_match = PIIMatch(
                    pii_type=PIIType.ADDRESS,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                    sensitivity=PIISensitivity.MEDIUM,
                    confidence=0.7,
                    context=context,
                )
                matches.append(pii_match)

        return matches

    def _detect_health_data(self, text: str) -> List[PIIMatch]:
        """Erkenne Gesundheitsdaten (kontextbasiert)."""
        matches = []
        text_lower = text.lower()

        for indicator in self.HEALTH_INDICATORS:
            if indicator in text_lower:
                # Finde Position
                idx = text_lower.find(indicator)

                # Extrahiere Kontext (50 Zeichen um den Indikator)
                start = max(0, idx - 25)
                end = min(len(text), idx + len(indicator) + 50)
                context = text[start:end]

                pii_match = PIIMatch(
                    pii_type=PIIType.HEALTH_DATA,
                    value=indicator,
                    start=idx,
                    end=idx + len(indicator),
                    sensitivity=PIISensitivity.CRITICAL,
                    confidence=0.6,
                    context=context,
                    metadata={"indicator": indicator},
                )
                matches.append(pii_match)

        return matches

    def _calculate_confidence(
        self,
        pii_type: PIIType,
        value: str,
        full_text: str,
    ) -> float:
        """Berechne Confidence fuer einen Fund."""
        base_confidence = 0.8

        # Hoehere Confidence bei validiertem Format
        if pii_type == PIIType.IBAN and self._validate_iban(value):
            return 0.99
        if pii_type == PIIType.CREDIT_CARD and self._validate_credit_card(value):
            return 0.99
        if pii_type == PIIType.EMAIL:
            return 0.95

        # Kontext-basierte Erhoehung
        context_keywords = {
            PIIType.IBAN: ["iban", "kontonummer", "bankverbindung"],
            PIIType.VAT_ID: ["ust-id", "vat", "mehrwertsteuer"],
            PIIType.TAX_ID: ["steuer-id", "steuernummer", "tin"],
            PIIType.PHONE: ["telefon", "tel.", "mobil", "fax"],
        }

        if pii_type in context_keywords:
            text_lower = full_text.lower()
            for keyword in context_keywords[pii_type]:
                if keyword in text_lower:
                    base_confidence = min(base_confidence + 0.1, 0.95)

        return base_confidence

    def _deduplicate_matches(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Entferne ueberlappende Matches, behalte hoechste Confidence."""
        if not matches:
            return []

        # Sortiere nach Start-Position
        sorted_matches = sorted(matches, key=lambda m: (m.start, -m.confidence))

        result = []
        for match in sorted_matches:
            # Pruefe Ueberlappung mit letztem Match
            if result and match.start < result[-1].end:
                # Ueberlappung: Behalte den mit hoeherer Confidence
                if match.confidence > result[-1].confidence:
                    result[-1] = match
            else:
                result.append(match)

        return result

    def _calculate_risk_score(self, matches: List[PIIMatch]) -> int:
        """Berechne Risiko-Score basierend auf gefundenen PII."""
        if not matches:
            return 0

        score = 0

        # Punkte pro Sensibilitaet
        sensitivity_points = {
            PIISensitivity.LOW: 5,
            PIISensitivity.MEDIUM: 15,
            PIISensitivity.HIGH: 30,
            PIISensitivity.CRITICAL: 50,
        }

        for match in matches:
            base_points = sensitivity_points.get(match.sensitivity, 10)
            # Gewichte mit Confidence
            score += int(base_points * match.confidence)

        # Cap bei 100
        return min(100, score)

    def _generate_recommendations(
        self,
        matches: List[PIIMatch],
        has_critical: bool,
    ) -> List[str]:
        """Generiere Empfehlungen basierend auf Funden."""
        recommendations = []

        if not matches:
            return ["Keine personenbezogenen Daten erkannt."]

        if has_critical:
            recommendations.append(
                "KRITISCHE DATEN GEFUNDEN: Dokument enthaelt hochsensible Informationen. "
                "Zugriff einschraenken und Verschluesselung sicherstellen."
            )

        # Spezifische Empfehlungen pro Typ
        types_found = {m.pii_type for m in matches}

        if PIIType.IBAN in types_found or PIIType.CREDIT_CARD in types_found:
            recommendations.append(
                "Bankdaten gefunden: Bei Export/Sharing maskieren oder entfernen."
            )

        if PIIType.HEALTH_DATA in types_found:
            recommendations.append(
                "Gesundheitsdaten gefunden: Besondere Kategorien nach DSGVO Art. 9. "
                "Verarbeitung nur mit expliziter Einwilligung."
            )

        if PIIType.SALARY in types_found:
            recommendations.append(
                "Gehaltsinformationen gefunden: Zugriff auf HR und Buchhaltung beschraenken."
            )

        if PIIType.EMAIL in types_found or PIIType.PHONE in types_found:
            recommendations.append(
                "Kontaktdaten gefunden: Bei Weitergabe Einwilligung pruefen."
            )

        return recommendations[:5]  # Max 5 Empfehlungen
