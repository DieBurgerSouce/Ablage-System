#!/bin/bash
# Vollständiges Vault Setup Script - Ablage-System OCR
# Initialisiert Vault mit allen Policies, Engines und Authentifizierung
#
# Verwendung:
#   ./setup-vault-complete.sh setup    # Vollständige Einrichtung
#   ./setup-vault-complete.sh unseal   # Vault entsperren
#   ./setup-vault-complete.sh status   # Status anzeigen
#   ./setup-vault-complete.sh rotate   # Secrets rotieren

set -e

# Konfiguration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ADDR="${VAULT_ADDR:-https://localhost:8200}"
VAULT_CACERT="${VAULT_CACERT:-$SCRIPT_DIR/config/certs/ca.crt}"
POLICIES_DIR="$SCRIPT_DIR/policies"
CONFIG_DIR="$SCRIPT_DIR/config"
SECRETS_DIR="$SCRIPT_DIR/.secrets"

# Erstelle Secrets-Verzeichnis mit sicheren Berechtigungen
mkdir -p "$SECRETS_DIR"
chmod 700 "$SECRETS_DIR"

# Farben
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Vault CLI mit TLS-Konfiguration
vault_cmd() {
    VAULT_ADDR="$VAULT_ADDR" VAULT_CACERT="$VAULT_CACERT" vault "$@"
}

# Prüfe Voraussetzungen
check_prerequisites() {
    log_info "Prüfe Voraussetzungen..."

    # Prüfe ob Vault CLI installiert ist
    if ! command -v vault &> /dev/null; then
        log_error "Vault CLI nicht gefunden. Installation: https://www.vaultproject.io/downloads"
        exit 1
    fi

    # Prüfe ob jq installiert ist
    if ! command -v jq &> /dev/null; then
        log_error "jq nicht gefunden. Installation: apt-get install jq"
        exit 1
    fi

    # Prüfe ob Zertifikate existieren
    if [[ ! -f "$VAULT_CACERT" ]]; then
        log_warn "CA-Zertifikat nicht gefunden: $VAULT_CACERT"
        log_info "Generiere Zertifikate..."
        "$CONFIG_DIR/certs/generate-certs.sh"
    fi

    log_success "Voraussetzungen erfüllt"
}

# Warte auf Vault
wait_for_vault() {
    log_info "Warte auf Vault..."

    local max_attempts=30
    local attempt=1

    while [[ $attempt -le $max_attempts ]]; do
        if curl -sk "$VAULT_ADDR/v1/sys/health" > /dev/null 2>&1; then
            log_success "Vault erreichbar"
            return 0
        fi
        echo -n "."
        sleep 2
        ((attempt++))
    done

    log_error "Vault nicht erreichbar nach $max_attempts Versuchen"
    exit 1
}

# Initialisiere Vault
initialize_vault() {
    log_info "Initialisiere Vault..."

    local init_file="$SECRETS_DIR/vault-init.json"

    # Prüfe ob bereits initialisiert
    local init_status=$(curl -sk "$VAULT_ADDR/v1/sys/init" | jq -r '.initialized')

    if [[ "$init_status" == "true" ]]; then
        log_warn "Vault ist bereits initialisiert"
        return 0
    fi

    # Initialisiere mit 5 Schlüsseln, Schwelle 3
    local init_response=$(curl -sk -X PUT \
        -d '{"secret_shares": 5, "secret_threshold": 3}' \
        "$VAULT_ADDR/v1/sys/init")

    # Speichere Initialisierungsdaten
    echo "$init_response" | jq '.' > "$init_file"
    chmod 600 "$init_file"

    # Extrahiere und speichere Unseal-Schlüssel
    echo "$init_response" | jq -r '.keys[]' > "$SECRETS_DIR/unseal-keys.txt"
    chmod 600 "$SECRETS_DIR/unseal-keys.txt"

    # Extrahiere und speichere Root-Token
    echo "$init_response" | jq -r '.root_token' > "$SECRETS_DIR/root-token.txt"
    chmod 600 "$SECRETS_DIR/root-token.txt"

    log_success "Vault initialisiert"
    log_warn "WICHTIG: Sichere folgende Dateien an einem sicheren Ort:"
    log_warn "  - $SECRETS_DIR/unseal-keys.txt"
    log_warn "  - $SECRETS_DIR/root-token.txt"
}

