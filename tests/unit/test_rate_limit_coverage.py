# -*- coding: utf-8 -*-
"""Unit-Test: B4 Rate-Limit-Decorator-Coverage.

Stellt sicher, dass jeder Endpoint in den 12 rate-limit-pflichtigen Routern
genau einen @limiter.limit-Decorator traegt. Verhindert Regression nach
Code-Review (z.B. wenn jemand einen neuen Endpoint hinzufuegt aber das
@limiter.limit-Decorator vergisst).

Feinpoliert und durchdacht - Rate-Limit-Invariante.
"""

import ast
from pathlib import Path

import pytest


pytestmark = [pytest.mark.unit]


RATE_LIMITED_ROUTERS = {
    "nlq.py": "10/minute",
    "dlp.py": "30/minute",
    "audit_chain.py": "60/minute",
    "event_sourcing.py": "60/minute",
    "graphql_api.py": "60/minute",
    "trash.py": "60/minute",
    "dpia.py": "60/minute",
    "ai_decisions.py": "60/minute",
    "compliance_autopilot.py": "60/minute",
    "smart_escalation.py": "30/minute",
    "supplier_verification.py": "60/minute",
    "notification_rules.py": "60/minute",
}


def _extract_endpoints(path: Path):
    """Return list of (func_name, has_router_dec, has_limiter_dec) tuples."""
    with open(path, "rb") as f:
        tree = ast.parse(f.read().decode("utf-8"))

    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        has_router = False
        has_limiter = False
        for dec in node.decorator_list:
            # @router.get(...) / @router.post(...) etc.
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if (
                    isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "router"
                ):
                    has_router = True
            # @limiter.limit(...)
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if (
                    isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == "limiter"
                    and dec.func.attr == "limit"
                ):
                    has_limiter = True
        if has_router:
            endpoints.append((node.name, has_router, has_limiter))
    return endpoints


@pytest.mark.parametrize("fname,_expected_rate", list(RATE_LIMITED_ROUTERS.items()))
def test_every_endpoint_has_limiter(fname, _expected_rate):
    """B4: Jeder @router-Endpoint in den 12 Routern hat @limiter.limit."""
    path = Path("app/api/v1") / fname
    assert path.exists(), f"{fname} fehlt"
    endpoints = _extract_endpoints(path)
    assert endpoints, f"Keine Endpoints in {fname} gefunden"
    missing = [name for name, has_router, has_lim in endpoints if not has_lim]
    assert not missing, (
        f"{fname}: {len(missing)} Endpoint(s) ohne @limiter.limit: {missing}"
    )


def test_router_files_all_exist():
    """Sanity: alle 12 Router-Files sind im Repo."""
    for fname in RATE_LIMITED_ROUTERS:
        path = Path("app/api/v1") / fname
        assert path.exists(), f"{fname} nicht gefunden"


def test_no_request_name_collision():
    """B4: Kein Endpoint hat `request: <NonRequestBodyType>` (Slowapi-Konflikt).

    Falls jemand einen neuen Body-Parameter `request: SomeBody` definiert,
    bricht slowapi - dieser Test faengt das ab.
    """
    import re

    failures = []
    for fname in RATE_LIMITED_ROUTERS:
        path = Path("app/api/v1") / fname
        content = path.read_text(encoding="utf-8")
        # Find all `request:` annotations and check they're :Request
        for m in re.finditer(r"\brequest\s*:\s*([A-Za-z_][\w\.]*)", content):
            ann = m.group(1)
            if ann not in ("Request",):
                failures.append(f"{fname}: `request: {ann}` (slowapi-Konflikt - umbenennen zu `body:`)")
    assert not failures, "Name-Kollisionen gefunden:\n" + "\n".join(failures)
