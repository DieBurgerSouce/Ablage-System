# Transit Secrets Engine Configuration
# Encryption-as-a-Service für DSGVO-konforme Datenverschlüsselung
#
# Art. 32 DSGVO - Sicherheit der Verarbeitung
# Transit ermöglicht Verschlüsselung ohne lokale Schlüsselverwaltung

# Haupt-Verschlüsselungsschlüssel für Dokumentendaten
key "ablage-data" {
  type                   = "aes256-gcm96"
  deletion_allowed       = false  # Schlüssel kann nicht gelöscht werden
  allow_plaintext_backup = false  # Kein Plaintext-Export
  exportable             = false  # Schlüssel kann nicht exportiert werden

  # Key-Rotation alle 90 Tage (empfohlen)
  min_decryption_version = 1
  min_encryption_version = 1

  # Konvergente Verschlüsselung deaktiviert (mehr Sicherheit)
  convergent_encryption  = false
}

# PII-Verschlüsselungsschlüssel (Personenbezogene Daten)
# Separate Schlüssel für Trennung der Datentypen
key "ablage-pii" {
  type                   = "aes256-gcm96"
  deletion_allowed       = false
  allow_plaintext_backup = false
  exportable             = false

  # Strengere Rotation für PII
  # Automatische Rotation kann über Vault API konfiguriert werden
}

# Backup-Verschlüsselungsschlüssel
key "ablage-backup" {
  type                   = "aes256-gcm96"
  deletion_allowed       = false
  allow_plaintext_backup = false
  exportable             = false
}

# HMAC-Schlüssel für Audit-Hashing
key "ablage-audit-hmac" {
  type                   = "aes256-gcm96"
  deletion_allowed       = false
  allow_plaintext_backup = false
  exportable             = false
}
