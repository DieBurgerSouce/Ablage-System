# Feature 09: Workflow-Automation

> **Status**: Ready for Implementation
> **Version**: 1.0.0
> **Erstellt**: 2026-01-02
> **Prioritaet**: P3 - Nice-to-Have
> **Geschaetzter Aufwand**: 5-6 Wochen
> **Abhaengigkeiten**: Feature 01, Feature 03, Feature 05

---

## Executive Summary

Die Workflow-Automation ermoeglicht es, komplexe Geschaeftsprozesse zu automatisieren. Ein visueller Regel-Editor erlaubt die Definition von WENN-DANN Regeln ohne Programmierung. Workflow-Ketten verknuepfen mehrere Schritte zu komplexen Ablaeufen.

**Business Value:**
- Automatisierung ohne Entwickler
- Konsistente Prozesse
- Zeitersparnis bei Routine-Aufgaben
- Eskalations-Management

---

## Anforderungen

### Funktionale Anforderungen

| ID | Anforderung | Prioritaet | Akzeptanzkriterium |
|----|-------------|-----------|-------------------|
| FR-01 | Visueller Regel-Editor | MUSS | WENN-DANN ohne Code |
| FR-02 | Vordefinierte Trigger | MUSS | 10+ Trigger-Typen |
| FR-03 | Vordefinierte Aktionen | MUSS | 8+ Aktions-Typen |
| FR-04 | Workflow-Ketten | SOLL | Multi-Step Workflows |
| FR-05 | Bedingte Verzweigungen | SOLL | IF/ELSE in Workflows |
| FR-06 | Eskalation nach Zeit | SOLL | Timeout → Eskalieren |
| FR-07 | Approval-Workflows | SOLL | Freigabe-Prozesse |

---

## Verfuegbare Trigger

| Trigger | Beschreibung | Parameter |
|---------|--------------|-----------|
| `document_uploaded` | Neues Dokument | types[], sources[] |
| `document_validated` | Dokument validiert | status |
| `invoice_overdue` | Rechnung ueberfaellig | days, min_amount |
| `contract_expiring` | Vertrag laeuft aus | days_before |
| `amount_exceeds` | Betrag ueberschreitet | threshold |
| `customer_new` | Neuer Kunde | - |
| `ocr_confidence_low` | KI unsicher | threshold |
| `time_based` | Zeitgesteuert | cron |
| `manual_trigger` | Manuell ausgeloest | - |
| `webhook_received` | Externer Webhook | source |

---

## Verfuegbare Aktionen

| Aktion | Beschreibung | Parameter |
|--------|--------------|-----------|
| `notify` | Benachrichtigen | users[], channels[] |
| `set_tag` | Label setzen | tag_name |
| `move_folder` | In Ordner verschieben | folder_id |
| `start_approval` | Freigabe starten | approvers[] |
| `export` | Exportieren | format, destination |
| `create_task` | Aufgabe erstellen | title, assignee |
| `send_email` | E-Mail senden | template, recipients[] |
| `call_webhook` | Webhook aufrufen | url, payload |
| `escalate` | Eskalieren | after_hours, to |
| `update_field` | Feld aktualisieren | field, value |

---

## API-Spezifikation

### Endpoints

| Method | Endpoint | Beschreibung | Auth |
|--------|----------|--------------|------|
| GET | `/api/v1/workflows/rules` | Alle Regeln | Required |
| POST | `/api/v1/workflows/rules` | Regel erstellen | Admin |
| PUT | `/api/v1/workflows/rules/{id}` | Regel bearbeiten | Admin |
| DELETE | `/api/v1/workflows/rules/{id}` | Regel loeschen | Admin |
| POST | `/api/v1/workflows/rules/{id}/test` | Regel testen | Admin |
| GET | `/api/v1/workflows/chains` | Workflow-Ketten | Required |
| POST | `/api/v1/workflows/chains` | Kette erstellen | Admin |
| GET | `/api/v1/workflows/executions` | Ausfuehrungen | Required |

### `POST /api/v1/workflows/rules`

**Request:**
```json
{
  "name": "Grosse Rechnungen zur Freigabe",
  "description": "Rechnungen >10.000€ benoetigen GF-Freigabe",
  "is_active": true,
  "trigger": {
    "type": "document_validated",
    "conditions": [
      {"field": "document_type", "operator": "equals", "value": "eingangsrechnung"},
      {"field": "amount", "operator": "greater_than", "value": 10000}
    ]
  },
  "actions": [
    {
      "type": "notify",
      "config": {
        "users": [],
        "roles": ["geschaeftsfuehrung"],
        "channels": ["email", "in_app"],
        "message_template": "freigabe_erforderlich"
      }
    },
    {
      "type": "set_tag",
      "config": {"tag": "freigabe_erforderlich"}
    },
    {
      "type": "start_approval",
      "config": {
        "approvers": [{"role": "geschaeftsfuehrung"}],
        "timeout_hours": 48,
        "escalate_to": "ceo"
      }
    }
  ],
  "priority": 10
}
```

---

## Datenbank-Schema

