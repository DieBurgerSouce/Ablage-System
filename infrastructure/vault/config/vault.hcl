# Vault Configuration - Ablage-System OCR
# Sicherheitskonfiguration für Production-Betrieb
#
# INFRASTRUCTURE HARDENING: Certificate Rotation
# Implementiert via: infrastructure/vault/scripts/cert-rotation.sh
# Dokumentation: .claude/Docs/INFRASTRUCTURE_HARDENING.md
#
# Optionen:
#   --auto    Automatische Rotation (fuer Cronjob)
#   --manual  Interaktive Rotation
#   --pki     PKI-basierte Rotation (Enterprise)
#   --check   Status pruefen

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

# Mlock - In Docker-Containern deaktiviert
# HINWEIS: disable_mlock=true ist in Docker notwendig, da CAP_IPC_LOCK
# nicht ausreicht. Der Container hat jedoch nur localhost-Zugriff.
# Für maximale Sicherheit in Production: Vault auf dediziertem Host betreiben.
disable_mlock = true

# Security-Hardening: Kürzere Lease TTLs
# Reduziert Risiko bei kompromittierten Tokens
default_lease_ttl = "24h"   # War: 768h (32 Tage) - jetzt 24 Stunden
max_lease_ttl     = "168h"  # War: 8760h (1 Jahr) - jetzt 7 Tage
