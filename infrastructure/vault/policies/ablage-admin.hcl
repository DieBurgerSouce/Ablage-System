# Vault Policy: ablage-admin
# Vollzugriff für Administratoren auf Ablage-System Geheimnisse
#
# WARNUNG: Diese Policy nur für vertrauenswürdige Administratoren verwenden!

# Vollzugriff auf Ablage-System Geheimnisse
path "secret/data/ablage-system/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/ablage-system/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/delete/ablage-system/*" {
  capabilities = ["update"]
}

path "secret/undelete/ablage-system/*" {
  capabilities = ["update"]
}

path "secret/destroy/ablage-system/*" {
  capabilities = ["update"]
}

# Datenbank-Verwaltung
path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Policy-Verwaltung für Ablage-System
path "sys/policies/acl/ablage-*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# AppRole-Verwaltung
path "auth/approle/role/ablage-*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Transit-Schlüssel-Verwaltung
path "transit/keys/ablage-*" {
  capabilities = ["create", "read", "update", "list"]
}

path "transit/config/ablage-*" {
  capabilities = ["create", "read", "update"]
}

# Audit-Logs lesen (für Compliance-Reporting)
path "sys/audit" {
  capabilities = ["read", "list"]
}

path "sys/audit/*" {
  capabilities = ["read"]
}

# Token-Verwaltung
path "auth/token/create" {
  capabilities = ["create", "update"]
}

path "auth/token/lookup" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/revoke" {
  capabilities = ["update"]
}

# Lease-Verwaltung
path "sys/leases/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Health-Status
path "sys/health" {
  capabilities = ["read"]
}

path "sys/seal-status" {
  capabilities = ["read"]
}
