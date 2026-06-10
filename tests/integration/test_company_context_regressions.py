"""Regressionstests: Multi-Tenant-Korrektheit (Welle 1 / Workstream 1a).

Verifizierte Defekte (Stand 2026-06-10, vor dem Fix alle ROT):

1. ``get_user_current_company`` / ``get_user_company_id`` werfen
   ``MultipleResultsFound`` (-> HTTP 500), wenn ein User mehrere
   ``UserCompany``-Zeilen mit ``is_current=True`` hat. Diese Korruption
   kann entstehen, weil die DB sie nie verhindert hat (kein Constraint).
2. ``require_company`` ohne ``X-Company-ID``-Header faellt in denselben
   Pfad -> 500 statt sauberem Ergebnis (Company bzw. 400).
3. ``GET /entities`` und ``GET /entities/customers`` filtern NICHT nach
   ``company_id`` -> Cross-Tenant-Leak in den Listen (CWE-639).
   Der Einzel-GET ist seit G5 gefixt, die Listen nicht.
4. ``app.api.dependencies.get_db`` baut eine EIGENE Engine; der
   RLS-Kontext (``SET LOCAL``) aus ``require_company`` (Session aus
   ``app.db.database``) erreicht die Endpoint-Session daher nie.

Tests benoetigen PostgreSQL (``test_db``-Fixture; ohne DB Laufzeit-Skip).
Die "korrupten" Seeds (zwei ``is_current=True``) simulieren Bestands-DBs
von vor Migration 268; dafuer wird der Schutz-Index im Test entfernt.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.api import dependencies as api_deps
from app.api.dependencies import (
    get_current_active_user,
    get_current_user,
    get_user_company_id,
)
from app.db import database as db_module
from app.db.models import BusinessEntity, Company, User, UserCompany
from app.main import app
from app.middleware import company_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Seeding-Helfer
# =============================================================================

async def _seed_company(session: AsyncSession, name: str) -> Company:
    company = Company(id=uuid.uuid4(), name=name)
    session.add(company)
    await session.flush()
    return company


async def _seed_user(session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=email.split("@", 1)[0] + "_" + uuid.uuid4().hex[:8],
        hashed_password="$2b$12$0123456789012345678901uVeryFakeHashForTestsOnly",
        full_name="Testnutzer",
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_membership(
    session: AsyncSession,
    user: User,
    company: Company,
    *,
    is_current: bool,
    created_at: datetime,
) -> UserCompany:
    membership = UserCompany(
        user_id=user.id,
        company_id=company.id,
        role="member",
        is_current=is_current,
        created_at=created_at,
    )
    session.add(membership)
    await session.flush()
    return membership


async def _drop_single_current_guard(session: AsyncSession) -> None:
    """Simuliert eine Bestands-DB von VOR Migration 268 (ohne Schutz-Index)."""
    await session.execute(
        sa.text("DROP INDEX IF EXISTS uq_user_companies_one_current")
    )


async def _seed_corrupt_double_current(
    session: AsyncSession, user: User
) -> tuple[Company, Company]:
    """Zwei Mitgliedschaften mit is_current=True (aeltere + neuere)."""
    await _drop_single_current_guard(session)
    older = await _seed_company(session, "Alte Firma GmbH")
    newer = await _seed_company(session, "Neue Firma AG")
    await _seed_membership(
        session, user, older,
        is_current=True, created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await _seed_membership(
        session, user, newer,
        is_current=True, created_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    return older, newer


# =============================================================================
# HTTP-Harness (uebersteuert BEIDE get_db-Varianten, s. Defekt 4)
# =============================================================================

class _AuthClient:
    def __init__(self, session: AsyncSession, user: User) -> None:
        self._session = session
        self._user = user
        self._overridden: list[object] = []

    async def __aenter__(self) -> AsyncClient:
        async def _override_user() -> User:
            return self._user

        async def _override_db() -> AsyncIterator[AsyncSession]:
            yield self._session

        for dep in (get_current_user, get_current_active_user):
            app.dependency_overrides[dep] = _override_user
            self._overridden.append(dep)
        for dep in (api_deps.get_db, db_module.get_db_session, db_module.get_db):
            app.dependency_overrides[dep] = _override_db
            self._overridden.append(dep)

        self._client = AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)
        for dep in self._overridden:
            app.dependency_overrides.pop(dep, None)


# =============================================================================
# Defekt 1: MultipleResultsFound bei doppeltem is_current
# =============================================================================

@pytest.mark.integration
@pytest.mark.multi_tenant
class TestMultipleIsCurrentResolution:
    @pytest.mark.asyncio
    async def test_get_user_current_company_survives_double_current(
        self, test_db: AsyncSession
    ) -> None:
        """Korrupte Daten (2x is_current) duerfen keinen 500er ausloesen.

        Erwartung nach Fix: deterministisch die NEUESTE Mitgliedschaft.
        """
        user = await _seed_user(test_db, "doppel@firma.local")
        _older, newer = await _seed_corrupt_double_current(test_db, user)

        company = await company_context.get_user_current_company(user.id, test_db)

        assert company is not None, "Company muss aufloesbar sein (kein 500er)"
        assert company.id == newer.id, "Deterministisch: neueste Mitgliedschaft"

    @pytest.mark.asyncio
    async def test_get_user_company_id_survives_double_current(
        self, test_db: AsyncSession
    ) -> None:
        user = await _seed_user(test_db, "doppel2@firma.local")
        _older, newer = await _seed_corrupt_double_current(test_db, user)

        company_id = await get_user_company_id(test_db, user)

        assert company_id == newer.id


# =============================================================================
# Defekt 2: require_company ohne Header
# =============================================================================

def _bare_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    return Request(scope)


@pytest.mark.integration
@pytest.mark.multi_tenant
class TestRequireCompanyWithoutHeader:
    @pytest.mark.asyncio
    async def test_double_current_resolves_instead_of_500(
        self, test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne X-Company-ID + korrupte Daten: Company statt MultipleResultsFound."""
        user = await _seed_user(test_db, "header-los@firma.local")
        _older, newer = await _seed_corrupt_double_current(test_db, user)

        async def _fake_extract(request: object, db: object) -> User:
            return user

        monkeypatch.setattr(
            company_context, "_extract_user_from_token", _fake_extract
        )
        company_context.set_company_context(None)

        company = await company_context.require_company(_bare_request(), test_db)

        assert company.id == newer.id

    @pytest.mark.asyncio
    async def test_no_membership_returns_400(
        self, test_db: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ohne Firmenzuordnung: sauberer 400er mit deutscher Meldung."""
        user = await _seed_user(test_db, "firmenlos@firma.local")

        async def _fake_extract(request: object, db: object) -> User:
            return user

        monkeypatch.setattr(
            company_context, "_extract_user_from_token", _fake_extract
        )
        company_context.set_company_context(None)

        with pytest.raises(HTTPException) as excinfo:
            await company_context.require_company(_bare_request(), test_db)

        assert excinfo.value.status_code == 400
        assert "Firma" in str(excinfo.value.detail)


# =============================================================================
# Defekt 3: Listen-Endpoints leaken fremde Entities
# =============================================================================

@pytest.mark.integration
@pytest.mark.multi_tenant
class TestEntityListIsolation:
    @pytest.mark.asyncio
    async def test_list_entities_no_cross_tenant_leak(
        self, test_db: AsyncSession
    ) -> None:
        """GET /entities liefert nur eigene + firmenuebergreifende Entities."""
        company_a = await _seed_company(test_db, "Firma A GmbH")
        company_b = await _seed_company(test_db, "Firma B AG")
        user_a = await _seed_user(test_db, "list-a@firma-a.local")
        await _seed_membership(
            test_db, user_a, company_a,
            is_current=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        own = BusinessEntity(
            id=uuid.uuid4(), name="Eigener Partner", company_id=company_a.id
        )
        shared = BusinessEntity(
            id=uuid.uuid4(), name="Globaler Partner", company_id=None
        )
        foreign = BusinessEntity(
            id=uuid.uuid4(), name="Geheimer Partner von B", company_id=company_b.id
        )
        test_db.add_all([own, shared, foreign])
        await test_db.flush()

        async with _AuthClient(test_db, user_a) as client:
            response = await client.get("/api/v1/entities", params={"per_page": 100})

        assert response.status_code == 200, response.text
        returned_ids = {e["id"] for e in response.json()["entities"]}
        assert str(own.id) in returned_ids
        assert str(shared.id) in returned_ids
        assert str(foreign.id) not in returned_ids, (
            "Cross-Tenant-Leak: Entity von Firma B in Liste von Firma A!"
        )

    @pytest.mark.asyncio
    async def test_customers_endpoint_filters_company(
        self, test_db: AsyncSession
    ) -> None:
        """GET /entities/customers leakt keine Kunden fremder Firmen."""
        company_a = await _seed_company(test_db, "Firma A GmbH")
        company_b = await _seed_company(test_db, "Firma B AG")
        user_a = await _seed_user(test_db, "kunden-a@firma-a.local")
        await _seed_membership(
            test_db, user_a, company_a,
            is_current=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        own = BusinessEntity(
            id=uuid.uuid4(), name="Kunde A", entity_type="customer",
            company_id=company_a.id,
        )
        foreign = BusinessEntity(
            id=uuid.uuid4(), name="Kunde B", entity_type="customer",
            company_id=company_b.id,
        )
        test_db.add_all([own, foreign])
        await test_db.flush()

        async with _AuthClient(test_db, user_a) as client:
            response = await client.get("/api/v1/entities/customers")

        assert response.status_code == 200, response.text
        returned_ids = {c["id"] for c in response.json()["items"]}
        assert str(own.id) in returned_ids
        assert str(foreign.id) not in returned_ids, (
            "Cross-Tenant-Leak: Kunde von Firma B in Kundenliste von Firma A!"
        )


# =============================================================================
# Defekt 4 + Migration 268: Konsolidierung und Schutz-Index
# =============================================================================

@pytest.mark.integration
@pytest.mark.multi_tenant
class TestStructuralGuards:
    def test_get_db_dependency_is_consolidated(self) -> None:
        """Beide get_db-Dependencies muessen DASSELBE Callable sein.

        Sonst erreicht der RLS-Kontext (SET LOCAL in require_company) die
        Endpoint-Session nie und Test-Overrides decken nur die Haelfte ab.
        """
        assert api_deps.get_db is db_module.get_db_session

    @pytest.mark.asyncio
    async def test_unique_index_blocks_second_is_current(
        self, test_db: AsyncSession
    ) -> None:
        """Der Partial-Unique-Index verhindert NEUE is_current-Korruption."""
        user = await _seed_user(test_db, "constraint@firma.local")
        company_1 = await _seed_company(test_db, "Erste Firma GmbH")
        company_2 = await _seed_company(test_db, "Zweite Firma AG")
        await _seed_membership(
            test_db, user, company_1,
            is_current=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        with pytest.raises(IntegrityError):
            await _seed_membership(
                test_db, user, company_2,
                is_current=True,
                created_at=datetime(2026, 2, 1, tzinfo=UTC),
            )
        await test_db.rollback()
