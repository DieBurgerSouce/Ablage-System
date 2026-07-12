# -*- coding: utf-8 -*-
"""Regressionstest F-P1-001 (Perception-Audit 2026-07-12).

set_config(..., is_local=true) ist transaktions-lokal: nach einem commit() im
Handler lief der Rest des Requests ohne RLS-Kontext (GUC auf gepoolter
Verbindung = '' -> Alt-Policies crashten mit "invalid input syntax for type
boolean" bzw. lieferten 0 Zeilen -> "Could not refresh instance" beim Upload).

persist_rls_gucs() merkt die GUCs auf der Session vor; ein after_begin-Listener
re-appliziert sie in JEDER Folgetransaktion. Diese Tests beweisen genau das
gegen die echte Datenbank (laufen im Backend-Container).
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import persist_rls_gucs

TEST_UID = "00000000-0000-0000-0000-000000000001"


@pytest.mark.asyncio
async def test_rls_gucs_ueberleben_commit():
    """GUCs muessen nach commit() in der Folgetransaktion wieder gesetzt sein."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            await persist_rls_gucs(
                session,
                {"app.current_user_id": TEST_UID, "app.is_admin": "false"},
            )
            v1 = (
                await session.execute(
                    text("SELECT current_setting('app.current_user_id', true)")
                )
            ).scalar()
            assert v1 == TEST_UID

            await session.commit()  # ohne Listener: Kontext ab hier ''/verloren

            v2 = (
                await session.execute(
                    text("SELECT current_setting('app.current_user_id', true)")
                )
            ).scalar()
            assert v2 == TEST_UID, (
                "RLS-Kontext ging durch commit() verloren — after_begin-Listener "
                "re-appliziert nicht (Regression F-P1-001)"
            )

            v3 = (
                await session.execute(
                    text("SELECT current_setting('app.is_admin', true)")
                )
            ).scalar()
            assert v3 == "false", (
                f"app.is_admin muss 'false' bleiben, war {v3!r} — ''-Zustand "
                "war der Crash-Ausloeser (invalid input syntax for type boolean)"
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_gucs_mehrfache_commits_und_update():
    """Auch nach mehreren Commits + GUC-Update bleibt der letzte Stand aktiv."""
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as session:
            await persist_rls_gucs(session, {"app.is_admin": "false"})
            await session.commit()
            await persist_rls_gucs(session, {"app.is_admin": "true"})
            await session.commit()
            await session.commit()  # noqa: doppelter Commit ist im Handler-Alltag moeglich
            v = (
                await session.execute(
                    text("SELECT current_setting('app.is_admin', true)")
                )
            ).scalar()
            assert v == "true"
    finally:
        await engine.dispose()
