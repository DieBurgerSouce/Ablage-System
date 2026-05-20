# Ablage-System Architecture

> Enterprise-Grade Dokumentenverarbeitungsplattform mit intelligenter OCR-Backend-Auswahl

## Systemuebersicht

Das Ablage-System ist eine On-Premises Dokumentenverarbeitungsplattform mit GPU-beschleunigter OCR, ML-gestuetztem Routing und umfassender Qualitaetssicherung. Entwickelt fuer deutsche Dokumente mit 100% Umlaut-Genauigkeit.

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    Ablage-System OCR                        │
                    ├─────────────────────────────────────────────────────────────┤
                    │  Frontend (Nginx:80)     │  Grafana (:3000)  │  Prometheus  │
                    ├──────────────────────────┴───────────────────┴──────────────┤
                    │                    FastAPI Backend (:8000)                  │
                    ├─────────────────────────────────────────────────────────────┤
                    │  Celery Workers  │  Redis (:6380)  │  PostgreSQL (:5433)    │
                    ├─────────────────────────────────────────────────────────────┤
                    │  OCR Backends: DeepSeek │ GOT-OCR │ Surya │ Surya-GPU       │
                    ├─────────────────────────────────────────────────────────────┤
                    │                 GPU: NVIDIA RTX 4080 (16GB)                 │
                    └─────────────────────────────────────────────────────────────┘
```

---

## Kernkomponenten

### 1. Document Processing Orchestrator

**Pfad:** `app/agents/orchestration/document_orchestrator.py`

Der zentrale Koordinator fuer den gesamten Dokumentenverarbeitungs-Workflow.

#### Workflow-States

```
PENDING → PREPROCESSING → CLASSIFYING → OCR_PROCESSING → POSTPROCESSING → QA_CHECK → COMPLETED
                                                                                   ↓
                                                                                FAILED
```

| State | Beschreibung |
|-------|--------------|
| `PENDING` | Dokument eingereicht, wartet auf Verarbeitung |
| `PREPROCESSING` | Bildoptimierung, Deskewing, Rauschreduzierung |
| `CLASSIFYING` | Dokumenttyp-Erkennung (Rechnung, Vertrag, etc.) |
| `OCR_PROCESSING` | Text-Extraktion via ausgewaehltem Backend |
| `POSTPROCESSING` | Deutsche Korrektur, Entity-Extraktion |
| `QA_CHECK` | Qualitaetspruefung und Validierung |
| `COMPLETED` | Erfolgreich verarbeitet |
| `FAILED` | Fehler aufgetreten |

---

### 2. ML Router System

**Pfad:** `app/ml/`

Enterprise-Grade ML-basierte Backend-Auswahl mit XGBoost und umfassendem Monitoring.

#### Komponenten

| Komponente | Pfad | Funktion |
|------------|------|----------|
| OCRRouterModel | `ml_router_model.py` | XGBoost-Klassifikator (22 Features) |
| DriftDetector | `drift_detector.py` | Erkennt Verteilungsaenderungen |
| SHAPExplainer | `shap_explainer.py` | Erklaert Routing-Entscheidungen |
| ABTestManager | `ab_testing.py` | Kontrollierte Experimente |
| MLMetrics | `metrics.py` | Prometheus-Integration |

#### Feature-Vektor (22 Dimensionen)

```python
Features:
- Dokumenttyp (7 one-hot: invoice, contract, receipt, form, letter, report, other)
- Dateigroesse (normalisiert)
- Seitenanzahl
- Bildinhalt (boolean)
- Tabelleninhalt (boolean)
- Handschrift (boolean)
- Sprache (de/en)
- Komplexitaetsscore
- SLA-Anforderungen (max_time, min_confidence, priority)
- Ressourcenstatus (GPU verfuegbar, VRAM frei, CPU-Last)
```

#### Drift Detection Schwellwerte

| Schweregrad | Score | Aktion |
|-------------|-------|--------|
| none | < 0.1 | Keine Aktion |
| low | 0.1-0.3 | Monitoring verstaerken |
| medium | 0.3-0.5 | Retraining planen |
| high | 0.5-0.7 | Retraining ausfuehren |
| critical | > 0.7 | Sofort reagieren |

---

### 3. OCR Backends

**Pfad:** `app/agents/ocr/`

| Backend | GPU | VRAM | Staerken | Use Cases |
|---------|-----|------|----------|-----------|
| DeepSeek-Janus-Pro | Ja | 12GB | Beste Umlaut-Genauigkeit, komplexe Layouts, Fraktur | Rechnungen, Vertraege |
| GOT-OCR 2.0 | Nein* | 10GB | Tabellen, Formeln, schnell | Technische Dokumente |
| Surya + Docling | Nein | 0GB | CPU-Fallback, Layout-Analyse | Hohe Last, GPU-Ausfall |
| Surya GPU | Ja | 4GB | Schnelle GPU-Variante | Standard-Dokumente |

*GOT-OCR nutzt CPU fuer maximale Parallelitaet

#### Backend-Auswahl Logik

```python
# Automatische Auswahl basierend auf Dokumenteigenschaften
if document.has_tables and document.complexity > 0.7:
    return "deepseek"  # Komplexe Layouts
