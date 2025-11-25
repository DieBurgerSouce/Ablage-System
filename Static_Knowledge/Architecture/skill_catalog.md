# Skill Catalog - Vollständiger Katalog aller Skills
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Skill Catalog Overview](#skill-catalog-overview)
2. [OCR & Processing Skills](#ocr--processing-skills)
3. [GPU Management Skills](#gpu-management-skills)
4. [German Language Skills](#german-language-skills)
5. [Error Handling Skills](#error-handling-skills)
6. [Monitoring Skills](#monitoring-skills)
7. [Skill Implementation Guide](#skill-implementation-guide)
8. [Skill Registry System](#skill-registry-system)

---

## Skill Catalog Overview

Skills sind **wiederverwendbare Fähigkeiten**, die Agents nutzen können. Dieser Katalog dokumentiert alle verfügbaren Skills im Ablage-System.

### Skill-Kategorien

```
┌───────────────────────────────────────────────────────────┐
│                    SKILL CATEGORIES                        │
├───────────────────────────────────────────────────────────┤
│                                                            │
│  📄 OCR & Processing    🔧 GPU Management                 │
│  - Backend Selection    - VRAM Monitoring                 │
│  - Template Extraction  - Batch Optimization              │
│  - Text Extraction      - OOM Prevention                  │
│                                                            │
│  🇩🇪 German Language    ⚠️  Error Handling                 │
│  - Text Normalization   - Retry Logic                     │
│  - Umlaut Validation    - Fallback Strategies             │
│  - Spell Checking       - Circuit Breaker                 │
│                                                            │
│  📊 Monitoring          🔐 Security                        │
│  - Health Checks        - Input Validation                │
│  - Metrics Collection   - Access Control                  │
│  - Alerting             - Data Sanitization               │
└───────────────────────────────────────────────────────────┘
```

### Skill Naming Convention

```
{domain}_{function}_skill.yaml

Examples:
- backend_selection_skill.yaml
- gpu_management_skill.yaml
- german_text_processing_skill.yaml
- error_recovery_skill.yaml
```

---

## OCR & Processing Skills

### 1. Backend Selection Skill

**File:** `Static_Knowledge/Skills/backend_selection_skill.yaml`

**Purpose:** Intelligente Auswahl des optimalen OCR-Backends

#### YAML Definition

```yaml
metadata:
  skill_id: "backend_selection"
  version: "1.2.0"
  category: "ocr_processing"
  dependencies: ["gpu_management"]
  last_updated: "2025-01-23"
  author: "Ablage-System Team"

description: |
  Wählt automatisch den optimalen OCR-Backend basierend auf:
  - Dokumenttyp und Komplexität
  - Verfügbare GPU-Ressourcen
  - Performance-Anforderungen
  - Qualitäts-Anforderungen

capabilities:
  - Document complexity analysis
  - Backend performance prediction
  - VRAM requirement estimation
  - Automatic fallback routing
  - Quality-performance trade-off optimization

backends:
  deepseek:
    name: "DeepSeek-Janus-Pro 1.0"
    type: "multimodal"
    vram_required_gb: 12
    strengths:
      - "Complex layouts (tables, multi-column)"
      - "Handwritten text"
      - "Fraktur fonts"
      - "Mixed German/English documents"
    ideal_for:
      - "complexity_score >= 7"
      - "has_handwriting == true"
      - "has_fraktur == true"
      - "document_type == 'vertrag'"
    performance:
      avg_pages_per_second: 2.5
      accuracy_score: 0.98

  got_ocr:
    name: "GOT-OCR 2.0"
    type: "transformer"
    vram_required_gb: 10
    strengths:
      - "Standard business documents"
      - "Invoices and forms"
      - "Clean printed text"
      - "Fast processing"
    ideal_for:
      - "complexity_score < 7"
      - "document_type == 'rechnung'"
      - "has_handwriting == false"
    performance:
      avg_pages_per_second: 6.0
      accuracy_score: 0.95

  surya:
    name: "Surya + Docling"
    type: "layout_aware"
    vram_required_gb: 0  # CPU only
    strengths:
      - "Layout analysis"
      - "Document structure extraction"
      - "No GPU required"
    ideal_for:
      - "gpu_available == false"
      - "layout_analysis_required == true"
    performance:
      avg_pages_per_second: 1.5
      accuracy_score: 0.90

selection_algorithm:
  step_1_document_classification:
    description: "Klassifiziere Dokument und bewerte Komplexität"
    inputs:
      - "image_path: str"
      - "metadata: Optional[Dict]"
    outputs:
      - "document_type: str"  # rechnung, vertrag, brief, formular
      - "has_tables: bool"
      - "has_handwriting: bool"
      - "has_fraktur: bool"
      - "text_density: float"  # 0-1
      - "image_quality: float"  # 0-1
      - "complexity_score: int"  # 0-10
    code_reference: "app/services/document_classifier.py"

  step_2_vram_check:
    description: "Prüfe verfügbare GPU-Ressourcen"
    inputs:
      - "None"
    outputs:
      - "gpu_available: bool"
      - "available_vram_gb: float"
      - "current_vram_usage_percent: float"
    code_reference: "app/gpu_manager.py"

  step_3_backend_selection:
    description: "Wähle optimalen Backend basierend auf Klassifikation und Ressourcen"
    decision_tree: |
      # Primary selection based on document characteristics
      IF gpu_available == false:
          RETURN "surya"  # CPU fallback

      IF current_vram_usage_percent > 80:
          RETURN "surya"  # GPU overloaded, use CPU

      IF has_handwriting OR has_fraktur:
          IF available_vram_gb >= 12:
              RETURN "deepseek"  # Best for handwriting/Fraktur
          ELSE:
              RETURN "got_ocr"  # Fallback

      IF complexity_score >= 7:
          IF available_vram_gb >= 12:
              RETURN "deepseek"  # Complex layout
          ELSE:
              RETURN "got_ocr"

      IF document_type == "rechnung" AND complexity_score < 5:
          RETURN "got_ocr"  # Fast processing for simple invoices

      IF document_type == "vertrag":
          IF available_vram_gb >= 12:
              RETURN "deepseek"  # High accuracy for contracts
          ELSE:
              RETURN "got_ocr"

      # Default: GOT-OCR for balanced performance
      RETURN "got_ocr"

    code_reference: "app/services/ocr/orchestrator.py"

  step_4_quality_validation:
    description: "Validiere Backend-Auswahl gegen Qualitäts-Anforderungen"
    inputs:
      - "selected_backend: str"
      - "quality_requirements: Dict"
    outputs:
      - "backend_validated: str"
      - "selection_reason: str"

usage_patterns:
  basic_usage:
    description: "Automatische Backend-Auswahl"
    example: |
      from app.services.ocr.orchestrator import OCROrchestrator

      orchestrator = OCROrchestrator()

      # Automatic backend selection
      backend = await orchestrator.select_backend(
          image_path="/path/to/document.pdf",
          metadata={"document_type": "rechnung"}
      )

      print(f"Selected backend: {backend}")
      # Output: "got_ocr"

  manual_override:
    description: "Manuelle Backend-Auswahl mit Validierung"
    example: |
      # Force specific backend (with validation)
      backend = await orchestrator.select_backend(
          image_path="/path/to/document.pdf",
          force_backend="deepseek"
      )

  batch_selection:
    description: "Backend-Auswahl für Batch-Verarbeitung"
    example: |
      # Select backend for batch of documents
      documents = [...]  # List of documents

      backend_distribution = await orchestrator.select_backend_for_batch(
          documents=documents,
          optimize_for="throughput"  # or "quality"
      )

      # Result: {
      #   "deepseek": [doc1, doc5],
      #   "got_ocr": [doc2, doc3, doc4],
      #   "surya": []
      # }

best_practices:
  - name: "Cache Classification Results"
    rationale: "Avoid re-classifying same document"
    implementation: |
      Use Redis cache with document hash as key:
      cache_key = f"doc_classification:{document_hash}"

  - name: "Monitor Backend Performance"
    rationale: "Adjust selection algorithm based on real performance data"
    implementation: |
      Track metrics:
      - backend_processing_time_ms{backend="deepseek"}
      - backend_accuracy_score{backend="deepseek"}

  - name: "Fallback Chain"
    rationale: "Always have fallback options"
    implementation: |
      Primary: deepseek → Fallback: got_ocr → Final: surya (CPU)

monitoring:
  metrics:
    - "backend_selections_total{backend='deepseek'}"
    - "backend_selections_total{backend='got_ocr'}"
    - "backend_selections_total{backend='surya'}"
    - "backend_selection_duration_seconds"
    - "document_complexity_score"

alerts:
  - condition: "gpu_available == false for > 5 minutes"
    action: "Alert: GPU not available, all requests using CPU backend"
    severity: "warning"

  - condition: "backend_selection_failures > 10 in 5 minutes"
    action: "Alert: Backend selection failing"
    severity: "critical"

references:
  - "app/services/ocr/orchestrator.py"
  - "app/services/document_classifier.py"
  - "app/gpu_manager.py"
  - "ARCHITECTURE.md#ocr-backend-selection"

changelog:
  - version: "1.2.0"
    date: "2025-01-23"
    changes:
      - "Added complexity scoring algorithm"
      - "Improved VRAM usage prediction"

  - version: "1.1.0"
    date: "2025-01-15"
    changes:
      - "Added Surya backend support"
      - "Added batch selection optimization"
```

#### Python Implementation

```python
# app/services/ocr/backend_selector.py
from typing import Dict, Any, Optional
from dataclasses import dataclass
import structlog
from app.gpu_manager import GPUManager
from app.services.document_classifier import DocumentClassifier

logger = structlog.get_logger(__name__)


@dataclass
class BackendSelection:
    """Result of backend selection."""
    backend: str
    reason: str
    confidence: float
    vram_required_gb: float
    estimated_processing_time_sec: float


class BackendSelectionSkill:
    """
    Implementation of Backend Selection Skill.

    Loads configuration from backend_selection_skill.yaml
    and provides intelligent backend selection.
    """

    def __init__(self, skill_config: Dict[str, Any]):
        self.config = skill_config
        self.backends = skill_config["backends"]
        self.gpu_manager = GPUManager()
        self.classifier = DocumentClassifier()

    async def select_backend(
        self,
        image_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        force_backend: Optional[str] = None
    ) -> BackendSelection:
        """
        Select optimal OCR backend.

        Args:
            image_path: Path to document image
            metadata: Optional metadata about document
            force_backend: Force specific backend (bypasses selection logic)

        Returns:
            BackendSelection with selected backend and reasoning
        """
        # Step 1: Document Classification
        classification = await self.classifier.classify(
            image_path=image_path,
            metadata=metadata
        )

        logger.info(
            "document_classified",
            document_type=classification["document_type"],
            complexity_score=classification["complexity_score"],
            has_handwriting=classification["has_handwriting"],
            has_fraktur=classification["has_fraktur"]
        )

        # Step 2: VRAM Check
        gpu_status = self.gpu_manager.get_status()

        logger.info(
            "gpu_status_checked",
            gpu_available=gpu_status["available"],
            available_vram_gb=gpu_status.get("free_vram_gb", 0),
            vram_usage_percent=gpu_status.get("vram_usage_percent", 0)
        )

        # Step 3: Backend Selection
        if force_backend:
            backend = force_backend
            reason = "manual_override"
        else:
            backend, reason = self._apply_selection_logic(
                classification,
                gpu_status
            )

        # Get backend info
        backend_info = self.backends[backend]

        # Estimate processing time
        estimated_time = self._estimate_processing_time(
            backend=backend,
            classification=classification
        )

        result = BackendSelection(
            backend=backend,
            reason=reason,
            confidence=0.95,  # Could be calculated based on classification confidence
            vram_required_gb=backend_info["vram_required_gb"],
            estimated_processing_time_sec=estimated_time
        )

        logger.info(
            "backend_selected",
            backend=result.backend,
            reason=result.reason,
            vram_required_gb=result.vram_required_gb,
            estimated_time_sec=result.estimated_processing_time_sec
        )

        return result

    def _apply_selection_logic(
        self,
        classification: Dict[str, Any],
        gpu_status: Dict[str, Any]
    ) -> tuple[str, str]:
        """
        Apply selection decision tree from skill configuration.

        Returns:
            (backend, reason) tuple
        """
        # Extract classification features
        document_type = classification["document_type"]
        complexity_score = classification["complexity_score"]
        has_handwriting = classification["has_handwriting"]
        has_fraktur = classification["has_fraktur"]

        # Extract GPU status
        gpu_available = gpu_status["available"]
        available_vram_gb = gpu_status.get("free_vram_gb", 0)
        vram_usage_percent = gpu_status.get("vram_usage_percent", 0)

        # Apply decision tree
        if not gpu_available:
            return "surya", "gpu_not_available"

        if vram_usage_percent > 80:
            return "surya", "gpu_overloaded"

        if has_handwriting or has_fraktur:
            if available_vram_gb >= 12:
                return "deepseek", "handwriting_or_fraktur_detected"
            else:
                return "got_ocr", "handwriting_but_insufficient_vram"

        if complexity_score >= 7:
            if available_vram_gb >= 12:
                return "deepseek", "complex_layout"
            else:
                return "got_ocr", "complex_but_insufficient_vram"

        if document_type == "rechnung" and complexity_score < 5:
            return "got_ocr", "simple_invoice_fast_processing"

        if document_type == "vertrag":
            if available_vram_gb >= 12:
                return "deepseek", "contract_high_accuracy_required"
            else:
                return "got_ocr", "contract_but_insufficient_vram"

        # Default
        return "got_ocr", "balanced_performance"

    def _estimate_processing_time(
        self,
        backend: str,
        classification: Dict[str, Any]
    ) -> float:
        """Estimate processing time based on backend and document characteristics."""
        backend_info = self.backends[backend]
        pages_per_second = backend_info["performance"]["avg_pages_per_second"]

        # Assume 1 page for now (could be extended for multi-page)
        base_time = 1.0 / pages_per_second

        # Adjust for complexity
        complexity_multiplier = 1.0 + (classification["complexity_score"] / 20.0)

        return base_time * complexity_multiplier


# Example Usage
async def example_backend_selection():
    """Example of using BackendSelectionSkill."""
    import yaml

    # Load skill configuration
    with open("Static_Knowledge/Skills/backend_selection_skill.yaml") as f:
        skill_config = yaml.safe_load(f)

    # Create skill instance
    selector = BackendSelectionSkill(skill_config)

    # Select backend for document
    selection = await selector.select_backend(
        image_path="/path/to/invoice.pdf",
        metadata={"document_type": "rechnung"}
    )

    print(f"Backend: {selection.backend}")
    print(f"Reason: {selection.reason}")
    print(f"VRAM Required: {selection.vram_required_gb} GB")
    print(f"Estimated Time: {selection.estimated_processing_time_sec:.2f} sec")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_backend_selection())
```

---

### 2. Template Extraction Skill

**File:** `Static_Knowledge/Skills/template_extraction_skill.yaml`

**Purpose:** Strukturierte Datenextraktion aus Dokumenten-Templates

#### YAML Definition

```yaml
metadata:
  skill_id: "template_extraction"
  version: "1.0.0"
  category: "document_processing"
  dependencies: ["german_text_processing"]
  last_updated: "2025-01-23"

description: |
  Extrahiert strukturierte Daten aus bekannten Dokumenttypen
  (Rechnungen, Verträge, Formulare) basierend auf Templates.

capabilities:
  - Template matching and identification
  - Key-value pair extraction
  - Field validation and type conversion
  - Confidence scoring
  - Multi-variant template support

templates:
  rechnung_standard:
    name: "Standard German Invoice"
    version: "1.0"
    match_patterns:
      - "Rechnung"
      - "Rechnungsnummer"
      - "Rechnungsdatum"
      - "Betrag"
    fields:
      rechnungsnummer:
        regex: "Rechnung(?:snummer)?:?\\s*([A-Z0-9-]+)"
        type: "string"
        required: true
        validation:
          pattern: "^[A-Z]{2}-\\d{4}-\\d{5}$"

      rechnungsdatum:
        regex: "Rechnung(?:sdatum)?:?\\s*(\\d{2}\\.\\d{2}\\.\\d{4})"
        type: "date"
        required: true
        format: "DD.MM.YYYY"

      betrag_netto:
        regex: "Nettobetrag:?\\s*([\\d.]+,\\d{2})\\s*€"
        type: "decimal"
        required: true
        format: "german_currency"

      betrag_brutto:
        regex: "Bruttobetrag|Gesamt:?\\s*([\\d.]+,\\d{2})\\s*€"
        type: "decimal"
        required: true
        format: "german_currency"

      lieferant:
        regex: "Firma|Von:?\\s*([\\w\\s&.-]+GmbH)"
        type: "string"
        required: true

      steuernummer:
        regex: "Steuernummer:?\\s*([\\d\\/]+)"
        type: "string"
        required: false

  vertrag_standard:
    name: "Standard German Contract"
    match_patterns:
      - "Vertrag"
      - "Vertragspartner"
      - "Vertragsnummer"
    fields:
      vertragsnummer:
        regex: "Vertrag(?:snummer)?:?\\s*([A-Z0-9-]+)"
        type: "string"
        required: true

      vertragsdatum:
        regex: "(?:Vertrags)?datum:?\\s*(\\d{2}\\.\\d{2}\\.\\d{4})"
        type: "date"
        required: true

      vertragspartner_a:
        regex: "Vertragspartei A:?\\s*([\\w\\s&.-]+)"
        type: "string"
        required: true

      vertragspartner_b:
        regex: "Vertragspartei B:?\\s*([\\w\\s&.-]+)"
        type: "string"
        required: true

extraction_algorithm:
  step_1_template_matching:
    description: "Identifiziere passendes Template"
    inputs:
      - "ocr_text: str"
    outputs:
      - "matched_template: Optional[str]"
      - "match_confidence: float"
    logic: |
      For each template:
        score = 0
        for pattern in template.match_patterns:
          if pattern in ocr_text:
            score += 1
        confidence = score / len(template.match_patterns)

      Select template with highest confidence
      Return None if confidence < 0.5

  step_2_field_extraction:
    description: "Extrahiere Felder aus Text"
    inputs:
      - "ocr_text: str"
      - "template: Dict"
    outputs:
      - "extracted_fields: Dict[str, Any]"
      - "field_confidences: Dict[str, float]"
    logic: |
      For each field in template.fields:
        matches = regex.findall(field.regex, ocr_text)
        if matches:
          value = matches[0]
          confidence = calculate_confidence(value, field)
          extracted_fields[field_name] = convert_type(value, field.type)
          field_confidences[field_name] = confidence

  step_3_validation:
    description: "Validiere extrahierte Daten"
    inputs:
      - "extracted_fields: Dict"
      - "template: Dict"
    outputs:
      - "validated_fields: Dict"
      - "validation_errors: List[str]"
    logic: |
      For each field in extracted_fields:
        if field.required and field not in extracted_fields:
          validation_errors.append(f"Missing required field: {field}")

        if field.validation:
          if not validate(extracted_fields[field], field.validation):
            validation_errors.append(f"Invalid {field}: {value}")

usage_patterns:
  basic_extraction:
    example: |
      from app.services.template_extractor import TemplateExtractor

      extractor = TemplateExtractor()

      # Extract data from invoice
      result = await extractor.extract(
          ocr_text="Rechnung RE-2025-00123...",
          document_type="rechnung"
      )

      print(result["extracted_fields"])
      # {
      #   "rechnungsnummer": "RE-2025-00123",
      #   "rechnungsdatum": date(2025, 1, 23),
      #   "betrag_netto": Decimal("1000.00"),
      #   "betrag_brutto": Decimal("1190.00")
      # }

best_practices:
  - name: "Validate All Extracted Data"
    rationale: "OCR errors can produce invalid data"

  - name: "Use Confidence Scores"
    rationale: "Flag low-confidence extractions for manual review"

  - name: "Support Template Variants"
    rationale: "Same document type can have multiple layouts"

monitoring:
  metrics:
    - "template_matches_total{template='rechnung_standard'}"
    - "extraction_confidence_score"
    - "validation_errors_total"

references:
  - "app/services/template_extractor.py"
```

---

## GPU Management Skills

### 3. GPU Management Skill

**File:** `Static_Knowledge/Skills/gpu_management_skill.yaml`

**Purpose:** GPU-Ressourcen Management und Optimierung

#### YAML Definition

```yaml
metadata:
  skill_id: "gpu_management"
  version: "1.3.0"
  category: "resource_management"
  dependencies: []
  last_updated: "2025-01-23"

description: |
  Verwaltet GPU-Ressourcen für OCR-Backends:
  - VRAM Monitoring
  - Batch Size Optimization
  - OOM Prevention
  - Multi-GPU Scheduling

capabilities:
  - Real-time VRAM monitoring
  - Dynamic batch size adjustment
  - Out-of-memory prevention
  - GPU utilization optimization
  - Multi-GPU load balancing
  - Memory leak detection

gpu_configuration:
  target_device: "RTX 4080"
  total_vram_gb: 16
  safe_threshold_percent: 85  # Use max 85% of VRAM
  batch_size_limits:
    deepseek:
      min: 1
      max: 32
      default: 8
    got_ocr:
      min: 1
      max: 64
      default: 16
    surya:
      min: 1
      max: 128
      default: 32

vram_requirements:
  # Estimated VRAM per image (in MB)
  deepseek:
    base_model_mb: 8192  # 8GB for model
    per_image_mb: 500
    overhead_mb: 1024

  got_ocr:
    base_model_mb: 6144  # 6GB for model
    per_image_mb: 300
    overhead_mb: 512

  surya:
    base_model_mb: 0  # CPU only
    per_image_mb: 0
    overhead_mb: 0

batch_optimization:
  algorithm: |
    # Calculate optimal batch size
    available_vram_mb = total_vram_mb * safe_threshold_percent
    usable_vram_mb = available_vram_mb - base_model_mb - overhead_mb

    optimal_batch = floor(usable_vram_mb / per_image_mb)
    optimal_batch = min(optimal_batch, max_batch_size)
    optimal_batch = max(optimal_batch, min_batch_size)

    return optimal_batch

  dynamic_adjustment: |
    # Adjust batch size during processing
    IF gpu_oom_detected:
        new_batch_size = current_batch_size // 2
        clear_cuda_cache()
        retry_with_smaller_batch()

    IF vram_usage < 50%:
        new_batch_size = min(current_batch_size * 1.5, max_batch_size)

memory_management:
  cleanup_strategies:
    - trigger: "after_each_batch"
      action: "torch.cuda.empty_cache()"

    - trigger: "vram_usage > 90%"
      action: "force_garbage_collection"

    - trigger: "oom_detected"
      action: "clear_all_caches_and_retry"

  leak_detection:
    enabled: true
    check_interval_seconds: 60
    threshold_mb_per_minute: 100
    action_on_leak: "alert_and_restart_worker"

monitoring:
  metrics:
    - "gpu_vram_total_bytes"
    - "gpu_vram_used_bytes"
    - "gpu_vram_free_bytes"
    - "gpu_vram_usage_percent"
    - "gpu_utilization_percent"
    - "gpu_temperature_celsius"
    - "gpu_power_watts"
    - "gpu_oom_errors_total"
    - "batch_size_current"
    - "batch_size_optimal"

  alerts:
    - condition: "vram_usage_percent > 95"
      severity: "critical"
      action: "Reduce batch size immediately"

    - condition: "gpu_temperature > 85"
      severity: "warning"
      action: "Throttle processing"

    - condition: "oom_errors > 3 in 5 minutes"
      severity: "critical"
      action: "Restart worker, investigate"

usage_patterns:
  basic_usage:
    example: |
      from app.gpu_manager import GPUManager

      gpu = GPUManager()

      # Check if GPU available
      if gpu.is_available():
          status = gpu.get_status()
          print(f"VRAM: {status['free_vram_gb']:.2f} GB free")

          # Calculate optimal batch size
          optimal_batch = gpu.calculate_optimal_batch_size(
              backend="deepseek"
          )
          print(f"Optimal batch size: {optimal_batch}")

  with_memory_guard:
    example: |
      from app.gpu_manager import gpu_memory_guard

      # Use context manager for safe GPU operations
      with gpu_memory_guard(threshold_gb=13.6):
          results = model.process_batch(images)
          # Automatically clears cache if threshold exceeded

  dynamic_batch_processing:
    example: |
      from app.services.batch_processor import DynamicBatchProcessor

      processor = DynamicBatchProcessor(backend="deepseek")

      # Automatically adjusts batch size during processing
      results = await processor.process_documents(
          documents=documents,
          initial_batch_size=16
      )
      # Batch size dynamically adjusted based on VRAM

best_practices:
  - name: "Always Check GPU Availability"
    rationale: "Graceful fallback to CPU if GPU not available"

  - name: "Monitor VRAM Throughout Processing"
    rationale: "Prevent OOM errors"

  - name: "Clear Cache After Large Batches"
    rationale: "Free fragmented memory"

  - name: "Use Memory Guards"
    rationale: "Automatic cleanup on threshold breach"

references:
  - "app/gpu_manager.py"
  - "app/services/batch_processor.py"

changelog:
  - version: "1.3.0"
    date: "2025-01-23"
    changes:
      - "Added memory leak detection"
      - "Improved batch size calculation"

  - version: "1.2.0"
    date: "2025-01-15"
    changes:
      - "Added multi-GPU support"
```

#### Python Implementation

```python
# app/gpu_manager.py
from typing import Dict, Any, Optional
from contextlib import contextmanager
import structlog

logger = structlog.get_logger(__name__)


class GPUManager:
    """
    GPU Management Skill Implementation.

    Provides GPU resource monitoring, batch size optimization,
    and OOM prevention based on gpu_management_skill.yaml.
    """

    def __init__(self, skill_config: Optional[Dict[str, Any]] = None):
        self.config = skill_config or self._load_default_config()
        self.gpu_config = self.config["gpu_configuration"]
        self.vram_requirements = self.config["vram_requirements"]

        # Try to import PyTorch
        try:
            import torch
            self.torch = torch
            self.gpu_available = torch.cuda.is_available()
        except ImportError:
            self.torch = None
            self.gpu_available = False

    def is_available(self) -> bool:
        """Check if GPU is available."""
        return self.gpu_available

    def get_status(self) -> Dict[str, Any]:
        """
        Get current GPU status.

        Returns:
            {
                "available": bool,
                "total_vram_gb": float,
                "used_vram_gb": float,
                "free_vram_gb": float,
                "vram_usage_percent": float,
                "gpu_utilization_percent": float,
                "temperature_celsius": float
            }
        """
        if not self.gpu_available:
            return {
                "available": False,
                "total_vram_gb": 0,
                "used_vram_gb": 0,
                "free_vram_gb": 0,
                "vram_usage_percent": 0
            }

        # Get VRAM stats
        total_vram = self.torch.cuda.get_device_properties(0).total_memory
        allocated_vram = self.torch.cuda.memory_allocated()
        free_vram = total_vram - allocated_vram

        total_gb = total_vram / 1024**3
        used_gb = allocated_vram / 1024**3
        free_gb = free_vram / 1024**3
        usage_percent = (allocated_vram / total_vram) * 100

        status = {
            "available": True,
            "total_vram_gb": total_gb,
            "used_vram_gb": used_gb,
            "free_vram_gb": free_gb,
            "vram_usage_percent": usage_percent
        }

        # Get GPU utilization (requires nvidia-ml-py3)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)

            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            temperature = pynvml.nvmlDeviceGetTemperature(
                handle,
                pynvml.NVML_TEMPERATURE_GPU
            )

            status["gpu_utilization_percent"] = utilization.gpu
            status["temperature_celsius"] = temperature

            pynvml.nvmlShutdown()
        except:
            pass  # nvidia-ml-py3 not available

        return status

    def calculate_optimal_batch_size(
        self,
        backend: str,
        current_batch_size: Optional[int] = None
    ) -> int:
        """
        Calculate optimal batch size for backend.

        Args:
            backend: OCR backend name (deepseek, got_ocr, surya)
            current_batch_size: Current batch size (for adjustment)

        Returns:
            Optimal batch size
        """
        if not self.gpu_available:
            # CPU fallback: use small batch
            return 1

        # Get backend config
        backend_limits = self.gpu_config["batch_size_limits"][backend]
        backend_vram = self.vram_requirements[backend]

        # Get current VRAM status
        status = self.get_status()
        total_vram_mb = status["total_vram_gb"] * 1024
        free_vram_mb = status["free_vram_gb"] * 1024

        # Calculate safe VRAM limit
        safe_threshold = self.gpu_config["safe_threshold_percent"] / 100
        available_vram_mb = total_vram_mb * safe_threshold

        # Calculate usable VRAM (accounting for model and overhead)
        usable_vram_mb = available_vram_mb - backend_vram["base_model_mb"] - backend_vram["overhead_mb"]

        # Calculate optimal batch size
        if usable_vram_mb > 0:
            optimal_batch = int(usable_vram_mb / backend_vram["per_image_mb"])
        else:
            optimal_batch = backend_limits["min"]

        # Apply limits
        optimal_batch = max(optimal_batch, backend_limits["min"])
        optimal_batch = min(optimal_batch, backend_limits["max"])

        logger.info(
            "optimal_batch_calculated",
            backend=backend,
            optimal_batch=optimal_batch,
            free_vram_gb=status["free_vram_gb"],
            vram_usage_percent=status["vram_usage_percent"]
        )

        return optimal_batch

    def clear_cache(self) -> None:
        """Clear GPU cache."""
        if self.gpu_available:
            self.torch.cuda.empty_cache()
            logger.info("gpu_cache_cleared")

    def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed GPU status including all metrics."""
        status = self.get_status()

        if self.gpu_available:
            # Add memory info
            memory_stats = self.torch.cuda.memory_stats()
            status["memory_stats"] = {
                "allocated_bytes": memory_stats.get("allocated_bytes.all.current", 0),
                "reserved_bytes": memory_stats.get("reserved_bytes.all.current", 0),
                "active_bytes": memory_stats.get("active_bytes.all.current", 0)
            }

        return status

    @staticmethod
    def _load_default_config() -> Dict[str, Any]:
        """Load default GPU configuration."""
        return {
            "gpu_configuration": {
                "target_device": "RTX 4080",
                "total_vram_gb": 16,
                "safe_threshold_percent": 85,
                "batch_size_limits": {
                    "deepseek": {"min": 1, "max": 32, "default": 8},
                    "got_ocr": {"min": 1, "max": 64, "default": 16},
                    "surya": {"min": 1, "max": 128, "default": 32}
                }
            },
            "vram_requirements": {
                "deepseek": {
                    "base_model_mb": 8192,
                    "per_image_mb": 500,
                    "overhead_mb": 1024
                },
                "got_ocr": {
                    "base_model_mb": 6144,
                    "per_image_mb": 300,
                    "overhead_mb": 512
                },
                "surya": {
                    "base_model_mb": 0,
                    "per_image_mb": 0,
                    "overhead_mb": 0
                }
            }
        }


@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6):
    """
    Context manager for GPU memory protection.

    Ensures GPU memory stays below threshold.
    Automatically clears cache if threshold exceeded.

    Args:
        threshold_gb: Maximum allowed VRAM usage in GB
    """
    import torch

    try:
        yield
    finally:
        if torch.cuda.is_available():
            current_memory_gb = torch.cuda.memory_allocated() / 1024**3

            if current_memory_gb > threshold_gb:
                logger.warning(
                    "gpu_memory_threshold_exceeded",
                    current_gb=current_memory_gb,
                    threshold_gb=threshold_gb
                )
                torch.cuda.empty_cache()
                logger.info("gpu_cache_cleared_by_guard")


# Example Usage
def example_gpu_management():
    """Example of using GPUManager."""
    gpu = GPUManager()

    # Check availability
    if gpu.is_available():
        print("GPU is available")

        # Get status
        status = gpu.get_status()
        print(f"VRAM Usage: {status['vram_usage_percent']:.1f}%")
        print(f"Free VRAM: {status['free_vram_gb']:.2f} GB")

        # Calculate optimal batch size
        batch_sizes = {}
        for backend in ["deepseek", "got_ocr", "surya"]:
            optimal = gpu.calculate_optimal_batch_size(backend)
            batch_sizes[backend] = optimal
            print(f"{backend}: {optimal} images/batch")

        # Use memory guard
        with gpu_memory_guard(threshold_gb=13.6):
            # Process data
            print("Processing with memory protection...")

    else:
        print("GPU not available - using CPU fallback")


if __name__ == "__main__":
    example_gpu_management()
```

---

**Fortsetzung folgt mit weiteren Skills (German Language, Error Handling, Monitoring)...**

Soll ich:
1. Die verbleibenden Skills fortsetzen?
2. Oder mit den anderen Dokumenten (hook_registry_system.md, etc.) fortfahren?
