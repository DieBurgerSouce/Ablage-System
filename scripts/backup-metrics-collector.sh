#!/bin/bash
# =============================================================================
# Ablage-System Backup Metrics Collector
# =============================================================================
# Sammelt und emittiert Prometheus-Metriken fuer Backup-Operationen.
#
# Verwendung:
#   backup-metrics-collector.sh emit_backup_success <type> <duration_s> <size_bytes>
#   backup-metrics-collector.sh emit_backup_failure <type> <duration_s> <error_msg>
#   backup-metrics-collector.sh emit_validation_success <duration_s>
#   backup-metrics-collector.sh emit_validation_failure <duration_s> <error_msg>
#   backup-metrics-collector.sh emit_remote_sync_success <duration_s>
#   backup-metrics-collector.sh emit_remote_sync_failure <error_msg>
#   backup-metrics-collector.sh emit_remote_sync_retry <attempt> <max>
#   backup-metrics-collector.sh emit_encryption_success
#   backup-metrics-collector.sh emit_encryption_failure <error_msg>
#   backup-metrics-collector.sh update_disk_usage
#   backup-metrics-collector.sh update_file_counts
#
# Konfiguration:
#   METRICS_FILE: Pfad zur Prometheus Textfile (default: /var/lib/prometheus/node-exporter/ablage_backup.prom)
#   BACKUP_DIR: Pfad zum Backup-Verzeichnis (default: /var/backups/ablage)
#   API_URL: URL zur Ablage-System API (optional, fuer Push-Metriken)
#
# =============================================================================

set -e

# Konfiguration
METRICS_FILE="${METRICS_FILE:-/var/lib/prometheus/node-exporter/ablage_backup.prom}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/ablage}"
API_URL="${API_URL:-}"
TIMESTAMP=$(date +%s)

# Temporaere Datei fuer atomisches Schreiben
TEMP_FILE=$(mktemp)
trap "rm -f $TEMP_FILE" EXIT

# =============================================================================
# Hilfsfunktionen
# =============================================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >&2
}

# Initialisiere Metriken-Datei wenn nicht vorhanden
init_metrics_file() {
    local dir=$(dirname "$METRICS_FILE")
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir" 2>/dev/null || true
    fi

    if [ ! -f "$METRICS_FILE" ]; then
        touch "$METRICS_FILE" 2>/dev/null || {
            log "WARNUNG: Kann Metriken-Datei nicht erstellen: $METRICS_FILE"
            return 1
        }
    fi
    return 0
}

# Schreibe Metrik in Datei (Prometheus Textfile Format)
write_metric() {
    local metric_name="$1"
    local labels="$2"
    local value="$3"
    local help_text="$4"
    local type="$5"

    {
        if [ -n "$help_text" ]; then
            echo "# HELP $metric_name $help_text"
        fi
        if [ -n "$type" ]; then
            echo "# TYPE $metric_name $type"
        fi
        if [ -n "$labels" ]; then
            echo "${metric_name}{${labels}} $value"
        else
            echo "$metric_name $value"
        fi
    } >> "$TEMP_FILE"
}

# Aktualisiere einzelne Metrik in bestehender Datei
update_single_metric() {
    local metric_name="$1"
    local labels="$2"
    local value="$3"

    local pattern
    if [ -n "$labels" ]; then
        pattern="${metric_name}{${labels}}"
    else
        pattern="$metric_name "
    fi

    # Entferne alte Metrik (falls vorhanden) und fuege neue hinzu
    if [ -f "$METRICS_FILE" ]; then
        grep -v "^${metric_name}" "$METRICS_FILE" > "$TEMP_FILE" 2>/dev/null || true
    fi

    if [ -n "$labels" ]; then
        echo "${metric_name}{${labels}} $value" >> "$TEMP_FILE"
    else
        echo "$metric_name $value" >> "$TEMP_FILE"
    fi

    mv "$TEMP_FILE" "$METRICS_FILE"
}

# Inkrementiere Counter
increment_counter() {
    local metric_name="$1"
    local labels="$2"

    local current=0
    local pattern
    if [ -n "$labels" ]; then
        pattern="${metric_name}{${labels}}"
    else
        pattern="^${metric_name} "
    fi

    if [ -f "$METRICS_FILE" ]; then
        current=$(grep "$pattern" "$METRICS_FILE" 2>/dev/null | awk '{print $NF}' | head -1)
        current=${current:-0}
    fi

    local new_value=$((current + 1))
    update_single_metric "$metric_name" "$labels" "$new_value"
}

# =============================================================================
# Backup-Metriken
# =============================================================================

emit_backup_success() {
    local backup_type="$1"
    local duration_s="$2"
    local size_bytes="$3"

    log "Backup erfolgreich: type=$backup_type, duration=${duration_s}s, size=${size_bytes}B"

    init_metrics_file || return 1

    # Letzter Erfolg Zeitstempel
    update_single_metric "ablage_backup_last_success_timestamp" "backup_type=\"$backup_type\"" "$TIMESTAMP"

    # Erfolgs-Counter inkrementieren
    increment_counter "ablage_backup_success_total" "backup_type=\"$backup_type\""

    # Groesse aktualisieren
    update_single_metric "ablage_backup_size_bytes" "backup_type=\"$backup_type\"" "$size_bytes"

    log "Metriken aktualisiert: $METRICS_FILE"
}

