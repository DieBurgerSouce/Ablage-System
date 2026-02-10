# Workflow Execution Visualization - Backend Implementation

**Status**: ✅ Implementiert (Phase B)
**Version**: 1.0.0
**Datum**: 2026-02-10
**Migration**: N/A (verwendet bestehende Tabellen)

---

## Übersicht

Die Workflow Execution Visualization ermöglicht Echtzeit-Überwachung von Workflow-Ausführungen mit detaillierten Status-Informationen, Zeitleisten und Performance-Metriken.

### Features

✅ **Echtzeit-Status**: Live-Updates über WebSocket
✅ **Knoten-Details**: Status, Timing, Fehler für jeden Schritt
✅ **Ausführungs-Zeitleiste**: Chronologische Historie aller Schritte
✅ **Performance-Metriken**: Durchschnittszeiten, Engpässe, langsamste Schritte
✅ **Multi-Tenant Security**: Company-basierte Isolation

---

## Architektur

### Event Broadcasting

**Datei**: `app/services/realtime/event_broadcaster.py`

#### Neue Event-Typen

```python
class RealtimeEventType(str, Enum):
    # Workflow Execution Events (Phase B)
    WORKFLOW_STEP_STARTED = "workflow.step_started"
    WORKFLOW_STEP_COMPLETED = "workflow.step_completed"
    WORKFLOW_STEP_FAILED = "workflow.step_failed"
    WORKFLOW_INSTANCE_COMPLETED = "workflow.instance_completed"
    WORKFLOW_SLA_WARNING = "workflow.sla_warning"
```

#### Event-Handler

```python
async def _handle_workflow_event(self, event: Event) -> None:
    """Verarbeitet Workflow Execution Events."""
    # Maps internal events to realtime events
    # Broadcasts to connected WebSocket clients
```

#### Convenience Methods

```python
# Schritt-Start emittieren
await broadcaster.emit_workflow_step_started(
    instance_id="uuid",
    step_id="uuid",
    step_name="Dokument verschieben",
    step_type="action"
)

# Schritt-Abschluss emittieren
await broadcaster.emit_workflow_step_completed(
    instance_id="uuid",
    step_id="uuid",
    step_name="Dokument verschieben",
    duration_ms=1234,
    next_steps=["uuid2", "uuid3"]
)

# Schritt-Fehler emittieren
await broadcaster.emit_workflow_step_failed(
    instance_id="uuid",
    step_id="uuid",
    step_name="Dokument verschieben",
    error_message="Zielordner nicht gefunden"
)

# Instanz-Abschluss emittieren
await broadcaster.emit_workflow_instance_completed(
    instance_id="uuid",
    workflow_id="uuid",
    workflow_name="Rechnungs-Workflow",
    status="completed",
    total_duration_ms=5678,
    steps_completed=5,
    steps_failed=0
)

# SLA-Warnung emittieren
await broadcaster.emit_workflow_sla_warning(
    instance_id="uuid",
    step_id="uuid",
    step_name="Genehmigung",
    sla_deadline="2026-02-10T15:00:00Z",
    elapsed_seconds=3600
)
```

---

## API Endpoints

**Datei**: `app/api/v1/workflows.py`

### 1. GET `/workflows/executions/{instance_id}/state`

**Beschreibung**: Ruft den aktuellen Ausführungsstatus ab

**Response**:
```python
{
  "instance_id": "uuid",
  "workflow_id": "uuid",
  "workflow_name": "Rechnungs-Workflow",
  "status": "running",  # pending, running, completed, failed, cancelled
  "progress_percent": 60,
  "started_at": "2026-02-10T14:00:00Z",
  "completed_at": null,
  "nodes": [
    {
      "node_id": "uuid1",
      "node_type": "action",  # action, condition, branch, delay, parallel, loop
      "node_name": "Dokument hochladen",
      "status": "completed",  # pending, active, completed, failed, skipped, warning
      "started_at": "2026-02-10T14:00:00Z",
      "completed_at": "2026-02-10T14:00:02Z",
      "duration_ms": 2000,
      "error_message": null,
      "sla_deadline": null,
      "sla_status": null
    },
    {
      "node_id": "uuid2",
      "node_type": "condition",
      "node_name": "Betrag prüfen",
      "status": "active",
      "started_at": "2026-02-10T14:00:02Z",
      "completed_at": null,
      "duration_ms": null,
      "error_message": null,
      "sla_deadline": "2026-02-10T15:00:00Z",
      "sla_status": "ok"
    }
  ],
  "active_step_ids": ["uuid2"]
}
```

