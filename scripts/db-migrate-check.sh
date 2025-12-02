#!/bin/bash
#
# db-migrate-check.sh - Pre-Migration Validation Script
#
# Fuehrt umfassende Pruefungen vor Datenbank-Migrationen durch:
# - Backup-Status pruefen
# - Pending Migrations anzeigen
# - Datenbank-Konsistenz validieren
# - Speicherplatz pruefen
# - Aktive Verbindungen anzeigen
#
# Verwendung: ./scripts/db-migrate-check.sh [--apply]
#

set -e

# Farben fuer Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Konfiguration
MIN_DISK_SPACE_GB=10
MAX_CONNECTIONS_FOR_MIGRATION=50
BACKUP_MAX_AGE_HOURS=24

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Ablage-System: Pre-Migration Check   ${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Funktion fuer Status-Ausgabe
check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAILED=1
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    WARNED=1
}

check_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

FAILED=0
WARNED=0

# 1. Datenbank-Verbindung pruefen
echo -e "\n${BLUE}1. Datenbank-Verbindung pruefen...${NC}"
if docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    check_pass "PostgreSQL ist erreichbar"
else
    check_fail "PostgreSQL ist nicht erreichbar"
    echo "   Starte zuerst die Datenbank: docker-compose up -d postgres"
    exit 1
fi

# 2. Aktuelle Revision pruefen
echo -e "\n${BLUE}2. Alembic-Status pruefen...${NC}"
CURRENT_REV=$(docker-compose exec -T backend alembic current 2>/dev/null | grep -oP '[a-f0-9]{12}' | head -1 || echo "none")
if [ "$CURRENT_REV" != "none" ]; then
    check_pass "Aktuelle Revision: $CURRENT_REV"
else
    check_warn "Keine aktuelle Revision gefunden"
fi

# 3. Pending Migrations anzeigen
echo -e "\n${BLUE}3. Pending Migrations pruefen...${NC}"
PENDING=$(docker-compose exec -T backend alembic history --indicate-current 2>/dev/null | grep -c "^[a-f0-9]" || echo "0")
PENDING_AFTER=$(docker-compose exec -T backend alembic history --indicate-current 2>/dev/null | grep -A 1000 "(current)" | grep -c "^[a-f0-9]" || echo "0")

if [ "$PENDING_AFTER" -gt "0" ]; then
    check_info "$PENDING_AFTER Migration(en) ausstehend:"
    docker-compose exec -T backend alembic history --indicate-current 2>/dev/null | grep -A 1000 "(current)" | head -20
else
    check_pass "Keine Migrations ausstehend"
fi

# 4. Speicherplatz pruefen
echo -e "\n${BLUE}4. Speicherplatz pruefen...${NC}"
AVAILABLE_GB=$(df -BG . | awk 'NR==2 {gsub("G",""); print $4}')
if [ "$AVAILABLE_GB" -ge "$MIN_DISK_SPACE_GB" ]; then
    check_pass "${AVAILABLE_GB}GB verfuegbar (minimum: ${MIN_DISK_SPACE_GB}GB)"
else
    check_fail "Nur ${AVAILABLE_GB}GB verfuegbar (minimum: ${MIN_DISK_SPACE_GB}GB)"
fi

# 5. Aktive Verbindungen pruefen
echo -e "\n${BLUE}5. Aktive Datenbankverbindungen pruefen...${NC}"
ACTIVE_CONN=$(docker-compose exec -T postgres psql -U postgres -d ablage -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'ablage';" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$ACTIVE_CONN" -lt "$MAX_CONNECTIONS_FOR_MIGRATION" ]; then
    check_pass "$ACTIVE_CONN aktive Verbindung(en) (max empfohlen: $MAX_CONNECTIONS_FOR_MIGRATION)"
else
    check_warn "$ACTIVE_CONN aktive Verbindungen - Migration koennte blockiert werden"
fi

