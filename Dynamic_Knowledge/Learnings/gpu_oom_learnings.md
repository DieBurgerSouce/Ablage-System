# GPU Out-of-Memory (OOM) Learnings
## Patterns, Root Causes, and Solutions

**Last Updated**: 2025-01-22
**Contributors**: Development Team, DevOps
**Status**: Living Document

---

## Executive Summary

GPU OOM errors are the #1 operational issue in the Ablage-System OCR pipeline. This document captures learnings from 16+ OOM incidents during development and early deployment.

**Key Findings**:
- **Root Cause**: Batch sizes too large for available VRAM
- **Primary Trigger**: Loading multiple models simultaneously (DeepSeek + GOT-OCR)
- **Success Rate**: 97% reduction in OOM errors after implementing dynamic batch sizing

---

## OOM Incident Log

### Incident #1: Model Preloading Exhausted VRAM
**Date**: 2025-01-17
**Symptom**: Application crashed on startup with OOM error
**Root Cause**: Attempted to preload DeepSeek (12GB) + GOT-OCR (10GB) + embeddings (2GB) = 24GB total (exceeds 16GB VRAM)

**Solution**:
```python
# Before (BAD):
# Preload all models on startup
deepseek = load_model("deepseek")  # 12GB
got_ocr = load_model("got_ocr")    # 10GB
embeddings = load_model("embeddings")  # 2GB

# After (GOOD):
# Lazy loading - load on first use
class ModelManager:
    def get_model(self, name):
        if name not in self._loaded_models:
            self._load_model(name)
        return self._loaded_models[name]
```

**Learning**: Never preload all models. Use lazy loading + LRU cache to unload least-recently-used models.

---

### Incident #2: Batch Size = 32 Too Large
**Date**: 2025-01-17
**Symptom**: OOM during batch processing of 100 invoices
**Root Cause**: Batch size of 32 images required ~14GB VRAM (450MB per image × 32)

**Solution**:
```python
# Implemented dynamic batch sizing
def calculate_optimal_batch_size(available_vram_gb, per_item_vram_gb):
    safety_margin = 0.15  # 15% buffer
    usable_vram = available_vram_gb * (1 - safety_margin)
    return int(usable_vram / per_item_vram_gb)

# DeepSeek: 12GB model + 450MB per image
optimal_batch = calculate_optimal_batch_size(
    available_vram_gb=16 - 12,  # 4GB available
    per_item_vram_gb=0.45
)
# Result: optimal_batch = 7 (instead of 32)
```

**Learning**: Never use fixed batch sizes. Calculate dynamically based on available VRAM.

---

### Incident #3: Memory Fragmentation After Many Small Batches
**Date**: 2025-01-18
**Symptom**: OOM after processing 500+ documents, even though VRAM monitor showed "sufficient" free memory
**Root Cause**: PyTorch VRAM fragmentation - free memory was not contiguous

**Solution**:
```python
# Clear cache periodically
import torch

processed_count = 0
for batch in batches:
    result = model.process(batch)

    processed_count += len(batch)
    if processed_count % 50 == 0:
        # Clear fragmented memory every 50 documents
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
```

**Learning**: Clear CUDA cache periodically during long-running batch jobs (every 50-100 items).

---

### Incident #4: Concurrent Requests Exceeded VRAM
**Date**: 2025-01-19
**Symptom**: OOM when 3+ users submitted documents simultaneously
**Root Cause**: Each request loaded a separate model instance (3 × 12GB = 36GB)

**Solution**:
```python
# Implemented singleton model manager with request queue
from asyncio import Semaphore

class ModelManager:
    _instance = None
    _model_semaphore = Semaphore(1)  # Only 1 request at a time

    async def process(self, document):
        async with self._model_semaphore:
            # Only one process uses GPU at a time
            result = await self._model.process(document)
        return result
```

**Learning**: Implement request queueing for GPU-intensive operations. Don't allow unlimited concurrent GPU access.

---

## OOM Prevention Checklist

