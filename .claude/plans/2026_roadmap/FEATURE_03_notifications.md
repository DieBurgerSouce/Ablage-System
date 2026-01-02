# Feature 03: Intelligentes Benachrichtigungssystem

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P1 - Kritisch
> **Geschaetzter Aufwand**: 3-4 Wochen
> **Abhaengigkeiten**: Feature 01 (Multi-Firma)

---

## Executive Summary

Das intelligente Benachrichtigungssystem informiert Benutzer proaktiv ueber wichtige Ereignisse wie ueberfaellige Rechnungen, ablaufende Vertraege und Fristen. Eine dreistufige Hierarchie (System → Rolle → User) ermoeglicht flexible Konfiguration, waehrend multiple Kanaele (In-App, E-Mail, Slack, Teams) fuer maximale Erreichbarkeit sorgen.

**Business Value:**
- Keine verpassten Fristen mehr
- Proaktive statt reaktive Arbeitsweise
- Konfigurierbar pro User/Rolle
- Zeitersparnis durch automatische Alerts

---

## Inhaltsverzeichnis

1. [Anforderungen](#anforderungen)
2. [Dreistufige Hierarchie](#dreistufige-hierarchie)
3. [API-Spezifikation](#api-spezifikation)
4. [Datenbank-Schema](#datenbank-schema)
5. [Regel-Engine](#regel-engine)
6. [Implementation Tasks](#implementation-tasks)
7. [Test-Szenarien](#test-szenarien)
8. [Quality Gates](#quality-gates)

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | In-App Benachrichtigungen | MUSS | Dashboard-Widget, Badge-Counter |
| FR-02 | E-Mail Benachrichtigungen | MUSS | Sofort oder Digest, konfigurierbar |
| FR-03 | Slack Integration | SOLL | Webhook zu Slack Channel |
| FR-04 | Microsoft Teams Integration | SOLL | Webhook zu Teams Channel |
| FR-05 | Browser Push Notifications | SOLL | Service Worker basiert |
| FR-06 | Dreistufige Hierarchie | MUSS | System → Rolle → User |
| FR-07 | Regel-Engine | MUSS | Flexibel konfigurierbare Trigger |
| FR-08 | Benachrichtigungs-Kategorien | MUSS | Zahlungen, Vertraege, Dokumente, System |

### Nicht-Funktionale Anforderungen

| ID | Anforderung | Metrik | Akzeptanzkriterium |
|----|-------------|--------|-------------------|
| NFR-01 | Latenz | Zustellung | < 5 Sekunden fuer In-App |
| NFR-02 | Zuverlaessigkeit | Zustellung | 99.9% erfolgreich |
| NFR-03 | Skalierbarkeit | Volume | 10.000+ Benachrichtigungen/Tag |
| NFR-04 | Konfigurierbarkeit | Optionen | User kann alles anpassen |

---

## Dreistufige Hierarchie

```
┌─────────────────────────────────────────────────────────────┐
│  Ebene 1: SYSTEM-DEFAULTS                                   │
│  ═══════════════════════════════════════                    │
│  Gilt fuer ALLE Benutzer                                    │
│  Konfiguriert von: Admin                                    │
│                                                             │
│  Beispiele:                                                 │
│  • System-Wartung Ankuendigungen                            │
│  • Kritische Sicherheitsmeldungen                           │
│  • Neue Feature-Releases                                    │
├─────────────────────────────────────────────────────────────┤
│  Ebene 2: ROLLE / DEPARTMENT                                │
│  ═══════════════════════════════════════                    │
│  Gilt fuer bestimmte Gruppen                                │
│  Konfiguriert von: Admin                                    │
│                                                             │
│  Beispiele:                                                 │
│  • Buchhaltung: Rechnungs-Alerts                            │
│  • Geschaeftsfuehrung: Finanz-Uebersichten                  │
│  • Einkauf: Lieferanten-Updates                             │
├─────────────────────────────────────────────────────────────┤
│  Ebene 3: USER-PRAEFERENZEN                                 │
│  ═══════════════════════════════════════                    │
│  Individuelle Anpassungen                                   │
│  Konfiguriert von: User selbst                              │
│                                                             │
│  Beispiele:                                                 │
│  • "Ich moechte keine E-Mails am Wochenende"                │
│  • "Slack statt E-Mail fuer Rechnungen"                     │
│  • "Nur Betraege > 1000€"                                   │
└─────────────────────────────────────────────────────────────┘

REGEL: User > Rolle > System
Wenn User etwas deaktiviert, hat das Vorrang.
Wenn Rolle etwas aktiviert, gilt das fuer alle in der Rolle.
System-Defaults gelten nur wenn nichts anderes definiert.
```

---

## API-Spezifikation

### Endpoints Uebersicht

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/notifications` | Alle Benachrichtigungen | Required |
| GET | `/api/v1/notifications/unread-count` | Anzahl ungelesener | Required |
| PUT | `/api/v1/notifications/{id}/read` | Als gelesen markieren | Required |
| PUT | `/api/v1/notifications/read-all` | Alle als gelesen | Required |
| DELETE | `/api/v1/notifications/{id}` | Loeschen | Required |
| GET | `/api/v1/notifications/settings` | User-Einstellungen | Required |
| PUT | `/api/v1/notifications/settings` | Einstellungen speichern | Required |
| GET | `/api/v1/admin/notifications/rules` | Alle Regeln (Admin) | Admin |
| POST | `/api/v1/admin/notifications/rules` | Neue Regel | Admin |
| PUT | `/api/v1/admin/notifications/rules/{id}` | Regel bearbeiten | Admin |

---

### `GET /api/v1/notifications`

**Query Parameters:**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|--------------|
| skip | int | 0 | Pagination Offset |
| limit | int | 50 | Max. Anzahl |
| category | string | - | Filter nach Kategorie |
| is_read | bool | - | Filter gelesen/ungelesen |

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": "notif-uuid",
      "type": "invoice_overdue",
      "category": "payments",
      "title": "Rechnung ueberfaellig",
      "message": "Rechnung RE-2026-001 von Lieferant GmbH ist seit 14 Tagen ueberfaellig (€2.450,00)",
      "severity": "warning",
      "is_read": false,
      "created_at": "2026-01-15T08:00:00Z",
      "data": {
        "document_id": "doc-uuid",
        "invoice_number": "RE-2026-001",
        "amount": 2450.00,
        "days_overdue": 14
      },
      "actions": [
        {
          "label": "Zur Rechnung",
          "url": "/documents/doc-uuid",
          "primary": true
        },
        {
          "label": "Mahnung erstellen",
          "url": "/invoices/doc-uuid/dunning"
        }
      ]
    }
  ],
  "total": 42,
  "unread_count": 5
}
```

---

### `GET /api/v1/notifications/settings`

**Response (200 OK):**
```json
{
  "channels": {
    "in_app": {
      "enabled": true
    },
    "email": {
      "enabled": true,
      "mode": "digest",
      "digest_time": "08:00",
      "digest_days": ["monday", "tuesday", "wednesday", "thursday", "friday"]
    },
    "slack": {
      "enabled": true,
      "webhook_url": "https://hooks.slack.com/...",
      "channel": "#buchhaltung"
    },
    "teams": {
      "enabled": false,
      "webhook_url": null
    },
    "push": {
      "enabled": true,
      "subscription": {...}
    }
  },
  "categories": {
    "payments": {
      "enabled": true,
      "channels": ["in_app", "email", "slack"],
      "min_amount": 100,
      "filters": {
        "only_overdue": true
      }
    },
    "contracts": {
      "enabled": true,
      "channels": ["in_app", "email"],
      "days_before_expiry": 30
    },
    "documents": {
      "enabled": true,
      "channels": ["in_app"],
      "types": ["invoice", "contract"]
    },
    "system": {
      "enabled": true,
      "channels": ["in_app"]
    }
  },
  "quiet_hours": {
    "enabled": true,
    "start": "18:00",
    "end": "08:00",
    "timezone": "Europe/Berlin"
  }
}
```

---

### `PUT /api/v1/notifications/settings`

**Request:**
```json
{
  "channels": {
    "email": {
      "mode": "immediate",
      "enabled": true
    }
  },
  "categories": {
    "payments": {
      "min_amount": 500
    }
  },
  "quiet_hours": {
    "enabled": false
  }
}
```

**Response (200 OK):** Aktualisierte Settings.

---

## Datenbank-Schema

### Neue Tabellen

#### `notifications`

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Empfaenger
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    company_id UUID REFERENCES companies(id) NOT NULL,

    -- Inhalt
    type VARCHAR(100) NOT NULL,  -- invoice_overdue, contract_expiring, etc.
    category VARCHAR(50) NOT NULL,  -- payments, contracts, documents, system
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',  -- info, warning, error, success

    -- Zusatzdaten
    data JSONB DEFAULT '{}',  -- document_id, amount, etc.
    actions JSONB DEFAULT '[]',  -- Action buttons

    -- Status
    is_read BOOLEAN DEFAULT false,
    read_at TIMESTAMPTZ,

    -- Zustellung
    channels_sent JSONB DEFAULT '[]',  -- ["in_app", "email"]
    email_sent_at TIMESTAMPTZ,
    slack_sent_at TIMESTAMPTZ,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    expires_at TIMESTAMPTZ  -- Optionaler Ablauf

);

CREATE INDEX ix_notifications_user ON notifications(user_id);
CREATE INDEX ix_notifications_unread ON notifications(user_id, is_read) WHERE is_read = false;
CREATE INDEX ix_notifications_category ON notifications(category);
CREATE INDEX ix_notifications_created ON notifications(created_at DESC);
```

#### `notification_rules`

```sql
CREATE TABLE notification_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identifikation
    name VARCHAR(255) NOT NULL,
    description TEXT,

    -- Scope
    scope VARCHAR(20) NOT NULL,  -- system, role, department
    scope_value VARCHAR(100),  -- role name or department name

    -- Trigger
    trigger_type VARCHAR(100) NOT NULL,  -- invoice_overdue, contract_expiring
    trigger_conditions JSONB NOT NULL,  -- {"days": 14, "min_amount": 100}

    -- Aktionen
    actions JSONB NOT NULL,  -- [{"type": "notify", "channels": [...]}]

    -- Empfaenger
    recipients JSONB NOT NULL,  -- {"roles": [...], "departments": [...]}

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_by_id UUID REFERENCES users(id),
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX ix_rules_scope ON notification_rules(scope);
CREATE INDEX ix_rules_trigger ON notification_rules(trigger_type);
CREATE INDEX ix_rules_active ON notification_rules(is_active) WHERE is_active = true;
```

#### `notification_settings`

```sql
CREATE TABLE notification_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,

    -- Kanaele
    channels JSONB DEFAULT '{
        "in_app": {"enabled": true},
        "email": {"enabled": true, "mode": "digest"},
        "slack": {"enabled": false},
        "teams": {"enabled": false},
        "push": {"enabled": false}
    }',

    -- Kategorie-Einstellungen
    categories JSONB DEFAULT '{
        "payments": {"enabled": true},
        "contracts": {"enabled": true},
        "documents": {"enabled": true},
        "system": {"enabled": true}
    }',

    -- Ruhezeiten
    quiet_hours JSONB DEFAULT '{
        "enabled": false,
        "start": "18:00",
        "end": "08:00",
        "timezone": "Europe/Berlin"
    }',

    -- Audit
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX ix_notification_settings_user ON notification_settings(user_id);
```

---

## Regel-Engine

### Vordefinierte Trigger-Typen

| Trigger | Beschreibung | Parameter |
|---------|--------------|-----------|
| `invoice_overdue` | Rechnung ueberfaellig | days, min_amount |
| `invoice_skonto_expiring` | Skonto laeuft ab | days_before |
| `contract_expiring` | Vertrag laeuft aus | days_before |
| `contract_cancellation` | Kuendigungsfrist | days_before |
| `document_new` | Neues Dokument | types[] |
| `document_needs_validation` | Validierung noetig | max_age_hours |
| `supplier_delivery` | Lieferung erwartet | days_before |
| `tax_deadline` | Steuer-Frist | deadline_type |

### Regel-Definition (JSON)

```json
{
  "name": "Mahnung bei 14 Tagen ueberfaellig",
  "trigger_type": "invoice_overdue",
  "trigger_conditions": {
    "days_overdue": 14,
    "min_amount": 100,
    "excluded_customers": []
  },
  "actions": [
    {
      "type": "notification",
      "channels": ["in_app", "email", "slack"],
      "severity": "warning"
    },
    {
      "type": "create_task",
      "assign_to": "buchhaltung",
      "title": "Mahnung erstellen fuer {{invoice_number}}"
    }
  ],
  "recipients": {
    "roles": ["buchhaltung", "geschaeftsfuehrung"],
    "departments": ["finanzen"]
  },
  "schedule": {
    "check_interval": "1h",
    "send_once": true  // Nicht wiederholen
  }
}
```

### Service-Architektur

```python
# app/services/notification_service.py

class NotificationService:
    """Zentrale Benachrichtigungs-Logik."""

    async def send_notification(
        self,
        user_id: UUID,
        notification_type: str,
        title: str,
        message: str,
        data: dict = None,
        severity: str = "info"
    ) -> Notification:
        """Sendet Benachrichtigung an User ueber konfigurierte Kanaele."""

        # 1. User-Settings laden
        settings = await self.get_effective_settings(user_id)

        # 2. Quiet Hours pruefen
        if self.is_quiet_hour(settings):
            return await self.queue_for_later(...)

        # 3. Kanaele ermitteln
        channels = self.get_channels_for_type(notification_type, settings)

        # 4. Notification erstellen
        notification = await self.create_notification(...)

        # 5. An Kanaele senden
        for channel in channels:
            await self.send_to_channel(channel, notification)

        return notification

    async def get_effective_settings(self, user_id: UUID) -> NotificationSettings:
        """Ermittelt effektive Settings aus allen 3 Ebenen."""

        # Ebene 1: System-Defaults
        system_settings = await self.get_system_defaults()

        # Ebene 2: Rollen-Settings
        user_roles = await self.get_user_roles(user_id)
        role_settings = await self.get_role_settings(user_roles)

        # Ebene 3: User-Settings
        user_settings = await self.get_user_settings(user_id)

        # Merge mit Prioritaet: User > Role > System
        return self.merge_settings(system_settings, role_settings, user_settings)
```

---

## Implementation Tasks

### Phase 1: Core-Infrastruktur (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 1.1 | [ ] DB-Tabellen | notifications, rules, settings | Migration fehlerfrei | - |
| 1.2 | [ ] Notification Model | SQLAlchemy + Pydantic | mypy clean | 1.1 |
| 1.3 | [ ] NotificationService | CRUD + Send-Logik | Unit Tests | 1.2 |
| 1.4 | [ ] Celery Task | Async Versand | Task laeuft | 1.3 |

### Phase 2: Kanaele (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 2.1 | [ ] In-App Kanal | DB + WebSocket Push | Sofort sichtbar | 1.4 |
| 2.2 | [ ] E-Mail Kanal | SMTP + Templates | E-Mail zugestellt | 2.1 |
| 2.3 | [ ] Slack Integration | Webhook | Message in Channel | 2.2 |
| 2.4 | [ ] Teams Integration | Webhook | Message in Teams | 2.3 |
| 2.5 | [ ] Browser Push | Service Worker | Push funktioniert | 2.4 |

### Phase 3: Regel-Engine (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 3.1 | [ ] Trigger-System | Vordefinierte Trigger | Trigger feuern | 2.5 |
| 3.2 | [ ] Condition-Evaluator | JSONB Bedingungen | Korrekt ausgewertet | 3.1 |
| 3.3 | [ ] Action-Executor | Notifications + Tasks | Aktionen ausgefuehrt | 3.2 |
| 3.4 | [ ] Scheduler | Celery Beat Schedule | Regelmaessige Checks | 3.3 |

### Phase 4: Frontend (1 Woche)

| # | Task | Beschreibung | Akzeptanzkriterium | Abhaengigkeit |
|---|------|--------------|-------------------|---------------|
| 4.1 | [ ] Notification Widget | Dashboard + Badge | Badge zeigt Count | 3.4 |
| 4.2 | [ ] Notification List | Alle Benachrichtigungen | Filter funktioniert | 4.1 |
| 4.3 | [ ] Settings UI | User-Praeferenzen | Speichern funktioniert | 4.2 |
| 4.4 | [ ] Admin Rules UI | Regel-Verwaltung | CRUD funktioniert | 4.3 |
| 4.5 | [ ] WebSocket Integration | Realtime Updates | Sofort sichtbar | 4.4 |

---

## Test-Szenarien

### Unit Tests

```python
# tests/unit/services/test_notification_service.py

class TestNotificationSending:

    @pytest.mark.asyncio
    async def test_sends_to_configured_channels(self, service, user_with_email_slack):
        """Sendet an alle konfigurierten Kanaele."""
        notification = await service.send_notification(
            user_id=user_with_email_slack.id,
            notification_type="invoice_overdue",
            title="Test",
            message="Test Message"
        )

        assert "in_app" in notification.channels_sent
        assert "email" in notification.channels_sent
        assert "slack" in notification.channels_sent

    @pytest.mark.asyncio
    async def test_respects_quiet_hours(self, service, user_with_quiet_hours):
        """Sendet nicht waehrend Ruhezeiten (ausser In-App)."""
        with freeze_time("2026-01-15 22:00:00"):  # In Quiet Hours
            notification = await service.send_notification(...)

        # E-Mail sollte gequeued, nicht gesendet sein
        assert notification.email_sent_at is None
        assert "email" not in notification.channels_sent


class TestEffectiveSettings:

    @pytest.mark.asyncio
    async def test_user_overrides_role(self, service, user_overriding_role):
        """User-Einstellung hat Vorrang vor Rolle."""
        settings = await service.get_effective_settings(user_overriding_role.id)

        # User hat E-Mail deaktiviert, Rolle hatte es aktiv
        assert settings.channels.email.enabled is False

    @pytest.mark.asyncio
    async def test_role_overrides_system(self, service, user_with_role_settings):
        """Rollen-Einstellung hat Vorrang vor System."""
        settings = await service.get_effective_settings(user_with_role_settings.id)

        # Rolle hat min_amount auf 500 gesetzt, System hatte 100
        assert settings.categories.payments.min_amount == 500
```

### Integration Tests

```python
@pytest.mark.integration
class TestNotificationFlow:

    @pytest.mark.asyncio
    async def test_overdue_invoice_triggers_notification(
        self, async_client, overdue_invoice
    ):
        """Ueberfaellige Rechnung loest Benachrichtigung aus."""
        # Trigger-Check ausfuehren
        await run_notification_checks()

        # Notification sollte existieren
        response = await async_client.get(
            "/api/v1/notifications?category=payments",
            headers=auth_headers
        )

        assert response.status_code == 200
        notifications = response.json()["items"]
        assert any(
            n["type"] == "invoice_overdue" and
            overdue_invoice.id in n["data"]["document_id"]
            for n in notifications
        )
```

---

## Quality Gates

### Vor Merge

- [ ] **Funktionalitaet**
  - [ ] Alle 5 Kanaele funktionieren
  - [ ] Dreistufige Hierarchie korrekt
  - [ ] Regel-Engine evaluiert richtig
  - [ ] Quiet Hours respektiert

- [ ] **Performance**
  - [ ] Versand < 5 Sekunden
  - [ ] 10.000 Notifications/Tag moeglich

- [ ] **Testing**
  - [ ] Unit Tests >80%
  - [ ] E2E fuer kritische Flows

### Definition of Done

1. [ ] In-App Notifications mit Badge
2. [ ] E-Mail Digest und Sofort-Versand
3. [ ] Slack/Teams Integration
4. [ ] User-Settings UI
5. [ ] Admin Regel-Verwaltung
6. [ ] Mindestens 5 vordefinierte Regeln aktiv