elif document.is_handwritten:
    return "deepseek"  # Handschrift-Erkennung
elif document.page_count > 10:
    return "got_ocr"   # Batch-Optimiert
elif gpu_available and vram_free > 4GB:
    return "surya_gpu" # Schnell
else:
    return "surya"     # CPU-Fallback
```

---

### 4. Preprocessing Pipeline

**Pfad:** `app/agents/preprocessing/`

| Agent | Funktion |
|-------|----------|
| Image Enhancement | Kontrastverbesserung, Rauschreduzierung |
| Deskewing | Schraeglagenkorrektur |
| Document Classification | Dokumenttyp-Erkennung |
| Language Detection | Sprache erkennen (DE/EN) |

---

### 5. Postprocessing Pipeline

**Pfad:** `app/agents/postprocessing/`

#### German Correction Agent

- Umlaut-Korrektur (ae→ae, oe→oe, ue→ue, ss→ss)
- Rechtschreibpruefung fuer deutsche Texte
- Fraktur-Normalisierung
- Unicode NFC-Normalisierung

#### Entity Extraction Agent

| Entity | Validierung |
|--------|-------------|
| IBAN | Pruefziffer-Validierung |
| USt-IdNr. | Format DE + 9 Ziffern |
| Datum | Deutsche Formate (DD.MM.YYYY) |
| Waehrung | EUR, CHF mit Dezimalstellen |
| Email | RFC 5322 konform |
| Telefon | Deutsche Formate |

#### QA Agent

```python
class QualityLevel(str, Enum):
    EXCELLENT = "excellent"    # Score >= 0.95
    GOOD = "good"              # Score >= 0.85
    ACCEPTABLE = "acceptable"  # Score >= 0.70
    POOR = "poor"              # Score >= 0.50
    UNACCEPTABLE = "unacceptable"  # Score < 0.50
```

---

### 6. Supporting Services

#### Notification Service

**Pfad:** `app/services/notification_service.py`

| Channel | Beschreibung |
|---------|--------------|
| EMAIL | SMTP mit HTML/Plain-Text Templates |
| WEBHOOK | HTTP-Callbacks mit HMAC-Signatur |
| IN_APP | Redis-basierte Echtzeit-Benachrichtigungen |

#### Rate Limiting

**Pfad:** `app/api/dependencies.py`

| Tier | OCR/Stunde | OCR/Tag | Batch/Stunde |
|------|------------|---------|--------------|
| Free | 10 | 50 | 5 |
| Premium | 100 | 1000 | 50 |
| Admin | 10.000 | - | - |

---

## Datenfluss

```
┌─────────────────┐
│ 1. Upload       │  POST /api/v1/documents/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. Preprocessing│  Image Enhancement, Classification
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. ML Router    │  Backend-Auswahl (XGBoost/Rules)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. OCR          │  DeepSeek / GOT-OCR / Surya
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 5. Postprocessing│ German Correction, Entity Extraction
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. QA Check     │  Quality Score, Validierung
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. Storage      │  PostgreSQL + MinIO + Redis Cache
└─────────────────┘
```

---

## Infrastructure

### Docker Services

| Service | Port | Beschreibung |
|---------|------|--------------|
| nginx | 80, 443 | Reverse Proxy, TLS Termination |
| backend | 8000 | FastAPI Application |
| worker | - | Celery GPU Worker |
| postgres | 5433 | PostgreSQL 16 + pgvector |
| redis | 6380 | Cache + Job Queue |
| minio | 9000, 9001 | Object Storage |
| prometheus | 9090 | Metrics Collection |
| grafana | 3000 | Dashboards |
| loki | 3100 | Log Aggregation |

### Network Segmentation

```
┌─────────────────────────────────────────────────────────┐
│                    frontend-network                      │
│  nginx ←→ backend                                       │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                    backend-network                       │
│  backend ←→ worker ←→ redis                             │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                      data-network                        │
│  backend ←→ postgres ←→ minio                           │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                   monitoring-network                     │
│  prometheus ←→ grafana ←→ loki                          │
└─────────────────────────────────────────────────────────┘
```

---

## GPU Resource Management

### VRAM Limits

```python
# RTX 4080: 16GB VRAM
MAX_VRAM_USAGE = 0.85  # 13.6GB
GPU_LOCK_TIMEOUT = 180  # Sekunden

