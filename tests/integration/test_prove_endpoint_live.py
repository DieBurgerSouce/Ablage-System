# -*- coding: utf-8 -*-
"""Trust-Theater K1 (2026-07-12): Live-Tests für die Beweisführung.

POST /integrity/documents/{id}/prove lädt das Original serverseitig aus dem
Storage, hasht neu und prüft Baseline + Beweiskette + Zeitstempel — ohne
Datei-Upload. Läuft wie test_annotations_endpoint_live.py gegen ein
LIVE-Backend und skippt sauber, wenn keins erreichbar ist.

Wichtig: Diese Tests sind read-only-freundlich — sie beweisen grün bzw.
no_baseline, aber manipulieren NIEMALS das echte Archiv (Negativ-Beweis
liegt isoliert in tests/unit/test_prove_integrity_logic.py, weil die
gobd_audit_chain unlöschbar ist und ein Live-Rot die Kette dauerhaft
verschmutzen würde).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request as _u
import uuid

import pytest

BASE = os.environ.get("AZ_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
EMAIL = os.environ.get("AZ_ADMIN_EMAIL", "admin@localhost.com")
PASSWORD = os.environ.get("AZ_ADMIN_PASSWORD", "admin123")
TIMEOUT = int(os.environ.get("AZ_HTTP_TIMEOUT", "120"))


def _request(method: str, url: str, headers: dict | None = None):
    req = _u.Request(url, headers=headers or {}, method=method)
    try:
        with _u.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception:
        return -1, b""


def _login() -> str | None:
    body = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    req = _u.Request(
        f"{BASE}/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with _u.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read()).get("access_token")
    except Exception:
        return None


@pytest.fixture(scope="module")
def token() -> str:
    status, _ = _request("GET", f"{BASE}/openapi.json")
    if status < 0:
        pytest.skip(f"Kein Live-Backend unter {BASE} erreichbar")
    tok = _login()
    if not tok:
        pytest.skip("Login fehlgeschlagen (Rate-Limit?/Seed?) - Live-Test uebersprungen")
    return tok


@pytest.fixture(scope="module")
def erstes_dokument(token: str) -> str:
    headers = {"Authorization": f"Bearer {token}"}
    status, body = _request("GET", f"{BASE}/api/v1/documents/?page=1&page_size=1", headers)
    if status != 200:
        pytest.skip(f"Dokumentliste nicht abrufbar ({status})")
    docs = json.loads(body).get("documents", [])
    if not docs:
        pytest.skip("Keine Dokumente in der Firma des Test-Users")
    return docs[0]["id"]


def test_prove_liefert_differenzierten_beweis(token: str, erstes_dokument: str):
    """200 + differenzierte Antwort; ein sauberes Archiv ist nie 'tampered'."""
    headers = {"Authorization": f"Bearer {token}"}
    status, body = _request(
        "POST", f"{BASE}/api/v1/integrity/documents/{erstes_dokument}/prove", headers
    )
    assert status == 200, f"prove liefert {status}: {body[:300]!r}"

    proof = json.loads(body)
    # Pflichtfelder des differenzierten Beweises
    for feld in (
        "verdict", "file_hash_matches", "baseline_source", "chain", "tsa",
        "verified_at", "message_de", "hash_algorithm",
    ):
        assert feld in proof, f"Feld {feld} fehlt in der Beweis-Antwort"

    assert proof["verdict"] in ("verified", "no_baseline"), (
        "ALARM: Das Live-Archiv meldet Manipulation ('tampered') — "
        f"sofort untersuchen! Antwort: {json.dumps(proof)[:500]}"
    )
    assert proof["hash_algorithm"] == "sha256"
    # Deutsche, verständliche Meldung
    assert proof["message_de"], "message_de darf nicht leer sein"

    if proof["verdict"] == "verified":
        assert proof["file_hash_matches"] is True
        assert proof["stored_hash"] == proof["computed_hash"]
        assert proof["baseline_source"] in ("archiv", "integritaets_hash")
        assert proof["chain"]["valid"] in (True, None)
    else:
        assert proof["file_hash_matches"] is None
        assert proof["baseline_source"] is None


def test_prove_unbekanntes_dokument_404(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    status, body = _request(
        "POST", f"{BASE}/api/v1/integrity/documents/{uuid.uuid4()}/prove", headers
    )
    assert status == 404, f"Erwartet 404 für fremde/unbekannte Dokumente, war {status}"


def test_prove_ohne_auth_verweigert(erstes_dokument: str):
    """Ohne Token kein Beweis: 401 oder 403 (FastAPI-HTTPBearer-Konvention)."""
    status, _ = _request(
        "POST", f"{BASE}/api/v1/integrity/documents/{erstes_dokument}/prove"
    )
    assert status in (401, 403), f"Erwartet 401/403 ohne Token, war {status}"
