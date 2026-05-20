#!/bin/bash
# =============================================================================
# Docker Volume Backup Script for Ablage-System
# Backs up all named Docker volumes using busybox tar
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
BACKUP_DIR="${BACKUP_BASE}/volumes"
LOG_DIR="${BACKUP_BASE}/logs"
LOG_FILE="${LOG_DIR}/volume_backup.log"
RETENTION_COUNT="${VOLUME_BACKUP_RETENTION:-3}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-ablage_system}"

# Volumes to backup (from docker-compose.yml)
# Excludes: postgres_data (handled by pg_backup.sh), redis_data (handled by redis_backup.sh),
#           minio_data (handled by minio_backup.sh)
VOLUMES_TO_BACKUP="${VOLUMES_TO_BACKUP:-uploads outputs backups model_cache clamav_data qdrant_data prometheus_data grafana_data loki_data alertmanager_data jaeger_data vault_data vault_logs}"

# Volumes to skip (already handled by dedicated backup scripts)
SKIP_VOLUMES="postgres_data redis_data redis_replica_data minio_data"

# -- Logging ------------------------------------------------------------------
mkdir -p "${LOG_DIR}" "${BACKUP_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] FEHLER: $1" >&2
}

# -- Helper: resolve full volume name ------------------------------------------
resolve_volume_name() {
    local short_name="$1"
    # Try with compose project prefix first
    local full_name="${COMPOSE_PROJECT}_${short_name}"
    if docker volume inspect "${full_name}" &>/dev/null; then
        echo "${full_name}"
        return 0
    fi
    # Try without prefix
    if docker volume inspect "${short_name}" &>/dev/null; then
        echo "${short_name}"
        return 0
    fi
    # Try common prefixes
    for prefix in "ablage-system" "ablagesystem" "ablage_system"; do
        full_name="${prefix}_${short_name}"
        if docker volume inspect "${full_name}" &>/dev/null; then
            echo "${full_name}"
            return 0
        fi
    done
    return 1
}

# -- Pre-flight checks --------------------------------------------------------
log "=== Docker-Volume-Backup gestartet ==="
log "Zielverzeichnis: ${BACKUP_DIR}"
log "Aufbewahrung: ${RETENTION_COUNT} Backups pro Volume"

# Check Docker availability
if ! docker info &>/dev/null; then
    log_error "Docker ist nicht verfuegbar oder laeuft nicht"
    exit 1
fi

# -- Discover volumes ----------------------------------------------------------
log "Ermittle Docker-Volumes..."
ERRORS=0
BACKED_UP=0
SKIPPED=0
TOTAL_SIZE=0

for vol_short in ${VOLUMES_TO_BACKUP}; do
    # Skip volumes handled by dedicated scripts
    if echo "${SKIP_VOLUMES}" | grep -qw "${vol_short}"; then
        log "  Ueberspringe '${vol_short}' (wird von dediziertem Script gesichert)"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    # Resolve the full Docker volume name
    VOLUME_NAME=$(resolve_volume_name "${vol_short}" 2>/dev/null) || true

    if [ -z "${VOLUME_NAME}" ]; then
        log "  Volume '${vol_short}' nicht gefunden, ueberspringe"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    VOLUME_DIR="${BACKUP_DIR}/${vol_short}"
    mkdir -p "${VOLUME_DIR}"

    BACKUP_FILE="${VOLUME_DIR}/${vol_short}_${TIMESTAMP}.tar.gz"
    log "Sichere Volume: ${VOLUME_NAME} -> ${BACKUP_FILE}"

    # Backup volume using busybox container
    if docker run --rm \
        -v "${VOLUME_NAME}:/source:ro" \
        -v "${VOLUME_DIR}:/backup" \
        busybox \
        tar czf "/backup/${vol_short}_${TIMESTAMP}.tar.gz" -C /source . 2>&1; then

        if [ -f "${BACKUP_FILE}" ]; then
            VOL_SIZE=$(du -sh "${BACKUP_FILE}" 2>/dev/null | cut -f1)
            log "  Volume '${vol_short}': ${VOL_SIZE}"
            BACKED_UP=$((BACKED_UP + 1))
        else
            log_error "  Backup-Datei nicht erstellt fuer '${vol_short}'"
            ERRORS=$((ERRORS + 1))
        fi
    else
        log_error "  Fehler beim Sichern von Volume '${vol_short}'"
        ERRORS=$((ERRORS + 1))
    fi
done

# -- Retention: keep only N backups per volume ---------------------------------
log "Wende Aufbewahrungsrichtlinie an (${RETENTION_COUNT} pro Volume)..."

for vol_short in ${VOLUMES_TO_BACKUP}; do
    VOLUME_DIR="${BACKUP_DIR}/${vol_short}"
    [ -d "${VOLUME_DIR}" ] || continue

    BACKUP_COUNT=$(find "${VOLUME_DIR}" -name "${vol_short}_*.tar.gz" -type f 2>/dev/null | wc -l)

    if [ "${BACKUP_COUNT}" -gt "${RETENTION_COUNT}" ]; then
        REMOVE_COUNT=$((BACKUP_COUNT - RETENTION_COUNT))
        find "${VOLUME_DIR}" -name "${vol_short}_*.tar.gz" -type f 2>/dev/null | sort | head -n "${REMOVE_COUNT}" | while read -r old_file; do
            log "  Loesche: ${vol_short}/$(basename "${old_file}")"
            rm -f "${old_file}"
        done
        log "  ${vol_short}: ${REMOVE_COUNT} alte Backups entfernt"
    fi
done

# -- Summary ------------------------------------------------------------------
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)

log "--- Zusammenfassung ---"
log "Volumes gesichert: ${BACKED_UP}"
log "Volumes uebersprungen: ${SKIPPED}"
log "Fehler: ${ERRORS}"
log "Gesamtgroesse: ${TOTAL_SIZE}"

if [ "${ERRORS}" -gt 0 ]; then
    log_error "Volume-Backup mit ${ERRORS} Fehler(n) abgeschlossen"
    log "=== Docker-Volume-Backup abgeschlossen (mit Fehlern) ==="
    exit 1
fi

log "=== Docker-Volume-Backup erfolgreich abgeschlossen ==="
exit 0
