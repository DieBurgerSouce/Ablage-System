# Vault Policy: ablage-worker
# Zugriff für Celery Worker auf Geheimnisse
#
# Worker benötigen eingeschränkten Zugriff - nur OCR- und Speicher-Credentials

# Worker-spezifische Geheimnisse lesen
path "secret/data/ablage-system/worker/*" {
  capabilities = ["read", "list"]
}

# Gemeinsame Geheimnisse (Datenbank, MinIO, Redis)
path "secret/data/ablage-system/database" {
  capabilities = ["read"]
}

path "secret/data/ablage-system/minio" {
  capabilities = ["read"]
}

path "secret/data/ablage-system/redis" {
  capabilities = ["read"]
}

# OCR-spezifische Geheimnisse
path "secret/data/ablage-system/ocr/*" {
  capabilities = ["read", "list"]
}

# Dynamische Datenbank-Credentials
path "database/creds/ablage-worker" {
  capabilities = ["read"]
}

# Token-Verwaltung
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "sys/leases/renew" {
  capabilities = ["update"]
}

# Transit-Verschlüsselung für Dokumente
path "transit/encrypt/ablage-data" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-data" {
  capabilities = ["update"]
}
