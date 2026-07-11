# -*- coding: utf-8 -*-
"""Konfiguration der M365-Extraktion — laedt .env.m365 (eigener KEY=VALUE-Parser).

Aufloesungsreihenfolge der .env.m365:
  1. Umgebungsvariable M365_ENV_FILE (expliziter Pfad)
  2. <STAGING_ROOT>\\secrets\\.env.m365   (STAGING_ROOT aus der OS-Umgebung)
  3. scripts\\m365\\.env.m365             (neben diesem Paket)

Bewusst ohne Fremd-Bibliothek (kein python-dotenv). Fehlt etwas, wird mit einer
klaren deutschen Meldung + Verweis auf das Runbook abgebrochen (Fail-fast).
"""

from __future__ import annotations

import os
from pathlib import Path

RUNBOOK = "RUNBOOK_P0_BEN.md"

# scripts\m365\  (Elternverzeichnis dieses Pakets).
_M365_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Fehlende/unvollstaendige M365-Konfiguration."""


def _parse_env_file(path: Path) -> dict[str, str]:
    """Liest KEY=VALUE-Zeilen; ignoriert Leerzeilen und #-Kommentare.

    Erlaubt fuehrendes 'export ' und Werte in "..." oder '...'.
    """
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        if key:
            data[key] = val
    return data


def _find_env_file() -> Path | None:
    """Sucht die .env.m365 gemaess der dokumentierten Reihenfolge."""
    explicit = os.environ.get("M365_ENV_FILE")
    if explicit:
        return Path(explicit)
    staging = os.environ.get("STAGING_ROOT")
    if staging:
        cand = Path(staging) / "secrets" / ".env.m365"
        if cand.is_file():
            return cand
    cand = _M365_DIR / ".env.m365"
    if cand.is_file():
        return cand
    return None


class Config:
    """Aufgeloeste M365-Zugangsdaten und Pfade."""

    def __init__(self, values: dict[str, str], source: Path | None):
        self.source = source

        def g(key: str) -> str:
            # Datei-Wert hat Vorrang, OS-Umgebung als Rueckfall.
            return (values.get(key) or os.environ.get(key) or "").strip()

        self.tenant_id = g("M365_TENANT_ID")
        self.client_id = g("M365_CLIENT_ID")
        self.client_secret = g("M365_CLIENT_SECRET")
        self.cert_path = g("M365_CERT_PATH")
        self.cert_thumbprint = g("M365_CERT_THUMBPRINT")
        self.staging_root = g("STAGING_ROOT")

    @property
    def use_cert(self) -> bool:
        return bool(self.cert_path and self.cert_thumbprint)

    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    def staging_path(self) -> Path | None:
        return Path(self.staging_root) if self.staging_root else None

    def summary(self) -> str:
        """Kurzfassung fuers Log — Secrets werden maskiert."""
        modus = "Zertifikat" if self.use_cert else ("Secret" if self.client_secret else "KEINE")
        return (
            f"Tenant={_mask(self.tenant_id)} Client={_mask(self.client_id)} "
            f"Anmeldung={modus} Staging={self.staging_root or '(nicht gesetzt)'}"
        )


def _mask(value: str) -> str:
    if not value:
        return "(leer)"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def _validate(cfg: Config, env_path: Path | None) -> None:
    if cfg.source:
        where = f"geladen aus {cfg.source}"
    elif env_path:
        where = f"NICHT gefunden (zuletzt gesucht: {env_path})"
    else:
        where = "NICHT gefunden (weder M365_ENV_FILE, noch <STAGING_ROOT>\\secrets\\, noch scripts\\m365\\)"

    problems: list[str] = []
    missing = [n for n, v in (("M365_TENANT_ID", cfg.tenant_id), ("M365_CLIENT_ID", cfg.client_id)) if not v]
    if missing:
        problems.append("Fehlende Pflichtwerte: " + ", ".join(missing))
    if not cfg.use_cert and not cfg.client_secret:
        problems.append(
            "Keine Anmeldeinformationen: entweder M365_CERT_PATH + M365_CERT_THUMBPRINT "
            "(Zertifikat, empfohlen) ODER M365_CLIENT_SECRET setzen."
        )
    if cfg.cert_path and cfg.cert_thumbprint and not Path(cfg.cert_path).is_file():
        problems.append(f"Zertifikatsdatei nicht gefunden: {cfg.cert_path}")

    if problems:
        raise ConfigError(
            "M365-Konfiguration unvollstaendig.\n"
            f"  .env.m365: {where}\n"
            + "".join(f"  - {p}\n" for p in problems)
            + "\nBitte .env.m365 aus .env.m365.example erzeugen und befuellen.\n"
            f"Schritt-fuer-Schritt-Anleitung: {RUNBOOK} (Abschnitte 2, 3, 6)."
        )


def load() -> Config:
    """Laedt und validiert die Konfiguration (Fail-fast bei fehlenden Zugangsdaten)."""
    env_path = _find_env_file()
    values = _parse_env_file(env_path) if (env_path and env_path.is_file()) else {}
    source = env_path if (env_path and env_path.is_file()) else None
    cfg = Config(values, source)
    _validate(cfg, env_path)
    return cfg
