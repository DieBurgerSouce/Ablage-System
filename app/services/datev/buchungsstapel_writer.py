# -*- coding: utf-8 -*-
"""
DATEV Buchungsstapel CSV Writer.

Erzeugt DATEV-konforme CSV-Dateien im Buchungsstapel-Format (Version 700).

Spezifikation:
- Encoding: CP1252 (Windows-1252, ANSI)
- Trennzeichen: Semikolon
- Dezimaltrennzeichen: Komma
- Datumsformat: DDMM (4-stellig, ohne Punkte)
- Header: 2 Zeilen (Metadaten + Spaltenkoepfe)
- 116 Spalten pro Buchungszeile
"""

import io
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

import structlog

from app.db import models
from app.core.safe_errors import safe_error_log
from .constants import (
    BUCHUNGSSTAPEL_COLUMN_COUNT,
    BUCHUNGSSTAPEL_COLUMNS,
    DATEV_CATEGORY,
    DATEV_DATE_FORMAT,
    DATEV_DECIMAL_SEP,
    DATEV_DELIMITER,
    DATEV_ENCODING,
    DATEV_FORMAT_HEADER,
    DATEV_FORMAT_NAME,
    DATEV_FORMAT_VERSION,
    DATEV_NEWLINE,
    DATEV_QUOTE_CHAR,
    DATEV_VERSION,
)
from .mapping.invoice_mapper import DATEVBuchung

# HIGH-8 FIX: CSV-Größenlimit
# DATEV akzeptiert praktisch max. ~100MB, größere Dateien werden oft abgelehnt
MAX_CSV_SIZE_BYTES = 100_000_000  # 100 MB

logger = structlog.get_logger(__name__)


