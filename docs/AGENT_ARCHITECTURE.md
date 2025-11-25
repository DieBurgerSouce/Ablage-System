# Multi-Agent Architecture - Ablage-System OCR

## Übersicht

Das Ablage-System verwendet eine **verteilte Multi-Agent-Architektur** für intelligente Dokumentenverarbeitung. Jeder Agent ist spezialisiert auf spezifische Aufgaben und kommuniziert über Celery-Message-Queues.

## Architektur-Prinzipien

### Design-Prinzipien
1. **Autonomie**: Jeder Agent arbeitet unabhängig mit klar definierten Verantwortlichkeiten
2. **Spezialisierung**: Agents fokussieren sich auf eine spezifische Domäne
3. **Kooperation**: Agents kommunizieren über Events und Message-Passing
4. **Skalierbarkeit**: Agents können horizontal skaliert werden
5. **Fehlertoleranz**: Graceful degradation bei Agent-Ausfällen
6. **Observability**: Alle Agents loggen strukturiert und emittieren Metriken

### Kommunikationsmuster
```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway Layer                         │
│                    (FastAPI - Synchron)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator Agents                           │
│   (Koordination, Routing, Workflow-Management)                   │
└─────┬──────────┬──────────┬──────────┬──────────────────────────┘
      │          │          │          │
      ▼          ▼          ▼          ▼
┌─────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
│ OCR     │ │ Pre-   │ │ Post-  │ │ Intel-   │
│ Workers │ │Process │ │Process │ │ligence   │
│ Agents  │ │ Agents │ │ Agents │ │ Agents   │
└─────────┘ └────────┘ └────────┘ └──────────┘
      │          │          │          │
      └──────────┴──────────┴──────────┘
                 │
                 ▼
      ┌──────────────────────┐
      │  Storage & Database  │
      │  (MinIO, PostgreSQL) │
      └──────────────────────┘
```

## Agent-Kategorien

### 1. Processing Agents (Kernverarbeitung)

#### 1.1 OCR Worker Agents
Spezialisierte Agents für verschiedene OCR-Backends.

**DeepSeek Agent** (`agents.ocr.deepseek_agent`)
- **Zweck**: Verarbeitung komplexer Layouts mit multimodalem Modell
- **GPU**: 12GB VRAM erforderlich
- **Spezialisierung**:
  - Tabellen und komplexe Layouts
  - Handschrift und Frakturschrift
  - Mehrsprachige Dokumente
- **Priorität**: Hoch (für kritische Dokumente)
- **Queue**: `ocr.deepseek`

**GOT-OCR Agent** (`agents.ocr.got_ocr_agent`)
- **Zweck**: Schnelle, transformer-basierte OCR
- **GPU**: 10GB VRAM erforderlich
- **Spezialisierung**:
  - Standard-Textdokumente
  - Hoher Durchsatz
  - Deutsche Umlaute
- **Priorität**: Mittel
- **Queue**: `ocr.got_ocr`

**Surya-Docling Agent** (`agents.ocr.surya_docling_agent`)
- **Zweck**: Layout-Analyse und Strukturerkennung
- **GPU**: Optional (kann CPU verwenden)
- **Spezialisierung**:
  - Dokumentstruktur-Erkennung
  - Layout-Preservation
  - PDF-Rekonstruktion
- **Priorität**: Niedrig (für Archivierung)
- **Queue**: `ocr.surya_docling`

**Hybrid OCR Agent** (`agents.ocr.hybrid_agent`)
- **Zweck**: Kombiniert mehrere OCR-Engines für maximale Genauigkeit
- **Strategie**:
  1. Parallel-Verarbeitung mit allen verfügbaren Engines
  2. Confidence-basierte Zusammenführung
  3. Voting-Mechanismus für unsichere Bereiche
- **Use Case**: Kritische Dokumente (Verträge, rechtliche Dokumente)
- **Queue**: `ocr.hybrid`

