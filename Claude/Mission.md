Multi-Backend OCR System - Vollständige Mission
Kontext & Hintergrund
Du arbeitest für Ben, einen 23-jährigen Web Developer aus Solingen, der eine eigene digitale Agentur betreibt. Die Agentur verarbeitet deutsche Business-Dokumente (Rechnungen, Verträge von verschiedenen Lieferanten) und benötigt eine professionelle, selbst-gehostete OCR-Lösung die alle Varianten abdeckt.
Ben's Hardware Arsenal
Primary System (Gaming-PC für GPU-Backends)
Hardware: Lenovo Legion T7 34IRZ8
CPU: Intel Core i9-13900KF (24 Kerne, 32 Threads @ 3.0 GHz)
GPU: NVIDIA RTX 4080 (16GB VRAM)
RAM: 64GB DDR5 (63.7 GB verfügbar)
OS: Windows 11 Home (Build 26200)
Storage: Ausreichend für alle Modelle
BIOS: UEFI, Secure Boot enabled
Sekundär System (Firmenlokaler Server für CPU-Backend)

6.000€ Investment, 2 Jahre alt
VM-Infrastruktur verfügbar
Dedizierte VM kann für OCR angelegt werden
CPU-only (keine GPU)

Deployment-Strategie

100% On-Premises - KEINE Cloud-Dependencies
Dual-System-Ansatz: GPU-Backends auf Gaming-PC, CPU-Backend auf Server
Remote API-Zugriff von überall
Volle Datenkontrolle


Kernaufgabe
Entwickle ein Multi-Backend OCR-System mit intelligentem Routing und Live-Benchmarking-Capabilities.
Die 3 Backends
1. GPU Backend A: DeepSeek-Janus-Pro
Zweck: Komplexe Dokumente, verschiedene Lieferanten-Formate
Hardware: RTX 4080 (16GB VRAM)
Eigenschaften:

Vision-Language-Model (VLM)
Exzellent für unbekannte/wechselnde Layouts
Beste Genauigkeit, aber langsamer
VRAM-intensiv (~14-16GB)

2. GPU Backend B: GOT-OCR 2.0
Zweck: Simple Docs, bekannte Layouts, Speed-Optimiert
Hardware: RTX 4080 (16GB VRAM)
Eigenschaften:

Spezialisiertes OCR-Model
Schnellste GPU-Option
Gut für wiederkehrende Lieferanten
Moderate VRAM-Nutzung (~8-10GB)

3. CPU Backend: Surya + Docling
Zweck: Fallback, Server-Deployment, No-GPU-Requirement
Hardware: Firmenlokaler Server (CPU)
Eigenschaften:

Reine CPU-Inferenz
Surya: Multilingual OCR (109 Sprachen inkl. Deutsch)
Docling: PDF Document Understanding
Langsamer, aber zuverlässig ohne GPU


System-Architektur
High-Level-Übersicht
┌─────────────────────────────────────────────────────────────┐
│                     Client Applications                      │
│          (Web-UI, Mobile App, API-Consumers)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Gateway                            │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Intelligent Router (routing.py)             │    │
│  │  • Analysiert Dokument-Charakteristiken             │    │
│  │  • Wählt optimales Backend                          │    │
│  │  • Load-Balancing zwischen GPU-Backends             │    │
│  └────────────────────────────────────────────────────┘    │
└──────────────┬──────────────┬──────────────┬───────────────┘
               │              │              │
       ┌───────▼──────┐ ┌────▼────┐ ┌───────▼────────┐
       │ DeepSeek     │ │ GOT-OCR │ │  Surya+Docling │
       │ Janus-Pro    │ │   2.0   │ │   (CPU)        │
       │ (GPU)        │ │  (GPU)  │ │                │
       └──────────────┘ └─────────┘ └────────────────┘
          RTX 4080        RTX 4080      Server-VM
Routing-Logik (Intelligente Backend-Auswahl)
pythonRouting-Entscheidung basierend auf:

1. **Dokumenten-Komplexität**:
   - Komplexes Layout → DeepSeek-Janus-Pro
   - Einfaches Layout → GOT-OCR 2.0
   - CPU-Fallback → Surya+Docling

2. **Lieferanten-Erkennung**:
   - Bekannter Lieferant (Template) → GOT-OCR 2.0
   - Unbekannter Lieferant → DeepSeek-Janus-Pro

3. **Performance-Anforderungen**:
   - Batch-Processing → GOT-OCR 2.0 (schneller)
   - Einzeldokument mit Präzision → DeepSeek-Janus-Pro

4. **GPU-Verfügbarkeit**:
   - GPU available → GPU-Backend (A oder B)
   - GPU busy/unavailable → CPU-Backend (Surya)

5. **User-Präferenz** (optional):
   - Explizite Backend-Auswahl via API-Parameter

Kritische Anforderungen
Deutsche Sprache - HÖCHSTE PRIORITÄT
Umlaut-Verarbeitung

ä, ö, ü, ß MÜSSEN 100% korrekt erkannt werden
Bekannte Probleme:

