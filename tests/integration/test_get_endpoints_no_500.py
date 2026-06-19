"""Regressionstest (W2-25): Kein parameterloser GET-Endpunkt darf HTTP 500 liefern.

Friert die F-31-Offensive (192 GET-500 -> 0) ein. Laeuft gegen ein LIVE-Backend
(dokumentierter Sweep-Weg). Skippt sauber, wenn kein Backend erreichbar ist -
analog zu den anderen DB-/Live-gateten Integrationstests.

Run:  AZ_BASE_URL=http://127.0.0.1:8000 AZ_ADMIN_EMAIL=admin@localhost.com \
      AZ_ADMIN_PASSWORD=admin123 pytest tests/integration/test_get_endpoints_no_500.py -v
"""
from __future__ import annotations

import os
import json
import urllib.request as _u
import urllib.error

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


def _parameterless_get_paths(spec: dict) -> list[str]:
    paths = []
    for path, ops in spec.get("paths", {}).items():
        if "{" in path:
            continue
        op = ops.get("get")
        if not op:
            continue
        params = op.get("parameters", []) or []
        if any(p.get("required") and p.get("in") in ("path", "query") for p in params):
            continue
        paths.append(path)
    return sorted(set(paths))


@pytest.fixture(scope="module")
def token() -> str:
    # Backend erreichbar?
    status, _ = _get(f"{BASE}/openapi.json")
    if status < 0:
        pytest.skip(f"Kein Live-Backend unter {BASE} erreichbar")
    tok = _login()
    if not tok:
        pytest.skip("Login fehlgeschlagen (Rate-Limit?/Seed?) - Live-Test uebersprungen")
    return tok


def test_no_parameterless_get_returns_500(token: str):
    status, raw = _get(f"{BASE}/openapi.json")
    assert status == 200, f"openapi.json nicht erreichbar: {status}"
    spec = json.loads(raw)
    paths = _parameterless_get_paths(spec)
    assert paths, "Keine parameterlosen GET-Pfade gefunden"

    headers = {"Authorization": f"Bearer {token}"}
    failures = []
    for path in paths:
        st, _ = _get(f"{BASE}{path}", headers=headers)
        if st >= 500:
            failures.append(f"{st} {path}")

    assert not failures, (
        f"{len(failures)} GET-Endpunkt(e) liefern 5xx (F-31-Regression!):\n"
        + "\n".join(failures[:50])
    )