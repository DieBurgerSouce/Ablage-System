# -*- coding: utf-8 -*-
"""Regressions-Guard: app.openapi() muss vollstaendig generieren.

Schuetzt gegen das Wiedereinfuehren von ``from __future__ import annotations``
in Router-Modulen, das unter pydantic 2.11 die OpenAPI-Generierung bricht
(/docs + /openapi.json -> HTTP 500). Laeuft im Unit-Job (kein DB/Infra noetig).
"""

from app.main import app


def test_app_openapi_generates() -> None:
    """app.openapi() generiert das volle Schema ohne PydanticUserError."""
    spec = app.openapi()
    assert spec.get("openapi"), "OpenAPI-Version fehlt"
    paths = spec.get("paths", {})
    assert len(paths) > 2000, (
        f"Nur {len(paths)} paths generiert - OpenAPI-Generierung womoeglich "
        "teilweise gebrochen (z. B. reintroduced `from __future__ import annotations`)."
    )