# 6. Laufende Transaktionen pruefen
echo -e "\n${BLUE}6. Lange laufende Transaktionen pruefen...${NC}"
LONG_RUNNING=$(docker-compose exec -T postgres psql -U postgres -d ablage -t -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - interval '5 minutes';" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$LONG_RUNNING" -eq "0" ]; then
    check_pass "Keine lange laufenden Transaktionen"
else
    check_warn "$LONG_RUNNING Transaktion(en) laeuft seit >5 Minuten"
    docker-compose exec -T postgres psql -U postgres -d ablage -c "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state = 'active' AND query_start < NOW() - interval '5 minutes';" 2>/dev/null
fi

# 7. Backup-Status pruefen
echo -e "\n${BLUE}7. Backup-Status pruefen...${NC}"
BACKUP_DIR="./backups"
if [ -d "$BACKUP_DIR" ]; then
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/*.sql.gz 2>/dev/null | head -1)
    if [ -n "$LATEST_BACKUP" ]; then
        BACKUP_AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "$LATEST_BACKUP")) / 3600 ))
        if [ "$BACKUP_AGE_HOURS" -lt "$BACKUP_MAX_AGE_HOURS" ]; then
            check_pass "Letztes Backup: $(basename $LATEST_BACKUP) (vor ${BACKUP_AGE_HOURS}h)"
        else
            check_warn "Backup ist ${BACKUP_AGE_HOURS}h alt (empfohlen: <${BACKUP_MAX_AGE_HOURS}h)"
        fi
    else
        check_warn "Kein Backup gefunden in $BACKUP_DIR"
    fi
else
    check_warn "Backup-Verzeichnis nicht gefunden: $BACKUP_DIR"
fi

# 8. Tabellen-Groessen anzeigen
echo -e "\n${BLUE}8. Tabellen-Groessen (Top 10):${NC}"
docker-compose exec -T postgres psql -U postgres -d ablage -c "
SELECT
    schemaname || '.' || tablename AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) AS data_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
LIMIT 10;
" 2>/dev/null || check_warn "Konnte Tabellen-Groessen nicht abrufen"

# 9. Constraint-Validierung
echo -e "\n${BLUE}9. Foreign Key Constraints pruefen...${NC}"
INVALID_FK=$(docker-compose exec -T postgres psql -U postgres -d ablage -t -c "
SELECT count(*) FROM pg_constraint
WHERE contype = 'f'
AND NOT convalidated;
" 2>/dev/null | tr -d ' ' || echo "0")
if [ "$INVALID_FK" -eq "0" ]; then
    check_pass "Alle Foreign Keys sind validiert"
else
    check_warn "$INVALID_FK unvalidierte Foreign Key(s)"
fi

# 10. Migration Dry-Run
echo -e "\n${BLUE}10. Migration Dry-Run...${NC}"
if docker-compose exec -T backend alembic upgrade head --sql > /dev/null 2>&1; then
    check_pass "Migration SQL generiert erfolgreich"
else
    check_fail "Migration SQL-Generierung fehlgeschlagen"
fi

# Zusammenfassung
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}          Zusammenfassung              ${NC}"
echo -e "${BLUE}========================================${NC}"

if [ "$FAILED" -eq "1" ]; then
    echo -e "${RED}Migration NICHT empfohlen - Fehler beheben!${NC}"
    exit 1
elif [ "$WARNED" -eq "1" ]; then
    echo -e "${YELLOW}Migration moeglich aber Warnungen beachten${NC}"
else
    echo -e "${GREEN}Migration kann sicher durchgefuehrt werden${NC}"
fi

# Optional: Migration ausfuehren
if [ "$1" == "--apply" ]; then
    echo -e "\n${YELLOW}Migration wird ausgefuehrt...${NC}"
    read -p "Fortfahren? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose exec -T backend alembic upgrade head
        echo -e "${GREEN}Migration abgeschlossen!${NC}"
    else
        echo "Migration abgebrochen."
    fi
else
    echo -e "\nFuehre './scripts/db-migrate-check.sh --apply' aus um Migration anzuwenden."
fi
