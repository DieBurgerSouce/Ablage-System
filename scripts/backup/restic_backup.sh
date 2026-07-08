#!/usr/bin/env bash
# =============================================================================
# restic 3-2-1-Backup - Ablage-System (Neuausrichtung Phase 7, Entscheidung 11)
# =============================================================================
# Sichert taeglich client-seitig verschluesselt in ZWEI restic-Repositories:
#   1. RESTIC_REPO_LOCAL   z. B. NAS-/USB-Pfad        (/mnt/nas/restic-ablage)
#   2. RESTIC_REPO_REMOTE  z. B. Hetzner Storage Box  (sftp:uXXXXXX@uXXXXXX.your-storagebox.de:/restic-ablage)
#
# Quellen (Staging unter ${RESTIC_STAGE_DIR}, stabile Pfade fuer Dedupe):
#   a) frischer pg_dump (custom format, via docker exec - Muster pg_backup.sh)
#   b) MinIO-Bucket-Export (mc mirror - Muster minio_backup.sh; Fallback:
#      neuester Snapshot aus ${BACKUP_BASE}/minio von minio_backup.sh)
#   c) Konfiguration: .env, infrastructure/nginx/ssl/, alembic-Version
#
# Retention je Repo: --keep-daily 14 --keep-weekly 8 --keep-monthly 24 --prune
# Snapshot-Tags: ablage, daily
#
# Aufruf:
#   bash scripts/backup/restic_backup.sh            # taegliches Backup
#   bash scripts/backup/restic_backup.sh --check    # woechentlich: restic check
#
# Pflicht-ENV:
#   RESTIC_PASSWORD_FILE   Datei mit dem restic-Passwort (chmod 600!)
#   RESTIC_REPO_LOCAL      und/oder RESTIC_REPO_REMOTE (mind. eines)
#   DB_PASSWORD bzw. POSTGRES_PASSWORD (fuer pg_dump)
#   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD (fuer mc mirror; nur wenn mc genutzt)
#
# Fehler-Semantik (ein Repo down => das andere wird trotzdem gesichert):
#   Exit 0 = alle konfigurierten Repos erfolgreich
#   Exit 1 = mindestens ein Repo fehlgeschlagen (Teilerfolg)
#   Exit 2 = fataler Fehler (Staging/pg_dump/Konfiguration) - nichts gesichert
#
# Einrichtung + Restore-Prozedur: scripts/backup/DR_RUNBOOK.md
# ("3-2-1-Backup mit restic"). restic-Installation siehe ebenda.
# =============================================================================
set -euo pipefail

# --- Konfiguration (ENV mit Defaults) ----------------------------------------
APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
BACKUP_BASE="${BACKUP_BASE:-/backup}"
RESTIC_STAGE_DIR="${RESTIC_STAGE_DIR:-${BACKUP_BASE}/restic-stage}"
LOG_DIR="${LOG_DIR:-${BACKUP_BASE}/logs}"
LOG_FILE="${LOG_DIR}/restic_backup.log"

RESTIC_REPO_LOCAL="${RESTIC_REPO_LOCAL:-}"
RESTIC_REPO_REMOTE="${RESTIC_REPO_REMOTE:-}"
RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-}"

# Retention (Entscheidung 11: lange Cloud-Historie, Quartals-Restore-Tests)
KEEP_DAILY="${RESTIC_KEEP_DAILY:-14}"
KEEP_WEEKLY="${RESTIC_KEEP_WEEKLY:-8}"
KEEP_MONTHLY="${RESTIC_KEEP_MONTHLY:-24}"

# PostgreSQL (Muster pg_backup.sh)
PG_CONTAINER_NAME="${PG_CONTAINER_NAME:-ablage-postgres}"
POSTGRES_DB="${POSTGRES_DB:-ablage_system}"
POSTGRES_USER="${POSTGRES_USER:-ablage_admin}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-${DB_PASSWORD:-}}"

