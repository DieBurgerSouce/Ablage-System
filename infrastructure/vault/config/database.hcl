# Database Secrets Engine Configuration
# Dynamische Datenbank-Credentials für PostgreSQL
#
# Vorteile:
# - Automatische Credential-Rotation
# - Zeitlich begrenzte Zugangsdaten
# - Audit-Trail für alle Credential-Anfragen

# PostgreSQL Verbindungskonfiguration
connection "postgresql" {
  plugin_name    = "postgresql-database-plugin"
  connection_url = "postgresql://{{username}}:{{password}}@postgres:5432/ablage_system"
  allowed_roles  = ["ablage-backend", "ablage-worker", "ablage-readonly"]

  # Admin-Credentials (werden beim Setup konfiguriert)
  username = "vault_admin"
  password = "VAULT_ADMIN_PASSWORD"  # Wird durch setup-vault.sh ersetzt

  # SSL-Konfiguration für Production
  # ssl_mode = "require"
}

# Backend-Rolle: Voller Zugriff auf Anwendungstabellen
role "ablage-backend" {
  db_name             = "postgresql"

  # SQL-Statements für User-Erstellung
  creation_statements = [
    "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' INHERIT",
    "GRANT ablage_app TO \"{{name}}\""
  ]

  # Aufräumen bei Widerruf
  revocation_statements = [
    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"",
    "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM \"{{name}}\"",
    "REVOKE USAGE ON SCHEMA public FROM \"{{name}}\"",
    "REASSIGN OWNED BY \"{{name}}\" TO postgres",
    "DROP OWNED BY \"{{name}}\"",
    "DROP ROLE IF EXISTS \"{{name}}\""
  ]

  # Credential-Lebensdauer
  default_ttl = "1h"
  max_ttl     = "24h"
}

# Worker-Rolle: Eingeschränkter Zugriff
role "ablage-worker" {
  db_name             = "postgresql"

  creation_statements = [
    "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' INHERIT",
    "GRANT ablage_worker TO \"{{name}}\""
  ]

  revocation_statements = [
    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"",
    "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM \"{{name}}\"",
    "REVOKE USAGE ON SCHEMA public FROM \"{{name}}\"",
    "REASSIGN OWNED BY \"{{name}}\" TO postgres",
    "DROP OWNED BY \"{{name}}\"",
    "DROP ROLE IF EXISTS \"{{name}}\""
  ]

  default_ttl = "1h"
  max_ttl     = "24h"
}

# Readonly-Rolle: Nur Lesezugriff (für Reporting/Monitoring)
role "ablage-readonly" {
  db_name             = "postgresql"

  creation_statements = [
    "CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}' INHERIT",
    "GRANT ablage_readonly TO \"{{name}}\""
  ]

  revocation_statements = [
    "REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"",
    "REASSIGN OWNED BY \"{{name}}\" TO postgres",
    "DROP OWNED BY \"{{name}}\"",
    "DROP ROLE IF EXISTS \"{{name}}\""
  ]

  default_ttl = "30m"
  max_ttl     = "4h"
}
