# -*- coding: utf-8 -*-
"""
SKR03 Kontenrahmen.

Standardkontenrahmen fuer Industrie und Handel.
Verwendung: Kleine und mittlere Unternehmen, Einzelunternehmen, GbR.

Gliederung:
- Klasse 0: Anlagevermoegen
- Klasse 1: Umlaufvermoegen, Finanzkonten
- Klasse 2: Ruecklagen, Verbindlichkeiten
- Klasse 3: Wareneingang
- Klasse 4: Aufwendungen
- Klasse 8: Erloese
- Klasse 9: Vortraege, Abschluss
"""

from typing import Dict, Optional

from .base import BaseKontenrahmen


class SKR03(BaseKontenrahmen):
    """
    SKR03 Kontenrahmen Implementierung.

    Der SKR03 ist der am haeufigsten verwendete Kontenrahmen in Deutschland.
    Er ist prozessorientiert aufgebaut (nach Geschaeftsvorfaellen).
    """

    @property
    def name(self) -> str:
        return "SKR03"

    @property
    def beschreibung(self) -> str:
        return "Standardkontenrahmen fuer Industrie und Handel (prozessorientiert)"

    # =========================================================================
    # AUFWANDSKONTEN (Klasse 3 und 4)
    # =========================================================================

    # Klasse 3: Wareneingang
    WARENEINGANG_19 = "3200"      # Wareneingang 19% Vorsteuer
    WARENEINGANG_7 = "3300"       # Wareneingang 7% Vorsteuer
    WARENEINGANG_EU_19 = "3425"   # Innergemeinschaftlicher Erwerb 19%
    WARENEINGANG_EU_7 = "3435"    # Innergemeinschaftlicher Erwerb 7%
    WARENEINGANG_DRITTLAND = "3550"  # Einfuhr Drittland

    # Klasse 4: Betriebsaufwendungen
    FREMDLEISTUNGEN = "4900"      # Fremdleistungen
    MIETE = "4210"                # Miete unbewegliche Wirtschaftsgueter
    NEBENKOSTEN = "4211"          # Nebenkosten Mietaufwendungen
    LEASING_PKW = "4570"          # Leasingkosten PKW
    LEASING_SONSTIGE = "4580"     # Sonstige Leasingkosten
    REISEKOSTEN = "4660"          # Reisekosten Unternehmer
    BEWIRTUNG = "4650"            # Bewirtungskosten
    WERBUNG = "4600"              # Werbekosten
    BUEROKOSTEN = "4930"          # Buerokosten
    TELEFON = "4920"              # Porto, Telefon
    VERSICHERUNGEN = "4360"       # Versicherungen
    RECHTSBERATUNG = "4950"       # Rechts- und Beratungskosten
    BUCHFUEHRUNG = "4955"         # Buchfuehrungskosten
    REPARATUREN = "4800"          # Reparatur und Instandhaltung
    KFZKOSTEN = "4500"            # Fahrzeugkosten
    KFZBETRIEB = "4510"           # Kfz-Betriebskosten
    ZINSEN = "2100"               # Zinsaufwendungen
    ABSCHREIBUNGEN = "4830"       # Abschreibungen Sachanlagen

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

    def get_expense_account(
        self,
        expense_type: str,
        vat_rate: Optional[float] = None
    ) -> str:
        expense_type = expense_type.lower().replace(" ", "_")

        # Spezialfall: Waren mit MwSt-Differenzierung
        if expense_type in ("waren", "wareneingang"):
            if vat_rate == 7:
                return self.WARENEINGANG_7
            return self.WARENEINGANG_19

        return self.expense_accounts.get(expense_type, self.WARENEINGANG_19)

    # =========================================================================
    # ERLOESKONTEN (Klasse 8)
    # =========================================================================

    ERLOESE_19 = "8400"           # Erloese 19% USt
    ERLOESE_7 = "8300"            # Erloese 7% USt
    ERLOESE_0 = "8100"            # Steuerfreie Umsaetze
    ERLOESE_EU = "8125"           # Innergemeinschaftliche Lieferungen
    ERLOESE_DRITTLAND = "8120"    # Ausfuhrlieferungen Drittland
    ERLOESE_RC = "8337"           # Erloese Reverse Charge
    ERLOESE_SONSTIGE = "8401"     # Sonstige Erloese

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

    def get_revenue_account(
        self,
        revenue_type: str,
        vat_rate: Optional[float] = None
    ) -> str:
        revenue_type = revenue_type.lower().replace(" ", "_")

        # Spezialfall: Differenzierung nach MwSt
        if revenue_type in ("waren", "dienstleistung"):
            if vat_rate == 7:
                return self.ERLOESE_7
            return self.ERLOESE_19

        return self.revenue_accounts.get(revenue_type, self.ERLOESE_19)

    # =========================================================================
    # PERSONENKONTEN
    # =========================================================================

    @property
    def default_creditor_account(self) -> str:
        return "70000"  # Erster Kreditor im Standardbereich

    @property
    def default_debtor_account(self) -> str:
        return "10000"  # Erster Debitor im Standardbereich

    @property
    def creditor_range_start(self) -> str:
        return "70000"

    @property
    def creditor_range_end(self) -> str:
        return "99999"

    @property
    def debtor_range_start(self) -> str:
        return "10000"

    @property
    def debtor_range_end(self) -> str:
        return "69999"

    # =========================================================================
    # SAMMELKONTEN
    # =========================================================================

    @property
    def sammelkonto_kreditoren(self) -> str:
        return "1600"  # Verbindlichkeiten aus LuL

    @property
    def sammelkonto_debitoren(self) -> str:
        return "1400"  # Forderungen aus LuL

    # =========================================================================
    # STEUERKONTEN
    # =========================================================================

    @property
    def vorsteuer_19(self) -> str:
        return "1576"  # Abziehbare Vorsteuer 19%

    @property
    def vorsteuer_7(self) -> str:
        return "1571"  # Abziehbare Vorsteuer 7%

    @property
    def umsatzsteuer_19(self) -> str:
        return "1776"  # Umsatzsteuer 19%

    @property
    def umsatzsteuer_7(self) -> str:
        return "1771"  # Umsatzsteuer 7%
