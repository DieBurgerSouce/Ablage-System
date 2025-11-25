# GPU Troubleshooting Guide - Ablage-System
**Version:** 1.0
**Status:** Production
**Letzte Aktualisierung:** 2025-11-23
**Hardware:** NVIDIA RTX 4080 (16GB VRAM)
**CUDA:** 12.x
**cuDNN:** 8.9+

**Tags:** #gpu #troubleshooting #cuda #vram #operations #devops #developer #critical #execution_layer

---

## Überblick

Dieser Guide behandelt alle GPU-bezogenen Probleme im Ablage-System. Da die GPU (RTX 4080) ein **kritischer Single Point of Failure** für die OCR-Pipeline ist, ist schnelle Problemerkennung und -behebung essentiell.

### Zielgruppe
- **DevOps Engineers** - Production issues, monitoring
- **Developers** - Development environment setup, debugging
- **On-Call Engineers** - Incident response

### Verwendete Komponenten
```
GPU-abhängige Komponenten:
├── app/gpu_manager.py         - GPU Resource Management (CRITICAL)
├── app/ocr_backends/
│   ├── deepseek.py            - DeepSeek-Janus-Pro (12GB VRAM)
│   ├── got_ocr.py             - GOT-OCR 2.0 (10GB VRAM)
│   └── surya.py               - CPU Fallback (0GB)
├── app/workers/ocr_tasks.py   - Celery GPU Workers
└── docker/Dockerfile.worker   - GPU Container Configuration
```

## Quick Diagnostic Commands

### Erste Schritte bei GPU-Problemen

```bash
# 1. GPU-Status prüfen
nvidia-smi

# 2. CUDA-Verfügbarkeit in Python prüfen
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"

# 3. VRAM-Nutzung im Detail
nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu --format=csv

# 4. GPU-Prozesse anzeigen
nvidia-smi pmon -c 1

# 5. GPU Manager Status (Ablage-System spezifisch)
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"

# 6. Container GPU-Zugriff prüfen
docker exec -it ablage-worker python -c "import torch; print(torch.cuda.is_available())"
```

**Erwartete Ausgaben:**
```
✅ Gesund:
CUDA: True
GPU: NVIDIA GeForce RTX 4080
Memory Used: <13.6GB (85% threshold)
GPU Utilization: 30-90%

❌ Problematisch:
CUDA: False
Memory Used: >14GB
GPU Utilization: 0% oder 100% dauerhaft
```

## Häufige GPU-Probleme

### Problem-Matrix