#### 1.2 Pre-Processing Agents

**Image Enhancement Agent** (`agents.preprocessing.image_enhancement`)
- **Aufgaben**:
  - Noise reduction (Gaussian, bilateral filtering)
  - Contrast enhancement (CLAHE)
  - Binarization (adaptive thresholding)
  - Deskew/rotation correction
  - Resolution upscaling (ESRGAN für niedrige DPI)
- **Output**: Optimiertes Bild für OCR
- **Queue**: `preprocessing.image`

**Document Classification Agent** (`agents.preprocessing.document_classifier`)
- **Aufgaben**:
  - Dokumenttyp-Erkennung (Rechnung, Vertrag, Brief, etc.)
  - Sprach-Erkennung (primär Deutsch, aber auch Englisch, etc.)
  - Layout-Komplexität-Bewertung
  - Qualitäts-Scoring (DPI, Schärfe, Kontrast)
- **ML Model**: Lightweight CNN oder Vision Transformer
- **Output**: Metadaten + beste OCR-Backend-Empfehlung
- **Queue**: `preprocessing.classification`

**Page Segmentation Agent** (`agents.preprocessing.segmentation`)
- **Aufgaben**:
  - Multi-Page PDF splitting
  - Region-of-Interest (ROI) detection
  - Table detection und extraction
  - Header/Footer removal
  - Margin cropping
- **Output**: Segmentierte Bereiche für gezielte OCR
- **Queue**: `preprocessing.segmentation`

#### 1.3 Post-Processing Agents

**German Language Agent** (`agents.postprocessing.german_language`)
- **Aufgaben**:
  - Umlaut-Korrektur (ue→ü, ae→ä, oe→ö, ss→ß)
  - Spell-checking mit deutschem Wörterbuch
  - Grammar-check (optional mit LanguageTool)
  - Named Entity Recognition (Firmen, Personen, Orte)
  - Business-Term-Extraktion (GmbH, USt-IdNr., etc.)
- **Libraries**: spaCy (de_core_news_lg), hunspell
- **Queue**: `postprocessing.german`

**Format Extraction Agent** (`agents.postprocessing.format_extraction`)
- **Aufgaben**:
  - Datum-Extraktion (DD.MM.YYYY, etc.)
  - Währung-Extraktion (EUR, €, mit deutscher Formatierung)
  - IBAN/BIC-Validation
  - Email/Phone extraction
  - VAT ID validation (USt-IdNr.)
  - Address parsing (deutsche Adressformate)
- **Output**: Strukturierte Metadaten (JSON)
- **Queue**: `postprocessing.extraction`

**Quality Assurance Agent** (`agents.postprocessing.qa`)
- **Aufgaben**:
  - Confidence-Scoring des OCR-Ergebnisses
  - Vollständigkeits-Check (alle Seiten verarbeitet?)
  - Anomalie-Erkennung (ungewöhnlich niedrige Confidence)
  - Human-in-the-Loop Triggering bei niedrigem Score
  - A/B testing verschiedener OCR-Engines
- **Metrics**: Confidence, completeness, consistency
- **Queue**: `postprocessing.qa`

**Document Reconstruction Agent** (`agents.postprocessing.reconstruction`)
- **Aufgaben**:
  - PDF/A-Generierung (archivierungsfähig)
  - Searchable PDF creation (Text-Layer)
  - Original Layout preservation
  - Metadata embedding (XMP, Dublin Core)
- **Output**: Durchsuchbares PDF
- **Queue**: `postprocessing.reconstruction`

### 2. Orchestration Agents (Koordination)

#### 2.1 Master Orchestrator Agent
**Document Processing Orchestrator** (`agents.orchestration.document_orchestrator`)