# MinIO (Muster minio_backup.sh)
MINIO_ALIAS="${MINIO_ALIAS:-ablage}"
MINIO_CONTAINER_NAME="${MINIO_CONTAINER_NAME:-ablage-minio}"
MINIO_ENDPOINT="${MINIO_ENDPOINT_HOST:-http://127.0.0.1:9000}"
MINIO_ACCESS_KEY="${MINIO_ROOT_USER:-}"
MINIO_SECRET_KEY="${MINIO_ROOT_PASSWORD:-}"

# Konfig-Quellen
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
NGINX_SSL_DIR="${NGINX_SSL_DIR:-${APP_DIR}/infrastructure/nginx/ssl}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
MODE="backup"
[[ "${1:-}" == "--check" ]] && MODE="check"

# --- Logging -----------------------------------------------------------------
mkdir -p "${LOG_DIR}"

log() {
    local level="$1"; shift
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [${level}] $*" | tee -a "${LOG_FILE}"
}

die() {
    log "FATAL" "$*"
    log "FATAL" "restic-Backup abgebrochen - nichts gesichert. Log: ${LOG_FILE}"
    exit 2
}

# --- Vorbedingungen ----------------------------------------------------------
check_prerequisites() {
    if ! command -v restic &>/dev/null; then
        die "restic ist nicht installiert. Installation: siehe scripts/backup/DR_RUNBOOK.md (Abschnitt '3-2-1-Backup mit restic') - z. B. 'apt install restic' oder Binary von https://github.com/restic/restic/releases"
    fi
    if ! command -v docker &>/dev/null; then
        die "Docker ist nicht installiert oder nicht im PATH"
    fi
    if [[ -z "${RESTIC_PASSWORD_FILE}" || ! -f "${RESTIC_PASSWORD_FILE}" ]]; then
        die "RESTIC_PASSWORD_FILE ist nicht gesetzt oder Datei fehlt. Passwort-Datei anlegen (chmod 600) und OFFLINE-Kopie des Passworts sicher verwahren (ohne Passwort ist JEDES Repo unlesbar!)"
    fi
    if [[ -z "${RESTIC_REPO_LOCAL}" && -z "${RESTIC_REPO_REMOTE}" ]]; then
        die "Weder RESTIC_REPO_LOCAL noch RESTIC_REPO_REMOTE gesetzt - mindestens ein Repository konfigurieren"
    fi
    if [[ "${MODE}" == "backup" ]]; then
        if ! docker inspect --format='{{.State.Running}}' "${PG_CONTAINER_NAME}" 2>/dev/null | grep -q "true"; then
            die "Container '${PG_CONTAINER_NAME}' laeuft nicht - pg_dump nicht moeglich"
        fi
        if [[ -z "${POSTGRES_PASSWORD}" ]]; then
            die "Kein Datenbank-Passwort gesetzt (POSTGRES_PASSWORD oder DB_PASSWORD)"
        fi
    fi
}

# --- Quelle a: frischer pg_dump (Muster pg_backup.sh) --------------------------
stage_postgres() {
    local dump_file="${RESTIC_STAGE_DIR}/postgres/${POSTGRES_DB}.dump"
    mkdir -p "${RESTIC_STAGE_DIR}/postgres"
    log "INFO" "pg_dump gestartet: ${POSTGRES_DB} -> ${dump_file}"

    # -h 127.0.0.1: TCP statt Unix-Socket — die pg_hba-local-Zeile ist peer-auth
    # (OS-User "postgres" != DB-Rolle ablage_admin), TCP nutzt scram + PGPASSWORD.
    if ! docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${PG_CONTAINER_NAME}" \
        pg_dump -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
        --format=custom --no-owner --no-privileges --compress=6 \
        2>>"${LOG_FILE}" > "${dump_file}"; then
        die "pg_dump fehlgeschlagen"
    fi

    if [[ ! -s "${dump_file}" ]]; then
        die "pg_dump-Datei ist leer: ${dump_file}"
    fi

    # Integritaet wie in pg_backup.sh: pg_restore --list gegen den Dump
    if ! docker exec -i "${PG_CONTAINER_NAME}" pg_restore --list < "${dump_file}" > /dev/null 2>>"${LOG_FILE}"; then
        die "pg_dump-Integritaetspruefung fehlgeschlagen (pg_restore --list)"
    fi

    log "INFO" "pg_dump ok ($(du -h "${dump_file}" | cut -f1)), Integritaet verifiziert"
}