❌ PaddleOCR: GitHub Issue #1646 - Umlaute werden komplett übersprungen ("Grüßen" → "Gren")
⚠️ Tesseract: Benötigt UTF-8 Config + -l deu + min. 300 DPI
✅ EasyOCR: Robuste Umlaut-Verarbeitung
✅ DeepSeek/GOT-OCR/Surya: Moderne VLMs handhaben Umlaute korrekt



Deutsche Geschäftsdokumente - Spezielle Felder

Steuernummer (Tax ID)
Mehrwertsteuer (VAT) / Umsatzsteuer
Rechnungsnummer
Datum (DD.MM.YYYY Format)
Beträge (Brutto/Netto)
Zahlungsbedingungen
Lieferantendaten
Bankverbindung (IBAN/BIC)

Performance-Anforderungen
GPU-Backends (RTX 4080)

DeepSeek-Janus-Pro: 3-8 Sekunden pro Seite
GOT-OCR 2.0: 0.5-2 Sekunden pro Seite
Batch-Processing: Parallel-Processing wo möglich
VRAM Management: Lazy-Loading + Unloading bei Bedarf

CPU-Backend (Server)

Surya + Docling: 5-15 Sekunden pro Seite
Async Processing: Nicht-blockierend
Queue-System: Für größere Batches

System-Anforderungen

Concurrent Users: Min. 5-10 gleichzeitig
Uptime: 99% (On-Premises)
API Response Time: <500ms für Status-Checks

Dokumenttypen
Rechnungen (Primär-Use-Case)

Deutsche Lieferantenrechnungen
Verschiedene Layouts/Templates
PDF und Bild-Formate
1-5 Seiten typisch

Verträge

GmbH-Verträge
Handelsregisterauszüge
Längere Dokumente (10-50 Seiten)
Layout-Preservation kritisch

Weitere Business-Dokumente

Angebote
Lieferscheine
Bestellungen
Mahnungen


Technischer Stack
Backend-Spezifikationen
GPU Backend A: DeepSeek-Janus-Pro
Model Details:

Model: deepseek-ai/Janus-Pro-7B
Size: ~14GB VRAM
Inference: PyTorch + CUDA
Quantization: Optional FP16/INT8 für VRAM-Reduktion

Dependencies:
torch>=2.0.0
transformers>=4.35.0
accelerate
Pillow
Features:

Vision-Language Understanding
Multi-Page PDF Support
Table Extraction
Layout Analysis

GPU Backend B: GOT-OCR 2.0
Model Details:

Model: ucaslcl/GOT-OCR2_0
Size: ~8-10GB VRAM
Inference: PyTorch + CUDA
Optimized for Speed

Dependencies:
torch>=2.0.0
transformers
verovio  # For formatting
Features:

Fast Inference
Multiple OCR Modes (ocr/format)
Fine/Multi-Crop Support
Color OCR

CPU Backend: Surya + Docling
Model Details:

Surya: Multilingual OCR (vikp/surya_rec2)
Docling: PDF Understanding
Pure CPU Inference

Dependencies:
surya-ocr
docling
torch (CPU)
Features:

No GPU Required
109 Language Support (inkl. Deutsch)
PDF Layout Preservation
Table Structure Recognition

Framework & Infrastructure
API Layer

Framework: FastAPI 0.104+
Async: Full async/await support
Documentation: Auto-generated (Swagger/ReDoc)
Validation: Pydantic v2
CORS: Configurierbar für Remote Access

Queue & Processing

Queue: Celery + Redis (optional für große Batches)
File Storage: Local filesystem mit temp cleanup
Result Caching: Redis (optional)
Job Tracking: SQLite/PostgreSQL

Monitoring & Logging

Metrics: Prometheus-compatible endpoints
Logging: Structured JSON logs
Health Checks: Per-Backend status
Performance Tracking: Processing times, VRAM usage

Deployment

Container: Docker + Docker Compose
Reverse Proxy: Nginx (optional)
SSL: Let's Encrypt (für Remote Access)
Networking: Port-Forwarding für Remote API


