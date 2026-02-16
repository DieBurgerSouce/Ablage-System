# -*- coding: utf-8 -*-
"""
Confidentiality Classifier Service.

Klassifiziert Dokumente nach Vertraulichkeitsstufe basierend auf:
- Explizite Vertraulichkeits-Marker
- Dokumenttyp
- Inhalt (PII, Finanzdaten, etc.)
- Geschäftsgeheimnisse

Vertraulichkeitsstufen:
- PUBLIC: Öffentlich zugaengliche Informationen
- INTERNAL: Nur für interne Nutzung
- CONFIDENTIAL: Vertraulich, eingeschraenkter Zugriff
- STRICTLY_CONFIDENTIAL: Streng vertraulich, minimaler Zugriff

Feinpoliert und durchdacht.
"""

import re
import structlog
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Set

logger = structlog.get_logger(__name__)


class ConfidentialityLevel(str, Enum):
    """Vertraulichkeitsstufen für Dokumente."""
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    STRICTLY_CONFIDENTIAL = "strictly_confidential"


@dataclass
class ConfidentialityClassificationResult:
    """Ergebnis der Vertraulichkeitsklassifikation."""
    level: ConfidentialityLevel
    confidence: float
    matched_indicators: List[str]
    detected_pii_types: List[str]
    reason: str
    requires_encryption: bool
    access_restriction: str  # Wer darf zugreifen


# =============================================================================
# CLASSIFICATION RULES
# =============================================================================

# Explizite Marker für Vertraulichkeit
STRICTLY_CONFIDENTIAL_MARKERS: Set[str] = {
    "streng vertraulich", "strictly confidential", "top secret",
    "geheim", "nur für geschäftsführung", "nur für vorstand",
    "persoenlich/vertraulich", "nicht zur weitergabe",
    "highly confidential", "secret", "restricted",
}

CONFIDENTIAL_MARKERS: Set[str] = {
    "vertraulich", "confidential", "nicht öffentlich",
    "intern und vertraulich", "nur für internen gebrauch",
    "privilegiert", "sensibel", "protected", "private",
}

INTERNAL_MARKERS: Set[str] = {
    "intern", "internal", "nur intern", "internal use only",
    "firmenintern", "nicht zur veröffentlichung",
    "for internal use", "company confidential",
}

# Dokumenttypen mit Standard-Vertraulichkeit
STRICTLY_CONFIDENTIAL_TYPES: Set[str] = {
    "salary", "gehalt", "lohnabrechnung", "gehaltsabrechnung",
    "board_resolution", "gesellschafterbeschluss",
    "personnel_file", "personalakte",
    "strategy", "strategie",
}

CONFIDENTIAL_TYPES: Set[str] = {
    "employment_contract", "arbeitsvertrag",
    "performance_review", "leistungsbeurteilung",
    "financial_statement", "jahresabschluss", "bilanz",
    "tax_return", "steuererklärung",
    "contract", "vertrag",
    "offer", "angebot",  # Preiskalkulationen
}

INTERNAL_TYPES: Set[str] = {
    "invoice", "rechnung",
    "purchase_order", "bestellung",
    "budget", "forecast",
    "meeting_minutes", "protokoll",
    "project_plan", "projektplan",
}

# PII-Patterns für automatische Einstufung
PII_PATTERNS = {
    "iban": re.compile(r'[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}', re.IGNORECASE),
    "steuer_id": re.compile(r'steuer[\s\-]?(?:id|nummer|nr)[\s:]*\d{10,11}', re.IGNORECASE),
    "sozialversicherung": re.compile(r'sv[\s\-]?(?:nummer|nr)[\s:]*\d{12}', re.IGNORECASE),
    "gehalt": re.compile(r'(?:brutto|netto)[\s\-]?gehalt[\s:]*[\d.,]+\s*(?:€|EUR)?', re.IGNORECASE),
    "personalausweis": re.compile(r'personalausweis[\s\-]?(?:nr|nummer)?[\s:]*[A-Z0-9]{9,10}', re.IGNORECASE),
    "geburtsdatum": re.compile(r'geburtsdatum[\s:]*\d{1,2}\.\d{1,2}\.\d{4}', re.IGNORECASE),
    "krankenversicherung": re.compile(r'(?:kranken)?versicherungsnummer[\s:]*[A-Z]?\d{9,10}', re.IGNORECASE),
}

