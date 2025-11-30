#!/bin/bash
# Vault Setup Script - Ablage-System OCR
# Automated Vault initialization and configuration

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
INIT_FILE="$SCRIPT_DIR/.vault-init.json"
ROOT_TOKEN_FILE="$SCRIPT_DIR/.vault-root-token"
UNSEAL_KEYS_FILE="$SCRIPT_DIR/.vault-unseal-keys"

echo -e "${BLUE}🔐 Vault Setup Script${NC}"
echo -e "${BLUE}════════════════════${NC}"
echo ""

# Function to check if Vault is running
check_vault_running() {
    echo -e "${BLUE}🔍 Checking if Vault is running...${NC}"

    if ! docker ps | grep -q "ablage-vault"; then
        echo -e "${YELLOW}⚠️  Vault is not running${NC}"
        read -p "Start Vault now? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            start_vault
        else
            exit 1
        fi
    fi

    echo -e "${GREEN}✅ Vault is running${NC}"
}

# Function to start Vault
start_vault() {
    echo -e "${BLUE}🚀 Starting Vault...${NC}"

    cd "$SCRIPT_DIR"
    docker-compose -f docker-compose.vault.yml up -d

    echo -e "${BLUE}Waiting for Vault to be ready...${NC}"
    sleep 5

    # Wait for Vault to be healthy
    MAX_RETRIES=30
    RETRY_COUNT=0

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        if curl -s "$VAULT_ADDR/v1/sys/health" | jq -e '.initialized' > /dev/null 2>&1 || [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ Vault is ready${NC}"
            break
        fi

        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo -n "."
        sleep 2
    done

    if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
        echo ""
        echo -e "${RED}❌ Vault failed to start${NC}"
        exit 1
    fi
    echo ""
}

# Function to initialize Vault
initialize_vault() {
    echo -e "${BLUE}🔧 Initializing Vault...${NC}"

    # Check if already initialized
    if [ -f "$INIT_FILE" ]; then
        echo -e "${YELLOW}⚠️  Vault appears to be already initialized${NC}"
        echo -e "${YELLOW}   Init file exists: $INIT_FILE${NC}"
        read -p "Re-initialize? This will create new keys! (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return
        fi
    fi

    # Initialize with 5 key shares, threshold of 3
    INIT_OUTPUT=$(curl -s -X PUT -d '{
        "secret_shares": 5,
        "secret_threshold": 3
    }' "$VAULT_ADDR/v1/sys/init")

    # Save initialization output
    echo "$INIT_OUTPUT" | jq '.' > "$INIT_FILE"

    # Extract root token
    echo "$INIT_OUTPUT" | jq -r '.root_token' > "$ROOT_TOKEN_FILE"

    # Extract unseal keys
    echo "$INIT_OUTPUT" | jq -r '.keys[]' > "$UNSEAL_KEYS_FILE"

    # Set permissions
    chmod 600 "$INIT_FILE" "$ROOT_TOKEN_FILE" "$UNSEAL_KEYS_FILE"

    echo -e "${GREEN}✅ Vault initialized${NC}"
    echo -e "${YELLOW}⚠️  IMPORTANT: Securely store these files:${NC}"
    echo -e "   - Root Token: $ROOT_TOKEN_FILE"
    echo -e "   - Unseal Keys: $UNSEAL_KEYS_FILE"
    echo -e "   - Init Data: $INIT_FILE"
    echo ""
    echo -e "${RED}🔥 Back up these files immediately! 🔥${NC}"
    echo ""
}

# Function to unseal Vault
unseal_vault() {
    echo -e "${BLUE}🔓 Unsealing Vault...${NC}"

    # Check if Vault is sealed
    SEALED=$(curl -s "$VAULT_ADDR/v1/sys/seal-status" | jq -r '.sealed')

    if [ "$SEALED" = "false" ]; then
        echo -e "${GREEN}✅ Vault is already unsealed${NC}"
        return
    fi

    # Check if unseal keys exist
    if [ ! -f "$UNSEAL_KEYS_FILE" ]; then
        echo -e "${RED}❌ Unseal keys file not found: $UNSEAL_KEYS_FILE${NC}"
        echo -e "${YELLOW}   Run initialization first or provide unseal keys manually${NC}"
        exit 1
    fi

    # Unseal with first 3 keys (threshold)
    UNSEAL_COUNT=0
    while IFS= read -r key && [ $UNSEAL_COUNT -lt 3 ]; do
        RESPONSE=$(curl -s -X PUT -d "{\"key\": \"$key\"}" "$VAULT_ADDR/v1/sys/unseal")
        SEALED=$(echo "$RESPONSE" | jq -r '.sealed')
        PROGRESS=$(echo "$RESPONSE" | jq -r '.progress')

        echo -e "${BLUE}Unseal progress: $PROGRESS/3${NC}"

        if [ "$SEALED" = "false" ]; then
            echo -e "${GREEN}✅ Vault unsealed successfully${NC}"
            return
        fi

        UNSEAL_COUNT=$((UNSEAL_COUNT + 1))
    done < "$UNSEAL_KEYS_FILE"

    echo -e "${RED}❌ Failed to unseal Vault${NC}"
    exit 1
}

# Function to login to Vault
login_vault() {
    echo -e "${BLUE}🔑 Logging in to Vault...${NC}"

    if [ ! -f "$ROOT_TOKEN_FILE" ]; then
        echo -e "${RED}❌ Root token file not found: $ROOT_TOKEN_FILE${NC}"
        exit 1
    fi

    export VAULT_TOKEN=$(cat "$ROOT_TOKEN_FILE")
    export VAULT_ADDR="$VAULT_ADDR"

    # Test login
    if vault token lookup > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Logged in to Vault${NC}"
    else
        echo -e "${RED}❌ Failed to login to Vault${NC}"
        exit 1
    fi
}

# Function to enable secrets engines
enable_secrets_engines() {
    echo -e "${BLUE}🔧 Enabling secrets engines...${NC}"

    # Enable KV v2 secrets engine
    vault secrets enable -path=secret kv-v2 2>/dev/null || echo "KV v2 already enabled"

    # Enable database secrets engine
    vault secrets enable database 2>/dev/null || echo "Database engine already enabled"

    # Enable AWS secrets engine (if using AWS)
    # vault secrets enable -path=aws aws 2>/dev/null || echo "AWS engine already enabled"

    echo -e "${GREEN}✅ Secrets engines enabled${NC}"
}

# Function to configure policies
configure_policies() {
    echo -e "${BLUE}📋 Configuring policies...${NC}"

    # Backend application policy
    vault policy write ablage-backend - <<EOF
# Read/write application secrets
path "secret/data/ablage-system/*" {
  capabilities = ["read", "list"]
}

# Read database credentials
path "database/creds/ablage-backend" {
  capabilities = ["read"]
}
EOF

    # Worker application policy
    vault policy write ablage-worker - <<EOF
# Read/write worker secrets
path "secret/data/ablage-system/worker/*" {
  capabilities = ["read", "list"]
}

# Read database credentials
path "database/creds/ablage-worker" {
  capabilities = ["read"]
}
EOF

    # Admin policy
    vault policy write ablage-admin - <<EOF
# Full access to ablage-system secrets
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "sys/policies/acl/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
EOF

    echo -e "${GREEN}✅ Policies configured${NC}"
}

# Function to create secrets
create_secrets() {
    echo -e "${BLUE}🔐 Creating initial secrets...${NC}"

    # Database credentials
    vault kv put secret/ablage-system/database \
        host="postgres" \
        port="5432" \
        database="ablage_system" \
        username="ablage_user" \
        password="CHANGE_ME_IN_PRODUCTION"

    # MinIO credentials
    vault kv put secret/ablage-system/minio \
        endpoint="http://minio:9000" \
        access_key="CHANGE_ME" \
        secret_key="CHANGE_ME"

    # Redis credentials
    vault kv put secret/ablage-system/redis \
        host="redis" \
        port="6379" \
        password=""

    # Application secrets
    vault kv put secret/ablage-system/app \
        secret_key="$(openssl rand -base64 32)" \
        jwt_secret="$(openssl rand -base64 32)"

    # Sentry DSN
    vault kv put secret/ablage-system/sentry \
        dsn="" \
        environment="production"

    # Alert configuration (Email + MS Teams)
    vault kv put secret/ablage-system/alerts \
        smtp_host="" \
        smtp_port="587" \
        smtp_username="" \
        smtp_password="" \
        smtp_from="alertmanager@ablage-system.local" \
        email_recipients="ops-team@internal.local" \
        teams_webhook_url=""

    echo -e "${GREEN}✅ Initial secrets created${NC}"
    echo -e "${YELLOW}⚠️  Update secrets with production values!${NC}"
}

# Function to create application tokens
create_app_tokens() {
    echo -e "${BLUE}🎫 Creating application tokens...${NC}"

    # Backend token
    BACKEND_TOKEN=$(vault token create -policy=ablage-backend -period=768h -format=json | jq -r '.auth.client_token')
    echo "$BACKEND_TOKEN" > "$SCRIPT_DIR/.vault-backend-token"
    chmod 600 "$SCRIPT_DIR/.vault-backend-token"
    echo -e "${GREEN}✅ Backend token created: $SCRIPT_DIR/.vault-backend-token${NC}"

    # Worker token
    WORKER_TOKEN=$(vault token create -policy=ablage-worker -period=768h -format=json | jq -r '.auth.client_token')
    echo "$WORKER_TOKEN" > "$SCRIPT_DIR/.vault-worker-token"
    chmod 600 "$SCRIPT_DIR/.vault-worker-token"
    echo -e "${GREEN}✅ Worker token created: $SCRIPT_DIR/.vault-worker-token${NC}"

    # Admin token
    ADMIN_TOKEN=$(vault token create -policy=ablage-admin -period=768h -format=json | jq -r '.auth.client_token')
    echo "$ADMIN_TOKEN" > "$SCRIPT_DIR/.vault-admin-token"
    chmod 600 "$SCRIPT_DIR/.vault-admin-token"
    echo -e "${GREEN}✅ Admin token created: $SCRIPT_DIR/.vault-admin-token${NC}"
}

# Function to show summary
show_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}   Vault Setup Complete! 🎉${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}"
    echo ""
    echo -e "${GREEN}✅ Vault is running and configured${NC}"
    echo ""
    echo -e "${BLUE}🌐 Access Points:${NC}"
    echo -e "   Vault API:  $VAULT_ADDR"
    echo -e "   Vault UI:   $VAULT_ADDR/ui"
    echo ""
    echo -e "${BLUE}🔑 Authentication:${NC}"
    echo -e "   Root Token: $(cat "$ROOT_TOKEN_FILE")"
    echo ""
    echo -e "${BLUE}📁 Important Files (keep secure):${NC}"
    echo -e "   $ROOT_TOKEN_FILE"
    echo -e "   $UNSEAL_KEYS_FILE"
    echo -e "   $SCRIPT_DIR/.vault-backend-token"
    echo -e "   $SCRIPT_DIR/.vault-worker-token"
    echo -e "   $SCRIPT_DIR/.vault-admin-token"
    echo ""
    echo -e "${YELLOW}⚠️  Security Reminders:${NC}"
    echo -e "   1. Back up unseal keys securely (offline)"
    echo -e "   2. Store root token safely (use only for emergencies)"
    echo -e "   3. Update default secrets with production values"
    echo -e "   4. Enable TLS in production"
    echo -e "   5. Configure auto-unseal for production"
    echo -e "   6. Rotate tokens regularly"
    echo ""
    echo -e "${BLUE}📝 Next Steps:${NC}"
    echo -e "   1. Update secrets: vault kv put secret/ablage-system/..."
    echo -e "   2. Configure application to use Vault"
    echo -e "   3. Enable audit logging: vault audit enable file file_path=/vault/logs/audit.log"
    echo -e "   4. Set up automatic backups"
    echo ""
    echo -e "${BLUE}📚 Usage Examples:${NC}"
    echo -e "   # Read secret"
    echo -e "   vault kv get secret/ablage-system/database"
    echo ""
    echo -e "   # Update secret"
    echo -e "   vault kv put secret/ablage-system/database password=new_password"
    echo ""
    echo -e "   # List secrets"
    echo -e "   vault kv list secret/ablage-system/"
    echo ""
}

# Main setup flow
main() {
    case "${1:-setup}" in
        setup)
            check_vault_running
            echo ""
            initialize_vault
            echo ""
            unseal_vault
            echo ""
            login_vault
            echo ""
            enable_secrets_engines
            echo ""
            configure_policies
            echo ""
            create_secrets
            echo ""
            create_app_tokens
            echo ""
            show_summary
            ;;

        start)
            start_vault
            ;;

        unseal)
            check_vault_running
            unseal_vault
            ;;

        status)
            curl -s "$VAULT_ADDR/v1/sys/seal-status" | jq '.'
            ;;

        stop)
            echo -e "${BLUE}Stopping Vault...${NC}"
            docker-compose -f "$SCRIPT_DIR/docker-compose.vault.yml" down
            echo -e "${GREEN}✅ Vault stopped${NC}"
            ;;

        help|-h|--help)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  setup    - Complete setup (initialize, unseal, configure)"
            echo "  start    - Start Vault container"
            echo "  unseal   - Unseal Vault"
            echo "  status   - Show Vault status"
            echo "  stop     - Stop Vault container"
            echo "  help     - Show this help message"
            ;;

        *)
            echo -e "${RED}❌ Unknown command: $1${NC}"
            echo "Run '$0 help' for usage"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
