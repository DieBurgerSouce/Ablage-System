# -*- coding: utf-8 -*-
"""
DATEV Steuerschluessel (BU-Schluessel) Mapper.

Mappt MwSt-Sätze und Steuerszenarien auf DATEV BU-Schluessel.

DATEV BU-Schluessel (Auswahl):
- 0: Keine automatische Steuer
- 2: Umsatzsteuer 7%
- 3: Umsatzsteuer 19%
- 8: Vorsteuer 7%
- 9: Vorsteuer 19%
- 10: Innergemeinschaftliche Lieferung
- 13: Reverse Charge (Leistungsempfänger schuldet)
- 91: Reverse Charge Vorsteuer
- 93: IG-Erwerb 7%
- 94: IG-Erwerb 19%
"""

from decimal import Decimal
from typing import Optional

from app.api.schemas.extracted_data import InvoiceDirection
from ..constants import EU_MEMBER_STATES


class TaxCodeMapper:
    """
    Mappt MwSt-Sätze auf DATEV Steuerschluessel (BU-Schluessel).

    Berücksichtigt:
    - Standard-Sätze (19%, 7%)
    - Reverse Charge (§13b UStG)
    - Innergemeinschaftliche Lieferung/Erwerb
    - Steuerfreie Umsätze
    - Auslandsgeschäfte (Drittland)
    """

    # =========================================================================
    # VORSTEUER (Eingangsrechnungen)
    # =========================================================================

    # Standard-Vorsteuer
    VORSTEUER_19 = "9"            # Vorsteuer 19%
    VORSTEUER_7 = "8"             # Vorsteuer 7%

    # Innergemeinschaftlicher Erwerb (§1a UStG)
    VORSTEUER_EU_19 = "94"        # IG-Erwerb 19%
    VORSTEUER_EU_7 = "93"         # IG-Erwerb 7%

    # Reverse Charge (§13b UStG) - Leistungsempfänger als Steuerschuldner
    VORSTEUER_RC_19 = "91"        # Reverse Charge 19%
    VORSTEUER_RC_7 = "92"         # Reverse Charge 7%

    # Steuerfrei / Drittland
    VORSTEUER_0 = "0"             # Ohne automatische Steuer

    # =========================================================================
    # UMSATZSTEUER (Ausgangsrechnungen)
    # =========================================================================

    # Standard-Umsatzsteuer
    UMSATZSTEUER_19 = "3"         # Umsatzsteuer 19%
    UMSATZSTEUER_7 = "2"          # Umsatzsteuer 7%

    # Innergemeinschaftliche Lieferung (§4 Nr. 1b UStG)
    UMSATZSTEUER_EU = "10"        # IG-Lieferung (steuerfrei mit Nachweis)

    # Reverse Charge (§13b UStG) - Empfänger schuldet Steuer
    UMSATZSTEUER_RC = "13"        # Reverse Charge Ausgang

    # Steuerfrei / Drittland
    UMSATZSTEUER_0 = "0"          # Ohne automatische Steuer
    UMSATZSTEUER_DRITTLAND = "0"  # Ausfuhrlieferung (steuerfrei)

    def get_tax_code(
        self,
        vat_rate: Optional[Decimal],
        direction: InvoiceDirection,
        is_reverse_charge: bool = False,
        is_intra_community: bool = False,
        is_third_country: bool = False,
        sender_country: Optional[str] = None,
        recipient_country: Optional[str] = None,
    ) -> Optional[str]:
        """
        Ermittelt den DATEV Steuerschluessel (BU-Schluessel).

        Args:
            vat_rate: MwSt-Satz als Decimal (z.B. Decimal("19"))
            direction: INCOMING oder OUTGOING
            is_reverse_charge: True wenn Reverse Charge (§13b)
            is_intra_community: True bei innergemeinschaftlichem Geschäft
            is_third_country: True bei Drittlandsgeschäft
            sender_country: ISO-Ländercode des Absenders
            recipient_country: ISO-Ländercode des Empfängers

        Returns:
            DATEV BU-Schluessel oder None wenn unklar
        """
        # Richtung unbekannt = kein Steuerschluessel
        if direction == InvoiceDirection.UNKNOWN:
            return None

        # Steuersatz normalisieren
        rate = self._normalize_rate(vat_rate)

        if direction == InvoiceDirection.INCOMING:
            return self._get_incoming_tax_code(
                rate=rate,
                is_reverse_charge=is_reverse_charge,
                is_intra_community=is_intra_community,
                is_third_country=is_third_country,
                sender_country=sender_country,
            )
        else:
            return self._get_outgoing_tax_code(
                rate=rate,
                is_reverse_charge=is_reverse_charge,
                is_intra_community=is_intra_community,
                is_third_country=is_third_country,
                recipient_country=recipient_country,
            )

    def _get_incoming_tax_code(
        self,
        rate: int,
        is_reverse_charge: bool,
        is_intra_community: bool,
        is_third_country: bool,
        sender_country: Optional[str],
    ) -> str:
        """Ermittelt Steuerschluessel für Eingangsrechnungen."""

        # Drittland (keine EU-Steuer, zollrechtliche Behandlung)
        if is_third_country:
            return self.VORSTEUER_0

        # Reverse Charge (§13b UStG)
        if is_reverse_charge:
            if rate == 7:
                return self.VORSTEUER_RC_7
            return self.VORSTEUER_RC_19

        # Innergemeinschaftlicher Erwerb (EU)
        if is_intra_community or (sender_country and self._is_eu_country(sender_country)):
            if rate == 7:
                return self.VORSTEUER_EU_7
            return self.VORSTEUER_EU_19

        # Standard Vorsteuer (Inland)
        if rate == 19:
            return self.VORSTEUER_19
        elif rate == 7:
            return self.VORSTEUER_7
        elif rate == 0:
            return self.VORSTEUER_0

        # Fallback: 19% Vorsteuer
        return self.VORSTEUER_19

    def _get_outgoing_tax_code(
        self,
        rate: int,
        is_reverse_charge: bool,
        is_intra_community: bool,
        is_third_country: bool,
        recipient_country: Optional[str],
    ) -> str:
        """Ermittelt Steuerschluessel für Ausgangsrechnungen."""

        # Drittland Export (steuerfrei mit Nachweis)
        if is_third_country:
            return self.UMSATZSTEUER_DRITTLAND

        # Innergemeinschaftliche Lieferung (EU)
        if is_intra_community or (recipient_country and self._is_eu_country(recipient_country)):
            return self.UMSATZSTEUER_EU

        # Reverse Charge (Empfänger schuldet Steuer)
        if is_reverse_charge:
            return self.UMSATZSTEUER_RC

        # Standard Umsatzsteuer (Inland)
        if rate == 19:
            return self.UMSATZSTEUER_19
        elif rate == 7:
            return self.UMSATZSTEUER_7
        elif rate == 0:
            return self.UMSATZSTEUER_0

        # Fallback: 19% Umsatzsteuer
        return self.UMSATZSTEUER_19

    def _normalize_rate(self, vat_rate: Optional[Decimal]) -> int:
        """Normalisiert MwSt-Satz zu Integer (0, 7, oder 19)."""
        if vat_rate is None:
            return 19  # Default

        rate = float(vat_rate)

        # Toleranzbereich für Rundungsfehler
        if abs(rate - 19) < 0.5:
            return 19
        elif abs(rate - 7) < 0.5:
            return 7
        elif abs(rate) < 0.5:
            return 0
        else:
            # Unbekannter Steuersatz - Default 19%
            return 19

    def _is_eu_country(self, country_code: str) -> bool:
        """
        Prüft ob Ländercode ein EU-Land ist (ausser DE).

        Verwendet zentrale EU_MEMBER_STATES aus constants.py.
        """
        if not country_code:
            return False
        upper_code = country_code.upper()
        # EU-Mitglied aber nicht Deutschland (DE ist der lokale Staat)
        return upper_code in EU_MEMBER_STATES and upper_code != "DE"

    def get_description(self, tax_code: str) -> str:
        """Gibt Beschreibung für einen Steuerschluessel zurück."""
        descriptions = {
            "0": "Ohne automatische Steuer",
            "2": "Umsatzsteuer 7%",
            "3": "Umsatzsteuer 19%",
            "8": "Vorsteuer 7%",
            "9": "Vorsteuer 19%",
            "10": "Innergemeinschaftliche Lieferung",
            "13": "Reverse Charge (Empfänger schuldet)",
            "91": "Reverse Charge Vorsteuer 19%",
            "92": "Reverse Charge Vorsteuer 7%",
            "93": "IG-Erwerb 7%",
            "94": "IG-Erwerb 19%",
        }
        return descriptions.get(tax_code, f"Unbekannt ({tax_code})")