System-Architektur (Detailliert)
Verzeichnisstruktur
/ocr-multi-backend/
├── README.md
├── docker-compose.yml
├── .env.example
├── requirements.txt
│
├── app/
│   ├── main.py                    # FastAPI App Entry
│   ├── __init__.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── ocr.py         # Main OCR endpoints
│   │   │   │   ├── batch.py       # Batch processing
│   │   │   │   ├── health.py      # Health checks
│   │   │   │   └── benchmark.py   # Benchmark endpoints
│   │   │   └── router.py          # API Router
│   │   └── dependencies.py        # Shared dependencies
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # Configuration
│   │   ├── logging.py             # Logging setup
│   │   └── security.py            # API Keys, Auth
│   │
│   ├── backend/
│   │   ├── __init__.py
│   │   ├── base.py                # Base Backend Interface
│   │   │
│   │   ├── gpu/
│   │   │   ├── __init__.py
│   │   │   ├── deepseek_backend.py    # DeepSeek-Janus-Pro
│   │   │   └── got_ocr_backend.py     # GOT-OCR 2.0
│   │   │
│   │   └── cpu/
│   │       ├── __init__.py
│   │       └── surya_docling_backend.py  # Surya + Docling
│   │
│   ├── routing/
│   │   ├── __init__.py
│   │   ├── router.py              # Intelligent Backend Router
│   │   ├── analyzer.py            # Document Analyzer
│   │   └── rules.py               # Routing Rules
│   │
│   ├── preprocessing/
│   │   ├── __init__.py
│   │   ├── pdf_processor.py       # PDF → Images
│   │   ├── image_enhancer.py      # Preprocessing
│   │   └── layout_analyzer.py     # Layout Detection
│   │
│   ├── postprocessing/
│   │   ├── __init__.py
│   │   ├── text_cleaner.py        # Text Cleanup
│   │   ├── spell_checker.py       # German Spell Check
│   │   └── field_extractor.py     # Invoice Field Extraction
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Pydantic Models
│   │   ├── results.py             # Result Models
│   │   └── config_models.py       # Config Models
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── benchmark.py           # Benchmarking Service
│   │   ├── cache.py               # Caching Service
│   │   └── metrics.py             # Metrics Collection
│   │
│   └── utils/
│       ├── __init__.py
│       ├── file_handler.py        # File Operations
│       ├── validators.py          # Input Validation
│       └── helpers.py             # Helper Functions
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api/
│   │   ├── test_ocr_endpoints.py
│   │   └── test_batch_endpoints.py
│   ├── test_backends/
│   │   ├── test_deepseek.py
│   │   ├── test_got_ocr.py
│   │   └── test_surya.py
│   ├── test_routing/
│   │   └── test_intelligent_router.py
│   └── test_data/
│       ├── sample_invoices/       # German Test Invoices
│       └── sample_contracts/      # German Test Contracts
│
├── docker/
│   ├── Dockerfile.gpu             # GPU-Backend Container
│   ├── Dockerfile.cpu             # CPU-Backend Container
│   └── docker-compose.yml
│
├── scripts/
│   ├── setup.sh                   # Setup Script
│   ├── download_models.py         # Model Downloader
│   └── benchmark.py               # Benchmark Runner
│
├── docs/
│   ├── API.md                     # API Documentation
│   ├── DEPLOYMENT.md              # Deployment Guide
│   ├── BENCHMARKS.md              # Benchmark Results
│   └── ARCHITECTURE.md            # Architecture Details
│
└── config/
    ├── routing_rules.yaml         # Routing Configuration
    ├── backend_config.yaml        # Backend Settings
    └── logging_config.yaml        # Logging Configuration

API-Spezifikation
Core Endpoints
POST /api/v1/ocr/process
Single Document Processing
pythonRequest:
{
  "file": <binary>,                    # PDF or Image file
  "backend": "auto|deepseek|gotocr|surya",  # Optional
  "options": {
    "language": "de",                  # Default: de
    "extract_fields": true,            # Extract invoice fields
    "preprocessing": true,             # Image enhancement
    "confidence_threshold": 0.90       # Min confidence
  }
}

Response:
{
  "document_id": "uuid-here",
  "backend_used": "deepseek",
  "processing_time": 3.2,
  "text": {
    "raw": "Full extracted text...",
    "structured": {
      "steuernummer": "DE123456789",
      "rechnungsnummer": "RE-2025-001",
      "datum": "2025-11-15",
      "betrag_netto": 1000.00,
      "mwst": 190.00,
      "betrag_brutto": 1190.00
    }
  },
  "confidence": 0.96,
  "metadata": {
    "pages": 1,
    "language": "de",
    "layout_complexity": "medium"
  }
}
POST /api/v1/ocr/batch
Batch Processing
pythonRequest:
{
  "files": [<binary>, <binary>, ...],
  "backend": "auto",
  "options": { ... }
}

Response:
{
  "job_id": "batch-uuid",
  "total_documents": 10,
  "status": "processing",
  "estimated_completion": "2025-11-15T10:35:00Z"
}
GET /api/v1/ocr/job/{job_id}
Job Status & Results
pythonResponse:
{
  "job_id": "batch-uuid",
  "status": "completed|processing|failed",
  "progress": {
    "total": 10,
    "processed": 10,
    "failed": 0
  },
  "results": [
    { "document_id": "...", ... },
    ...
  ]
}
POST /api/v1/benchmark/run
Live Benchmark
pythonRequest:
{
  "test_documents": ["doc1.pdf", "doc2.pdf"],
  "backends": ["deepseek", "gotocr", "surya"]
}

Response:
{
  "benchmark_id": "uuid",
  "results": {
    "deepseek": {
      "avg_time": 3.5,
      "accuracy": 0.97,
      "vram_usage": 14.2
    },
    "gotocr": {
      "avg_time": 1.2,
      "accuracy": 0.95,
      "vram_usage": 8.5
    },
    "surya": {
      "avg_time": 8.5,
      "accuracy": 0.93,
      "ram_usage": 4.2
    }
  }
}
GET /api/v1/health
System Health
pythonResponse:
{
  "status": "healthy",
  "backends": {
    "deepseek": {
      "status": "loaded",
      "vram_used": "14.2 GB",
      "response_time": "3.2s"
    },
    "gotocr": {
      "status": "loaded",
      "vram_used": "8.5 GB",
      "response_time": "1.2s"
    },
    "surya": {
      "status": "ready",
      "ram_used": "4.2 GB",
      "response_time": "8.5s"
    }
  },
  "system": {
    "gpu_available": true,
    "gpu_name": "NVIDIA RTX 4080",
    "cpu_cores": 32
  }
}