class BuchungsstapelWriter:
    """
    DATEV Buchungsstapel CSV Writer.

    Erzeugt eine DATEV-kompatible CSV-Datei aus einer Liste von Buchungssätzen.

    Verwendung:
        writer = BuchungsstapelWriter()
        csv_bytes = writer.write(
            buchungen=[buchung1, buchung2, ...],
            config=datev_config,
            export_date=datetime.now()
        )
        # csv_bytes ist im CP1252 Encoding
    """

    def write(
        self,
        buchungen: List[DATEVBuchung],
        config: models.DATEVConfiguration,
        export_date: Optional[datetime] = None,
    ) -> bytes:
        """
        Schreibt Buchungsstapel als DATEV-CSV.

        Args:
            buchungen: Liste der Buchungssätze
            config: DATEV-Konfiguration
            export_date: Export-Zeitstempel (Default: jetzt)

        Returns:
            CSV-Datei als Bytes in CP1252 Encoding
        """
        if export_date is None:
            export_date = datetime.now()

        lines: List[str] = []

        # Zeile 1: Header (Metadaten)
        lines.append(self._write_header_line(config, export_date, len(buchungen)))

        # Zeile 2: Spaltenkoepfe
        lines.append(self._write_column_headers())

        # Zeile 3+: Buchungssätze
        for buchung in buchungen:
            lines.append(self._write_buchung_line(buchung, config))

        # Zusammenfuegen mit CRLF
        content = DATEV_NEWLINE.join(lines)

        # In CP1252 encodieren
        # MEDIUM-8 FIX: errors='strict' statt 'replace'
        # 'replace' erzeugt stille Datenkorrumpierung (? statt Sonderzeichen)
        # die DATEV-Import fehlschlagen laesst ohne Benutzerhinweis
        try:
            csv_bytes = content.encode(DATEV_ENCODING, errors="strict")
        except UnicodeEncodeError as e:
            # Problematisches Zeichen identifizieren und hilfreiche Fehlermeldung
            problem_char = e.object[e.start:e.end]
            logger.error(
                "datev_encoding_error",
                **safe_error_log(e),
                problem_char=repr(problem_char),
                position=e.start,
            )
            raise ValueError(
                f"Zeichen '{problem_char}' (Position {e.start}) kann nicht in DATEV-Format "
                f"(CP1252) kodiert werden. Bitte entfernen Sie Sonderzeichen aus den "
                f"Rechnungsdaten oder ersetzen Sie sie durch ASCII-kompatible Zeichen."
            ) from e
        except Exception as e:
            logger.error("datev_encoding_unexpected_error", **safe_error_log(e))
            raise ValueError(
                f"Unerwarteter Fehler beim Kodieren der DATEV-Datei: {type(e).__name__}"
            ) from e

        # HIGH-8 FIX: CSV-Größenlimit prüfen
        # DATEV akzeptiert praktisch max. ~100MB
        if len(csv_bytes) > MAX_CSV_SIZE_BYTES:
            size_mb = len(csv_bytes) / 1024 / 1024
            max_mb = MAX_CSV_SIZE_BYTES / 1024 / 1024
            logger.error(
                "datev_csv_too_large",
                size_bytes=len(csv_bytes),
                size_mb=size_mb,
                max_bytes=MAX_CSV_SIZE_BYTES,
                buchungen_count=len(buchungen),
            )
            raise ValueError(
                f"CSV-Datei zu gross ({size_mb:.1f} MB). "
                f"DATEV akzeptiert maximal {max_mb:.0f} MB. "
                f"Bitte exportieren Sie kleinere Zeitraeume oder weniger Dokumente."
            )

        return csv_bytes

    def _write_header_line(
        self,
        config: models.DATEVConfiguration,
        export_date: datetime,
        entry_count: int,
    ) -> str:
        """
        Schreibt DATEV Header-Zeile (Zeile 1).

        Format (27 Felder):
        "EXTF";700;21;"Buchungsstapel";7;YYYYMMDDHHMMSS000;
        "Berater";"Mandant";WJ-Beginn;Sachkontenlänge;;;Währung;...
        """
        # Zeitstempel: YYYYMMDDHHMMSS + 3 Ziffern
        timestamp = export_date.strftime("%Y%m%d%H%M%S") + "000"

        # WJ-Beginn als YYYYMMDD
        wj_beginn = config.wj_beginn.strftime("%Y%m%d")

        # Header-Felder (32 Felder gemäß DATEV Version 700)
        header_fields = [
            self._quote(DATEV_FORMAT_HEADER),   # 1: "EXTF"
            str(DATEV_VERSION),                  # 2: 700
            str(DATEV_CATEGORY),                 # 3: 21 (Buchungsstapel)
            self._quote(DATEV_FORMAT_NAME),      # 4: "Buchungsstapel"
            str(DATEV_FORMAT_VERSION),           # 5: 7
            timestamp,                           # 6: Zeitstempel
            "",                                  # 7: reserviert
            "",                                  # 8: reserviert
            "",                                  # 9: reserviert
            self._quote(config.berater_nr),      # 10: Beraternummer
            self._quote(config.mandanten_nr),    # 11: Mandantennummer
            wj_beginn,                           # 12: WJ-Beginn
            str(config.sachkontenlange),         # 13: Sachkontenlänge
            "",                                  # 14: Datum von (optional)
            "",                                  # 15: Datum bis (optional)
            "",                                  # 16: Bezeichnung (optional)
            "",                                  # 17: Diktatkürzel (optional)
            "0",                                 # 18: Buchungstyp (0=Fibu)
            "0",                                 # 19: Rechnungslegungszweck
            "",                                  # 20: reserviert
            "",                                  # 21: reserviert
            "",                                  # 22: Anwendungsinfo
            "",                                  # 23: reserviert
            "",                                  # 24: reserviert
            "",                                  # 25: reserviert
            self._quote("EUR"),                  # 26: Währung
            "",                                  # 27: reserviert
            "",                                  # 28: Herkunfts-Kennung (leer)
            "",                                  # 29: reserviert
            "",                                  # 30: reserviert
            "",                                  # 31: reserviert
            "",                                  # 32: Versionsnummer (leer)
        ]

        return DATEV_DELIMITER.join(header_fields)

    def _write_column_headers(self) -> str:
        """
        Schreibt Spaltenkoepfe (Zeile 2).

        Die Spaltenkoepfe müssen in Anführungszeichen stehen.
        """
        quoted_headers = [self._quote(col) for col in BUCHUNGSSTAPEL_COLUMNS]
        return DATEV_DELIMITER.join(quoted_headers)

    def _write_buchung_line(
        self,
        buchung: DATEVBuchung,
        config: models.DATEVConfiguration
    ) -> str:
        """
        Schreibt eine Buchungszeile (116 Felder).

        Die meisten Felder sind leer, nur die relevanten werden befuellt.
        """
        # Initialisiere alle 116 Felder als leer
        fields = [""] * BUCHUNGSSTAPEL_COLUMN_COUNT

        # Feld 1: Umsatz (Betrag, positiv, mit Komma als Dezimaltrenner)
        fields[0] = self._format_amount(buchung.umsatz)

        # Feld 2: Soll/Haben-Kennzeichen
        fields[1] = self._quote(buchung.soll_haben)

        # Feld 3: WKZ Umsatz (Währung)
        fields[2] = self._quote(buchung.wkz_umsatz)

        # Feld 4: Kurs (Wechselkurs, optional)
        if buchung.kurs:
            fields[3] = self._format_amount(buchung.kurs)

        # Feld 7: Konto (Sachkonto)
        fields[6] = buchung.konto

        # Feld 8: Gegenkonto
        fields[7] = buchung.gegenkonto

        # Feld 9: BU-Schluessel (Steuerschluessel)
        if buchung.bu_schluessel:
            fields[8] = buchung.bu_schluessel

        # Feld 10: Belegdatum (DDMM)
        fields[9] = self._format_date(buchung.belegdatum)

        # Feld 11: Belegfeld 1 (Rechnungsnummer)
        # MEDIUM-12 FIX: Belegfeld-Werte normalisieren (Whitespace entfernen)
        belegfeld_1 = self._normalize_belegfeld(buchung.belegfeld_1, max_len=36)
        fields[10] = self._quote(belegfeld_1 or "OHNE-NR")

        # Feld 12: Belegfeld 2 (optional)
        belegfeld_2 = self._normalize_belegfeld(buchung.belegfeld_2, max_len=12)
        if belegfeld_2:
            fields[11] = self._quote(belegfeld_2)

        # Feld 13: Skonto (optional)
        if buchung.skonto:
            fields[12] = self._format_amount(buchung.skonto)

        # Feld 14: Buchungstext
        fields[13] = self._quote(buchung.buchungstext[:60])

        # Feld 37: KOST1 - Kostenstelle (optional)
        if buchung.kostenstelle_1:
            fields[36] = self._quote(buchung.kostenstelle_1[:20])

        # Feld 38: KOST2 - Kostenstelle (optional)
        if buchung.kostenstelle_2:
            fields[37] = self._quote(buchung.kostenstelle_2[:20])

        return DATEV_DELIMITER.join(fields)

    def _format_amount(self, amount: Decimal) -> str:
        """
        Formatiert Betrag mit Komma als Dezimaltrennzeichen.

        DATEV erwartet:
        - Positiver Betrag
        - Komma als Dezimaltrenner
        - 2 Nachkommastellen
        """
        # Auf 2 Dezimalstellen runden
        rounded = round(abs(amount), 2)
        # Punkt durch Komma ersetzen
        formatted = f"{rounded:.2f}".replace(".", DATEV_DECIMAL_SEP)
        return formatted

    def _format_date(self, d: date) -> str:
        """
        Formatiert Datum als DDMM (4-stellig, ohne Jahr).

        DATEV verwendet das Jahr aus dem Header (WJ-Beginn).
        """
        return d.strftime(DATEV_DATE_FORMAT)

    def _normalize_belegfeld(
        self,
        value: Optional[str],
        max_len: int
    ) -> Optional[str]:
        """
        Normalisiert Belegfeld-Werte.

        MEDIUM-12 FIX:
        - Entfernt führende/folgende Whitespace
        - Ersetzt mehrfache Leerzeichen durch einzelne
        - Gibt None zurück bei leeren/whitespace-only Werten
        - Kürzt auf max_len
        """
        if not value:
            return None

        # Whitespace normalisieren
        normalized = " ".join(value.split())

        # Leer nach Normalisierung?
        if not normalized:
            return None

        # Auf maximale Länge kürzen
        return normalized[:max_len]

    def _quote(self, value: str) -> str:
        """
        Setzt Text in Anführungszeichen.

        Entfernt vorhandene Anführungszeichen und Semikolons.
        """
        if not value:
            return '""'
        # Entferne problematische Zeichen
        cleaned = value.replace(DATEV_QUOTE_CHAR, "").replace(DATEV_DELIMITER, " ")
        return f'{DATEV_QUOTE_CHAR}{cleaned}{DATEV_QUOTE_CHAR}'


def create_buchungsstapel_writer() -> BuchungsstapelWriter:
    """Factory-Funktion für BuchungsstapelWriter."""
    return BuchungsstapelWriter()
