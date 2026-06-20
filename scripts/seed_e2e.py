# -*- coding: utf-8 -*-
"""Idempotent E2E seed for deterministic agent / Playwright runs.

Creates (or reuses) a stable admin user, a non-admin "viewer" user, one test
company, their UserCompany memberships, and two synthetic Lexware business
entities. All data is SYNTHETIC (no real PII). Credentials are for local/CI
E2E only and must never be used in production.

Run inside the backend container (the app DATABASE_URL must be reachable):

    docker compose exec backend python scripts/seed_e2e.py

The script is idempotent: running it repeatedly leaves the database unchanged.
"""
from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

from sqlalchemy import select, text

import app.db.all_models  # noqa: F401  # registers the full ORM model graph (configure_mappers)
from app.core.security_auth import get_password_hash
from app.db.models import User
from app.db.models_cash_company import Company, UserCompany
from app.db.models_datev import DATEVConfiguration
from app.db.models_entity_business import BusinessEntity, EntityType
from app.db.session import get_async_session_context

# --- Deterministic fixtures (synthetic) -------------------------------------
ADMIN_EMAIL = "admin@localhost.com"
ADMIN_PASSWORD = "admin123"  # matches tests/frontend/e2e/auth.setup.ts defaults
VIEWER_EMAIL = "viewer@localhost.com"
VIEWER_PASSWORD = "viewer123"
COMPANY_NAME = "E2E Test GmbH"
COMPANY_VAT = "DE999999999"


async def _get_or_create_user(
    session, *, email: str, username: str, password: str, full_name: str, is_superuser: bool
):
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    user = User(
        id=uuid4(),
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        full_name=full_name,
        is_active=True,
        is_superuser=is_superuser,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    return user, True


async def _get_or_create_company(session, *, name: str, vat_id: str):
    existing = (
        await session.execute(select(Company).where(Company.vat_id == vat_id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    company = Company(
        id=uuid4(),
        name=name,
        short_name="e2e",
        vat_id=vat_id,
        is_active=True,
        is_default=False,
    )
    session.add(company)
    await session.flush()
    return company, True


async def _ensure_membership(session, *, user, company, role: str, is_current: bool, **perms) -> bool:
    existing = (
        await session.execute(
            select(UserCompany).where(
                UserCompany.user_id == user.id,
                UserCompany.company_id == company.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(
        UserCompany(
            id=uuid4(),
            user_id=user.id,
            company_id=company.id,
            role=role,
            is_current=is_current,
            can_manage_cash=perms.get("can_manage_cash", False),
            can_approve_expenses=perms.get("can_approve_expenses", False),
            can_export_datev=perms.get("can_export_datev", False),
            can_manage_settings=perms.get("can_manage_settings", False),
        )
    )
    return True


async def _ensure_business_entity(session, *, name: str, vat_id: str, entity_type: str) -> bool:
    existing = (
        await session.execute(select(BusinessEntity).where(BusinessEntity.vat_id == vat_id))
    ).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(
        BusinessEntity(
            id=uuid4(),
            entity_type=entity_type,
            name=name,
            vat_id=vat_id,
            verified=True,
            is_active=True,
        )
    )
    return True


async def _ensure_datev_config(session, *, user) -> bool:
    """Eine DATEV-Konfiguration fuer den Nutzer anlegen (user-scoped).

    Ohne mindestens eine Konfiguration zeigt die Export-Seite den Leer-Zustand
    "Keine Konfiguration vorhanden" statt des Export-Formulars -> der E2E-Test
    fuer das F4-Validator-Gate (datev-export.spec.ts) findet "Neuen Export
    erstellen"/Vorschau-Button nicht. `list_configs` filtert auf
    user_id == current_user.id, daher dem Admin-Nutzer zuordnen.
    """
    # .first() statt scalar_one_or_none(): DATEVConfiguration erlaubt LAUT MODELL
    # mehrere Konfigurationen pro Nutzer ("Jeder Benutzer kann mehrere ... haben"),
    # und reset-state leert datev_configurations NICHT -> bei >1 Bestands-Config
    # wuerfe scalar_one_or_none() MultipleResultsFound und der Seed (und damit die
    # up-/api-Stufe) braeche ab. Wir pruefen nur, OB schon eine existiert.
    existing = (
        await session.execute(
            select(DATEVConfiguration)
            .where(DATEVConfiguration.user_id == user.id)
            .limit(1)
        )
    ).scalars().first()
    if existing is not None:
        return False
    session.add(
        DATEVConfiguration(
            id=uuid4(),
            user_id=user.id,
            berater_nr="1234567",
            mandanten_nr="12345",
            wj_beginn=date(2026, 1, 1),
            kontenrahmen="SKR03",
            is_default=True,
            is_active=True,
        )
    )
    return True


async def main() -> None:
    async with get_async_session_context() as session:
        # Seed runs cross-tenant -> bypass RLS so inserts are not filtered.
        await session.execute(text("SELECT set_config('app.rls_bypass', 'true', true)"))

        admin, admin_new = await _get_or_create_user(
            session,
            email=ADMIN_EMAIL,
            username="e2e-admin",
            password=ADMIN_PASSWORD,
            full_name="E2E Admin",
            is_superuser=True,
        )
        viewer, viewer_new = await _get_or_create_user(
            session,
            email=VIEWER_EMAIL,
            username="e2e-viewer",
            password=VIEWER_PASSWORD,
            full_name="E2E Viewer",
            is_superuser=False,
        )
        company, company_new = await _get_or_create_company(
            session, name=COMPANY_NAME, vat_id=COMPANY_VAT
        )

        await _ensure_membership(
            session,
            user=admin,
            company=company,
            role="owner",
            is_current=True,
            can_manage_cash=True,
            can_approve_expenses=True,
            can_export_datev=True,
            can_manage_settings=True,
        )
        await _ensure_membership(
            session, user=viewer, company=company, role="viewer", is_current=True
        )

        await _ensure_business_entity(
            session, name="E2E Kunde GmbH", vat_id="DE111111111", entity_type=EntityType.CUSTOMER.value
        )
        await _ensure_business_entity(
            session, name="E2E Lieferant AG", vat_id="DE222222222", entity_type=EntityType.SUPPLIER.value
        )

        await _ensure_datev_config(session, user=admin)

        print(
            f"[seed_e2e] admin={'created' if admin_new else 'exists'} "
            f"viewer={'created' if viewer_new else 'exists'} "
            f"company={'created' if company_new else 'exists'} "
            f"company_id={company.id}"
        )

    print("[seed_e2e] done")


if __name__ == "__main__":
    asyncio.run(main())