# Entsperre Vault
unseal_vault() {
    log_info "Entsperre Vault..."

    local seal_status=$(curl -sk "$VAULT_ADDR/v1/sys/seal-status" | jq -r '.sealed')

    if [[ "$seal_status" == "false" ]]; then
        log_success "Vault ist bereits entsperrt"
        return 0
    fi

    if [[ ! -f "$SECRETS_DIR/unseal-keys.txt" ]]; then
        log_error "Unseal-Schlüssel nicht gefunden: $SECRETS_DIR/unseal-keys.txt"
        exit 1
    fi

    # Verwende die ersten 3 Schlüssel
    local count=0
    while IFS= read -r key && [[ $count -lt 3 ]]; do
        curl -sk -X PUT -d "{\"key\": \"$key\"}" "$VAULT_ADDR/v1/sys/unseal" > /dev/null
        ((count++))
    done < "$SECRETS_DIR/unseal-keys.txt"

    # Prüfe Ergebnis
    seal_status=$(curl -sk "$VAULT_ADDR/v1/sys/seal-status" | jq -r '.sealed')

    if [[ "$seal_status" == "false" ]]; then
        log_success "Vault entsperrt"
    else
        log_error "Vault konnte nicht entsperrt werden"
        exit 1
    fi
}

# Authentifiziere mit Root-Token
authenticate() {
    log_info "Authentifiziere..."

    if [[ ! -f "$SECRETS_DIR/root-token.txt" ]]; then
        log_error "Root-Token nicht gefunden"
        exit 1
    fi

    export VAULT_TOKEN=$(cat "$SECRETS_DIR/root-token.txt")

    if vault_cmd token lookup > /dev/null 2>&1; then
        log_success "Authentifiziert"
    else
        log_error "Authentifizierung fehlgeschlagen"
        exit 1
    fi
}

# Aktiviere Secrets Engines
enable_secrets_engines() {
    log_info "Aktiviere Secrets Engines..."

    # KV v2 (statische Geheimnisse)
    vault_cmd secrets enable -path=secret kv-v2 2>/dev/null || log_warn "KV v2 bereits aktiviert"

    # Database (dynamische Credentials)
    vault_cmd secrets enable database 2>/dev/null || log_warn "Database Engine bereits aktiviert"

    # Transit (Verschlüsselung)
    vault_cmd secrets enable transit 2>/dev/null || log_warn "Transit Engine bereits aktiviert"

    log_success "Secrets Engines aktiviert"
}

# Aktiviere Authentifizierungsmethoden
enable_auth_methods() {
    log_info "Aktiviere Authentifizierungsmethoden..."

    # AppRole für Anwendungen
    vault_cmd auth enable approle 2>/dev/null || log_warn "AppRole bereits aktiviert"

    log_success "Authentifizierungsmethoden aktiviert"
}

