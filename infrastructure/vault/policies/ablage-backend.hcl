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
path "transit/encrypt/ablage-data" {
  capabilities = ["update"]
}

path "transit/decrypt/ablage-data" {
  capabilities = ["update"]
}

# Keine Schreibrechte auf Secrets - nur Admins dürfen schreiben