Implementierungs-Phasen
Phase 1: Foundation (Woche 1)
Ziele:

✅ Projekt-Setup & Struktur
✅ FastAPI Basis-Application
✅ Base Backend Interface
✅ Ein Backend lauffähig (Start mit GOT-OCR 2.0)
✅ Basic Health Check

Deliverables:

app/main.py mit FastAPI
app/backend/base.py Interface
app/backend/gpu/got_ocr_backend.py funktional
/api/v1/ocr/process Endpoint funktioniert
Docker-Setup (optional, kann später)

Success Criteria:

Single-Document OCR mit GOT-OCR 2.0 funktioniert
API ist lokal erreichbar
Deutsche Umlaute werden korrekt erkannt
Response < 2 Sekunden


Phase 2: Multi-Backend (Woche 2)
Ziele:

✅ DeepSeek-Janus-Pro Integration
✅ Surya + Docling Integration
✅ Backend-Switching via API
✅ VRAM Management (Lazy Loading)

Deliverables:

app/backend/gpu/deepseek_backend.py
app/backend/cpu/surya_docling_backend.py
Backend-Auswahl via backend Parameter
Lazy Model Loading/Unloading

Success Criteria:

Alle 3 Backends funktionieren
Manuelle Backend-Auswahl möglich
VRAM bleibt unter 16GB
CPU-Backend funktioniert ohne GPU


Phase 3: Intelligent Routing (Woche 3)
Ziele:

✅ Document Analyzer implementieren
✅ Routing Logic mit Rules
✅ Auto-Backend-Selection
✅ Performance-basiertes Routing

Deliverables:

app/routing/router.py
app/routing/analyzer.py
app/routing/rules.py
Routing basierend auf Layout-Komplexität

Success Criteria:

Automatisches Backend-Routing funktioniert
Komplexe Docs → DeepSeek
Simple Docs → GOT-OCR
GPU unavailable → Surya


Phase 4: Production Features (Woche 4)
Ziele:

✅ Batch Processing
✅ Invoice Field Extraction
✅ Preprocessing Pipeline
✅ Postprocessing (Spell Check)

Deliverables:

app/api/v1/endpoints/batch.py
app/postprocessing/field_extractor.py
app/preprocessing/image_enhancer.py
Celery Queue System (optional)

Success Criteria:

Batch-Upload funktioniert
Deutsche Rechnungsfelder werden extrahiert
Preprocessing verbessert Genauigkeit
Spell-Checking korrigiert Fehler


Phase 5: Benchmarking & Optimization (Woche 5)
Ziele:

✅ Live Benchmark System
✅ Performance Metrics
✅ Accuracy Comparison
✅ Cost/Time Analysis

Deliverables:

app/services/benchmark.py
app/api/v1/endpoints/benchmark.py
Benchmark Reports (Markdown/JSON)
Performance Dashboard (optional Web-UI)

Success Criteria:

Live Benchmark mit echten Docs möglich
Vergleich aller 3 Backends
Metriken: Zeit, Genauigkeit, Ressourcen
Report-Generierung


Phase 6: Deployment & Documentation (Woche 6)
Ziele:

✅ Docker Containerization
✅ Remote Access Setup
✅ API Documentation
✅ Deployment Guide

Deliverables:

docker/Dockerfile.gpu & docker/Dockerfile.cpu
docker-compose.yml
docs/DEPLOYMENT.md
docs/API.md
SSL Setup für Remote Access

Success Criteria:

Docker Containers laufen
Remote API-Zugriff funktioniert
Dokumentation vollständig
System production-ready


Technische Implementierung
Base Backend Interface
python# app/backend/base.py

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from ..models.results import ProcessingResult

