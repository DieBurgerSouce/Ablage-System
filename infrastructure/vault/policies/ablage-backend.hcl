# Vault Policy: ablage-backend
# Zugriff für das FastAPI Backend auf Geheimnisse
#
# Art. 25 DSGVO - Datenschutz durch Technikgestaltung
# Nur minimale Rechte werden gewährt (Principle of Least Privilege)

# Anwendungs-Geheimnisse lesen (KV v2)
path "secret/data/ablage-system/*" {
  capabilities = ["read", "list"]
}

# Anwendungs-Metadaten lesen (für Secret-Versionen)
path "secret/metadata/ablage-system/*" {
  capabilities = ["read", "list"]
}

# Dynamische Datenbank-Credentials anfordern
path "database/creds/ablage-backend" {
  capabilities = ["read"]
}

# Token-Informationen abfragen (für Lease-Verwaltung)
path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# Eigenes Token erneuern
path "auth/token/renew-self" {
  capabilities = ["update"]
}

# Lease-Erneuerung für dynamische Credentials
path "sys/leases/renew" {
  capabilities = ["update"]
}

# Transit-Verschlüsselung für sensible Daten (DSGVO-konform)
# ablage-data: Dokumentendaten
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

path "transit/rewrap/ablage-encryption-key" {
  capabilities = ["update"]
}

# ablage-pii: Personenbezogene Daten
path "transit/encrypt/ablage-pii" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-pii" {
  capabilities = ["update"]
}

path "transit/rewrap/ablage-pii" {
  capabilities = ["update"]
}

# ablage-totp-secrets: MFA-Secrets
path "transit/encrypt/ablage-totp-secrets" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-totp-secrets" {
  capabilities = ["update"]
}

# ablage-api-keys: ERP/API-Keys
path "transit/encrypt/ablage-api-keys" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-api-keys" {
  capabilities = ["update"]
}

# Transit Key-Info lesen (für Debugging)
path "transit/keys/ablage-*" {
  capabilities = ["read"]
}

# Keine Schreibrechte auf Secrets - nur Admins dürfen schreiben
