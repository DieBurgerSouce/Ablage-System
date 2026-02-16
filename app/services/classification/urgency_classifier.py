# -*- coding: utf-8 -*-
"""
Urgency Classifier Service.

Klassifiziert Dokumente nach Dringlichkeit basierend auf:
- Erkannte Fristen und Deadlines
- Mahnungen und Eskalationen
- Keywords für Dringlichkeit
- Dokumenttyp-spezifische Regeln

Dringlichkeitsstufen:
- IMMEDIATE: Frist < 3 Tage, Mahnungen, kritische Dokumente
- NORMAL: Frist 3-14 Tage, Standard-Geschäftsdokumente
- CAN_WAIT: Frist > 14 Tage oder keine Frist

Feinpoliert und durchdacht.
"""

import re
import structlog
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Set, Tuple

logger = structlog.get_logger(__name__)


class UrgencyLevel(str, Enum):
    """Dringlichkeitsstufen für Dokumente."""
    IMMEDIATE = "immediate"  # < 3 Tage
    NORMAL = "normal"  # 3-14 Tage
    CAN_WAIT = "can_wait"  # > 14 Tage oder keine Frist


@dataclass
class UrgencyClassificationResult:
    """Ergebnis der Dringlichkeitsklassifikation."""
    urgency_level: UrgencyLevel
    confidence: float
    deadline: Optional[datetime]
    days_until_deadline: Optional[int]
    matched_indicators: List[str]
    reason: str


# =============================================================================
# KEYWORD CONFIGURATION
# =============================================================================

# Keywords für hoechste Dringlichkeit (IMMEDIATE)
IMMEDIATE_KEYWORDS: Set[str] = {
    # Mahnungen
    "mahnung", "zahlungserinnerung", "letzte mahnung", "inkasso",
    "1. mahnung", "2. mahnung", "3. mahnung", "erste mahnung",
    "zweite mahnung", "dritte mahnung", "mahnverfahren",

    # Dringlichkeit
    "dringend", "sofort", "umgehend", "unverzueglich", "eilig",
    "fristablauf", "letzte frist", "endgültig", "abschlussfrist",

    # Rechtliche Eskalation
    "anwalt", "rechtlich", "gerichtlich", "vollstreckung",
    "zwangsvollstreckung", "androhung", "klage", "mahnbescheid",

    # Kündigungen
    "kündigung", "vertragsende", "letzter tag", "ablauf",

    # Finanzielle Dringlichkeit
    "skonto", "skontofrist", "rabattfrist", "zahlungsfrist",
    "überfällig", "rückstand", "ausstehend",
}

# Keywords für normale Dringlichkeit (NORMAL)
NORMAL_KEYWORDS: Set[str] = {
    "zahlungsziel", "fällig", "bis zum", "spätestens",
    "deadline", "termin", "frist", "abgabetermin",
    "liefertermin", "lieferdatum", "verlängerung",
    "gültig bis", "angebotsfrist",
}

# Keywords die auf niedrige Dringlichkeit hinweisen
LOW_URGENCY_KEYWORDS: Set[str] = {
    "zur kenntnisnahme", "zur information", "archiv",
    "dokumentation", "protokoll", "bericht", "jahresbericht",
    "übersicht", "zusammenfassung", "nachrichtlich",
    "kopie", "duplikat",
}

# Dokumenttypen mit hoher Standarddringlichkeit
HIGH_URGENCY_DOC_TYPES: Set[str] = {
    "dunning", "dunning_letter", "mahnung",
    "cancellation", "kündigung",
    "legal_notice", "rechtliche_mitteilung",
}

# Regex-Patterns für Datumserkennung
DATE_PATTERNS = [
    # DD.MM.YYYY oder DD.MM.YY
    re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})'),
    # YYYY-MM-DD (ISO)
    re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})'),
    # "bis zum DD.MM."
    re.compile(r'bis\s+(?:zum\s+)?(\d{1,2})\.(\d{1,2})\.?(?:(\d{2,4}))?', re.IGNORECASE),
    # "innerhalb von X Tagen"
    re.compile(r'innerhalb\s+(?:von\s+)?(\d+)\s+(?:werk)?tage?n?', re.IGNORECASE),
    # "X Tage Frist"
    re.compile(r'(\d+)\s+(?:werk)?tage?\s+(?:frist|zahlungsziel)', re.IGNORECASE),
]