# Geschäftsgeheimnisse
TRADE_SECRET_KEYWORDS: Set[str] = {
    "patentanmeldung", "erfindung", "forschung", "entwicklung",
    "kundenliste", "preiskalkulation", "margenkalkulation",
    "lieferantenkonditionen", "einkaufspreise", "herstellkosten",
    "betriebsgeheimnis", "geschäftsgeheimnis",
    "prototyp", "rezeptur", "formel", "algorithmus",
    "know-how", "verfahren",
}


class ConfidentialityClassifier:
    """
    Klassifiziert Dokumente nach Vertraulichkeit.

    Performance: < 15ms pro Dokument (inkl. PII-Scan)
    """

    def __init__(self) -> None:
        """Initialisiere den Confidentiality Classifier."""
        self._stats = {
            "total_classifications": 0,
            "by_level": {level.value: 0 for level in ConfidentialityLevel},
            "pii_detections": 0,
        }

    def classify(
        self,
        text: str,
        document_type: Optional[str] = None,
    ) -> ConfidentialityClassificationResult:
        """
        Klassifiziere die Vertraulichkeit eines Dokuments.

        Args:
            text: OCR-Text des Dokuments
            document_type: Optionaler Dokumenttyp

        Returns:
            ConfidentialityClassificationResult mit Level und Details
        """
        if not text or not text.strip():
            return ConfidentialityClassificationResult(
                level=ConfidentialityLevel.INTERNAL,  # Default: intern
                confidence=0.5,
                matched_indicators=[],
                detected_pii_types=[],
                reason="Kein Text zur Analyse - Standardklassifikation 'intern'",
                requires_encryption=False,
                access_restriction="Alle Mitarbeiter",
            )

        self._stats["total_classifications"] += 1

        # Text normalisieren
        normalized_text = self._normalize_text(text)

        # 1. Explizite Marker suchen
        strict_markers = self._find_markers(normalized_text, STRICTLY_CONFIDENTIAL_MARKERS)
        conf_markers = self._find_markers(normalized_text, CONFIDENTIAL_MARKERS)
        internal_markers = self._find_markers(normalized_text, INTERNAL_MARKERS)

        # 2. PII scannen
        pii_types = self._scan_pii(text)  # Original-Text für bessere Erkennung
        if pii_types:
            self._stats["pii_detections"] += 1

        # 3. Trade Secrets prüfen
        trade_secrets = self._find_markers(normalized_text, TRADE_SECRET_KEYWORDS)

        # 4. Dokumenttyp berücksichtigen
        doc_type_level = self._get_doc_type_level(document_type)

        # 5. Level bestimmen
        level, confidence, reason = self._determine_level(
            strict_markers=strict_markers,
            conf_markers=conf_markers,
            internal_markers=internal_markers,
            pii_types=pii_types,
            trade_secrets=trade_secrets,
            doc_type_level=doc_type_level,
        )

        # Statistik aktualisieren
        self._stats["by_level"][level.value] += 1

        # Access Restriction bestimmen
        access_restriction = self._get_access_restriction(level)

        all_indicators = strict_markers + conf_markers + internal_markers + trade_secrets

        logger.debug(
            "confidentiality_classified",
            level=level.value,
            confidence=confidence,
            pii_types=pii_types,
            matched_indicators=all_indicators[:5],
        )

        return ConfidentialityClassificationResult(
            level=level,
            confidence=confidence,
            matched_indicators=all_indicators,
            detected_pii_types=pii_types,
            reason=reason,
            requires_encryption=level in [ConfidentialityLevel.CONFIDENTIAL, ConfidentialityLevel.STRICTLY_CONFIDENTIAL],
            access_restriction=access_restriction,
        )

    def _normalize_text(self, text: str) -> str:
        """Normalisiere Text für Marker-Matching."""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _find_markers(self, text: str, markers: Set[str]) -> List[str]:
        """Finde alle passenden Marker im Text."""
        return [marker for marker in markers if marker in text]

    def _scan_pii(self, text: str) -> List[str]:
        """Scanne Text nach PII-Typen."""
        found_types = []
        for pii_type, pattern in PII_PATTERNS.items():
            if pattern.search(text):
                found_types.append(pii_type)
        return found_types

    def _get_doc_type_level(self, document_type: Optional[str]) -> Optional[ConfidentialityLevel]:
        """Bestimme Standardlevel basierend auf Dokumenttyp."""
        if not document_type:
            return None

        doc_type_lower = document_type.lower()

        for strict_type in STRICTLY_CONFIDENTIAL_TYPES:
            if strict_type in doc_type_lower:
                return ConfidentialityLevel.STRICTLY_CONFIDENTIAL

        for conf_type in CONFIDENTIAL_TYPES:
            if conf_type in doc_type_lower:
                return ConfidentialityLevel.CONFIDENTIAL

        for internal_type in INTERNAL_TYPES:
            if internal_type in doc_type_lower:
                return ConfidentialityLevel.INTERNAL

        return None

    def _determine_level(
        self,
        strict_markers: List[str],
        conf_markers: List[str],
        internal_markers: List[str],
        pii_types: List[str],
        trade_secrets: List[str],
        doc_type_level: Optional[ConfidentialityLevel],
    ) -> tuple:
        """
        Bestimme Vertraulichkeitslevel.

        Returns:
            (level, confidence, reason)
        """
        # Priorität 1: Explizite streng vertraulich Marker
        if strict_markers:
            return (
                ConfidentialityLevel.STRICTLY_CONFIDENTIAL,
                0.95,
                f"Expliziter Marker: {strict_markers[0]}",
            )

        # Priorität 2: Sensible PII (Gehalt, Steuer-ID, etc.)
        sensitive_pii = {"gehalt", "steuer_id", "sozialversicherung"}
        if any(pii in pii_types for pii in sensitive_pii):
            return (
                ConfidentialityLevel.STRICTLY_CONFIDENTIAL,
                0.9,
                f"Sensible personenbezogene Daten erkannt: {', '.join(pii_types)}",
            )

        # Priorität 3: Trade Secrets
        if len(trade_secrets) >= 2:
            return (
                ConfidentialityLevel.STRICTLY_CONFIDENTIAL,
                0.85,
                f"Geschäftsgeheimnisse erkannt: {', '.join(trade_secrets[:2])}",
            )

        # Priorität 4: Explizite vertraulich Marker
        if conf_markers:
            return (
                ConfidentialityLevel.CONFIDENTIAL,
                0.9,
                f"Expliziter Marker: {conf_markers[0]}",
            )

        # Priorität 5: PII vorhanden
        if pii_types:
            return (
                ConfidentialityLevel.CONFIDENTIAL,
                0.8,
                f"Personenbezogene Daten erkannt: {', '.join(pii_types)}",
            )

        # Priorität 6: Trade Secrets (einzeln)
        if trade_secrets:
            return (
                ConfidentialityLevel.CONFIDENTIAL,
                0.75,
                f"Potenzielle Geschäftsinformationen: {trade_secrets[0]}",
            )

        # Priorität 7: Dokumenttyp-basiert
        if doc_type_level:
            confidence = 0.8 if doc_type_level == ConfidentialityLevel.STRICTLY_CONFIDENTIAL else 0.7
            return (
                doc_type_level,
                confidence,
                f"Basierend auf Dokumenttyp",
            )

        # Priorität 8: Explizite intern Marker
        if internal_markers:
            return (
                ConfidentialityLevel.INTERNAL,
                0.85,
                f"Expliziter Marker: {internal_markers[0]}",
            )

        # Default: Internal (sicherer Default)
        return (
            ConfidentialityLevel.INTERNAL,
            0.6,
            "Standardklassifikation für Geschäftsdokumente",
        )

    def _get_access_restriction(self, level: ConfidentialityLevel) -> str:
        """Bestimme Zugriffsbeschraenkung basierend auf Level."""
        restrictions = {
            ConfidentialityLevel.PUBLIC: "Keine Einschränkung",
            ConfidentialityLevel.INTERNAL: "Alle Mitarbeiter",
            ConfidentialityLevel.CONFIDENTIAL: "Nur autorisierte Mitarbeiter",
            ConfidentialityLevel.STRICTLY_CONFIDENTIAL: "Nur Geschäftsführung und benannte Personen",
        }
        return restrictions.get(level, "Unbekannt")

    def get_stats(self) -> dict:
        """Gibt Klassifizierungs-Statistiken zurück."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Setzt Statistiken zurück."""
        self._stats = {
            "total_classifications": 0,
            "by_level": {level.value: 0 for level in ConfidentialityLevel},
            "pii_detections": 0,
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_confidentiality_classifier: Optional[ConfidentialityClassifier] = None


def get_confidentiality_classifier() -> ConfidentialityClassifier:
    """Gibt die Singleton-Instanz des Confidentiality Classifier zurück."""
    global _confidentiality_classifier
    if _confidentiality_classifier is None:
        _confidentiality_classifier = ConfidentialityClassifier()
    return _confidentiality_classifier
