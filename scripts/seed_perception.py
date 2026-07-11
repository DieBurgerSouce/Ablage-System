# -*- coding: utf-8 -*-
"""Idempotenter Seed fuer den Perception-Audit (Erste-10-Minuten-Walks).

Erstellt (oder findet) eine isolierte Audit-Firma "Perception Audit GmbH"
mit vier synthetischen Persona-Nutzern (KEIN Superuser — ehrliche TTFV ohne
Admin-Abkuerzungen) sowie einen Lieferanten "Buerohaus Mueller GmbH" als
Such-/Matching-Ziel. Alle Daten sind SYNTHETISCH (keine echte PII, keine
echten Firmenich-Accounts). Credentials nur fuer lokale Audit-Walks.

Run (Konvention wie seed_e2e.py):
    docker compose exec -T backend python - < scripts/seed_perception.py

Idempotent: Mehrfachlauf laesst die Datenbank unveraendert.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

from sqlalchemy import select, text

import app.db.all_models  # noqa: F401  # registriert den ORM-Model-Graph
from app.core.security_auth import get_password_hash
from app.db.models import User
from app.db.models_cash_company import Company, UserCompany
from app.db.models_entity_business import BusinessEntity, EntityType
from app.db.session import get_async_session_context

# --- Deterministische Fixtures (synthetisch) ---------------------------------

COMPANY_NAME = "Perception Audit GmbH"
COMPANY_VAT = "DE888888888"  # eindeutiger Idempotenz-Schluessel (E2E nutzt DE999999999)

SUPPLIER_NAME = "Bürohaus Müller GmbH"
SUPPLIER_VAT = "DE888800001"

# (email, username, passwort, voller Name, rolle, perms)
PERSONAS = [
    ("azubi@localhost.com", "percep-azubi", "azubi123", "Paul Azubi", "member", {}),
    (
        "prokurist@localhost.com",
        "percep-prokurist",
        "prokurist123",
        "Petra Prokurist",
        "admin",
        {"can_approve_expenses": True, "can_manage_settings": True},
    ),
    ("pruefer@localhost.com", "percep-pruefer", "pruefer123", "Sabine Prüfer", "viewer", {}),
    ("familie@localhost.com", "percep-familie", "familie123", "Finn Familie", "member", {}),
]


async def _get_or_create_user(session, *, email, username, password, full_name):
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
        is_superuser=False,
        email_verified=True,
    )
    session.add(user)
    await session.flush()
    return user, True


async def _get_or_create_company(session):
    existing = (
        await session.execute(select(Company).where(Company.vat_id == COMPANY_VAT))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False
    company = Company(
        id=uuid4(),
        name=COMPANY_NAME,
        short_name="percep",
        vat_id=COMPANY_VAT,
        is_active=True,
        is_default=False,
    )
    session.add(company)
    await session.flush()
    return company, True


async def _ensure_membership(session, *, user, company, role, **perms) -> bool:
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
    # is_current=True ist sicher: jede Persona hat genau EINE Mitgliedschaft
    # (partial-unique uq_user_companies_one_current bleibt gewahrt).
    session.add(
        UserCompany(
            id=uuid4(),
            user_id=user.id,
            company_id=company.id,
            role=role,
            is_current=True,
            can_manage_cash=perms.get("can_manage_cash", False),
            can_approve_expenses=perms.get("can_approve_expenses", False),
            can_export_datev=False,  # DATEV ist eingefrorenes Modul
            can_manage_settings=perms.get("can_manage_settings", False),
        )
    )
    return True


async def _ensure_supplier(session) -> bool:
    existing = (
        await session.execute(
            select(BusinessEntity).where(BusinessEntity.vat_id == SUPPLIER_VAT)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(
        BusinessEntity(
            id=uuid4(),
            entity_type=EntityType.SUPPLIER.value,
            name=SUPPLIER_NAME,
            vat_id=SUPPLIER_VAT,
            verified=True,
            is_active=True,
        )
    )
    return True


async def main() -> None:
    async with get_async_session_context() as session:
        # Seed laeuft cross-tenant -> RLS-Bypass, sonst filtern Policies die Inserts.
        # user_companies hat eine EIGENE Policy (user_company_access_policy), die
        # NICHT app.rls_bypass honoriert, sondern app.current_user_id/app.is_admin
        # prueft -> beide GUCs setzen (transaktions-lokal, Seed = eine Transaktion).
        await session.execute(text("SELECT set_config('app.rls_bypass', 'true', true)"))
        await session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))

        company, company_new = await _get_or_create_company(session)

        results = []
        for email, username, password, full_name, role, perms in PERSONAS:
            user, created = await _get_or_create_user(
                session,
                email=email,
                username=username,
                password=password,
                full_name=full_name,
            )
            await _ensure_membership(session, user=user, company=company, role=role, **perms)
            results.append(f"{username}={'created' if created else 'exists'}")

        supplier_new = await _ensure_supplier(session)

        print(
            f"[seed_perception] company={'created' if company_new else 'exists'} "
            f"({company.id}) supplier={'created' if supplier_new else 'exists'} "
            + " ".join(results)
        )

    print("[seed_perception] done")


if __name__ == "__main__":
    asyncio.run(main())