emit_backup_failure() {
    local backup_type="$1"
    local duration_s="$2"
    local error_msg="$3"

    log "Backup fehlgeschlagen: type=$backup_type, duration=${duration_s}s, error=$error_msg"

    init_metrics_file || return 1

    # Letzter Fehler Zeitstempel
    update_single_metric "ablage_backup_last_failure_timestamp" "backup_type=\"$backup_type\"" "$TIMESTAMP"

    # Fehler-Counter inkrementieren
    increment_counter "ablage_backup_failure_total" "backup_type=\"$backup_type\""

    log "Metriken aktualisiert: $METRICS_FILE"
}

# =============================================================================
# Validierungs-Metriken
# =============================================================================

emit_validation_success() {
    local duration_s="$1"

    log "Validierung erfolgreich: duration=${duration_s}s"

    init_metrics_file || return 1

    update_single_metric "ablage_backup_validation_last_run_timestamp" "" "$TIMESTAMP"
    increment_counter "ablage_backup_validation_success_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

emit_validation_failure() {
    local duration_s="$1"
    local error_msg="$2"

    log "Validierung fehlgeschlagen: duration=${duration_s}s, error=$error_msg"

    init_metrics_file || return 1

    update_single_metric "ablage_backup_validation_last_run_timestamp" "" "$TIMESTAMP"
    increment_counter "ablage_backup_validation_failure_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

# =============================================================================
# Remote-Sync Metriken
# =============================================================================

emit_remote_sync_success() {
    local duration_s="$1"

    log "Remote-Sync erfolgreich: duration=${duration_s}s"

    init_metrics_file || return 1

    increment_counter "ablage_backup_remote_sync_success_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

emit_remote_sync_failure() {
    local error_msg="$1"

    log "Remote-Sync fehlgeschlagen: error=$error_msg"

    init_metrics_file || return 1

    increment_counter "ablage_backup_remote_sync_failure_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

emit_remote_sync_retry() {
    local attempt="$1"
    local max_attempts="$2"

    log "Remote-Sync Wiederholung: Versuch $attempt von $max_attempts"

    init_metrics_file || return 1

    increment_counter "ablage_backup_remote_sync_retry_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

# =============================================================================
# Verschluesselungs-Metriken
# =============================================================================

emit_encryption_success() {
    log "Verschluesselung erfolgreich"

    init_metrics_file || return 1

    increment_counter "ablage_backup_encryption_success_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

emit_encryption_failure() {
    local error_msg="$1"

    log "Verschluesselung fehlgeschlagen: error=$error_msg"

    init_metrics_file || return 1

    increment_counter "ablage_backup_encryption_failure_total" ""

    log "Metriken aktualisiert: $METRICS_FILE"
}

# =============================================================================
# Speicherplatz-Metriken
# =============================================================================

update_disk_usage() {
    log "Aktualisiere Speicherplatz-Metriken fuer: $BACKUP_DIR"

    init_metrics_file || return 1

    if [ ! -d "$BACKUP_DIR" ]; then
        log "WARNUNG: Backup-Verzeichnis existiert nicht: $BACKUP_DIR"
        return 1
    fi

    # Hole Speicherplatz-Info
    local disk_info
    disk_info=$(df -B1 "$BACKUP_DIR" | tail -1)

    local total=$(echo "$disk_info" | awk '{print $2}')
    local used=$(echo "$disk_info" | awk '{print $3}')
    local free=$(echo "$disk_info" | awk '{print $4}')

    update_single_metric "ablage_backup_disk_total_bytes" "" "$total"
    update_single_metric "ablage_backup_disk_usage_bytes" "" "$used"
    update_single_metric "ablage_backup_disk_free_bytes" "" "$free"

    log "Speicherplatz: total=${total}B, used=${used}B, free=${free}B"
}

update_file_counts() {
    log "Zaehle Backup-Dateien in: $BACKUP_DIR"

    init_metrics_file || return 1

    if [ ! -d "$BACKUP_DIR" ]; then
        log "WARNUNG: Backup-Verzeichnis existiert nicht: $BACKUP_DIR"
        return 1
    fi

    # Zaehle Dateien nach Typ
    local postgres_count=0
    local redis_count=0
    local minio_count=0
    local config_count=0

    [ -d "$BACKUP_DIR/postgres" ] && postgres_count=$(find "$BACKUP_DIR/postgres" -name "*.sql.gz" -type f 2>/dev/null | wc -l)
    [ -d "$BACKUP_DIR/redis" ] && redis_count=$(find "$BACKUP_DIR/redis" -name "*.rdb" -type f 2>/dev/null | wc -l)
    [ -d "$BACKUP_DIR/minio" ] && minio_count=$(find "$BACKUP_DIR/minio" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    [ -d "$BACKUP_DIR/config" ] && config_count=$(find "$BACKUP_DIR/config" -name "*.tar.gz" -type f 2>/dev/null | wc -l)

    update_single_metric "ablage_backup_file_count" "backup_type=\"postgres\"" "$postgres_count"
    update_single_metric "ablage_backup_file_count" "backup_type=\"redis\"" "$redis_count"
    update_single_metric "ablage_backup_file_count" "backup_type=\"minio\"" "$minio_count"
    update_single_metric "ablage_backup_file_count" "backup_type=\"config\"" "$config_count"

    log "Dateien: postgres=$postgres_count, redis=$redis_count, minio=$minio_count, config=$config_count"
}

# =============================================================================
# Alle Metriken aktualisieren
# =============================================================================

update_all() {
    log "Aktualisiere alle Metriken..."
    update_disk_usage
    update_file_counts
    log "Alle Metriken aktualisiert"
}

# =============================================================================
# Hauptprogramm
# =============================================================================

show_usage() {
    cat <<EOF
Ablage-System Backup Metrics Collector

Verwendung:
    $0 <command> [arguments]

Befehle:
    emit_backup_success <type> <duration_s> <size_bytes>
        Erfasse erfolgreiches Backup

    emit_backup_failure <type> <duration_s> <error_msg>
        Erfasse fehlgeschlagenes Backup

    emit_validation_success <duration_s>
        Erfasse erfolgreiche Validierung

    emit_validation_failure <duration_s> <error_msg>
        Erfasse fehlgeschlagene Validierung

    emit_remote_sync_success <duration_s>
        Erfasse erfolgreiche Remote-Synchronisation

    emit_remote_sync_failure <error_msg>
        Erfasse fehlgeschlagene Remote-Synchronisation

    emit_remote_sync_retry <attempt> <max>
        Erfasse Wiederholungsversuch

    emit_encryption_success
        Erfasse erfolgreiche Verschluesselung

    emit_encryption_failure <error_msg>
        Erfasse fehlgeschlagene Verschluesselung

    update_disk_usage
        Aktualisiere Speicherplatz-Metriken

    update_file_counts
        Aktualisiere Datei-Zaehler

    update_all
        Aktualisiere alle Metriken

Umgebungsvariablen:
    METRICS_FILE    Pfad zur Metriken-Datei (default: /var/lib/prometheus/node-exporter/ablage_backup.prom)
    BACKUP_DIR      Pfad zum Backup-Verzeichnis (default: /var/backups/ablage)

Beispiele:
    $0 emit_backup_success postgres 120 1073741824
    $0 emit_backup_failure minio 30 "Connection refused"
    $0 update_all
EOF
}

main() {
    local command="${1:-}"
    shift 2>/dev/null || true

    case "$command" in
        emit_backup_success)
            [ $# -ge 3 ] || { log "FEHLER: emit_backup_success erfordert 3 Argumente"; exit 1; }
            emit_backup_success "$1" "$2" "$3"
            ;;
        emit_backup_failure)
            [ $# -ge 3 ] || { log "FEHLER: emit_backup_failure erfordert 3 Argumente"; exit 1; }
            emit_backup_failure "$1" "$2" "$3"
            ;;
        emit_validation_success)
            [ $# -ge 1 ] || { log "FEHLER: emit_validation_success erfordert 1 Argument"; exit 1; }
            emit_validation_success "$1"
            ;;
        emit_validation_failure)
            [ $# -ge 2 ] || { log "FEHLER: emit_validation_failure erfordert 2 Argumente"; exit 1; }
            emit_validation_failure "$1" "$2"
            ;;
        emit_remote_sync_success)
            [ $# -ge 1 ] || { log "FEHLER: emit_remote_sync_success erfordert 1 Argument"; exit 1; }
            emit_remote_sync_success "$1"
            ;;
        emit_remote_sync_failure)
            [ $# -ge 1 ] || { log "FEHLER: emit_remote_sync_failure erfordert 1 Argument"; exit 1; }
            emit_remote_sync_failure "$1"
            ;;
        emit_remote_sync_retry)
            [ $# -ge 2 ] || { log "FEHLER: emit_remote_sync_retry erfordert 2 Argumente"; exit 1; }
            emit_remote_sync_retry "$1" "$2"
            ;;
        emit_encryption_success)
            emit_encryption_success
            ;;
        emit_encryption_failure)
            [ $# -ge 1 ] || { log "FEHLER: emit_encryption_failure erfordert 1 Argument"; exit 1; }
            emit_encryption_failure "$1"
            ;;
        update_disk_usage)
            update_disk_usage
            ;;
        update_file_counts)
            update_file_counts
            ;;
        update_all)
            update_all
            ;;
        help|--help|-h)
            show_usage
            exit 0
            ;;
        "")
            show_usage
            exit 1
            ;;
        *)
            log "FEHLER: Unbekannter Befehl: $command"
            show_usage
            exit 1
            ;;
    esac
}

main "$@"
