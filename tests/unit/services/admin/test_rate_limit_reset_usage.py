# -*- coding: utf-8 -*-
"""Tests: RateLimitService.reset_usage - Session-Hygiene im Fehlerfall.

Vorher fehlte das rollback() im except-Zweig: Nach einem fehlgeschlagenen
add()/commit() blieb die request-gebundene Session in einer kaputten
Transaktion zurueck (PendingRollbackError fuer alle Folgenutzer).
Ausserdem leakte der Redis-Client, wenn delete() warf.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.admin.rate_limit_service import RateLimitService

pytestmark = pytest.mark.asyncio


def _make_admin() -> MagicMock:
    admin = MagicMock()
    admin.id = uuid.uuid4()
    return admin


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    return db


def _make_redis_client() -> AsyncMock:
    client = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    return client


class TestResetUsage:
    async def test_erfolg_loescht_keys_und_commited(self) -> None:
        db = _make_db()
        client = _make_redis_client()

        with patch(
            "app.services.admin.rate_limit_service.redis.from_url",
            return_value=client,
        ):
            ok = await RateLimitService.reset_usage(
                db, uuid.uuid4(), _make_admin(), ip_address="127.0.0.1"
            )

        assert ok is True
        assert client.delete.await_count == 4
        client.close.assert_awaited_once()
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        db.rollback.assert_not_awaited()

    async def test_commit_fehler_rollt_session_zurueck(self) -> None:
        """Kein PendingRollbackError fuer Folgenutzer der Session."""
        db = _make_db()
        db.commit = AsyncMock(side_effect=RuntimeError("DB kaputt"))
        client = _make_redis_client()

        with patch(
            "app.services.admin.rate_limit_service.redis.from_url",
            return_value=client,
        ):
            ok = await RateLimitService.reset_usage(
                db, uuid.uuid4(), _make_admin()
            )

        assert ok is False
        db.rollback.assert_awaited_once()

    async def test_redis_fehler_schliesst_client_und_rollt_zurueck(self) -> None:
        """Redis-Fehler: kein Client-Leak, Rueckgabe False, Session sauber."""
        db = _make_db()
        client = _make_redis_client()
        client.delete = AsyncMock(side_effect=ConnectionError("Redis weg"))

        with patch(
            "app.services.admin.rate_limit_service.redis.from_url",
            return_value=client,
        ):
            ok = await RateLimitService.reset_usage(
                db, uuid.uuid4(), _make_admin()
            )

        assert ok is False
        client.close.assert_awaited_once()
        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()

    async def test_rollback_fehler_wird_geschluckt(self) -> None:
        """Auch ein scheiternder rollback() laesst reset_usage sauber False liefern."""
        db = _make_db()
        db.commit = AsyncMock(side_effect=RuntimeError("DB kaputt"))
        db.rollback = AsyncMock(side_effect=RuntimeError("rollback kaputt"))
        client = _make_redis_client()

        with patch(
            "app.services.admin.rate_limit_service.redis.from_url",
            return_value=client,
        ):
            ok = await RateLimitService.reset_usage(
                db, uuid.uuid4(), _make_admin()
            )

        assert ok is False
