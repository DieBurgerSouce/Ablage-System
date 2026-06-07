# -*- coding: utf-8 -*-
"""E2E test-harness endpoint - state reset for deterministic agent/E2E runs.

HARD-GATED: this router is only mounted when ``settings.TESTING`` is true AND the
environment is not production (see ``app/main.py``). The handler additionally
re-checks the flag, so even an accidental mount stays inert (404). This MUST
NEVER be reachable in production.

Purpose: give browser-agent / Playwright runs a clean, reproducible baseline by
truncating transactional tables between runs, while preserving the deterministic
seeded identities (users / companies / memberships from ``scripts/seed_e2e.py``).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_session

router = APIRouter(prefix="/test", tags=["test-harness"])

# Hardcoded whitelist of tables that are safe to wipe between E2E runs.
# Source is a constant (NO user input -> no SQL-injection surface, CWE-89).
# Seeded identities (users, companies, user_companies) are intentionally absent
# so the deterministic E2E accounts survive a reset. TRUNCATE ... CASCADE only
# affects dependent (child) tables, never parent tables like ``users``.
RESETTABLE_TABLES = [
    "documents",
    "business_entities",
    "transactions",
    "banking_transactions",
    "invoices",
    "bpmn_process_instances",
    "bpmn_process_tasks",
    "import_logs",
]


def _require_testing() -> None:
    """Fail closed: behave as if the route does not exist outside test envs."""
    if not settings.TESTING or settings.is_production:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.post(
    "/reset-state",
    summary="Truncate transactional tables for a clean E2E baseline",
)
async def reset_state(db: AsyncSession = Depends(get_async_session)) -> dict:
    _require_testing()

    # Filter the whitelist down to tables that actually exist in this schema,
    # so the endpoint is robust across schema variants.
    existing = await db.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = ANY(:names)"
        ),
        {"names": RESETTABLE_TABLES},
    )
    tables = [row[0] for row in existing.fetchall()]
    if not tables:
        return {"reset": [], "detail": "no matching tables"}

    # Cross-tenant maintenance op -> bypass RLS for the truncate.
    await db.execute(text("SELECT set_config('app.rls_bypass', 'true', true)"))

    # Identifiers originate from the hardcoded whitelist, existence-verified
    # above -> safe to interpolate (no user-controlled value reaches the SQL).
    table_list = ", ".join(f'"{t}"' for t in tables)
    await db.execute(text(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE"))
    await db.commit()

    return {"reset": tables}