class OCRBackend(ABC):
    """Base interface for all OCR backends"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_loaded = False
    
    @abstractmethod
    async def load_model(self):
        """Load the OCR model into memory"""
        pass
    
    @abstractmethod
    async def unload_model(self):
        """Unload model to free resources"""
        pass
    
    @abstractmethod
    async def process_document(
        self,
        image_path: str,
        options: Dict[str, Any] = None
    ) -> ProcessingResult:
        """Process a single document"""
        pass
    
    @abstractmethod
    async def process_batch(
        self,
        image_paths: List[str],
        options: Dict[str, Any] = None
    ) -> List[ProcessingResult]:
        """Process multiple documents"""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if backend is healthy"""
        pass
    
    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Get backend performance metrics"""
        pass
Processing Result Model
python# app/models/results.py

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime

class ProcessingResult(BaseModel):
    """Result from OCR processing"""
    
    document_id: str = Field(description="Unique document ID")
    text: str = Field(description="Extracted raw text")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall confidence")
    
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Extracted structured fields (for invoices)"
    )
    
    layout: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Layout information (blocks, regions)"
    )
    
    tables: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Extracted tables"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Processing metadata"
    )
    
    backend_used: str = Field(description="Which backend processed this")
    processing_time: float = Field(description="Processing time in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "doc-12345",
                "text": "Rechnung RE-2025-001...",
                "confidence": 0.96,
                "structured_data": {
                    "rechnungsnummer": "RE-2025-001",
                    "datum": "2025-11-15",
                    "betrag_brutto": 1190.00
                },
                "backend_used": "deepseek",
                "processing_time": 3.2
            }
        }
Intelligent Router
python# app/routing/router.py

from typing import Dict, Any, Optional
from ..backend.base import OCRBackend
from ..backend.gpu.deepseek_backend import DeepSeekBackend
from ..backend.gpu.got_ocr_backend import GOTOCRBackend
from ..backend/cpu.surya_docling_backend import SuryaDoclingBackend
from .analyzer import DocumentAnalyzer
from .rules import RoutingRules

class IntelligentRouter:
    """Routes documents to optimal backend"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.analyzer = DocumentAnalyzer()
        self.rules = RoutingRules(config)
        
        # Initialize backends
        self.backends = {
            'deepseek': DeepSeekBackend(config['deepseek']),
            'gotocr': GOTOCRBackend(config['gotocr']),
            'surya': SuryaDoclingBackend(config['surya'])
        }
    
    async def route_document(
        self,
        document_path: str,
        user_preference: Optional[str] = None
    ) -> OCRBackend:
        """Select optimal backend for document"""
        
        # User explicit choice
        if user_preference and user_preference in self.backends:
            return self.backends[user_preference]
        
        # Analyze document
        characteristics = await self.analyzer.analyze(document_path)
        
        # Apply routing rules
        backend_name = self.rules.select_backend(characteristics)
        
        return self.backends[backend_name]
    
    async def get_available_backends(self) -> List[str]:
        """Get list of currently available backends"""
        available = []
        for name, backend in self.backends.items():
            if backend.health_check():
                available.append(name)
        return available
Document Analyzer
python# app/routing/analyzer.py

from typing import Dict, Any
from PIL import Image
import numpy as np

class DocumentAnalyzer:
    """Analyzes document characteristics for routing"""
    
    async def analyze(self, document_path: str) -> Dict[str, Any]:
        """Analyze document and return characteristics"""
        
        img = Image.open(document_path)
        
        return {
            'complexity': self._assess_complexity(img),
            'page_count': self._get_page_count(document_path),
            'has_tables': self._detect_tables(img),
            'layout_type': self._classify_layout(img),
            'text_density': self._calculate_text_density(img),
            'language': 'de',  # Could use language detection
        }
    
    def _assess_complexity(self, img: Image) -> str:
        """Assess layout complexity: simple, medium, complex"""
        # Implement complexity detection
        # Based on: number of regions, table presence, etc.
        return "medium"
    
    def _get_page_count(self, path: str) -> int:
        """Get number of pages in document"""
        # For PDFs, extract page count
        return 1
    
    def _detect_tables(self, img: Image) -> bool:
        """Detect if document contains tables"""
        # Simple table detection
        return False
    
    def _classify_layout(self, img: Image) -> str:
        """Classify document layout type"""
        # invoice, contract, letter, etc.
        return "invoice"
    
    def _calculate_text_density(self, img: Image) -> float:
        """Calculate text vs whitespace ratio"""
        return 0.6
Routing Rules
python# app/routing/rules.py

from typing import Dict, Any

