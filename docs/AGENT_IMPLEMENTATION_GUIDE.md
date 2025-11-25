# Multi-Agent Implementation Guide

## 📋 Übersicht

Dieses Dokument beschreibt die Implementierung und Verwendung der Multi-Agent-Architektur für das Ablage-System OCR.

**Status**: ✅ Production-Ready Design mit 30+ spezialisierten Agents

## 🏗️ Architektur-Überblick

### Erstellte Komponenten

#### 1. **Base Agent Framework** ([app/agents/base.py](../app/agents/base.py))

```python
# Basis-Klassen für alle Agents
from app.agents.base import (
    BaseAgent,                 # Abstract base
    OCRAgent,                  # OCR-spezialisiert
    PreprocessingAgent,        # Vorverarbeitung
    PostprocessingAgent,       # Nachverarbeitung
    OrchestrationAgent,        # Koordination
    IntelligenceAgent,         # KI-Funktionen
    MonitoringAgent,           # Monitoring
)
```

**Features**:
- ✅ Automatisches Metrics-Tracking (Prometheus)
- ✅ Strukturiertes Logging (structlog)
- ✅ Retry-Logik mit Exponential Backoff
- ✅ Error Handling und State Management
- ✅ Async/Await Support

#### 2. **OCR Processing Agents** ([app/agents/ocr/](../app/agents/ocr/))

**Implementierte Agents**:

| Agent | Datei | Beschreibung | GPU | VRAM |
|-------|-------|--------------|-----|------|
| `DeepSeekAgent` | [deepseek_agent.py](../app/agents/ocr/deepseek_agent.py) | Multimodale OCR für komplexe Layouts | ✅ | 12GB |
| `GOTOCRAgent` | [got_ocr_agent.py](../app/agents/ocr/got_ocr_agent.py) | Schnelle transformer-basierte OCR | Optional | 10GB |
| `SuryaDoclingAgent` | [surya_docling_agent.py](../app/agents/ocr/surya_docling_agent.py) | Layout-Preservation | ❌ | 0GB |
| `HybridOCRAgent` | [hybrid_agent.py](../app/agents/ocr/hybrid_agent.py) | Multi-Engine Fusion | ✅ | 12GB |

**Verwendung**:

```python
from app.agents.ocr import DeepSeekAgent

agent = DeepSeekAgent()

result = await agent.execute(
    input_data={
        "document_id": "doc123",
        "image_path": "/path/to/document.pdf",
        "language": "de",
    },
    context={"task_id": "task456", "user_id": "user789"}
)

print(f"Text: {result['result']['text']}")
print(f"Confidence: {result['result']['confidence']}")
print(f"Duration: {result['metadata']['duration_seconds']}s")
```

#### 3. **Orchestration Agents** ([app/agents/orchestration/](../app/agents/orchestration/))

**Document Processing Orchestrator** ([document_orchestrator.py](../app/agents/orchestration/document_orchestrator.py))

```python
from app.agents.orchestration import DocumentProcessingOrchestrator

orchestrator = DocumentProcessingOrchestrator()

# Führt kompletten Workflow aus:
# 1. Classification → 2. Pre-Processing → 3. OCR
# → 4. Post-Processing → 5. QA → 6. Storage

result = await orchestrator.execute(
    input_data={
        "document_id": "doc123",
        "file_path": "/uploads/invoice.pdf",
        "priority": 1,  # 0=normal, 1=high, 2=critical
        "options": {
            "extract_entities": True,
            "detect_layout": True,
        }
    }
)

# Result enthält:
# - document_id
# - status (completed/failed)
# - phases_completed (liste aller Phasen)
# - result (text, entities, metadata)
# - workflow_metadata (duration, priority)
```

**OCR Backend Router** ([ocr_router.py](../app/agents/orchestration/ocr_router.py))

```python
from app.agents.orchestration import OCRBackendRouter

router = OCRBackendRouter(use_ml_routing=False)

backend_selection = await router.execute(
    input_data={
        "document_metadata": {
            "document_type": "invoice",
            "complexity": "high",
            "has_tables": True,
            "quality_score": 0.85,
        },
        "sla_requirements": {
            "max_processing_time_seconds": 30,
        }
    }
)

print(f"Selected: {backend_selection['result']['backend']}")
print(f"Reason: {backend_selection['result']['reason']}")
print(f"Alternatives: {backend_selection['result']['alternatives']}")
```

## 🚀 Integration mit Celery

### Existierende Celery-Konfiguration

Die Basis-Celery-Konfiguration existiert bereits in [app/workers/celery_app.py](../app/workers/celery_app.py).

### Erweiterte Queue-Struktur (empfohlen)