# --- Quelle b: MinIO-Bucket-Export (Muster minio_backup.sh) --------------------
# Rueckgabe ueber globale Variable MINIO_SOURCE_DIR (Pfad, der gesichert wird).
MINIO_SOURCE_DIR=""
stage_minio() {
    local stage_dir="${RESTIC_STAGE_DIR}/minio"

    # mc-Kommando bestimmen (Kaskade wie minio_backup.sh): Host-mc, wenn der
    # Endpoint vom Host erreichbar ist; sonst minio/mc-Container im Netz des
    # MinIO-Containers (MinIO published aus Sicherheitsgruenden keinen Host-Port).
    local mc_mode=""
    if command -v mc &>/dev/null && mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS_KEY}" "${MINIO_SECRET_KEY}" --api S3v4 >/dev/null 2>>"${LOG_FILE}" \
        && mc ls "${MINIO_ALIAS}/" >/dev/null 2>>"${LOG_FILE}"; then
        mc_mode="host"
    elif docker ps --format '{{.Names}}' | grep -qx "${MINIO_CONTAINER_NAME}"; then
        mc_mode="container"
    fi

    if [[ -n "${mc_mode}" ]]; then
        if [[ -z "${MINIO_ACCESS_KEY}" || -z "${MINIO_SECRET_KEY}" ]]; then
            die "MINIO_ROOT_USER/MINIO_ROOT_PASSWORD nicht gesetzt (fuer mc mirror noetig)"
        fi
        mkdir -p "${stage_dir}"

        # Einheitlicher mc-Aufruf: Host-Binary oder Wegwerf-Container mit
        # --network container:<minio> (127.0.0.1:9000 im Container-Netz) und
        # Stage als /stage-Mount. MSYS_NO_PATHCONV verhindert Git-Bash-Pfad-Mangling.
        run_mc() {
            if [[ "${mc_mode}" == "host" ]]; then
                mc "$@"
            else
                MSYS_NO_PATHCONV=1 docker run --rm \
                    --network "container:${MINIO_CONTAINER_NAME}" \
                    -e MC_HOST_${MINIO_ALIAS}="http://${MINIO_ACCESS_KEY}:${MINIO_SECRET_KEY}@127.0.0.1:9000" \
                    -v "${stage_dir}:/stage" \
                    --entrypoint mc minio/mc "$@"
            fi
        }
        # Stage-Zielpfad haengt vom Modus ab (Host-Pfad vs. Container-Mount)
        local stage_target="${stage_dir}"
        [[ "${mc_mode}" == "container" ]] && stage_target="/stage"

        log "INFO" "MinIO-Export via mc mirror (${mc_mode}) -> ${stage_dir}"
        local buckets
        buckets="$(run_mc ls "${MINIO_ALIAS}/" 2>>"${LOG_FILE}" | awk '{print $NF}' | tr -d '/\r' || true)"
        if [[ -z "${buckets}" ]]; then
            log "WARN" "Keine MinIO-Buckets gefunden - MinIO-Quelle wird uebersprungen"
            return 0
        fi
        local bucket
        for bucket in ${buckets}; do
            mkdir -p "${stage_dir}/${bucket}"
            # --remove: Stage spiegelt den Ist-Zustand; Historie liegt in den
            # restic-Snapshots selbst (nicht im Stage-Verzeichnis).
            if ! run_mc mirror --overwrite --remove "${MINIO_ALIAS}/${bucket}" "${stage_target}/${bucket}" >>"${LOG_FILE}" 2>&1; then
                die "mc mirror fehlgeschlagen fuer Bucket '${bucket}'"
            fi
            log "INFO" "  Bucket '${bucket}' gespiegelt ($(find "${stage_dir}/${bucket}" -type f | wc -l) Objekte)"
        done
        MINIO_SOURCE_DIR="${stage_dir}"
        return 0
    fi

    # Fallback: neuester Snapshot von minio_backup.sh / backup_full_task
    local latest_snapshot
    latest_snapshot="$(find "${BACKUP_BASE}/minio" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1 || true)"
    if [[ -n "${latest_snapshot}" ]]; then
        log "WARN" "mc nicht auf dem Host gefunden - nutze letzten minio_backup.sh-Snapshot: ${latest_snapshot}"
        MINIO_SOURCE_DIR="${latest_snapshot}"
        return 0
    fi

    die "MinIO-Quelle nicht verfuegbar: weder mc auf dem Host noch ein Snapshot unter ${BACKUP_BASE}/minio (zuerst minio_backup.sh laufen lassen oder mc installieren)"
}

