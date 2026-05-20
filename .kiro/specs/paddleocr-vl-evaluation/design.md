# Design Document: PaddleOCR-VL 0.9B Evaluation

## Overview

Dieses Design beschreibt die systematische Evaluierung von PaddleOCR-VL 0.9B für die Integration in das Ablage-System. Die Evaluierung folgt dem Projekt-Ethos "Feinpoliert und durchdacht" mit isolierten Tests, umfassenden Benchmarks und einer dokumentierten Go/No-Go Entscheidung.

### Kontext

- **Aktueller Stand:** PaddleOCR-VL 0.9B ist noch nicht öffentlich verfügbar (Stand Dezember 2025)
- **Fallback:** PaddleOCR 3.3.2 Migration wurde bereits durchgeführt
- **Infrastruktur:** Docker-Container und Benchmark-System sind bereit

### Ziele

1. Validierung der GPU-Kompatibilität auf RTX 4080 (16GB VRAM)
2. Messung der OCR-Qualität für deutsche Geschäftsdokumente
3. Vergleich mit bestehenden Backends (PP-OCRv5, Surya, DeepSeek)
4. Fundierte Go/No-Go Entscheidung mit dokumentierter Begründung

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Evaluation System                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Availability     │    │ Docker Container │                   │
│  │ Checker          │───▶│ (GPU Isolated)   │                   │
│  └──────────────────┘    └────────┬─────────┘                   │
│                                   │                              │
│                                   ▼                              │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              Experimental Agent                       │       │
│  │  ┌─────────────────┐  ┌─────────────────┐            │       │
│  │  │ PaddleOCR-VL    │  │ PaddleOCR 3.3.2 │            │       │
│  │  │ (wenn verfügbar)│  │ (Fallback)      │            │       │
│  │  └─────────────────┘  └─────────────────┘            │       │
│  │  experimental=True                                    │       │
│  └──────────────────────────────────────────────────────┘       │
│                                   │                              │
│                                   ▼                              │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              Benchmark Runner                         │       │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │       │
│  │  │PP-OCRv5 │ │ Surya   │ │DeepSeek │ │PaddleVL │    │       │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │       │
│  └──────────────────────────────────────────────────────┘       │
│                                   │                              │
│                                   ▼                              │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              Report Generator                         │       │
│  │  • Accuracy Metrics    • VRAM Usage                  │       │
│  │  • CER/WER Calculation • Go/No-Go Decision           │       │
│  └──────────────────────────────────────────────────────┘       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Phasen-Architektur

```
Phase 1: Verfügbarkeitsprüfung
    │
    ├─▶ VL verfügbar ──▶ Phase 2: Isolated PoC
    │                         │
    │                         ▼
    │                    Phase 3: Benchmark
    │                         │
    │                         ▼
    │                    Phase 4: Go/No-Go
    │                         │
    │                         ├─▶ GO ──▶ Phase 5: Integration
    │                         │
    │                         └─▶ NO-GO ──▶ Dokumentation
    │
    └─▶ VL nicht verfügbar ──▶ Fallback: PaddleOCR 3.3.2
                                    │
                                    ▼
                              Migration & Test
```

## Components and Interfaces

### 1. AvailabilityChecker

Prüft die Verfügbarkeit von PaddleOCR-VL und dessen Abhängigkeiten.

```python
class AvailabilityChecker:
    """Prüft PaddleOCR-VL Verfügbarkeit."""

    def check_package_availability(self, package_name: str) -> AvailabilityResult:
        """
        Prüft ob ein Package auf PyPI oder PaddlePaddle Repos verfügbar ist.

        Args:
            package_name: Name des zu prüfenden Packages

        Returns:
            AvailabilityResult mit status, version, und source
        """
        pass

    def verify_version_requirements(
        self,
        installed_version: str,
        min_version: str
    ) -> bool:
        """
        Vergleicht installierte Version mit Mindestanforderung.

        Args:
            installed_version: Aktuell installierte Version
            min_version: Mindestens erforderliche Version

        Returns:
            True wenn Version ausreichend, sonst False
        """
        pass

    def get_dependency_report(self) -> DependencyReport:
        """Erstellt Bericht über alle Abhängigkeiten."""
        pass
```