class RoutingRules:
    """Routing decision rules"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def select_backend(self, characteristics: Dict[str, Any]) -> str:
        """Select backend based on document characteristics"""
        
        complexity = characteristics['complexity']
        layout_type = characteristics['layout_type']
        has_tables = characteristics['has_tables']
        
        # Rule 1: Complex documents → DeepSeek
        if complexity == 'complex':
            return 'deepseek'
        
        # Rule 2: Documents with tables → DeepSeek
        if has_tables:
            return 'deepseek'
        
        # Rule 3: Known invoice layouts → GOT-OCR (faster)
        if layout_type == 'invoice' and complexity == 'simple':
            return 'gotocr'
        
        # Rule 4: Simple documents → GOT-OCR
        if complexity == 'simple':
            return 'gotocr'
        
        # Default: GOT-OCR (good balance)
        return 'gotocr'
    
    def get_fallback_order(self) -> List[str]:
        """Get fallback order if primary fails"""
        return ['gotocr', 'deepseek', 'surya']

Qualitätsmetriken & Success Criteria
Genauigkeits-Ziele
Character Accuracy

Ziel: ≥95% Character-Level Accuracy
Methode: Edit Distance zu Ground Truth
Deutsche Umlaute: 100% korrekt (Zero Tolerance)

Field Extraction (Rechnungen)

Rechnungsnummer: ≥98% Genauigkeit
Datum: ≥99% Genauigkeit
Beträge: ≥99% Genauigkeit (finanzkritisch!)
Steuernummer: ≥98% Genauigkeit
IBAN/BIC: ≥99% Genauigkeit

Layout Preservation

Struktur erkennbar: Block-Order korrekt
Tabellen: Zeilen/Spalten-Struktur erhalten
Headers/Footers: Identifiziert

Performance-Ziele
GPU Backend A (DeepSeek-Janus-Pro)

Single Page: 3-8 Sekunden
VRAM Usage: <15 GB
Batch (5 Docs): <25 Sekunden
Accuracy: ≥97%

GPU Backend B (GOT-OCR 2.0)

Single Page: 0.5-2 Sekunden
VRAM Usage: <10 GB
Batch (5 Docs): <8 Sekunden
Accuracy: ≥95%

CPU Backend (Surya + Docling)

Single Page: 5-15 Sekunden
RAM Usage: <6 GB
Batch (5 Docs): <60 Sekunden
Accuracy: ≥93%

System-Ziele

API Response: <500ms (excluding OCR processing)
Concurrent Requests: 5-10 gleichzeitig
Uptime: 99% (On-Premises)
Error Rate: <1%


Testing Strategy
Unit Tests
Backend Tests
python# tests/test_backends/test_deepseek.py

import pytest
from app.backend.gpu.deepseek_backend import DeepSeekBackend

@pytest.mark.asyncio
async def test_deepseek_load():
    backend = DeepSeekBackend(config={})
    await backend.load_model()
    assert backend.is_loaded

@pytest.mark.asyncio
async def test_deepseek_process_simple():
    backend = DeepSeekBackend(config={})
    result = await backend.process_document("test_invoice.pdf")
    assert result.confidence > 0.90
    assert "Rechnung" in result.text

@pytest.mark.asyncio
async def test_german_umlauts():
    backend = DeepSeekBackend(config={})
    result = await backend.process_document("test_umlauts.pdf")
    assert "ä" in result.text
    assert "ö" in result.text
    assert "ü" in result.text
    assert "ß" in result.text
Routing Tests
python# tests/test_routing/test_intelligent_router.py

import pytest
from app.routing.router import IntelligentRouter

@pytest.mark.asyncio
async def test_complex_doc_routes_to_deepseek():
    router = IntelligentRouter(config={})
    backend = await router.route_document("complex_doc.pdf")
    assert backend.__class__.__name__ == "DeepSeekBackend"

@pytest.mark.asyncio
async def test_simple_invoice_routes_to_gotocr():
    router = IntelligentRouter(config={})
    backend = await router.route_document("simple_invoice.pdf")
    assert backend.__class__.__name__ == "GOTOCRBackend"
Integration Tests
python# tests/test_api/test_ocr_endpoints.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_process_endpoint():
    with open("test_invoice.pdf", "rb") as f:
        response = client.post(
            "/api/v1/ocr/process",
            files={"file": f},
            data={"backend": "auto"}
        )
    assert response.status_code == 200
    assert "document_id" in response.json()
    assert "text" in response.json()

def test_batch_endpoint():
    files = [
        ("files", open("invoice1.pdf", "rb")),
        ("files", open("invoice2.pdf", "rb")),
    ]
    response = client.post("/api/v1/ocr/batch", files=files)
    assert response.status_code == 200
    assert "job_id" in response.json()
Accuracy Tests
python# tests/test_accuracy.py

import pytest
from app.backend.gpu.deepseek_backend import DeepSeekBackend
from tests.utils import calculate_accuracy

@pytest.mark.asyncio
async def test_invoice_field_extraction_accuracy():
    """Test on 50 real German invoices with ground truth"""
    backend = DeepSeekBackend(config={})
    
    test_cases = load_test_invoices_with_ground_truth()
    results = []
    
    for test_case in test_cases:
        result = await backend.process_document(test_case['path'])
        accuracy = calculate_accuracy(
            predicted=result.structured_data,
            ground_truth=test_case['ground_truth']
        )
        results.append(accuracy)
    
    avg_accuracy = sum(results) / len(results)
    assert avg_accuracy >= 0.95  # 95% accuracy required

Deployment
Docker Setup
GPU Backend Dockerfile
dockerfile# docker/Dockerfile.gpu

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Install Python
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements-gpu.txt .
RUN pip3 install -r requirements-gpu.txt

# Copy application
COPY app/ /app/
WORKDIR /app

# Download models
RUN python3 -c "from transformers import AutoModel; \
    AutoModel.from_pretrained('deepseek-ai/Janus-Pro-7B'); \
    AutoModel.from_pretrained('ucaslcl/GOT-OCR2_0')"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
CPU Backend Dockerfile
dockerfile# docker/Dockerfile.cpu

FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-cpu.txt .
RUN pip3 install -r requirements-cpu.txt

COPY app/ /app/
WORKDIR /app

RUN python3 -c "from surya.model.recognition.model import load_model; \
    load_model()"

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
Docker Compose
yaml# docker-compose.yml

version: '3.8'

services:
  ocr-gpu:
    build:
      context: .
      dockerfile: docker/Dockerfile.gpu
    ports:
      - "8000:8000"
    environment:
      - CUDA_VISIBLE_DEVICES=0
      - CONFIG_PATH=/config/backend_config.yaml
    volumes:
      - ./config:/config
      - ./uploads:/uploads
      - ./outputs:/outputs
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped

  ocr-cpu:
    build:
      context: .
      dockerfile: docker/Dockerfile.cpu
    ports:
      - "8001:8001"
    environment:
      - CONFIG_PATH=/config/backend_config.yaml
    volumes:
      - ./config:/config
      - ./uploads:/uploads
      - ./outputs:/outputs
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  # Optional: Celery Worker for batches
  celery-worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.gpu
    command: celery -A app.workers.celery_app worker --loglevel=info
    depends_on:
      - redis
      - ocr-gpu
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
Remote Access Setup
Nginx Reverse Proxy
nginx# /etc/nginx/sites-available/ocr-api

server {
    listen 80;
    server_name ocr.your-domain.com;

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name ocr.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/ocr.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ocr.your-domain.com/privkey.pem;

    client_max_body_size 50M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long OCR processing
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
Firewall (Windows)
powershell# Allow inbound on port 8000 (or 443 if using nginx)
New-NetFirewallRule -DisplayName "OCR API" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
Port Forwarding (Router)
External Port: 443 (HTTPS)
Internal IP: 192.168.x.x (Ben's PC)
Internal Port: 8000 (or 443 if nginx)
Protocol: TCP

Monitoring & Operations
Health Checks
python# app/api/v1/endpoints/health.py

from fastapi import APIRouter, Depends
from typing import Dict, Any

router = APIRouter()

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """System health check"""
    
    backends = {
        'deepseek': await check_backend_health('deepseek'),
        'gotocr': await check_backend_health('gotocr'),
        'surya': await check_backend_health('surya')
    }
    
    gpu_info = get_gpu_info() if torch.cuda.is_available() else None
    
    return {
        'status': 'healthy' if all(b['healthy'] for b in backends.values()) else 'degraded',
        'backends': backends,
        'system': {
            'gpu_available': torch.cuda.is_available(),
            'gpu_info': gpu_info,
            'cpu_cores': os.cpu_count(),
            'ram_available_gb': psutil.virtual_memory().available / 1024**3
        }
    }
Metrics Endpoints
python# app/api/v1/endpoints/metrics.py

from fastapi import APIRouter
from prometheus_client import Counter, Histogram, generate_latest

router = APIRouter()

# Metrics
ocr_requests_total = Counter('ocr_requests_total', 'Total OCR requests', ['backend'])
ocr_processing_time = Histogram('ocr_processing_seconds', 'OCR processing time', ['backend'])
ocr_errors_total = Counter('ocr_errors_total', 'Total OCR errors', ['backend', 'error_type'])

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type="text/plain")
Logging Configuration
python# app/core/logging.py

import logging
import json
from datetime import datetime

class StructuredLogger:
    """Structured JSON logging"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        handler = logging.StreamHandler()
        handler.setFormatter(self.JSONFormatter())
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
            }
            if hasattr(record, 'extra'):
                log_data.update(record.extra)
            return json.dumps(log_data)
    
    def info(self, message: str, **kwargs):
        self.logger.info(message, extra=kwargs)
    
    def error(self, message: str, **kwargs):
        self.logger.error(message, extra=kwargs)

