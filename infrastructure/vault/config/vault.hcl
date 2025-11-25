# Vault Configuration - Ablage-System OCR

# Storage backend
storage "file" {
  path = "/vault/data"
}

# For production, use Consul or etcd:
# storage "consul" {
#   address = "consul:8500"
#   path    = "vault/"
# }

# HTTP listener
listener "tcp" {
  address     = "0.0.0.0:8200"
  tls_disable = 1  # Enable TLS in production!

  # For production with TLS:
  # tls_disable     = 0
  # tls_cert_file   = "/vault/config/vault.crt"
  # tls_key_file    = "/vault/config/vault.key"
  # tls_min_version = "tls12"
}

# API settings
api_addr = "http://0.0.0.0:8200"
cluster_addr = "https://0.0.0.0:8201"

# UI
ui = true

# Telemetry
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = false
}

# Logging
log_level = "info"

# Seal configuration (Auto-unseal in production)
# seal "awskms" {
#   region     = "eu-central-1"
#   kms_key_id = "your-kms-key-id"
# }

# Disable mlock (only for development in containers)
disable_mlock = true