### 2. ExperimentalAgent

Isolierter Agent für PaddleOCR-VL Tests mit experimental Flag.

```python
class PaddleOCRVLAgentExperimental(BaseOCRAgent):
    """
    Experimenteller Agent für PaddleOCR-VL Evaluierung.

    WARNUNG: Nicht für Production verwenden!
    """

    experimental: bool = True  # Markiert als experimentell

    def __init__(self, config: AgentConfig):
        """
        Initialisiert den experimentellen Agent.

        Versucht PaddleOCR-VL zu laden, fällt auf 3.3.2 zurück.
        """
        pass

    async def process(
        self,
        image: bytes,
        options: ProcessingOptions
    ) -> OCRResult:
        """
        Verarbeitet ein Bild mit PaddleOCR-VL.

        Args:
            image: Bild als Bytes
            options: Verarbeitungsoptionen

        Returns:
            OCRResult mit Text, Konfidenz, und Metriken
        """
        pass

    def get_vram_usage(self) -> VRAMMetrics:
        """Misst aktuellen VRAM-Verbrauch."""
        pass
```

### 3. BenchmarkRunner

Führt systematische Vergleiche zwischen OCR-Backends durch.

```python
class BenchmarkRunner:
    """Führt OCR-Backend-Benchmarks durch."""

    def __init__(self, config: BenchmarkConfig):
        self.backends: Dict[str, BackendConfig] = {}
        self.experimental_enabled: bool = False

    def get_available_backends(
        self,
        include_experimental: bool = False
    ) -> List[BackendConfig]:
        """
        Gibt verfügbare Backends zurück.

        Args:
            include_experimental: Ob experimentelle Backends eingeschlossen werden

        Returns:
            Liste der verfügbaren Backend-Konfigurationen
        """
        pass

    async def run_benchmark(
        self,
        backends: List[str],
        documents: List[Document],
        ground_truth: Dict[str, str]
    ) -> BenchmarkResults:
        """
        Führt Benchmark für alle angegebenen Backends durch.

        Args:
            backends: Liste der zu testenden Backend-Namen
            documents: Liste der Test-Dokumente
            ground_truth: Mapping von Dokument-ID zu Referenztext

        Returns:
            BenchmarkResults mit allen Metriken
        """
        pass

    def calculate_error_rates(
        self,
        ocr_text: str,
        ground_truth: str
    ) -> ErrorRates:
        """
        Berechnet CER und WER.

        Args:
            ocr_text: Vom OCR extrahierter Text
            ground_truth: Referenztext

        Returns:
            ErrorRates mit CER und WER
        """
        pass
```

### 4. ReportGenerator

Generiert strukturierte Berichte und Go/No-Go Empfehlungen.

```python
class ReportGenerator:
    """Generiert Evaluierungsberichte."""

    GO_CRITERIA = {
        "accuracy": 0.95,      # >= 95%
        "vram_gb": 14.0,       # <= 14GB
        "time_factor": 2.0     # <= 2x PP-OCRv5
    }

    NO_GO_CRITERIA = {
        "accuracy": 0.90,      # < 90%
        "oom_errors": True,    # Jeder OOM-Fehler
        "critical_bugs": True  # Jeder kritische Bug
    }

    def evaluate_go_criteria(
        self,
        results: BenchmarkResults
    ) -> GoNoGoDecision:
        """
        Evaluiert Go/No-Go Kriterien.

        Args:
            results: Benchmark-Ergebnisse

        Returns:
            GoNoGoDecision mit Empfehlung und Begründung
        """
        pass

    def generate_markdown_report(
        self,
        results: BenchmarkResults,
        decision: GoNoGoDecision
    ) -> str:
        """Generiert Markdown-Bericht."""
        pass

    def document_failure(
        self,
        test_name: str,
        error: Exception,
        potential_solutions: List[str]
    ) -> FailureReport:
        """Dokumentiert Testfehler mit Lösungsvorschlägen."""
        pass
```

## Data Models

