# -*- coding: utf-8 -*-
"""Unit-Tests fuer scripts/import_wa_we.py (Neuausrichtung Phase 5).

Testet die reinen Parser-/Filter-Funktionen des WA/WE-Altbestand-Imports:
- Dateiname-Regex inkl. Umlaut-Monat ("März") und ASCII-Variante ("Maerz")
- Monatsletzter-Berechnung (inkl. Schaltjahr)
- Platzhalter-Filter (byte-identische 172643-Byte-Monats-PDFs)
- Verzeichnis-Scan mit Limit

Bewusst OHNE App-/DB-Imports lauffaehig (das Skript importiert app.* nur
lazy im --execute-Pfad).
"""

import os
import sys
from datetime import date
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]


def _locate_scripts_dir() -> str:
    """Finde scripts/ ueber mehrere Kandidaten-Pfade (Host + Container)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", "scripts"),
        "/app/scripts",
        os.path.join(os.getcwd(), "scripts"),
    ]
    for base in candidates:
        path = os.path.abspath(os.path.join(base, "import_wa_we.py"))
        if os.path.isfile(path):
            return os.path.dirname(path)
    return ""


_SCRIPTS_DIR = _locate_scripts_dir()

if not _SCRIPTS_DIR:
    pytest.skip(
        "import_wa_we.py nicht auffindbar - scripts/ ist in dieser "
        "Umgebung nicht gemountet (Infra-Setup, kein Test-Drift).",
        allow_module_level=True,
    )

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from import_wa_we import (  # noqa: E402
    PLACEHOLDER_SIZE_BYTES,
    is_placeholder_size,
    month_end,
    parse_wa_we_filename,
    scan_source_dirs,
)


class TestParseWaWeFilename:
    """Dateiname-Regex: WA/WE, deutsche Monate, Jahr."""

    def test_wa_wird_warenausgang(self):
        parsed = parse_wa_we_filename("Spargelmesser_WA_Januar_2010.pdf")
        assert parsed is not None
        assert parsed.beleg_typ == "warenausgang"
        assert parsed.year == 2010
        assert parsed.month == 1
        assert parsed.periode == "2010-01"

    def test_we_wird_wareneingang(self):
        parsed = parse_wa_we_filename("Spargelmesser_WE_Dezember_2026.pdf")
        assert parsed is not None
        assert parsed.beleg_typ == "wareneingang"
        assert parsed.periode == "2026-12"
        assert parsed.document_date == date(2026, 12, 31)

    def test_umlaut_monat_maerz(self):
        """Reale Dateien nutzen 'März' mit Umlaut (verifiziert am Bestand)."""
        parsed = parse_wa_we_filename("Spargelmesser_WA_März_2019.pdf")
        assert parsed is not None
        assert parsed.month == 3
        assert parsed.periode == "2019-03"
        assert parsed.document_date == date(2019, 3, 31)

    def test_ascii_variante_maerz_toleriert(self):
        parsed = parse_wa_we_filename("Spargelmesser_WE_Maerz_2012.pdf")
        assert parsed is not None
        assert parsed.month == 3
        assert parsed.beleg_typ == "wareneingang"

    def test_alle_zwoelf_monate(self):
        monate = [
            ("Januar", 1), ("Februar", 2), ("März", 3), ("April", 4),
            ("Mai", 5), ("Juni", 6), ("Juli", 7), ("August", 8),
            ("September", 9), ("Oktober", 10), ("November", 11),
            ("Dezember", 12),
        ]
        for name, nummer in monate:
            parsed = parse_wa_we_filename(f"Spargelmesser_WA_{name}_2015.pdf")
            assert parsed is not None, f"Monat {name} nicht erkannt"
            assert parsed.month == nummer

    @pytest.mark.parametrize(
        "filename",
        [
            "Spargelmesser_XX_Januar_2010.pdf",   # unbekanntes Kuerzel
            "Spargelmesser_WA_Januarr_2010.pdf",  # Tippfehler-Monat
            "Spargelmesser_WA_January_2010.pdf",  # englischer Monat
            "Spargelmesser_WA_Januar_10.pdf",     # 2-stelliges Jahr
            "Spargelmesser_WA_Januar_2010.PDF.exe",  # falsche Endung
            "Folie_WA_Januar_2010.pdf",           # falscher Praefix
            "Spargelmesser_WA_Januar_2010.txt",   # kein PDF
            "Spargelmesser_WA__2010.pdf",         # Monat fehlt
        ],
    )
    def test_nicht_passende_namen(self, filename):
        assert parse_wa_we_filename(filename) is None


class TestMonthEnd:
    """document_date = Monatsletzter."""

    def test_januar(self):
        assert month_end(2020, 1) == date(2020, 1, 31)

    def test_april_30(self):
        assert month_end(2021, 4) == date(2021, 4, 30)

    def test_februar_schaltjahr(self):
        assert month_end(2024, 2) == date(2024, 2, 29)

    def test_februar_kein_schaltjahr(self):
        assert month_end(2023, 2) == date(2023, 2, 28)

    def test_dezember(self):
        assert month_end(2008, 12) == date(2008, 12, 31)


class TestPlatzhalterFilter:
    """Leere Monats-PDFs sind byte-identisch 172643 Bytes gross."""

    def test_exakte_groesse_ist_platzhalter(self):
        assert is_placeholder_size(172643) is True
        assert PLACEHOLDER_SIZE_BYTES == 172643

    def test_andere_groessen_kein_platzhalter(self):
        assert is_placeholder_size(172642) is False
        assert is_placeholder_size(172644) is False
        assert is_placeholder_size(0) is False
        assert is_placeholder_size(2770912) is False


class TestScanSourceDirs:
    """Verzeichnis-Scan: Kategorisierung + Limit."""

    @pytest.fixture
    def quellordner(self, tmp_path: Path) -> Path:
        # 2 importierbare, 1 Platzhalter, 1 ignorierte Datei
        (tmp_path / "Spargelmesser_WA_Januar_2010.pdf").write_bytes(b"x" * 100)
        (tmp_path / "Spargelmesser_WE_März_2011.pdf").write_bytes(b"y" * 200)
        (tmp_path / "Spargelmesser_WA_Februar_2008.pdf").write_bytes(
            b"p" * PLACEHOLDER_SIZE_BYTES
        )
        (tmp_path / "Notizen.pdf").write_bytes(b"z")
        return tmp_path

    def test_kategorisierung(self, quellordner: Path):
        ergebnis = scan_source_dirs([str(quellordner)])
        assert len(ergebnis.importierbar) == 2
        assert len(ergebnis.platzhalter) == 1
        assert ergebnis.platzhalter[0].path.name == "Spargelmesser_WA_Februar_2008.pdf"
        assert len(ergebnis.ignoriert) == 1
        assert ergebnis.ignoriert[0].name == "Notizen.pdf"

    def test_limit_greift_nur_auf_importierbare(self, quellordner: Path):
        ergebnis = scan_source_dirs([str(quellordner)], limit=1)
        assert len(ergebnis.importierbar) == 1
        # Platzhalter/ignoriert werden weiterhin vollstaendig protokolliert
        assert len(ergebnis.platzhalter) == 1
        assert len(ergebnis.ignoriert) == 1

    def test_fehlender_ordner_wird_uebersprungen(self, tmp_path: Path, capsys):
        ergebnis = scan_source_dirs([str(tmp_path / "gibt_es_nicht")])
        assert ergebnis.importierbar == []
        assert "Quellordner fehlt" in capsys.readouterr().out