class UrgencyClassifier:
    """
    Klassifiziert Dokumente nach Dringlichkeit.

    Performance: < 10ms pro Dokument (rein regelbasiert)
    """

    # Schwellenwerte für Dringlichkeit
    IMMEDIATE_DAYS = 3
    NORMAL_DAYS = 14

    def __init__(self) -> None:
        """Initialisiere den Urgency Classifier."""
        self._stats = {
            "total_classifications": 0,
            "by_level": {level.value: 0 for level in UrgencyLevel},
        }

    def classify(
        self,
        text: str,
        document_type: Optional[str] = None,
        document_date: Optional[datetime] = None,
    ) -> UrgencyClassificationResult:
        """
        Klassifiziere die Dringlichkeit eines Dokuments.

        Args:
            text: OCR-Text des Dokuments
            document_type: Optionaler Dokumenttyp für kontextuelle Klassifikation
            document_date: Optionales Dokumentdatum für Fristberechnung

        Returns:
            UrgencyClassificationResult mit Level, Confidence und Details
        """
        if not text or not text.strip():
            return UrgencyClassificationResult(
                urgency_level=UrgencyLevel.CAN_WAIT,
                confidence=0.5,
                deadline=None,
                days_until_deadline=None,
                matched_indicators=[],
                reason="Kein Text zur Analyse vorhanden",
            )

        self._stats["total_classifications"] += 1

        # Text normalisieren
        normalized_text = self._normalize_text(text)

        # 1. Fristen extrahieren
        deadline, days_until = self._extract_deadline(normalized_text, document_date)

        # 2. Keywords analysieren
        immediate_matches = self._find_keywords(normalized_text, IMMEDIATE_KEYWORDS)
        normal_matches = self._find_keywords(normalized_text, NORMAL_KEYWORDS)
        low_matches = self._find_keywords(normalized_text, LOW_URGENCY_KEYWORDS)

        # 3. Dokumenttyp berücksichtigen
        doc_type_score = 0.0
        if document_type and document_type.lower() in HIGH_URGENCY_DOC_TYPES:
            doc_type_score = 0.3

        # 4. Score berechnen
        urgency_level, confidence, reason = self._calculate_urgency(
            deadline=deadline,
            days_until=days_until,
            immediate_matches=immediate_matches,
            normal_matches=normal_matches,
            low_matches=low_matches,
            doc_type_score=doc_type_score,
        )

        # Statistik aktualisieren
        self._stats["by_level"][urgency_level.value] += 1

        all_matches = list(immediate_matches) + list(normal_matches)

        logger.debug(
            "urgency_classified",
            urgency_level=urgency_level.value,
            confidence=confidence,
            deadline=deadline.isoformat() if deadline else None,
            days_until=days_until,
            matched_indicators=all_matches[:5],
        )

        return UrgencyClassificationResult(
            urgency_level=urgency_level,
            confidence=confidence,
            deadline=deadline,
            days_until_deadline=days_until,
            matched_indicators=all_matches,
            reason=reason,
        )

    def _normalize_text(self, text: str) -> str:
        """Normalisiere Text für Keyword-Matching."""
        text = text.lower()
        # Deutsche Umlaute beibehalten für besseres Matching
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _find_keywords(self, text: str, keywords: Set[str]) -> List[str]:
        """Finde alle passenden Keywords im Text."""
        matches = []
        for keyword in keywords:
            if keyword in text:
                matches.append(keyword)
        return matches

    def _extract_deadline(
        self,
        text: str,
        document_date: Optional[datetime],
    ) -> Tuple[Optional[datetime], Optional[int]]:
        """
        Extrahiere Deadline aus dem Text.

        Returns:
            (deadline_datetime, days_until_deadline)
        """
        today = datetime.now()
        base_date = document_date or today

        # Versuche verschiedene Patterns
        for pattern in DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                try:
                    groups = match.groups()

                    # Pattern "innerhalb von X Tagen"
                    if len(groups) == 1:
                        days = int(groups[0])
                        deadline = base_date + timedelta(days=days)
                        days_until = (deadline - today).days
                        return deadline, days_until

                    # Datums-Pattern
                    if len(groups) >= 2:
                        day = int(groups[0])
                        month = int(groups[1])
                        year = int(groups[2]) if groups[2] else today.year

                        # 2-stellige Jahreszahl korrigieren
                        if year < 100:
                            year += 2000

                        deadline = datetime(year, month, day)

                        # Wenn Datum in Vergangenheit und kein Jahr angegeben,
                        # nächstes Jahr annehmen
                        if deadline < today and not groups[2]:
                            deadline = datetime(today.year + 1, month, day)

                        days_until = (deadline - today).days
                        return deadline, days_until

                except (ValueError, TypeError):
                    continue

        return None, None

    def _calculate_urgency(
        self,
        deadline: Optional[datetime],
        days_until: Optional[int],
        immediate_matches: List[str],
        normal_matches: List[str],
        low_matches: List[str],
        doc_type_score: float,
    ) -> Tuple[UrgencyLevel, float, str]:
        """
        Berechne Dringlichkeitslevel basierend auf allen Faktoren.

        Returns:
            (urgency_level, confidence, reason)
        """
        # Basis-Score für Immediate (0-1)
        immediate_score = 0.0
        normal_score = 0.0
        low_score = 0.0

        # Faktor 1: Deadline
        if days_until is not None:
            if days_until <= 0:
                immediate_score += 0.8
            elif days_until <= self.IMMEDIATE_DAYS:
                immediate_score += 0.6
            elif days_until <= self.NORMAL_DAYS:
                normal_score += 0.5
            else:
                low_score += 0.3

        # Faktor 2: Keywords
        immediate_score += min(0.5, len(immediate_matches) * 0.15)
        normal_score += min(0.3, len(normal_matches) * 0.1)
        low_score += min(0.3, len(low_matches) * 0.15)

        # Faktor 3: Dokumenttyp
        immediate_score += doc_type_score

        # Entscheidung treffen
        if immediate_score >= 0.4:
            confidence = min(0.99, 0.5 + immediate_score * 0.5)

            if days_until is not None and days_until <= 0:
                reason = "Frist bereits abgelaufen"
            elif days_until is not None:
                reason = f"Frist in {days_until} Tagen"
            elif immediate_matches:
                reason = f"Dringlichkeits-Indikatoren: {', '.join(immediate_matches[:3])}"
            else:
                reason = "Dokumenttyp erfordert sofortige Bearbeitung"

            return UrgencyLevel.IMMEDIATE, confidence, reason

        if normal_score >= 0.3 or (days_until is not None and days_until <= self.NORMAL_DAYS):
            confidence = min(0.95, 0.5 + normal_score)

            if days_until is not None:
                reason = f"Frist in {days_until} Tagen"
            else:
                reason = "Standard-Geschäftsdokument mit erkannter Frist"

            return UrgencyLevel.NORMAL, confidence, reason

        # Default: Niedrige Dringlichkeit
        confidence = min(0.9, 0.5 + low_score)

        if low_matches:
            reason = f"Informatives Dokument: {', '.join(low_matches[:2])}"
        else:
            reason = "Keine erkannte Frist oder Dringlichkeit"

        return UrgencyLevel.CAN_WAIT, confidence, reason

    def get_stats(self) -> dict:
        """Gibt Klassifizierungs-Statistiken zurück."""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """Setzt Statistiken zurück."""
        self._stats = {
            "total_classifications": 0,
            "by_level": {level.value: 0 for level in UrgencyLevel},
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_urgency_classifier: Optional[UrgencyClassifier] = None


def get_urgency_classifier() -> UrgencyClassifier:
    """Gibt die Singleton-Instanz des Urgency Classifier zurück."""
    global _urgency_classifier
    if _urgency_classifier is None:
        _urgency_classifier = UrgencyClassifier()
    return _urgency_classifier
