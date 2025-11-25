# SOP-002: Handling GPU Out of Memory (OOM) Errors

**ID**: SOP-002
**Category**: Operations / Troubleshooting
**Difficulty**: Medium
**Estimated Time**: 5-15 minutes
**Priority**: High (Production Issue)
**Related ADRs**: ADR-001 (Backend Selection), ADR-002 (GPU Fallback)

---

## Overview

This SOP guides you through diagnosing and resolving GPU Out of Memory (OOM) errors in the Ablage-System OCR pipeline. OOM errors occur when VRAM usage exceeds 16GB (RTX 4080).

**Common Symptoms**:
- `torch.cuda.OutOfMemoryError: CUDA out of memory`
- Processing failures after several successful documents
- Degraded performance (system switching to CPU)
- Error logs showing VRAM >85%

---

## Prerequisites

- Access to server with GPU
- Admin/sudo access for system monitoring
- Basic knowledge of NVIDIA tools

---

## Quick Diagnosis

### Step 1: Check Current GPU Status

```bash
# Check GPU memory usage
nvidia-smi

# Expected output:
# +-----------------------------------------------------------------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |===============================+======================+======================|
# |   0  NVIDIA GeForce RTX 4080  On   | 00000000:01:00.0 Off |                  N/A |
# | 45%   65C    P2   250W / 320W |  14500MiB / 16384MiB |     95%      Default |
# +-----------------------------------------------------------------------------+
```

**Interpretation**:
- ✅ **Memory < 13.6GB (85%)**: Healthy
- ⚠️ **Memory 13.6-15.5GB**: Approaching limit
- 🔴 **Memory >15.5GB**: OOM imminent

---

### Step 2: Check System Logs

```bash
# Check recent OOM errors
curl -s http://localhost:8000/ocr/stats | python -m json.tool | grep -A 5 "errors"

# Check application logs
tail -n 50 Dynamic_Knowledge/Logs/error_logs/$(date +%Y-%m-%d)_errors.md
```

**Look For**:
- Number of OOM errors in last hour
- Which backend caused OOM
- Batch sizes being processed

---

## Resolution Procedures

### Procedure A: Immediate OOM Recovery (Production)

**When to Use**: Active OOM error, processing halted

**Steps**:

1. **Clear GPU Cache Immediately**
   ```bash
   # Via API
   curl -X POST http://localhost:8000/gpu/clear-cache

   # Or via Python console
   python -c "import torch; torch.cuda.empty_cache(); print('Cache cleared')"
   ```

2. **Verify Memory Released**
   ```bash
   nvidia-smi | grep "Memory-Usage"
   # Should see reduced usage
   ```

3. **Check System Status**
   ```bash
   curl -s http://localhost:8000/health | python -m json.tool
   ```

4. **Retry Failed Document**
   ```bash
   # System will automatically use smaller backend or CPU
   curl -X POST http://localhost:8000/ocr/process \
     -F "file=@path/to/failed_document.pdf"
   ```

**Expected Outcome**: Processing resumes with CPU or smaller backend

---

### Procedure B: Prevent Future OOMs (Configuration)

**When to Use**: Recurring OOM errors

**Steps**:

1. **Analyze OOM Patterns**
   ```bash
   # Get error statistics
   curl -s http://localhost:8000/ocr/stats | python -m json.tool
   ```

   Look for:
   - Which backend causes most OOMs? (DeepSeek likely)
   - Average document size when OOM occurs
   - Batch size settings

2. **Adjust Batch Sizes**

   Edit `Static_Knowledge/Skills/skills_config.yaml`:

   ```yaml
   backends:
     deepseek:
       batch_size_max: 16  # Reduce from 32
       batch_size_optimal: 8
       vram_safety_margin_gb: 2.0  # Increase margin
   ```

3. **Lower VRAM Threshold**

   Edit `app/gpu_manager.py`:

   ```python
   # Change from 85% to 80%
   VRAM_SAFE_THRESHOLD = 0.80  # 80% of 16GB = 12.8GB
   ```

