# OCR Processing - Map of Content

**Category**: Technical Overview
**Last Updated**: 2025-11-22
**Status**: Active
**Maintainer**: Backend Team

## Overview

Complete map of content for OCR (Optical Character Recognition) processing in the Ablage-System. This MOC connects all resources, documentation, and code related to document OCR.

## 📋 Quick Reference

- **Primary Backend**: DeepSeek-Janus-Pro (multimodal, best accuracy)
- **Secondary Backend**: GOT-OCR 2.0 (transformer, best speed)
- **Fallback Backend**: Surya + Docling (CPU-based, layout-aware)
- **Processing Time**: < 2s per page (GPU), < 10s (CPU)
- **Accuracy Target**: > 95% (German text with umlauts)

---

## 🏗️ Architecture

### High-Level Flow

```
Document Upload
    ↓
Validation & Virus Scan
    ↓
Classification (Rechnung/Vertrag/Brief/etc.)
    ↓
Backend Selection (auto or manual)
    ↓
GPU Resource Check
    ↓
Celery Task Queue
    ↓
OCR Processing (DeepSeek/GOT-OCR/Surya)
    ↓
Post-Processing (German text normalization, spell-check)
    ↓
Entity Extraction (invoice data, company names, dates)
    ↓
Storage (PostgreSQL + MinIO)
    ↓
Cache Results (Redis)
    ↓
Webhook Notification
```

### Components

**API Layer** → [app/api/v1/ocr.py](../../app/api/v1/ocr.py)
- REST endpoints for OCR operations
- Status polling
- Webhook configuration

**Orchestration** → [Relations/Workflows/ocr_backend_selection_workflow.yaml](../../Relations/Workflows/ocr_backend_selection_workflow.yaml)
- Intelligent backend selection
- Document complexity analysis
- GPU availability check

**Processing** → [app/services/ocr/](../../app/services/ocr/)
- `deepseek.py` - DeepSeek-Janus-Pro integration
- `got_ocr.py` - GOT-OCR 2.0 integration
- `surya_docling.py` - Surya + Docling pipeline
- `orchestrator.py` - Backend coordination

**Task Queue** → [app/workers/ocr_tasks.py](../../app/workers/ocr_tasks.py)
- Celery async tasks
- Retry logic
- Error handling

**GPU Management** → [Static_Knowledge/Skills/gpu_management_skill.yaml](../../Static_Knowledge/Skills/gpu_management_skill.yaml)
- VRAM monitoring
- Dynamic batch sizing
- Model loading/unloading

---

## 🎯 OCR Backends

### 1. DeepSeek-Janus-Pro

**When to Use:**
- Complex layouts (tables + images)
- Fraktur fonts (historical German documents)
- High accuracy requirements
- Multimodal content

**Specifications:**
- Model Size: 1.3B parameters
- VRAM Required: 12 GB base + 1.5 GB per page
- Speed: ~2-3 pages/second
- Languages: German (primary), English, multilingual

