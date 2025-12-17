# -*- coding: utf-8 -*-
"""
SKR04 Kontenrahmen.

Standardkontenrahmen fuer bilanzierende Unternehmen.
Verwendung: GmbH, AG, groessere Unternehmen mit Bilanzierungspflicht.

Gliederung (nach Abschlussgliederungsprinzip):
- Klasse 0: Anlagevermoegen
- Klasse 1: Umlaufvermoegen
- Klasse 2: Eigenkapital
- Klasse 3: Verbindlichkeiten, Rueckstellungen
- Klasse 4: Ertraege
- Klasse 5: Material- und Personalaufwand
- Klasse 6: Sonstige Aufwendungen
- Klasse 7: Weitere Ertraege und Aufwendungen
"""

from typing import Dict

from .base import BaseKontenrahmen


class SKR04(BaseKontenrahmen):
    """
    SKR04 Kontenrahmen Implementierung.

    Der SKR04 ist nach dem Abschlussgliederungsprinzip aufgebaut
    und orientiert sich an der Bilanz- und GuV-Struktur.
    """

    @property
    def name(self) -> str:
        return "SKR04"

    @property
    def beschreibung(self) -> str:
        return "Standardkontenrahmen fuer bilanzierende Unternehmen (abschlussorientiert)"

    # =========================================================================
    # AUFWANDSKONTEN (Klasse 5 und 6)
    # =========================================================================

    # Klasse 5: Materialaufwand
    WARENEINGANG_19 = "5200"      # Wareneingang 19% Vorsteuer
    WARENEINGANG_7 = "5300"       # Wareneingang 7% Vorsteuer
    WARENEINGANG_EU_19 = "5425"   # Innergemeinschaftlicher Erwerb 19%
    WARENEINGANG_EU_7 = "5435"    # Innergemeinschaftlicher Erwerb 7%
    WARENEINGANG_DRITTLAND = "5550"  # Einfuhr Drittland
    FREMDLEISTUNGEN = "5900"      # Aufwendungen fuer bez. Leistungen

    # Klasse 6: Sonstige betriebliche Aufwendungen
    MIETE = "6310"                # Miete
    NEBENKOSTEN = "6315"          # Nebenkosten
    LEASING_PKW = "6560"          # Leasingkosten PKW
    LEASING_SONSTIGE = "6565"     # Sonstige Leasingkosten
    REISEKOSTEN = "6650"          # Reisekosten
    BEWIRTUNG = "6640"            # Bewirtungskosten
    WERBUNG = "6600"              # Werbekosten
    BUEROKOSTEN = "6820"          # Buerokosten
    TELEFON = "6805"              # Telekommunikation
    VERSICHERUNGEN = "6400"       # Versicherungen
    RECHTSBERATUNG = "6825"       # Rechts- und Beratungskosten
    BUCHFUEHRUNG = "6827"         # Buchfuehrungskosten
    REPARATUREN = "6470"          # Reparatur und Instandhaltung
    KFZKOSTEN = "6520"            # Kfz-Kosten
    KFZBETRIEB = "6530"           # Lfd. Kfz-Betriebskosten
    ABSCHREIBUNGEN = "6200"       # Abschreibungen auf Sachanlagen

    # Klasse 7: Zinsen
    ZINSEN = "7310"               # Zinsaufwendungen

    @property
    def expense_accounts(self) -> Dict[str, str]:
        return {
            "waren": self.WARENEINGANG_19,
            "waren_19": self.WARENEINGANG_19,
            "waren_7": self.WARENEINGANG_7,
            "waren_eu_19": self.WARENEINGANG_EU_19,
            "waren_eu_7": self.WARENEINGANG_EU_7,
            "waren_drittland": self.WARENEINGANG_DRITTLAND,
            "dienstleistung": self.FREMDLEISTUNGEN,
            "fremdleistung": self.FREMDLEISTUNGEN,
            "miete": self.MIETE,
            "nebenkosten": self.NEBENKOSTEN,
            "leasing_pkw": self.LEASING_PKW,
            "leasing": self.LEASING_SONSTIGE,
            "reise": self.REISEKOSTEN,
            "bewirtung": self.BEWIRTUNG,
            "werbung": self.WERBUNG,
            "buero": self.BUEROKOSTEN,
            "telefon": self.TELEFON,
            "versicherung": self.VERSICHERUNGEN,
            "rechtsberatung": self.RECHTSBERATUNG,
            "buchfuehrung": self.BUCHFUEHRUNG,
            "reparatur": self.REPARATUREN,
            "kfz": self.KFZKOSTEN,
            "kfz_betrieb": self.KFZBETRIEB,
            "zinsen": self.ZINSEN,
            "abschreibung": self.ABSCHREIBUNGEN,
        }

    # Properties fuer Base-Klassen-Methoden (get_expense_account/get_revenue_account)
    @property
    def _wareneingang_19(self) -> str:
        return self.WARENEINGANG_19

    @property
    def _wareneingang_7(self) -> str:
        return self.WARENEINGANG_7

    # =========================================================================
    # ERLOESKONTEN (Klasse 4)
    # =========================================================================

    ERLOESE_19 = "4400"           # Erloese 19% USt
    ERLOESE_7 = "4300"            # Erloese 7% USt
    ERLOESE_0 = "4100"            # Steuerfreie Umsaetze Inland
    ERLOESE_EU = "4125"           # Steuerfreie IG Lieferungen
    ERLOESE_DRITTLAND = "4120"    # Steuerfreie Ausfuhrlieferungen
    ERLOESE_RC = "4337"           # Erloese Reverse Charge
    ERLOESE_SONSTIGE = "4830"     # Sonstige betriebliche Ertraege

    @property
    def revenue_accounts(self) -> Dict[str, str]:
        return {
            "waren": self.ERLOESE_19,
            "waren_19": self.ERLOESE_19,
            "waren_7": self.ERLOESE_7,
            "dienstleistung": self.ERLOESE_19,
            "dienstleistung_19": self.ERLOESE_19,
            "dienstleistung_7": self.ERLOESE_7,
            "steuerfrei": self.ERLOESE_0,
            "eu": self.ERLOESE_EU,
            "drittland": self.ERLOESE_DRITTLAND,
            "reverse_charge": self.ERLOESE_RC,
            "sonstige": self.ERLOESE_SONSTIGE,
        }

    @property
    def _erloese_19(self) -> str:
        return self.ERLOESE_19

    @property
    def _erloese_7(self) -> str:
        return self.ERLOESE_7

    # =========================================================================
    # PERSONENKONTEN (Defaults aus BaseKontenrahmen uebernommen)
    # =========================================================================
    # Kreditor-/Debitoren-Ranges sind identisch zu SKR03, daher in Base definiert

    # =========================================================================
    # SAMMELKONTEN (Klasse 3)
    # =========================================================================

    @property
    def sammelkonto_kreditoren(self) -> str:
        return "3300"  # Verbindlichkeiten aus LuL

    @property
    def sammelkonto_debitoren(self) -> str:
        return "1200"  # Forderungen aus LuL

    # =========================================================================
    # STEUERKONTEN (Klasse 1)
    # =========================================================================

    @property
    def vorsteuer_19(self) -> str:
        return "1406"  # Abziehbare Vorsteuer 19%

    @property
    def vorsteuer_7(self) -> str:
        return "1401"  # Abziehbare Vorsteuer 7%

    @property
    def umsatzsteuer_19(self) -> str:
        return "3806"  # Umsatzsteuer 19%

    @property
    def umsatzsteuer_7(self) -> str:
        return "3801"  # Umsatzsteuer 7%
