# -*- coding: utf-8 -*-
"""Unit-Tests für die Modul-Registry (Einfrier-Mechanik, Odoo-Neuausrichtung).

DB-frei: testet nur ``app/core/module_registry.py`` gegen eine
FastAPI-Dummy-App. Settings-Overrides via monkeypatch auf dem
``settings``-Singleton.
"""

import pytest
from fastapi import APIRouter, FastAPI

from app.core.config import settings
from app.core.module_registry import (
    FROZEN_BY_DEFAULT,
    KNOWN_OPTIONAL_MODULES,
    MODULE_AI_SPECULATIVE,
    MODULE_BANKING,
    MODULE_DATEV,
    MODULE_EINVOICE,
    MODULE_LEXWARE,
    get_module_status,
    include_module_router,
    is_module_active,
)


@pytest.fixture(autouse=True)
def _clean_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stellt fuer jeden Test den Default her (kein Override aktiv)."""
    monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "", raising=False)


def _make_router() -> APIRouter:
    router = APIRouter(prefix="/dummy", tags=["Dummy"])

    @router.get("/ping")
    async def ping() -> dict:
        return {"pong": True}

    return router


def _openapi_paths(app: FastAPI) -> set:
    """Registrierte Pfade versionsrobust ermitteln (fastapi 0.121 wie 0.138).

    Neuere fastapi/starlette-Versionen wrappen inkludierte Router in
    ``_IncludedRouter`` ohne ``path``-Attribut — das OpenAPI-Schema ist die
    stabile, versionsunabhaengige Sicht auf die registrierten Routen.
    """
    app.openapi_schema = None  # Cache invalidieren (frische Sicht)
    return set(app.openapi().get("paths", {}).keys())


# =============================================================================
# is_module_active
# =============================================================================


class TestIsModuleActive:
    def test_default_alle_frozen_module_inaktiv(self) -> None:
        for key in FROZEN_BY_DEFAULT:
            assert is_module_active(key) is False, f"{key} muss default-eingefroren sein"

    def test_einvoice_ist_default_frozen(self) -> None:
        """M-06-Regression: die unauthentifizierten einvoice-Endpoints muessen
        ohne expliziten Override eingefroren sein."""
        assert MODULE_EINVOICE in FROZEN_BY_DEFAULT
        assert is_module_active(MODULE_EINVOICE) is False

    def test_unbekannter_key_gilt_als_aktiv(self) -> None:
        assert is_module_active("gibt_es_nicht") is True

    def test_env_override_aktiviert_einzelne_module(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "banking, datev")
        assert is_module_active(MODULE_BANKING) is True
        assert is_module_active(MODULE_DATEV) is True
        assert is_module_active(MODULE_LEXWARE) is False
        assert is_module_active(MODULE_EINVOICE) is False

    def test_env_override_ist_case_und_whitespace_tolerant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "  BANKING ,Datev ")
        assert is_module_active(MODULE_BANKING) is True
        assert is_module_active(MODULE_DATEV) is True

    def test_wildcard_aktiviert_alle_module(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "*")
        for key in KNOWN_OPTIONAL_MODULES:
            assert is_module_active(key) is True

    def test_unbekannte_keys_im_override_werden_ignoriert(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "tippfehler,banking")
        assert is_module_active(MODULE_BANKING) is True
        assert is_module_active("tippfehler") is True  # unbekannt = nie eingefroren
        assert is_module_active(MODULE_DATEV) is False


# =============================================================================
# include_module_router
# =============================================================================


class TestIncludeModuleRouter:
    def test_frozen_modul_registriert_router_nicht(self) -> None:
        app = FastAPI()
        registered = include_module_router(
            app, _make_router(), MODULE_BANKING, prefix="/api/v1"
        )
        assert registered is False
        assert "/api/v1/dummy/ping" not in _openapi_paths(app)

    def test_aktives_modul_registriert_router(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "banking")
        app = FastAPI()
        registered = include_module_router(
            app, _make_router(), MODULE_BANKING, prefix="/api/v1"
        )
        assert registered is True
        assert "/api/v1/dummy/ping" in _openapi_paths(app)

    def test_nicht_gefrorener_key_registriert_immer(self) -> None:
        app = FastAPI()
        registered = include_module_router(
            app, _make_router(), "kein_freeze_key", prefix="/api/v1"
        )
        assert registered is True
        assert "/api/v1/dummy/ping" in _openapi_paths(app)

    def test_tags_werden_durchgereicht(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "banking")
        app = FastAPI()
        include_module_router(
            app, _make_router(), MODULE_BANKING, prefix="/api/v1", tags=["Extra"]
        )
        app.openapi_schema = None
        operation = app.openapi()["paths"]["/api/v1/dummy/ping"]["get"]
        assert "Extra" in operation.get("tags", [])

    def test_reaktivierung_wirkt_pro_aufruf(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kein Modul-Cache: Settings-Aenderung wirkt beim naechsten Aufruf."""
        app = FastAPI()
        assert include_module_router(app, _make_router(), MODULE_DATEV, prefix="/x") is False
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "datev")
        assert include_module_router(app, _make_router(), MODULE_DATEV, prefix="/x") is True


# =============================================================================
# get_module_status
# =============================================================================


class TestGetModuleStatus:
    def test_default_alles_frozen(self) -> None:
        status = get_module_status()
        assert status["active"] == []
        assert set(status["frozen"]) == set(KNOWN_OPTIONAL_MODULES)

    def test_status_ist_konsistent_und_disjunkt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "ACTIVE_OPTIONAL_MODULES", "banking,ai_speculative"
        )
        status = get_module_status()
        active = set(status["active"])
        frozen = set(status["frozen"])
        assert active == {MODULE_BANKING, MODULE_AI_SPECULATIVE}
        assert active.isdisjoint(frozen)
        assert active | frozen == set(KNOWN_OPTIONAL_MODULES)

    def test_listen_sind_sortiert(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ACTIVE_OPTIONAL_MODULES", "*")
        status = get_module_status()
        assert status["active"] == sorted(status["active"])
        assert status["frozen"] == []

    def test_status_konsistent_mit_is_module_active(self) -> None:
        status = get_module_status()
        for key in status["active"]:
            assert is_module_active(key) is True
        for key in status["frozen"]:
            assert is_module_active(key) is False