**Security**:
- Verifiziert `triggered_by_id == current_user.id`
- Prüft `workflow.company_id == company_id` (Multi-Tenant)

---

### 2. GET `/workflows/executions/{instance_id}/timeline`

**Beschreibung**: Ruft die chronologische Ausführungs-Zeitleiste ab

**Response**:
```python
[
  {
    "step_id": "uuid1",
    "step_name": "Dokument hochladen",
    "step_type": "action",
    "status": "completed",
    "started_at": "2026-02-10T14:00:00Z",
    "completed_at": "2026-02-10T14:00:02Z",
    "duration_ms": 2000,
    "input_summary": "5 Felder",
    "output_summary": "3 Felder",
    "error_message": null
  },
  {
    "step_id": "uuid2",
    "step_name": "OCR durchführen",
    "step_type": "action",
    "status": "completed",
    "started_at": "2026-02-10T14:00:02Z",
    "completed_at": "2026-02-10T14:00:05Z",
    "duration_ms": 3000,
    "input_summary": "1 Felder",
    "output_summary": "10 Felder",
    "error_message": null
  }
]
```

**Sortierung**: Nach `execution_order` (chronologisch)

---

### 3. GET `/workflows/executions/{instance_id}/metrics`

**Beschreibung**: Ruft Performance-Metriken ab

**Response**:
```python
{
  "instance_id": "uuid",
  "total_duration_ms": 5678,
  "steps_completed": 5,
  "steps_failed": 0,
  "steps_pending": 1,
  "avg_step_duration_ms": 1135.6,
  "slowest_step": "OCR durchführen",
  "slowest_step_duration_ms": 3000,
  "bottleneck_step": "Genehmigung"  # Schritt mit längster Wartezeit
}
```

**Berechnungen**:
- `avg_step_duration_ms`: Durchschnitt aller abgeschlossenen Schritte
- `slowest_step`: Schritt mit höchstem `duration_ms`
- `bottleneck_step`: Schritt mit längster Wartezeit zwischen `prev.completed_at` und `current.started_at`

---

## Datenbank-Schema

### Verwendete Tabellen

#### `workflow_executions`
```sql
id                     UUID PRIMARY KEY
workflow_id            UUID (FK workflows.id)
company_id             UUID (FK companies.id)  -- Multi-Tenant
triggered_by_id        UUID (FK users.id)
status                 VARCHAR(20)  -- pending, running, completed, failed, cancelled
progress_percent       INTEGER
started_at             TIMESTAMP
completed_at           TIMESTAMP
duration_ms            INTEGER
```

#### `workflow_step_executions`
```sql
id                     UUID PRIMARY KEY
workflow_execution_id  UUID (FK workflow_executions.id)
workflow_step_id       UUID (FK workflow_steps.id)
execution_order        INTEGER
status                 VARCHAR(20)  -- pending, running, completed, failed, skipped
input_data             JSONB
output_data            JSONB
error_message          TEXT
started_at             TIMESTAMP
completed_at           TIMESTAMP
duration_ms            INTEGER
```

#### `workflow_steps`
```sql
id                     UUID PRIMARY KEY
workflow_id            UUID (FK workflows.id)
step_order             INTEGER
name                   VARCHAR(255)
step_type              VARCHAR(30)  -- action, condition, branch, delay, parallel, loop
```

---

## Integration mit Services

### WorkflowExecutionService

**Datei**: `app/services/workflow/workflow_execution_service.py`

**Emit-Punkte**:

```python
from app.services.realtime.event_broadcaster import get_event_broadcaster

# Bei Schritt-Start
async def _execute_step(self, step_execution: WorkflowStepExecution):
    broadcaster = get_event_broadcaster()
    await broadcaster.emit_workflow_step_started(
        instance_id=str(self.execution.id),
        step_id=str(step_execution.workflow_step_id),
        step_name=step_execution.workflow_step.name,
        step_type=step_execution.workflow_step.step_type,
        user_id=str(self.execution.triggered_by_id),
        company_id=str(self.execution.company_id)
    )

    # ... Schritt ausführen ...

    # Bei Erfolg
    await broadcaster.emit_workflow_step_completed(
        instance_id=str(self.execution.id),
        step_id=str(step_execution.workflow_step_id),
        step_name=step_execution.workflow_step.name,
        duration_ms=duration,
        next_steps=[str(s) for s in next_step_ids],
        user_id=str(self.execution.triggered_by_id),
        company_id=str(self.execution.company_id)
    )

    # Bei Fehler
    except Exception as e:
        await broadcaster.emit_workflow_step_failed(
            instance_id=str(self.execution.id),
            step_id=str(step_execution.workflow_step_id),
            step_name=step_execution.workflow_step.name,
            error_message=str(e),
            user_id=str(self.execution.triggered_by_id),
            company_id=str(self.execution.company_id)
        )
```

