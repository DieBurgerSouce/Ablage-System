# -*- coding: utf-8 -*-
"""
DATEV Format Konstanten.

Definiert die Struktur des DATEV Buchungsstapel-Formats (Version 700).
Referenz: DATEV Schnittstellen-Entwicklungsleitfaden
"""

# =============================================================================
# DATEV HEADER KONSTANTEN
# =============================================================================

# Format-Kennung
DATEV_FORMAT_HEADER = "EXTF"     # Externes Format
DATEV_VERSION = 700              # Format-Version (aktuell 700)
DATEV_CATEGORY = 21              # Kategorie: Buchungsstapel
DATEV_FORMAT_NAME = "Buchungsstapel"
DATEV_FORMAT_VERSION = 7         # Datenformat-Version

# Buchungsstapel hat 116 Spalten (Version 700)
BUCHUNGSSTAPEL_COLUMN_COUNT = 116


# =============================================================================
# SPALTENSTRUKTUR (Version 700, 116 Felder)
# =============================================================================

# Die ersten 14 Felder sind die wichtigsten
BUCHUNGSSTAPEL_COLUMNS = [
    # Feld 1-10
    "Umsatz (ohne Soll/Haben-Kz)",      # 1: Betrag (positiv)
    "Soll/Haben-Kennzeichen",            # 2: S oder H
    "WKZ Umsatz",                        # 3: Währungscode
    "Kurs",                              # 4: Wechselkurs (optional)
    "Basis-Umsatz",                      # 5: Basis bei Fremdwährung
    "WKZ Basis-Umsatz",                  # 6: Währungscode Basis
    "Konto",                             # 7: Sachkonto
    "Gegenkonto (ohne BU-Schlüssel)",    # 8: Gegenkonto
    "BU-Schlüssel",                      # 9: Steuerschluessel
    "Belegdatum",                        # 10: DDMM Format

    # Feld 11-20
    "Belegfeld 1",                       # 11: Rechnungsnummer
    "Belegfeld 2",                       # 12: Zusatzinfo
    "Skonto",                            # 13: Skonto-Betrag
    "Buchungstext",                      # 14: 60 Zeichen max

    "Postensperre",                      # 15
    "Diverse Adressnummer",              # 16
    "Geschäftspartnerbank",              # 17
    "Sachverhalt",                       # 18
    "Zinssperre",                        # 19
    "Beleglink",                         # 20

    # Feld 21-30
    "Beleginfo - Art 1",                 # 21
    "Beleginfo - Inhalt 1",              # 22
    "Beleginfo - Art 2",                 # 23
    "Beleginfo - Inhalt 2",              # 24
    "Beleginfo - Art 3",                 # 25
    "Beleginfo - Inhalt 3",              # 26
    "Beleginfo - Art 4",                 # 27
    "Beleginfo - Inhalt 4",              # 28
    "Beleginfo - Art 5",                 # 29
    "Beleginfo - Inhalt 5",              # 30

    # Feld 31-40
    "Beleginfo - Art 6",                 # 31
    "Beleginfo - Inhalt 6",              # 32
    "Beleginfo - Art 7",                 # 33
    "Beleginfo - Inhalt 7",              # 34
    "Beleginfo - Art 8",                 # 35
    "Beleginfo - Inhalt 8",              # 36
    "KOST1 - Kostenstelle",              # 37
    "KOST2 - Kostenstelle",              # 38
    "Kost-Menge",                        # 39
    "EU-Land u. UStID",                  # 40

    # Feld 41-50
    "EU-Steuersatz",                     # 41
    "Abw. Versteuerungsart",             # 42
    "Sachverhalt L+L",                   # 43
    "Funktionsergänzung L+L",            # 44
    "BU 49 Hauptfunktionstyp",           # 45
    "BU 49 Hauptfunktionsnummer",        # 46
    "BU 49 Funktionsergänzung",          # 47
    "Zusatzinformation - Art 1",         # 48
    "Zusatzinformation - Inhalt 1",      # 49
    "Zusatzinformation - Art 2",         # 50

    # Feld 51-60
    "Zusatzinformation - Inhalt 2",      # 51
    "Zusatzinformation - Art 3",         # 52
    "Zusatzinformation - Inhalt 3",      # 53
    "Zusatzinformation - Art 4",         # 54
    "Zusatzinformation - Inhalt 4",      # 55
    "Zusatzinformation - Art 5",         # 56
    "Zusatzinformation - Inhalt 5",      # 57
    "Zusatzinformation - Art 6",         # 58
    "Zusatzinformation - Inhalt 6",      # 59
    "Zusatzinformation - Art 7",         # 60

    # Feld 61-70
    "Zusatzinformation - Inhalt 7",      # 61
    "Zusatzinformation - Art 8",         # 62
    "Zusatzinformation - Inhalt 8",      # 63
    "Zusatzinformation - Art 9",         # 64
    "Zusatzinformation - Inhalt 9",      # 65
    "Zusatzinformation - Art 10",        # 66
    "Zusatzinformation - Inhalt 10",     # 67
    "Zusatzinformation - Art 11",        # 68
    "Zusatzinformation - Inhalt 11",     # 69
    "Zusatzinformation - Art 12",        # 70

    # Feld 71-80
    "Zusatzinformation - Inhalt 12",     # 71
    "Zusatzinformation - Art 13",        # 72
    "Zusatzinformation - Inhalt 13",     # 73
    "Zusatzinformation - Art 14",        # 74
    "Zusatzinformation - Inhalt 14",     # 75
    "Zusatzinformation - Art 15",        # 76
    "Zusatzinformation - Inhalt 15",     # 77
    "Zusatzinformation - Art 16",        # 78
    "Zusatzinformation - Inhalt 16",     # 79
    "Zusatzinformation - Art 17",        # 80

    # Feld 81-90
    "Zusatzinformation - Inhalt 17",     # 81
    "Zusatzinformation - Art 18",        # 82
    "Zusatzinformation - Inhalt 18",     # 83
    "Zusatzinformation - Art 19",        # 84
    "Zusatzinformation - Inhalt 19",     # 85
    "Zusatzinformation - Art 20",        # 86
    "Zusatzinformation - Inhalt 20",     # 87
    "Stück",                             # 88
    "Gewicht",                           # 89
    "Zahlweise",                         # 90

    # Feld 91-100
    "Forderungsart",                     # 91
    "Veranlagungsjahr",                  # 92
    "Zugeordnete Fälligkeit",            # 93
    "Skontotyp",                         # 94
    "Auftragsnummer",                    # 95
    "Buchungstyp",                       # 96
    "USt-Schlüssel (Anzahlungen)",       # 97
    "EU-Land (Anzahlungen)",             # 98
    "Sachverhalt L+L (Anzahlungen)",     # 99
    "EU-Steuersatz (Anzahlungen)",       # 100

    # Feld 101-110
    "Erlöskonto (Anzahlungen)",          # 101
    "Herkunft-Kz",                       # 102
    "Buchungs GUID",                     # 103
    "KOST-Datum",                        # 104
    "SEPA-Mandatsreferenz",              # 105
    "Skontosperre",                      # 106
    "Gesellschaftername",                # 107
    "Beteiligtennummer",                 # 108
    "Identifikationsnummer",             # 109
    "Zeichnernummer",                    # 110

    # Feld 111-116
    "Postensperre bis",                  # 111
    "Bezeichnung SoBil-Sachverhalt",     # 112
    "Kennzeichen SoBil-Buchung",         # 113
    "Festschreibung",                    # 114
    "Leistungsdatum",                    # 115
    "Datum Zuord. Steuerperiode",        # 116
]


