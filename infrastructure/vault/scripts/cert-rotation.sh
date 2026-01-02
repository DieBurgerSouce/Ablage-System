#!/bin/bash
# =============================================================================
# Vault Certificate Rotation Script
# Ablage-System OCR - Infrastructure Hardening
# =============================================================================
#
# Dieses Script automatisiert die Zertifikats-Rotation fuer HashiCorp Vault.
# Es kann manuell oder via Cronjob ausgefuehrt werden.
#
# Voraussetzungen:
#   - HashiCorp Vault CLI installiert
#   - VAULT_ADDR und VAULT_TOKEN gesetzt
#   - OpenSSL installiert
#   - Vault PKI Secrets Engine aktiviert (optional, fuer CA-signierte Zertifikate)
#
# Verwendung:
#   ./cert-rotation.sh [--auto|--manual|--pki|--check|--help]
#
# Optionen:
#   --auto    Automatische Rotation mit selbst-signierten Zertifikaten
#   --manual  Interaktive Rotation mit Benutzerbestaetigung
#   --pki     Rotation via Vault PKI Secrets Engine (Enterprise)
#   --check   Prueft Zertifikatsablauf ohne Rotation
#   --help    Zeigt diese Hilfe
#
# Cronjob-Beispiel (monatliche Rotation):
#   0 2 1 * * /opt/ablage-system/infrastructure/vault/scripts/cert-rotation.sh --auto
#
# =============================================================================

set -euo pipefail

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_DIR="$(dirname "$SCRIPT_DIR")"
CERT_DIR="${VAULT_DIR}/config/certs"
BACKUP_DIR="${VAULT_DIR}/config/certs/backup"
LOG_FILE="${VAULT_DIR}/logs/cert-rotation.log"

# Zertifikatseinstellungen
CERT_VALIDITY_DAYS=365
CERT_KEY_SIZE=4096
CERT_COMMON_NAME="${VAULT_CERT_CN:-vault.ablage-system.local}"
CERT_ORGANIZATION="${VAULT_CERT_ORG:-Ablage-System}"
CERT_COUNTRY="${VAULT_CERT_COUNTRY:-DE}"
CERT_STATE="${VAULT_CERT_STATE:-Bavaria}"
CERT_LOCALITY="${VAULT_CERT_LOCALITY:-Munich}"

# Warnschwellen (Tage bis Ablauf)
WARNING_THRESHOLD=30
CRITICAL_THRESHOLD=7

# Farben fuer Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging-Funktion
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    mkdir -p "$(dirname "$LOG_FILE")"
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"

    case "$level" in
        "INFO")  echo -e "${BLUE}[INFO]${NC} $message" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC} $message" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} $message" ;;
        "OK")    echo -e "${GREEN}[OK]${NC} $message" ;;
    esac
}

# Hilfe anzeigen
show_help() {
    cat << 'EOF'
Vault Certificate Rotation Script
==================================

Verwendung:
  ./cert-rotation.sh [OPTION]

Optionen:
  --auto      Automatische Rotation mit selbst-signierten Zertifikaten
  --manual    Interaktive Rotation mit Benutzerbestaetigung
  --pki       Rotation via Vault PKI Secrets Engine
  --check     Prueft Zertifikatsablauf ohne Rotation
  --help      Zeigt diese Hilfe

Beispiele:
  # Zertifikatsstatus pruefen
  ./cert-rotation.sh --check

  # Automatische Rotation (fuer Cronjob)
  ./cert-rotation.sh --auto

  # Interaktive Rotation mit Bestaetigung
  ./cert-rotation.sh --manual

Cronjob-Einrichtung:
  # Monatliche Rotation am 1. um 02:00 Uhr
  0 2 1 * * /path/to/cert-rotation.sh --auto

  # Woechentliche Pruefung (ohne Rotation)
  0 8 * * 1 /path/to/cert-rotation.sh --check

Umgebungsvariablen:
  VAULT_ADDR          Vault Server URL
  VAULT_TOKEN         Vault Root/Admin Token (nur fuer PKI)
  VAULT_CERT_CN       Common Name fuer Zertifikat
  VAULT_CERT_ORG      Organisation fuer Zertifikat
  VAULT_CERT_COUNTRY  Land (2-Buchstaben Code)

EOF
}