### Konfiguration

```python
from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum

class BackendStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"

@dataclass
class BackendConfig:
    """Konfiguration für ein OCR-Backend."""
    name: str
    display_name: str
    requires_gpu: bool
    vram_gb: float
    agent_class: str
    experimental: bool = False
    enabled: bool = True

@dataclass
class AvailabilityResult:
    """Ergebnis der Verfügbarkeitsprüfung."""
    package_name: str
    available: bool
    version: Optional[str]
    source: Optional[str]  # "pypi", "paddlepaddle", "github"
    error_message: Optional[str]

@dataclass
class DependencyReport:
    """Bericht über alle Abhängigkeiten."""
    paddleocr_vl: AvailabilityResult
    paddlepaddle_gpu: AvailabilityResult
    cuda: AvailabilityResult
    all_satisfied: bool
```

### Metriken

```python
@dataclass
class VRAMMetrics:
    """VRAM-Nutzungsmetriken."""
    initial_mb: float
    peak_mb: float
    final_mb: float
    exceeded_threshold: bool
    threshold_mb: float = 14336  # 14GB

@dataclass
class ErrorRates:
    """Fehlerraten für OCR-Qualität."""
    cer: float  # Character Error Rate
    wer: float  # Word Error Rate
    umlaut_accuracy: float
    monetary_accuracy: float

@dataclass
class BenchmarkMetrics:
    """Metriken für einen Benchmark-Lauf."""
    backend_name: str
    document_id: str
    accuracy: float
    processing_time_ms: float
    vram_metrics: VRAMMetrics
    error_rates: ErrorRates
    confidence: float
```

### Entscheidungen

```python
class Decision(Enum):
    GO = "go"
    NO_GO = "no_go"
    CONDITIONAL = "conditional"

@dataclass
class GoNoGoDecision:
    """Go/No-Go Entscheidung mit Begründung."""
    decision: Decision
    reasons: List[str]
    metrics_summary: Dict[str, float]
    recommendations: List[str]

@dataclass
class FailureReport:
    """Dokumentation eines Testfehlers."""
    test_name: str
    error_type: str
    error_message: str
    timestamp: str
    potential_solutions: List[str]
    next_steps: List[str]
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Version Comparison Correctness

*For any* two version strings in semantic versioning format, the version comparison function SHALL correctly determine if the first version meets or exceeds the second version.

**Validates: Requirements 1.3**

### Property 2: Experimental Agent Exclusion

*For any* agent marked with `experimental=True`, the Benchmark_Runner SHALL exclude it from the list of available backends when `include_experimental=False`.

**Validates: Requirements 2.4**

### Property 3: VRAM Threshold Warning

*For any* VRAM measurement exceeding 14GB (14336MB), the Evaluation_System SHALL log a warning and set `exceeded_threshold=True` in the VRAMMetrics.

**Validates: Requirements 3.3**

### Property 4: German Text Quality

*For any* German text containing Umlauts (ä, ö, ü, Ä, Ö, Ü, ß) or compound words, the OCR result SHALL preserve these characters without corruption or incorrect splitting.

**Validates: Requirements 4.1, 4.4**

### Property 5: German Monetary Format Extraction

*For any* German monetary value in format "X.XXX,XX €" within a document, the OCR result SHALL correctly extract the value with proper decimal and thousand separators.

**Validates: Requirements 4.3**

### Property 6: Benchmark Consistency

*For any* benchmark run with multiple backends, all backends SHALL process the exact same set of documents in the same order.

**Validates: Requirements 5.2**

### Property 7: Error Rate Calculation Round-Trip

*For any* OCR text and ground truth pair, calculating CER and WER and then applying the inverse transformation SHALL produce consistent results within floating-point tolerance.

**Validates: Requirements 5.4**

### Property 8: Dataset Integrity

*For any* document in the evaluation dataset, there SHALL exist a corresponding ground truth entry with non-empty text content.

**Validates: Requirements 6.3**

### Property 9: Decision Logic Consistency

*For any* benchmark result, if all GO criteria are met AND no NO-GO criteria are met, the decision SHALL be GO. If any NO-GO criteria are met, the decision SHALL be NO-GO regardless of GO criteria.

**Validates: Requirements 7.3, 7.4**

### Property 10: Failure Documentation Completeness

*For any* failed test, the failure report SHALL contain: test name, error type, error message, timestamp, and at least one potential solution.

**Validates: Requirements 8.2**

## Error Handling

### Fehlerklassen

```python
class EvaluationError(Exception):
    """Basis-Exception für Evaluierungsfehler."""
    pass