**Workflow-Koordination**:
```python
class DocumentProcessingWorkflow:
    """
    Koordiniert den gesamten Dokumenten-Verarbeitungs-Workflow.

    Workflow:
    1. Document Upload → 2. Classification → 3. Pre-Processing
    4. OCR Selection → 5. OCR Processing → 6. Post-Processing
    7. QA → 8. Storage → 9. Indexing
    """

    async def orchestrate(self, document_id: str):
        # Phase 1: Classification
        classification = await self.classify_document(document_id)

        # Phase 2: Pre-Processing (parallel)
        preprocessing_tasks = [
            self.enhance_image(document_id),
            self.segment_pages(document_id),
        ]
        await asyncio.gather(*preprocessing_tasks)

        # Phase 3: OCR Backend Selection
        backend = self.select_ocr_backend(classification)

        # Phase 4: OCR Processing
        ocr_result = await self.run_ocr(document_id, backend)

        # Phase 5: Post-Processing (parallel)
        postprocessing_tasks = [
            self.correct_german_text(ocr_result),
            self.extract_metadata(ocr_result),
            self.assess_quality(ocr_result),
        ]
        await asyncio.gather(*postprocessing_tasks)

        # Phase 6: Final QA
        qa_result = await self.final_qa_check(document_id)

        if qa_result.needs_review:
            await self.trigger_human_review(document_id)

        # Phase 7: Storage & Indexing
        await self.store_and_index(document_id)
```

**Verantwortlichkeiten**:
- Workflow state management (Saga pattern)
- Fehlerbehandlung und Retry-Logik
- Performance-Optimierung (parallele Tasks)
- Progress tracking und Status updates
- Event emission für Frontend

**Queue**: `orchestration.master`

#### 2.2 Smart Routing Agent
**OCR Backend Router** (`agents.orchestration.ocr_router`)

**Intelligente Backend-Auswahl**:
```python
class OCRBackendRouter:
    """
    Wählt den optimalen OCR-Backend basierend auf:
    - Dokumenttyp und -komplexität
    - Verfügbare GPU-Ressourcen
    - Aktuelle Workload
    - Historische Performance
    - SLA-Anforderungen
    """

    def select_backend(
        self,
        document_metadata: dict,
        sla_requirements: dict = None,
    ) -> str:
        # Regelbasierte Auswahl
        if document_metadata["has_tables"]:
            return "deepseek"  # Beste Table-Performance

        if document_metadata["has_handwriting"]:
            return "deepseek"  # Handschrift-Support

        if document_metadata["complexity"] == "low":
            return "got_ocr"  # Schnellste Verarbeitung

        # GPU-Verfügbarkeit prüfen
        gpu_status = self.gpu_manager.check_availability()
        if not gpu_status["available"]:
            return "surya"  # CPU-Fallback

        # Workload-basierte Auswahl
        queue_lengths = self.get_queue_lengths()
        if queue_lengths["deepseek"] > 100:
            return "got_ocr"  # Load balancing

        # ML-basierte Auswahl (optional)
        if self.use_ml_routing:
            return self.ml_model.predict_best_backend(document_metadata)

        return "deepseek"  # Default
```

**Features**:
- Regelbasiertes Routing
- ML-basiertes Routing (optional)
- Load balancing
- Failover-Logik
- A/B testing support

**Queue**: `orchestration.routing`

#### 2.3 Resource Management Agent
**GPU Resource Manager Agent** (`agents.orchestration.gpu_manager`)

**Aufgaben**:
- GPU-Speicher-Monitoring (VRAM usage)
- Dynamische Batch-Size-Anpassung
- OOM-Prevention (proaktives Memory clearing)
- Multi-Model GPU-Sharing
- GPU-Utilization-Optimierung

**Strategien**:
```python
class GPUResourceStrategy:
    """
    Intelligentes GPU-Resource-Management mit verschiedenen Strategien.
    """

    def allocate_resources(self, backend: str, batch_size: int):
        # Strategie 1: First-Fit
        # Erste GPU mit genug Speicher

        # Strategie 2: Best-Fit
        # GPU mit passendster Speichergröße

        # Strategie 3: Load-Balanced
        # GPU mit niedrigster Auslastung

        # Strategie 4: Model-Affinity
        # Bevorzuge GPU, die das Model bereits geladen hat
        pass
```

