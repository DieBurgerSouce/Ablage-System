#!/usr/bin/env bash
# ============================================================
# Backend-Entrypoint (M-08, Phase 0 Betriebsreife)
#
# Ablauf:
#   1. Auf PostgreSQL warten (Python/asyncpg-Connect-Loop,
#      Timeout PG_WAIT_TIMEOUT, Default 120 s).
#   2. `alembic upgrade head` EINMALIG ausfuehren, geschuetzt durch
#      einen Postgres-Advisory-Lock (Key 815001): Parallele Container
#      mit demselben Image (Backend-Replikate, worker/beat im
#      Haupt-Compose) migrieren dadurch nie doppelt — sie warten am
#      Lock und laufen anschliessend als No-op durch.
#      Abschaltbar per RUN_MIGRATIONS=false.
#   3. exec "$@" — startet das eigentliche CMD (uvicorn bzw. celery).
#
# Hinweis: pg_isready ist im Backend-Image nicht installiert
# (kein postgresql-client); asyncpg ist ohnehin vorhanden, daher
# erfolgt der Wait- und Lock-Teil als Python-Inline-Snippet.
# ============================================================
set -euo pipefail

RUN_MIGRATIONS="${RUN_MIGRATIONS:-true}"
PG_WAIT_TIMEOUT="${PG_WAIT_TIMEOUT:-120}"
MIGRATION_LOCK_KEY="${MIGRATION_LOCK_KEY:-815001}"

python3 - "${PG_WAIT_TIMEOUT}" "${MIGRATION_LOCK_KEY}" "${RUN_MIGRATIONS}" <<'PYEOF'
import asyncio
import os
import subprocess
import sys
import time

wait_timeout = int(sys.argv[1])
lock_key = int(sys.argv[2])
run_migrations = sys.argv[3].strip().lower() in ("1", "true", "yes", "ja")

raw_url = os.getenv("ABLAGE_DATABASE_URL") or os.getenv("DATABASE_URL")
if not raw_url:
    print("[entrypoint] FEHLER: DATABASE_URL (oder ABLAGE_DATABASE_URL) ist nicht gesetzt.", flush=True)
    sys.exit(1)

# RLS light (Phase 7): Migrationen brauchen DDL-Rechte. Laeuft die App als
# ablage_app (NOSUPERUSER/NOBYPASSRLS, kein CREATE auf public), liefert
# MIGRATION_DATABASE_URL die Owner-Verbindung NUR fuer Wait/Lock/alembic —
# das eigentliche CMD (uvicorn/celery) behaelt die App-DATABASE_URL.
mig_url = os.getenv("MIGRATION_DATABASE_URL") or raw_url

# SQLAlchemy-Schema "postgresql+asyncpg://" -> asyncpg-DSN "postgresql://"
dsn = mig_url.replace("postgresql+asyncpg://", "postgresql://", 1)

import asyncpg  # noqa: E402  (erst nach dem DSN-Check importieren)


async def wait_for_postgres() -> None:
    """Wartet bis PostgreSQL Verbindungen annimmt (max. wait_timeout Sekunden)."""
    deadline = time.monotonic() + wait_timeout
    attempt = 0
    while True:
        attempt += 1
        try:
            conn = await asyncpg.connect(dsn, timeout=10)
            try:
                await conn.execute("SELECT 1")
            finally:
                await conn.close()
            print(f"[entrypoint] PostgreSQL erreichbar (Versuch {attempt}).", flush=True)
            return
        except (OSError, asyncio.TimeoutError, asyncpg.PostgresError) as exc:
            if time.monotonic() >= deadline:
                print(
                    f"[entrypoint] FEHLER: PostgreSQL nach {wait_timeout}s nicht erreichbar "
                    f"(letzter Fehler: {type(exc).__name__}).",
                    flush=True,
                )
                sys.exit(1)
            print(
                f"[entrypoint] Warte auf PostgreSQL ... (Versuch {attempt}, {type(exc).__name__})",
                flush=True,
            )
            await asyncio.sleep(2)


