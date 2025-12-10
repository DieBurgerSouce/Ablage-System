# Vault Configuration - Ablage-System OCR
# Sicherheitskonfiguration für Production-Betrieb

# Storage backend
storage "file" {
  path = "/vault/data"
}

# For production with high availability, use Consul or etcd:
# storage "consul" {
#   address = "consul:8500"
#   path    = "vault/"
# }

# HTTPS listener (TLS enabled for production)
listener "tcp" {
  address     = "0.0.0.0:8200"

  # TLS Configuration - aktiviert für sichere Kommunikation
  tls_disable     = 0
  tls_cert_file   = "/vault/config/certs/vault.crt"
  tls_key_file    = "/vault/config/certs/vault.key"
  tls_min_version = "tls12"

  # Zusätzliche TLS-Sicherheit
  tls_cipher_suites = "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384,TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256,TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"

  # Client Certificate Verification (optional, für mTLS)
  # tls_require_and_verify_client_cert = true
  # tls_client_ca_file = "/vault/config/certs/ca.crt"
}

# Development listener (nur für lokale Entwicklung, in Production entfernen!)
# listener "tcp" {
#   address     = "127.0.0.1:8201"
#   tls_disable = 1
# }

# API settings - HTTPS für Production
api_addr     = "https://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"

# UI
ui = true

# Telemetry für Prometheus Monitoring
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = false
}

# Logging
log_level = "info"

# Seal configuration (Auto-unseal für Production empfohlen)
# Optionen: awskms, azurekeyvault, gcpkms, transit, pkcs11
# seal "awskms" {
#   region     = "eu-central-1"
#   kms_key_id = "your-kms-key-id"
# }

# Mlock - In Docker-Containern auf true setzen!
# false = Secrets werden im RAM gelockt und können nicht auf Disk geswappt werden
# true  = Für Container empfohlen (trotz CAP_IPC_LOCK), verhindert Startup-Probleme
disable_mlock = true

# Default Lease TTL
default_lease_ttl = "768h"
max_lease_ttl     = "8760h"