**Documentation:**
- [Skills/ocr_backends_skill.yaml](../../Static_Knowledge/Skills/ocr_backends_skill.yaml#deepseek)
- [Execution_Layer/Agents/document_classifier_agent.py](../../Execution_Layer/Agents/document_classifier_agent.py)

**Configuration:**
```python
DEEPSEEK_CONFIG = {
    "model_name": "deepseek-janus-pro-1.3b",
    "device": "cuda",
    "batch_size": 8,  # Dynamic based on VRAM
    "fp16": True,      # Mixed precision for memory efficiency
    "max_length": 2048
}
```

### 2. GOT-OCR 2.0

**When to Use:**
- Simple to medium complexity documents
- Speed priority over maximum accuracy
- Standard business documents (invoices, letters)
- High throughput processing

**Specifications:**
- Model Size: 600M parameters
- VRAM Required: 10 GB base + 0.8 GB per page
- Speed: ~5-7 pages/second
- Languages: German, English, multilingual

**Documentation:**
- [Skills/ocr_backends_skill.yaml](../../Static_Knowledge/Skills/ocr_backends_skill.yaml#got_ocr)
- [Bookmarks/development_tools.yaml](../../Dynamic_Knowledge/Bookmarks/development_tools.yaml) (GitHub repo)

**Configuration:**
```python
GOT_OCR_CONFIG = {
    "model_name": "got-ocr-2.0-600m",
    "device": "cuda",
    "batch_size": 16,
    "fp16": True,
    "language": "de"
}
```

### 3. Surya + Docling

**When to Use:**
- GPU unavailable (CPU fallback)
- Layout analysis priority
- Structured document parsing
- Long documents (100+ pages)

**Specifications:**
- Model Size: CPU-optimized
- VRAM Required: 0 GB (CPU-only)
- Speed: ~1-2 pages/second
- Languages: German, multilingual

**Documentation:**
- [Skills/ocr_backends_skill.yaml](../../Static_Knowledge/Skills/ocr_backends_skill.yaml#surya)
- [Bookmarks/development_tools.yaml](../../Dynamic_Knowledge/Bookmarks/development_tools.yaml) (GitHub repos)

**Configuration:**
```python
SURYA_CONFIG = {
    "device": "cpu",
    "batch_size": 4,
    "enable_layout_analysis": True,
    "language": "de"
}
```

---

## 📊 Performance Optimization

### Database Optimization
→ [Relations/Playbooks/database_performance_playbook.yaml](../../Relations/Playbooks/database_performance_playbook.yaml)

- Index on `documents(user_id, created_at)`
- Materialized view for user stats
- Connection pooling (20 base, 40 overflow)

### Caching Strategy
→ [Relations/Decision_Trees/cache_invalidation_tree.yaml](../../Relations/Decision_Trees/cache_invalidation_tree.yaml)

- OCR results cached for 1 hour (`ocr_result:{doc_id}`)
- Document metadata cached for 30 minutes
- User stats cached for 5 minutes
- Invalidation on document update/delete

### GPU Optimization
→ [Static_Knowledge/Prompts/optimization_prompts.yaml](../../Static_Knowledge/Prompts/optimization_prompts.yaml#gpu_optimization)

- Dynamic batch sizing (based on available VRAM)
- Lazy model loading (load on first use)
- CUDA cache clearing on high memory
- Mixed precision (FP16) for 2x memory savings

---

## 🇩🇪 German Language Processing

### Text Normalization
→ [app/utils/german_text.py](../../app/utils/german_text.py)

```python
from app.utils.german_text import normalize_german_text

text = normalize_german_text(ocr_output)
# - NFC Unicode normalization
# - Fraktur character mapping
# - ß (eszett) handling
```

### Validation
→ [Execution_Layer/Validators/german_text_validator.py](../../Execution_Layer/Validators/german_text_validator.py)

- Umlaut accuracy check (target: 100%)
- Business term validation (§14 UStG, Rechnungsnummer, etc.)
- Date format validation (DD.MM.YYYY)
- Currency format (1.234,56 €)

### Entity Extraction
→ [Execution_Layer/Sub_Agents/invoice_data_extractor.py](../../Execution_Layer/Sub_Agents/invoice_data_extractor.py)

**Extracted Fields:**
- Rechnungsnummer (Invoice Number)
- Rechnungsdatum (Invoice Date)
- USt-IdNr. (VAT ID)
- Steuernummer (Tax Number)
- Netto/Brutto/MwSt (Net/Gross/VAT)
- IBAN, BIC
- Company names and addresses

---

## 🔄 Workflows

### Standard Processing Flow

1. **Upload** → [Relations/Hooks/document_processing_hooks.yaml](../../Relations/Hooks/document_processing_hooks.yaml#on_upload)
   - Virus scan (ClamAV)
   - Validation (file type, size)
   - Metadata extraction
   - Queue for OCR

2. **Classification** → [Execution_Layer/Agents/document_classifier_agent.py](../../Execution_Layer/Agents/document_classifier_agent.py)
   - Pattern matching (keywords)
   - ML classification (transformer model)
   - Categories: Rechnung, Vertrag, Brief, etc.

3. **Backend Selection** → [Relations/Workflows/ocr_backend_selection_workflow.yaml](../../Relations/Workflows/ocr_backend_selection_workflow.yaml)
   - Analyze document complexity
   - Check GPU availability
   - Apply selection rules
   - Validate backend readiness

4. **OCR Processing** → [Relations/Hooks/document_processing_hooks.yaml](../../Relations/Hooks/document_processing_hooks.yaml#on_processing_started)
   - Load OCR model
   - Process with selected backend
   - Track GPU memory usage
   - Fallback on error

5. **Post-Processing** → [Relations/Hooks/document_processing_hooks.yaml](../../Relations/Hooks/document_processing_hooks.yaml#on_processing_completed)
   - Normalize German text
   - Validate umlaut accuracy
   - Extract business entities
   - Cache results

6. **Completion** → [Relations/Hooks/document_processing_hooks.yaml](../../Relations/Hooks/document_processing_hooks.yaml#on_processing_completed)
   - Update database
   - Send webhooks
   - Update quota
   - Log metrics

### Error Handling Flow

→ [Relations/Hooks/document_processing_hooks.yaml](../../Relations/Hooks/document_processing_hooks.yaml#on_processing_failed)

1. Log error with context
2. Attempt fallback backend
3. Retry up to 3 times
4. Notify user if all retries fail
5. Send webhook notification

---

## 🧪 Testing

### Unit Tests
```bash
pytest tests/unit/services/test_ocr_service.py -v
```

### Integration Tests
```bash
pytest tests/integration/test_ocr_pipeline.py -v
```

### GPU Tests
```bash
pytest tests/gpu/test_ocr_gpu.py -m gpu -v
```

### Batch Processing
→ [Execution_Layer/Runners/batch_ocr_runner.py](../../Execution_Layer/Runners/batch_ocr_runner.py)

```bash
python Execution_Layer/Runners/batch_ocr_runner.py \
  /path/to/documents/ \
  --backend deepseek \
  --max-concurrent 10 \
  --recursive
```

---

## 📈 Monitoring

### Metrics
→ [Static_Knowledge/Skills/monitoring_observability_skill.yaml](../../Static_Knowledge/Skills/monitoring_observability_skill.yaml)

**Prometheus Metrics:**
- `ocr_requests_total` - Total OCR requests (by backend, status)
- `ocr_processing_duration_seconds` - Processing time histogram
- `ocr_backend_selections_total` - Backend selection counts
- `gpu_memory_usage_bytes` - Current GPU VRAM usage
- `ocr_confidence_score` - OCR confidence scores

**Grafana Dashboards:**
- OCR Processing Overview
- GPU Resource Utilization
- Backend Performance Comparison
- Error Rate Tracking

### Logging
→ [app/core/logging.py](../../app/core/logging.py)

```python
logger.info(
    "ocr_processing_completed",
    document_id=doc_id,
    backend="deepseek",
    processing_time_seconds=2.34,
    confidence=0.97,
    page_count=3,
    gpu_memory_gb=12.5
)
```

---

## 🚨 Troubleshooting

### Common Issues

**1. GPU Out of Memory (OOM)**
→ [Relations/Playbooks/gpu_troubleshooting_playbook.yaml](../../Relations/Playbooks/gpu_troubleshooting_playbook.yaml)

**Symptoms:**
- `torch.cuda.OutOfMemoryError`
- Processing fails midway

**Solutions:**
1. Reduce batch size: Edit `DEEPSEEK_CONFIG["batch_size"]`
2. Clear CUDA cache: `torch.cuda.empty_cache()`
3. Fallback to CPU: Use Surya backend
4. Restart worker: `systemctl restart ablage-worker`

**2. Low OCR Accuracy**
→ [Dynamic_Knowledge/Learnings/ocr_accuracy_improvement.md](../../Dynamic_Knowledge/Learnings/ocr_accuracy_improvement.md)

**Symptoms:**
- Confidence score < 0.80
- Many umlaut errors

**Solutions:**
1. Check image DPI (minimum 150, recommended 300)
2. Use DeepSeek for complex documents
3. Verify German text normalization is applied
4. Check for PDF corruption

**3. Slow Processing**
→ [Static_Knowledge/Prompts/optimization_prompts.yaml](../../Static_Knowledge/Prompts/optimization_prompts.yaml)

**Symptoms:**
- Processing time > 10s per page
- Queue backup

**Solutions:**
1. Switch to faster backend (GOT-OCR)
2. Increase Celery workers
3. Enable GPU batch processing
4. Check database query performance

---

## 📚 Learning Resources

### Internal Documentation
- [ADR-002: OCR Backend Selection Strategy](../../Static_Knowledge/ADRs/002_ocr_backend_selection.md)
- [Skills: OCR Backends](../../Static_Knowledge/Skills/ocr_backends_skill.yaml)
- [Skills: GPU Management](../../Static_Knowledge/Skills/gpu_management_skill.yaml)
- [Learnings: OCR Optimization](../../Dynamic_Knowledge/Learnings/ocr_accuracy_improvement.md)

### External Resources
→ [Dynamic_Knowledge/Bookmarks/development_tools.yaml](../../Dynamic_Knowledge/Bookmarks/development_tools.yaml)

- **DeepSeek**: (Model documentation)
- **GOT-OCR 2.0**: https://github.com/ucaslcl/GOT-OCR2.0
- **Surya**: https://github.com/VikParuchuri/surya
- **Docling**: https://github.com/DS4SD/docling
- **PyTorch CUDA**: https://pytorch.org/docs/stable/notes/cuda.html

---

## 🔗 Related MOCs

- [DEVELOPMENT_MOC.md](DEVELOPMENT_MOC.md) - Overall development guide
- [SECURITY_MOC.md](SECURITY_MOC.md) - Security best practices
- [INFRASTRUCTURE_MOC.md](INFRASTRUCTURE_MOC.md) - Infrastructure setup

---

## 🎯 Quick Commands

```bash
# Start OCR worker
celery -A app.celery worker --loglevel=info --concurrency=1 --pool=solo

# Monitor GPU usage
watch -n 1 nvidia-smi

# Check OCR queue length
redis-cli LLEN celery

# Process single document (API)
curl -X POST http://localhost:8000/api/v1/ocr/process \
  -H "Content-Type: application/json" \
  -d '{"document_id": "doc_123", "backend": "deepseek"}'

# Batch process documents
python Execution_Layer/Runners/batch_ocr_runner.py /path/to/docs/ --recursive
```

---

**Last Updated**: 2025-11-22
**Contributors**: Backend Team, ML Team
**Questions?** See [DEVELOPMENT_MOC.md](DEVELOPMENT_MOC.md) or ask in #ablage-dev
