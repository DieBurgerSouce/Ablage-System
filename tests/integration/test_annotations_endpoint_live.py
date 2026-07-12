# -*- coding: utf-8 -*-
"""Regressionstest F-P2-009 (Perception-Audit 2026-07-12).

Der Annotations-Router behandelte current_user als dict (current_user["id"],
current_user["company_id"]) — get_current_user liefert aber ein User-ORM-
Objekt, und User hat gar KEIN company_id-Attribut (kommt aus UserCompany via
get_user_company_id_dep). Folge: JEDER Annotations-Aufruf crashte mit
TypeError -> HTTP 500 — auf der Dokument-Detailseite als roter
„Server-Fehler"-Toast für jeden Nutzer sichtbar (Walk-Evidenz iter02).

Läuft wie test_get_endpoints_no_500 gegen ein LIVE-Backend und skippt sauber,
wenn keins erreichbar ist. Der Pfad hat einen Parameter und war deshalb nie
vom parameterlosen F-31-Sweep abgedeckt.
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
TIMEOUT = int(os.environ.get("AZ_HTTP_TIMEOUT", "30"))


def _get(url: str, headers: dict | None = None):
    req = _u.Request(url, headers=headers or {})
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
    status, _ = _get(f"{BASE}/openapi.json")
    if status < 0:
        pytest.skip(f"Kein Live-Backend unter {BASE} erreichbar")
    tok = _login()
    if not tok:
        pytest.skip("Login fehlgeschlagen (Rate-Limit?/Seed?) - Live-Test uebersprungen")
    return tok


def test_annotations_document_get_kein_500(token: str):
    """GET /annotations/document/{id} darf nie 5xx liefern (F-P2-009)."""
    headers = {"Authorization": f"Bearer {token}"}
    zufalls_id = uuid.uuid4()
    status, body = _get(
        f"{BASE}/api/v1/annotations/document/{zufalls_id}", headers=headers
    )
    assert status < 500, (
        f"Annotations-GET liefert {status} (F-P2-009-Regression: "
        f"current_user-Interface): {body[:200]!r}"
    )


def test_annotations_stats_get_kein_500(token: str):
    headers = {"Authorization": f"Bearer {token}"}
    zufalls_id = uuid.uuid4()
    status, body = _get(
        f"{BASE}/api/v1/annotations/document/{zufalls_id}/stats", headers=headers
    )
    assert status < 500, (
        f"Annotations-Stats liefert {status}: {body[:200]!r}"
    )