async def run_alembic_with_lock() -> None:
    """Fuehrt `alembic upgrade head` unter pg_advisory_lock aus (exactly-once)."""
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        print(f"[entrypoint] Hole Migrations-Lock pg_advisory_lock({lock_key}) ...", flush=True)
        # Session-Lock: blockiert, bis kein anderer Container mehr migriert.
        await conn.execute("SELECT pg_advisory_lock($1)", lock_key)
        print("[entrypoint] Lock erhalten — fuehre 'alembic upgrade head' aus ...", flush=True)
        # alembic/env.py bezieht die URL aus den App-Settings -> beide Env-Namen
        # auf die Migrations-URL zwingen (nur fuer diesen Subprozess).
        mig_env = dict(os.environ, DATABASE_URL=mig_url, ABLAGE_DATABASE_URL=mig_url)
        result = subprocess.run(["alembic", "upgrade", "head"], cwd="/app", env=mig_env)
        if result.returncode != 0:
            print(
                f"[entrypoint] FEHLER: 'alembic upgrade head' fehlgeschlagen (Exit-Code {result.returncode}).",
                flush=True,
            )
            sys.exit(result.returncode)
        print("[entrypoint] Migration abgeschlossen (Schema auf 'head').", flush=True)
    finally:
        try:
            await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
        finally:
            await conn.close()


def _code_head() -> str:
    """Ziel-Revision aus der Migrationskette (offline, ohne DB).

    `alembic heads` liest nur das versions/-Verzeichnis (env.py wird fuer
    dieses Kommando nicht ausgefuehrt). Bei Fehlern oder mehreren Heads
    wird '' geliefert -> Version-Check wird uebersprungen (fail-open).
    """
    try:
        out = subprocess.run(
            ["alembic", "heads"], cwd="/app", capture_output=True, text=True, timeout=60
        )
        heads = [line.split()[0] for line in out.stdout.splitlines() if line.strip()]
        if out.returncode == 0 and len(heads) == 1:
            return heads[0]
        print(f"[entrypoint] WARNUNG: alembic heads uneindeutig ({heads}) — Version-Check entfaellt.", flush=True)
    except Exception as exc:  # noqa: BLE001 — fail-open ist hier Absicht
        print(f"[entrypoint] WARNUNG: alembic heads fehlgeschlagen ({type(exc).__name__}) — Version-Check entfaellt.", flush=True)
    return ""


async def wait_for_migrations() -> None:
    """F-14: Nicht-Migratoren warten, bis das Schema auf Code-Head steht.

    Schliesst das Sekundenfenster, in dem ein Worker gegen ein halb
    migriertes Schema startet (Fresh-Deploy/Schema-Change): erst am
    Advisory-Lock dem aktiven Migrator den Vortritt lassen, dann
    alembic_version gegen den Code-Head pruefen. Kommt innerhalb
    PG_WAIT_TIMEOUT kein Migrator (z.B. Worker-only-Deployment), wird
    mit Warnung fortgefahren (fail-open = bisheriges Verhalten).
    """
    target = _code_head()
    deadline = time.monotonic() + wait_timeout
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        while True:
            # Aktiven Migrator abwarten (Lock nehmen und sofort freigeben).
            await conn.execute("SELECT pg_advisory_lock($1)", lock_key)
            await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)
            if not target:
                print("[entrypoint] Migrator abgewartet (ohne Version-Check).", flush=True)
                return
            current = await conn.fetchval(
                "SELECT version_num FROM alembic_version LIMIT 1"
            ) if await conn.fetchval("SELECT to_regclass('public.alembic_version') IS NOT NULL") else None
            if current == target:
                print(f"[entrypoint] Schema auf Code-Head {target} — starte CMD.", flush=True)
                return
            if time.monotonic() >= deadline:
                print(
                    f"[entrypoint] WARNUNG: Schema ({current}) != Code-Head ({target}) nach "
                    f"{wait_timeout}s — fahre fort (fail-open, F-14).",
                    flush=True,
                )
                return
            print(f"[entrypoint] Warte auf Migration ({current} -> {target}) ...", flush=True)
            await asyncio.sleep(2)
    finally:
        await conn.close()


async def main() -> None:
    await wait_for_postgres()
    if run_migrations:
        await run_alembic_with_lock()
    else:
        print("[entrypoint] RUN_MIGRATIONS=false — warte auf Migrator (F-14).", flush=True)
        await wait_for_migrations()


asyncio.run(main())
PYEOF

exec "$@"
