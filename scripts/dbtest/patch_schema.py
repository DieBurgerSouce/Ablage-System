# -*- coding: utf-8 -*-
"""Patcht ablage_test: ergaenzt fehlende Modell-Spalten an Tabellen, die meine
Integrationstests nutzen (documents u.a.), damit ORM-Inserts gegen den Klon
laufen. Nur ADD COLUMN (nicht-destruktiv)."""
import asyncio, os, re
url = os.environ["DATABASE_URL"]
test_url = re.sub(r"/[^/?]+(\?|$)", r"/ablage_test\1", url)
import app.main  # noqa
from sqlalchemy.orm import configure_mappers
configure_mappers()
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from app.db.models import Document, ApprovalRequest, ApprovalStep, BusinessEntity, User, Company
# NB: DATEV-Tabellen werden NICHT mehr gepatcht -> Migration 263 (Doppik-Reconcile)
# baut sie korrekt auf (alembic stamp 262 && upgrade head). Hier nur die noch nicht
# migrationsseitig aufgeloesten Drifts (documents/users/...) bis Stufe-2-Infra-Fix.
TARGETS = [Document, ApprovalRequest, ApprovalStep, BusinessEntity, User, Company]


async def main():
    eng = create_async_engine(test_url, echo=False)
    import sqlalchemy as sa
    async with eng.begin() as conn:
        # 1) Fehlende native ENUM-Typen anlegen (Modell deklariert sie, Klon-DB hat sie nicht)
        for model in TARGETS:
            for col in model.__table__.columns:
                ct = col.type
                if isinstance(ct, sa.Enum) and getattr(ct, "name", None):
                    exists = (await conn.execute(sa.text(
                        "SELECT 1 FROM pg_type WHERE typname=:n"), {"n": ct.name})).first()
                    if not exists and ct.enums:
                        vals = ", ".join("'" + v.replace("'", "''") + "'" for v in ct.enums)
                        try:
                            await conn.execute(sa.text(f"CREATE TYPE {ct.name} AS ENUM ({vals})"))
                            print(f"  TYPE {ct.name} ({len(ct.enums)} Werte)", flush=True)
                        except Exception as e:
                            print(f"  TYPE {ct.name} skip ({type(e).__name__})", flush=True)
        # 2) Fehlende Spalten ergaenzen
        for model in TARGETS:
            tbl = model.__tablename__
            rows = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name=:t"), {"t": tbl})
            have = {r[0] for r in rows}
            for col in model.__table__.columns:
                if col.name in have:
                    continue
                try:
                    coltype = col.type.compile(dialect=postgresql.dialect())
                except Exception:
                    coltype = "TEXT"
                nullable = "" if col.nullable else " "  # immer nullable hinzufuegen (Backfill-frei)
                ddl = f'ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS "{col.name}" {coltype}'
                await conn.execute(text(ddl))
                print(f"  + {tbl}.{col.name} {coltype}", flush=True)
    await eng.dispose()
    print("PATCH OK", flush=True)

asyncio.run(main())