**Queue**: `orchestration.gpu`

#### 2.4 Priority Queue Manager
**Priority-based Task Scheduler** (`agents.orchestration.priority_scheduler`)

**Priority Levels**:
- **P0 - Critical**: Live-Anfragen, API-Requests (< 5s SLA)
- **P1 - High**: Premium-User, geschäftskritische Dokumente
- **P2 - Normal**: Standard batch processing
- **P3 - Low**: Archivierungs-Workflows, Re-OCR

**Features**:
- Dynamic priority adjustment
- SLA-aware scheduling
- Starvation prevention (low-priority tasks)
- Fair queueing

**Queue**: `orchestration.scheduler`

### 3. Intelligence Agents (KI-Funktionen)

#### 3.1 Document Understanding Agent
**Semantic Document Analyzer** (`agents.intelligence.semantic_analyzer`)

**Aufgaben**:
- Document summarization (TL;DR generation)
- Key information extraction (Hauptaussagen)
- Entity linking (Verknüpfung von Entitäten)
- Relationship extraction (z.B. Vertragsparteien)
- Intent classification (Zweck des Dokuments)

**ML Models**:
- German BERT für Semantic Understanding
- GPT-based summarization (optional, lokal mit DeepSeek)
- Custom NER models für deutsche Business-Dokumente

**Queue**: `intelligence.semantic`

#### 3.2 Duplicate Detection Agent
**Document Deduplication Agent** (`agents.intelligence.deduplication`)

**Aufgaben**:
- Perceptual hashing (pHash für Bilder)
- Text similarity (Levenshtein, cosine similarity)
- Fuzzy matching für Near-Duplicates
- Version detection (gleicher Inhalt, unterschiedliche Scans)

**Use Cases**:
- Verhindern von doppelten Uploads
- Archiv-Bereinigung
- Storage-Optimierung

**Queue**: `intelligence.dedup`

#### 3.3 Anomaly Detection Agent
**Document Anomaly Detector** (`agents.intelligence.anomaly_detection`)

**Aufgaben**:
- Ungewöhnliche Dokumenttypen erkennen
- Qualitäts-Anomalien (extrem niedrige Confidence)
- Security-Checks (potentielle Malware, Phishing-Dokumente)
- Data leakage detection (PII, vertrauliche Informationen)

**ML Approach**:
- Isolation Forest für Anomalie-Erkennung
- One-Class SVM
- Autoencoder für unüberwachtes Learning

**Queue**: `intelligence.anomaly`

#### 3.4 Learning Agent
**Continuous Learning Agent** (`agents.intelligence.learning`)

**Aufgaben**:
- Sammeln von Feedback (User corrections)
- Model retraining (periodisch)
- Hyperparameter-Optimierung
- Performance-Tracking und -Analyse
- A/B test evaluation

**Feedback Loop**:
```
User Correction → Feedback Collection → Dataset Update
→ Model Retraining → A/B Testing → Deployment
```

**Queue**: `intelligence.learning`

### 4. Monitoring & Operations Agents

#### 4.1 Health Check Agent
**System Health Monitor** (`agents.monitoring.health_check`)

**Checks**:
- Database connectivity (PostgreSQL)
- Cache availability (Redis)
- Storage access (MinIO)
- GPU health (NVIDIA SMI)
- Queue health (Celery workers alive?)
- External services (optional: SMTP, Webhooks)

**Interval**: Every 30 seconds
**Queue**: `monitoring.health`

#### 4.2 Performance Monitoring Agent
**Performance Metrics Collector** (`agents.monitoring.performance`)

**Metriken**:
- OCR throughput (documents/hour)
- Average processing time per backend
- GPU utilization (% usage)
- Queue lengths und wait times
- Error rates
- API response times