# --- Quelle c: Konfiguration ---------------------------------------------------
stage_config() {
    local cfg_dir="${RESTIC_STAGE_DIR}/config"
    mkdir -p "${cfg_dir}"

    if [[ -f "${ENV_FILE}" ]]; then
        cp -f "${ENV_FILE}" "${cfg_dir}/.env"
        chmod 600 "${cfg_dir}/.env" || true
        log "INFO" "Konfig: .env eingesammelt (${ENV_FILE})"
    else
        log "WARN" "Konfig: ${ENV_FILE} nicht gefunden - wird uebersprungen"
    fi

    if [[ -d "${NGINX_SSL_DIR}" ]]; then
        rm -rf "${cfg_dir}/nginx-ssl"
        cp -r "${NGINX_SSL_DIR}" "${cfg_dir}/nginx-ssl"
        log "INFO" "Konfig: nginx-TLS-Material eingesammelt (${NGINX_SSL_DIR})"
    else
        log "WARN" "Konfig: ${NGINX_SSL_DIR} nicht gefunden - wird uebersprungen"
    fi

    # Alembic-Version aus der DB (fuer den Restore-Abgleich 'alembic upgrade head')
    local alembic_version
    alembic_version="$(docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${PG_CONTAINER_NAME}" \
        psql -h 127.0.0.1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -t -A \
        -c "SELECT version_num FROM alembic_version;" 2>>"${LOG_FILE}" || true)"
    if [[ -n "${alembic_version}" ]]; then
        printf 'alembic_version=%s\nzeitpunkt=%s\n' "${alembic_version}" "${TIMESTAMP}" \
            > "${cfg_dir}/alembic_version.txt"
        log "INFO" "Konfig: alembic-Version ${alembic_version} protokolliert"
    else
        log "WARN" "Konfig: alembic-Version konnte nicht gelesen werden"
    fi
}

# --- restic-Helfer -------------------------------------------------------------
ensure_repo() {
    local repo="$1"
    if restic -r "${repo}" --password-file "${RESTIC_PASSWORD_FILE}" cat config >/dev/null 2>&1; then
        return 0
    fi
    log "INFO" "Repository noch nicht initialisiert - fuehre 'restic init' aus: ${repo}"
    if ! restic -r "${repo}" --password-file "${RESTIC_PASSWORD_FILE}" init >>"${LOG_FILE}" 2>&1; then
        log "ERROR" "restic init fehlgeschlagen fuer ${repo} (Repo nicht erreichbar?)"
        return 1
    fi
    return 0
}

backup_to_repo() {
    local label="$1" repo="$2"
    shift 2
    local paths=("$@")

    log "INFO" "[${label}] Backup nach ${repo} gestartet (${#paths[@]} Quellpfade)"

    if ! ensure_repo "${repo}"; then
        log "ERROR" "[${label}] Repository nicht verfuegbar - dieses Repo wird uebersprungen"
        return 1
    fi

    if ! restic -r "${repo}" --password-file "${RESTIC_PASSWORD_FILE}" backup \
        --tag ablage --tag daily \
        "${paths[@]}" >>"${LOG_FILE}" 2>&1; then
        log "ERROR" "[${label}] restic backup fehlgeschlagen (Details: ${LOG_FILE})"
        return 1
    fi
    log "INFO" "[${label}] Snapshot erstellt"

    if ! restic -r "${repo}" --password-file "${RESTIC_PASSWORD_FILE}" forget \
        --tag ablage \
        --keep-daily "${KEEP_DAILY}" --keep-weekly "${KEEP_WEEKLY}" --keep-monthly "${KEEP_MONTHLY}" \
        --prune >>"${LOG_FILE}" 2>&1; then
        log "ERROR" "[${label}] restic forget/prune fehlgeschlagen (Snapshot selbst ist erstellt)"
        return 1
    fi
    log "INFO" "[${label}] Retention angewendet (daily=${KEEP_DAILY} weekly=${KEEP_WEEKLY} monthly=${KEEP_MONTHLY})"
    return 0
}

