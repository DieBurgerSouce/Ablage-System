# -*- coding: utf-8 -*-
"""Adversariale Tests fuer RLS_ENFORCE_DEFAULT (fail-closed Tenant-Kontext).

BOUNDED INCREMENT (KEIN voller RLS-Abschluss): prueft den APP-seitigen Fail-Closed-
Guard in set_rls_company_context. Die PG-Policy-Reconciliation (3 Session-Vars,
company_id IS NULL-Leak) bleibt ein separater Task.
"""
import uuid

import pytest
from unittest.mock import AsyncMock, patch

from app.middleware.company_context import set_rls_company_context


@pytest.mark.asyncio
async def test_enforce_on_missing_context_denies():
    """Enforcement an + KEIN company_id -> harte Verweigerung, KEINE Query."""
    db = AsyncMock()
    with patch("app.middleware.company_context.settings.RLS_ENFORCE_DEFAULT", True):
        with pytest.raises(PermissionError):
            await set_rls_company_context(db, None)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_enforce_on_invalid_uuid_denies():
    """Enforcement an + ungueltige UUID -> Verweigerung statt stillem Skip (war fail-open)."""
    db = AsyncMock()
    with patch("app.middleware.company_context.settings.RLS_ENFORCE_DEFAULT", True):
        with pytest.raises(PermissionError):
            await set_rls_company_context(db, "not-a-uuid")


@pytest.mark.asyncio
async def test_enforce_on_valid_context_sets_and_succeeds():
    """Enforcement an + gueltige company_id -> Kontext wird gesetzt (set_config), kein raise."""
    db = AsyncMock()
    cid = uuid.uuid4()
    with patch("app.middleware.company_context.settings.RLS_ENFORCE_DEFAULT", True):
        await set_rls_company_context(db, cid)
    db.execute.assert_awaited()  # set_config('app.current_company_id', ...) wurde ausgefuehrt


@pytest.mark.asyncio
async def test_enforce_off_missing_context_no_raise_backward_compat():
    """Default AUS: fehlender Kontext -> KEIN raise (bisheriges Verhalten unveraendert)."""
    db = AsyncMock()
    with patch("app.middleware.company_context.settings.RLS_ENFORCE_DEFAULT", False):
        await set_rls_company_context(db, None)
    db.execute.assert_not_called()