**Export**:
- Prometheus metrics
- Grafana dashboards
- Alerts bei Threshold-Überschreitungen

**Queue**: `monitoring.performance`

#### 4.3 Error Recovery Agent
**Automatic Error Recovery** (`agents.monitoring.error_recovery`)

**Strategien**:
- Automatic retry mit exponential backoff
- Fallback zu alternativen Backends
- Partial result recovery
- Human-in-the-loop escalation
- Dead letter queue management

**Error Types**:
- Transient errors → Retry
- GPU OOM → Reduce batch size, retry
- Model failure → Fallback backend
- Permanent errors → Human review

**Queue**: `monitoring.recovery`

#### 4.4 Cleanup Agent
**Resource Cleanup Agent** (`agents.monitoring.cleanup`)

**Aufgaben**:
- Temporary file deletion (>24h alt)
- GPU memory clearing
- Old log file rotation
- Cache eviction (LRU)
- Database vacuum (PostgreSQL)
- Orphaned task cleanup

**Schedule**: Täglich um 3:00 Uhr
**Queue**: `monitoring.cleanup`

#### 4.5 Backup Agent
**Automated Backup Agent** (`agents.monitoring.backup`)

**Backup Targets**:
- PostgreSQL database (pg_dump)
- MinIO objects (incremental)
- Configuration files
- Model weights

**Schedule**:
- Full backup: Wöchentlich (Sonntag 2:00)
- Incremental: Täglich (2:00)
- Retention: 30 Tage

**Encryption**: GPG-verschlüsselt
**Queue**: `monitoring.backup`

### 5. Integration Agents

#### 5.1 Webhook Notification Agent
**Event Notification Agent** (`agents.integration.webhooks`)

**Events**:
- Document uploaded
- OCR processing started
- OCR processing completed
- Error occurred
- Review required

**Protocols**:
- HTTP webhooks (POST requests)
- Email notifications (SMTP)
- Slack/Discord/Teams integration
- Custom callbacks

**Queue**: `integration.webhooks`

#### 5.2 Export Agent
**Document Export Agent** (`agents.integration.export`)

**Export Formate**:
- Searchable PDF (PDF/A)
- Plain text (UTF-8)
- Structured JSON (mit Metadaten)
- XML (custom schema)
- CSV (für Tabellenextraktion)

**Destinations**:
- MinIO/S3
- Local filesystem
- FTP/SFTP
- WebDAV
- Email attachment

**Queue**: `integration.export`

#### 5.3 API Integration Agent
**Third-Party API Integration** (`agents.integration.external_apis`)

**Integrationen**:
- Buchhaltungssysteme (DATEV, Lexoffice)
- DMS-Systeme (SharePoint, Alfresco)
- Cloud-Storage (optional: Nextcloud, ownCloud)
- ERP-Systeme (SAP, Microsoft Dynamics)

**Queue**: `integration.external`

## Agent Communication

### Message Passing
Agents kommunizieren über Celery Tasks und Events:

```python
# Event-basierte Kommunikation
@celery_app.task(name="agents.ocr.deepseek.process")
def deepseek_ocr_task(document_id: str):
    result = DeepSeekAgent().process(document_id)

    # Emit event für nächste Phase
    emit_event("ocr.completed", {
        "document_id": document_id,
        "backend": "deepseek",
        "result": result
    })

    return result

# Event Handler
@celery_app.task(name="agents.postprocessing.german.on_ocr_completed")
def on_ocr_completed(event_data: dict):
    document_id = event_data["document_id"]
    ocr_result = event_data["result"]

    # Post-Processing starten
    corrected_text = GermanLanguageAgent().process(ocr_result)

    emit_event("postprocessing.completed", {
        "document_id": document_id,
        "corrected_text": corrected_text
    })
```

### State Management
Workflow-State wird in Redis gespeichert:

