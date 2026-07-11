"""Tests fuer get_connection_config: Odoo-Company-Context-Aufloesung (AP-1).

Hintergrund (Go-Live-Runbook AP-1, P1): Der Vendor-Bill-Push baut seinen
Connector ueber get_connection_config(); das setzte odoo_company_id nie,
waehrend der Mirror die ID separat aufloeste. Ohne Context laufen
find_partner/create_vendor_bill_draft firmenuebergreifend (Company 1
"ALT-KOPIE"-Risiko). get_connection_config loest die ID jetzt selbst auf:
OdooSyncStatus.sync_state["odoo_company_id"] (mirror_account_move-Zeile,
Vorrang) -> settings.ODOO_MIRROR_COMPANY_ID (Fallback) -> None.

Mock-Muster wie tests/unit/services/erp/test_odoo_mirror_service.py
(keine echte DB, AsyncSession-Mock mit side_effect-Ergebnissen).
"""

from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.models import ERPConnection, OdooSyncStatus


def _make_connection() -> ERPConnection:
    """ERPConnection-ORM-Instanz ohne DB (Spalten explizit gesetzt)."""
    return ERPConnection(
        id=uuid4(),
        company_id=uuid4(),
        erp_type="odoo",
        name="Odoo Spargelmesser",
        url="https://odoo.example.com",
        database_name="odoo-db",
        username="ablage-integration",
        encrypted_api_key=None,
        sync_direction="pull",
        sync_interval_minutes=30,
        enabled_entities=["invoice"],
        max_requests_per_minute=60,
        batch_size=100,
        max_retries=3,
        retry_delay_seconds=5,
        connect_timeout_seconds=10,
        read_timeout_seconds=30,
        last_sync_at=None,
        is_active=True,
        created_by=None,
    )


def _make_sync_status(
    connection: ERPConnection, odoo_company_id: Optional[Any]
) -> OdooSyncStatus:
    state: Dict[str, Any] = {}
    if odoo_company_id is not None:
        state["odoo_company_id"] = odoo_company_id
    return OdooSyncStatus(
        id=uuid4(),
        connection_id=connection.id,
        data_type="mirror_account_move",
        sync_state=state,
        consecutive_failures=0,
        is_paused=False,
    )


def _result_scalar(value: Any) -> MagicMock:
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    return res


def _make_db(connection: ERPConnection, sync_status: Optional[OdooSyncStatus]) -> MagicMock:
    """AsyncSession-Mock: 1. execute -> Connection, 2. execute -> SyncStatus."""
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[_result_scalar(connection), _result_scalar(sync_status)]
    )
    return db


@pytest.mark.asyncio
async def test_config_uebernimmt_odoo_company_id_aus_sync_state(monkeypatch):
    """sync_state["odoo_company_id"] landet in ERPConnectionConfig (Push-Pfad)."""
    from app.core.config import settings
    from app.workers.tasks.erp_sync_tasks import get_connection_config

    monkeypatch.setattr(settings, "ODOO_MIRROR_COMPANY_ID", None, raising=False)
    connection = _make_connection()
    db = _make_db(connection, _make_sync_status(connection, odoo_company_id=2))

    config = await get_connection_config(db, connection.id)

    assert config is not None
    assert config.odoo_company_id == 2


@pytest.mark.asyncio
async def test_config_faellt_auf_setting_zurueck(monkeypatch):
    """Ohne sync_state-Wert greift ODOO_MIRROR_COMPANY_ID (Ein-Verbindungs-Setup)."""
    from app.core.config import settings
    from app.workers.tasks.erp_sync_tasks import get_connection_config

    monkeypatch.setattr(settings, "ODOO_MIRROR_COMPANY_ID", 7, raising=False)
    connection = _make_connection()
    db = _make_db(connection, None)

    config = await get_connection_config(db, connection.id)

    assert config is not None
    assert config.odoo_company_id == 7


@pytest.mark.asyncio
async def test_sync_state_hat_vorrang_vor_setting(monkeypatch):
    """Per-Connection-Wert schlaegt das globale Setting (Folie-Szenario)."""
    from app.core.config import settings
    from app.workers.tasks.erp_sync_tasks import get_connection_config

    monkeypatch.setattr(settings, "ODOO_MIRROR_COMPANY_ID", 2, raising=False)
    connection = _make_connection()
    db = _make_db(connection, _make_sync_status(connection, odoo_company_id=5))

    config = await get_connection_config(db, connection.id)

    assert config is not None
    assert config.odoo_company_id == 5


@pytest.mark.asyncio
async def test_ohne_state_und_setting_bleibt_none(monkeypatch):
    """Kein Wert nirgends -> None (heutiges kein-Context-Verhalten, Mirror skippt)."""
    from app.core.config import settings
    from app.workers.tasks.erp_sync_tasks import get_connection_config

    monkeypatch.setattr(settings, "ODOO_MIRROR_COMPANY_ID", None, raising=False)
    connection = _make_connection()
    db = _make_db(connection, None)

    config = await get_connection_config(db, connection.id)

    assert config is not None
    assert config.odoo_company_id is None


@pytest.mark.asyncio
async def test_unbrauchbarer_state_wert_faellt_auf_setting_zurueck(monkeypatch):
    """Nicht-numerischer sync_state-Wert wird verworfen -> Setting-Fallback."""
    from app.core.config import settings
    from app.workers.tasks.erp_sync_tasks import get_connection_config

    monkeypatch.setattr(settings, "ODOO_MIRROR_COMPANY_ID", 2, raising=False)
    connection = _make_connection()
    db = _make_db(connection, _make_sync_status(connection, odoo_company_id="kaputt"))

    config = await get_connection_config(db, connection.id)

    assert config is not None
    assert config.odoo_company_id == 2