Success Criteria
Phase 1: MVP (Minimum Viable Product)

 FastAPI Server läuft lokal
 Ein GPU-Backend (GOT-OCR 2.0) funktioniert
 Single-Document Upload & Processing
 Deutsche Umlaute 100% korrekt
 API Response < 2 Sekunden
 Basic Health-Check

Phase 2: Multi-Backend

 Alle 3 Backends (DeepSeek, GOT-OCR, Surya) funktionieren
 Manuelle Backend-Auswahl via API
 VRAM Management (Lazy Loading)
 CPU-Backend läuft auf separatem Server (optional)

Phase 3: Intelligent Routing

 Automatische Backend-Auswahl
 Document Analyzer identifiziert Komplexität
 Routing Rules greifen korrekt
 Fallback-Mechanismus bei Backend-Failure

Phase 4: Production-Ready

 Batch-Processing funktioniert
 Invoice Field Extraction (deutsche Rechnungen)
 Preprocessing Pipeline verbessert Genauigkeit
 Postprocessing (Spell Check, Cleanup)
 95%+ Accuracy auf Test-Set (50 Docs)

Phase 5: Benchmarking

 Live Benchmark System
 Performance-Vergleich aller Backends
 Accuracy-Metriken dokumentiert
 Benchmark-Reports generieren

Phase 6: Deployment

 Docker Containers bauen & laufen
 Remote API-Zugriff funktioniert
 SSL/HTTPS konfiguriert (optional)
 Monitoring & Logging aktiv
 Dokumentation vollständig


DO's & DON'Ts
DO's ✅
Architecture

✅ Async/Await für I/O-Operations
✅ Lazy Model Loading (VRAM Management)
✅ Graceful Fallbacks (Backend unavailable → CPU)
✅ Type Hints überall (Python 3.10+)
✅ Pydantic Models für Validation

Code Quality

✅ Strukturierte Logs (JSON Format)
✅ Error Handling mit Context
✅ Unit Tests für kritische Funktionen
✅ Integration Tests für API
✅ Deutsche Test-Dokumente verwenden

Performance

✅ Batch-Processing wo möglich
✅ Caching für wiederholte Dokumente
✅ Parallel-Processing (careful mit VRAM)
✅ Progress-Tracking für lange Jobs

Security

✅ API-Keys für Zugriffskontrolle
✅ Rate Limiting implementieren
✅ Input Validation (File Size, Types)
✅ Sanitization von User-Inputs

DON'Ts ❌
Architecture

❌ KEINE Cloud-Dependencies (AWS, Azure, Google)
❌ KEINE synchronen Blocking-Operations in API
❌ KEINE Hardcoded Credentials
❌ KEINE ungetesteten Modelle in Production

Models

❌ KEINE PaddleOCR ohne Umlaut-Fix
❌ KEINE Modelle die >16GB VRAM brauchen
❌ KEINE unbekannten Model-Versionen