class PackageUnavailableError(EvaluationError):
    """Package ist nicht verfügbar."""
    pass

class GPUNotAvailableError(EvaluationError):
    """GPU ist nicht verfügbar oder nicht erkannt."""
    pass

class VRAMExceededError(EvaluationError):
    """VRAM-Limit überschritten."""
    pass

class GroundTruthMissingError(EvaluationError):
    """Ground Truth für Dokument fehlt."""
    pass

class BenchmarkFailedError(EvaluationError):
    """Benchmark konnte nicht abgeschlossen werden."""
    pass
```

### Fehlerbehandlungsstrategie

| Fehler | Aktion | Dokumentation |
|--------|--------|---------------|
| PackageUnavailableError | Fallback zu 3.3.2 | Unavailability Report |
| GPUNotAvailableError | CPU-Modus oder Abbruch | GPU Status Report |
| VRAMExceededError | Warnung + Batch-Size reduzieren | VRAM Warning Log |
| GroundTruthMissingError | Dokument überspringen | Missing GT Report |
| OOM Error | Graceful Catch + NO-GO | OOM Failure Report |

### Graceful Degradation

```python
async def process_with_fallback(self, image: bytes) -> OCRResult:
    """Verarbeitet mit Fallback-Strategie."""
    try:
        # Versuch 1: PaddleOCR-VL
        return await self._process_vl(image)
    except PackageUnavailableError:
        logger.warning("paddleocr_vl_unavailable", fallback="3.3.2")
        # Versuch 2: PaddleOCR 3.3.2
        return await self._process_332(image)
    except torch.cuda.OutOfMemoryError as e:
        logger.error("gpu_oom", error=str(e))
        self._document_oom_failure(e)
        raise VRAMExceededError("OOM während Verarbeitung") from e
```

## Testing Strategy

### Dual Testing Approach

Die Evaluierung verwendet sowohl Unit Tests als auch Property-Based Tests:

- **Unit Tests:** Spezifische Beispiele, Edge Cases, Integrationspunkte
- **Property Tests:** Universelle Eigenschaften über alle gültigen Eingaben

### Property-Based Testing Framework

**Framework:** `hypothesis` (Python)

**Konfiguration:**
- Minimum 100 Iterationen pro Property Test
- Deadline: 10 Sekunden pro Test
- Seed für Reproduzierbarkeit

### Test-Kategorien

| Kategorie | Typ | Beschreibung |
|-----------|-----|--------------|
| Verfügbarkeit | Unit | Package-Checks, Version-Vergleiche |
| GPU/VRAM | Unit + Property | VRAM-Messung, Threshold-Verhalten |
| OCR-Qualität | Property | Umlaut-Erkennung, Monetary-Extraktion |
| Benchmark | Property | Konsistenz, Error-Rate-Berechnung |
| Entscheidung | Property | Go/No-Go Logik |
| Dokumentation | Unit | Report-Generierung, Failure-Handling |

### Test-Annotationen

```python
# Format: Feature: paddleocr-vl-evaluation, Property N: <property_text>

@given(st.text(alphabet=string.digits + ".", min_size=3, max_size=20))
def test_version_comparison_correctness(version_str):
    """
    Feature: paddleocr-vl-evaluation, Property 1: Version Comparison Correctness
    Validates: Requirements 1.3
    """
    # Test implementation
    pass
```

### Testdaten

- **Dataset:** 20 deutsche Geschäftsdokumente
- **Ground Truth:** Manuell verifizierte Referenztexte
- **Kategorien:** Rechnungen, Verträge, Briefe, Formulare, Mixed Layouts, Handschrift
