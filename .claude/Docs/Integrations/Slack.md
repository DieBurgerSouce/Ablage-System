# Slack Integration

> **Letzte Aktualisierung**: 2026-01-27
> **Status**: Production-Ready
> **Migration**: 100 (add_slack_integration)

---

## Übersicht

Die Slack Integration ermöglicht automatische Benachrichtigungen an Slack-Kanäle für wichtige Geschäftsereignisse. Der Service unterstützt sowohl einfache Webhooks als auch erweiterte Bot-Funktionen mit Block Kit Formatting.

**Basis-URL**: `/api/v1/slack`
**Authentifizierung**: JWT Bearer Token erforderlich (Admin für Konfiguration)
**Multi-Tenant**: Company-spezifische Kanäle und Konfiguration

---

## Benachrichtigungstypen

| Typ | Code | Beschreibung |
|-----|------|--------------|
| Dokument verarbeitet | `document_processed` | Nach erfolgreicher OCR-Verarbeitung |
| Dokument-Fehler | `document_error` | Bei OCR- oder Verarbeitungsfehlern |
| Genehmigung erforderlich | `approval_required` | Workflow wartet auf Genehmigung |
| Genehmigung abgeschlossen | `approval_completed` | Dokument wurde genehmigt/abgelehnt |
| Workflow abgeschlossen | `workflow_completed` | Workflow erfolgreich beendet |
| High-Risk Entity | `high_risk_entity` | Geschäftspartner mit hohem Risiko-Score |
| Mahnstufen-Eskalation | `dunning_escalation` | Mahnstufe erhöht |
| Skonto läuft ab | `skonto_expiring` | Skonto-Frist endet bald |
| Report generiert | `report_generated` | Report wurde erstellt |
| System-Alert | `system_alert` | System-Benachrichtigung |
| Benutzerdefiniert | `custom` | Freie Nachricht |

---

## Nachrichtenprioritäten

| Priorität | Code | Verhalten |
|-----------|------|-----------|
| Niedrig | `low` | Normale Zustellung |
| Normal | `normal` | Standard (default) |
| Hoch | `high` | Visuelle Hervorhebung |
| Dringend | `urgent` | @channel Mention |

---

## Core Service

| Service | Datei | Zweck |
|---------|-------|-------|
| **SlackService** | `slack_service.py` | Singleton-Service für Slack-Kommunikation |

**Features**:
- Webhook-basierte Benachrichtigungen
- Block Kit für reichhaltige Nachrichten
- Rate Limiting mit Sliding Window (30/min default)
- Retry-Logik für temporäre Fehler
- Thread-Support für Konversationen

---

## Endpunkte

### Konfiguration

#### GET /slack/config

Ruft die aktuelle Slack-Konfiguration ab (Admin).

**Response** (200):
```json
{
  "enabled": true,
  "webhook_configured": true,
  "bot_configured": false,
  "default_channel": "#ablage-notifications",
  "notification_types": [
    "document_processed",
    "approval_required",
    "high_risk_entity",
    "system_alert"
  ],
  "rate_limit_per_minute": 30
}
```

---

#### PATCH /slack/config

Aktualisiert die Slack-Konfiguration (Admin).

**Request Body**:
```json
{
  "enabled": true,
  "default_channel": "#ablage-notifications",
  "notification_types": [
    "document_processed",
    "approval_required",
    "high_risk_entity"
  ]
}
```

**Response** (200):
```json
{
  "enabled": true,
  "default_channel": "#ablage-notifications",
  "notification_types": [...],
  "updated_at": "2026-01-27T10:00:00Z"
}
```

---

#### POST /slack/test

Sendet eine Testnachricht zur Überprüfung der Konfiguration (Admin).

**Request Body**:
```json
{
  "channel": "#test-channel"
}
```

**Response** (200):
```json
{
  "success": true,
  "message": "Testnachricht erfolgreich gesendet",
  "channel": "#test-channel",
  "timestamp": "1706349600.123456"
}
```

---

### Benachrichtigungen senden

#### POST /slack/notify

Sendet eine Benachrichtigung an Slack.

**Request Body**:
```json
{
  "notification_type": "document_processed",
  "title": "Dokument verarbeitet",
  "message": "Rechnung #12345 wurde erfolgreich verarbeitet",
  "priority": "normal",
  "channel": "#rechnungen",
  "context": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "confidence": 0.95,
    "processing_time_ms": 1250
  },
  "attachments": [
    {
      "color": "#36a64f",
      "title": "Rechnungsdetails",
      "fields": [
        {
          "title": "Betrag",
          "value": "1.250,00 €",
          "short": true
        },
        {
          "title": "Lieferant",
          "value": "Müller GmbH",
          "short": true
        }
      ]
    }
  ]
}
```

**Response** (200):
```json
{
  "success": true,
  "message_ts": "1706349600.123456",
  "channel": "#rechnungen"
}
```

---

#### POST /slack/notify/bulk

Sendet mehrere Benachrichtigungen (mit Rate Limiting).

**Request Body**:
```json
{
  "notifications": [
    {
      "notification_type": "document_processed",
      "title": "Rechnung #12345",
      "message": "Verarbeitung abgeschlossen"
    },
    {
      "notification_type": "document_processed",
      "title": "Rechnung #12346",
      "message": "Verarbeitung abgeschlossen"
    }
  ]
}
```

**Response** (200):
```json
{
  "sent": 2,
  "failed": 0,
  "results": [
    {"success": true, "message_ts": "1706349600.123456"},
    {"success": true, "message_ts": "1706349601.234567"}
  ]
}
```