check_repo() {
    local label="$1" repo="$2"
    log "INFO" "[${label}] restic check gestartet: ${repo}"
    if ! restic -r "${repo}" --password-file "${RESTIC_PASSWORD_FILE}" check >>"${LOG_FILE}" 2>&1; then
        log "ERROR" "[${label}] restic check FEHLGESCHLAGEN - Repo-Integritaet pruefen! (${LOG_FILE})"
        return 1
    fi
    log "INFO" "[${label}] restic check ok"
    return 0
}

# --- Main ----------------------------------------------------------------------
main() {
    log "INFO" "=========================================="
    log "INFO" "restic 3-2-1-Backup gestartet (Modus: ${MODE})"
    log "INFO" "=========================================="

    check_prerequisites

    local failures=0 successes=0

    if [[ "${MODE}" == "check" ]]; then
        if [[ -n "${RESTIC_REPO_LOCAL}" ]]; then
            if check_repo "lokal" "${RESTIC_REPO_LOCAL}"; then successes=$((successes+1)); else failures=$((failures+1)); fi
        fi
        if [[ -n "${RESTIC_REPO_REMOTE}" ]]; then
            if check_repo "remote" "${RESTIC_REPO_REMOTE}"; then successes=$((successes+1)); else failures=$((failures+1)); fi
        fi
    else
        mkdir -p "${RESTIC_STAGE_DIR}"
        chmod 700 "${RESTIC_STAGE_DIR}" || true

        stage_postgres
        stage_minio
        stage_config

        # Quellpfade: Stage (pg_dump + config [+ minio, wenn via mc]) und ggf.
        # der externe MinIO-Fallback-Snapshot.
        local paths=("${RESTIC_STAGE_DIR}")
        if [[ -n "${MINIO_SOURCE_DIR}" && "${MINIO_SOURCE_DIR}" != "${RESTIC_STAGE_DIR}/minio" ]]; then
            paths+=("${MINIO_SOURCE_DIR}")
        fi

        if [[ -n "${RESTIC_REPO_LOCAL}" ]]; then
            if backup_to_repo "lokal" "${RESTIC_REPO_LOCAL}" "${paths[@]}"; then successes=$((successes+1)); else failures=$((failures+1)); fi
        else
            log "WARN" "RESTIC_REPO_LOCAL nicht gesetzt - lokales Repo uebersprungen (3-2-1 unvollstaendig!)"
        fi
        if [[ -n "${RESTIC_REPO_REMOTE}" ]]; then
            if backup_to_repo "remote" "${RESTIC_REPO_REMOTE}" "${paths[@]}"; then successes=$((successes+1)); else failures=$((failures+1)); fi
        else
            log "WARN" "RESTIC_REPO_REMOTE nicht gesetzt - Offsite-Repo uebersprungen (3-2-1 unvollstaendig!)"
        fi
    fi

    log "INFO" "=========================================="
    log "INFO" "Zusammenfassung: ${successes} Repo(s) erfolgreich, ${failures} fehlgeschlagen"
    if (( failures > 0 )); then
        log "ERROR" "restic-Backup mit Fehlern abgeschlossen - siehe ${LOG_FILE}"
        log "INFO" "=========================================="
        exit 1
    fi
    log "INFO" "restic-Backup erfolgreich abgeschlossen"
    log "INFO" "=========================================="
    exit 0
}

main "$@"
