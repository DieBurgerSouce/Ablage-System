#!/bin/bash
# =============================================================================
# Terraform Lock Wrapper Script
# Ablage-System OCR Infrastructure
# =============================================================================
#
# This script provides distributed state locking for Terraform when using
# MinIO as the S3 backend. It uses PostgreSQL for lock management since
# MinIO doesn't support DynamoDB-style locking.
#
# Usage:
#   ./terraform-lock-wrapper.sh plan
#   ./terraform-lock-wrapper.sh apply
#   ./terraform-lock-wrapper.sh destroy
#
# Environment Variables:
#   POSTGRES_HOST     - PostgreSQL host (default: localhost)
#   POSTGRES_PORT     - PostgreSQL port (default: 5432)
#   POSTGRES_DB       - Database name (default: ablage_system)
#   POSTGRES_USER     - Database user (default: ablage_admin)
#   PGPASSWORD        - Database password (required)
#   TF_LOCK_TIMEOUT   - Lock timeout in seconds (default: 300)
#   TF_WORKSPACE      - Terraform workspace (default: default)
#
# =============================================================================

set -euo pipefail

# Configuration
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
LOCK_TIMEOUT="${TF_LOCK_TIMEOUT:-300}"
WORKSPACE="${TF_WORKSPACE:-default}"

# Lock ID based on workspace and current directory
LOCK_ID="terraform-${WORKSPACE}-$(basename "$(pwd)")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_debug() { [[ "${TF_LOCK_DEBUG:-false}" == "true" ]] && echo -e "${BLUE}[DEBUG]${NC} $1" || true; }

# Check prerequisites
check_prerequisites() {
    if ! command -v psql &> /dev/null; then
        log_error "psql ist nicht installiert. Bitte PostgreSQL Client installieren."
        exit 1
    fi

    if ! command -v terraform &> /dev/null; then
        log_error "terraform ist nicht installiert."
        exit 1
    fi

    if [[ -z "${PGPASSWORD:-}" ]]; then
        log_error "PGPASSWORD Umgebungsvariable muss gesetzt sein."
        exit 1
    fi
}

# Execute PostgreSQL query
pg_query() {
    local query="$1"
    psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -t -A -c "$query" 2>/dev/null
}

# Acquire lock
acquire_lock() {
    local hostname=$(hostname)
    local pid=$$
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local user="${USER:-unknown}"
    local terraform_version=$(terraform version -json 2>/dev/null | grep -o '"terraform_version":"[^"]*"' | cut -d'"' -f4 || echo "unknown")

    local lock_info=$(cat <<EOF
{
    "ID": "$LOCK_ID",
    "Operation": "$1",
    "Info": "",
    "Who": "$user@$hostname",
    "Version": "$terraform_version",
    "Created": "$timestamp",
    "Path": "$(pwd)"
}
EOF
)

    log_info "Versuche Lock zu erwerben: $LOCK_ID"
    log_debug "Lock-Info: $lock_info"

    # Try to acquire lock using the PostgreSQL function
    local result
    result=$(pg_query "SELECT terraform_acquire_lock('$LOCK_ID', '$lock_info'::jsonb, $LOCK_TIMEOUT);")

    if [[ "$result" == "t" ]]; then
        log_info "Lock erfolgreich erworben."
        return 0
    else
        # Check who holds the lock
        local lock_holder
        lock_holder=$(pg_query "SELECT info->>'Who' FROM terraform_locks WHERE id = '$LOCK_ID' AND expires_at > NOW();")

        if [[ -n "$lock_holder" ]]; then
            log_error "Lock wird bereits gehalten von: $lock_holder"
            log_error "Warte bis der Lock freigegeben wird oder timeout erreicht ist."
        else
            log_error "Lock konnte nicht erworben werden (unbekannter Fehler)."
        fi
        return 1
    fi
}

# Release lock
release_lock() {
    log_info "Gebe Lock frei: $LOCK_ID"

    local result
    result=$(pg_query "SELECT terraform_release_lock('$LOCK_ID');")

    if [[ "$result" == "t" ]]; then
        log_info "Lock erfolgreich freigegeben."
    else
        log_warn "Lock existierte nicht oder war bereits freigegeben."
    fi
}

# Check lock status
check_lock_status() {
    log_info "Prüfe Lock-Status: $LOCK_ID"

    local result
    result=$(pg_query "SELECT * FROM terraform_is_locked('$LOCK_ID');")

    if [[ "$result" == "t|"* ]]; then
        log_warn "Lock ist aktiv!"
        local lock_info=$(pg_query "SELECT info FROM terraform_locks WHERE id = '$LOCK_ID';")
        echo "$lock_info" | python3 -m json.tool 2>/dev/null || echo "$lock_info"
        return 1
    else
        log_info "Kein aktiver Lock vorhanden."
        return 0
    fi
}

