# -*- coding: utf-8 -*-
"""
CompanyMatchingService - Eingangs-/Ausgangsrechnung-Erkennung.

Vergleicht extrahierte Rechnungsdaten mit den Admin-Firmendaten
um automatisch zu erkennen ob es sich um eine Eingangs- oder
Ausgangsrechnung handelt.

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.extracted_data import (
    ExtractedAddress,
    ExtractedInvoiceData,
    InvoiceDirection,
)
from app.db.models import CompanySettings

logger = structlog.get_logger(__name__)


@dataclass
class MatchResult:
    """Ergebnis eines Adress-/Firmen-Vergleichs."""
    matched: bool
    confidence: float
    reason: str


class CompanyMatchingService:
    """
    Service zur Erkennung von Eingangs-/Ausgangsrechnungen.

    Vergleicht den extrahierten Empfaenger/Absender mit den
    Admin-Firmendaten und bestimmt die Rechnungsrichtung.

    Matching-Prioritaet (hoechste zuerst):
    1. VAT-ID exakt: 0.99 Confidence
    2. IBAN exakt: 0.95 Confidence
    3. Name exakt (inkl. alternative_names): 0.90 Confidence
    4. Name fuzzy (>90%) + PLZ: 0.85 Confidence
    5. Nur Name fuzzy (>90%): 0.70 Confidence
    """

    # Schwellenwert ab dem die Richtung als "erkannt" gilt
    CONFIDENCE_THRESHOLD = 0.80

    # Rechtsformen die beim Namensvergleich entfernt werden
    # FIX 2025-12-15: \s+ (nicht \s*) vor kurzen Suffixen wie AG, KG, SE, EG
    # um false positives zu vermeiden (z.B. "Montag" → "Monta" verhindern)
    LEGAL_SUFFIXES = [
        r"\s*gmbh\s*&\s*co\.?\s*kg\s*$",
        r"\s*gmbh\s*$",
        r"\s+ag\s*$",    # \s+ um "...dag" nicht zu matchen
        r"\s+kg\s*$",    # \s+ um "...ekg" nicht zu matchen
        r"\s+ohg\s*$",   # \s+ fuer Konsistenz
        r"\s*ug\s*(?:\(haftungsbeschraenkt\))?\s*$",
        r"\s*mbh\s*$",
        r"\s+se\s*$",    # \s+ um "Spargelmesse" nicht zu matchen
        r"\s+eg\s*$",    # \s+ um false positives zu vermeiden
        r"\s*e\.?\s*v\.?\s*$",
        r"\s*gbr\s*$",
        r"\s*b\.?\s*v\.?\s*$",  # Niederlaendisch
        r"\s*n\.?\s*v\.?\s*$",  # Niederlaendisch
        r"\s*s\.?\s*a\.?\s*$",  # Franzoesisch
        r"\s*ltd\.?\s*$",       # Englisch
        r"\s*inc\.?\s*$",       # Englisch
        r"\s*llc\.?\s*$",       # Englisch
    ]

    async def match_invoice_direction(
        self,
        invoice: ExtractedInvoiceData,
        db: AsyncSession
    ) -> Tuple[InvoiceDirection, float, str]:
        """
        Bestimmt ob es sich um eine Eingangs- oder Ausgangsrechnung handelt.

        Args:
            invoice: Extrahierte Rechnungsdaten
            db: Datenbank-Session

        Returns:
            Tuple mit (direction, confidence, reason)
        """
        # 1. CompanySettings laden
        company = await self._get_company_settings(db)
        if not company:
            logger.debug("company_matching_skipped", reason="no_company_settings")
            return (
                InvoiceDirection.UNKNOWN,
                0.0,
                "Keine Firmendaten konfiguriert"
            )

        # 2. Empfaenger pruefen (Eingangsrechnung = Rechnung AN uns)
        recipient_match = self._match_address_to_company(
            address=invoice.recipient,
            vat_id=invoice.recipient_vat_id,
            iban=None,  # Empfaenger-IBAN nicht relevant
            company=company
        )

        if recipient_match.confidence >= self.CONFIDENCE_THRESHOLD:
            logger.info(
                "invoice_direction_detected",
                direction="incoming",
                confidence=recipient_match.confidence,
                reason=recipient_match.reason
            )
            return (
                InvoiceDirection.INCOMING,
                recipient_match.confidence,
                recipient_match.reason
            )

        # 3. Absender pruefen (Ausgangsrechnung = Rechnung VON uns)
        sender_iban = None
        if invoice.sender_bank and invoice.sender_bank.iban:
            sender_iban = invoice.sender_bank.iban

        sender_match = self._match_address_to_company(
            address=invoice.sender,
            vat_id=invoice.sender_vat_id,
            iban=sender_iban,
            company=company
        )

        if sender_match.confidence >= self.CONFIDENCE_THRESHOLD:
            logger.info(
                "invoice_direction_detected",
                direction="outgoing",
                confidence=sender_match.confidence,
                reason=sender_match.reason
            )
            return (
                InvoiceDirection.OUTGOING,
                sender_match.confidence,
                sender_match.reason
            )

        # 4. Keine eindeutige Zuordnung
        logger.debug(
            "invoice_direction_unknown",
            recipient_confidence=recipient_match.confidence,
            sender_confidence=sender_match.confidence
        )
        return (
            InvoiceDirection.UNKNOWN,
            max(recipient_match.confidence, sender_match.confidence),
            "Keine eindeutige Zuordnung"
        )

    async def _get_company_settings(self, db: AsyncSession) -> Optional[CompanySettings]:
        """Laedt die Admin-Firmendaten aus der Datenbank."""
        result = await db.execute(
            select(CompanySettings).limit(1)
        )
        return result.scalar_one_or_none()

    def _match_address_to_company(
        self,
        address: Optional[ExtractedAddress],
        vat_id: Optional[str],
        iban: Optional[str],
        company: CompanySettings
    ) -> MatchResult:
        """
        Vergleicht eine extrahierte Adresse mit den Firmendaten.

        Matching-Prioritaet:
        1. VAT-ID exakt: 0.99
        2. IBAN exakt: 0.95
        3. Name exakt: 0.90
        4. Name fuzzy + PLZ: 0.85
        5. Name fuzzy: 0.70

        Args:
            address: Extrahierte Adresse (kann None sein)
            vat_id: USt-IdNr (kann None sein)
            iban: IBAN (kann None sein)
            company: Admin-Firmendaten

        Returns:
            MatchResult mit matched, confidence, reason
        """
        # 1. VAT-ID Vergleich (hoechste Prioritaet)
        if vat_id and company.vat_id:
            normalized_extracted = self._normalize_vat_id(vat_id)
            normalized_company = self._normalize_vat_id(company.vat_id)
            if normalized_extracted == normalized_company:
                return MatchResult(
                    matched=True,
                    confidence=0.99,
                    reason="USt-IdNr stimmt ueberein"
                )

        # 2. IBAN Vergleich
        if iban and company.iban:
            normalized_extracted = self._normalize_iban(iban)
            normalized_company = self._normalize_iban(company.iban)
            if normalized_extracted == normalized_company:
                return MatchResult(
                    matched=True,
                    confidence=0.95,
                    reason="IBAN stimmt ueberein"
                )

        # Fuer weitere Checks brauchen wir eine Adresse
        if not address:
            return MatchResult(
                matched=False,
                confidence=0.0,
                reason="Keine Adresse vorhanden"
            )

        # 3. Firmenname-Vergleich
        extracted_name = address.company
        if not extracted_name:
            return MatchResult(
                matched=False,
                confidence=0.0,
                reason="Kein Firmenname extrahiert"
            )

        # Alle moeglichen Firmennamen sammeln
        company_names = [company.company_name]
        if company.alternative_names:
            company_names.extend(company.alternative_names)

        # 3a. Exakter Name-Match
        for company_name in company_names:
            if self._names_match_exact(extracted_name, company_name):
                return MatchResult(
                    matched=True,
                    confidence=0.90,
                    reason="Firmenname stimmt exakt ueberein"
                )

        # 3b. Fuzzy Name-Match
        best_similarity = 0.0
        for company_name in company_names:
            similarity = self._calculate_name_similarity(extracted_name, company_name)
            best_similarity = max(best_similarity, similarity)

        if best_similarity >= 0.90:
            # PLZ-Vergleich fuer hoehere Confidence
            if address.zip_code and company.postal_code:
                if address.zip_code.strip() == company.postal_code.strip():
                    return MatchResult(
                        matched=True,
                        confidence=0.85,
                        reason=f"Firmenname aehnlich ({best_similarity:.0%}) und PLZ stimmt"
                    )

            # Nur Name-Match (niedrigere Confidence)
            return MatchResult(
                matched=True,
                confidence=0.70,
                reason=f"Firmenname aehnlich ({best_similarity:.0%})"
            )

        # Kein Match
        return MatchResult(
            matched=False,
            confidence=best_similarity * 0.5,  # Partielle Konfidenz
            reason="Keine Uebereinstimmung gefunden"
        )

    def _normalize_vat_id(self, vat_id: str) -> str:
        """Normalisiert eine USt-IdNr fuer den Vergleich."""
        return vat_id.replace(" ", "").replace(".", "").replace("-", "").upper()

    def _normalize_iban(self, iban: str) -> str:
        """Normalisiert eine IBAN fuer den Vergleich."""
        return iban.replace(" ", "").upper()

    def _names_match_exact(self, name1: str, name2: str) -> bool:
        """Prueft ob zwei Firmennamen exakt uebereinstimmen (nach Normalisierung)."""
        n1 = self._normalize_company_name(name1)
        n2 = self._normalize_company_name(name2)
        return n1 == n2

    def _normalize_company_name(self, name: str) -> str:
        """
        Normalisiert einen Firmennamen fuer den Vergleich.

        - Kleinbuchstaben
        - Rechtsformen entfernen
        - Mehrfache Leerzeichen entfernen
        """
        normalized = name.lower().strip()

        # Rechtsformen entfernen
        for suffix_pattern in self.LEGAL_SUFFIXES:
            normalized = re.sub(suffix_pattern, "", normalized, flags=re.IGNORECASE)

        # Mehrfache Leerzeichen entfernen
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Berechnet die Aehnlichkeit zweier Firmennamen (0.0-1.0).

        Verwendet Levenshtein-Distanz nach Normalisierung.
        """
        n1 = self._normalize_company_name(name1)
        n2 = self._normalize_company_name(name2)

        if n1 == n2:
            return 1.0

        if not n1 or not n2:
            return 0.0

        # Levenshtein-Distanz
        distance = self._levenshtein_distance(n1, n2)
        max_len = max(len(n1), len(n2))

        similarity = 1.0 - (distance / max_len)
        return round(max(0.0, similarity), 4)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Berechnet die Levenshtein-Distanz zwischen zwei Strings."""
        if len(s1) < len(s2):
            s1, s2 = s2, s1

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


# Singleton-Instanz fuer Performance
_company_matching_service: Optional[CompanyMatchingService] = None


def get_company_matching_service() -> CompanyMatchingService:
    """Gibt die Singleton-Instanz des CompanyMatchingService zurueck."""
    global _company_matching_service
    if _company_matching_service is None:
        _company_matching_service = CompanyMatchingService()
    return _company_matching_service
