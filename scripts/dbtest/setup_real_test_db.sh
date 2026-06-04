#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Baut die Integrationstest-DB `ablage_test` aus dem REALEN Schema auf.
#
# Warum nicht `alembic upgrade head` oder `Base.metadata.create_all`?
#   - create_all ist kaputt (dangling FK peppol_participants -> entities)
#   - `alembic upgrade head` von Null laeuft nicht durch (fehlende german_text-
#     TS-Config; eine Migration nutzt TextClause statt Column)
#   - die Dev-DB ist auf Alembic 261 gestempelt, aber Migrations-231-Spalten
#     fehlen (inkonsistenter Stand)
# Siehe `.claude/memory/KNOWN_ISSUES.md` ("Pervasives Modell<->DB-Drift").
#
# Daher: realen Schema-Klon ziehen + fehlende Modell-Spalten/Enum-Typen patchen
# (scripts/dbtest/patch_schema.py) + Status-Spalten auf native Enum konvertieren.
#
# Lokal (Docker): einfach ausfuehren -> nutzt die laufenden ablage-Container.
#   bash scripts/dbtest/setup_real_test_db.sh
#
# CI: PG_CONTAINER / BACKEND_CONTAINER / SOURCE_DB anpassen; danach Tests mit
#   TEST_DATABASE_URL=postgresql+asyncpg://<user>:<pw>@<host>:<port>/ablage_test
#   pytest tests/integration/test_workflow_insights_real_db.py -m integration
# ---------------------------------------------------------------------------
set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-ablage-postgres}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-ablage-backend}"
DB_USER="${DB_USER:-ablage_admin}"
SOURCE_DB="${SOURCE_DB:-ablage_system}"
TEST_DB="${TEST_DB:-ablage_test}"

echo ">> 1/4 ${TEST_DB} droppen + neu anlegen"
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$SOURCE_DB" -c "DROP DATABASE IF EXISTS ${TEST_DB};"
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$SOURCE_DB" -c "CREATE DATABASE ${TEST_DB};"
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$TEST_DB" \
  -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;" || true
# Custom Text-Search-Config (existiert in der echten DB ausserhalb der Migrationen)
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$TEST_DB" \
  -c "CREATE TEXT SEARCH CONFIGURATION german_text (COPY = german);" || true

echo ">> 2/4 Reales Schema klonen (pg_dump --schema-only)"
docker exec "$PG_CONTAINER" bash -c \
  "pg_dump -U ${DB_USER} --schema-only --no-owner --no-privileges ${SOURCE_DB} | psql -U ${DB_USER} -q ${TEST_DB}"

echo ">> 3/4 Fehlende Modell-Spalten + Enum-Typen patchen (patch_schema.py)"
# patch_schema.py liegt im gemounteten app/-Verzeichnis-Kontext NICHT; daher in /tmp
# via stdin in den Backend-Container leiten (app/-Code ist gemountet -> Imports gehen).
docker exec -e PYTHONPATH=/app -e TEST_DB="$TEST_DB" -i -w /app "$BACKEND_CONTAINER" \
  python - < "$(dirname "$0")/patch_schema.py"

echo ">> 4/4 Status-Spalten auf native Enum konvertieren (Modell deklariert native Enum)"
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$TEST_DB" -c \
  "ALTER TABLE approval_requests ALTER COLUMN status DROP DEFAULT;
   ALTER TABLE approval_requests ALTER COLUMN status TYPE approvalstatus USING status::approvalstatus;"
docker exec "$PG_CONTAINER" psql -U "$DB_USER" -d "$TEST_DB" -c \
  "ALTER TABLE approval_steps ALTER COLUMN status DROP DEFAULT;
   ALTER TABLE approval_steps ALTER COLUMN status TYPE approvalstatus USING status::approvalstatus;"

echo ">> FERTIG: ${TEST_DB} ist bereit fuer die Integrationstests."
