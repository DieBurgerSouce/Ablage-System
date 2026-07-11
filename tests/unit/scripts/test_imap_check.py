"""Tests fuer scripts/imap_check.py (AP-6 Go-Live-Runbook, IMAP-Postfach-Test).

Reine Funktionen: M365-Fallen-Erkennung (Basic-Auth-IMAP tot) und
Fehler-Hinweistexte — ohne echte IMAP-Verbindung.
"""

import os
import sys

import pytest

pytestmark = [pytest.mark.unit]


def _locate_scripts_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", "scripts"),
        "/app/scripts",
        os.path.join(os.getcwd(), "scripts"),
    ]
    for base in candidates:
        path = os.path.abspath(os.path.join(base, "imap_check.py"))
        if os.path.isfile(path):
            return os.path.dirname(path)
    return ""


_SCRIPTS_DIR = _locate_scripts_dir()

if not _SCRIPTS_DIR:
    pytest.skip(
        "imap_check.py nicht auffindbar - scripts/ ist in dieser "
        "Umgebung nicht gemountet (Infra-Setup, kein Test-Drift).",
        allow_module_level=True,
    )

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from imap_check import failure_hint, is_m365_host  # noqa: E402


def test_m365_hosts_werden_erkannt():
    assert is_m365_host("outlook.office365.com")
    assert is_m365_host("Outlook.Office365.com")
    assert is_m365_host("imap.outlook.com")
    assert not is_m365_host("imap.strato.de")
    assert not is_m365_host("mail.firmenich.de")


def test_login_fehler_auf_m365_nennt_die_oauth_falle():
    hint = failure_hint("outlook.office365.com", "AUTHENTICATE failed")
    assert "OAuth2" in hint
    assert "Basic" in hint or "Passwort" in hint


def test_login_fehler_auf_normalem_host_nennt_credentials():
    hint = failure_hint("imap.strato.de", "LOGIN failed")
    assert "OAuth2" not in hint
    assert "Zugangsdaten" in hint or "Passwort" in hint


def test_verbindungsfehler_nennt_netzwerk():
    hint = failure_hint("mail.firmenich.de", "timed out")
    assert "erreichbar" in hint or "Firewall" in hint or "Port" in hint
