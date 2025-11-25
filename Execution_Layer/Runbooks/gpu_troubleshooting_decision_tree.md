# GPU Troubleshooting Decision Tree
**Ablage-System - GPU-Fehlerdiagnose und -Behebung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team + Performance Engineering
Severity: CRITICAL

---

## Quick Reference

| Symptom | Likely Cause | Page |
|---------|--------------|------|
| GPU not detected | Driver/CUDA issue | [Section 1](#1-gpu-not-detected) |
| OOM errors | Memory leak/large batch | [Section 2](#2-out-of-memory-errors) |
| Slow processing | Thermal throttling/config | [Section 3](#3-performance-degradation) |
| CUDA errors | Version mismatch | [Section 4](#4-cuda-runtime-errors) |
| Stuck processes | Zombie GPU processes | [Section 5](#5-stuck-gpu-processes) |
| High idle memory | Memory not released | [Section 6](#6-high-idle-gpu-memory) |

---

## Decision Tree Overview

```
GPU Issue Detected
    │
    ├─→ GPU Not Detected? ───→ [Section 1: Detection Issues]
    │
    ├─→ OOM Errors? ──────────→ [Section 2: Memory Management]
    │
    ├─→ Slow Processing? ─────→ [Section 3: Performance Issues]
    │
    ├─→ CUDA Errors? ─────────→ [Section 4: Runtime Errors]
    │
    ├─→ Stuck Processes? ─────→ [Section 5: Process Management]
    │
    └─→ High Idle Memory? ────→ [Section 6: Memory Leaks]
```

---

## 1. GPU Not Detected

### Symptoms
- `torch.cuda.is_available()` returns `False`
- Health check shows `"gpu": false`
- API falls back to CPU processing
- No GPU listed in `nvidia-smi`

### Decision Flow

```
START: GPU not detected
    │
    ├─→ Q1: Does nvidia-smi work on host?
    │   ├─→ YES → Go to Q2
    │   └─→ NO  → [Fix: Reinstall NVIDIA drivers] → Go to Solution 1.1
    │
    ├─→ Q2: Is Docker running with --gpus flag?
    │   ├─→ YES → Go to Q3
    │   └─→ NO  → [Fix: Update docker-compose.yml] → Go to Solution 1.2
    │
    ├─→ Q3: Is NVIDIA Container Toolkit installed?
    │   ├─→ YES → Go to Q4
    │   └─→ NO  → [Fix: Install toolkit] → Go to Solution 1.3
    │
    └─→ Q4: Is CUDA version compatible?
        ├─→ YES → [Advanced troubleshooting] → Go to Solution 1.4
        └─→ NO  → [Fix: Update CUDA/PyTorch] → Go to Solution 1.5
```

### Solution 1.1: Reinstall NVIDIA Drivers

**Diagnosis:**
```bash
# Check if drivers loaded
lsmod | grep nvidia

# Check driver version
nvidia-smi

# If command not found or no output, drivers not installed
```

**Fix:**
```bash
# Ubuntu 22.04 - Install recommended driver
sudo ubuntu-drivers devices
sudo ubuntu-drivers autoinstall

# Or install specific version
sudo apt install nvidia-driver-535

# Reboot required
sudo reboot

# Verify after reboot
nvidia-smi
```

**Verification:**
```bash
# Should show GPU details
nvidia-smi --query-gpu=name,driver_version,cuda_version --format=csv

# Expected output:
# RTX 4080, 535.154.05, 12.2
```

**⏱️ Time to Resolve:** 15-30 minutes (including reboot)
**🔄 Requires Downtime:** YES (system reboot)

---

### Solution 1.2: Fix Docker GPU Access

**Diagnosis:**
```bash
# Check docker-compose.yml has GPU configuration
grep -A 5 "deploy:" docker-compose.yml

# Should contain:
#   deploy:
#     resources:
#       reservations:
#         devices:
#           - driver: nvidia
#             count: 1
#             capabilities: [gpu]
```

**Fix:**
```yaml
# Edit docker-compose.yml
# backend and worker services need:

services:
  backend:
    # ... other config ...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  worker:
    # ... other config ...
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

**Apply Fix:**
```bash
# Restart services with new config
docker-compose down
docker-compose up -d

# Verify GPU access in container
docker exec ablage-backend nvidia-smi
```

**⏱️ Time to Resolve:** 2-5 minutes
**🔄 Requires Downtime:** YES (service restart)

---

### Solution 1.3: Install NVIDIA Container Toolkit

**Diagnosis:**
```bash
# Check if toolkit installed
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi

# If error: "could not select device driver", toolkit not installed
```

**Fix:**
```bash
# Add NVIDIA package repository
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# Install toolkit
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# Restart Docker daemon
sudo systemctl restart docker

# Verify
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

**⏱️ Time to Resolve:** 5-10 minutes
**🔄 Requires Downtime:** YES (Docker restart affects all containers)

---

### Solution 1.4: Advanced Detection Troubleshooting

**Check PyTorch CUDA Build:**
```python
# Run inside container
docker exec -it ablage-backend python -c "
import torch
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version (built): {torch.version.cuda}')
if torch.cuda.is_available():
    print(f'GPU name: {torch.cuda.get_device_name(0)}')
    print(f'GPU count: {torch.cuda.device_count()}')
"
```

**Common Issues:**
- **PyTorch built for wrong CUDA version:** Reinstall PyTorch with correct CUDA
- **Environment variable issues:** Check `CUDA_VISIBLE_DEVICES`
- **Permissions:** Container user may not have GPU access

**Fix Environment Variables:**
```bash
# Check environment in container
docker exec ablage-backend env | grep CUDA

# Add to docker-compose.yml if missing:
environment:
  - CUDA_VISIBLE_DEVICES=0
  - NVIDIA_VISIBLE_DEVICES=all
  - NVIDIA_DRIVER_CAPABILITIES=compute,utility
```

**⏱️ Time to Resolve:** 10-20 minutes
**🔄 Requires Downtime:** Depends on fix

---

### Solution 1.5: CUDA/PyTorch Version Mismatch

**Diagnosis:**
```bash
# Check CUDA version on host
nvidia-smi | grep "CUDA Version"

# Check PyTorch CUDA version
docker exec ablage-backend python -c "import torch; print(torch.version.cuda)"

# They must be compatible (PyTorch CUDA <= Host CUDA)
```

**Compatibility Matrix:**
| PyTorch | CUDA 11.8 | CUDA 12.1 | CUDA 12.2 |
|---------|-----------|-----------|-----------|
| 2.0.x   | ✅        | ✅        | ✅        |
| 2.1.x   | ✅        | ✅        | ✅        |
| 2.2.x   | ❌        | ✅        | ✅        |

**Fix:**
```dockerfile
# Update Dockerfile to use correct PyTorch version
# For CUDA 12.2:
RUN pip install torch==2.2.0+cu122 -f https://download.pytorch.org/whl/torch_stable.html

# Rebuild container
docker-compose build backend worker
docker-compose up -d backend worker
```

**⏱️ Time to Resolve:** 10-15 minutes (rebuild time)
**🔄 Requires Downtime:** YES (container rebuild)

---

## 2. Out of Memory (OOM) Errors

### Symptoms
- `torch.cuda.OutOfMemoryError`
- Processing stops mid-batch
- GPU memory climbs to 100%
- Documents fail with "GPU memory exhausted"

### Decision Flow

```
START: OOM Error Detected
    │
    ├─→ Q1: Does nvidia-smi show high memory usage?
    │   ├─→ YES → Go to Q2
    │   └─→ NO  → [Different issue] → Check application logs
    │
    ├─→ Q2: Is this during batch processing?
    │   ├─→ YES → [Fix: Reduce batch size] → Go to Solution 2.1
    │   └─→ NO  → Go to Q3
    │
    ├─→ Q3: Are there multiple models loaded?
    │   ├─→ YES → [Fix: Model unloading] → Go to Solution 2.2
    │   └─→ NO  → Go to Q4
    │
    └─→ Q4: Is memory increasing over time?
        ├─→ YES → [Memory leak] → Go to Solution 2.3
        └─→ NO  → [Undersized GPU] → Go to Solution 2.4
```

### Solution 2.1: Reduce Batch Size

**Diagnosis:**
```bash
# Check current batch configuration
docker exec ablage-backend cat /app/config/ocr_config.yaml | grep batch_size

# Monitor memory during processing
watch -n 1 'nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader'
```

**Fix - Dynamic Batch Sizing:**
```python
# Update app/services/ocr/batch_processor.py
class GPUBatchProcessor:
    def _calculate_optimal_batch_size(self, document_complexity: str) -> int:
        """Calculate batch size based on available VRAM."""
        import torch

        if not torch.cuda.is_available():
            return 1

        # Get available memory (GB)
        total_mem = torch.cuda.get_device_properties(0).total_memory / 1024**3
        used_mem = torch.cuda.memory_allocated() / 1024**3
        available_mem = total_mem - used_mem

        # Complexity-aware batch sizing
        if document_complexity == "simple":
            # Simple: ~300MB per document
            return max(1, int((available_mem * 0.7) / 0.3))
        elif document_complexity == "medium":
            # Medium: ~600MB per document
            return max(1, int((available_mem * 0.7) / 0.6))
        else:  # complex
            # Complex: ~1.2GB per document
            return max(1, int((available_mem * 0.7) / 1.2))
```

**Quick Fix (Configuration):**
```yaml
# Edit config/ocr_config.yaml
batch_config:
  max_batch_size: 16  # Reduce from 32
  simple_documents: 12  # Reduce from 16
  medium_documents: 6   # Reduce from 8
  complex_documents: 3  # Reduce from 4

  # Enable adaptive sizing
  adaptive_sizing: true
  memory_threshold_gb: 13.6  # 85% of 16GB
```

**Apply Fix:**
```bash
# Restart worker to apply new config
docker-compose restart worker

# Monitor next batch
docker-compose logs -f worker | grep "batch_size"
```

**⏱️ Time to Resolve:** 1-2 minutes
**🔄 Requires Downtime:** Minimal (worker restart only)

---

### Solution 2.2: Model Memory Management

**Diagnosis:**
```python
# Check loaded models
docker exec ablage-backend python -c "
import torch
from app.services.ocr.model_manager import ModelManager

manager = ModelManager()
print('Loaded models:', manager._models.keys())

for name, model in manager._models.items():
    mem = sum(p.numel() * p.element_size() for p in model.parameters())
    print(f'{name}: {mem / 1024**3:.2f} GB')
"
```

**Fix - Lazy Loading:**
```python
# Update app/services/ocr/model_manager.py
class ModelManager:
    def __init__(self):
        self._models = {}
        self._last_used = {}
        self._max_models_in_memory = 2  # NEW: Limit concurrent models

    def get_model(self, model_name: str):
        """Load model with automatic unloading of unused models."""
        import torch
        from datetime import datetime

        # Load model if not cached
        if model_name not in self._models:
            # Unload least recently used if at capacity
            if len(self._models) >= self._max_models_in_memory:
                lru_model = min(self._last_used, key=self._last_used.get)
                logger.info(f"Unloading model {lru_model} to free memory")

                # Move to CPU and delete
                self._models[lru_model].cpu()
                del self._models[lru_model]
                torch.cuda.empty_cache()

            # Load new model
            self._models[model_name] = self._load_model(model_name)

        # Update last used timestamp
        self._last_used[model_name] = datetime.now()

        return self._models[model_name]
```

**⏱️ Time to Resolve:** 5-10 minutes (code change + restart)
**🔄 Requires Downtime:** YES (backend restart)

---

### Solution 2.3: Memory Leak Detection

**Diagnosis:**
```python
# Monitor memory growth over time
docker exec ablage-backend python -c "
import torch
import gc

# Initial state
torch.cuda.empty_cache()
gc.collect()

print('Initial memory:', torch.cuda.memory_allocated() / 1024**3, 'GB')

# Process several documents
from app.services.ocr.deepseek import DeepSeekOCR
ocr = DeepSeekOCR()

for i in range(10):
    # Simulate processing
    result = ocr.process_test_image()
    print(f'After doc {i+1}:', torch.cuda.memory_allocated() / 1024**3, 'GB')

    # Check for leaks
    if i > 0:
        del result
        torch.cuda.empty_cache()
        gc.collect()
"
```

**Common Memory Leak Patterns:**
1. **Not deleting large tensors:** Always `del large_tensor` after use
2. **Circular references:** Use `weakref` for callbacks
3. **Gradient accumulation:** Call `optimizer.zero_grad()` and `model.eval()`
4. **CUDA streams not synchronized**

**Fix - Memory Cleanup Context Manager:**
```python
# Add to app/utils/gpu_manager.py
from contextlib import contextmanager
import torch
import gc

@contextmanager
def gpu_memory_guard():
    """Ensure GPU memory is cleaned up after operation."""
    try:
        # Record initial memory
        torch.cuda.reset_peak_memory_stats()
        initial_mem = torch.cuda.memory_allocated()

        yield

    finally:
        # Force cleanup
        torch.cuda.empty_cache()
        gc.collect()
        torch.cuda.synchronize()  # Wait for GPU operations to finish

        # Log memory delta
        final_mem = torch.cuda.memory_allocated()
        delta = (final_mem - initial_mem) / 1024**2  # MB

        if delta > 100:  # More than 100MB leaked
            logger.warning(f"Potential memory leak: {delta:.2f}MB not released")

# Usage in OCR services
with gpu_memory_guard():
    result = model.process(image)
```

**⏱️ Time to Resolve:** 15-30 minutes (investigation + fix)
**🔄 Requires Downtime:** Depends on fix location

---

### Solution 2.4: GPU Undersized for Workload

**Assessment:**
```
RTX 4080 Specifications:
- VRAM: 16 GB GDDR6X
- Compute Capability: 8.9
- Memory Bandwidth: 736 GB/s

Minimum Requirements by Backend:
- DeepSeek-Janus-Pro: 12 GB (batch=1)
- GOT-OCR 2.0: 10 GB (batch=1)
- Surya + Docling: 0 GB (CPU fallback)

Safety Margin: 15% (2.4 GB reserved for OS/overhead)
```

**If Truly Undersized:**
```bash
# Option 1: Use smaller models
# Edit config to prefer GOT-OCR over DeepSeek
backend_selection:
  default: "got_ocr"  # Instead of "deepseek"
  high_accuracy_mode: false  # Disable for throughput

# Option 2: Mixed precision inference
model_config:
  precision: "fp16"  # Instead of "fp32" (halves memory usage)
  use_amp: true      # Automatic mixed precision

# Option 3: CPU offloading (slower but works)
offloading:
  enabled: true
  offload_layers: 12  # Move some layers to CPU
```

**Hardware Upgrade Path:**
```
Current: RTX 4080 (16GB) - $1,200
Upgrade Options:
- RTX 4090 (24GB) - $1,600 (+50% VRAM)
- RTX A6000 (48GB) - $4,500 (+200% VRAM, enterprise)
- RTX 6000 Ada (48GB) - $6,800 (+200% VRAM, latest)
```

**⏱️ Time to Resolve:**
- Config changes: 5 minutes
- Hardware upgrade: 2-4 hours (plus procurement time)
**🔄 Requires Downtime:** Depends on solution

---

## 3. Performance Degradation

### Symptoms
- Processing slower than baseline (<150 docs/hour)
- GPU utilization low (<40%) despite queue backlog
- Increased P95 latency (>500ms API calls)
- Users report slow response times

### Decision Flow

```
START: Slow GPU Processing
    │
    ├─→ Q1: Is GPU temperature high (>85°C)?
    │   ├─→ YES → [Thermal throttling] → Go to Solution 3.1
    │   └─→ NO  → Go to Q2
    │
    ├─→ Q2: Is GPU utilization low (<40%)?
    │   ├─→ YES → [CPU bottleneck] → Go to Solution 3.2
    │   └─→ NO  → Go to Q3
    │
    ├─→ Q3: Are batch sizes suboptimal?
    │   ├─→ YES → [Batch configuration] → Go to Solution 3.3
    │   └─→ NO  → Go to Q4
    │
    └─→ Q4: Is model in correct precision?
        ├─→ NO  → [FP32 instead of FP16] → Go to Solution 3.4
        └─→ YES → [Advanced profiling] → Go to Solution 3.5
```

### Solution 3.1: Thermal Throttling

**Diagnosis:**
```bash
# Check GPU temperature
nvidia-smi --query-gpu=temperature.gpu,temperature.memory,power.draw,clocks.current.graphics --format=csv,noheader

# Monitor continuously
watch -n 1 'nvidia-smi --query-gpu=temperature.gpu,clocks.current.graphics --format=csv,noheader'

# Critical thresholds:
# Temperature: >85°C → Throttling begins
# Clock speed: <1500 MHz (RTX 4080 base is 2205 MHz) → Throttled
```

**Immediate Fix:**
```bash
# Reduce workload to cool GPU
docker-compose scale worker=0  # Pause processing

# Wait for cooldown
while true; do
  temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader)
  echo "Current temp: ${temp}°C"
  if [ "$temp" -lt 70 ]; then
    echo "Cooled down sufficiently"
    break
  fi
  sleep 10
done

# Resume processing
docker-compose scale worker=1
```

**Root Cause Fixes:**
1. **Check Cooling System:**
```bash
# Physical inspection required
# - Clean dust from GPU fans and heatsink
# - Verify case airflow (intake/exhaust)
# - Check fan operation (should spin faster under load)
# - Ensure proper thermal paste application
```

2. **Improve Airflow:**
```bash
# Software fan control (if available)
sudo nvidia-settings -a "[gpu:0]/GPUFanControlState=1"
sudo nvidia-settings -a "[fan:0]/GPUTargetFanSpeed=75"  # 75% speed
```

3. **Reduce Power Limit:**
```bash
# Lower power limit to reduce heat (reduces performance slightly)
sudo nvidia-smi -pl 280  # Reduce from 320W to 280W (RTX 4080)

# Make persistent across reboots
echo "sudo nvidia-smi -pl 280" | sudo tee /etc/rc.local
sudo chmod +x /etc/rc.local
```

**⏱️ Time to Resolve:**
- Immediate cooldown: 10-15 minutes
- Physical cleaning: 30-60 minutes
- Hardware fixes: 2-4 hours
**🔄 Requires Downtime:** YES (during cleaning/maintenance)

---

### Solution 3.2: CPU Bottleneck (Low GPU Utilization)

**Diagnosis:**
```bash
# Monitor CPU usage during GPU processing
docker stats ablage-backend ablage-worker --no-stream

# Check for CPU-bound operations
docker exec ablage-backend py-spy top --pid 1

# Common bottlenecks:
# - Image preprocessing (CPU-based)
# - Data loading from disk
# - Python GIL contention
```

**Fix 1: Optimize Preprocessing Pipeline:**
```python
# Update app/utils/image_preprocessing.py
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor

class ImagePreprocessor:
    def __init__(self, num_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

    def preprocess_batch(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """Parallel preprocessing on CPU while GPU processes previous batch."""
        futures = [
            self.executor.submit(self._preprocess_single, img)
            for img in images
        ]
        return [f.result() for f in futures]

    def _preprocess_single(self, image: np.ndarray) -> np.ndarray:
        """Single image preprocessing (runs in thread)."""
        # Resize
        image = cv2.resize(image, (1024, 1024), interpolation=cv2.INTER_LANCZOS4)

        # Normalize
        image = image.astype(np.float32) / 255.0

        # Denoise (CPU-intensive operation)
        image = cv2.fastNlMeansDenoising((image * 255).astype(np.uint8), h=10)

        return image.astype(np.float32) / 255.0
```

**Fix 2: Asynchronous Data Loading:**
```python
# Update app/services/ocr/data_loader.py
import asyncio
import aiofiles

class AsyncDocumentLoader:
    async def load_documents_async(self, document_ids: List[str]) -> List[bytes]:
        """Load documents asynchronously to prevent GPU stalling."""
        tasks = [self._load_single(doc_id) for doc_id in document_ids]
        return await asyncio.gather(*tasks)

    async def _load_single(self, doc_id: str) -> bytes:
        """Load single document from MinIO asynchronously."""
        async with aiofiles.open(f"/tmp/documents/{doc_id}.pdf", "rb") as f:
            return await f.read()
```

**Fix 3: Increase Worker Threads:**
```yaml
# Edit docker-compose.yml
services:
  worker:
    # ... other config ...
    environment:
      - CELERY_WORKER_PREFETCH_MULTIPLIER=4  # Increase from 1
      - OMP_NUM_THREADS=4  # OpenMP threads for preprocessing

    # Allocate more CPU cores
    deploy:
      resources:
        limits:
          cpus: '8'  # Increase from 4
```

**⏱️ Time to Resolve:** 10-20 minutes (config) to 1-2 hours (code changes)
**🔄 Requires Downtime:** YES (service restart)

---

### Solution 3.3: Suboptimal Batch Configuration

**Diagnosis:**
```bash
# Check current batch sizes in use
docker-compose logs worker | grep "Processing batch" | tail -20

# Analyze batch size vs throughput
docker exec ablage-backend python -c "
from app.services.ocr.performance_analyzer import PerformanceAnalyzer
analyzer = PerformanceAnalyzer()
analyzer.analyze_batch_efficiency()
"
```

**Optimal Batch Sizes (RTX 4080, 16GB):**
```yaml
batch_config:
  # Based on gpu_memory_optimization_experiment.yaml results
  deepseek:
    simple: 12
    medium: 6
    complex: 3

  got_ocr:
    simple: 16
    medium: 10
    complex: 6

  surya:
    simple: 32  # CPU-based, no limit
    medium: 24
    complex: 16

  # Dynamic adjustment
  adaptive_sizing: true
  memory_safety_margin: 0.15  # Reserve 15% VRAM

  # Throughput targets
  target_throughput_docs_per_hour: 192
  fallback_if_oom: true
```

**Apply Configuration:**
```bash
# Update config
docker exec ablage-backend python /opt/ablage/scripts/update_batch_config.py \
  --config /app/config/ocr_config.yaml \
  --optimize-for throughput

# Restart worker
docker-compose restart worker

# Monitor results
docker-compose logs -f worker | grep throughput
```

**⏱️ Time to Resolve:** 5 minutes
**🔄 Requires Downtime:** Minimal (worker restart)

---

### Solution 3.4: Incorrect Model Precision

**Diagnosis:**
```python
# Check model precision
docker exec ablage-backend python -c "
import torch
from app.services.ocr.model_manager import ModelManager

manager = ModelManager()
model = manager.get_model('deepseek')

# Check first parameter dtype
first_param = next(model.parameters())
print(f'Model precision: {first_param.dtype}')

# Should be torch.float16 for optimal performance
# If torch.float32, you're using 2x memory and slower inference
"
```

**Fix - Enable FP16 Inference:**
```python
# Update app/services/ocr/model_manager.py
class ModelManager:
    def _load_model(self, model_name: str):
        """Load model with optimal precision."""
        import torch
        from transformers import AutoModel

        model = AutoModel.from_pretrained(
            f"models/{model_name}",
            torch_dtype=torch.float16,  # FP16 precision
            device_map="auto"
        )

        model.eval()  # Inference mode

        # Enable cudnn autotuner for additional speed
        torch.backends.cudnn.benchmark = True

        return model
```

**Performance Impact:**
- **FP32 (current):** 100% memory, 100% speed (baseline)
- **FP16 (optimized):** 50% memory, 150-200% speed
- **INT8 (quantized):** 25% memory, 120-150% speed (slight accuracy loss)

**⏱️ Time to Resolve:** 10-15 minutes (code change + model reload)
**🔄 Requires Downtime:** YES (backend restart to reload models)

---

### Solution 3.5: Advanced Performance Profiling

**When to Use:** All other solutions haven't resolved the issue

**Profiling Tools:**
```bash
# 1. PyTorch Profiler
docker exec ablage-backend python -c "
import torch
from torch.profiler import profile, ProfilerActivity
from app.services.ocr.deepseek import DeepSeekOCR

ocr = DeepSeekOCR()

with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
    result = ocr.process_test_image()

print(prof.key_averages().table(sort_by='cuda_time_total', row_limit=10))
prof.export_chrome_trace('/tmp/trace.json')
"

# View trace in Chrome: chrome://tracing

# 2. NVIDIA Nsight Systems
nsys profile -o /tmp/profile docker exec ablage-backend python -m app.services.ocr.benchmark

# 3. CUDA Memory Profiler
docker exec ablage-backend python -m torch.utils.bottleneck app/services/ocr/deepseek.py
```

**Common Issues Found:**
1. **Excessive CPU-GPU transfers:** Batch tensors on CPU before moving to GPU
2. **Synchronous operations:** Use `non_blocking=True` for `.cuda()` calls
3. **Small kernel launches:** Increase batch size to amortize overhead
4. **Memory fragmentation:** Call `torch.cuda.empty_cache()` periodically

**⏱️ Time to Resolve:** 1-4 hours (investigation + optimization)
**🔄 Requires Downtime:** Depends on findings

---

## 4. CUDA Runtime Errors

### Symptoms
- `RuntimeError: CUDA error: ...`
- `CUDNN_STATUS_NOT_INITIALIZED`
- `CUDA out of memory` (different from Section 2)
- `illegal memory access`

### Common Error Codes

| Error Code | Meaning | Solution |
|------------|---------|----------|
| 2 | Out of memory | See [Section 2](#2-out-of-memory-errors) |
| 4 | System not initialized | Reinstall CUDA/drivers |
| 35 | Context is destroyed | Restart application |
| 77 | Illegal memory access | Check model compatibility |
| 98 | Invalid device function | CUDA version mismatch |

### Solution 4.1: CUDA Context Errors

**Diagnosis:**
```bash
# Check CUDA context state
docker exec ablage-backend python -c "
import torch
print('CUDA available:', torch.cuda.is_available())
print('Current device:', torch.cuda.current_device())
print('Device name:', torch.cuda.get_device_name(0))

# Try creating tensor
try:
    x = torch.randn(1000, 1000, device='cuda')
    print('Context healthy')
except Exception as e:
    print(f'Context error: {e}')
"
```

**Fix:**
```bash
# Restart application to reset CUDA context
docker-compose restart backend worker

# If persists, restart Docker daemon
sudo systemctl restart docker
docker-compose up -d
```

**⏱️ Time to Resolve:** 2-5 minutes
**🔄 Requires Downtime:** YES

---

## 5. Stuck GPU Processes

### Symptoms
- GPU memory in use but no active processing
- Worker appears hung
- `nvidia-smi` shows processes that won't terminate

### Solution 5.1: Identify and Kill Stuck Processes

**Diagnosis:**
```bash
# List GPU processes
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

# Check if process responsive
ps aux | grep [PID] | grep -v grep
```

**Fix:**
```bash
# Graceful shutdown attempt
docker-compose stop worker

# Wait 30 seconds
sleep 30

# Check if still running
nvidia-smi

# If still stuck, force kill
docker-compose kill worker

# Clean up GPU memory
sudo fuser -v /dev/nvidia*
sudo kill -9 [STUCK_PID]

# Restart
docker-compose up -d worker
```

**⏱️ Time to Resolve:** 2-5 minutes
**🔄 Requires Downtime:** YES (worker restart)

---

## 6. High Idle GPU Memory

### Symptoms
- GPU memory >2GB when idle (no processing)
- Memory doesn't decrease after processing completes
- Gradual memory increase over time

### Solution 6.1: Force Memory Cleanup

**Immediate Fix:**
```bash
# Clear cache
docker exec ablage-backend python -c "
import torch
import gc

torch.cuda.empty_cache()
gc.collect()

print('Memory after cleanup:', torch.cuda.memory_allocated() / 1024**2, 'MB')
"
```

**Automated Cleanup:**
```python
# Add to app/services/ocr/cleanup_scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
import torch
import gc

def scheduled_gpu_cleanup():
    """Run every 30 minutes during idle periods."""
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        gc.collect()

        mem_used = torch.cuda.memory_allocated() / 1024**2
        logger.info(f"Scheduled GPU cleanup: {mem_used:.2f}MB in use")

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_gpu_cleanup, 'interval', minutes=30)
scheduler.start()
```

**⏱️ Time to Resolve:** 1 minute (immediate), 10 minutes (automated)
**🔄 Requires Downtime:** NO

---

## Emergency Procedures

### Complete GPU Reset

**When:** All else fails, system unresponsive

```bash
# 1. Stop all GPU workloads
docker-compose down

# 2. Kill all GPU processes
sudo fuser -k /dev/nvidia*

# 3. Unload NVIDIA modules
sudo rmmod nvidia_uvm
sudo rmmod nvidia_drm
sudo rmmod nvidia_modeset
sudo rmmod nvidia

# 4. Reload drivers
sudo modprobe nvidia
sudo modprobe nvidia_modeset
sudo modprobe nvidia_drm
sudo modprobe nvidia_uvm

# 5. Verify GPU clean state
nvidia-smi

# 6. Restart application
docker-compose up -d
```

**⏱️ Time to Resolve:** 5-10 minutes
**🔄 Requires Downtime:** YES (complete system)
**⚠️ Warning:** Only use when other solutions fail

---

## Prevention Best Practices

### 1. Resource Monitoring
```yaml
# Set up automated monitoring
monitoring:
  gpu:
    check_interval: 60s  # Every minute
    memory_threshold: 85%
    temperature_threshold: 85°C
    alert_on_breach: true
```

### 2. Graceful Degradation
```python
# Always implement CPU fallback
try:
    result = gpu_ocr.process(image)
except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
    logger.warning(f"GPU processing failed, falling back to CPU: {e}")
    result = cpu_ocr.process(image)
```

### 3. Regular Maintenance
- **Daily:** Check [daily_operations_checklist.md](daily_operations_checklist.md)
- **Weekly:** GPU stress test and benchmark
- **Monthly:** Full system health audit

---

## Related Documents
- [Daily Operations Checklist](daily_operations_checklist.md)
- [Performance Degradation Runbook](performance_degradation_runbook.md)
- [Weekly Maintenance Runbook](weekly_maintenance_runbook.md)
- [Incident Response Playbook](../incident_response_playbook.md)

---

## Revision History

| Version | Date       | Author               | Changes                              |
|---------|------------|----------------------|--------------------------------------|
| 1.0     | 2025-01-23 | Performance Team     | Initial GPU troubleshooting guide    |
