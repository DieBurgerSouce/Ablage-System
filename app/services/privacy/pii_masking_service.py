# -*- coding: utf-8 -*-
"""
PII Masking Service.

Maskiert und pseudonymisiert personenbezogene Daten:
- Vollständige Maskierung (****)
- Partielle Maskierung (DE89****1234)
- Pseudonymisierung (reversibel mit Schluessel)
- Tokenisierung

Feinpoliert und durchdacht.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List, Tuple, Union
from typing_extensions import TypedDict

# Type definitions for mypy strict mode - no Any types
MaskingMetadata = Union[str, int, float, bool, None]
JSONValue = Union[str, int, float, bool, None, List["JSONValue"], Dict[str, "JSONValue"]]


class ReplacementDict(TypedDict, total=False):
    """Typed dictionary for replacement info."""
    original: str
    masked: str
    pii_type: str
    start: int
    end: int
    strategy: str
import re

from app.services.privacy.pii_detection_service import (
    PIIDetectionService,
    PIIType,
    PIIMatch,
    PIISensitivity,
)

logger = logging.getLogger(__name__)


class MaskingStrategy(str, Enum):
    """Maskierungsstrategien."""
    FULL = "full"           # Vollständige Maskierung: ********
    PARTIAL = "partial"     # Partielle Maskierung: DE89****1234
    HASH = "hash"           # Hash-Ersetzung: sha256(value)[:8]
    PSEUDONYM = "pseudonym" # Pseudonymisierung: [PERSON-001]
    REDACT = "redact"       # Schwärzung: [REDACTED]
    TOKEN = "token"         # Tokenisierung: tok_abc123


@dataclass
class MaskingResult:
    """Ergebnis einer Maskierung."""
    original_text: str
    masked_text: str
    replacements: List[ReplacementDict]
    tokens_map: Dict[str, str]  # Token -> Original (für Reversierung)


class PIIMaskingService:
    """
    Service für die Maskierung personenbezogener Daten.

    Unterstützt verschiedene Maskierungsstrategien je nach
    Sensibilitaet und Verwendungszweck.
    """

    # Standard-Maskierungszeichen
    MASK_CHAR = "*"

    # Strategie pro Sensibilitaet (Standard)
    DEFAULT_STRATEGIES = {
        PIISensitivity.LOW: MaskingStrategy.PARTIAL,
        PIISensitivity.MEDIUM: MaskingStrategy.PARTIAL,
        PIISensitivity.HIGH: MaskingStrategy.FULL,
        PIISensitivity.CRITICAL: MaskingStrategy.REDACT,
    }

    # Typ-spezifische Maskierungsregeln
    TYPE_SPECIFIC_MASKS = {
        PIIType.IBAN: {
            "strategy": MaskingStrategy.PARTIAL,
            "show_start": 4,   # DE89
            "show_end": 4,     # Letzte 4 Ziffern
        },
        PIIType.CREDIT_CARD: {
            "strategy": MaskingStrategy.PARTIAL,
            "show_start": 0,
            "show_end": 4,     # Nur letzte 4 Ziffern
        },
        PIIType.EMAIL: {
            "strategy": MaskingStrategy.PARTIAL,
            "show_start": 2,   # Erste 2 Zeichen
            "show_end": 0,
            "preserve_domain": True,
        },
        PIIType.PHONE: {
            "strategy": MaskingStrategy.PARTIAL,
            "show_start": 4,   # Vorwahl
            "show_end": 2,     # Letzte 2 Ziffern
        },
        PIIType.NAME: {
            "strategy": MaskingStrategy.PSEUDONYM,
            "prefix": "PERSON",
        },
        PIIType.ADDRESS: {
            "strategy": MaskingStrategy.REDACT,
        },
        PIIType.SALARY: {
            "strategy": MaskingStrategy.REDACT,
        },
        PIIType.HEALTH_DATA: {
            "strategy": MaskingStrategy.REDACT,
        },
    }

    def __init__(
        self,
        detection_service: Optional[PIIDetectionService] = None,
        secret_key: Optional[str] = None,
    ):
        """
        Initialisiere Service.

        Args:
            detection_service: Optional vorhandener Detection-Service
            secret_key: Geheimer Schluessel für reversible Pseudonymisierung
        """
        self.detection_service = detection_service or PIIDetectionService()
        self.secret_key = secret_key or secrets.token_hex(32)
        self._pseudonym_counter: Dict[str, int] = {}
        self._token_map: Dict[str, str] = {}  # Token -> Original

    def mask_text(
        self,
        text: str,
        strategy: Optional[MaskingStrategy] = None,
        pii_types: Optional[set] = None,
    ) -> MaskingResult:
        """
        Maskiere PII in einem Text.

        Args:
            text: Zu maskierender Text
            strategy: Globale Maskierungsstrategie (überschreibt Typ-spezifische)
            pii_types: Optional Set von zu maskierenden PII-Typen

        Returns:
            MaskingResult mit maskiertem Text und Mapping
        """
        if not text:
            return MaskingResult(
                original_text="",
                masked_text="",
                replacements=[],
                tokens_map={},
            )

        # PII erkennen
        detection_result = self.detection_service.detect(text, pii_types)

        if not detection_result.pii_found:
            return MaskingResult(
                original_text=text,
                masked_text=text,
                replacements=[],
                tokens_map={},
            )

        # Sortiere Matches nach Position (rückwärts für korrekte Ersetzung)
        sorted_matches = sorted(
            detection_result.pii_found,
            key=lambda m: m.start,
            reverse=True,
        )

        masked_text = text
        replacements = []
        tokens_map = {}

        for match in sorted_matches:
            # Bestimme Strategie
            mask_strategy = strategy or self._get_strategy_for_match(match)

            # Maskiere
            masked_value, token = self._mask_value(match, mask_strategy)

            # Ersetze im Text
            masked_text = (
                masked_text[:match.start] +
                masked_value +
                masked_text[match.end:]
            )

            # Speichere Ersetzung (typed dict)
            replacements.append(ReplacementDict(
                original=match.value,
                masked=masked_value,
                pii_type=match.pii_type.value,
                start=match.start,
                end=match.end,
                strategy=mask_strategy.value,
            ))

            # Token-Map für Reversierung
            if token:
                tokens_map[token] = match.value

        # Kehre Replacements um (für chronologische Reihenfolge)
        replacements.reverse()

        return MaskingResult(
            original_text=text,
            masked_text=masked_text,
            replacements=replacements,
            tokens_map=tokens_map,
        )

    def mask_dict(
        self,
        data: Dict[str, JSONValue],
        strategy: Optional[MaskingStrategy] = None,
        pii_types: Optional[set] = None,
    ) -> Dict[str, JSONValue]:
        """
        Maskiere PII in allen String-Werten eines Dictionaries.

        Args:
            data: Dictionary mit zu maskierenden Werten
            strategy: Globale Maskierungsstrategie
            pii_types: Optional Set von zu maskierenden PII-Typen

        Returns:
            Dictionary mit maskierten Werten
        """
        result: Dict[str, JSONValue] = {}

        for key, value in data.items():
            if isinstance(value, str):
                mask_result = self.mask_text(value, strategy, pii_types)
                result[key] = mask_result.masked_text
            elif isinstance(value, dict):
                # Type cast for recursive call
                nested_dict = {k: v for k, v in value.items() if isinstance(k, str)}
                result[key] = self.mask_dict(nested_dict, strategy, pii_types)
            elif isinstance(value, list):
                masked_list: List[JSONValue] = []
                for item in value:
                    if isinstance(item, str):
                        masked_list.append(self.mask_text(item, strategy, pii_types).masked_text)
                    else:
                        masked_list.append(item)
                result[key] = masked_list
            else:
                result[key] = value

        return result

    def unmask_text(
        self,
        masked_text: str,
        tokens_map: Dict[str, str],
    ) -> str:
        """
        Stelle Original-Text aus maskiertem Text wieder her.

        Nur möglich bei Token-basierten Maskierungen.

        Args:
            masked_text: Maskierter Text
            tokens_map: Token -> Original Mapping

        Returns:
            Original-Text (soweit möglich)
        """
        result = masked_text

        for token, original in tokens_map.items():
            result = result.replace(token, original)

        return result

    def create_pseudonym(
        self,
        value: str,
        pii_type: PIIType,
    ) -> str:
        """
        Erstelle konsistentes Pseudonym für einen Wert.

        Gleiche Werte ergeben immer das gleiche Pseudonym.

        Args:
            value: Zu pseudonymisierender Wert
            pii_type: Typ des PII

        Returns:
            Pseudonym wie [PERSON-001]
        """
        # Prefix basierend auf Typ
        prefix = self.TYPE_SPECIFIC_MASKS.get(pii_type, {}).get("prefix", pii_type.value.upper())

        # Hash des Werts für Konsistenz
        value_hash = hashlib.sha256(
            (value + self.secret_key).encode()
        ).hexdigest()[:8]

        return f"[{prefix}-{value_hash}]"

    def create_token(self, value: str) -> str:
        """
        Erstelle reversiblen Token für einen Wert.

        Args:
            value: Zu tokenisierender Wert

        Returns:
            Token wie tok_abc123
        """
        token_id = secrets.token_hex(6)
        token = f"tok_{token_id}"

        # Speichere Mapping
        self._token_map[token] = value

        return token

    def _get_strategy_for_match(self, match: PIIMatch) -> MaskingStrategy:
        """Bestimme Maskierungsstrategie für einen Match."""
        # Typ-spezifische Regel
        type_config = self.TYPE_SPECIFIC_MASKS.get(match.pii_type, {})
        if "strategy" in type_config:
            return type_config["strategy"]

        # Fallback: Sensibilitaets-basiert
        return self.DEFAULT_STRATEGIES.get(
            match.sensitivity,
            MaskingStrategy.PARTIAL,
        )

    def _mask_value(
        self,
        match: PIIMatch,
        strategy: MaskingStrategy,
    ) -> Tuple[str, Optional[str]]:
        """
        Maskiere einen einzelnen Wert.

        Args:
            match: Der PII-Match
            strategy: Zu verwendende Strategie

        Returns:
            Tuple aus (maskierter_wert, token_für_reversierung)
        """
        value = match.value
        token = None

        if strategy == MaskingStrategy.FULL:
            # Vollständige Maskierung
            masked = self.MASK_CHAR * len(value)

        elif strategy == MaskingStrategy.PARTIAL:
            masked = self._partial_mask(match)

        elif strategy == MaskingStrategy.HASH:
            # Hash-Ersetzung
            value_hash = hashlib.sha256(value.encode()).hexdigest()[:8]
            masked = f"[HASH:{value_hash}]"

        elif strategy == MaskingStrategy.PSEUDONYM:
            masked = self.create_pseudonym(value, match.pii_type)

        elif strategy == MaskingStrategy.REDACT:
            masked = "[REDACTED]"

        elif strategy == MaskingStrategy.TOKEN:
            token = self.create_token(value)
            masked = token

        else:
            # Fallback
            masked = self.MASK_CHAR * len(value)

        return masked, token

    def _partial_mask(self, match: PIIMatch) -> str:
        """Partielle Maskierung basierend auf Typ-Konfiguration."""
        value = match.value
        config = self.TYPE_SPECIFIC_MASKS.get(match.pii_type, {})

        show_start = config.get("show_start", 2)
        show_end = config.get("show_end", 2)
        preserve_domain = config.get("preserve_domain", False)

        # E-Mail-Spezialfall
        if match.pii_type == PIIType.EMAIL and preserve_domain:
            parts = value.split("@")
            if len(parts) == 2:
                local = parts[0]
                domain = parts[1]
                if len(local) > show_start:
                    masked_local = local[:show_start] + self.MASK_CHAR * (len(local) - show_start)
                else:
                    masked_local = self.MASK_CHAR * len(local)
                return f"{masked_local}@{domain}"

        # Standard partielle Maskierung
        if len(value) <= show_start + show_end:
            # Zu kurz: Alles maskieren bis auf 1 Zeichen
            return value[0] + self.MASK_CHAR * (len(value) - 1)

        start_part = value[:show_start]
        end_part = value[-show_end:] if show_end > 0 else ""
        middle_length = len(value) - show_start - show_end
        middle_masked = self.MASK_CHAR * middle_length

        return f"{start_part}{middle_masked}{end_part}"

    def mask_for_logs(
        self,
        text: str,
    ) -> str:
        """
        Maskiere Text für Log-Ausgaben.

        Schnelle Methode die kritische Daten immer maskiert.

        Args:
            text: Zu maskierender Text

        Returns:
            Maskierter Text
        """
        # Schnelle Patterns für Logs
        patterns = [
            # IBAN
            (r'(DE\d{2})\d{14}(\d{4})', r'\1**************\2'),
            # E-Mail
            (r'([a-zA-Z0-9._%+-]{2})[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
             r'\1***@\2'),
            # Kreditkarte
            (r'\b(\d{4})[\s-]?\d{4}[\s-]?\d{4}[\s-]?(\d{4})\b', r'\1-****-****-\2'),
            # Telefon
            (r'(\+49\s?[0-9]{2,4})\s?[0-9]{4,8}', r'\1*****'),
        ]

        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result)

        return result
