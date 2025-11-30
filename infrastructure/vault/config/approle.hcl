# AppRole Authentication Configuration
# Ermöglicht sichere Authentifizierung ohne statische Tokens
#
# AppRole verwendet:
# - role_id: Identität der Anwendung (kann eingebettet werden)
# - secret_id: Einmal-Token für Authentifizierung (muss sicher verteilt werden)

# Backend-Rolle
# Langlebig mit Token-Erneuerung
path "auth/approle/role/ablage-backend" {
  # Secret-ID Konfiguration
  secret_id_ttl          = "24h"        # Secret-ID gültig für 24 Stunden
  secret_id_num_uses     = 0            # Unbegrenzte Nutzung (für Container-Restarts)

  # Token Konfiguration
  token_ttl              = "1h"         # Token gültig für 1 Stunde
  token_max_ttl          = "24h"        # Maximale Token-Lebensdauer
  token_policies         = ["ablage-backend"]

  # CIDR-Beschränkung (optional, für zusätzliche Sicherheit)
  # secret_id_bound_cidrs = ["172.28.0.0/16"]
  # token_bound_cidrs     = ["172.28.0.0/16"]

  # Typ
  token_type             = "service"
}

# Worker-Rolle
# Ähnlich wie Backend, aber mit Worker-Policy
path "auth/approle/role/ablage-worker" {
  secret_id_ttl          = "24h"
  secret_id_num_uses     = 0

  token_ttl              = "1h"
  token_max_ttl          = "24h"
  token_policies         = ["ablage-worker"]

  token_type             = "service"
}

# Admin-Rolle
# Kürzere Lebensdauer für erhöhte Sicherheit
path "auth/approle/role/ablage-admin" {
  secret_id_ttl          = "1h"         # Kurze Secret-ID Lebensdauer
  secret_id_num_uses     = 1            # Einmalige Nutzung

  token_ttl              = "30m"        # Kurze Token-Lebensdauer
  token_max_ttl          = "2h"         # Maximale Token-Lebensdauer
  token_policies         = ["ablage-admin"]

  token_type             = "service"
}
