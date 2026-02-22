#!/bin/bash
# =============================================================================
# Backup Metrics Exporter for Prometheus Textfile Collector
# Reads backup logs and outputs Prometheus-format metrics to .prom file
#
# Usage: Run via cron after each backup_all.sh execution
#   */5 * * * * /path/to/backup_metrics.sh
# =============================================================================
set -euo pipefail

# -- Configuration (override via environment) ---------------------------------
BACKUP_BASE="${BACKUP_BASE:-/backup}"
LOG_DIR="${BACKUP_BASE}/logs"
METRICS_DIR="${BACKUP_BASE}/metrics"
METRICS_FILE="${METRICS_DIR}/backup_metrics.prom"
METRICS_TEMP="${METRICS_DIR}/backup_metrics.prom.tmp"

# -- Ensure directories exist ------------------------------------------------
mkdir -p "${METRICS_DIR}"

# -- Helper functions ---------------------------------------------------------

# Get Unix timestamp of the latest successful backup for a given type
get_last_success_timestamp() {
    local backup_type="$1"
    local log_file="${LOG_DIR}/${backup_type}_backup.log"
    local backup_dir=""

    case "${backup_type}" in
        postgresql) backup_dir="${BACKUP_BASE}/postgres" ;;
        minio)      backup_dir="${BACKUP_BASE}/minio" ;;
        redis)      backup_dir="${BACKUP_BASE}/redis" ;;
        volumes)    backup_dir="${BACKUP_BASE}/volumes" ;;
    esac

    # Find newest file in the backup directory
    if [ -d "${backup_dir}" ]; then
        local newest_file
        newest_file=$(find "${backup_dir}" -type f -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
        if [ -n "${newest_file}" ]; then
            # Truncate to integer
            echo "${newest_file%.*}"
            return
        fi
    fi

    echo "0"
}

# Get size in bytes of the latest backup for a given type
get_latest_backup_size() {
    local backup_type="$1"
    local backup_dir=""

    case "${backup_type}" in
        postgresql) backup_dir="${BACKUP_BASE}/postgres" ;;
        minio)      backup_dir="${BACKUP_BASE}/minio" ;;
        redis)      backup_dir="${BACKUP_BASE}/redis" ;;
        volumes)    backup_dir="${BACKUP_BASE}/volumes" ;;
    esac

    if [ -d "${backup_dir}" ]; then
        local total_size
        total_size=$(du -sb "${backup_dir}" 2>/dev/null | cut -f1)
        echo "${total_size:-0}"
    else
        echo "0"
    fi
}

# Get duration from most recent backup summary for a given type
get_last_duration() {
    local backup_type="$1"
    local summary_file

    # Find most recent summary file
    summary_file=$(find "${LOG_DIR}" -name "backup_summary_*.txt" -type f 2>/dev/null | sort -r | head -1)

    if [ -z "${summary_file}" ]; then
        echo "0"
        return
    fi

    # Parse duration from summary (format: "PostgreSQL: ERFOLGREICH (42s, 1.2G)")
    local type_label=""
    case "${backup_type}" in
        postgresql) type_label="PostgreSQL" ;;
        minio)      type_label="MinIO" ;;
        redis)      type_label="Redis" ;;
        volumes)    type_label="Docker-Vol." ;;
    esac

    local duration
    duration=$(grep "${type_label}" "${summary_file}" 2>/dev/null \
        | grep -oP '\((\d+)s' \
        | grep -oP '\d+' \
        | head -1)

    echo "${duration:-0}"
}

