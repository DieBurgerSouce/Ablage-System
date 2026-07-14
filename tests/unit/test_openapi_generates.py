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
    # Schwelle 1900: Stand nach dem Neuausrichtung-Modul-Freeze sind 1989
    # Pfade legitim (vorher >2000). Der Guard soll GROSSE Ausfaelle erkennen
    # (kaputte Generierung reisst hunderte Pfade weg), nicht einzelne Routen.
    assert len(paths) > 1900, (
        f"Nur {len(paths)} paths generiert - OpenAPI-Generierung womoeglich "
        "teilweise gebrochen (z. B. reintroduced `from __future__ import annotations`)."
    )


def test_privat_endpoints_are_mounted() -> None:
    """F-P4-001 (Perception-Audit 2026-07-12): Die Privat-Endpunkte muessen
    tatsaechlich registriert sein.

    Regression: ``app/api/v1/privat.py`` (echte Routen) wurde vom leeren
    Package ``app/api/v1/privat/`` verschattet -> ``from app.api.v1.privat
    import router`` lud den Leer-Router und ALLE ``/api/v1/privat/*``-Pfade
    lieferten 404 (Privat-Dashboard/Familienmitglied-Flow tot). Fix: Modul
    nach ``privat/routes.py`` verschoben + im Package re-exportiert.
    """
    paths = app.openapi().get("paths", {})
    for expected in ("/api/v1/privat/dashboard", "/api/v1/privat/spaces"):
        assert expected in paths, (
            f"Privat-Endpunkt {expected} ist nicht gemountet - der leere "
            "privat/-Package-Router verschattet vermutlich wieder privat/routes.py."
        )