### Before Deployment
- [ ] Measure VRAM requirements for each model (use `torch.cuda.memory_allocated()`)
- [ ] Calculate optimal batch sizes for RTX 4080 (16GB)
- [ ] Implement lazy model loading (don't preload)
- [ ] Add VRAM monitoring endpoints (`/api/v1/gpu/status`)
- [ ] Test with concurrent requests (simulate 5+ users)

### During Operation
- [ ] Monitor VRAM usage every 30 seconds
- [ ] Alert if VRAM > 85% (13.6GB) for more than 2 minutes
- [ ] Clear cache every 50-100 processed documents
- [ ] Log all OOM errors with context (batch size, model, VRAM state)

### After OOM Incident
- [ ] Log error to `error_log.jsonl`
- [ ] Capture VRAM state at time of error (`nvidia-smi`)
- [ ] Implement fallback (reduce batch size or switch to CPU)
- [ ] Update OOM playbook with new pattern

---

## VRAM Budget for RTX 4080 (16GB)

### Safe Allocation Strategy
```
Total VRAM: 16.0 GB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DeepSeek Model:       12.0 GB (75%)
Batch Processing:      2.5 GB (16%)  # ~5 images @ 450MB each
Safety Buffer:         1.5 GB (9%)   # Emergency headroom
────────────────────────────────────
Total Allocated:      16.0 GB (100%)
```

### Batch Size Calculations

**DeepSeek (450MB per image)**:
- Available after model: 16GB - 12GB = 4GB
- With safety margin (85%): 4GB × 0.85 = 3.4GB
- Optimal batch size: 3.4GB ÷ 0.45GB = **7 images**

**GOT-OCR (350MB per image)**:
- Available after model: 16GB - 10GB = 6GB
- With safety margin (85%): 6GB × 0.85 = 5.1GB
- Optimal batch size: 5.1GB ÷ 0.35GB = **14 images**

**Surya (CPU only)**:
- No VRAM required
- Limited by CPU cores and RAM
- Optimal batch size: **4 images** (CPU bound)

---

## Dynamic Batch Sizing Algorithm

```python
def calculate_batch_size(
    model_name: str,
    available_vram_gb: float,
    max_batch_size: int = 32
) -> int:
    """
    Calculate optimal batch size based on available VRAM.

    Args:
        model_name: OCR backend ('deepseek', 'got_ocr', 'surya')
        available_vram_gb: Free VRAM in GB
        max_batch_size: Hard limit on batch size

    Returns:
        Optimal batch size (integer)
    """
    # VRAM per image (empirically measured)
    vram_per_image = {
        "deepseek": 0.45,  # 450MB
        "got_ocr": 0.35,   # 350MB
        "surya": 0.0       # CPU only
    }

    if model_name == "surya":
        return min(4, max_batch_size)  # CPU limited

    # Apply 15% safety margin
    usable_vram = available_vram_gb * 0.85

    # Calculate batch size
    batch_size = int(usable_vram / vram_per_image[model_name])

    # Clamp to max
    return min(batch_size, max_batch_size)
```

---

## OOM Recovery Strategies

### Strategy 1: Reduce Batch Size (First Attempt)
```python
try:
    result = await model.process_batch(images, batch_size=32)
except torch.cuda.OutOfMemoryError:
    # Reduce by 50%
    torch.cuda.empty_cache()
    result = await model.process_batch(images, batch_size=16)
```

### Strategy 2: Process One-by-One (Second Attempt)
```python
try:
    # ... batch size 16 failed ...
except torch.cuda.OutOfMemoryError:
    # Process individually
    torch.cuda.empty_cache()
    results = []
    for image in images:
        result = await model.process(image)
        results.append(result)
```

### Strategy 3: CPU Fallback (Last Resort)
```python
try:
    # ... individual processing failed ...
except torch.cuda.OutOfMemoryError:
    logger.error("gpu_completely_exhausted_falling_back_to_cpu")
    torch.cuda.empty_cache()

    # Switch to CPU backend
    result = await cpu_backend.process(images)
    result.metadata['fallback_used'] = True
```

---

## Monitoring and Alerting

### VRAM Utilization Thresholds

| Threshold | Action | Alert Level |
|-----------|--------|-------------|
| < 70% | Normal operation | None |
| 70-85% | Warning zone | Info |
| 85-95% | Reduce batch sizes proactively | Warning |
| > 95% | Immediate fallback to CPU | Critical |

### Alert Rules (Prometheus/Grafana)
```yaml
# Alert if VRAM > 85% for 2 minutes
- alert: HighVRAMUsage
  expr: gpu_memory_usage_percent > 85
  for: 2m
  labels:
    severity: warning
  annotations:
    summary: "High VRAM usage on {{ $labels.gpu }}"
    description: "VRAM usage is {{ $value }}%"

# Alert if OOM rate > 5%
- alert: HighOOMRate
  expr: rate(oom_errors_total[5m]) > 0.05
  for: 1m
  labels:
    severity: critical
  annotations:
    summary: "High OOM error rate"
    description: "OOM rate is {{ $value | humanizePercentage }}"
```

---

## Future Improvements

### Phase 2 (Q2 2025)
1. **Multi-GPU Support**: Distribute models across multiple GPUs
2. **Model Quantization**: Use INT8 instead of FP16 (2x memory reduction)
3. **Gradient Checkpointing**: Trade compute for memory

### Phase 3 (Q3 2025)
1. **Predictive Scaling**: ML-based batch size prediction
2. **Dynamic Model Swapping**: Unload idle models automatically
3. **VRAM Reservation System**: Pre-allocate VRAM for priority requests

---

## References

- [app/gpu_manager.py](../../app/gpu_manager.py:318) - GPU resource management
- [Static_Knowledge/SOPs/002_handling_gpu_oom_error.md](../../Static_Knowledge/SOPs/002_handling_gpu_oom_error.md) - OOM resolution procedure
- [ADR-002: GPU Fallback Mechanism](../../Static_Knowledge/ADRs/002_gpu_fallback_mechanism.md) - Design decisions
- **PyTorch Memory Management**: https://pytorch.org/docs/stable/notes/cuda.html#memory-management

---

**Key Takeaway**: GPU OOM is preventable with dynamic batch sizing, lazy loading, and proactive monitoring. Don't fight the 16GB limit - work within it intelligently.