# Batch Size basierend auf VRAM
def calculate_batch_size(available_vram_gb: float) -> int:
    vram_per_image = 0.5  # ~500MB pro Bild fuer DeepSeek
    return max(1, int(available_vram_gb / vram_per_image))
```

### Fallback Strategy

```
GPU verfuegbar? ──► Ja ──► VRAM < 85%? ──► Ja ──► GPU-Backend
       │                        │
       ▼                        ▼
    Surya CPU              Warten oder Surya CPU
```

---

## Security Architecture

### Authentication Flow

```
Client ──► Login ──► JWT Access Token (15min)
                 └──► Refresh Token (7d, httpOnly Cookie)

API Request ──► Bearer Token ──► Validate ──► Check Blacklist ──► Process
```

### Rate Limiting

```python
# Fail-Closed: Bei Redis-Ausfall werden Requests blockiert
RATE_LIMIT_FAIL_CLOSED = True

# Trusted Proxies fuer X-Forwarded-For
TRUSTED_PROXIES = ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12"]
```

### GDPR Compliance

| Artikel | Implementierung |
|---------|-----------------|
| Art. 17 | Soft-Delete mit 30-Tage Retention |
| Art. 20 | Data Export API |
| Art. 25 | Privacy by Design |
| Art. 30 | Processing Activity Records |

---

## Monitoring & Observability

### Key Metrics

| Metrik | Typ | Beschreibung |
|--------|-----|--------------|
| `ablage_ocr_requests_total` | Counter | OCR-Anfragen gesamt |
| `ablage_ocr_duration_seconds` | Histogram | Verarbeitungszeit |
| `ablage_gpu_memory_bytes` | Gauge | VRAM-Nutzung |
| `ml_routing_confidence` | Histogram | ML-Routing Konfidenz |
| `ml_drift_score` | Gauge | Data Drift Score |

### Alerting Rules

| Alert | Bedingung | Severity |
|-------|-----------|----------|
| GPUHighMemory | VRAM > 90% fuer 2min | critical |
| OCRHighLatency | p95 > 10s fuer 5min | warning |
| MLDriftCritical | Drift > 0.5 fuer 5min | critical |
| BackendDown | Health Check failed | critical |

---

## Deployment Architecture

### Blue-Green Deployment

```
Load Balancer
     │
     ├──► Blue (Current) ──► backend:8000
     │
     └──► Green (New) ──► backend-new:8000
```

### Canary Deployment

```
Nginx Upstream
     │
     ├──► 90% ──► backend:8000 (Stable)
     │
     └──► 10% ──► backend-canary:8000 (New)
```

---

## Verzeichnisstruktur

```
Ablage_System/
├── app/
│   ├── agents/                 # AI/ML Agents
│   │   ├── orchestration/      # Document Orchestrator, ML Router
│   │   ├── preprocessing/      # Image Enhancement, Classification
│   │   ├── ocr/                # OCR Backends
│   │   └── postprocessing/     # German Correction, Entity Extraction
│   ├── api/v1/                 # REST API Endpoints
│   ├── core/                   # Config, Security, Logging
│   ├── db/                     # SQLAlchemy Models, Repositories
│   ├── ml/                     # ML Router, Drift Detection, SHAP
│   ├── services/               # Business Logic Services
│   └── workers/                # Celery Tasks
├── frontend/                   # React + TypeScript UI
├── infrastructure/
│   ├── ansible/                # Configuration Management
│   ├── grafana/                # Dashboards
│   ├── nginx/                  # Reverse Proxy Config
│   ├── prometheus/             # Metrics + Alerts
│   └── terraform/              # Infrastructure as Code
├── tests/
│   ├── unit/                   # Unit Tests
│   ├── integration/            # Integration Tests
│   └── e2e/                    # End-to-End Tests
└── docker-compose.yml          # Container Orchestration
```

---

## Verwandte Dokumentation

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment-Anleitung
- [API_REFERENCE.md](./API_REFERENCE.md) - API-Dokumentation
- [QUICKSTART.md](./QUICKSTART.md) - Schnellstart-Anleitung
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Beitragen zum Projekt
- [.claude/Docs/ML_ROUTING.md](./.claude/Docs/ML_ROUTING.md) - ML Router Details

---

*Version: 2.0 | Letzte Aktualisierung: 2024-12*
*Feinpoliert und durchdacht - Enterprise-Grade Dokumentenverarbeitung*