# Count retained backups for a given type and period
count_retained_backups() {
    local backup_type="$1"
    local period="$2"
    local backup_dir=""

    case "${backup_type}" in
        postgresql) backup_dir="${BACKUP_BASE}/postgres" ;;
        minio)      backup_dir="${BACKUP_BASE}/minio" ;;
        redis)      backup_dir="${BACKUP_BASE}/redis" ;;
        volumes)    backup_dir="${BACKUP_BASE}/volumes" ;;
    esac

    if [ ! -d "${backup_dir}" ]; then
        echo "0"
        return
    fi

    case "${period}" in
        daily)
            # Files from last 7 days (daily backups)
            find "${backup_dir}" -type f -name "*daily*" 2>/dev/null | wc -l
            ;;
        weekly)
            # Files marked as weekly
            find "${backup_dir}" -type f -name "*weekly*" 2>/dev/null | wc -l
            ;;
        monthly)
            # Files marked as monthly
            find "${backup_dir}" -type f -name "*monthly*" 2>/dev/null | wc -l
            ;;
        *)
            # Fallback: count all files
            find "${backup_dir}" -maxdepth 1 -type f 2>/dev/null | wc -l
            ;;
    esac
}

# Get restore test result from most recent report
get_restore_test_result() {
    local report_file
    report_file=$(find "${LOG_DIR}" -name "restore_test_report_*.txt" -type f 2>/dev/null | sort -r | head -1)

    if [ -z "${report_file}" ]; then
        echo "0"
        return
    fi

    if grep -q "GESAMTERGEBNIS: BESTANDEN" "${report_file}" 2>/dev/null; then
        echo "1"
    else
        echo "0"
    fi
}

# Get restore test timestamp from most recent report
get_restore_test_timestamp() {
    local report_file
    report_file=$(find "${LOG_DIR}" -name "restore_test_report_*.txt" -type f 2>/dev/null | sort -r | head -1)

    if [ -z "${report_file}" ]; then
        echo "0"
        return
    fi

    local file_mtime
    file_mtime=$(stat -c %Y "${report_file}" 2>/dev/null || stat -f %m "${report_file}" 2>/dev/null || echo "0")
    echo "${file_mtime}"
}

# =============================================================================
# Generate Prometheus Metrics
# =============================================================================

{
    echo "# HELP backup_last_success_timestamp Unix timestamp of last successful backup"
    echo "# TYPE backup_last_success_timestamp gauge"

    for btype in postgresql minio redis volumes; do
        ts=$(get_last_success_timestamp "${btype}")
        echo "backup_last_success_timestamp{type=\"${btype}\"} ${ts}"
    done

    echo ""
    echo "# HELP backup_size_bytes Total size of backup directory in bytes"
    echo "# TYPE backup_size_bytes gauge"

    for btype in postgresql minio redis volumes; do
        size=$(get_latest_backup_size "${btype}")
        echo "backup_size_bytes{type=\"${btype}\"} ${size}"
    done

    echo ""
    echo "# HELP backup_duration_seconds Duration of last backup in seconds"
    echo "# TYPE backup_duration_seconds gauge"

    for btype in postgresql minio redis volumes; do
        dur=$(get_last_duration "${btype}")
        echo "backup_duration_seconds{type=\"${btype}\"} ${dur}"
    done

    echo ""
    echo "# HELP backup_retention_count Number of retained backup files per type and period"
    echo "# TYPE backup_retention_count gauge"

    for btype in postgresql minio redis volumes; do
        for period in daily weekly monthly; do
            count=$(count_retained_backups "${btype}" "${period}")
            echo "backup_retention_count{type=\"${btype}\",period=\"${period}\"} ${count}"
        done
    done

    echo ""
    echo "# HELP backup_restore_test_success 1 if last restore test passed, 0 if failed"
    echo "# TYPE backup_restore_test_success gauge"
    restore_result=$(get_restore_test_result)
    echo "backup_restore_test_success ${restore_result}"

    echo ""
    echo "# HELP backup_restore_test_timestamp Unix timestamp of last restore test"
    echo "# TYPE backup_restore_test_timestamp gauge"
    restore_ts=$(get_restore_test_timestamp)
    echo "backup_restore_test_timestamp ${restore_ts}"

} > "${METRICS_TEMP}"

# Atomic replace to prevent Prometheus from reading partial files
mv "${METRICS_TEMP}" "${METRICS_FILE}"