```python
class WorkflowState:
    def __init__(self, document_id: str):
        self.document_id = document_id
        self.redis_key = f"workflow:{document_id}"

    def update(self, phase: str, status: str, data: dict = None):
        state = {
            "phase": phase,
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
            "data": data or {}
        }
        redis_client.hset(self.redis_key, phase, json.dumps(state))

    def get_current_phase(self) -> str:
        # Gibt aktuelle Workflow-Phase zurück
        pass
```

## Deployment & Scaling

### Horizontal Scaling
Jeder Agent-Typ kann unabhängig skaliert werden:

```bash
# OCR Agents (GPU-Worker)
celery -A app.celery worker \
    -Q ocr.deepseek,ocr.got_ocr \
    --concurrency=1 \
    --pool=solo \
    --hostname=ocr-gpu-worker@%h

# Pre-Processing Agents (CPU-Worker)
celery -A app.celery worker \
    -Q preprocessing.image,preprocessing.classification \
    --concurrency=4 \
    --pool=prefork \
    --hostname=preprocessing-worker@%h

# Post-Processing Agents (CPU-Worker)
celery -A app.celery worker \
    -Q postprocessing.german,postprocessing.extraction \
    --concurrency=4 \
    --pool=prefork \
    --hostname=postprocessing-worker@%h
```

### Resource Allocation
```yaml
# docker-compose.yml - Production
services:
  # GPU Workers (1-2 Instanzen)
  ocr-worker-gpu:
    deploy:
      replicas: 2
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  # CPU Workers (4-8 Instanzen)
  preprocessing-worker:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2'
          memory: 4G

  postprocessing-worker:
    deploy:
      replicas: 4
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

## Monitoring & Observability

### Metrics
Jeder Agent emittiert Prometheus-Metriken:

```python
from prometheus_client import Counter, Histogram, Gauge

# Agent-spezifische Metriken
ocr_documents_total = Counter(
    'agent_ocr_documents_total',
    'Total documents processed by OCR agent',
    ['backend', 'status']
)

ocr_processing_duration = Histogram(
    'agent_ocr_processing_duration_seconds',
    'OCR processing duration',
    ['backend']
)

gpu_memory_usage = Gauge(
    'agent_gpu_memory_usage_bytes',
    'Current GPU memory usage'
)
```

### Logging
Strukturiertes Logging für alle Agents:

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info(
    "agent_task_started",
    agent="deepseek_ocr",
    document_id=doc_id,
    task_id=task_id
)
```

### Tracing
Distributed Tracing mit OpenTelemetry:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("deepseek_ocr_processing") as span:
    span.set_attribute("document.id", document_id)
    span.set_attribute("ocr.backend", "deepseek")

    result = process_document(document_id)

    span.set_attribute("ocr.confidence", result["confidence"])
```

## Zusammenfassung

### Agent-Übersicht (30+ Specialized Agents)

| Kategorie           | Agents | Queues | GPU Required |
| ------------------- | ------ | ------ | ------------ |
| OCR Processing      | 4      | 4      | Ja (3/4)     |
| Pre-Processing      | 3      | 3      | Nein         |
| Post-Processing     | 4      | 4      | Nein         |
| Orchestration       | 4      | 4      | Nein         |
| Intelligence        | 4      | 4      | Optional     |
| Monitoring          | 5      | 5      | Nein         |
| Integration         | 3      | 3      | Nein         |
| **Total**           | **27** | **27** | **3-6**      |

### Performance-Ziele

| Metrik                      | Ziel         |
| --------------------------- | ------------ |
| OCR Throughput              | 500+ docs/h  |
| Average Processing Time     | < 5s/page    |
| GPU Utilization             | 70-85%       |
| Error Rate                  | < 1%         |
| API Response Time (p95)     | < 500ms      |
| Queue Wait Time (p95)       | < 10s        |
| System Uptime               | 99.9%        |

---

**Version**: 1.0
**Autor**: Ablage-System Architecture Team
**Datum**: 2024-11-25
**Status**: Production-Ready Design