---

## Security Considerations

### Multi-Tenant Isolation

**Alle Endpoints prüfen**:
1. `triggered_by_id == current_user.id` (Ownership)
2. `workflow.company_id == company_id` (Company-Zugehörigkeit)

```python
# SECURITY: company_id via UserCompany-Tabelle
company_id = await get_user_company_id(db, current_user)

# SECURITY: Verify ownership
if execution.triggered_by_id != current_user.id:
    raise HTTPException(status_code=403, detail="Keine Berechtigung")

# SECURITY: Verify company_id
if company_id and execution.workflow.company_id != company_id:
    raise HTTPException(status_code=403, detail="Keine Berechtigung")
```

### PII-Schutz

**Input/Output-Summaries**:
- Nur generische Zusammenfassungen (`"5 Felder"`)
- KEINE sensiblen Daten in Timeline-Summaries
- Vollständige Daten nur in `step_executions` Tabelle (separater Zugriff)

---

## Frontend Integration

### WebSocket Subscription

```typescript
// WebSocket verbinden
const ws = useWebSocket('/ws/realtime');

// Workflow-Events abonnieren
ws.subscribe('workflow.*', (event) => {
  if (event.type === 'workflow.step_started') {
    updateNodeStatus(event.payload.step_id, 'active');
  }

  if (event.type === 'workflow.step_completed') {
    updateNodeStatus(event.payload.step_id, 'completed');
    updateNodeDuration(event.payload.step_id, event.payload.duration_ms);
  }

  if (event.type === 'workflow.step_failed') {
    updateNodeStatus(event.payload.step_id, 'failed');
    showError(event.payload.error_message);
  }

  if (event.type === 'workflow.instance_completed') {
    showCompletionDialog(event.payload);
  }
});
```

### State Polling (Fallback)

```typescript
// Polling-Fallback wenn WebSocket nicht verfügbar
const { data: state } = useQuery({
  queryKey: ['workflow-execution', instanceId],
  queryFn: () => api.get(`/workflows/executions/${instanceId}/state`),
  refetchInterval: 2000, // 2 Sekunden
  enabled: !wsConnected
});
```

### ReactFlow Integration

```typescript
// Knoten-Status in ReactFlow aktualisieren
const nodes = state.nodes.map(node => ({
  id: node.node_id,
  type: node.node_type,
  data: {
    label: node.node_name,
    status: node.status,
    duration: node.duration_ms,
    error: node.error_message,
    sla: node.sla_status
  },
  className: `node-${node.status}` // CSS-Klassen für Farben
}));
```

---

## Testing

### Unit Tests

**Datei**: `tests/unit/services/realtime/test_event_broadcaster.py`

```python
@pytest.mark.asyncio
async def test_emit_workflow_step_started():
    broadcaster = EventBroadcaster()

    await broadcaster.emit_workflow_step_started(
        instance_id="test-uuid",
        step_id="step-uuid",
        step_name="Test Step",
        step_type="action"
    )

    # Verify event was broadcasted
    # ...
```

### Integration Tests

**Datei**: `tests/integration/api/v1/test_workflows_execution.py`

```python
@pytest.mark.asyncio
async def test_get_execution_state(client, test_user):
    # Create workflow execution
    execution = await create_test_execution()

    # Get state
    response = await client.get(f"/workflows/executions/{execution.id}/state")

    assert response.status_code == 200
    data = response.json()
    assert data["instance_id"] == str(execution.id)
    assert len(data["nodes"]) > 0
```

### E2E Tests (Playwright)

