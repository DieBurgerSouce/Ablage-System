# HashiCorp Vault Integration - Ablage-System OCR

Secure secrets management with HashiCorp Vault for production environments.

## 🚀 Quick Start

```bash
# Navigate to vault directory
cd infrastructure/vault

# Start Vault and complete setup
./setup-vault.sh setup

# Access Vault UI
open http://localhost:8200/ui
```

## 📋 Features

### Secrets Management

- **KV Secrets Engine**: Store application secrets securely
- **Dynamic Database Credentials**: Auto-generated, time-limited DB access
- **Secret Versioning**: Track and rollback secret changes
- **Access Policies**: Fine-grained access control
- **Audit Logging**: Complete audit trail of secret access

### Security

- **Encryption at Rest**: All secrets encrypted with AES-256-GCM
- **Encryption in Transit**: TLS 1.2+ for all API communication
- **Token-based Authentication**: Short-lived access tokens
- **Lease Management**: Automatic credential rotation
- **Seal/Unseal**: Vault starts sealed, requires unseal keys

## ⚙️ Configuration

### Docker Compose Deployment

```bash
# Start Vault
docker-compose -f docker-compose.vault.yml up -d

# Check status
docker logs ablage-vault
```

### Configuration File

[config/vault.hcl](config/vault.hcl):

```hcl
storage "file" {
  path = "/vault/data"
}

listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1  # Enable TLS in production!
}

ui = true
```

## 🔧 Setup

### Automated Setup

```bash
# Complete setup (recommended)
./setup-vault.sh setup
```

This will:
1. Start Vault container
2. Initialize Vault (5 keys, threshold 3)
3. Unseal Vault automatically
4. Enable secrets engines (KV v2, Database)
5. Configure policies (backend, worker, admin)
6. Create initial secrets
7. Generate application tokens

### Manual Setup

#### 1. Start Vault

```bash
./setup-vault.sh start
```

#### 2. Initialize Vault

```bash
vault operator init -key-shares=5 -key-threshold=3
```

Save the unseal keys and root token securely!

#### 3. Unseal Vault

```bash
vault operator unseal <KEY_1>
vault operator unseal <KEY_2>
vault operator unseal <KEY_3>
```

#### 4. Login

```bash
vault login <ROOT_TOKEN>
```

#### 5. Enable Secrets Engine

```bash
vault secrets enable -path=secret kv-v2
```

## 🔑 Usage

### Python Client

```python
from infrastructure.vault.vault_client import VaultClient, VaultConfig

# Initialize client
vault = VaultClient(
    url="http://localhost:8200",
    token="your-vault-token"
)

# Write secret
vault.set_secret('ablage-system/database', {
    'host': 'postgres',
    'port': 5432,
    'username': 'ablage_user',
    'password': 'secure_password'
})

# Read secret
db_config = vault.get_secret('ablage-system/database')
password = vault.get_secret('ablage-system/database', key='password')

# Using config loader
config = VaultConfig()
db_password = config.database.password
```

### CLI Commands

```bash
# Write secret
vault kv put secret/ablage-system/database \
    host=postgres \
    port=5432 \
    password=secure_password

# Read secret
vault kv get secret/ablage-system/database

# Read specific field
vault kv get -field=password secret/ablage-system/database

# List secrets
vault kv list secret/ablage-system/

# Delete secret
vault kv delete secret/ablage-system/database
```

## 📊 Secrets Organization

```
secret/ablage-system/
├── database          # PostgreSQL credentials
├── minio             # MinIO S3 credentials
├── redis             # Redis credentials
├── app               # Application secrets (JWT, etc.)
├── sentry            # Sentry DSN
└── alerts            # Alert webhook URLs
    ├── slack_webhook
    ├── pagerduty_key
    └── opsgenie_key
```

### Database Secrets

```bash
vault kv put secret/ablage-system/database \
    host="postgres" \
    port="5432" \
    database="ablage_system" \
    username="ablage_user" \
    password="$(openssl rand -base64 32)"
```

### MinIO Secrets

```bash
vault kv put secret/ablage-system/minio \
    endpoint="http://minio:9000" \
    access_key="$(openssl rand -hex 20)" \
    secret_key="$(openssl rand -base64 40)"
```

### Application Secrets

```bash
vault kv put secret/ablage-system/app \
    secret_key="$(openssl rand -base64 32)" \
    jwt_secret="$(openssl rand -base64 32)"
```

## 🔐 Access Policies

### Backend Policy

```hcl
# Read application secrets
path "secret/data/ablage-system/*" {
  capabilities = ["read", "list"]
}
```

### Worker Policy

```hcl
# Read worker secrets
path "secret/data/ablage-system/worker/*" {
  capabilities = ["read", "list"]
}
```

### Admin Policy

```hcl
# Full access
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
```

### Create Token with Policy

```bash
# Backend token
vault token create -policy=ablage-backend -period=768h

# Worker token
vault token create -policy=ablage-worker -period=768h

# Admin token
vault token create -policy=ablage-admin -period=768h
```

## 🔄 Dynamic Database Credentials

### Configure Database Engine

```bash
# Enable database secrets engine
vault secrets enable database

# Configure PostgreSQL connection
vault write database/config/ablage-postgres \
    plugin_name=postgresql-database-plugin \
    allowed_roles="ablage-backend,ablage-worker" \
    connection_url="postgresql://{{username}}:{{password}}@postgres:5432/ablage_system?sslmode=disable" \
    username="vault" \
    password="vault_password"

# Create role
vault write database/roles/ablage-backend \
    db_name=ablage-postgres \
    creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; \
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
    default_ttl="1h" \
    max_ttl="24h"
```

### Generate Credentials