```python
# app/workers/celery_app.py - erweiterte Konfiguration

from kombu import Exchange, Queue

# Exchanges nach Agent-Kategorien
ocr_exchange = Exchange("ocr", type="topic")
preprocessing_exchange = Exchange("preprocessing", type="topic")
postprocessing_exchange = Exchange("postprocessing", type="topic")
orchestration_exchange = Exchange("orchestration", type="topic")

# Queues mit Prioritäten
TASK_QUEUES = (
    # OCR Queues (GPU-Worker)
    Queue(
        "ocr.deepseek",
        exchange=ocr_exchange,
        routing_key="ocr.deepseek",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "ocr.got_ocr",
        exchange=ocr_exchange,
        routing_key="ocr.got_ocr",
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "ocr.hybrid",
        exchange=ocr_exchange,
        routing_key="ocr.hybrid",
        queue_arguments={"x-max-priority": 10},
    ),

    # Pre-Processing Queues (CPU-Worker)
    Queue(
        "preprocessing.classification",
        exchange=preprocessing_exchange,
        routing_key="preprocessing.classification",
    ),

    # Orchestration Queue
    Queue(
        "orchestration.master",
        exchange=orchestration_exchange,
        routing_key="orchestration.master",
    ),
)
```

### Celery Tasks erstellen

```python
# app/workers/tasks/ocr_tasks.py

from app.workers.celery_app import celery_app
from app.agents.ocr import DeepSeekAgent, GOTOCRAgent
import asyncio


@celery_app.task(
    name="tasks.ocr.deepseek_process",
    bind=True,
    max_retries=3,
    time_limit=600,  # 10 minutes
)
def deepseek_ocr_task(self, document_id: str, image_path: str):
    """Celery task for DeepSeek OCR processing."""
    agent = DeepSeekAgent()

    try:
        # Run async agent in event loop
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            agent.execute(
                input_data={
                    "document_id": document_id,
                    "image_path": image_path,
                },
                context={"task_id": self.request.id},
            )
        )

        return result

    except Exception as e:
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="tasks.ocr.got_ocr_process")
def got_ocr_task(document_id: str, image_path: str):
    """Celery task for GOT-OCR processing."""
    agent = GOTOCRAgent()

    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(
        agent.execute(
            input_data={
                "document_id": document_id,
                "image_path": image_path,
            }
        )
    )

    return result
```

```python
# app/workers/tasks/orchestration_tasks.py

from app.workers.celery_app import celery_app
from app.agents.orchestration import DocumentProcessingOrchestrator
import asyncio


@celery_app.task(
    name="tasks.orchestration.process_document",
    bind=True,
    max_retries=3,
    time_limit=900,  # 15 minutes for full workflow
)
def process_document_task(self, document_id: str, file_path: str, priority: int = 0):
    """Orchestrate complete document processing workflow."""
    orchestrator = DocumentProcessingOrchestrator()

    try:
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            orchestrator.execute(
                input_data={
                    "document_id": document_id,
                    "file_path": file_path,
                    "priority": priority,
                },
                context={"task_id": self.request.id},
            )
        )

        return result

    except Exception as e:
        # Log error and retry
        raise self.retry(exc=e, countdown=120)
```

### Worker starten

```bash
# GPU Worker für OCR (DeepSeek, GOT-OCR, Hybrid)
celery -A app.workers.celery_app worker \
    --queues=ocr.deepseek,ocr.got_ocr,ocr.hybrid \
    --concurrency=1 \
    --pool=solo \
    --loglevel=info \
    --hostname=gpu-worker@%h

# CPU Worker für Pre/Post-Processing
celery -A app.workers.celery_app worker \
    --queues=preprocessing.classification,postprocessing.german \
    --concurrency=4 \
    --pool=prefork \
    --loglevel=info \
    --hostname=cpu-worker@%h

# Orchestrator Worker
celery -A app.workers.celery_app worker \
    --queues=orchestration.master \
    --concurrency=2 \
    --pool=prefork \
    --loglevel=info \
    --hostname=orchestrator-worker@%h
```

## 📊 Monitoring & Metriken

### Prometheus Metriken

Alle Agents emittieren automatisch Prometheus-Metriken:

```prometheus
# Anzahl verarbeiteter Tasks
agent_tasks_total{agent_name="deepseek_ocr_agent", category="ocr", status="success"} 150

# Task-Dauer (Histogram)
agent_task_duration_seconds{agent_name="deepseek_ocr_agent", category="ocr"}

# Aktive Tasks (Gauge)
agent_active_tasks{agent_name="deepseek_ocr_agent", category="ocr"} 2

# Fehler
agent_errors_total{agent_name="deepseek_ocr_agent", category="ocr", error_type="GPUOutOfMemoryError"} 3
```

### Grafana Dashboards

**Empfohlene Panels**:

1. **OCR Throughput**:
   ```promql
   rate(agent_tasks_total{category="ocr", status="success"}[5m])
   ```

2. **Average Processing Time**:
   ```promql
   histogram_quantile(0.95, agent_task_duration_seconds{category="ocr"})
   ```

3. **Error Rate**:
   ```promql
   rate(agent_errors_total[5m])
   ```

4. **GPU Utilization** (wenn GPU-Manager integriert):
   ```promql
   gpu_memory_usage_bytes / gpu_memory_total_bytes
   ```

## 🔧 Entwicklung & Testing

### Unit Tests für Agents