---

### Thread-Support

#### POST /slack/reply

Antwortet in einem bestehenden Thread.

**Request Body**:
```json
{
  "thread_ts": "1706349600.123456",
  "channel": "#rechnungen",
  "message": "Update: Rechnung wurde genehmigt",
  "broadcast": false
}
```

**Response** (200):
```json
{
  "success": true,
  "message_ts": "1706349700.345678",
  "thread_ts": "1706349600.123456"
}
```

---

## Block Kit Support

Der Service unterstützt Slack Block Kit für reichhaltige Nachrichten.

### Beispiel mit Blocks

```json
{
  "notification_type": "approval_required",
  "title": "Genehmigung erforderlich",
  "message": "Rechnung über 5.000 € wartet auf Freigabe",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "Genehmigung erforderlich"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Rechnung RE-2026-001234*\nLieferant: Müller Office GmbH\nBetrag: *5.250,00 €*"
      },
      "accessory": {
        "type": "button",
        "text": {
          "type": "plain_text",
          "text": "Öffnen"
        },
        "url": "https://ablage.local/documents/..."
      }
    },
    {
      "type": "actions",
      "elements": [
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Genehmigen"
          },
          "style": "primary",
          "value": "approve"
        },
        {
          "type": "button",
          "text": {
            "type": "plain_text",
            "text": "Ablehnen"
          },
          "style": "danger",
          "value": "reject"
        }
      ]
    }
  ]
}
```

---

## Konfiguration

### Umgebungsvariablen

```python
# Webhook URL (einfache Integration)
SLACK_WEBHOOK_URL: SecretStr  # https://hooks.slack.com/services/...

# Bot Token (erweiterte Features)
SLACK_BOT_TOKEN: SecretStr    # xoxb-...

# Standard-Einstellungen
SLACK_DEFAULT_CHANNEL: str = "#ablage-notifications"
SLACK_ENABLED: bool = True
SLACK_RATE_LIMIT_PER_MINUTE: int = 30

# Aktivierte Benachrichtigungstypen
SLACK_NOTIFICATION_TYPES: list[str] = [
    "document_processed",
    "approval_required",
    "high_risk_entity",
    "system_alert"
]
```

### Webhook vs. Bot Token

| Feature | Webhook | Bot Token |
|---------|---------|-----------|
| Einfache Nachrichten | ✅ | ✅ |
| Block Kit | ✅ | ✅ |
| Thread-Antworten | ❌ | ✅ |
| Datei-Uploads | ❌ | ✅ |
| Slash-Commands | ❌ | ✅ |
| Interaktive Buttons | ❌ | ✅ |
| Kanal-Wechsel | ❌ | ✅ |

---

## Rate Limiting

Der Service implementiert ein Sliding-Window Rate Limiting:

- **Standard-Limit**: 30 Nachrichten pro Minute
- **Burst**: Kurze Bursts werden toleriert
- **Backoff**: Bei Slack-429 wird automatisch gewartet

```python
# Bei Rate Limit
{
  "error": "Rate limit erreicht",
  "retry_after_seconds": 60,
  "remaining_in_window": 0
}
```

---

## Celery Tasks

| Task | Trigger | Beschreibung |
|------|---------|--------------|
| `slack.send_notification` | Event-basiert | Asynchrone Nachricht senden |
| `slack.send_digest` | Täglich 08:00 | Tagesübersicht senden |

---

## Event-Integration

Der Service reagiert auf Events vom Cross-Module-Orchestrator:

```python
# Automatische Benachrichtigungen bei:
EVENT_TYPE_DOCUMENT_PROCESSED  → document_processed
EVENT_TYPE_APPROVAL_REQUESTED  → approval_required
EVENT_TYPE_APPROVAL_COMPLETED  → approval_completed
EVENT_TYPE_RISK_SCORE_UPDATED  → high_risk_entity (wenn Score > 75)
EVENT_TYPE_DUNNING_ESCALATED   → dunning_escalation
EVENT_TYPE_SKONTO_EXPIRING     → skonto_expiring
```

---

## Fehler-Codes

| Code | HTTP | Beschreibung |
|------|------|--------------|
| `SLACK_NOT_CONFIGURED` | 503 | Slack-Integration nicht konfiguriert |
| `SLACK_RATE_LIMITED` | 429 | Rate Limit erreicht |
| `SLACK_SEND_FAILED` | 502 | Nachricht konnte nicht gesendet werden |
| `SLACK_INVALID_CHANNEL` | 400 | Ungültiger Kanal |
| `SLACK_CHANNEL_NOT_FOUND` | 404 | Kanal nicht gefunden |

---

## Frontend

**Admin-Seite**: `/admin/slack`

Features:
- Webhook/Bot-Token Konfiguration
- Aktivierte Benachrichtigungstypen
- Test-Nachricht senden
- Rate-Limit-Status
- Gesendete Nachrichten (letzte 24h)

---

## Sicherheitshinweise

1. **Credentials**: Webhook-URL und Bot-Token als SecretStr verschlüsselt
2. **Rate Limiting**: Schutz vor Spam und API-Missbrauch
3. **Multi-Tenant**: Company-spezifische Kanäle
4. **Audit-Logging**: Alle gesendeten Nachrichten werden protokolliert
5. **PII-Schutz**: Sensible Daten werden nicht in Slack-Nachrichten geleakt

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-01-27 | 1.0 | Initial Release |
