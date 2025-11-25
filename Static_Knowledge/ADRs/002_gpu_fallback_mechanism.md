# ADR-002: GPU Fallback Mechanism

**Status**: Accepted
**Date**: 2025-01-22
**Decision Makers**: Development Team
**Related**: ADR-001 (Backend Selection Strategy)

---

## Context and Problem Statement

The Ablage-System relies on GPU-accelerated OCR backends (DeepSeek, GOT-OCR) for optimal performance. However, GPU resources are finite and subject to:
- Out-of-Memory (OOM) errors when VRAM is exhausted
- Hardware failures or driver issues
- Multi-user contention for GPU resources
- Development environments without GPU access

**Question**: How should the system handle GPU unavailability while maintaining service continuity?

---

## Decision Drivers

1. **Reliability**: System must process documents even when GPU fails
2. **User Experience**: Minimize impact on users (avoid complete failures)
3. **Performance**: GPU preferred, but CPU acceptable as fallback
4. **Transparency**: Users should know when degraded performance occurs
5. **Resource Efficiency**: Optimize GPU usage before resorting to CPU

---

## Considered Options

### Option 1: GPU-Only (No Fallback)
**Approach**: Fail immediately when GPU unavailable

**Pros**:
- Simple implementation
- Clear error messages
- No performance variance

**Cons**:
- ❌ Complete service outage on GPU failure
- ❌ Development requires GPU hardware
- ❌ Poor user experience during peak load

### Option 2: CPU-Only (No GPU)
**Approach**: Use CPU for all processing

**Pros**:
- Works everywhere
- Predictable performance
- No GPU complexity

**Cons**:
- ❌ 5-10x slower than GPU
- ❌ Underutilizes available hardware
- ❌ Higher operating costs (more CPU time)

### Option 3: Manual Fallback Selection
**Approach**: User chooses GPU or CPU

**Pros**:
- User control
- Transparent choice

**Cons**:
- ❌ Poor UX (users shouldn't need to know)
- ❌ Doesn't handle automatic failures
- ❌ Requires user knowledge of system state

### Option 4: Automatic GPU → CPU Cascade (CHOSEN)
**Approach**: Try GPU backends first, automatically fallback to CPU on failure

**Pros**:
- ✅ Optimal performance when GPU available
- ✅ Service continuity when GPU fails
- ✅ Transparent to users (with metadata flag)
- ✅ Works in dev environments without GPU

**Cons**:
- More complex implementation
- Performance variability
- Requires CPU backend maintenance

---

## Decision Outcome

**Chosen Option**: Automatic GPU → CPU Cascade (Option 4)

### Cascade Sequence

```
1. Try GPU Backend (DeepSeek or GOT-OCR)
   ├─ Success → Return result
   └─ Failure (OOM, unavailable)
       ↓
2. Reduce Batch Size (if OOM)
   ├─ Success → Return result
   └─ Still Failure
       ↓
3. Fallback to CPU Backend (Surya+Docling)
   ├─ Success → Return result with degraded flag
   └─ Failure → Permanent error
```

### Implementation Details

**OOM Detection and Recovery**:
```python
try:
    result = await gpu_backend.process(document_id)
except torch.cuda.OutOfMemoryError:
    logger.warning("gpu_oom_detected", document_id=document_id)

    # Clear cache and retry with smaller batch
    torch.cuda.empty_cache()
    result = await gpu_backend.process(document_id, batch_size=1)

    if still_fails:
        # Fallback to CPU
        result = await cpu_backend.process(document_id)
        result.metadata['fallback_used'] = True
```

**GPU Unavailable (Startup)**:
```python
import torch

if not torch.cuda.is_available():
    logger.warning("gpu_not_available_using_cpu_only")
    DEFAULT_BACKEND = "surya"  # CPU backend
else:
    DEFAULT_BACKEND = "auto"  # Smart selection
```

**Transparency**:
- Add `metadata.fallback_used` flag to results
- Log all fallback events with reason
- Include performance metrics (processing time)
- Notify monitoring system of degraded state

---

## Positive Consequences

- **High Availability**: Service continues even during GPU failures
- **Graceful Degradation**: Users get slower results instead of errors
- **Development Flexibility**: Developers can work without GPU
- **Cost Optimization**: GPU used when available, CPU when necessary
- **User Transparency**: Metadata indicates when fallback occurred

---

## Negative Consequences

- **Performance Variability**: 2-3 pages/sec (GPU) vs 1-2 pages/sec (CPU)
- **Complexity**: More code paths to test and maintain
- **Monitoring Overhead**: Need to track fallback rates
- **User Confusion**: Why are some documents slower?

---

## Mitigation Strategies

### 1. Performance Communication
```python
if result.metadata.get('fallback_used'):
    return {
        "result": result,
        "notice": "Verarbeitung mit CPU (GPU nicht verfügbar). "
                  "Bearbeitungszeit kann länger sein."
    }
```

### 2. Fallback Monitoring
Alert if fallback rate > 20% of requests:
```python
fallback_rate = fallback_count / total_requests
if fallback_rate > 0.2:
    alert_ops_team("High GPU fallback rate: {fallback_rate:.1%}")
```

### 3. Proactive GPU Management
Prevent OOM before it happens:
```python
gpu = GPUManager()
if gpu.get_memory_info()['free_gb'] < 3.0:
    logger.warning("low_vram_preemptive_cpu_fallback")
    use_cpu_backend = True
```

---

## Validation Metrics

**Success Criteria**:
- ✅ Fallback rate < 20% under normal operation
- ✅ No complete service outages due to GPU issues
- ✅ CPU processing completes successfully for all document types
- ✅ Fallback events logged and monitored

**Performance Targets**:
- GPU Processing: 2-3 pages/sec (95th percentile)
- CPU Fallback: 1-2 pages/sec (95th percentile)
- Fallback Detection: < 1 second
- Batch Size Reduction: Try at least 2 sizes before CPU fallback

---

## Related Decisions

- **ADR-001**: Backend Selection Strategy → Defines when to use each backend
- **Future ADR**: GPU Resource Scheduling → Multi-user GPU allocation

---

## References

- [app/gpu_manager.py](../../app/gpu_manager.py) - GPU availability checking
- [app/services/ocr_service.py](../../app/services/ocr_service.py) - Fallback implementation
- [Relations/Playbooks/error_response_playbook.yaml](../../Relations/Playbooks/error_response_playbook.yaml) - Error handling procedures
- [Static_Knowledge/SOPs/002_handling_gpu_oom_error.md](../SOPs/002_handling_gpu_oom_error.md) - OOM resolution steps

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2025-01-22 | 1.0 | Initial decision: Automatic GPU → CPU cascade |