4. **Restart Services**
   ```bash
   # Kill old server
   pkill -f "uvicorn app.main:app"

   # Start with new config
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

5. **Verify Configuration**
   ```bash
   curl -s http://localhost:8000/ocr/backends | python -m json.tool
   # Check updated batch sizes
   ```

---

### Procedure C: Optimize Document Processing

**When to Use**: OOMs with specific document types

**Steps**:

1. **Identify Problem Documents**
   ```bash
   # Check logs for document patterns
   grep "OOM" Dynamic_Knowledge/Logs/error_logs/*.md | \
     grep -o "filename: [^,]*" | sort | uniq -c | sort -rn
   ```

2. **Adjust Routing Rules**

   If invoices cause OOMs, route to GOT-OCR instead:

   ```yaml
   # skills_config.yaml
   routing_rules:
     rechnung:
       primary: "got_ocr"  # Changed from deepseek
       fallback: ["surya"]
   ```

3. **Test with Sample Documents**
   ```bash
   # Process test invoice
   curl -X POST http://localhost:8000/ocr/process \
     -F "file=@tests/fixtures/large_invoice.pdf" \
     -F "backend=got_ocr"
   ```

4. **Monitor VRAM During Processing**
   ```bash
   # Run in separate terminal
   watch -n 1 nvidia-smi
   ```

---

## Advanced Troubleshooting

### Issue: OOMs During Batch Processing

**Symptoms**: First few documents process fine, then OOM

**Root Cause**: VRAM fragmentation or incomplete cleanup

**Solution**:

```python
# Add to batch processing loop
for batch in batches:
    try:
        results = process_batch(batch)
    finally:
        # Force cleanup after each batch
        import gc
        gc.collect()
        torch.cuda.empty_cache()
```

---

### Issue: OOMs with Small Documents

**Symptoms**: Even small PDFs cause OOM

**Root Cause**: Memory leak or residual allocations

**Solution**:

1. **Check for Memory Leaks**
   ```python
   # Add GPU memory tracking
   from app.gpu_manager import GPUManager

   gpu = GPUManager()
   gpu.start_allocation_tracking()

   # Process document
   result = ocr.process(document)

   # Check allocations
   leaks = gpu.get_allocation_history()
   print(f"Unfreed allocations: {leaks}")
   ```

2. **Restart Service**
   ```bash
   # Temporary fix: restart clears all memory
   systemctl restart ablage-ocr
   ```

3. **Investigate Leak Source**
   - Check backend wrappers for unclosed resources
   - Verify model `eval()` mode (no gradients stored)
   - Ensure temporary tensors are deleted

---

### Issue: Competing GPU Processes

**Symptoms**: Available VRAM fluctuates

**Root Cause**: Other processes using GPU

**Solution**:

1. **Identify GPU Processes**
   ```bash
   nvidia-smi --query-compute-apps=pid,used_memory --format=csv
   ```

2. **Kill Competing Processes** (if safe)
   ```bash
   # Example: Kill old Python process
   kill -9 <PID>
   ```

3. **Reserve GPU for OCR**
   ```bash
   # Set CUDA_VISIBLE_DEVICES to dedicated GPU
   export CUDA_VISIBLE_DEVICES=0
   ```

---

## Prevention Strategies

### Strategy 1: Pre-Processing Document Size Check

```python
def safe_process(document_path):
    """Check document size before processing"""
    file_size_mb = os.path.getsize(document_path) / 1024 / 1024

    # Large documents → CPU directly
    if file_size_mb > 50:
        return surya_backend.process(document_path)

    # Normal flow
    return backend_manager.auto_select(document_path)
```

### Strategy 2: Dynamic Batch Sizing

```python
def calculate_safe_batch_size(available_vram_gb):
    """Dynamically adjust batch size based on VRAM"""
    # Rule: ~500MB per document for DeepSeek
    safe_batch = int(available_vram_gb * 0.7 / 0.5)
    return min(safe_batch, 32)  # Cap at 32
```

### Strategy 3: Automatic Fallback Chain

```python
def process_with_fallback(document):
    """Automatic fallback on OOM"""
    backends_to_try = ["deepseek", "got_ocr", "surya"]

    for backend in backends_to_try:
        try:
            return process_with_backend(backend, document)
        except torch.cuda.OutOfMemoryError:
            logger.warning(f"{backend} OOM, trying next...")
            torch.cuda.empty_cache()

    raise ProcessingError("All backends failed")
```

---

## Monitoring Setup

### Set Up VRAM Alerts

```yaml
# prometheus_alerts.yaml
groups:
  - name: gpu_alerts
    rules:
      - alert: HighVRAMUsage
        expr: gpu_memory_usage_percent > 85
        for: 2m
        annotations:
          summary: "GPU VRAM usage critical"
          description: "VRAM {{ $value }}% (>85%)"

      - alert: FrequentOOM
        expr: rate(ocr_oom_errors[5m]) > 0.1
        annotations:
          summary: "Frequent OOM errors detected"
```

### Dashboard Metrics

Track these metrics in Grafana:

```python
metrics_to_track = {
    "vram_usage_gb": "Current VRAM usage",
    "vram_peak_gb": "Peak VRAM in last hour",
    "oom_count": "Number of OOM errors",
    "fallback_rate": "% of requests using CPU fallback",
    "avg_batch_size": "Average batch size processed"
}
```

---

## Rollback Procedures

### If Configuration Changes Make it Worse

1. **Restore Previous Config**
   ```bash
   git checkout HEAD~1 Static_Knowledge/Skills/skills_config.yaml
   ```

2. **Restart Service**
   ```bash
   systemctl restart ablage-ocr
   ```

3. **Verify Rollback**
   ```bash
   curl -s http://localhost:8000/health
   ```

---

## Testing & Validation

### Test OOM Recovery

```bash
# 1. Force OOM by processing huge document
curl -X POST http://localhost:8000/ocr/process \
  -F "file=@tests/fixtures/massive_document.pdf" \
  -F "backend=deepseek"

# Expected: OOM occurs, falls back to GOT-OCR or Surya

# 2. Verify recovery
curl -s http://localhost:8000/health | grep "status"
# Expected: "status": "healthy"

# 3. Check fallback worked
curl -s http://localhost:8000/ocr/stats
# Expected: fallback_triggers > 0
```

---

## Escalation

### When to Escalate

Escalate to DevOps if:
- ❌ OOM errors >10 per hour (sustained)
- ❌ CPU fallback rate >50%
- ❌ Memory leak suspected (VRAM doesn't decrease)
- ❌ GPU hardware failure suspected

### Escalation Information to Provide

```bash
# Collect diagnostics
cat > oom_report.txt << EOF
Date: $(date)
nvidia-smi output:
$(nvidia-smi)

OOM Statistics:
$(curl -s http://localhost:8000/ocr/stats)

Recent Errors:
$(tail -n 100 Dynamic_Knowledge/Logs/error_logs/$(date +%Y-%m-%d)_errors.md)

Configuration:
$(cat Static_Knowledge/Skills/skills_config.yaml)
EOF

# Send to ops team
```

---

## Success Criteria

✅ **OOM Resolved When**:
- VRAM usage stable <85%
- OOM error rate <1 per hour
- Processing continues without manual intervention
- CPU fallback working correctly
- No memory leaks detected

---

## Related Documentation

- **ADR-001**: Backend Selection Strategy
- **ADR-002**: GPU Fallback Mechanism
- **SOP-001**: Installing OCR Backend
- **Playbook**: `Relations/Playbooks/error_response_playbook.yaml`
- **Learning**: `Dynamic_Knowledge/Learnings/errors_and_fixes/gpu_oom_patterns.md`

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2024-11-22 | Ops Team | Initial SOP |

---

**Last Tested**: 2024-11-22
**Next Review**: 2024-12-22
**Status**: Active
