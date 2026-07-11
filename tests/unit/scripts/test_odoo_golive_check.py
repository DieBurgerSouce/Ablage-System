"""Tests fuer scripts/odoo_golive_check.py (AP-3 Go-Live-Runbook).

Abgedeckt (alles gemockt, keine echten Odoo-Calls, keine DB):
- compute_move_diff: Zaehler-Abgleich je move_type (0-Diff = PASS)
- verify_sample_content: Hash-Dreifach-Pruefung (SHA256 lokal, SHA-1 gegen
  gespeicherten und gegen live gelesenen Odoo-Checksum)
- run_phase2: Login -> account.move-Count -> Draft-Bill create+unlink
  (Gate-Logik, Abbruch bei Login-Fehler, --keep-draft)
"""

import hashlib
import os
import sys
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = [pytest.mark.unit]


def _locate_scripts_dir() -> str:
    """Finde scripts/ ueber mehrere Kandidaten-Pfade (Host + Container)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "..", "scripts"),
        "/app/scripts",
        os.path.join(os.getcwd(), "scripts"),
    ]
    for base in candidates:
        path = os.path.abspath(os.path.join(base, "odoo_golive_check.py"))
        if os.path.isfile(path):
            return os.path.dirname(path)
    return ""


_SCRIPTS_DIR = _locate_scripts_dir()

if not _SCRIPTS_DIR:
    pytest.skip(
        "odoo_golive_check.py nicht auffindbar - scripts/ ist in dieser "
        "Umgebung nicht gemountet (Infra-Setup, kein Test-Drift).",
        allow_module_level=True,
    )

if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odoo_golive_check import (  # noqa: E402
    Phase2Result,
    build_check_ref,
    compute_move_diff,
    run_phase2,
    verify_sample_content,
)


# =============================================================================
# compute_move_diff
# =============================================================================


def test_diff_null_diff_ist_pass():
    rows = compute_move_diff(
        {"out_invoice": 3, "in_invoice": 2},
        {"out_invoice": 3, "in_invoice": 2},
    )
    assert all(r.delta == 0 for r in rows)
    assert all(r.ok for r in rows)


def test_diff_fehlende_lokale_moves_werden_gemeldet():
    rows = compute_move_diff({"out_invoice": 5}, {"out_invoice": 3})
    (row,) = [r for r in rows if r.move_type == "out_invoice"]
    assert row.delta == 2
    assert not row.ok


def test_diff_deckt_alle_move_types_ab_auch_ohne_lokale_zeilen():
    rows = compute_move_diff({"in_refund": 1}, {})
    (row,) = [r for r in rows if r.move_type == "in_refund"]
    assert row.odoo_count == 1
    assert row.local_count == 0
    assert row.delta == 1


# =============================================================================
# verify_sample_content
# =============================================================================


def _content_and_hashes(payload: bytes):
    return (
        payload,
        hashlib.sha256(payload).hexdigest(),
        hashlib.sha1(payload).hexdigest(),
    )


def test_sample_alle_hashes_stimmen():
    content, sha256, sha1 = _content_and_hashes(b"beleg-bytes")
    result = verify_sample_content(
        content,
        stored_sha256=sha256,
        stored_odoo_sha1=sha1,
        live_odoo_sha1=sha1,
    )
    assert result.ok
    assert result.problems == []


def test_sample_manipulierter_inhalt_faellt_durch():
    content, sha256, sha1 = _content_and_hashes(b"beleg-bytes")
    result = verify_sample_content(
        b"MANIPULIERT",
        stored_sha256=sha256,
        stored_odoo_sha1=sha1,
        live_odoo_sha1=sha1,
    )
    assert not result.ok
    assert any("sha256" in p for p in result.problems)


def test_sample_odoo_seitige_aenderung_wird_erkannt():
    content, sha256, sha1 = _content_and_hashes(b"beleg-bytes")
    result = verify_sample_content(
        content,
        stored_sha256=sha256,
        stored_odoo_sha1=sha1,
        live_odoo_sha1="deadbeef" * 5,
    )
    assert not result.ok
    assert any("live" in p for p in result.problems)


def test_sample_ohne_odoo_checksums_prueft_nur_sha256():
    content, sha256, _ = _content_and_hashes(b"beleg-bytes")
    result = verify_sample_content(
        content,
        stored_sha256=sha256,
        stored_odoo_sha1=None,
        live_odoo_sha1=None,
    )
    assert result.ok


# =============================================================================
# run_phase2
# =============================================================================


def _make_connector(
    *,
    connect_ok: bool = True,
    move_count: int = 5,
    partner_ids: Optional[List[int]] = None,
    created_move_id: Optional[str] = "77",
    unlink_ok: bool = True,
) -> MagicMock:
    connector = MagicMock()
    connector.connect = AsyncMock(return_value=connect_ok)
    connector.disconnect = AsyncMock()
    connector.create_vendor_bill_draft = AsyncMock(return_value=created_move_id)

    async def _execute_kw(model: str, method: str, args: List[Any], kwargs: Optional[Dict[str, Any]] = None):
        if model == "account.move" and method == "search_count":
            return move_count
        if model == "res.partner" and method == "search":
            return list(partner_ids if partner_ids is not None else [42])
        if model == "account.move" and method == "unlink":
            if not unlink_ok:
                raise RuntimeError("unlink verboten")
            return True
        raise AssertionError(f"Unerwarteter Call: {model}.{method}")

    connector._execute_kw = AsyncMock(side_effect=_execute_kw)
    return connector


@pytest.mark.asyncio
async def test_phase2_happy_path_legt_draft_an_und_loescht_ihn():
    connector = _make_connector()

    result: Phase2Result = await run_phase2(connector, odoo_company_id=2)

    assert result.ok
    assert result.move_count == 5
    assert result.draft_move_id == "77"
    assert result.draft_deleted
    connector.create_vendor_bill_draft.assert_awaited_once()
    unlink_calls = [
        c for c in connector._execute_kw.await_args_list
        if c.args[0] == "account.move" and c.args[1] == "unlink"
    ]
    assert len(unlink_calls) == 1
    assert unlink_calls[0].args[2] == [[77]]


@pytest.mark.asyncio
async def test_phase2_login_fehler_bricht_ab():
    connector = _make_connector(connect_ok=False)

    result = await run_phase2(connector, odoo_company_id=2)

    assert not result.ok
    connector.create_vendor_bill_draft.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase2_ohne_company_context_faellt_durch():
    """odoo_company_id=None ist ein Konfig-Fehler (AP-1/AP-2) -> FAIL mit Hinweis."""
    connector = _make_connector()

    result = await run_phase2(connector, odoo_company_id=None)

    assert not result.ok
    assert any("ODOO_MIRROR_COMPANY_ID" in p for p in result.problems)
    connector.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase2_keep_draft_loescht_nicht():
    connector = _make_connector()

    result = await run_phase2(connector, odoo_company_id=2, keep_draft=True)

    assert result.ok
    assert not result.draft_deleted
    unlink_calls = [
        c for c in connector._execute_kw.await_args_list
        if c.args[0] == "account.move" and c.args[1] == "unlink"
    ]
    assert unlink_calls == []


@pytest.mark.asyncio
async def test_phase2_unlink_fehler_ist_warnung_nicht_fail():
    """Draft existiert dann noch (manuell loeschbar) -> ok bleibt True + Hinweis."""
    connector = _make_connector(unlink_ok=False)

    result = await run_phase2(connector, odoo_company_id=2)

    assert result.ok
    assert not result.draft_deleted
    assert any("manuell" in p.lower() for p in result.problems)


@pytest.mark.asyncio
async def test_phase2_null_moves_ist_pass():
    """Prod startet buchungsfrei: search_count == 0 ist ausdruecklich OK."""
    connector = _make_connector(move_count=0)

    result = await run_phase2(connector, odoo_company_id=2)

    assert result.ok
    assert result.move_count == 0


def test_check_ref_ist_eindeutig_und_erkennbar():
    ref1 = build_check_ref()
    ref2 = build_check_ref()
    assert ref1.startswith("ABLAGE-GOLIVE-CHECK-")
    assert ref1 != ref2
