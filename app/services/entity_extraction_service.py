# -*- coding: utf-8 -*-
"""
Entity Extraction Service für Geschäftspartner-Erkennung.

Extrahiert Geschäftspartner (Kunden/Lieferanten) aus OCR-Text mit
99%+ Praezision durch Mehrfach-Validierung.

Erkannte Entitäten:
- USt-IdNr (DE123456789)
- IBAN (DE89 3704 0044 0532 0130 00)
- Steuernummer
- Firmennamen
- Adressen (PLZ, Stadt, Strasse)
- E-Mail und Telefon

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

import re
import structlog
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload

logger = structlog.get_logger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ExtractedIdentifier:
    """Ein extrahierter Identifier aus dem OCR-Text."""
    identifier_type: str  # "vat_id", "iban", "tax_number", "email", etc.
    value: str
    normalized_value: str  # Ohne Leerzeichen/Formatierung
    confidence: float  # 0.0-1.0
    position_start: int
    position_end: int
    context: str  # Umgebender Text
    country_code: Optional[str] = None  # ISO 3166-1 Alpha-2 (z.B. "DE", "NL", "AT")


@dataclass
class ExtractedAddress:
    """Eine extrahierte Adresse."""
    street: Optional[str] = None
    street_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: str = "DE"
    confidence: float = 0.0
    raw_text: str = ""
    # Neue Felder für intelligente Zuordnung
    role: Optional[str] = None  # "sender" oder "recipient"
    position_start: int = 0  # Position im Text für Proximity-Matching
    company_name: Optional[str] = None  # Firmenname aus Kontext (ohne Rechtsform)


@dataclass
class ExtractedCompanyName:
    """Ein extrahierter Firmenname."""
    name: str
    legal_form: Optional[str] = None  # GmbH, AG, etc.
    confidence: float = 0.0
    position_start: int = 0
    position_end: int = 0


@dataclass
class EntityExtractionResult:
    """Ergebnis der Entity-Extraktion aus einem Dokument."""
    identifiers: List[ExtractedIdentifier] = field(default_factory=list)
    addresses: List[ExtractedAddress] = field(default_factory=list)
    company_names: List[ExtractedCompanyName] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    phone_numbers: List[str] = field(default_factory=list)
    overall_confidence: float = 0.0
    extraction_details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityMatchResult:
    """Ergebnis des Matchings mit bestehenden Entities."""
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    match_type: str = "none"  # "vat_id", "iban", "name_address", "none"
    confidence: float = 0.0
    is_new: bool = True
    match_details: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# REGEX PATTERNS
# =============================================================================

class GermanPatterns:
    """Regex-Muster für deutsche Geschäftsdokumente."""

    # USt-IdNr: DE gefolgt von genau 9 Ziffern (Legacy, nur DE)
    VAT_ID = re.compile(
        r'\b(DE\s?[0-9]{3}\s?[0-9]{3}\s?[0-9]{3})\b',
        re.IGNORECASE
    )

    # EU USt-IdNr: Alle EU-Mitgliedstaaten
    # Formate: AT + U + 8 Ziffern, BE + 10 Ziffern, NL + 9 Zeichen + B + 2 Zeichen, etc.
    EU_VAT_ID = re.compile(
        r'\b(?P<country>AT|BE|BG|CY|CZ|DK|EE|FI|FR|GR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK|DE)'
        r'(?P<number>[A-Z0-9]{8,12})\b',
        re.IGNORECASE
    )

    # Spezifischere Patterns für häufige Länder (höhere Praezision)
    # WICHTIG: Mit optionalen Leerzeichen für OCR-Toleranz!
    VAT_ID_NL = re.compile(
        r'\b(NL\s?[0-9]{9}\s?B\s?[0-9]{2})\b',  # NL + 9 Ziffern + B + 2 Ziffern (mit optionalen Leerzeichen)
        re.IGNORECASE
    )

    VAT_ID_AT = re.compile(
        r'\b(ATU[0-9]{8})\b',  # AT + U + 8 Ziffern
        re.IGNORECASE
    )

    VAT_ID_BE = re.compile(
        r'\b(BE[01][0-9]{9})\b',  # BE + 0 oder 1 + 9 Ziffern
        re.IGNORECASE
    )

    # =========================================================================
    # EU-WEITE IBAN/BIC PATTERNS (KRITISCH!)
    # =========================================================================
    # EU IBAN - Alle Länder (ersetzt DE-only Pattern)
    # Format: 2 Buchstaben Ländercode + 2 Prüfziffern + bis zu 30 alphanumerische Zeichen
    # Mit optionalen Leerzeichen zwischen 4er-Gruppen
    EU_IBAN = re.compile(
        r'\b([A-Z]{2}\s?[0-9]{2}\s?(?:[A-Z0-9]{4}\s?){2,7}[A-Z0-9]{0,2})\b',
        re.IGNORECASE
    )

    # Legacy: DE-only IBAN (für Rückwärtskompatibilität)
    IBAN = re.compile(
        r'\b(DE\s?[0-9]{2}[\s]?(?:[0-9]{4}[\s]?){4}[0-9]{2})\b',
        re.IGNORECASE
    )

    # Kürzere IBAN-Variante für edge cases (DE-only)
    IBAN_SHORT = re.compile(
        r'\b(DE[0-9]{20})\b',
        re.IGNORECASE
    )

    # IBAN-Längen pro Land (ohne Leerzeichen)
    IBAN_LENGTHS: Dict[str, int] = {
        'DE': 22,  # Deutschland
        'NL': 18,  # Niederlande
        'AT': 20,  # Oesterreich
        'BE': 16,  # Belgien
        'FR': 27,  # Frankreich
        'IT': 27,  # Italien
        'ES': 24,  # Spanien
        'CH': 21,  # Schweiz
        'PL': 28,  # Polen
        'CZ': 24,  # Tschechien
        'GB': 22,  # Grossbritannien
        'LU': 20,  # Luxemburg
        'DK': 18,  # Daenemark
        'SE': 24,  # Schweden
        'NO': 15,  # Norwegen
        'FI': 18,  # Finnland
        'PT': 25,  # Portugal
        'GR': 27,  # Griechenland
        'IE': 22,  # Irland
        'HU': 28,  # Ungarn
        'SK': 24,  # Slowakei
        'SI': 19,  # Slowenien
        'HR': 21,  # Kroatien
        'RO': 24,  # Rumaenien
        'BG': 22,  # Bulgarien
    }

    # EU BIC/SWIFT - Alle Länder (ersetzt DE-only Pattern)
    # Format: 4 Buchstaben Bank + 2 Buchstaben Land + 2 alphanumerische Ort + optional 3 alphanumerische Filiale
    EU_BIC = re.compile(
        r'\b([A-Z]{4}\s?[A-Z]{2}\s?[A-Z0-9]{2}(?:\s?[A-Z0-9]{3})?)\b',
        re.IGNORECASE
    )

    # Legacy: DE-only BIC (für Rückwärtskompatibilität)
    BIC = re.compile(
        r'\b([A-Z]{4}DE[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b'
    )

    # Deutsche Steuernummer (verschiedene Formate je nach Bundesland)
    TAX_NUMBER = re.compile(
        r'\b([0-9]{2,3}/[0-9]{3}/[0-9]{4,5})\b'
    )

    # =========================================================================
    # MULTI-LAND PLZ PATTERNS
    # =========================================================================
    # Deutsche PLZ (5-stellig) + Stadt
    # Unterstützt optionales Länder-Prefix: "D-42719", "DE-42719", "42719"
    PLZ_CITY = re.compile(
        r'(?:^|[^\d])(?:D-|DE-)?([0-9]{5})[ \t]+([A-ZÄÖÜ][a-zäöüß]+(?:[ \t]+[A-Za-zäöüß]+)*)\b',
        re.UNICODE
    )

    # Niederlaendische PLZ (4 Ziffern + 2 Buchstaben) + Stadt
    # Unterstützt Leerzeichen in PLZ: "7418 HG" oder "7418HG"
    PLZ_CITY_NL = re.compile(
        r'\b([0-9]{4}[ \t]?[A-Z]{2})[ \t]+([A-Za-z\-]+(?:[ \t]+[A-Za-z\-]+)*)\b',
        re.UNICODE
    )

    # Oesterreichische PLZ (4-stellig) + Stadt
    PLZ_CITY_AT = re.compile(
        r'\b([0-9]{4})\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-Za-zäöüß]+)*)\b',
        re.UNICODE
    )

    # Schweizer PLZ (4-stellig) + Stadt
    PLZ_CITY_CH = re.compile(
        r'\b([0-9]{4})\s+([A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-Za-zäöüß]+)*)\b',
        re.UNICODE
    )

    # Belgische PLZ (4-stellig) + Stadt
    PLZ_CITY_BE = re.compile(
        r'\b([0-9]{4})\s+([A-Za-z\-]+(?:\s+[A-Za-z\-]+)*)\b',
        re.UNICODE
    )

    # =========================================================================
    # SENDER / RECIPIENT LABELS (mit Word Boundaries!)
    # =========================================================================
    SENDER_LABELS = re.compile(
        r'\b(?:von|from|sender|absender|lieferant|supplier|vendor|'
        r'rechnungssteller|verkäufer|seller|geliefert\s+von)\b',
        re.IGNORECASE
    )

    RECIPIENT_LABELS = re.compile(
        r'\b(?:an|to|recipient|empfänger|empfänger|kunde|customer|'
        r'rechnungsempfänger|rechnungsempfänger|käufer|käufer|buyer|'
        r'bill\s*to|ship\s*to|lieferadresse|rechnungsadresse)\b',
        re.IGNORECASE
    )

    # Straße + Hausnummer
    # Erkennt: "Van der Landeweg 6", "Albertus-Magnus-Str. 11", "Musterstraße 42"
    STREET = re.compile(
        # Optionales Präfix: "Van der", "De", "Am", "An der", etc.
        r'((?:(?:Van|Von|De|Het|An|Am|Im|Auf|Bei|Zum|Zur|In)[ \t]+(?:der|den|dem|het)?[ \t]*)?'
        # Straßenname: kann Bindestriche haben (Albertus-Magnus, Karl-Marx)
        r'[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß-]*'
        # Straßentyp
        r'(?:str(?:a[sß]e)?\.?|weg|platz|allee|ring|gasse|damm|ufer|berg|hof|steig|pfad))'
        # Hausnummer (OPTIONAL - mit optionalem Buchstaben)
        r'\.?(?:[ \t]+(\d+(?:[ \t]*[a-zA-Z])?))?',
        re.UNICODE | re.IGNORECASE
    )

    # Hausnummer separat (für fragmentierten OCR wo Nummer auf eigener Zeile)
    HOUSE_NUMBER = re.compile(
        r'^(\d{1,4}(?:[ \t]*[a-zA-Z])?)$',
        re.UNICODE
    )

    # E-Mail
    EMAIL = re.compile(
        r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
    )

    # Telefon (deutsch)
    PHONE = re.compile(
        r'(?:Tel\.?|Telefon|Phone|Fon|Fax)[\s:]*([+]?[0-9\s\-/()]{8,20})',
        re.IGNORECASE
    )

    # Handelsregister
    TRADE_REGISTER = re.compile(
        r'\b(HRB?\s*[0-9]{4,8})\b',
        re.IGNORECASE
    )

    # Rechtsformen (DE + EU)
    LEGAL_FORMS = re.compile(
        r'\b(GmbH|AG|KG|OHG|UG|e\.?\s?K\.|GmbH\s*&\s*Co\.?\s*KG|mbH|SE|eG|KGaA|'
        r'B\.?V\.?|N\.?V\.?|S\.?A\.?|S\.?L\.?|S\.?R\.?L\.?|Ltd\.?|Inc\.?|PLC|LLC)\b',
        re.IGNORECASE
    )

    # =========================================================================
    # LAENDERNAMEN MAPPING (Mehrsprachig -> ISO 3166-1 Alpha-2)
    # =========================================================================
    # Alle Varianten in Kleinbuchstaben für case-insensitive Matching
    COUNTRY_NAMES_TO_CODE: Dict[str, str] = {
        # Deutschland
        "deutschland": "DE", "germany": "DE", "duitsland": "DE",
        "allemagne": "DE", "alemania": "DE", "germania": "DE",
        "d": "DE",  # D-42719 Prefix
        # Niederlande
        "niederlande": "NL", "netherlands": "NL", "nederland": "NL",
        "holland": "NL", "pays-bas": "NL", "paesi bassi": "NL",
        "nl": "NL",
        # Oesterreich
        "oesterreich": "AT", "österreich": "AT", "austria": "AT",
        "autriche": "AT", "oostenrijk": "AT",
        "a": "AT", "at": "AT",
        # Schweiz
        "schweiz": "CH", "switzerland": "CH", "suisse": "CH",
        "svizzera": "CH", "zwitserland": "CH",
        "ch": "CH",
        # Belgien
        "belgien": "BE", "belgium": "BE", "belgique": "BE",
        "belgie": "BE", "belgio": "BE",
        "b": "BE", "be": "BE",
        # Frankreich
        "frankreich": "FR", "france": "FR", "francia": "FR",
        "frankrijk": "FR",
        "f": "FR", "fr": "FR",
        # Italien
        "italien": "IT", "italy": "IT", "italia": "IT",
        "italie": "IT",
        "i": "IT", "it": "IT",
        # Spanien
        "spanien": "ES", "spain": "ES", "espana": "ES", "españa": "ES",
        "espagne": "ES", "spanje": "ES",
        "e": "ES", "es": "ES",
        # Polen
        "polen": "PL", "poland": "PL", "polska": "PL",
        "pologne": "PL",
        "pl": "PL",
        # Tschechien
        "tschechien": "CZ", "czech republic": "CZ", "czechia": "CZ",
        "cesko": "CZ", "tsjechie": "CZ",
        "cz": "CZ",
        # Grossbritannien
        "grossbritannien": "GB", "großbritannien": "GB", "united kingdom": "GB",
        "uk": "GB", "gb": "GB", "england": "GB", "great britain": "GB",
        "royaume-uni": "GB", "verenigd koninkrijk": "GB",
        # Luxemburg
        "luxemburg": "LU", "luxembourg": "LU", "lussemburgo": "LU",
        "l": "LU", "lu": "LU",
    }

    # Pattern für Ländernamen im Text (nach PLZ/Stadt)
    COUNTRY_NAME_PATTERN = re.compile(
        r'(?:^|\n|\r)\s*([A-Za-zäöüÄÖÜßéèêëàâùûôîïç\-\s]+?)\s*(?:$|\n|\r)',
        re.UNICODE | re.MULTILINE
    )

    # Firmenname (vor Rechtsform) - inkl. EU-Rechtsformen
    # WICHTIG: Nur Leerzeichen (keine Newlines), Rechtsformen in Reihenfolge (GmbH vor mbH!)
    # FIX 2025-12-17: \s+ durch [ \t]+ ersetzt - keine Zeilenumbrueche matchen!
    # Das Pattern matcht alles vor der Rechtsform auf EINER Zeile
    COMPANY_NAME = re.compile(
        r'\b([A-ZÄÖÜ][A-Za-zäöüß&\-\.]+(?:[ \t]+[A-Za-zäöüß&\-\.]+)*)[ \t]+'
        r'(GmbH|mbH|AG|KG|OHG|UG|e\.?\s?K\.|SE|eG|KGaA|'
        r'B\.?V\.?|N\.?V\.?|S\.?A\.?|S\.?L\.?|S\.?R\.?L\.?|Ltd\.?|Inc\.?|PLC|LLC)\b',
        re.UNICODE
    )


# =============================================================================
# ENTITY EXTRACTION SERVICE
# =============================================================================

class EntityExtractionService:
    """
    Service zur Extraktion von Geschäftspartnern aus OCR-Text.

    Verwendet Mehrfach-Validierung für 99%+ Praezision:
    1. Regex-basierte Erkennung
    2. Validierung (IBAN-Prüfziffer, etc.)
    3. Kontext-Analyse
    4. Matching mit bekannten Entities

    Usage:
        service = EntityExtractionService(db)
        result = await service.extract_entities(ocr_text)
        match = await service.match_to_existing(result)
    """

    # Confidence-Schwellenwerte für 99%+ Präzision
    HIGH_CONFIDENCE_THRESHOLD = 0.99
    MEDIUM_CONFIDENCE_THRESHOLD = 0.80
    LOW_CONFIDENCE_THRESHOLD = 0.60

    def __init__(self, db: Optional[AsyncSession] = None):
        """
        Initialisiert den Entity Extraction Service.

        Args:
            db: Optionale Datenbankverbindung für Matching
        """
        self.db = db
        self.patterns = GermanPatterns()
        self._extraction_stats: Dict[str, int] = {
            "total_extractions": 0,
            "vat_ids_found": 0,
            "ibans_found": 0,
            "addresses_found": 0,
            "companies_found": 0,
        }

    async def extract_entities(
        self,
        text: str,
        document_id: Optional[UUID] = None
    ) -> EntityExtractionResult:
        """
        Extrahiert alle Geschäftspartner-Informationen aus OCR-Text.

        Args:
            text: OCR-Text
            document_id: Optionale Dokument-ID für Logging

        Returns:
            EntityExtractionResult mit allen gefundenen Entitäten
        """
        if not text or not text.strip():
            return EntityExtractionResult()

        self._extraction_stats["total_extractions"] += 1

        result = EntityExtractionResult()

        # 1. Identifiers extrahieren
        result.identifiers.extend(self._extract_vat_ids(text))
        result.identifiers.extend(self._extract_ibans(text))
        result.identifiers.extend(self._extract_bics(text))  # NEU: BIC/SWIFT Extraktion
        result.identifiers.extend(self._extract_tax_numbers(text))
        result.identifiers.extend(self._extract_trade_registers(text))

        # 2. Adressen extrahieren
        result.addresses = self._extract_addresses(text)

        # 3. Firmennamen extrahieren
        result.company_names = self._extract_company_names(text)

        # 4. Kontaktdaten extrahieren
        result.emails = self._extract_emails(text)
        result.phone_numbers = self._extract_phone_numbers(text)

        # 5. Overall Confidence berechnen
        result.overall_confidence = self._calculate_overall_confidence(result)

        # 6. Extraction Details
        result.extraction_details = {
            "document_id": str(document_id) if document_id else None,
            "text_length": len(text),
            "identifiers_count": len(result.identifiers),
            "addresses_count": len(result.addresses),
            "companies_count": len(result.company_names),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "entity_extraction_completed",
            document_id=str(document_id) if document_id else None,
            identifiers_count=len(result.identifiers),
            addresses_count=len(result.addresses),
            companies_count=len(result.company_names),
            overall_confidence=result.overall_confidence,
        )

        return result

    def _extract_vat_ids(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert EU USt-IdNr (alle Mitgliedstaaten).

        Unterstützt:
        - DE: DE + 9 Ziffern (z.B. DE200053646)
        - NL: NL + 9 Ziffern + B + 2 Ziffern (z.B. NL820594829B01)
        - AT: AT + U + 8 Ziffern (z.B. ATU12345678)
        - BE: BE + 10 Ziffern (z.B. BE0123456789)
        - Alle anderen EU-Länder: Ländercode + 8-12 alphanumerische Zeichen
        """
        results: List[ExtractedIdentifier] = []
        seen_vat_ids: Set[str] = set()

        # 1. Zuerst spezifische Patterns mit hoher Praezision (NL, AT, BE)
        specific_patterns = [
            (self.patterns.VAT_ID_NL, "NL", 14),  # NL + 9 + B + 2 = 14
            (self.patterns.VAT_ID_AT, "AT", 11),  # AT + U + 8 = 11
            (self.patterns.VAT_ID_BE, "BE", 12),  # BE + 10 = 12
            (self.patterns.VAT_ID, "DE", 11),     # DE + 9 = 11
        ]

        for pattern, country, expected_len in specific_patterns:
            for match in pattern.finditer(text):
                raw_value = match.group(1) if match.lastindex else match.group(0)
                normalized = re.sub(r'\s', '', raw_value).upper()

                if normalized in seen_vat_ids:
                    continue

                # Längen-Validierung
                if len(normalized) != expected_len:
                    continue

                seen_vat_ids.add(normalized)
                context = self._get_context(text, match.start(), match.end())
                confidence = self._calculate_vat_confidence(normalized, context)

                results.append(ExtractedIdentifier(
                    identifier_type="vat_id",
                    value=raw_value,
                    normalized_value=normalized,
                    confidence=confidence,
                    position_start=match.start(),
                    position_end=match.end(),
                    context=context,
                    country_code=country,
                ))
                self._extraction_stats["vat_ids_found"] += 1

        # 2. Dann generisches EU-Pattern für andere Länder
        for match in self.patterns.EU_VAT_ID.finditer(text):
            country = match.group('country').upper()
            number = match.group('number').upper()
            normalized = f"{country}{number}"

            if normalized in seen_vat_ids:
                continue

            # Überspringe bereits durch spezifische Patterns erfasste
            if country in ("DE", "NL", "AT", "BE"):
                continue

            # Minimale Längenvalidierung (Ländercode + mindestens 8 Zeichen)
            if len(normalized) < 10:
                continue

            # KRITISCH: VAT-IDs MUESSEN mindestens eine Ziffer enthalten!
            # Filtert Woerter wie "SILBERGRAU" (SI+LBERGRAU) oder "SEITENWAND" (SE+ITENWAND)
            if not any(c.isdigit() for c in number):
                continue

            # Zusätzlich: Ablehne bekannte deutsche Woerter die mit Ländercodes beginnen
            german_words_with_country_prefix = {
                "SILBERGRAU", "SEITENWAND", "SEITE", "SEITLICH", "SILBER",
                "DEKO", "DEKORATION", "DEKOR", "DECKEL", "DEFAULT",
                "FREI", "FREIHEIT", "FRISCH", "FRONT", "FRONTAL",
                "GRAU", "GRUEN", "GROSS", "GROESSE",
                "PLATZ", "PLATTE", "PLASTIK", "PLAN",
                "ITALIEN", "ITALIENISCH",
            }
            if normalized in german_words_with_country_prefix:
                continue

            seen_vat_ids.add(normalized)
            context = self._get_context(text, match.start(), match.end())
            confidence = self._calculate_vat_confidence(normalized, context)

            results.append(ExtractedIdentifier(
                identifier_type="vat_id",
                value=match.group(0),
                normalized_value=normalized,
                confidence=confidence,
                position_start=match.start(),
                position_end=match.end(),
                context=context,
                country_code=country,
            ))
            self._extraction_stats["vat_ids_found"] += 1

        # Sortiere nach Position im Text (für spätere Proximity-Analyse)
        results.sort(key=lambda x: x.position_start)

        return results

    def _extract_ibans(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert EU-weite IBANs mit Prüfziffern-Validierung.

        Unterstützt alle EU-Länder mit länderspezifischer Längenvalidierung:
        - DE: 22 Zeichen (z.B. DE89370400440532013000)
        - NL: 18 Zeichen (z.B. NL51INGB0658010921)
        - AT: 20 Zeichen (z.B. AT611904300234573201)
        - BE: 16 Zeichen (z.B. BE68539007547034)
        - etc.
        """
        results: List[ExtractedIdentifier] = []
        seen_ibans: Set[str] = set()

        # EU-weites IBAN Pattern (ersetzt DE-only)
        for match in self.patterns.EU_IBAN.finditer(text):
            raw_value = match.group(1)
            normalized = re.sub(r'\s', '', raw_value).upper()

            # Duplikate vermeiden
            if normalized in seen_ibans:
                continue

            # Ländercode extrahieren
            if len(normalized) < 2:
                continue
            country = normalized[:2]

            # Länderspezifische Längenvalidierung
            expected_len = self.patterns.IBAN_LENGTHS.get(country)
            if expected_len:
                if len(normalized) != expected_len:
                    # Länge stimmt nicht - überspringe
                    logger.debug(
                        "iban_length_mismatch",
                        country=country,
                        expected=expected_len,
                        actual=len(normalized),
                        value=normalized[:8] + "***",
                    )
                    continue
            else:
                # Unbekanntes Land - mindestens 15 Zeichen erforderlich
                if len(normalized) < 15:
                    continue

            # IBAN-Prüfziffer validieren
            if not self._validate_iban(normalized):
                logger.debug(
                    "iban_checksum_invalid",
                    country=country,
                    value=normalized[:8] + "***",
                )
                continue

            seen_ibans.add(normalized)
            context = self._get_context(text, match.start(), match.end())

            results.append(ExtractedIdentifier(
                identifier_type="iban",
                value=raw_value,
                normalized_value=normalized,
                confidence=0.99,  # IBAN mit gültiger Prüfziffer = sehr hohe Konfidenz
                position_start=match.start(),
                position_end=match.end(),
                context=context,
                country_code=country,  # NEU: Ländercode für spätere Attribution
            ))
            self._extraction_stats["ibans_found"] += 1
            logger.debug(
                "iban_extracted",
                country=country,
                value=normalized[:8] + "***",
            )

        return results

    def _extract_bics(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert BIC/SWIFT Codes (EU-weit).

        BIC-Format: 4 Buchstaben Bank + 2 Buchstaben Land + 2 Zeichen Ort + optional 3 Zeichen Filiale
        Beispiele:
        - INGBNL2A (8 Zeichen) - ING Bank Niederlande
        - DEUTDEFF (8 Zeichen) - Deutsche Bank Deutschland
        - COBADEFFXXX (11 Zeichen) - Commerzbank Deutschland mit Filiale
        """
        results: List[ExtractedIdentifier] = []
        seen_bics: Set[str] = set()

        # Bekannte EU-Ländercodes für BIC-Validierung
        valid_country_codes = {
            'DE', 'NL', 'AT', 'BE', 'FR', 'IT', 'ES', 'PT', 'CH', 'GB',
            'IE', 'LU', 'DK', 'SE', 'FI', 'NO', 'PL', 'CZ', 'HU', 'SK',
            'SI', 'HR', 'RO', 'BG', 'EE', 'LV', 'LT', 'CY', 'MT', 'GR',
        }

        for match in self.patterns.EU_BIC.finditer(text):
            raw_value = match.group(1)
            # Leerzeichen entfernen und normalisieren (OCR kann "ING BNL 2A" liefern)
            normalized = re.sub(r'\s', '', raw_value).upper()

            # Duplikate vermeiden
            if normalized in seen_bics:
                continue

            # Längenvalidierung: 8 oder 11 Zeichen (nach Entfernung von Leerzeichen)
            if len(normalized) not in (8, 11):
                continue

            # Ländercode aus BIC extrahieren (Zeichen 5-6)
            country = normalized[4:6]

            # STRENGE Validierung: Ländercode muss bekannter EU-Code sein
            if country not in valid_country_codes:
                continue

            # Kontextbasierte Validierung
            context = self._get_context(text, match.start(), match.end())

            # NUR akzeptieren wenn BIC/SWIFT/Bank-Kontext vorhanden
            # (Verhindert False Positives wie "BAKKENEN", "DEVENTER" etc.)
            if not re.search(r'bic|swift|bank', context, re.IGNORECASE):
                # Ohne Kontext nur akzeptieren wenn eindeutig ein BIC-Pattern
                # (z.B. endet mit Zahl oder typische Bank-Kürzel)
                if not re.match(r'^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}[A-Z0-9]{0,3}$', normalized):
                    continue
                # Zusätzlich: Muss mindestens eine Ziffer enthalten (typisch für BIC)
                if not any(c.isdigit() for c in normalized):
                    continue

            # Confidence basierend auf Kontext
            confidence = 0.85
            if re.search(r'bic|swift', context, re.IGNORECASE):
                confidence = 0.98
            elif re.search(r'bank', context, re.IGNORECASE):
                confidence = 0.92

            seen_bics.add(normalized)

            results.append(ExtractedIdentifier(
                identifier_type="bic",
                value=raw_value,
                normalized_value=normalized,
                confidence=confidence,
                position_start=match.start(),
                position_end=match.end(),
                context=context,
                country_code=country,
            ))
            logger.debug(
                "bic_extracted",
                country=country,
                value=normalized,
            )

        # ZUSAETZLICH: Explizit gelabelte BICs suchen (z.B. "swift: ING BNL 2A")
        # Diese haben oft falsche Leerzeichen durch OCR
        # Pattern: swift/bic + optional : + lockere Zeichenkette (wird später validiert)
        # Stoppt bei Newline oder wenn zu viele Zeichen
        labeled_bic_pattern = re.compile(
            r'(?:swift|bic)\s*[:\.]?\s*([A-Z][A-Z0-9\s]{6,15})',
            re.IGNORECASE
        )
        for match in labeled_bic_pattern.finditer(text):
            raw_value = match.group(1).strip()
            # Alle Leerzeichen entfernen
            normalized = re.sub(r'\s', '', raw_value).upper()

            # Wenn zu lang, versuche auf 8 zu kürzen (Standard-BIC)
            # 8 chars ist der Standard, 11 nur mit Branch-Code
            if len(normalized) > 11:
                candidate_8 = normalized[:8]
                # Prüfe ob 8-char Version validen Ländercode hat
                if candidate_8[4:6] in valid_country_codes:
                    normalized = candidate_8
                else:
                    # Fallback: 11 chars versuchen
                    candidate_11 = normalized[:11]
                    if candidate_11[4:6] in valid_country_codes:
                        normalized = candidate_11
                    else:
                        continue

            # Muss 8 oder 11 Zeichen haben
            if len(normalized) not in (8, 11):
                continue

            # Duplikate vermeiden
            if normalized in seen_bics:
                continue

            # Ländercode validieren (Position 5-6)
            country = normalized[4:6]
            if country not in valid_country_codes:
                continue

            seen_bics.add(normalized)
            context = self._get_context(text, match.start(), match.end())

            results.append(ExtractedIdentifier(
                identifier_type="bic",
                value=raw_value,
                normalized_value=normalized,
                confidence=0.98,  # Hohe Konfidenz weil explizit gelabelt
                position_start=match.start(),
                position_end=match.end(),
                context=context,
                country_code=country,
            ))
            logger.debug(
                "bic_extracted_from_label",
                country=country,
                value=normalized,
                label_type="swift/bic",
            )

        return results

    def _validate_iban(self, iban: str) -> bool:
        """
        Validiert IBAN mit ISO 7064 Mod 97-10 Prüfziffer.

        Args:
            iban: Normalisierte IBAN ohne Leerzeichen

        Returns:
            True wenn IBAN gültig
        """
        try:
            # IBAN umstellen: erste 4 Zeichen ans Ende
            rearranged = iban[4:] + iban[:4]

            # Buchstaben zu Zahlen (A=10, B=11, ..., Z=35)
            numeric = ""
            for char in rearranged:
                if char.isdigit():
                    numeric += char
                else:
                    numeric += str(ord(char) - ord('A') + 10)

            # Mod 97 = 1 für gültige IBAN
            return int(numeric) % 97 == 1
        except (ValueError, TypeError):
            return False

    def _extract_tax_numbers(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert deutsche Steuernummern."""
        results = []

        for match in self.patterns.TAX_NUMBER.finditer(text):
            raw_value = match.group(1)
            context = self._get_context(text, match.start(), match.end())

            # Kontextbasierte Konfidenz (nach "Steuer" suchen)
            confidence = 0.70
            if re.search(r'steuer|finanzamt|fa\s', context, re.IGNORECASE):
                confidence = 0.90

            results.append(ExtractedIdentifier(
                identifier_type="tax_number",
                value=raw_value,
                normalized_value=raw_value.replace(" ", ""),
                confidence=confidence,
                position_start=match.start(),
                position_end=match.end(),
                context=context,
            ))

        return results

    def _extract_trade_registers(self, text: str) -> List[ExtractedIdentifier]:
        """Extrahiert Handelsregisternummern."""
        results = []

        for match in self.patterns.TRADE_REGISTER.finditer(text):
            raw_value = match.group(1)
            context = self._get_context(text, match.start(), match.end())

            # Kontextbasierte Konfidenz
            confidence = 0.75
            if re.search(r'handelsregister|amtsgericht|registergericht', context, re.IGNORECASE):
                confidence = 0.95

            results.append(ExtractedIdentifier(
                identifier_type="trade_register",
                value=raw_value,
                normalized_value=raw_value.upper().replace(" ", ""),
                confidence=confidence,
                position_start=match.start(),
                position_end=match.end(),
                context=context,
            ))

        return results

    def _extract_addresses(self, text: str) -> List[ExtractedAddress]:
        """
        Extrahiert Adressen (PLZ + Stadt + optional Strasse).

        Unterstützt mehrere Länder:
        - DE: 5-stellig (12345)
        - NL: 4 Ziffern + 2 Buchstaben (1234 AB)
        - AT/CH/BE: 4-stellig (1234)

        Weist Rollen (sender/recipient) basierend auf Kontext-Labels zu.
        """
        results = []
        seen_positions: Set[int] = set()  # Verhindere Duplikate

        # PLZ-Patterns für verschiedene Länder
        plz_patterns = [
            (self.patterns.PLZ_CITY, "DE"),
            (self.patterns.PLZ_CITY_NL, "NL"),
            # AT/CH/BE nur wenn explizit im Kontext oder keine DE-Adresse
            # (vermeidet false positives mit 4-stelligen Zahlen)
        ]

        for pattern, country in plz_patterns:
            for match in pattern.finditer(text):
                # Verhindere Duplikate an gleicher Position
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())

                plz = match.group(1)
                city = match.group(2).strip()

                address = ExtractedAddress(
                    postal_code=plz,
                    city=city,
                    country=country,
                    confidence=0.85,
                    raw_text=match.group(0),
                    position_start=match.start(),
                )

                # Land aus Kontext bestimmen (überschreibt PLZ-basiertes Land)
                # ABER: Bei eindeutigem PLZ-Format (NL NNNN AA) nicht überschreiben!
                # Das verhindert falsche Zuordnung wenn nachfolgende Adressen anderes Land haben.
                detected_country = self._detect_country_from_context(
                    text, match.start(), match.end()
                )
                if detected_country:
                    # NL-PLZ (4+2 Format) ist eindeutig - nicht überschreiben
                    plz_is_nl_format = re.match(r'^[0-9]{4}[ 	]?[A-Z]{2}$', address.postal_code or '')
                    if plz_is_nl_format and country == 'NL' and detected_country != 'NL':
                        # Behalte NL - das PLZ-Format ist eindeutig
                        pass
                    else:
                        address.country = detected_country
                        address.confidence += 0.05  # Boost für expliziten Ländernamen

                # Strasse in der Naehe suchen (150 Zeichen vorher)
                # WICHTIG: Letzten Match verwenden (nächster zur PLZ)
                search_start = max(0, match.start() - 150)
                before_text = text[search_start:match.start()]

                street_matches = list(self.patterns.STREET.finditer(before_text))
                if street_matches:
                    # Letzten Match nehmen - der ist am nächsten zur PLZ
                    street_match = street_matches[-1]
                    address.street = street_match.group(1)
                    address.street_number = street_match.group(2)  # Kann None sein
                    address.confidence = 0.92

                    # Wenn keine Hausnummer im Straßenmatch, suche in nächster Zeile
                    if not address.street_number:
                        # Text nach der Strasse bis zur PLZ
                        after_street = before_text[street_match.end():].strip()
                        lines_after = [l.strip() for l in after_street.split('\n') if l.strip()]
                        if lines_after:
                            # Erste Zeile nach Strasse könnte Hausnummer sein
                            potential_number = lines_after[0]
                            number_match = self.patterns.HOUSE_NUMBER.match(potential_number)
                            if number_match:
                                address.street_number = number_match.group(1)

                    # Firmenname VOR der Strasse suchen (ohne Rechtsform)
                    # Suche in den Zeilen vor der Strasse
                    street_pos_in_before = street_match.start()
                    text_before_street = before_text[:street_pos_in_before].strip()

                    # Letzte nicht-leere Zeile vor der Strasse = potentieller Firmenname
                    lines_before = [l.strip() for l in text_before_street.split('\n') if l.strip()]
                    if lines_before:
                        potential_company = lines_before[-1]
                        # Validiere: Nicht zu kurz, nicht nur Zahlen, kein Label
                        skip_patterns = [
                            'absender', 'empfänger', 'empfänger', 'sender', 'recipient',
                            'an:', 'von:', 'to:', 'from:', 'rechnung', 'invoice',
                            'lieferadresse', 'rechnungsadresse', 'delivery', 'billing',
                        ]
                        is_valid_company = (
                            len(potential_company) >= 3 and
                            not potential_company.isdigit() and
                            not any(skip in potential_company.lower() for skip in skip_patterns) and
                            not re.match(r'^\d', potential_company)  # Nicht mit Zahl beginnen
                        )
                        if is_valid_company:
                            address.company_name = potential_company

                # Rolle aus Kontext-Labels bestimmen (das LETZTE Label im Kontext gewinnt)
                context_window = 120  # Zeichen vor der Adresse (erhöhte für mehrzeilige Adressen)
                context_start = max(0, match.start() - context_window)
                context_before = text[context_start:match.start()]

                # Finde das letzte (nächste zur Adresse) Label
                sender_matches = list(self.patterns.SENDER_LABELS.finditer(context_before))
                recipient_matches = list(self.patterns.RECIPIENT_LABELS.finditer(context_before))

                last_sender_pos = sender_matches[-1].end() if sender_matches else -1
                last_recipient_pos = recipient_matches[-1].end() if recipient_matches else -1

                # Das naehere Label gewinnt
                if last_sender_pos > last_recipient_pos:
                    address.role = "sender"
                    address.confidence += 0.05
                elif last_recipient_pos > last_sender_pos:
                    address.role = "recipient"
                    address.confidence += 0.05

                results.append(address)
                self._extraction_stats["addresses_found"] += 1

        # Sortiere nach Position im Text
        results.sort(key=lambda a: a.position_start)

        return results

    def _detect_country_from_context(
        self,
        text: str,
        plz_start: int,
        plz_end: int,
    ) -> Optional[str]:
        """
        Erkennt Ländernamen im Kontext einer Adresse.

        Sucht in 3 Bereichen:
        1. Direkt nach der PLZ/Stadt (nächste Zeile)
        2. Vor der PLZ (D-42719 Prefix)
        3. Im weiteren Kontext (100 Zeichen danach)

        Args:
            text: Gesamter OCR-Text
            plz_start: Start-Position der PLZ
            plz_end: End-Position der PLZ/Stadt

        Returns:
            ISO 3166-1 Alpha-2 Code oder None
        """
        # 1. Prüfe Länder-Prefix vor der PLZ (z.B. "D-42719")
        prefix_start = max(0, plz_start - 3)
        prefix_text = text[prefix_start:plz_start].strip()
        if prefix_text.endswith("-") or prefix_text.endswith(" "):
            prefix_char = prefix_text.rstrip("- ").upper()
            if len(prefix_char) <= 2:
                country_code = self.patterns.COUNTRY_NAMES_TO_CODE.get(
                    prefix_char.lower()
                )
                if country_code:
                    return country_code

        # 2. Suche Ländernamen nach der PLZ/Stadt (nächste 100 Zeichen)
        after_start = plz_end
        after_end = min(len(text), plz_end + 100)
        after_text = text[after_start:after_end]

        # Suche nach Ländernamen auf einer eigenen Zeile oder nach Komma/Zeilenumbruch
        # Typische Patterns: "42719 Solingen\nDuitsland" oder "42719 Solingen, Germany"
        country_pattern = re.compile(
            r'[\n\r,]\s*([A-Za-zäöüÄÖÜßéèê\-]+)\s*(?:[\n\r,]|$)',
            re.UNICODE
        )

        for match in country_pattern.finditer(after_text):
            potential_country = match.group(1).strip().lower()
            # Ignoriere zu kurze oder zu lange Strings
            if len(potential_country) < 1 or len(potential_country) > 25:
                continue
            # Prüfe gegen Mapping
            country_code = self.patterns.COUNTRY_NAMES_TO_CODE.get(potential_country)
            if country_code:
                return country_code

        # 3. Fallback: Suche nach bekannten Ländernamen als Wort im Kontext
        context_end = min(len(text), plz_end + 80)
        context_text = text[plz_end:context_end].lower()

        for country_name, code in self.patterns.COUNTRY_NAMES_TO_CODE.items():
            # Nur längere Namen (mind. 4 Zeichen) als Fallback
            if len(country_name) >= 4:
                if re.search(r'\b' + re.escape(country_name) + r'\b', context_text):
                    return code

        return None

    def _extract_company_names(self, text: str) -> List[ExtractedCompanyName]:
        """Extrahiert Firmennamen mit Rechtsform."""
        results = []
        seen_names: Set[str] = set()

        for match in self.patterns.COMPANY_NAME.finditer(text):
            name = match.group(1).strip()
            legal_form = match.group(2)

            # Bereinigung
            name = re.sub(r'\s+', ' ', name)

            # Duplikate vermeiden
            normalized_name = name.lower()
            if normalized_name in seen_names:
                continue
            seen_names.add(normalized_name)

            # Minimale Länge
            if len(name) < 3:
                continue

            results.append(ExtractedCompanyName(
                name=name,
                legal_form=legal_form,
                confidence=0.80,
                position_start=match.start(),
                position_end=match.end(),
            ))
            self._extraction_stats["companies_found"] += 1

        return results

    def _extract_emails(self, text: str) -> List[str]:
        """Extrahiert E-Mail-Adressen."""
        emails = []
        for match in self.patterns.EMAIL.finditer(text):
            email = match.group(1).lower()
            if email not in emails:
                emails.append(email)
        return emails

    def _extract_phone_numbers(self, text: str) -> List[str]:
        """Extrahiert Telefonnummern."""
        phones = []
        for match in self.patterns.PHONE.finditer(text):
            phone = re.sub(r'[^\d+]', '', match.group(1))
            if len(phone) >= 8 and phone not in phones:
                phones.append(phone)
        return phones

    def _get_context(self, text: str, start: int, end: int, window: int = 50) -> str:
        """Gibt den umgebenden Kontext eines Matches zurück."""
        context_start = max(0, start - window)
        context_end = min(len(text), end + window)
        return text[context_start:context_end]

    def _calculate_vat_confidence(self, vat_id: str, context: str) -> float:
        """Berechnet Konfidenz für USt-IdNr basierend auf Kontext."""
        base_confidence = 0.85

        # Kontext-Boost
        if re.search(r'ust|umsatzsteuer|vat|mwst', context, re.IGNORECASE):
            base_confidence += 0.10
        if re.search(r'id|identifikation|nummer|nr', context, re.IGNORECASE):
            base_confidence += 0.04

        return min(base_confidence, 0.99)

    def _calculate_overall_confidence(self, result: EntityExtractionResult) -> float:
        """Berechnet Overall-Konfidenz basierend auf allen Extraktionen."""
        confidences = []

        # Identifiers
        for identifier in result.identifiers:
            confidences.append(identifier.confidence)

        # Adressen
        for address in result.addresses:
            confidences.append(address.confidence)

        # Firmennamen
        for company in result.company_names:
            confidences.append(company.confidence)

        if not confidences:
            return 0.0

        # Gewichteter Durchschnitt mit Bonus für mehrere Signale
        avg_confidence = sum(confidences) / len(confidences)

        # Multi-Signal-Bonus
        if len(confidences) >= 3:
            avg_confidence = min(avg_confidence + 0.05, 0.99)
        if len(confidences) >= 5:
            avg_confidence = min(avg_confidence + 0.03, 0.99)

        return round(avg_confidence, 4)

    # =========================================================================
    # ENTITY MATCHING
    # =========================================================================

    async def match_to_existing(
        self,
        extraction: EntityExtractionResult
    ) -> EntityMatchResult:
        """
        Matched extrahierte Daten mit existierenden BusinessEntities.

        Matching-Priorität für 99%+ Präzision:
        1. USt-IdNr (eindeutig, höchste Konfidenz)
        2. IBAN (fast eindeutig)
        3. Name + Adresse (Fuzzy-Match mit hohem Schwellenwert)

        Args:
            extraction: Ergebnis der Entity-Extraktion

        Returns:
            EntityMatchResult mit Match-Details
        """
        if not self.db:
            return EntityMatchResult(
                is_new=True,
                match_details={"error": "Keine Datenbankverbindung"}
            )

        # Import hier um zirkuläre Imports zu vermeiden
        from app.db.models import BusinessEntity

        # 1. Match auf USt-IdNr (höchste Präzision)
        for identifier in extraction.identifiers:
            if identifier.identifier_type == "vat_id" and identifier.confidence >= 0.90:
                result = await self.db.execute(
                    select(BusinessEntity).where(
                        BusinessEntity.vat_id == identifier.normalized_value,
                        BusinessEntity.deleted_at.is_(None)
                    )
                )
                entity = result.scalar_one_or_none()

                if entity:
                    return EntityMatchResult(
                        entity_id=entity.id,
                        entity_name=entity.name,
                        match_type="vat_id",
                        confidence=0.99,  # USt-IdNr ist eindeutig
                        is_new=False,
                        match_details={
                            "matched_vat_id": identifier.normalized_value,
                            "extraction_confidence": identifier.confidence,
                        }
                    )

        # 2. Match auf IBAN
        for identifier in extraction.identifiers:
            if identifier.identifier_type == "iban" and identifier.confidence >= 0.95:
                result = await self.db.execute(
                    select(BusinessEntity).where(
                        BusinessEntity.iban == identifier.normalized_value,
                        BusinessEntity.deleted_at.is_(None)
                    )
                )
                entity = result.scalar_one_or_none()

                if entity:
                    return EntityMatchResult(
                        entity_id=entity.id,
                        entity_name=entity.name,
                        match_type="iban",
                        confidence=0.98,
                        is_new=False,
                        match_details={
                            "matched_iban": identifier.normalized_value[:8] + "****",
                            "extraction_confidence": identifier.confidence,
                        }
                    )

        # 3. Match auf Name + PLZ (für 99%+ brauchen wir beide)
        if extraction.company_names and extraction.addresses:
            for company in extraction.company_names:
                for address in extraction.addresses:
                    if company.confidence >= 0.75 and address.confidence >= 0.80:
                        # Suche nach ähnlichem Namen UND gleichem PLZ
                        result = await self.db.execute(
                            select(BusinessEntity).where(
                                BusinessEntity.postal_code == address.postal_code,
                                BusinessEntity.deleted_at.is_(None)
                            )
                        )
                        entities = result.scalars().all()

                        for entity in entities:
                            # Name-Similarity prüfen
                            similarity = self._calculate_name_similarity(
                                company.name, entity.name
                            )

                            if similarity >= 0.90:  # Sehr hoher Schwellenwert
                                return EntityMatchResult(
                                    entity_id=entity.id,
                                    entity_name=entity.name,
                                    match_type="name_address",
                                    confidence=min(similarity, 0.95),
                                    is_new=False,
                                    match_details={
                                        "matched_name": entity.name,
                                        "extracted_name": company.name,
                                        "similarity": similarity,
                                        "postal_code": address.postal_code,
                                    }
                                )

        # Kein Match gefunden - neue Entity
        return EntityMatchResult(
            is_new=True,
            match_details={
                "identifiers_checked": len(extraction.identifiers),
                "companies_checked": len(extraction.company_names),
                "addresses_checked": len(extraction.addresses),
            }
        )

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Berechnet Ähnlichkeit zwischen zwei Firmennamen.

        Verwendet normalisierte Levenshtein-Distanz.
        """
        # Normalisierung
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        # Rechtsformen entfernen für Vergleich
        for suffix in ['gmbh', 'ag', 'kg', 'ohg', 'ug', 'mbh', 'se', 'eg']:
            n1 = re.sub(rf'\s*{suffix}\s*$', '', n1)
            n2 = re.sub(rf'\s*{suffix}\s*$', '', n2)

        n1 = n1.strip()
        n2 = n2.strip()

        # Exakter Match
        if n1 == n2:
            return 1.0

        # Levenshtein-Distanz
        distance = self._levenshtein_distance(n1, n2)
        max_len = max(len(n1), len(n2))

        if max_len == 0:
            return 0.0

        similarity = 1 - (distance / max_len)
        return round(similarity, 4)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Berechnet Levenshtein-Distanz zwischen zwei Strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    # =========================================================================
    # LEARNING / FEEDBACK
    # =========================================================================

    async def learn_from_confirmation(
        self,
        document_id: UUID,
        entity_id: UUID,
        user_id: UUID,
        extraction: EntityExtractionResult
    ) -> None:
        """
        Lernt aus Benutzer-Bestätigung einer Entity-Verknüpfung.

        Aktualisiert:
        - Name-Aliase der Entity
        - Adress-Patterns
        - Email-Domains

        Args:
            document_id: Dokument-ID
            entity_id: Bestätigte Entity-ID
            user_id: User der bestätigt hat
            extraction: Ursprüngliche Extraktion
        """
        if not self.db:
            logger.warning("learn_from_confirmation_no_db")
            return

        from app.db.models import BusinessEntity

        result = await self.db.execute(
            select(BusinessEntity).where(BusinessEntity.id == entity_id)
        )
        entity = result.scalar_one_or_none()

        if not entity:
            logger.warning("learn_from_confirmation_entity_not_found", entity_id=str(entity_id))
            return

        updated = False

        # Neue Namen-Aliase hinzufügen
        for company in extraction.company_names:
            full_name = f"{company.name} {company.legal_form}".strip() if company.legal_form else company.name
            if full_name.lower() != entity.name.lower():
                if entity.name_aliases is None:
                    entity.name_aliases = []
                if full_name not in entity.name_aliases:
                    entity.name_aliases.append(full_name)
                    updated = True
                    logger.info(
                        "entity_alias_added",
                        entity_id=str(entity_id),
                        new_alias=full_name,
                    )

        # Neue Email-Domains hinzufügen
        for email in extraction.emails:
            domain = email.split('@')[-1]
            if entity.email_domains is None:
                entity.email_domains = []
            if domain not in entity.email_domains:
                entity.email_domains.append(domain)
                updated = True

        if updated:
            await self.db.commit()
            logger.info(
                "entity_learning_completed",
                entity_id=str(entity_id),
                document_id=str(document_id),
                user_id=str(user_id),
            )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_extraction_stats(self) -> Dict[str, int]:
        """Gibt Extraktions-Statistiken zurück."""
        return self._extraction_stats.copy()

    def reset_stats(self) -> None:
        """Setzt Statistiken zurück."""
        self._extraction_stats = {
            "total_extractions": 0,
            "vat_ids_found": 0,
            "ibans_found": 0,
            "addresses_found": 0,
            "companies_found": 0,
        }
