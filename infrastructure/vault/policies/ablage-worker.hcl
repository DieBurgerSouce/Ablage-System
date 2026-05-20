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

# ablage-encryption-key: Allgemeine Verschlüsselung (Standard-Key)
path "transit/encrypt/ablage-encryption-key" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-encryption-key" {
  capabilities = ["update"]
}

# ablage-pii: Personenbezogene Daten (Worker für Batch-Verarbeitung)
path "transit/encrypt/ablage-pii" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-pii" {
  capabilities = ["update"]
}

# ==========================================================================
# SECURITY: Bewusst NICHT freigegebene Keys für Worker (Principle of Least Privilege)
# ==========================================================================
#
# Die folgenden Transit-Keys sind NUR für das Backend freigegeben:
#
# - ablage-totp-secrets: MFA-Secrets für Benutzerauthentifizierung
#   Grund: Worker verarbeiten keine Authentifizierung, nur das Backend
#
# - ablage-api-keys: ERP/API-Zugangsdaten
#   Grund: Worker benötigen keinen Zugriff auf externe API-Credentials
#
# - ablage-backup: Backup-Verschlüsselung
#   Grund: Backups werden vom Backend orchestriert, nicht von Workern
#
# - ablage-audit-hmac: Audit-Log-Hashing
#   Grund: Audit-Logs werden zentral vom Backend geführt
#
# Falls ein Worker diese Keys benötigt, muss ein separater Worker-Pool
# mit erweiterten Rechten erstellt werden (Dokumentation erforderlich).
# ==========================================================================