# Voraussetzungen pruefen
check_prerequisites() {
    log "INFO" "Pruefe Voraussetzungen..."

    # OpenSSL
    if ! command -v openssl &> /dev/null; then
        log "ERROR" "OpenSSL ist nicht installiert"
        exit 1
    fi

    # Zertifikatsverzeichnis
    if [[ ! -d "$CERT_DIR" ]]; then
        log "WARN" "Zertifikatsverzeichnis existiert nicht, erstelle..."
        mkdir -p "$CERT_DIR"
    fi

    # Backup-Verzeichnis
    mkdir -p "$BACKUP_DIR"

    log "OK" "Voraussetzungen erfuellt"
}

# Aktuelles Zertifikat pruefen
check_certificate_expiry() {
    local cert_file="${CERT_DIR}/vault.crt"

    if [[ ! -f "$cert_file" ]]; then
        log "WARN" "Kein Zertifikat vorhanden: $cert_file"
        return 1
    fi

    # Ablaufdatum extrahieren
    local expiry_date
    expiry_date=$(openssl x509 -enddate -noout -in "$cert_file" 2>/dev/null | cut -d= -f2)

    if [[ -z "$expiry_date" ]]; then
        log "ERROR" "Konnte Ablaufdatum nicht lesen"
        return 1
    fi

    # Tage bis Ablauf berechnen
    local expiry_epoch
    local current_epoch
    local days_remaining

    expiry_epoch=$(date -d "$expiry_date" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$expiry_date" +%s 2>/dev/null)
    current_epoch=$(date +%s)
    days_remaining=$(( (expiry_epoch - current_epoch) / 86400 ))

    log "INFO" "Zertifikat laeuft ab am: $expiry_date"
    log "INFO" "Tage bis Ablauf: $days_remaining"

    # Status bewerten
    if [[ $days_remaining -lt 0 ]]; then
        log "ERROR" "Zertifikat ist ABGELAUFEN!"
        return 2
    elif [[ $days_remaining -lt $CRITICAL_THRESHOLD ]]; then
        log "ERROR" "KRITISCH: Zertifikat laeuft in $days_remaining Tagen ab!"
        return 3
    elif [[ $days_remaining -lt $WARNING_THRESHOLD ]]; then
        log "WARN" "WARNUNG: Zertifikat laeuft in $days_remaining Tagen ab"
        return 4
    else
        log "OK" "Zertifikat gueltig fuer weitere $days_remaining Tage"
        return 0
    fi
}

# Zertifikat-Backup erstellen
backup_certificates() {
    local backup_timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_path="${BACKUP_DIR}/${backup_timestamp}"

    mkdir -p "$backup_path"

    if [[ -f "${CERT_DIR}/vault.crt" ]]; then
        cp "${CERT_DIR}/vault.crt" "$backup_path/"
        log "INFO" "Zertifikat gesichert: $backup_path/vault.crt"
    fi

    if [[ -f "${CERT_DIR}/vault.key" ]]; then
        cp "${CERT_DIR}/vault.key" "$backup_path/"
        chmod 600 "$backup_path/vault.key"
        log "INFO" "Private Key gesichert: $backup_path/vault.key"
    fi

    if [[ -f "${CERT_DIR}/ca.crt" ]]; then
        cp "${CERT_DIR}/ca.crt" "$backup_path/"
        log "INFO" "CA-Zertifikat gesichert: $backup_path/ca.crt"
    fi

    # Alte Backups aufraumen (behalte letzte 10)
    local backup_count=$(ls -1d "$BACKUP_DIR"/*/ 2>/dev/null | wc -l)
    if [[ $backup_count -gt 10 ]]; then
        log "INFO" "Raeume alte Backups auf..."
        ls -1dt "$BACKUP_DIR"/*/ | tail -n +11 | xargs rm -rf
    fi

    log "OK" "Backup erstellt: $backup_path"
}

# Selbst-signiertes Zertifikat generieren
generate_self_signed_cert() {
    log "INFO" "Generiere neues selbst-signiertes Zertifikat..."

    # Private Key generieren
    openssl genrsa -out "${CERT_DIR}/vault.key.new" $CERT_KEY_SIZE 2>/dev/null
    chmod 600 "${CERT_DIR}/vault.key.new"

    # CSR erstellen
    openssl req -new \
        -key "${CERT_DIR}/vault.key.new" \
        -out "${CERT_DIR}/vault.csr" \
        -subj "/C=${CERT_COUNTRY}/ST=${CERT_STATE}/L=${CERT_LOCALITY}/O=${CERT_ORGANIZATION}/CN=${CERT_COMMON_NAME}" \
        2>/dev/null

    # Zertifikat signieren
    openssl x509 -req \
        -days $CERT_VALIDITY_DAYS \
        -in "${CERT_DIR}/vault.csr" \
        -signkey "${CERT_DIR}/vault.key.new" \
        -out "${CERT_DIR}/vault.crt.new" \
        -extfile <(printf "subjectAltName=DNS:vault,DNS:vault.ablage-system.local,DNS:localhost,IP:127.0.0.1") \
        2>/dev/null

    # CSR aufraumen
    rm -f "${CERT_DIR}/vault.csr"

    # Neue Zertifikate aktivieren
    mv "${CERT_DIR}/vault.key.new" "${CERT_DIR}/vault.key"
    mv "${CERT_DIR}/vault.crt.new" "${CERT_DIR}/vault.crt"

    # CA ist bei selbst-signierten Zertifikaten das Zertifikat selbst
    cp "${CERT_DIR}/vault.crt" "${CERT_DIR}/ca.crt"

    log "OK" "Neues Zertifikat generiert"

    # Zertifikatsdetails anzeigen
    log "INFO" "Zertifikatsdetails:"
    openssl x509 -in "${CERT_DIR}/vault.crt" -noout -text | grep -E "Subject:|Not Before|Not After|DNS:|IP:" | head -10
}

# Zertifikat via Vault PKI generieren (Enterprise)
generate_pki_cert() {
    log "INFO" "Generiere Zertifikat via Vault PKI Secrets Engine..."

    # Vault CLI pruefen
    if ! command -v vault &> /dev/null; then
        log "ERROR" "Vault CLI ist nicht installiert"
        exit 1
    fi

    # Vault-Verbindung pruefen
    if [[ -z "${VAULT_ADDR:-}" ]]; then
        log "ERROR" "VAULT_ADDR ist nicht gesetzt"
        exit 1
    fi

    if [[ -z "${VAULT_TOKEN:-}" ]]; then
        log "ERROR" "VAULT_TOKEN ist nicht gesetzt"
        exit 1
    fi

    # PKI-Zertifikat anfordern
    local pki_response
    pki_response=$(vault write -format=json pki_int/issue/ablage-system \
        common_name="${CERT_COMMON_NAME}" \
        alt_names="vault,vault.ablage-system.local,localhost" \
        ip_sans="127.0.0.1" \
        ttl="${CERT_VALIDITY_DAYS}d" \
        2>/dev/null)

    if [[ $? -ne 0 ]]; then
        log "ERROR" "PKI-Zertifikatsanforderung fehlgeschlagen"
        log "INFO" "Stelle sicher, dass PKI Secrets Engine konfiguriert ist"
        exit 1
    fi

    # Zertifikat und Key extrahieren
    echo "$pki_response" | jq -r '.data.certificate' > "${CERT_DIR}/vault.crt.new"
    echo "$pki_response" | jq -r '.data.private_key' > "${CERT_DIR}/vault.key.new"
    echo "$pki_response" | jq -r '.data.issuing_ca' > "${CERT_DIR}/ca.crt.new"

    chmod 600 "${CERT_DIR}/vault.key.new"

    # Neue Zertifikate aktivieren
    mv "${CERT_DIR}/vault.crt.new" "${CERT_DIR}/vault.crt"
    mv "${CERT_DIR}/vault.key.new" "${CERT_DIR}/vault.key"
    mv "${CERT_DIR}/ca.crt.new" "${CERT_DIR}/ca.crt"

    log "OK" "PKI-Zertifikat generiert"
}

# Vault neustarten
restart_vault() {
    log "INFO" "Starte Vault Container neu..."

    # Docker-Compose verwenden falls verfuegbar
    if command -v docker-compose &> /dev/null; then
        cd "$VAULT_DIR"
        docker-compose restart vault 2>/dev/null && \
            log "OK" "Vault Container neugestartet" || \
            log "WARN" "Docker-Compose Neustart fehlgeschlagen"
    elif command -v docker &> /dev/null; then
        docker restart ablage-vault 2>/dev/null && \
            log "OK" "Vault Container neugestartet" || \
            log "WARN" "Docker Neustart fehlgeschlagen"
    else
        log "WARN" "Docker nicht gefunden - manueller Neustart erforderlich"
    fi

    # Warten auf Vault
    log "INFO" "Warte auf Vault-Bereitschaft..."
    sleep 10

    # Health-Check
    if curl -sk "https://127.0.0.1:8200/v1/sys/health" &>/dev/null; then
        log "OK" "Vault ist bereit"
    else
        log "WARN" "Vault Health-Check fehlgeschlagen - manuelle Pruefung erforderlich"
    fi
}

# Automatische Rotation
auto_rotate() {
    log "INFO" "=== Automatische Zertifikats-Rotation gestartet ==="

    check_prerequisites

    # Zertifikat pruefen
    local check_result
    set +e
    check_certificate_expiry
    check_result=$?
    set -e

    # Rotation nur bei Warnung oder kritischem Status
    if [[ $check_result -eq 0 ]]; then
        log "INFO" "Zertifikat ist noch gueltig, keine Rotation noetig"
        return 0
    fi

    log "INFO" "Starte Zertifikats-Rotation..."
    backup_certificates
    generate_self_signed_cert
    restart_vault

    log "OK" "=== Zertifikats-Rotation abgeschlossen ==="
}

# Manuelle Rotation
manual_rotate() {
    log "INFO" "=== Manuelle Zertifikats-Rotation ==="

    check_prerequisites
    check_certificate_expiry || true

    echo ""
    echo -e "${YELLOW}Soll das Zertifikat jetzt rotiert werden? (j/N)${NC}"
    read -r confirm

    if [[ "$confirm" =~ ^[jJyY]$ ]]; then
        backup_certificates
        generate_self_signed_cert

        echo ""
        echo -e "${YELLOW}Vault Container jetzt neustarten? (j/N)${NC}"
        read -r restart_confirm

        if [[ "$restart_confirm" =~ ^[jJyY]$ ]]; then
            restart_vault
        else
            log "INFO" "Vault muss manuell neugestartet werden"
        fi

        log "OK" "=== Manuelle Rotation abgeschlossen ==="
    else
        log "INFO" "Rotation abgebrochen"
    fi
}

# Nur Check
check_only() {
    log "INFO" "=== Zertifikats-Pruefung ==="
    check_prerequisites

    set +e
    check_certificate_expiry
    local result=$?
    set -e

    echo ""
    echo "Zertifikatsdetails:"
    echo "==================="

    if [[ -f "${CERT_DIR}/vault.crt" ]]; then
        openssl x509 -in "${CERT_DIR}/vault.crt" -noout -text | \
            grep -E "Subject:|Issuer:|Not Before|Not After|DNS:|IP:" | \
            sed 's/^[[:space:]]*//'
    fi

    exit $result
}

# PKI-Rotation
pki_rotate() {
    log "INFO" "=== PKI-basierte Zertifikats-Rotation ==="

    check_prerequisites
    backup_certificates
    generate_pki_cert
    restart_vault

    log "OK" "=== PKI-Rotation abgeschlossen ==="
}

# Hauptprogramm
main() {
    case "${1:-}" in
        --auto)
            auto_rotate
            ;;
        --manual)
            manual_rotate
            ;;
        --pki)
            pki_rotate
            ;;
        --check)
            check_only
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo "Verwendung: $0 [--auto|--manual|--pki|--check|--help]"
            echo "Nutze --help fuer Details"
            exit 1
            ;;
    esac
}

main "$@"
