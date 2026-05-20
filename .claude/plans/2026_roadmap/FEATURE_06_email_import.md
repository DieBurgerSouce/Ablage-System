# Feature 06: E-Mail & Ordner-Import

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P2 - Wichtig
> **Geschaetzter Aufwand**: 2-3 Wochen
> **Abhaengigkeiten**: Feature 01 (Multi-Firma)

---

## Executive Summary

Der E-Mail & Ordner-Import automatisiert den Dokumenten-Eingang. E-Mails mit Anhaengen werden automatisch abgerufen und verarbeitet, Ordner werden auf neue Dateien ueberwacht. KI-basierte Filter erkennen Spam und Duplikate.

**Business Value:**
- Automatischer Dokumenten-Eingang
- Keine manuelle Datei-Kopiererei
- KI filtert irrelevante E-Mails
- Multi-Firma faehig

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | IMAP E-Mail Abruf | MUSS | Anhaenge werden importiert |
| FR-02 | Ordner-Watcher | MUSS | Neue Dateien erkannt |
| FR-03 | KI Spam-Filter | SOLL | Nicht-Rechnungen ignoriert |
| FR-04 | Duplikat-Erkennung | MUSS | Hash-basiert |
| FR-05 | Multi-Firma E-Mail | MUSS | Pro Firma eigenes Postfach |
| FR-06 | Absender-Whitelist | SOLL | Nur bekannte Absender |

---

## API-Spezifikation

### Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/import/email/accounts` | E-Mail Konten | Admin |
| POST | `/api/v1/import/email/accounts` | Konto hinzufuegen | Admin |
| POST | `/api/v1/import/email/accounts/{id}/test` | Verbindung testen | Admin |
| GET | `/api/v1/import/folders` | Ordner-Watcher | Admin |
| POST | `/api/v1/import/folders` | Ordner hinzufuegen | Admin |
| GET | `/api/v1/import/history` | Import-Historie | Required |

### `POST /api/v1/import/email/accounts`

**Request:**
```json
{
  "company_id": "company-uuid",
  "name": "Eingangsrechnungen",
  "imap_server": "imap.example.com",
  "imap_port": 993,
  "use_ssl": true,
  "username": "rechnung@firma.de",
  "password": "secret",
  "folder": "INBOX",
  "check_interval_minutes": 5,
  "target_folder_id": "folder-uuid",
  "filters": {
    "ai_spam_filter": true,
    "duplicate_check": true,
    "sender_whitelist": ["@lieferant.de"]
  }
}
```

---

## Datenbank-Schema

### `import_email_accounts`

```sql
CREATE TABLE import_email_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) NOT NULL,

    name VARCHAR(255) NOT NULL,
    imap_server VARCHAR(255) NOT NULL,
    imap_port INTEGER DEFAULT 993,
    use_ssl BOOLEAN DEFAULT true,
    username VARCHAR(255) NOT NULL,
    password_encrypted TEXT NOT NULL,
    folder VARCHAR(100) DEFAULT 'INBOX',

    check_interval_minutes INTEGER DEFAULT 5,
    target_folder_id UUID REFERENCES folders(id),
    filters JSONB DEFAULT '{}',

    is_active BOOLEAN DEFAULT true,
    last_check_at TIMESTAMPTZ,
    last_error TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `import_folder_watchers`

```sql
CREATE TABLE import_folder_watchers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) NOT NULL,

    name VARCHAR(255) NOT NULL,
    path VARCHAR(500) NOT NULL,
    category VARCHAR(50),  -- auto-detect wenn NULL

    is_active BOOLEAN DEFAULT true,
    last_check_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Implementation Tasks

### Phase 1: E-Mail Import (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] IMAP Connector | Verbindung + Abruf |
| 1.2 | [ ] Attachment Parser | PDF/Images extrahiert |
| 1.3 | [ ] Celery Task | Regelmaessiger Abruf |
| 1.4 | [ ] Duplikat-Check | Hash-Vergleich |

### Phase 2: Ordner-Watcher (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Watchdog Service | Filesystem Events |
| 2.2 | [ ] File Processing | OCR-Queue |
| 2.3 | [ ] Error Handling | Fehler geloggt |

### Phase 3: KI-Filter (0.5 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Spam-Klassifikation | ML-basiert |
| 3.2 | [ ] Whitelist-Matching | Regex + Domain |

### Phase 4: Frontend (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 4.1 | [ ] E-Mail Account UI | CRUD + Test |
| 4.2 | [ ] Ordner-Watcher UI | CRUD + Status |
| 4.3 | [ ] Import-Historie | Logs sichtbar |

---

## Quality Gates

- [ ] E-Mails werden automatisch abgerufen
- [ ] Ordner werden ueberwacht
- [ ] Duplikate werden erkannt
- [ ] Credentials sind verschluesselt
- [ ] Multi-Firma funktioniert