### `workflow_rules`

```sql
CREATE TABLE workflow_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) NOT NULL,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    trigger JSONB NOT NULL,
    conditions JSONB DEFAULT '[]',
    actions JSONB NOT NULL,

    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,

    execution_count INTEGER DEFAULT 0,
    last_executed_at TIMESTAMPTZ,

    created_by_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `workflow_chains`

```sql
CREATE TABLE workflow_chains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) NOT NULL,

    name VARCHAR(255) NOT NULL,
    description TEXT,

    steps JSONB NOT NULL,  -- Array of steps with conditions
    -- [{
    --   "id": "step-1",
    --   "rule_id": "rule-uuid",
    --   "next_on_success": "step-2",
    --   "next_on_failure": "step-error",
    --   "wait_conditions": {...}
    -- }]

    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `workflow_executions`

```sql
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    rule_id UUID REFERENCES workflow_rules(id),
    chain_id UUID REFERENCES workflow_chains(id),
    document_id UUID REFERENCES documents(id),

    trigger_data JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    -- pending, running, completed, failed, cancelled

    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    steps_executed JSONB DEFAULT '[]',
    error_message TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### `workflow_approvals`

```sql
CREATE TABLE workflow_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES workflow_executions(id) NOT NULL,
    document_id UUID REFERENCES documents(id) NOT NULL,

    status VARCHAR(20) DEFAULT 'pending',
    -- pending, approved, rejected, escalated

    approvers JSONB NOT NULL,
    approved_by_id UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,

    timeout_at TIMESTAMPTZ,
    escalated_to_id UUID REFERENCES users(id),

    comments TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Visueller Regel-Editor

```
┌─────────────────────────────────────────────────────────────┐
│  REGEL ERSTELLEN                                            │
├─────────────────────────────────────────────────────────────┤
│  Name: [Grosse Rechnungen zur Freigabe___________]          │
├─────────────────────────────────────────────────────────────┤
│  WENN                                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [Dokument-Typ ▼] [ist ▼] [Eingangsrechnung ▼]       │    │
│  │                                                      │    │
│  │ [+ UND Bedingung]                                   │    │
│  │                                                      │    │
│  │ [Betrag ▼] [groesser als ▼] [10000] [€]             │    │
│  │                                                      │    │
│  │ [+ UND Bedingung]                                   │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  DANN                                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [1] [Benachrichtigen ▼]                             │    │
│  │     Empfaenger: [Geschaeftsfuehrung ▼]              │    │
│  │     Kanaele: [x] In-App  [x] E-Mail  [ ] Slack      │    │
│  │                                                      │    │
│  │ [2] [Tag setzen ▼]                                  │    │
│  │     Tag: [Freigabe erforderlich]                    │    │
│  │                                                      │    │
│  │ [3] [Freigabe starten ▼]                            │    │
│  │     Genehmiger: [Geschaeftsfuehrung ▼]              │    │
│  │     Timeout: [48] Stunden                           │    │
│  │     Eskalieren an: [CEO ▼]                          │    │
│  │                                                      │    │
│  │ [+ Aktion hinzufuegen]                              │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│  [Abbrechen]              [Testen]         [Speichern]      │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Phase 1: Regel-Engine (2 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 1.1 | [ ] DB Schema | Rules, Executions, Approvals |
| 1.2 | [ ] Trigger-Registry | Alle Trigger registriert |
| 1.3 | [ ] Action-Registry | Alle Aktionen registriert |
| 1.4 | [ ] Condition-Evaluator | Bedingungen ausgewertet |
| 1.5 | [ ] Execution-Engine | Regeln ausgefuehrt |

### Phase 2: Workflow-Ketten (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 2.1 | [ ] Chain-Model | Multi-Step definierbar |
| 2.2 | [ ] Conditional Branching | IF/ELSE funktioniert |
| 2.3 | [ ] Wait-Conditions | Auf Events warten |
| 2.4 | [ ] Parallelisierung | Parallele Schritte |

### Phase 3: Approval-System (1 Woche)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 3.1 | [ ] Approval-Flow | Genehmigen/Ablehnen |
| 3.2 | [ ] Timeout-Handling | Nach X Stunden eskalieren |
| 3.3 | [ ] Notifications | Erinnerungen |
| 3.4 | [ ] Audit-Trail | Alle Entscheidungen geloggt |

### Phase 4: Frontend (1.5 Wochen)

| # | Task | Akzeptanzkriterium |
|---|------|-------------------|
| 4.1 | [ ] Regel-Editor UI | Visuell, Drag & Drop |
| 4.2 | [ ] Chain-Builder UI | Flow-Diagramm |
| 4.3 | [ ] Execution-Monitor | Status sichtbar |
| 4.4 | [ ] Approval-Inbox | Pending Approvals |

---

## Quality Gates

- [ ] Alle 10 Trigger funktionieren
- [ ] Alle 10 Aktionen funktionieren
- [ ] Workflow-Ketten laufen durch
- [ ] Approval-Flow vollstaendig
- [ ] Eskalation nach Timeout
- [ ] Audit-Trail komplett