```bash
# Generate credentials
vault read database/creds/ablage-backend

# Output:
# Key                Value
# ---                -----
# lease_id           database/creds/ablage-backend/abc123
# lease_duration     1h
# lease_renewable    true
# password           A1a-random-password
# username           v-root-ablage-backend-xyz789
```

### Python Usage

```python
# Generate dynamic credentials
creds = vault.get_database_credentials(role='ablage-backend')

# Use credentials
connection_string = f"postgresql://{creds['username']}:{creds['password']}@postgres:5432/ablage_system"

# Renew lease
vault.renew_lease(creds['lease_id'], increment=3600)

# Revoke when done
vault.revoke_lease(creds['lease_id'])
```

## 🔄 Secret Rotation

### Rotate Database Password

```bash
# Generate new password
NEW_PASSWORD=$(openssl rand -base64 32)

# Update in Vault
vault kv put secret/ablage-system/database password="$NEW_PASSWORD"

# Update in PostgreSQL
psql -U postgres -c "ALTER USER ablage_user WITH PASSWORD '$NEW_PASSWORD';"

# Restart applications to pick up new password
kubectl rollout restart deployment/ablage-backend
```

### Automated Rotation Script

```bash
#!/bin/bash
# rotate-secrets.sh

# Read current secret
OLD_SECRET=$(vault kv get -field=password secret/ablage-system/database)

# Generate new password
NEW_SECRET=$(openssl rand -base64 32)

# Update PostgreSQL
psql -U postgres -c "ALTER USER ablage_user WITH PASSWORD '$NEW_SECRET';"

# Update Vault
vault kv put secret/ablage-system/database password="$NEW_SECRET"

# Restart services
systemctl restart ablage-backend.service
```

## 🐛 Troubleshooting

### Vault is Sealed

```bash
# Check seal status
vault status

# Unseal with 3 keys
./setup-vault.sh unseal

# Or manually
vault operator unseal <KEY_1>
vault operator unseal <KEY_2>
vault operator unseal <KEY_3>
```

### Permission Denied

```bash
# Check token capabilities
vault token capabilities secret/ablage-system/database

# Create new token with correct policy
vault token create -policy=ablage-backend
```

### Connection Refused

```bash
# Check if Vault is running
docker ps | grep vault

# Check logs
docker logs ablage-vault

# Verify VAULT_ADDR
echo $VAULT_ADDR  # Should be http://localhost:8200
```

### Secret Not Found

```bash
# List all secrets
vault kv list secret/ablage-system/

# Check path (v2 includes 'data' in API path)
vault kv get secret/ablage-system/database  # Correct
vault kv get secret/data/ablage-system/database  # Also works
```

## 🔒 Security Best Practices

### 1. Secure Unseal Keys

- **Never commit** unseal keys to git
- **Store offline** in secure location (password manager, safe)
- **Split among team** members (3 of 5 threshold)
- **Backup encrypted** in multiple locations

### 2. Rotate Root Token

```bash
# Generate new root token
vault operator generate-root -init
vault operator generate-root -otp=<OTP>

# Use new root token
vault login <NEW_ROOT_TOKEN>

# Revoke old root token
vault token revoke <OLD_ROOT_TOKEN>
```

### 3. Enable Audit Logging

```bash
# Enable file audit
vault audit enable file file_path=/vault/logs/audit.log

# Enable syslog audit
vault audit enable syslog tag="vault" facility="LOCAL7"
```

### 4. Enable TLS

```hcl
# In vault.hcl
listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_disable   = 0
  tls_cert_file = "/vault/config/vault.crt"
  tls_key_file  = "/vault/config/vault.key"
  tls_min_version = "tls12"
}
```

### 5. Use Auto-Unseal (Production)

```hcl
# AWS KMS auto-unseal
seal "awskms" {
  region     = "eu-central-1"
  kms_key_id = "your-kms-key-id"
}

# Or Azure Key Vault
seal "azurekeyvault" {
  tenant_id     = "your-tenant-id"
  vault_name    = "your-vault-name"
  key_name      = "your-key-name"
}
```

### 6. Limit Token TTL

```bash
# Create tokens with short TTL
vault token create -policy=ablage-backend -ttl=1h -renewable

# Implement automatic token renewal in application
```

### 7. Regular Backups

```bash
# Backup Vault data
tar -czf vault-backup-$(date +%Y%m%d).tar.gz /vault/data

# Backup to remote
rsync -az /vault/data/ backup-server:/backups/vault/
```

## 📊 Monitoring

### Health Check

```bash
# Check health
curl http://localhost:8200/v1/sys/health

# Expected response for unsealed, initialized Vault:
# {"initialized":true,"sealed":false,"standby":false,...}
```

### Metrics (Prometheus)

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'vault'
    metrics_path: '/v1/sys/metrics'
    params:
      format: ['prometheus']
    bearer_token: 'your-vault-token'
    static_configs:
      - targets: ['vault:8200']
```

### Audit Logs

```bash
# View audit logs
tail -f /vault/logs/audit.log | jq '.'

# Find specific operations
grep "secret/ablage-system/database" /vault/logs/audit.log

# Count operations by user
cat /vault/logs/audit.log | jq -r '.auth.display_name' | sort | uniq -c
```

## 📚 Resources

- [Vault Documentation](https://www.vaultproject.io/docs)
- [Vault Best Practices](https://learn.hashicorp.com/tutorials/vault/production-hardening)
- [HVAC Python Client](https://hvac.readthedocs.io/)
- [Vault on Docker](https://hub.docker.com/_/vault)

---

**Last Updated**: 2025-01-24
**Vault Version**: 1.15.4
**Maintainer**: Ablage-System Team
