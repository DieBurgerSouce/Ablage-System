"""Tests fuer admin/erp-Verbindungs-Helfer (Go-Live-Folge-Tasks, 2026-07-11).

1) AAD-Roundtrip UI->Worker (P1-Fund): Die UI verschluesselte API-Keys mit
   AAD "erp:{company_id}", der Worker entschluesselt mit
   "erp_connection:{connection_id}" (decrypt_api_key) -> AES-GCM InvalidTag
   -> jede UI-Connection waere am Go-Live-Tag mit "Login fehlgeschlagen"
   gestorben. Create/Update muessen encrypt_api_key(connection_id) nutzen.

2) odoo_company_id bedienbar (Runbook AP-2-Folge): per-Connection-Wert lebt
   in OdooSyncStatus.sync_state["odoo_company_id"] (mirror-Zeile, Vorrang
   vor ODOO_MIRROR_COMPANY_ID) — Upsert-Helfer + Schema-Felder.
"""

import re
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.unit]

_ERP_API_FILE = (
    Path(__file__).resolve().parents[3] / "app" / "api" / "v1" / "admin" / "erp.py"
)


# =============================================================================
# 1) API-Key-AAD
# =============================================================================


def test_ui_verschluesselung_ist_worker_entschluesselbar():
    """Roundtrip: Helfer der UI-Endpoints -> decrypt_api_key des Workers."""
    from app.api.v1.admin.erp import _encrypt_connection_api_key
    from app.core.encryption import decrypt_api_key

    connection_id = uuid4()
    encrypted = _encrypt_connection_api_key("geheimer-odoo-key", connection_id)

    assert decrypt_api_key(encrypted, str(connection_id)) == "geheimer-odoo-key"


def test_alte_company_aad_nicht_mehr_im_quelltext():
    """Quelltext-Wache: die falsche AAD 'erp:{company.id}' darf nie zurueckkehren."""
    source = _ERP_API_FILE.read_text(encoding="utf-8")
    assert 'associated_data=f"erp:' not in source, (
        "admin/erp.py verschluesselt wieder mit Company-AAD — der Worker "
        "entschluesselt mit erp_connection:{connection_id} (decrypt_api_key)!"
    )
    assert "_encrypt_connection_api_key" in source


# =============================================================================
# 2) odoo_company_id: Upsert-Helfer
# =============================================================================


def _make_db(existing_status: Optional[Any]) -> MagicMock:
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing_status)
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    return db


@pytest.mark.asyncio
async def test_set_odoo_company_id_legt_sync_status_an():
    from app.api.v1.admin.erp import _set_connection_odoo_company_id

    db = _make_db(existing_status=None)
    connection_id = uuid4()

    await _set_connection_odoo_company_id(db, connection_id, 2)

    db.add.assert_called_once()
    created = db.add.call_args.args[0]
    assert created.connection_id == connection_id
    assert created.data_type == "mirror_account_move"
    assert dict(created.sync_state)["odoo_company_id"] == 2


@pytest.mark.asyncio
async def test_set_odoo_company_id_aktualisiert_bestehende_zeile():
    from app.api.v1.admin.erp import _set_connection_odoo_company_id
    from app.db.models import OdooSyncStatus

    existing = OdooSyncStatus(
        id=uuid4(),
        connection_id=uuid4(),
        data_type="mirror_account_move",
        sync_state={"last_run": {"created": 3}, "odoo_company_id": 1},
    )
    old_state = existing.sync_state
    db = _make_db(existing_status=existing)

    await _set_connection_odoo_company_id(db, existing.connection_id, 5)

    assert dict(existing.sync_state)["odoo_company_id"] == 5
    # Nachbar-Keys bleiben erhalten
    assert dict(existing.sync_state)["last_run"] == {"created": 3}
    # CrossDBJSON: Neuzuweisung des kompletten Dicts, kein In-Place-Mutieren
    assert existing.sync_state is not old_state
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_set_odoo_company_id_none_entfernt_den_wert():
    """None = Wert loeschen -> Fallback auf ODOO_MIRROR_COMPANY_ID greift wieder."""
    from app.api.v1.admin.erp import _set_connection_odoo_company_id
    from app.db.models import OdooSyncStatus

    existing = OdooSyncStatus(
        id=uuid4(),
        connection_id=uuid4(),
        data_type="mirror_account_move",
        sync_state={"odoo_company_id": 7, "cursor_hint": "x"},
    )
    db = _make_db(existing_status=existing)

    await _set_connection_odoo_company_id(db, existing.connection_id, None)

    assert "odoo_company_id" not in dict(existing.sync_state)
    assert dict(existing.sync_state)["cursor_hint"] == "x"


@pytest.mark.asyncio
async def test_set_odoo_company_id_none_ohne_zeile_ist_noop():
    from app.api.v1.admin.erp import _set_connection_odoo_company_id

    db = _make_db(existing_status=None)

    await _set_connection_odoo_company_id(db, uuid4(), None)

    db.add.assert_not_called()


# =============================================================================
# 2b) Schemas
# =============================================================================


def test_create_schema_akzeptiert_odoo_company_id():
    from app.api.v1.admin.erp import ERPConnectionCreate

    data = ERPConnectionCreate(
        name="Odoo Spargelmesser",
        url="https://odoo.example.com",
        username="ablage-integration",
        api_key="k",
        odoo_company_id=2,
    )
    assert data.odoo_company_id == 2


def test_response_schema_hat_odoo_company_id():
    from app.api.v1.admin.erp import ERPConnectionResponse

    assert "odoo_company_id" in ERPConnectionResponse.model_fields