```typescript
test('workflow execution visualization', async ({ page }) => {
  // Start workflow
  await page.click('[data-testid="execute-workflow"]');

  // Wait for execution to start
  await page.waitForSelector('[data-testid="execution-state"]');

  // Verify real-time updates
  await expect(page.locator('.node-active')).toBeVisible();

  // Wait for completion
  await page.waitForSelector('[data-testid="execution-completed"]');

  // Verify metrics
  const metrics = await page.locator('[data-testid="execution-metrics"]').textContent();
  expect(metrics).toContain('Schritte abgeschlossen: 5');
});
```

---

## Performance Considerations

### Database Queries

**Optimierungen**:
- `selectinload()` für Relationships (vermeidet N+1-Queries)
- Index auf `workflow_execution_id` in `workflow_step_executions`
- Index auf `execution_order` für Timeline-Sortierung

### Caching

**Redis-Cache für häufige Zugriffe**:
```python
@cache(ttl=5)  # 5 Sekunden Cache
async def get_execution_state(instance_id: UUID):
    # ...
```

### WebSocket Throttling

**Event-Aggregation** (bereits in `EventBroadcaster`):
- Max 20 Events pro 5 Sekunden pro Company
- Aggregation bei High-Volume (>10 Events)

---

## Monitoring & Observability

### Prometheus Metriken

```python
workflow_execution_duration_seconds = Histogram(
    'workflow_execution_duration_seconds',
    'Workflow execution duration',
    ['workflow_name', 'status']
)

workflow_step_duration_seconds = Histogram(
    'workflow_step_duration_seconds',
    'Workflow step duration',
    ['workflow_name', 'step_type']
)

workflow_execution_total = Counter(
    'workflow_execution_total',
    'Total workflow executions',
    ['workflow_name', 'status']
)
```

### Grafana Dashboards

**Dashboard**: `Workflow Execution Monitoring`

**Panels**:
- Execution Duration (Histogram)
- Success Rate (Gauge)
- Active Executions (Graph)
- Failed Steps (Counter)
- Bottleneck Steps (Table)

---

## Migration Notes

**Keine Migration erforderlich**

Die Implementierung nutzt die bestehenden Tabellen:
- `workflow_executions`
- `workflow_step_executions`
- `workflow_steps`
- `workflows`

Alle erforderlichen Felder sind bereits vorhanden.

---

## Changelog

### Version 1.0.0 (2026-02-10)

**Added**:
- ✅ Event-Typen in `RealtimeEventType`
- ✅ Event-Handler `_handle_workflow_event`
- ✅ Convenience Methods für Event-Emission
- ✅ API-Endpoint `/executions/{id}/state`
- ✅ API-Endpoint `/executions/{id}/timeline`
- ✅ API-Endpoint `/executions/{id}/metrics`
- ✅ Multi-Tenant Security Checks
- ✅ Pydantic Schemas für Responses

**Documentation**:
- ✅ Feature-Dokumentation
- ✅ Integration-Anleitung
- ✅ Security Considerations
- ✅ Testing-Beispiele

---

## Next Steps (Phase C - Frontend)

1. **ReactFlow Visualisierung**
   - Workflow-Graph mit Echtzeit-Status
   - Knoten-Farben basierend auf Status
   - Animations für Übergänge

2. **Timeline-Komponente**
   - Vertikale Zeitleiste mit allen Schritten
   - Expandierbare Details (Input/Output)
   - Fehler-Highlighting

3. **Metrics-Dashboard**
   - Performance-KPIs (Durchschnitt, Langsamste)
   - Engpass-Analyse
   - SLA-Tracking

4. **WebSocket Integration**
   - Live-Updates ohne Polling
   - Reconnection-Handling
   - Event-Subscription

---

## Support & Troubleshooting

### Häufige Probleme

**Problem**: Events werden nicht emittiert
**Lösung**: Prüfen ob `EventBroadcaster.start()` aufgerufen wurde

**Problem**: WebSocket disconnects
**Lösung**: Fallback auf Polling (2-Sekunden-Intervall)

**Problem**: Langsame State-Abfrage
**Lösung**: Redis-Cache aktivieren (`@cache(ttl=5)`)

### Logs

```bash
# Event Broadcaster Logs
grep "workflow_event" /var/log/ablage-system/app.log

# API Request Logs
grep "GET /workflows/executions/.*/state" /var/log/nginx/access.log
```

---

**Autor**: Backend API Developer (Claude Code)
**Reviewed by**: -
**Status**: ✅ Production-Ready