```python
# tests/unit/agents/test_deepseek_agent.py

import pytest
from app.agents.ocr import DeepSeekAgent


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deepseek_agent_process():
    """Test DeepSeek agent processing."""
    agent = DeepSeekAgent()

    result = await agent.execute(
        input_data={
            "document_id": "test123",
            "image_path": "/path/to/test.png",
        }
    )

    assert result["metadata"]["status"] == "success"
    assert "text" in result["result"]
    assert result["result"]["confidence"] > 0.0


@pytest.mark.asyncio
@pytest.mark.gpu
async def test_deepseek_agent_gpu_allocation():
    """Test GPU allocation (requires actual GPU)."""
    agent = DeepSeekAgent()

    # Should allocate GPU resources
    await agent._ensure_gpu_allocated()

    # GPU should be allocated
    assert agent.gpu_manager.check_availability()["available"]
```

### Integration Tests

```python
# tests/integration/test_orchestrator.py

import pytest
from app.agents.orchestration import DocumentProcessingOrchestrator


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_document_workflow(tmp_path):
    """Test complete document processing workflow."""
    # Create test document
    test_doc = tmp_path / "test.pdf"
    test_doc.write_bytes(b"PDF content")

    orchestrator = DocumentProcessingOrchestrator()

    result = await orchestrator.execute(
        input_data={
            "document_id": "integration_test_1",
            "file_path": str(test_doc),
            "priority": 0,
        }
    )

    # Verify workflow completed
    assert result["metadata"]["status"] == "success"
    assert "completed" in result["result"]["status"]
    assert len(result["result"]["phases_completed"]) > 0
```

## 📚 Nächste Schritte

### Sofort einsatzbereit:
- ✅ Base Agent Framework
- ✅ OCR Agents (DeepSeek, GOT-OCR, Surya, Hybrid)
- ✅ Document Processing Orchestrator
- ✅ OCR Backend Router

### Noch zu implementieren (TODO):

1. **Pre-Processing Agents**:
   ```python
   # app/agents/preprocessing/image_enhancement_agent.py
   # app/agents/preprocessing/document_classifier_agent.py
   # app/agents/preprocessing/segmentation_agent.py
   ```

2. **Post-Processing Agents**:
   ```python
   # app/agents/postprocessing/german_language_agent.py
   # app/agents/postprocessing/entity_extraction_agent.py
   # app/agents/postprocessing/qa_agent.py
   ```

3. **Intelligence Agents**:
   ```python
   # app/agents/intelligence/semantic_analyzer_agent.py
   # app/agents/intelligence/deduplication_agent.py
   # app/agents/intelligence/anomaly_detection_agent.py
   ```

4. **Monitoring Agents**:
   ```python
   # app/agents/monitoring/health_check_agent.py
   # app/agents/monitoring/performance_monitor_agent.py
   # app/agents/monitoring/cleanup_agent.py
   ```

5. **State Management** (Redis):
   ```python
   # app/agents/state/workflow_state_manager.py
   # Für persistente Workflow-States
   ```

## 🎯 Best Practices

### 1. Agent-Design

```python
class MyCustomAgent(BaseAgent):
    """
    GOOD: Klare Verantwortlichkeiten, gut dokumentiert.

    Best for:
    - Specific use case
    - Clear input/output

    Performance:
    - Average: Xms
    - GPU required: Yes/No
    """

    def __init__(self):
        super().__init__(
            name="my_custom_agent",
            category=AgentCategory.PROCESSING,
            max_retries=3,
        )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        # Validate input
        self.validate_input(input_data, ["required_key"])

        # Log start
        self.logger.info("processing_started", **input_data)

        try:
            # Do work
            result = await self._do_work(input_data)

            # Log success
            self.logger.info("processing_completed", result_size=len(result))

            return result

        except Exception as e:
            # Log error
            self.logger.error("processing_failed", error=str(e))
            raise
```

### 2. Error Handling

```python
from app.agents.base import AgentProcessingError, AgentResourceError

try:
    result = await agent.process(data)
except AgentResourceError:
    # Resource unavailable (GPU, memory) - might be transient
    # → Retry later
    pass
except AgentProcessingError:
    # Processing failed - might be input issue
    # → Log and notify
    pass
```

### 3. Monitoring

```python
# ALWAYS log structured data
self.logger.info(
    "event_name",
    document_id=doc_id,
    duration_ms=duration,
    result_size=len(result),
)

# NOT:
# logger.info(f"Processed {doc_id} in {duration}ms")
```

## 📖 Weitere Dokumentation

- [Agent Architecture](AGENT_ARCHITECTURE.md) - Vollständige Architektur-Beschreibung
- [API Documentation](../README.md) - FastAPI Endpoints
- [Deployment Guide](../DEPLOYMENT.md) - Production Deployment
- [Security Policy](../SECURITY.md) - Sicherheitsrichtlinien

---

**Version**: 1.0
**Erstellt**: 2024-11-25
**Status**: ✅ Production-Ready Design
**Nächstes Review**: Bei Implementierung weiterer Agents
