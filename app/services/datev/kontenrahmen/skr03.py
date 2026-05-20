# -*- coding: utf-8 -*-
"""
SKR03 Kontenrahmen.

Standardkontenrahmen für Industrie und Handel.
Verwendung: Kleine und mittlere Unternehmen, Einzelunternehmen, GbR.

Gliederung:
- Klasse 0: Anlagevermoegen
- Klasse 1: Umlaufvermoegen, Finanzkonten
- Klasse 2: Rücklagen, Verbindlichkeiten
- Klasse 3: Wareneingang
- Klasse 4: Aufwendungen
- Klasse 8: Erloese
- Klasse 9: Vortraege, Abschluss
"""

from typing import Dict

from .base import BaseKontenrahmen


class SKR03(BaseKontenrahmen):
    """
    SKR03 Kontenrahmen Implementierung.

    Der SKR03 ist der am häufigsten verwendete Kontenrahmen in Deutschland.
    Er ist prozessorientiert aufgebaut (nach Geschäftsvorfaellen).
    """

    @property
    def name(self) -> str:
        return "SKR03"

    @property
    def beschreibung(self) -> str:
        return "Standardkontenrahmen für Industrie und Handel (prozessorientiert)"

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
    BUCHFUEHRUNG = "4955"         # Buchführungskosten
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
            "buchführung": self.BUCHFUEHRUNG,
            "reparatur": self.REPARATUREN,
            "kfz": self.KFZKOSTEN,
            "kfz_betrieb": self.KFZBETRIEB,
            "zinsen": self.ZINSEN,
            "abschreibung": self.ABSCHREIBUNGEN,
        }

    # Properties für Base-Klassen-Methoden (get_expense_account/get_revenue_account)
    @property
    def _wareneingang_19(self) -> str:
        return self.WARENEINGANG_19

    @property
    def _wareneingang_7(self) -> str:
        return self.WARENEINGANG_7

    # =========================================================================
    # ERLOESKONTEN (Klasse 8)
    # =========================================================================

    ERLOESE_19 = "8400"           # Erloese 19% USt
    ERLOESE_7 = "8300"            # Erloese 7% USt
    ERLOESE_0 = "8100"            # Steuerfreie Umsätze
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

    @property
    def _erloese_19(self) -> str:
        return self.ERLOESE_19

    @property
    def _erloese_7(self) -> str:
        return self.ERLOESE_7

    # =========================================================================
    # PERSONENKONTEN (Defaults aus BaseKontenrahmen übernommen)
    # =========================================================================
    # Kreditor-/Debitoren-Ranges sind identisch zu SKR04, daher in Base definiert

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
