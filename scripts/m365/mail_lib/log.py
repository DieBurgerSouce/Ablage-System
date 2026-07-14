# -*- coding: utf-8 -*-
"""Einfaches Logging: Datei unter <STAGING_ROOT>\\logs\\ (Fallback scripts\\m365\\logs\\) + Konsole.

Die Datei erhaelt DEBUG (jede Graph-Anfrage), die Konsole nur INFO+ (knapp auf stderr).
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# scripts\m365\  (Elternverzeichnis dieses Pakets) — Fallback-Log-Ort.
_M365_DIR = Path(__file__).resolve().parent.parent

_ROOT_NAME = "m365"
_configured = False


def _log_dir() -> Path:
    """Log-Verzeichnis: <STAGING_ROOT>\\logs\\ wenn moeglich, sonst scripts\\m365\\logs\\."""
    staging = os.environ.get("STAGING_ROOT")
    if staging:
        d = Path(staging) / "logs"
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            # SSD nicht angeschlossen o. ae. -> stiller Fallback unten.
            pass
    d = _M365_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def setup(staging_root: str | None = None, level: int = logging.INFO) -> Path:
    """Konfiguriert das Logging einmalig und liefert den Pfad der Logdatei.

    staging_root: falls gesetzt und STAGING_ROOT noch nicht in der Umgebung,
                  wird es gesetzt, damit Logdatei und Reports am selben Ort landen.
    level:        Konsolen-Schwelle (Datei ist immer DEBUG).
    """
    global _configured
    if staging_root and not os.environ.get("STAGING_ROOT"):
        os.environ["STAGING_ROOT"] = staging_root

    logfile = _log_dir() / f"m365_{datetime.now():%Y%m%d}.log"
    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(logging.DEBUG)

    if not _configured:
        fh = logging.FileHandler(logfile, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(levelname)-7s %(message)s"))
        root.addHandler(fh)
        root.addHandler(ch)
        root.propagate = False
        _configured = True
    return logfile


def get_logger(name: str) -> logging.Logger:
    """Liefert einen Kind-Logger.

    Konfiguriert NICHT selbst (kein Datei-/Verzeichnis-Nebeneffekt beim Import).
    Die Handler haengen am Wurzel-Logger 'm365' und werden von setup() gesetzt;
    Kind-Logger propagieren dorthin. Der Aufrufer (CLI) ruft setup() einmalig auf.
    """
    return logging.getLogger(_ROOT_NAME).getChild(name)