Performance

❌ KEINE synchronen Batch-Processing (blockiert API)
❌ KEINE unbegrenzten File-Uploads
❌ KEIN uncontrolled Memory Growth

Testing

❌ KEINE Production-Deployments ohne Tests
❌ KEINE Tests ohne deutsche Sample-Docs
❌ KEIN Skippen von Umlaut-Tests


Nächste Schritte
Immediate Actions (Start NOW)

Setup Project Structure

bash   mkdir ocr-multi-backend
   cd ocr-multi-backend
   mkdir -p app/api/v1/endpoints app/backend/gpu app/backend/cpu app/routing
   touch app/main.py app/backend/base.py

Install Dependencies

bash   pip install fastapi uvicorn torch transformers pillow
   pip install surya-ocr docling  # CPU backend

Download First Model (GOT-OCR)

python   from transformers import AutoModel, AutoTokenizer
   model = AutoModel.from_pretrained("ucaslcl/GOT-OCR2_0", trust_remote_code=True)
   tokenizer = AutoTokenizer.from_pretrained("ucaslcl/GOT-OCR2_0", trust_remote_code=True)

Implement Base Interface

Start with app/backend/base.py (see code above)
Implement ProcessingResult model


Implement First Backend (GOT-OCR)

app/backend/gpu/got_ocr_backend.py
Single-document processing
Test with 1 German invoice


Basic FastAPI App

app/main.py mit FastAPI
POST /api/v1/ocr/process endpoint
Test locally: uvicorn app.main:app --reload



Week 1 Goals

GOT-OCR Backend funktioniert
Single-Document API läuft
Deutsche Umlaute werden korrekt erkannt
Basic Tests geschrieben

Week 2 Goals

DeepSeek + Surya Backends hinzufügen
Backend-Switching via API
VRAM Management implementieren

Week 3+ Goals

Intelligent Routing
Batch Processing
Invoice Field Extraction
Benchmarking System
Docker Deployment


Besondere Hinweise für Claude Code

Umlaut-Testing ist CRITICAL

Erstelle dedizierte Tests mit: "Grüße", "Häuser", "Größe", "Straße", "Äpfel", "Öl", "Übung"
Jedes Backend muss diese Tests bestehen


VRAM Management

RTX 4080 hat nur 16GB
Lazy Loading: Model nur laden wenn gebraucht
Unload when switching backends
Monitor VRAM: torch.cuda.memory_allocated()


German Invoice Samples

Besorge oder erstelle 10-20 Sample-PDFs
Verschiedene Lieferanten/Layouts
Ground-Truth für Accuracy-Tests


Backend-Comparison

Live-Benchmarking ist ein Hauptfeature
User will SEHEN welches Backend für welche Docs besser ist
Metrics: Zeit, Accuracy, VRAM/RAM, Confidence


Remote Access

API muss von überall erreichbar sein
SSL/HTTPS empfohlen (Let's Encrypt)
Port-Forwarding am Router nötig


Error Handling

GPU unavailable → fallback to CPU
Backend fails → try next in fallback order
VRAM OOM → unload less critical model


Configuration

Alle Model-Paths konfigurierbar
Backend-Parameter (confidence, etc.) in YAML
Environment-Variables für Secrets


Logging

Jeder OCR-Durchlauf wird geloggt
Processing time, backend used, confidence
Errors mit Stack Traces
Structured JSON Logs




Budget & Ressourcen
Kosten

Hardware: Bereits vorhanden (0€ zusätzlich)
Software: 100% Open-Source (0€)
Cloud: 0€ (alles On-Premises)
Strom: ~€0.15-0.25/h bei GPU-Vollast

Zeitrahmen

Phase 1 (MVP): 1 Woche
Phase 2 (Multi-Backend): 1 Woche
Phase 3 (Routing): 1 Woche
Phase 4 (Production): 1 Woche
Phase 5 (Benchmark): 1 Woche
Phase 6 (Deployment): 1 Woche

Total: 6 Wochen für Full Production System
Wartung

Model Updates: Quarterly (neue Versionen prüfen)
Security Patches: Monthly (Dependencies updaten)
Monitoring: Continuous (Prometheus/Grafana optional)
Backups: Weekly (Config + Logs)


Zusammenfassung
Mission Owner: Ben (Digital Agency, Solingen)
Priority: HOCH - Business-Critical
System: Multi-Backend OCR mit 3 Engines

GPU A: DeepSeek-Janus-Pro (Komplexität)
GPU B: GOT-OCR 2.0 (Speed)
CPU: Surya + Docling (Fallback)

Hardware:

RTX 4080 (16GB VRAM)
i9-13900KF (32 Threads)
64GB RAM
Firmenlokaler Server (CPU)

Deployment: 100% On-Premises, Remote API Access
Expected Outcome:
Production-ready Multi-Backend OCR System mit:

Intelligent Routing
Live Benchmarking
Deutsche Business-Doc Support
95%+ Accuracy
<2s Response Time (GOT-OCR)

Special Focus:

Deutsche Umlaute (Zero Tolerance)
Rechnungs-Feldextraktion
Lieferanten-Template-Erkennung
VRAM-Efficient Model Management