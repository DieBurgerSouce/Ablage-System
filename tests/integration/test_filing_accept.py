# -*- coding: utf-8 -*-
"""W3-F1: POST /automation/filing-suggestions/{id}/accept.

Vertrauens-Loop nach Upload: der Nutzer bestätigt (oder korrigiert) den
Ablage-Vorschlag, das Dokument landet real in der Kategorie. Verifiziert
Mandanten-Isolation (404 cross-tenant), Validierung (400 unbekannte
Kategorie) und den Happy-Path. Braucht PostgreSQL (``test_db``).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.dependencies import get_current_active_user, get_current_user
from app.db.database import get_db_session
from app.db.models import Company, Document, User, UserCompany
from app.main import app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_company(session: "AsyncSession", name: str) -> Company:
    company = Company(id=uuid.uuid4(), name=name)
    session.add(company)
    await session.flush()
    return company


async def _seed_user(session: "AsyncSession", company: Company, email: str) -> User:
    # Eindeutiger Suffix: der Accept-Endpoint committet echt, daher ueberleben
    # Testdaten den Lauf; feste Emails wuerden bei Wiederholung kollidieren.
    unique = uuid.uuid4().hex[:8]
    local, domain = email.split("@", 1)
    user = User(
        id=uuid.uuid4(),
        email=f"{local}+{unique}@{domain}",
        username=f"{local}_{unique}",
        hashed_password="$2b$12$0123456789012345678901uVeryFakeHashForTestsOnly",
        full_name="Ablagenutzer",
        is_active=True,
        is_superuser=False,
    )
    session.add(user)
    await session.flush()
    session.add(
        UserCompany(user_id=user.id, company_id=company.id, role="member", is_current=True)
    )
    await session.flush()
    return user


async def _seed_document(session: "AsyncSession", company: Company, owner: User) -> Document:
    doc = Document(
        id=uuid.uuid4(),
        filename="rechnung.pdf",
        original_filename="rechnung.pdf",
        company_id=company.id,
        owner_id=owner.id,
        data_category="briefe",
    )
    session.add(doc)
    await session.flush()
    return doc


class _AuthClient:
    def __init__(self, session: "AsyncSession", user: User) -> None:
        self._session = session
        self._user = user

    async def __aenter__(self) -> AsyncClient:
        from app.core.security_auth import create_access_token

        async def _override_user() -> User:
            return self._user

        async def _override_db() -> "AsyncIterator[AsyncSession]":
            yield self._session

        app.dependency_overrides[get_current_user] = _override_user
        app.dependency_overrides[get_current_active_user] = _override_user
        app.dependency_overrides[get_db_session] = _override_db
        # Bearer-Token: CSRF-Middleware laesst Bearer-authentifizierte POSTs
        # durch (kann nicht cross-origin gesetzt werden).
        token = create_access_token({"sub": str(self._user.id)})
        self._client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        )
        return await self._client.__aenter__()

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)
        for dep in (get_current_user, get_current_active_user, get_db_session):
            app.dependency_overrides.pop(dep, None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accept_files_document(test_db: "AsyncSession") -> None:
    """Happy-Path: bestätigte Kategorie wird real gesetzt (filed=true)."""
    company = await _seed_company(test_db, "Ablage GmbH")
    user = await _seed_user(test_db, company, "filer@firma.local")
    doc = await _seed_document(test_db, company, user)

    async with _AuthClient(test_db, user) as client:
        response = await client.post(
            f"/api/v1/automation/filing-suggestions/{doc.id}/accept",
            json={"target_category": "rechnungen"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filed"] is True
    assert body["target_category"] == "rechnungen"

    # bulk_move_category setzt document_type aus dem Kategorie-Mapping.
    await test_db.refresh(doc)
    assert doc.document_type is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accept_rejects_unknown_category(test_db: "AsyncSession") -> None:
    """Unbekannte Kategorie -> 400 mit deutscher Meldung."""
    company = await _seed_company(test_db, "Ablage GmbH")
    user = await _seed_user(test_db, company, "filer2@firma.local")
    doc = await _seed_document(test_db, company, user)

    async with _AuthClient(test_db, user) as client:
        response = await client.post(
            f"/api/v1/automation/filing-suggestions/{doc.id}/accept",
            json={"target_category": "gibtsnicht"},
        )

    assert response.status_code == 400
    # Globaler Exception-Handler liefert das deutsche Error-Schema.
    assert "Kategorie" in response.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accept_cross_tenant_returns_404(test_db: "AsyncSession") -> None:
    """Dokument einer fremden Firma -> 404 (kein Cross-Tenant-Zugriff)."""
    company_a = await _seed_company(test_db, "Firma A GmbH")
    company_b = await _seed_company(test_db, "Firma B AG")
    user_a = await _seed_user(test_db, company_a, "a@firma-a.local")
    owner_b = await _seed_user(test_db, company_b, "b@firma-b.local")
    doc_b = await _seed_document(test_db, company_b, owner_b)

    async with _AuthClient(test_db, user_a) as client:
        response = await client.post(
            f"/api/v1/automation/filing-suggestions/{doc_b.id}/accept",
            json={"target_category": "rechnungen"},
        )

    assert response.status_code == 404
