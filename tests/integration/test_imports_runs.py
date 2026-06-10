# -*- coding: utf-8 -*-
"""W3-F2: GET /imports/runs — Gruppierung der Import-Logs nach batch_id.

Verifiziert die Datengrundlage der Live-Status-Anzeige: pro Lauf (batch_id)
korrekte Aggregation von total/completed/failed/skipped/pending und das
``is_running``-Flag. Braucht PostgreSQL (``test_db``); ohne DB Laufzeit-Skip.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_current_active_user, get_current_user
from app.db.database import get_db_session
from app.db.models import Company, Document, ImportLog, User
from app.main import app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_user(session: "AsyncSession", email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=email.split("@", 1)[0] + "_" + uuid.uuid4().hex[:8],
        hashed_password="$2b$12$0123456789012345678901uVeryFakeHashForTestsOnly",
        full_name="Importnutzer",
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_document(session: "AsyncSession") -> Document:
    company = Company(id=uuid.uuid4(), name="Import Test GmbH")
    session.add(company)
    await session.flush()
    doc = Document(
        id=uuid.uuid4(),
        filename="import.pdf",
        original_filename="import.pdf",
        company_id=company.id,
    )
    session.add(doc)
    await session.flush()
    return doc


async def _seed_log(
    session: "AsyncSession",
    user: User,
    batch_id: uuid.UUID,
    status: str,
    *,
    started_at: datetime,
    with_document: bool = False,
) -> None:
    document_id = None
    if with_document:
        doc = await _seed_document(session)
        document_id = doc.id
    session.add(
        ImportLog(
            id=uuid.uuid4(),
            user_id=user.id,
            source_type="email",
            batch_id=batch_id,
            status=status,
            document_id=document_id,
            started_at=started_at,
            completed_at=started_at + timedelta(seconds=5),
        )
    )
    await session.flush()


class _AuthClient:
    def __init__(self, session: "AsyncSession", user: User) -> None:
        self._session = session
        self._user = user

    async def __aenter__(self) -> AsyncClient:
        async def _override_user() -> User:
            return self._user

        async def _override_db() -> "AsyncIterator[AsyncSession]":
            yield self._session

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_active_user] = _override_user
        app.dependency_overrides[get_db_session] = _override_db
        self._client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)
        for dep in (get_current_user, get_current_active_user, get_db_session):
            app.dependency_overrides.pop(dep, None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runs_aggregates_by_batch(test_db: "AsyncSession") -> None:
    """Ein abgeschlossener Lauf wird korrekt aggregiert (10 OK, 2 Fehler)."""
    user = await _seed_user(test_db, "runs-a@firma.local")
    batch = uuid.uuid4()
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    for _ in range(10):
        await _seed_log(test_db, user, batch, "completed", started_at=base, with_document=True)
    for _ in range(2):
        await _seed_log(test_db, user, batch, "failed", started_at=base)

    async with _AuthClient(test_db, user) as client:
        response = await client.get("/api/v1/imports/runs")

    assert response.status_code == 200, response.text
    runs = response.json()
    assert len(runs) == 1
    run = runs[0]
    assert run["total"] == 12
    assert run["completed"] == 10
    assert run["failed"] == 2
    assert run["documents_created"] == 10
    assert run["is_running"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runs_flags_running_batch(test_db: "AsyncSession") -> None:
    """Ein Lauf mit offenen Einträgen ist als is_running markiert."""
    user = await _seed_user(test_db, "runs-b@firma.local")
    batch = uuid.uuid4()
    base = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _seed_log(test_db, user, batch, "completed", started_at=base, with_document=True)
    await _seed_log(test_db, user, batch, "processing", started_at=base)

    async with _AuthClient(test_db, user) as client:
        response = await client.get("/api/v1/imports/runs")

    assert response.status_code == 200, response.text
    run = response.json()[0]
    assert run["pending"] == 1
    assert run["is_running"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runs_isolated_per_user(test_db: "AsyncSession") -> None:
    """Ein Nutzer sieht nur seine eigenen Läufe."""
    user_a = await _seed_user(test_db, "runs-iso-a@firma.local")
    user_b = await _seed_user(test_db, "runs-iso-b@firma.local")
    base = datetime.now(timezone.utc) - timedelta(minutes=3)
    await _seed_log(test_db, user_a, uuid.uuid4(), "completed", started_at=base)
    await _seed_log(test_db, user_b, uuid.uuid4(), "completed", started_at=base)

    async with _AuthClient(test_db, user_a) as client:
        response = await client.get("/api/v1/imports/runs")

    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