# =============================================================================
# FELDLAENGEN UND VALIDIERUNG
# =============================================================================

FIELD_MAX_LENGTHS = {
    "belegfeld_1": 36,      # Rechnungsnummer
    "belegfeld_2": 12,      # Zusatzinfo
    "buchungstext": 60,     # Buchungstext
    "konto": 8,             # Kontonummer (4-8 Stellen je nach Config)
    "gegenkonto": 8,        # Gegenkonto
    "bu_schluessel": 4,     # BU-Schluessel
    "kostenstelle": 20,     # Kostenstelle
    "kostenträger": 20,    # Kostenträger
    "währung": 3,          # ISO-Währungscode
}


# =============================================================================
# ENCODING UND FORMAT
# =============================================================================

DATEV_ENCODING = "cp1252"        # Windows-1252 (ANSI)
DATEV_DELIMITER = ";"            # Semikolon als Trennzeichen
DATEV_DECIMAL_SEP = ","          # Komma als Dezimaltrenner
DATEV_NEWLINE = "\r\n"           # Windows-Zeilenumbruch
DATEV_DATE_FORMAT = "%d%m"       # DDMM ohne Punkte
DATEV_QUOTE_CHAR = '"'           # Textfelder in Anführungszeichen


# =============================================================================
# EU-MITGLIEDSTAATEN (ISO 3166-1 alpha-2)
# =============================================================================

# Alle 27 EU-Mitgliedstaaten (Stand: 2025)
# Verwendet für: Innergemeinschaftliche Lieferungen, Reverse Charge, etc.
EU_MEMBER_STATES: frozenset[str] = frozenset({
    "AT",  # Oesterreich
    "BE",  # Belgien
    "BG",  # Bulgarien
    "CY",  # Zypern
    "CZ",  # Tschechien
    "DE",  # Deutschland
    "DK",  # Daenemark
    "EE",  # Estland
    "ES",  # Spanien
    "FI",  # Finnland
    "FR",  # Frankreich
    "GR",  # Griechenland
    "HR",  # Kroatien
    "HU",  # Ungarn
    "IE",  # Irland
    "IT",  # Italien
    "LT",  # Litauen
    "LU",  # Luxemburg
    "LV",  # Lettland
    "MT",  # Malta
    "NL",  # Niederlande
    "PL",  # Polen
    "PT",  # Portugal
    "RO",  # Rumaenien
    "SE",  # Schweden
    "SI",  # Slowenien
    "SK",  # Slowakei
})


def is_eu_country(country_code: str) -> bool:
    """
    Prüft ob ein Land EU-Mitglied ist.

    Args:
        country_code: ISO 3166-1 alpha-2 Ländercode (z.B. "DE", "AT")

    Returns:
        True wenn EU-Mitglied, False sonst
    """
    if not country_code:
        return False
    return country_code.upper() in EU_MEMBER_STATES


def is_third_country(country_code: str) -> bool:
    """
    Prüft ob ein Land ein Drittland (nicht EU) ist.

    Args:
        country_code: ISO 3166-1 alpha-2 Ländercode

    Returns:
        True wenn Drittland, False wenn EU-Mitglied oder leer
    """
    if not country_code:
        return False
    return country_code.upper() not in EU_MEMBER_STATES
