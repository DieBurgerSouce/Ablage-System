#!/usr/bin/env bash
# W2 (Plan-Item 0d): API-Contract-Fuzzing mit Schemathesis.
#
# Laeuft gegen den LOKALEN Test-Stack (docker-compose.test.yml-Override,
# NIE gegen Produktion). Schemathesis generiert aus der OpenAPI-Spec
# Hunderte Requests und jagt 5xx-Antworten (Check: not_a_server_error -
# kaum False-Positives; Schema-Conformance-Checks koennen spaeter
# zugeschaltet werden).
#
# Nutzung:
#   make api-fuzz                       # Stack starten + seeden + fuzzen
#   BASE_URL=http://localhost:8000 MAX_EXAMPLES=50 scripts/run_schemathesis.sh
#
# Voraussetzungen: schemathesis auf dem Host (pip install -r requirements-dev.txt),
# laufender Stack mit Test-Override (TESTING=true, Rate-Limit aus).
set -euo pipefail

# Windows-Hosts: Schemathesis-Ausgabe enthaelt Unicode -> cp1252 crasht.
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1

BASE_URL="${BASE_URL:-http://localhost:8000}"
MAX_EXAMPLES="${MAX_EXAMPLES:-25}"
MAX_FAILURES="${MAX_FAILURES:-10}"
ADMIN_EMAIL="${E2E_ADMIN_EMAIL:-admin@localhost.com}"
ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-admin123}"
SEED="${SEED:-1}"

echo ">> Warte auf Backend ($BASE_URL)..."
for _ in $(seq 1 60); do
    if curl -fsS "$BASE_URL/health" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
curl -fsS "$BASE_URL/health" >/dev/null || {
    echo "FEHLER: Backend nicht erreichbar. Stack starten mit:" >&2
    echo "  docker compose -f docker-compose.yml -f docker-compose.test.yml up -d" >&2
    exit 1
}

if [ "$SEED" = "1" ]; then
    echo ">> Seede deterministische Testdaten (seed_e2e.py)..."
    # scripts/ ist nicht ins Backend-Image gemountet -> per stdin pipen.
    docker compose -f docker-compose.yml -f docker-compose.test.yml \
        exec -T backend python - < scripts/seed_e2e.py
fi

# OpenAPI-Schema vorwaermen: Die Spec ist gross (~7-8 MB) und die ERSTE
# Generierung nach (Re-)Start dauert >10s. Schemathesis v4 hat einen festen
# 10s-Schema-Load-Read-Timeout -> ohne Warmup schlaegt das Laden fehl
# ("Read timed out after 10 seconds"). Nach dem Warmup laedt /openapi.json
# in <0.5s. Generoeses --max-time, Fehler nicht fatal (schemathesis meldet es
# sonst selbst).
echo ">> Waerme OpenAPI-Schema vor (erste Generierung kann >10s dauern)..."
curl -fsS --max-time 90 "$BASE_URL/openapi.json" >/dev/null 2>&1 \
    || echo "WARNUNG: OpenAPI-Warmup langsam/fehlgeschlagen - Schemathesis koennte beim Laden scheitern." >&2

echo ">> Hole Access-Token ($ADMIN_EMAIL)..."
TOKEN=$(curl -fsS -X POST "$BASE_URL/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" \
    | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
    echo "FEHLER: Kein Access-Token erhalten." >&2
    exit 1
fi

echo ">> Starte Schemathesis (max-examples=$MAX_EXAMPLES, Check: not_a_server_error)..."
# Ausgeschlossen: /api/v1/test/ (Reset wuerde den Seed-Zustand zerstoeren),
# Auth-Logout (wuerde das Fuzz-Token invalidieren) sowie DELETE-Methoden
# (erste Ausbaustufe konservativ - kein Wegfuzzen von Dev-Daten).
# SCHEMATHESIS_BIN: absoluter Pfad fuer Windows-Hosts, auf denen das
# Python-Scripts-Verzeichnis nicht im (Git-Bash-)PATH liegt.
"${SCHEMATHESIS_BIN:-schemathesis}" run "$BASE_URL/openapi.json" \
    --header "Authorization: Bearer $TOKEN" \
    --checks not_a_server_error \
    --max-examples "$MAX_EXAMPLES" \
    --max-failures "$MAX_FAILURES" \
    --exclude-method DELETE \
    --exclude-path-regex '^/api/v1/(test/|auth/logout)' \
    "$@"