# Force unlock (use with caution)
force_unlock() {
    log_warn "ACHTUNG: Force-Unlock wird ausgeführt!"
    log_warn "Dies sollte nur verwendet werden, wenn der Lock-Inhaber abgestürzt ist."

    read -p "Sind Sie sicher? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        log_info "Force-Unlock abgebrochen."
        return 1
    fi

    release_lock
    log_info "Force-Unlock abgeschlossen."
}

# List all locks
list_locks() {
    log_info "Aktive Terraform Locks:"
    echo ""

    pg_query "
        SELECT
            id,
            info->>'Who' as who,
            info->>'Operation' as operation,
            created_at,
            expires_at
        FROM terraform_locks
        WHERE expires_at > NOW()
        ORDER BY created_at DESC;
    " | column -t -s '|' || echo "Keine aktiven Locks gefunden."
}

# Cleanup expired locks
cleanup_locks() {
    log_info "Bereinige abgelaufene Locks..."

    local count
    count=$(pg_query "DELETE FROM terraform_locks WHERE expires_at < NOW() RETURNING id;" | wc -l)

    log_info "$count abgelaufene Locks entfernt."
}

# Main Terraform wrapper
run_terraform() {
    local operation="${1:-plan}"
    shift || true

    # Commands that need locking
    local needs_lock=true
    case "$operation" in
        plan|apply|destroy|import|refresh|taint|untaint)
            needs_lock=true
            ;;
        init|validate|fmt|show|state|output|providers|version|help)
            needs_lock=false
            ;;
        *)
            needs_lock=true
            ;;
    esac

    if [[ "$needs_lock" == "true" ]]; then
        # Try to acquire lock
        local retry_count=0
        local max_retries=5
        local retry_delay=10

        while ! acquire_lock "$operation"; do
            ((retry_count++))
            if [[ $retry_count -ge $max_retries ]]; then
                log_error "Maximale Anzahl an Lock-Versuchen erreicht ($max_retries)."
                exit 1
            fi
            log_warn "Lock nicht verfügbar. Warte ${retry_delay}s... (Versuch $retry_count/$max_retries)"
            sleep $retry_delay
        done

        # Ensure lock is released on exit
        trap 'release_lock; exit' EXIT INT TERM

        # Run Terraform
        log_info "Führe Terraform $operation aus..."
        terraform "$operation" "$@"
        local tf_exit_code=$?

        # Release lock explicitly
        release_lock
        trap - EXIT INT TERM

        return $tf_exit_code
    else
        # No lock needed, run directly
        terraform "$operation" "$@"
    fi
}

# Print help
print_help() {
    cat << EOF
Terraform Lock Wrapper für Ablage-System

Verwendung:
    $(basename "$0") <terraform-command> [options]
    $(basename "$0") --status          Zeigt Lock-Status
    $(basename "$0") --list            Listet alle aktiven Locks
    $(basename "$0") --force-unlock    Erzwingt Lock-Freigabe
    $(basename "$0") --cleanup         Bereinigt abgelaufene Locks
    $(basename "$0") --help            Zeigt diese Hilfe

Beispiele:
    $(basename "$0") plan
    $(basename "$0") apply -auto-approve
    $(basename "$0") destroy

Umgebungsvariablen:
    POSTGRES_HOST     PostgreSQL Host (default: localhost)
    POSTGRES_PORT     PostgreSQL Port (default: 5432)
    POSTGRES_DB       Datenbank Name (default: ablage_system)
    POSTGRES_USER     Datenbank User (default: ablage_admin)
    PGPASSWORD        Datenbank Passwort (required)
    TF_LOCK_TIMEOUT   Lock Timeout in Sekunden (default: 300)
    TF_WORKSPACE      Terraform Workspace (default: default)
    TF_LOCK_DEBUG     Debug-Ausgabe aktivieren (default: false)

EOF
}

# Main entry point
main() {
    check_prerequisites

    case "${1:-}" in
        --help|-h)
            print_help
            ;;
        --status)
            check_lock_status
            ;;
        --list)
            list_locks
            ;;
        --force-unlock)
            force_unlock
            ;;
        --cleanup)
            cleanup_locks
            ;;
        "")
            log_error "Kein Befehl angegeben. Verwende --help für Hilfe."
            exit 1
            ;;
        *)
            run_terraform "$@"
            ;;
    esac
}

main "$@"