| Problem | Symptom | Wahrscheinlichkeit | Severity | Lösung |
|---------|---------|-------------------|----------|--------|
| **CUDA Not Available** | `torch.cuda.is_available() = False` | 🟠 Medium | 🔴 CRITICAL | [→ Abschnitt 1](#1-cuda-not-available) |
| **Out of Memory (OOM)** | `RuntimeError: CUDA out of memory` | 🔴 High | 🔴 CRITICAL | [→ Abschnitt 2](#2-out-of-memory-oom) |
| **GPU Not Detected** | `nvidia-smi: command not found` | 🟡 Low | 🔴 CRITICAL | [→ Abschnitt 3](#3-gpu-not-detected) |
| **Driver Version Mismatch** | CUDA version conflicts | 🟡 Low | 🟠 HIGH | [→ Abschnitt 4](#4-driver-version-mismatch) |
| **Memory Leak** | VRAM usage continuously increases | 🟠 Medium | 🟠 HIGH | [→ Abschnitt 5](#5-memory-leak) |
| **Slow Inference** | Processing time >>2s per page | 🟠 Medium | 🟡 MEDIUM | [→ Abschnitt 6](#6-slow-inference) |
| **Docker GPU Access** | Container can't access GPU | 🟠 Medium | 🔴 CRITICAL | [→ Abschnitt 7](#7-docker-gpu-access) |
| **Multi-Process Conflicts** | Multiple workers fight for GPU | 🟡 Low | 🟠 HIGH | [→ Abschnitt 8](#8-multi-process-conflicts) |

---

## 1. CUDA Not Available

### Symptome
```python
import torch
torch.cuda.is_available()  # Returns False

# Celery worker logs:
ERROR: CUDA not available, falling back to CPU
WARNING: OCR processing will be significantly slower
```

### Diagnose

**Schritt 1: Prüfe GPU-Hardware**
```bash
# Ist die GPU physisch erkannt?
lspci | grep -i nvidia

# Erwartete Ausgabe:
# 01:00.0 VGA compatible controller: NVIDIA Corporation AD104 [GeForce RTX 4080] (rev a1)
```

**Schritt 2: Prüfe NVIDIA-Treiber**
```bash
nvidia-smi

# ❌ Falls Fehler:
# NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.
# → Treiber nicht installiert oder geladen
```

**Schritt 3: Prüfe CUDA-Installation**
```bash
nvcc --version

# Erwartete Ausgabe:
# Cuda compilation tools, release 12.x
```

**Schritt 4: Prüfe PyTorch CUDA-Binding**
```python
import torch
print(torch.version.cuda)  # Sollte "12.x" sein
print(torch.cuda.is_available())  # Sollte True sein

# Falls CUDA version mismatch:
print(torch.version.cuda)  # → 11.8
# aber nvidia-smi zeigt → CUDA 12.1
# → PyTorch wurde für falsche CUDA-Version kompiliert
```

### Lösungen

#### Lösung 1: Treiber neu installieren (Ubuntu)

```bash
# 1. Alte Treiber entfernen
sudo apt-get purge nvidia-*
sudo apt-get autoremove

# 2. Neueste Treiber installieren
sudo apt-get update
sudo apt-get install nvidia-driver-535  # oder neuer

# 3. Neustart
sudo reboot

# 4. Validieren
nvidia-smi
```

#### Lösung 2: CUDA Toolkit neu installieren

```bash
# 1. CUDA 12.x herunterladen
wget https://developer.download.nvidia.com/compute/cuda/12.1.0/local_installers/cuda_12.1.0_530.30.02_linux.run

# 2. Installieren
sudo sh cuda_12.1.0_530.30.02_linux.run

# 3. Environment Variables setzen
echo 'export PATH=/usr/local/cuda-12.1/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# 4. Validieren
nvcc --version
```

#### Lösung 3: PyTorch neu installieren (CUDA 12.x)

```bash
# 1. Alte PyTorch-Installation entfernen
pip uninstall torch torchvision torchaudio

# 2. PyTorch mit CUDA 12.x installieren
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Validieren
python -c "import torch; print(torch.cuda.is_available())"
```

#### Lösung 4: Container NVIDIA Runtime

```bash
# 1. NVIDIA Container Toolkit installieren
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 2. Docker neu starten
sudo systemctl restart docker

# 3. Testen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

### Prävention

```python
# app/core/startup_checks.py
"""GPU startup validation."""

import torch
import logging

logger = logging.getLogger(__name__)

def validate_gpu_environment():
    """Validate GPU environment on application startup."""
    checks = {
        "cuda_available": torch.cuda.is_available(),
        "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
        "gpu_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    }

    if not checks["cuda_available"]:
        logger.critical("CUDA not available! GPU-dependent features will fail.")
        logger.info("Running in CPU-only mode (significantly slower)")
        return False

    if checks["gpu_count"] == 0:
        logger.error("No GPUs detected despite CUDA availability")
        return False

    logger.info(f"GPU Environment OK: {checks['gpu_name']}, CUDA {checks['cuda_version']}")
    return True

# In app/main.py
@app.on_event("startup")
async def startup_event():
    if not validate_gpu_environment():
        logger.warning("GPU validation failed - some features unavailable")
```

---

## 2. Out of Memory (OOM)

### Symptome

```python
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 16.00 GiB total capacity; 14.50 GiB already allocated; 1.25 GiB free; 14.80 GiB reserved in total by PyTorch)
```

**Celery Worker Logs:**
```
ERROR: OCR processing failed for document abc123
RuntimeError: CUDA out of memory
Worker process crashed, restarting...
```

### Diagnose

**Schritt 1: Aktuelle VRAM-Nutzung**
```bash
nvidia-smi

# Output analysieren:
# |-------------------------------+----------------------+----------------------+
# | GPU  Name        Persistence-M| Bus-Id        Disp.A | Volatile Uncorr. ECC |
# | Fan  Temp  Perf  Pwr:Usage/Cap|         Memory-Usage | GPU-Util  Compute M. |
# |===============================+======================+======================|
# |   0  NVIDIA GeForce ... Off  | 00000000:01:00.0 Off |                  N/A |
# | 30%   65C    P2   220W / 320W |  15234MiB / 16384MiB |     87%      Default |
# +-------------------------------+----------------------+----------------------+

# ❌ Problematisch: >14GB (>85%)
# ✅ Gesund: <13.6GB (<85%)
```

**Schritt 2: Prozess-spezifische VRAM-Nutzung**
```bash
nvidia-smi pmon -c 1

# Output:
# # gpu        pid  type    sm   mem   enc   dec   command
# # Idx          #   C/G     %     %     %     %   name
#     0      12345     C    85    95     -     -   python (deepseek OCR)
#     0      12346     C    10    20     -     -   python (batch processor)
```

**Schritt 3: PyTorch Memory Profiling**
```python
import torch

# Detaillierte Memory-Statistik
print(torch.cuda.memory_summary(device=0, abbreviated=False))

# Output-Beispiel:
# |===========================================================================|
# |                  PyTorch CUDA memory summary                              |
# |---------------------------------------------------------------------------|
# |            CUDA OOMs: 1            |
# |  Allocation retries: 0             |
# |===========================================================================|
# | Metric             | Cur Usage  | Peak Usage | Tot Alloc  | Tot Freed  |
# |--------------------|------------|------------|------------|------------|
# | Allocated memory   |  14.2 GB   |  15.8 GB   |  48.3 GB   |  34.1 GB   |
# | Active memory      |  14.2 GB   |  15.8 GB   |  48.3 GB   |  34.1 GB   |
```

**Schritt 4: Identifiziere Memory-Hog**
```python
# app/utils/gpu_debug.py
def find_large_tensors(threshold_mb=100):
    """Finde alle großen Tensors im GPU-Speicher."""
    import gc
    import torch

    large_tensors = []
    for obj in gc.get_objects():
        try:
            if torch.is_tensor(obj) and obj.is_cuda:
                size_mb = obj.element_size() * obj.nelement() / 1024**2
                if size_mb > threshold_mb:
                    large_tensors.append({
                        'size_mb': size_mb,
                        'shape': obj.shape,
                        'dtype': obj.dtype,
                        'device': obj.device
                    })
        except:
            pass

    # Sortiere nach Größe
    large_tensors.sort(key=lambda x: x['size_mb'], reverse=True)
    return large_tensors

# Verwendung:
tensors = find_large_tensors(threshold_mb=500)
for t in tensors[:10]:  # Top 10 größte Tensors
    print(f"Size: {t['size_mb']:.2f} MB, Shape: {t['shape']}, Device: {t['device']}")
```

### Lösungen

#### Lösung 1: Batch Size reduzieren

```python
# app/services/ocr/batch_processor.py
class GPUBatchProcessor:
    def __init__(self):
        self.optimal_batch_size = self._find_optimal_batch_size()

    def _find_optimal_batch_size(self) -> int:
        """Dynamisch optimale Batch-Größe bestimmen."""
        if not torch.cuda.is_available():
            return 1

        total_memory = torch.cuda.get_device_properties(0).total_memory
        available = total_memory - torch.cuda.memory_allocated()

        # Heuristik: ~500MB pro Bild für DeepSeek
        estimated_batch = int(available * 0.7 / (500 * 1024**2))

        # Konservativ: Max 32, Min 1
        return max(1, min(estimated_batch, 32))

    async def process_batch(self, images: List[np.ndarray]) -> List[OCRResult]:
        """Process mit automatischer Batch-Size-Anpassung."""
        batch_size = self.optimal_batch_size
        results = []

        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            try:
                batch_results = await self._process_batch_internal(batch)
                results.extend(batch_results)
            except torch.cuda.OutOfMemoryError:
                # OOM → Batch-Size halbieren und retry
                logger.warning(f"OOM detected, reducing batch size: {batch_size} → {batch_size // 2}")
                batch_size = max(1, batch_size // 2)
                self.optimal_batch_size = batch_size

                # Clear cache
                torch.cuda.empty_cache()

                # Retry mit kleinerer Batch-Size
                batch_results = await self._process_batch_internal(batch[:batch_size])
                results.extend(batch_results)

        return results
```

#### Lösung 2: Memory Guard implementieren

```python
# app/utils/gpu_memory_guard.py
from contextlib import contextmanager
import torch
import logging

logger = logging.getLogger(__name__)

@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6, auto_clear: bool = True):
    """
    Context Manager für GPU-Memory-Überwachung.

    Args:
        threshold_gb: VRAM-Schwellwert (Standard: 85% von 16GB)
        auto_clear: Automatisch Cache leeren bei Überschreitung
    """
    initial_memory = torch.cuda.memory_allocated() / 1024**3 if torch.cuda.is_available() else 0

    try:
        yield
    finally:
        if torch.cuda.is_available():
            current_memory = torch.cuda.memory_allocated() / 1024**3
            peak_memory = torch.cuda.max_memory_allocated() / 1024**3

            logger.info(
                f"GPU Memory: Initial={initial_memory:.2f}GB, "
                f"Current={current_memory:.2f}GB, Peak={peak_memory:.2f}GB"
            )

            if current_memory > threshold_gb:
                logger.warning(
                    f"GPU memory exceeded threshold: {current_memory:.2f}GB > {threshold_gb:.2f}GB"
                )
                if auto_clear:
                    logger.info("Clearing GPU cache...")
                    torch.cuda.empty_cache()
                    gc.collect()
                    cleared_memory = torch.cuda.memory_allocated() / 1024**3
                    logger.info(f"Memory after clear: {cleared_memory:.2f}GB")

# Verwendung:
with gpu_memory_guard(threshold_gb=13.6):
    results = deepseek_model.process_batch(images)
```

#### Lösung 3: Gradient Checkpointing

```python
# app/ocr_backends/deepseek.py
from torch.utils.checkpoint import checkpoint

class DeepSeekOCR:
    def __init__(self, use_checkpointing: bool = True):
        self.model = self._load_model()

        if use_checkpointing:
            # Aktiviere Gradient Checkpointing für Memory-Einsparung
            # Trade-off: 20-30% langsamer, aber 40-50% weniger VRAM
            self.model.gradient_checkpointing_enable()
            logger.info("Gradient checkpointing enabled (reduced memory usage)")

    def process_with_checkpointing(self, image: torch.Tensor) -> str:
        """Process mit memory-efficient checkpointing."""
        # Statt:
        # output = self.model(image)

        # Nutze checkpointing:
        output = checkpoint(self.model, image, use_reentrant=False)
        return output
```

#### Lösung 4: Model Quantization

```python
# app/ocr_backends/deepseek.py
import torch.quantization

class DeepSeekOCR:
    def __init__(self, use_quantization: bool = True):
        self.model = self._load_model()

        if use_quantization:
            # INT8 Quantization: 50% weniger VRAM, minimal accuracy loss
            self.model = torch.quantization.quantize_dynamic(
                self.model,
                {torch.nn.Linear, torch.nn.Conv2d},
                dtype=torch.qint8
            )
            logger.info("Model quantized to INT8 (50% memory reduction)")
```

#### Lösung 5: Aggressive Cache Clearing

```python
# app/workers/ocr_tasks.py
@celery_app.task
async def process_document_task(document_id: str):
    """OCR task mit aggressivem Memory-Management."""
    try:
        # Process document
        result = await ocr_service.process(document_id)

        return result
    finally:
        # IMMER cleanup, auch bei Erfolg
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            gc.collect()

            # Optional: Synchronize GPU
            torch.cuda.synchronize()

            logger.debug(f"GPU cache cleared after processing {document_id}")
```

### Prävention

```python
# app/core/config.py
class GPUConfig:
    """GPU Configuration with safety limits."""

    # VRAM Limits (in GB)
    VRAM_TOTAL = 16.0
    VRAM_SAFE_THRESHOLD = 0.85  # 85% = 13.6GB
    VRAM_CRITICAL_THRESHOLD = 0.95  # 95% = 15.2GB

    # Batch Processing
    DEFAULT_BATCH_SIZE = 16
    MAX_BATCH_SIZE = 32
    MIN_BATCH_SIZE = 1

    # Model Settings
    USE_GRADIENT_CHECKPOINTING = True
    USE_QUANTIZATION = False  # Nur bei extremem Memory-Druck

    # Monitoring
    MEMORY_CHECK_INTERVAL = 60  # seconds
    ENABLE_MEMORY_PROFILING = False  # Nur für Debugging

# Monitoring Setup
from prometheus_client import Gauge

gpu_memory_usage = Gauge('gpu_memory_usage_bytes', 'Current GPU memory usage')
gpu_memory_peak = Gauge('gpu_memory_peak_bytes', 'Peak GPU memory usage')

def monitor_gpu_memory():
    """Kontinuierliches GPU-Memory-Monitoring."""
    while True:
        if torch.cuda.is_available():
            current = torch.cuda.memory_allocated()
            peak = torch.cuda.max_memory_allocated()

            gpu_memory_usage.set(current)
            gpu_memory_peak.set(peak)

            if current > GPUConfig.VRAM_TOTAL * 1024**3 * GPUConfig.VRAM_CRITICAL_THRESHOLD:
                logger.critical(f"GPU memory critical: {current / 1024**3:.2f}GB")
                # Trigger alert

        time.sleep(GPUConfig.MEMORY_CHECK_INTERVAL)
```

---

## 3. GPU Not Detected

### Symptome

```bash
$ nvidia-smi
bash: nvidia-smi: command not found

$ lspci | grep -i nvidia
# Keine Ausgabe
```

### Diagnose

**Schritt 1: Hardware-Erkennung**
```bash
# Prüfe ob GPU physisch vorhanden
lspci | grep -i vga

# Prüfe ob NVIDIA-Gerät erkannt wird
lspci -nn | grep '\[03'

# Erwartete Ausgabe (irgendeine VGA):
# 00:02.0 VGA compatible controller [0300]: ...
```

**Schritt 2: Kernel-Module**
```bash
# Sind NVIDIA-Kernel-Module geladen?
lsmod | grep nvidia

# Erwartete Ausgabe:
# nvidia_drm             73728  0
# nvidia_modeset       1224704  1 nvidia_drm
# nvidia              56315904  1 nvidia_modeset

# Falls leer → Treiber nicht geladen
```

**Schritt 3: BIOS/UEFI Settings**
```bash
# Prüfe BIOS-Logs (falls verfügbar)
sudo dmesg | grep -i nvidia

# Schaue nach:
# - "NVIDIA GPU not found"
# - "PCI device disabled"
```

### Lösungen

#### Lösung 1: Treiber installieren

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install nvidia-driver-535

# RHEL/CentOS
sudo dnf install nvidia-driver-latest-dkms

# Neustart erforderlich
sudo reboot
```

#### Lösung 2: Secure Boot deaktivieren

```
NVIDIA-Treiber sind oft nicht mit Secure Boot kompatibel.

1. Neustart → BIOS/UEFI aufrufen (meist F2, F10, Del)
2. Security → Secure Boot → Disabled
3. Save & Exit
4. System bootet → Treiber neu installieren
```

#### Lösung 3: Blacklist Nouveau Driver

```bash
# Nouveau (Open-Source) blockt oft proprietären NVIDIA-Treiber

# 1. Blacklist-Datei erstellen
sudo bash -c "echo 'blacklist nouveau' > /etc/modprobe.d/blacklist-nvidia-nouveau.conf"
sudo bash -c "echo 'options nouveau modeset=0' >> /etc/modprobe.d/blacklist-nvidia-nouveau.conf"

# 2. Initramfs neu generieren
sudo update-initramfs -u

# 3. Neustart
sudo reboot

# 4. Validieren (Nouveau sollte NICHT erscheinen)
lsmod | grep nouveau
```

#### Lösung 4: Hardware-Check

```
Falls Software-Lösungen fehlschlagen:

1. Ist GPU korrekt im PCIe-Slot eingesteckt?
2. Sind alle Stromkabel (6-pin/8-pin) angeschlossen?
3. Ist PCIe-Slot im BIOS aktiviert?
4. GPU in anderem System testen (Hardware-Defekt?)
```

---

## 4. Driver Version Mismatch

### Symptome

```bash
$ nvidia-smi
Failed to initialize NVML: Driver/library version mismatch

$ python -c "import torch; print(torch.version.cuda)"
11.8

$ nvidia-smi | grep "Driver Version"
Driver Version: 535.129.03    CUDA Version: 12.2
```

**Problem:** PyTorch für CUDA 11.8 kompiliert, aber System hat CUDA 12.2.

### Diagnose

```bash
# Schritt 1: Treiber-Version
nvidia-smi | grep "Driver Version"

# Schritt 2: CUDA-Version (System)
nvcc --version

# Schritt 3: CUDA-Version (PyTorch)
python -c "import torch; print(f'PyTorch CUDA: {torch.version.cuda}')"

# Schritt 4: Kompatibilitäts-Check
# CUDA 12.x Treiber können CUDA 11.x ausführen (forward-compatible)
# Aber nicht umgekehrt!
```

### Lösungen

#### Lösung 1: PyTorch neu installieren (empfohlen)

```bash
# 1. Aktuelle CUDA-Version identifizieren
nvcc --version  # → CUDA 12.1

# 2. Passende PyTorch-Version installieren
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 3. Validieren
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

#### Lösung 2: Treiber downgraden (nur wenn notwendig)

```bash
# Nur wenn PyTorch-Update nicht möglich

# 1. Alte Treiber entfernen
sudo apt-get purge nvidia-*

# 2. Spezifische Version installieren (passend zu PyTorch)
# Für CUDA 11.8 → Treiber 520.x
sudo apt-get install nvidia-driver-520

# 3. Neustart
sudo reboot
```

#### Lösung 3: Multiple CUDA Versions

```bash
# Installiere beide CUDA-Versionen parallel

# CUDA 12.1 (System-default)
/usr/local/cuda -> /usr/local/cuda-12.1

# CUDA 11.8 (für alte Models)
/usr/local/cuda-11.8

# In requirements.txt oder virtualenv:
export CUDA_HOME=/usr/local/cuda-11.8
export LD_LIBRARY_PATH=/usr/local/cuda-11.8/lib64:$LD_LIBRARY_PATH
```

---

## 5. Memory Leak

### Symptome

```bash
# VRAM-Nutzung steigt kontinuierlich über Zeit
# Anfangs: 8GB → Nach 1h: 12GB → Nach 2h: 15GB → OOM

# nvidia-smi zeigt kontinuierlichen Anstieg:
watch -n 5 nvidia-smi
```

### Diagnose

**Schritt 1: Memory-Profiling über Zeit**
```python
# app/utils/memory_profiler.py
import torch
import time
from collections import defaultdict

class GPUMemoryProfiler:
    def __init__(self, interval_seconds=60):
        self.interval = interval_seconds
        self.measurements = []

    def start_monitoring(self, duration_minutes=10):
        """Monitor GPU memory für festgelegte Dauer."""
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)

        while time.time() < end_time:
            measurement = {
                'timestamp': time.time(),
                'allocated': torch.cuda.memory_allocated() / 1024**3,
                'reserved': torch.cuda.memory_reserved() / 1024**3,
                'max_allocated': torch.cuda.max_memory_allocated() / 1024**3
            }
            self.measurements.append(measurement)

            print(f"[{time.strftime('%H:%M:%S')}] "
                  f"Allocated: {measurement['allocated']:.2f}GB, "
                  f"Reserved: {measurement['reserved']:.2f}GB")

            time.sleep(self.interval)

        self.analyze_leak()

    def analyze_leak(self):
        """Analysiere ob Memory Leak vorliegt."""
        if len(self.measurements) < 3:
            print("Nicht genug Messungen für Leak-Analyse")
            return

        # Lineare Regression: Steigt Memory kontinuierlich?
        allocations = [m['allocated'] for m in self.measurements]
        timestamps = [m['timestamp'] for m in self.measurements]

        # Einfache Steigungsberechnung
        time_span = timestamps[-1] - timestamps[0]
        memory_increase = allocations[-1] - allocations[0]
        rate_gb_per_hour = (memory_increase / time_span) * 3600

        print(f"\n=== Memory Leak Analysis ===")
        print(f"Time span: {time_span / 60:.1f} minutes")
        print(f"Memory increase: {memory_increase:.2f} GB")
        print(f"Rate: {rate_gb_per_hour:.3f} GB/hour")

        if rate_gb_per_hour > 0.5:
            print("⚠️  WARNING: Potential memory leak detected!")
            print(f"At this rate, OOM in {(13.6 - allocations[-1]) / (rate_gb_per_hour / 3600) / 60:.1f} minutes")
        else:
            print("✅ No significant memory leak detected")

# Verwendung:
profiler = GPUMemoryProfiler(interval_seconds=30)
profiler.start_monitoring(duration_minutes=10)
```

**Schritt 2: Identifiziere Leak-Quelle**
```python
# Nutze torch.cuda.memory_snapshot() (PyTorch 2.0+)
import torch
import pickle

# Snapshot erstellen
snapshot = torch.cuda.memory._snapshot()

# Speichern für Analyse
with open('memory_snapshot.pickle', 'wb') as f:
    pickle.dump(snapshot, f)

# Analyse mit PyTorch Memory Visualizer
# https://pytorch.org/memory_viz
# Lade snapshot.pickle dort hoch
```

### Lösungen

#### Lösung 1: Explizites Tensor-Cleanup

```python
# ❌ Schlecht: Tensors bleiben im GPU-Speicher
class BadOCRService:
    def __init__(self):
        self.cached_features = []  # Leak!

    def process(self, image):
        features = self.model.extract_features(image)
        self.cached_features.append(features)  # LEAK: Features nie gelöscht!
        return features

# ✅ Gut: Explizites Cleanup
class GoodOCRService:
    def __init__(self):
        self.cached_features = []
        self.max_cache_size = 100

    def process(self, image):
        features = self.model.extract_features(image)

        # Limited cache mit Cleanup
        if len(self.cached_features) >= self.max_cache_size:
            # Lösche älteste Features
            old_features = self.cached_features.pop(0)
            del old_features  # Explizites Löschen

        self.cached_features.append(features)
        return features

    def clear_cache(self):
        """Cleanup-Methode für manuellen Call."""
        for features in self.cached_features:
            del features
        self.cached_features.clear()

        # GPU-Cache leeren
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
```

#### Lösung 2: Context Manager für Auto-Cleanup

```python
@contextmanager
def gpu_memory_cleanup():
    """Automatisches GPU-Cleanup nach Operation."""
    try:
        yield
    finally:
        # Erzwinge Python Garbage Collection
        gc.collect()

        # Leere PyTorch CUDA Cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

# Verwendung:
with gpu_memory_cleanup():
    results = model.process_batch(images)
# Nach diesem Block: Automatisches Cleanup
```

#### Lösung 3: Periodisches Forced Cleanup

```python
# app/workers/ocr_tasks.py
@celery_app.task
async def process_document_task(document_id: str):
    """Task mit periodischem Cleanup."""

    # Zähler für Cleanup-Trigger
    if not hasattr(process_document_task, 'task_counter'):
        process_document_task.task_counter = 0

    process_document_task.task_counter += 1

    try:
        result = await ocr_service.process(document_id)
        return result
    finally:
        # Cleanup alle 10 Tasks
        if process_document_task.task_counter % 10 == 0:
            logger.info("Periodic GPU cleanup triggered")
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()
```

#### Lösung 4: Worker Restart nach N Tasks

```python
# docker-compose.yml
services:
  worker:
    # ...
    command: >
      celery -A app.workers.celery_app worker
      --loglevel=info
      --concurrency=1
      --pool=solo
      --max-tasks-per-child=100  # Worker restart nach 100 Tasks

# Verhindert langfristige Memory Leaks durch Worker-Neustart
```

---

## 6. Slow Inference

### Symptome

```
Erwartete Performance: 2-3 Seiten/Sekunde (A4, 300 DPI)
Tatsächliche Performance: 0.5 Seiten/Sekunde oder langsamer
```

### Diagnose

**Schritt 1: GPU Utilization prüfen**
```bash
# GPU sollte bei Inference 70-95% ausgelastet sein
nvidia-smi dmon -s u -c 10

# gpu   pwr  temp    sm   mem   enc   dec
#   0   220    65    15    25     0     0  ← ❌ Zu niedrig (15%)
#   0   280    72    85    90     0     0  ← ✅ Gut (85%)
```

**Schritt 2: Python-Profiling**
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# OCR Processing
result = ocr_backend.process(image)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)

# Suche nach Bottlenecks:
# - I/O Operations (file reads)
# - CPU-basierte Preprocessing
# - Ineffiziente Datenkonvertierung
```

**Schritt 3: CUDA Profiling**
```bash
# NVIDIA Nsight Systems
nsys profile -o profile_output python app/main.py

# PyTorch Profiler
python -m torch.utils.bottleneck app/services/ocr_service.py
```

### Lösungen

#### Lösung 1: Optimize Data Transfer (CPU ↔ GPU)

```python
# ❌ Ineffizient: Mehrfache CPU-GPU Transfers
def slow_batch_processing(images):
    results = []
    for img in images:
        # Jedes Bild einzeln zu GPU transferieren
        img_gpu = torch.from_numpy(img).cuda()
        result = model(img_gpu)
        results.append(result.cpu().numpy())  # Zurück zu CPU
    return results

# ✅ Effizient: Batch-Transfer
def fast_batch_processing(images):
    # Alle Bilder auf einmal zu GPU
    batch = torch.stack([torch.from_numpy(img) for img in images]).cuda()

    # Batch-Inferenz
    with torch.no_grad():  # Deaktiviere Gradient-Berechnung
        results = model(batch)

    # Einmaliger CPU-Transfer
    return results.cpu().numpy()
```

#### Lösung 2: Mixed Precision (FP16)

```python
# app/ocr_backends/deepseek.py
from torch.cuda.amp import autocast

class DeepSeekOCR:
    def __init__(self, use_fp16: bool = True):
        self.model = self._load_model()
        self.use_fp16 = use_fp16

        if use_fp16:
            # FP16: 2x schneller, 50% weniger VRAM, minimal accuracy loss
            self.model = self.model.half()
            logger.info("Model converted to FP16 (2x speedup)")

    @torch.no_grad()
    def process(self, image: torch.Tensor) -> str:
        image = image.cuda()

        if self.use_fp16:
            with autocast():
                output = self.model(image)
        else:
            output = self.model(image)

        return self._decode_output(output)
```

#### Lösung 3: Compilation (PyTorch 2.0+)

```python
# app/ocr_backends/deepseek.py
import torch

class DeepSeekOCR:
    def __init__(self, compile_model: bool = True):
        self.model = self._load_model()

        if compile_model and hasattr(torch, 'compile'):
            # PyTorch 2.0+ Compilation: 20-50% speedup
            self.model = torch.compile(self.model, mode='reduce-overhead')
            logger.info("Model compiled with torch.compile (20-50% speedup)")
```

#### Lösung 4: Asynchronous Processing

```python
# app/services/ocr_service.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

class OCRService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)

    async def process_multiple_documents(self, document_ids: List[str]) -> List[OCRResult]:
        """Parallel processing für mehrere Dokumente."""

        # Erstelle Tasks für parallele Ausführung
        tasks = [
            asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._process_sync,
                doc_id
            )
            for doc_id in document_ids
        ]

        # Warte auf alle parallel
        results = await asyncio.gather(*tasks)
        return results
```

---

## 7. Docker GPU Access

### Symptome

```bash
# Host: GPU funktioniert
nvidia-smi  # ✅ OK

# Container: GPU nicht verfügbar
docker exec -it ablage-worker nvidia-smi
# OCI runtime exec failed: exec failed: unable to find user : no matching entries in passwd file
```

### Diagnose

**Schritt 1: NVIDIA Container Toolkit installiert?**
```bash
# Prüfe Installation
dpkg -l | grep nvidia-container-toolkit

# Erwartete Ausgabe:
# ii  nvidia-container-toolkit  1.14.0-1  amd64  ...
```

**Schritt 2: Docker Runtime konfiguriert?**
```bash
# Prüfe Docker-Daemon-Konfiguration
cat /etc/docker/daemon.json

# Sollte enthalten:
# {
#   "default-runtime": "nvidia",
#   "runtimes": {
#     "nvidia": {
#       "path": "nvidia-container-runtime",
#       "runtimeArgs": []
#     }
#   }
# }
```

**Schritt 3: Container mit GPU-Flag gestartet?**
```bash
# Prüfe Container-Konfiguration
docker inspect ablage-worker | grep -i nvidia

# Sollte zeigen:
# "Gpus": "all"
```

### Lösungen

#### Lösung 1: NVIDIA Container Toolkit installieren

```bash
# 1. Repository hinzufügen
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 2. Installieren
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 3. Docker konfigurieren
sudo nvidia-ctk runtime configure --runtime=docker

# 4. Docker neu starten
sudo systemctl restart docker

# 5. Testen
docker run --rm --gpus all nvidia/cuda:12.0-base nvidia-smi
```

#### Lösung 2: Docker Compose korrekt konfigurieren

```yaml
# docker-compose.yml
version: '3.8'

services:
  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker

    # GPU-Zugriff aktivieren
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1  # Oder 'all'
              capabilities: [gpu]

    # Alternativ (ältere Docker-Versionen):
    # runtime: nvidia

    environment:
      - NVIDIA_VISIBLE_DEVICES=0  # GPU 0 verwenden
      - NVIDIA_DRIVER_CAPABILITIES=compute,utility

    volumes:
      - ./app:/app
```

#### Lösung 3: Dockerfile optimieren

```dockerfile
# docker/Dockerfile.worker
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# CUDA-Umgebung
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
ENV CUDA_HOME=/usr/local/cuda
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Python + Dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# PyTorch mit CUDA
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Ablage-System Dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Startup validation
COPY scripts/validate_gpu.py /validate_gpu.py
RUN python3 /validate_gpu.py || echo "WARNING: GPU validation failed"

WORKDIR /app
CMD ["celery", "-A", "app.workers.celery_app", "worker", "--loglevel=info"]
```

---

## 8. Multi-Process Conflicts

### Symptome

```
Mehrere Celery-Worker greifen gleichzeitig auf GPU zu:
- CUDA initialization errors
- "Device is already in use"
- Random OOM errors trotz genug VRAM
- Deadlocks
```

### Diagnose

```bash
# Wie viele Prozesse nutzen die GPU?
nvidia-smi pmon -c 1

# Erwartete Output (Problem):
# gpu        pid  type    sm   mem
#   0      12345     C    50    60    python (worker 1)
#   0      12346     C    50    60    python (worker 2)  ← Konflikt!

# Gewünscht Output:
#   0      12345     C    90    95    python (single worker)
```

### Lösungen

#### Lösung 1: Single Worker mit --pool=solo

```bash
# Celery mit solo pool (kein Multi-Processing)
celery -A app.workers.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo

# Solo pool: Ein Prozess, sequential task processing
# Vermeidet Multi-Process GPU conflicts
```

#### Lösung 2: GPU-Lock-Mechanismus

```python
# app/utils/gpu_lock.py
import fcntl
import os
from contextmanager import contextmanager

@contextmanager
def gpu_lock(lock_file='/tmp/gpu_lock'):
    """File-based lock für GPU-Zugriff."""
    lock_fd = open(lock_file, 'w')
    try:
        # Acquire exclusive lock (blocks bis verfügbar)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        logger.debug("GPU lock acquired")
        yield
    finally:
        # Release lock
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        logger.debug("GPU lock released")

# Verwendung in Worker:
@celery_app.task
async def process_document_task(document_id: str):
    with gpu_lock():
        # Nur ein Worker kann GPU gleichzeitig nutzen
        result = await ocr_service.process(document_id)
    return result
```

#### Lösung 3: Multi-GPU Setup (falls verfügbar)

```python
# app/core/config.py
class GPUConfig:
    # Definiere GPU-Zuweisung pro Worker
    GPU_DEVICE_MAP = {
        'worker_1': 0,  # GPU 0
        'worker_2': 1,  # GPU 1
    }

# In Worker-Startup:
import os
worker_name = os.environ.get('WORKER_NAME', 'worker_1')
gpu_id = GPUConfig.GPU_DEVICE_MAP.get(worker_name, 0)

os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu_id)
logger.info(f"Worker {worker_name} assigned to GPU {gpu_id}")
```

---

## Emergency Procedures

### GPU-Notfall-Checkliste

Wenn GPU komplett versagt hat:

```bash
# 1. CPU-Fallback aktivieren
export USE_GPU=false
systemctl restart ablage-worker

# 2. Priorisierte Queue für kritische Dokumente
celery -A app.workers.celery_app inspect active
# Identifiziere laufende Tasks, kill falls notwendig

# 3. Monitoring-Alert bestätigen
curl -X POST http://alertmanager:9093/api/v1/alerts \
    -d '[{"labels": {"alertname": "GPU_Failure_Acknowledged"}}]'

# 4. Diagnostics sammeln
nvidia-bug-report.sh  # Generiert /var/log/nvidia-bug-report.log.gz

# 5. Incident dokumentieren
# → Meta_Layer/Incidents/YYYY-MM-DD_gpu_failure.md
```

### GPU Hard Reset

```bash
# 1. Alle GPU-Prozesse killen
sudo pkill -9 python
sudo pkill -9 celery

# 2. NVIDIA-Treiber neu laden
sudo rmmod nvidia_drm nvidia_modeset nvidia_uvm nvidia
sudo modprobe nvidia

# 3. Validate
nvidia-smi

# 4. Services neu starten
sudo systemctl restart docker
docker-compose restart worker
```

### Fallback zu CPU

```python
# app/core/config.py
USE_GPU = os.getenv('USE_GPU', 'true').lower() == 'true'

if not USE_GPU:
    logger.warning("GPU disabled by configuration - using CPU fallback")
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

# In OCR Service:
class OCRService:
    def __init__(self):
        if torch.cuda.is_available() and USE_GPU:
            self.backend = DeepSeekOCR()  # GPU
        else:
            self.backend = SuryaOCR()     # CPU Fallback
```

---

## Monitoring & Alerting

### Prometheus Metrics

```python
# app/metrics/gpu_metrics.py
from prometheus_client import Gauge, Counter, Histogram

# GPU Memory
gpu_memory_total = Gauge('gpu_memory_total_bytes', 'Total GPU memory')
gpu_memory_allocated = Gauge('gpu_memory_allocated_bytes', 'Allocated GPU memory')
gpu_memory_reserved = Gauge('gpu_memory_reserved_bytes', 'Reserved GPU memory')

# GPU Utilization
gpu_utilization = Gauge('gpu_utilization_percent', 'GPU utilization percentage')
gpu_temperature = Gauge('gpu_temperature_celsius', 'GPU temperature')

# OCR Performance
ocr_processing_duration = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing time',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

ocr_oom_errors = Counter('ocr_oom_errors_total', 'Total OOM errors')

def collect_gpu_metrics():
    """Collect GPU metrics for Prometheus."""
    if torch.cuda.is_available():
        gpu_memory_total.set(torch.cuda.get_device_properties(0).total_memory)
        gpu_memory_allocated.set(torch.cuda.memory_allocated())
        gpu_memory_reserved.set(torch.cuda.memory_reserved())

        # nvidia-smi data
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True
        )
        util, temp = result.stdout.strip().split(',')
        gpu_utilization.set(float(util))
        gpu_temperature.set(float(temp))
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "GPU Monitoring - Ablage System",
    "panels": [
      {
        "title": "GPU Memory Usage",
        "targets": [
          {
            "expr": "gpu_memory_allocated_bytes / gpu_memory_total_bytes * 100"
          }
        ],
        "alert": {
          "name": "High GPU Memory",
          "conditions": [
            {
              "evaluator": { "params": [85], "type": "gt" },
              "query": { "model": "A" }
            }
          ]
        }
      },
      {
        "title": "GPU Utilization",
        "targets": [
          {
            "expr": "gpu_utilization_percent"
          }
        ]
      },
      {
        "title": "OCR Processing Time",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

### Alert Rules

```yaml
# prometheus/alerts/gpu_alerts.yml
groups:
  - name: gpu_alerts
    interval: 30s
    rules:
      - alert: GPUMemoryHigh
        expr: (gpu_memory_allocated_bytes / gpu_memory_total_bytes) > 0.85
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage above 85%"
          description: "GPU memory at {{ $value }}%, risk of OOM"

      - alert: GPUMemoryCritical
        expr: (gpu_memory_allocated_bytes / gpu_memory_total_bytes) > 0.95
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "GPU memory usage above 95%"
          description: "GPU memory at {{ $value }}%, OOM imminent"

      - alert: GPUNotAvailable
        expr: up{job="gpu_exporter"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "GPU not available"
          description: "GPU monitoring down, check nvidia-smi"

      - alert: GPUTemperatureHigh
        expr: gpu_temperature_celsius > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU temperature high"
          description: "GPU at {{ $value }}°C, check cooling"

      - alert: FrequentOOMErrors
        expr: rate(ocr_oom_errors_total[5m]) > 0.1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Frequent OOM errors detected"
          description: "{{ $value }} OOM errors/second"
```

---

## Troubleshooting Cheatsheet

```markdown
┌─────────────────────────────────────────────────────────────────┐
│                   GPU TROUBLESHOOTING CHEATSHEET                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🔍 DIAGNOSE:                                                   │
│     nvidia-smi                          # GPU status            │
│     nvidia-smi pmon -c 1                # GPU processes         │
│     python -c "import torch; ..."       # CUDA availability     │
│     docker exec ... nvidia-smi          # Container GPU         │
│                                                                 │
│  🚨 COMMON ISSUES:                                              │
│     OOM          → Reduce batch size, clear cache              │
│     CUDA False   → Reinstall drivers, check CUDA version       │
│     Slow         → Use FP16, batch processing, compile         │
│     Docker       → Install nvidia-container-toolkit            │
│                                                                 │
│  🔧 QUICK FIXES:                                                │
│     torch.cuda.empty_cache()            # Clear GPU cache      │
│     gc.collect()                        # Python GC            │
│     sudo rmmod nvidia && modprobe nvidia # Reload driver       │
│     docker restart ablage-worker        # Restart container    │
│                                                                 │
│  📊 MONITORING:                                                 │
│     Grafana: http://localhost:3000/d/gpu-dashboard             │
│     Prometheus: http://localhost:9090/alerts                   │
│                                                                 │
│  📖 DOCUMENTATION:                                              │
│     Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md│
│     Static_Knowledge/Architecture/agent_implementation_patterns.md│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Verwandte Dokumentation

- **[gpu_manager.py](../../app/gpu_manager.py)** - GPU Manager Implementation
- **[agent_implementation_patterns.md](../../Static_Knowledge/Architecture/agent_implementation_patterns.md)** - GPU-optimized patterns
- **[agent_deployment_operations.md](../../Static_Knowledge/Architecture/agent_deployment_operations.md)** - Deployment mit GPU
- **[ocr_quality_troubleshooting.md](./ocr_quality_troubleshooting.md)** - OCR Quality Issues

## Changelog

| Version | Datum | Änderungen | Autor |
|---------|-------|-----------|-------|
| 1.0 | 2025-11-23 | Initial release: Vollständiger GPU Troubleshooting Guide | Development Team |

---

**Feedback:** Issues oder PRs im Repository erstellen
**Maintainer:** DevOps Team + Development Team
**Review:** Quarterly oder nach Major-Incidents
**Nächstes Review:** 2026-02-23