# Lade Policies
configure_policies() {
    log_info "Konfiguriere Policies..."

    for policy_file in "$POLICIES_DIR"/*.hcl; do
        if [[ -f "$policy_file" ]]; then
            local policy_name=$(basename "$policy_file" .hcl)
            vault_cmd policy write "$policy_name" "$policy_file"
            log_success "Policy geladen: $policy_name"
        fi
    done
}

# Konfiguriere AppRoles
configure_approles() {
    log_info "Konfiguriere AppRoles..."

    # Backend AppRole
    vault_cmd write auth/approle/role/ablage-backend \
        secret_id_ttl=24h \
        secret_id_num_uses=0 \
        token_ttl=1h \
        token_max_ttl=24h \
        token_policies="ablage-backend"

    # Worker AppRole
    vault_cmd write auth/approle/role/ablage-worker \
        secret_id_ttl=24h \
        secret_id_num_uses=0 \
        token_ttl=1h \
        token_max_ttl=24h \
        token_policies="ablage-worker"

    # Admin AppRole
    vault_cmd write auth/approle/role/ablage-admin \
        secret_id_ttl=1h \
        secret_id_num_uses=1 \
        token_ttl=30m \
        token_max_ttl=2h \
        token_policies="ablage-admin"

    log_success "AppRoles konfiguriert"

    # Generiere Role-IDs und Secret-IDs
    log_info "Generiere AppRole Credentials..."

    for role in ablage-backend ablage-worker ablage-admin; do
        local role_id=$(vault_cmd read -field=role_id auth/approle/role/$role/role-id)
        local secret_id=$(vault_cmd write -f -field=secret_id auth/approle/role/$role/secret-id)

        echo "$role_id" > "$SECRETS_DIR/${role}-role-id.txt"
        echo "$secret_id" > "$SECRETS_DIR/${role}-secret-id.txt"
        chmod 600 "$SECRETS_DIR/${role}-role-id.txt" "$SECRETS_DIR/${role}-secret-id.txt"

        log_success "AppRole Credentials für $role gespeichert"
    done
}

# Konfiguriere Transit-Schlüssel
configure_transit() {
    log_info "Konfiguriere Transit-Verschlüsselung..."

    # Haupt-Datenschlüssel
    vault_cmd write -f transit/keys/ablage-data \
        type=aes256-gcm96 \
        deletion_allowed=false \
        allow_plaintext_backup=false \
        exportable=false

    # PII-Schlüssel
    vault_cmd write -f transit/keys/ablage-pii \
        type=aes256-gcm96 \
        deletion_allowed=false \
        allow_plaintext_backup=false \
        exportable=false

    # Backup-Schlüssel
    vault_cmd write -f transit/keys/ablage-backup \
        type=aes256-gcm96 \
        deletion_allowed=false \
        allow_plaintext_backup=false \
        exportable=false

    log_success "Transit-Schlüssel konfiguriert"
}

# Aktiviere Audit-Logging
enable_audit_logging() {
    log_info "Aktiviere Audit-Logging..."

    # File-Audit (für lokale Logs)
    vault_cmd audit enable file file_path=/vault/logs/audit.log 2>/dev/null || log_warn "File-Audit bereits aktiviert"

    log_success "Audit-Logging aktiviert"
}

# Erstelle initiale Geheimnisse
create_initial_secrets() {
    log_info "Erstelle initiale Geheimnisse..."

    # Generiere sichere Zufallswerte
    local secret_key=$(openssl rand -base64 32)
    local jwt_secret=$(openssl rand -base64 32)

    # Anwendungs-Geheimnisse
    vault_cmd kv put secret/ablage-system/app \
        secret_key="$secret_key" \
        jwt_secret="$jwt_secret" \
        algorithm="HS256"

    # Datenbank-Geheimnisse (Platzhalter)
    vault_cmd kv put secret/ablage-system/database \
        host="postgres" \
        port="5432" \
        database="ablage_system" \
        username="ablage_admin" \
        password="CHANGE_ME_IN_PRODUCTION"

    # MinIO-Geheimnisse (Platzhalter)
    vault_cmd kv put secret/ablage-system/minio \
        endpoint="minio:9000" \
        access_key="CHANGE_ME" \
        secret_key="CHANGE_ME"

    # Redis-Geheimnisse (Platzhalter)
    vault_cmd kv put secret/ablage-system/redis \
        host="redis" \
        port="6379" \
        password=""

    # SMTP-Geheimnisse (Platzhalter)
    vault_cmd kv put secret/ablage-system/smtp \
        host="" \
        port="587" \
        username="" \
        password="" \
        from_email="noreply@ablage-system.local"

    # Alert-Konfiguration (Platzhalter)
    vault_cmd kv put secret/ablage-system/alerts \
        email_recipients="" \
        teams_webhook_url=""

    log_success "Initiale Geheimnisse erstellt"
    log_warn "WICHTIG: Aktualisiere Platzhalter-Werte mit echten Credentials!"
}

# Zeige Status
show_status() {
    echo ""
    log_info "=== Vault Status ==="

    # Seal-Status
    local seal_status=$(curl -sk "$VAULT_ADDR/v1/sys/seal-status")
    echo "$seal_status" | jq '.'

    # Aktivierte Engines
    echo ""
    log_info "=== Aktivierte Secrets Engines ==="
    vault_cmd secrets list -format=table 2>/dev/null || log_warn "Nicht authentifiziert"

    # Aktivierte Auth-Methoden
    echo ""
    log_info "=== Aktivierte Auth-Methoden ==="
    vault_cmd auth list -format=table 2>/dev/null || log_warn "Nicht authentifiziert"

    # Policies
    echo ""
    log_info "=== Konfigurierte Policies ==="
    vault_cmd policy list 2>/dev/null || log_warn "Nicht authentifiziert"
}

# Zeige Zusammenfassung
show_summary() {
    echo ""
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo -e "${GREEN}   Vault Setup abgeschlossen! 🔐${NC}"
    echo -e "${GREEN}════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${BLUE}🌐 Zugriff:${NC}"
    echo "   Vault UI:  $VAULT_ADDR/ui"
    echo "   API:       $VAULT_ADDR"
    echo ""
    echo -e "${BLUE}📁 Credentials (SICHER AUFBEWAHREN!):${NC}"
    echo "   Root Token:       $SECRETS_DIR/root-token.txt"
    echo "   Unseal Keys:      $SECRETS_DIR/unseal-keys.txt"
    echo "   Backend AppRole:  $SECRETS_DIR/ablage-backend-*.txt"
    echo "   Worker AppRole:   $SECRETS_DIR/ablage-worker-*.txt"
    echo ""
    echo -e "${BLUE}📝 Nächste Schritte:${NC}"
    echo "   1. Aktualisiere Geheimnisse mit echten Werten:"
    echo "      vault kv put secret/ablage-system/database password=<echtes_password>"
    echo ""
    echo "   2. Konfiguriere Backend für AppRole:"
    echo "      export VAULT_ROLE_ID=\$(cat $SECRETS_DIR/ablage-backend-role-id.txt)"
    echo "      export VAULT_SECRET_ID=\$(cat $SECRETS_DIR/ablage-backend-secret-id.txt)"
    echo ""
    echo "   3. Aktiviere Vault in .env:"
    echo "      VAULT_ENABLED=true"
    echo "      VAULT_ADDR=$VAULT_ADDR"
    echo ""
    echo -e "${YELLOW}⚠️  Sicherheitshinweise:${NC}"
    echo "   - Sichere Unseal-Keys an verschiedenen Orten"
    echo "   - Rotiere Root-Token nach Einrichtung"
    echo "   - Verwende AppRole statt statischer Tokens"
    echo "   - Aktiviere Auto-Unseal für Production"
    echo ""
}

# Rotiere Secrets
rotate_secrets() {
    log_info "Rotiere Secrets..."

    authenticate

    # Rotiere Transit-Schlüssel
    vault_cmd write -f transit/keys/ablage-data/rotate
    vault_cmd write -f transit/keys/ablage-pii/rotate
    vault_cmd write -f transit/keys/ablage-backup/rotate

    log_success "Transit-Schlüssel rotiert"

    # Generiere neue AppRole Secret-IDs
    for role in ablage-backend ablage-worker ablage-admin; do
        local secret_id=$(vault_cmd write -f -field=secret_id auth/approle/role/$role/secret-id)
        echo "$secret_id" > "$SECRETS_DIR/${role}-secret-id.txt"
        chmod 600 "$SECRETS_DIR/${role}-secret-id.txt"
        log_success "Neue Secret-ID für $role generiert"
    done

    log_warn "WICHTIG: Verteile neue Secret-IDs an Anwendungen!"
}

# Hauptfunktion
main() {
    case "${1:-setup}" in
        setup)
            check_prerequisites
            wait_for_vault
            initialize_vault
            unseal_vault
            authenticate
            enable_secrets_engines
            enable_auth_methods
            configure_policies
            configure_approles
            configure_transit
            enable_audit_logging
            create_initial_secrets
            show_summary
            ;;
        unseal)
            check_prerequisites
            wait_for_vault
            unseal_vault
            ;;
        status)
            check_prerequisites
            show_status
            ;;
        rotate)
            check_prerequisites
            wait_for_vault
            unseal_vault
            rotate_secrets
            ;;
        help|-h|--help)
            echo "Verwendung: $0 [Befehl]"
            echo ""
            echo "Befehle:"
            echo "  setup   - Vollständige Vault-Einrichtung"
            echo "  unseal  - Vault entsperren"
            echo "  status  - Vault-Status anzeigen"
            echo "  rotate  - Secrets rotieren"
            echo "  help    - Diese Hilfe anzeigen"
            ;;
        *)
            log_error "Unbekannter Befehl: $1"
            echo "Verwende '$0 help' für Hilfe"
            exit 1
            ;;
    esac
}

main "$@"
