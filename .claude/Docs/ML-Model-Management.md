# ML Model Management Guide

## 🎯 Überblick

Dieser Guide beschreibt das Management von ML-Modellen im Ablage-System, mit Fokus auf:
- VRAM-Optimierung für GPU-Backends
- Model Loading/Unloading Strategien
- Quantization Techniques
- Performance Benchmarking
- Fallback Strategies

---

## 🧠 Model Inventory

### GPU Models

| Model | Size | VRAM | Params | Speed | Accuracy | Use Case |
|-------|------|------|--------|-------|----------|----------|
| **DeepSeek-Janus-Pro-1B** | ~4GB | 14GB | 1.3B | 1-2s | ⭐⭐⭐⭐⭐ | Complex documents, layouts |
| **GOT-OCR 2.0** | ~2.2GB | 11GB | 580M | 0.3-0.5s | ⭐⭐⭐⭐ | Fast text extraction |
| **Qwen2-VL 2B** | ~5GB | 12GB | 2B | 1.5s | ⭐⭐⭐⭐⭐ | Multilingual, complex |

### CPU Models

| Model | Size | RAM | Params | Speed | Accuracy | Use Case |
|-------|------|-----|--------|-------|----------|----------|
| **Surya OCR** | ~500MB | 4GB | ~100M | 3-5s | ⭐⭐⭐ | Fallback, CPU-only |
| **Docling** | ~800MB | 6GB | ~200M | 2-4s | ⭐⭐⭐⭐ | Layout analysis |
| **PaddleOCR** | ~300MB | 3GB | ~50M | 2-3s | ⭐⭐⭐ | Fast CPU OCR |

---

## 📦 Model Loading Strategies

### 1. Lazy Loading (Empfohlen für Production)

**Konzept**: Modelle werden nur geladen, wenn sie tatsächlich benötigt werden.

**Vorteile**:
- ✅ Minimaler Startup-RAM/VRAM
- ✅ Flexibles Switching zwischen Backends
- ✅ Bessere Resource Utilization

**Nachteile**:
- ❌ Initial Latency beim ersten Request (~5-8 Sekunden)
- ❌ Komplexeres State Management

**Implementation**:

```python
# backend/core/model_manager.py

import asyncio
from typing import Dict, Optional
from enum import Enum
import torch
import psutil
import logging

logger = logging.getLogger(__name__)

class ModelState(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"

class ModelManager:
    """Lazy loading model manager with automatic swapping"""

    def __init__(self, max_vram_usage_percent: float = 0.9):
        self.models: Dict[str, Any] = {}
        self.model_states: Dict[str, ModelState] = {}
        self.loading_locks: Dict[str, asyncio.Lock] = {}
        self.max_vram_usage = max_vram_usage_percent

        # Track current GPU model
        self.active_gpu_model: Optional[str] = None

    async def get_model(self, model_name: str, backend_class):
        """Get model, loading if necessary"""

        # If already loaded, return immediately
        if self.model_states.get(model_name) == ModelState.LOADED:
            logger.info(f"Model {model_name} already loaded, returning")
            return self.models[model_name]

        # Ensure we have a lock for this model
        if model_name not in self.loading_locks:
            self.loading_locks[model_name] = asyncio.Lock()

        async with self.loading_locks[model_name]:
            # Double-check after acquiring lock
            if self.model_states.get(model_name) == ModelState.LOADED:
                return self.models[model_name]

            logger.info(f"Loading model {model_name}...")
            self.model_states[model_name] = ModelState.LOADING

            # Check if we need to unload another GPU model
            if backend_class.requires_gpu and self.active_gpu_model:
                if self.active_gpu_model != model_name:
                    await self.unload_model(self.active_gpu_model)

            # Load model
            model = backend_class(config={})
            await model.load_model()

            self.models[model_name] = model
            self.model_states[model_name] = ModelState.LOADED

            if backend_class.requires_gpu:
                self.active_gpu_model = model_name

            logger.info(f"Model {model_name} loaded successfully")
            self._log_memory_stats()

            return model

    async def unload_model(self, model_name: str):
        """Unload model to free memory"""

        if model_name not in self.models:
            return

        logger.info(f"Unloading model {model_name}...")
        self.model_states[model_name] = ModelState.UNLOADING

        model = self.models[model_name]
        await model.unload_model()

        del self.models[model_name]
        self.model_states[model_name] = ModelState.UNLOADED

        if self.active_gpu_model == model_name:
            self.active_gpu_model = None

        # Force garbage collection
        import gc
        gc.collect()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

        logger.info(f"Model {model_name} unloaded")
        self._log_memory_stats()

    def _log_memory_stats(self):
        """Log current memory usage"""
        # RAM
        ram = psutil.virtual_memory()
        logger.info(f"RAM: {ram.used / 1024**3:.2f}GB / {ram.total / 1024**3:.2f}GB ({ram.percent}%)")

        # VRAM
        if torch.cuda.is_available():
            vram_allocated = torch.cuda.memory_allocated() / 1024**3
            vram_reserved = torch.cuda.memory_reserved() / 1024**3
            logger.info(f"VRAM: {vram_allocated:.2f}GB allocated, {vram_reserved:.2f}GB reserved")

    def get_vram_usage_percent(self) -> float:
        """Get current VRAM usage as percentage"""
        if not torch.cuda.is_available():
            return 0.0

        total = torch.cuda.get_device_properties(0).total_memory
        allocated = torch.cuda.memory_allocated()
        return (allocated / total) * 100

    async def ensure_vram_available(self, required_gb: float):
        """Ensure enough VRAM is available"""
        if not torch.cuda.is_available():
            return

        total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        available = total_vram * self.max_vram_usage - (torch.cuda.memory_allocated() / 1024**3)

        if available < required_gb:
            logger.warning(f"Insufficient VRAM. Need {required_gb}GB, have {available:.2f}GB")

            # Unload currently active GPU model
            if self.active_gpu_model:
                await self.unload_model(self.active_gpu_model)

                # Recalculate
                available = total_vram * self.max_vram_usage - (torch.cuda.memory_allocated() / 1024**3)

                if available < required_gb:
                    raise RuntimeError(f"Cannot free enough VRAM. Need {required_gb}GB, have {available:.2f}GB")

# Global instance
model_manager = ModelManager(max_vram_usage_percent=0.9)
```

### 2. Eager Loading (Development Only)

**Konzept**: Alle Modelle werden beim Server-Start geladen.

**Vorteile**:
- ✅ Keine Latency bei ersten Requests
- ✅ Einfaches State Management

**Nachteile**:
- ❌ Hoher RAM/VRAM-Verbrauch beim Start
- ❌ Nur 1 GPU-Model gleichzeitig möglich (wegen VRAM-Limits)

**Implementation**:

```python
# backend/main.py

from fastapi import FastAPI
from backend.core.model_manager import model_manager
from backend.gpu.deepseek_backend import DeepSeekBackend

app = FastAPI()

@app.on_event("startup")
async def startup():
    """Pre-load models"""
    logger.info("Pre-loading models...")

    # Load default GPU backend
    await model_manager.get_model("deepseek", DeepSeekBackend)

    # Load CPU backend (always available)
    await model_manager.get_model("surya", SuryaDoclingBackend)

    logger.info("Models pre-loaded")
```

---

## 🗜️ Quantization Strategies

### Overview

| Method | Size Reduction | Speed | Accuracy Loss | VRAM Savings |
|--------|---------------|-------|---------------|--------------|
| **FP16** (Half Precision) | 2x | 1.5-2x faster | Minimal (<1%) | 50% |
| **INT8** (8-bit) | 4x | 2-3x faster | Small (1-3%) | 75% |
| **INT4** (4-bit) | 8x | 3-4x faster | Moderate (3-5%) | 87.5% |

### FP16 (Recommended)

```python
# backend/gpu/deepseek_backend.py

import torch
from transformers import AutoModelForVision2Seq

class DeepSeekBackend(BaseOCRBackend):

    async def load_model(self):
        self.model = AutoModelForVision2Seq.from_pretrained(
            self.model_name,
            torch_dtype=torch.float16,  # FP16 quantization
            device_map="auto",
            trust_remote_code=True
        )

        # Move to GPU
        self.model = self.model.to('cuda')

        logger.info(f"Model loaded in FP16: {torch.cuda.memory_allocated() / 1024**3:.2f}GB VRAM")
```

**Results**:
- DeepSeek-Janus-Pro: **14GB VRAM** (vs 28GB FP32)
- GOT-OCR 2.0: **11GB VRAM** (vs 22GB FP32)

### INT8 with bitsandbytes

```python
# Requires: pip install bitsandbytes accelerate

from transformers import AutoModelForVision2Seq, BitsAndBytesConfig

quantization_config = BitsAndBytesConfig(
    load_in_8bit=True,
    llm_int8_threshold=6.0,
    llm_int8_has_fp16_weight=False
)

model = AutoModelForVision2Seq.from_pretrained(
    model_name,
    quantization_config=quantization_config,
    device_map="auto",
    trust_remote_code=True
)
```

**Results**:
- DeepSeek-Janus-Pro: **7GB VRAM** (vs 14GB FP16)
- Accuracy loss: ~2%
- Speed: 1.8x faster

### INT4 (Experimental)

```python
quantization_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_compute_dtype=torch.float16,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4"  # NormalFloat4
)

model = AutoModelForVision2Seq.from_pretrained(
    model_name,
    quantization_config=quantization_config,
    device_map="auto"
)
```

**Results**:
- DeepSeek-Janus-Pro: **3.5GB VRAM** (vs 14GB FP16)
- Accuracy loss: ~5%
- Speed: 2.5x faster
- **Trade-off**: Noticeably lower quality on complex documents

---

## 🚀 Performance Optimization

### 1. Torch Compile (PyTorch 2.0+)

```python
import torch

class DeepSeekBackend(BaseOCRBackend):

    async def load_model(self):
        self.model = AutoModelForVision2Seq.from_pretrained(...)

        # Compile model for faster inference
        self.model = torch.compile(
            self.model,
            mode="reduce-overhead",  # or "max-autotune"
            fullgraph=True
        )

        logger.info("Model compiled with torch.compile")
```

**Results**:
- 15-30% faster inference
- First run will be slower (compilation)
- Best for batch processing

### 2. Flash Attention 2

```python
from transformers import AutoModelForVision2Seq

model = AutoModelForVision2Seq.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
    attn_implementation="flash_attention_2",  # Requires flash-attn
    trust_remote_code=True
)
```

**Requirements**:
```bash
pip install flash-attn --no-build-isolation
```

**Results**:
- 2-3x faster attention computation
- 30-40% less VRAM for attention
- Especially good for long documents

### 3. Model Warmup

```python
def warmup_model(model, processor, device):
    """Warmup model with dummy input"""

    dummy_image = Image.new('RGB', (800, 600), color='white')
    dummy_prompt = "Extract text from this document"

    inputs = processor(
        text=dummy_prompt,
        images=dummy_image,
        return_tensors="pt"
    ).to(device)

    # Run inference
    with torch.no_grad():
        _ = model.generate(**inputs, max_new_tokens=100)

    logger.info("Model warmed up")
```

**Why?**:
- First inference allocates CUDA kernels
- Warmup prevents slow first request
- Typical warmup time: 2-3 seconds

### 4. Batch Processing

```python
async def process_batch(
    self,
    image_paths: List[str],
    options: Dict[str, Any] = None
) -> List[ProcessingResult]:
    """Batch processing for efficiency"""

    # Load all images
    images = [Image.open(path).convert('RGB') for path in image_paths]

    # Prepare batch
    prompts = [self._get_prompt_for_type(options.get('document_type', 'unknown'))] * len(images)

    inputs = self.processor(
        text=prompts,
        images=images,
        return_tensors="pt",
        padding=True  # Pad to same size
    ).to(self.device, dtype=self.dtype)

    # Batch inference
    with torch.no_grad():
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            num_beams=1,  # Faster than beam search
            do_sample=False
        )

    # Decode all at once
    generated_texts = self.processor.batch_decode(outputs, skip_special_tokens=True)

    # Return results
    return [
        ProcessingResult(
            text=text,
            confidence=0.95,
            ...
        )
        for text in generated_texts
    ]
```

**Results**:
- 3-4x faster than sequential processing
- Better GPU utilization
- Trade-off: Higher peak VRAM

---

## 📊 Memory Management

### VRAM Monitoring

```python
import torch
import logging

class VRAMMonitor:
    """Monitor and log VRAM usage"""

    @staticmethod
    def log_stats(stage: str = ""):
        if not torch.cuda.is_available():
            return

        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3

        logger.info(
            f"[{stage}] VRAM: {allocated:.2f}GB allocated / "
            f"{reserved:.2f}GB reserved / {total:.2f}GB total "
            f"({(allocated/total)*100:.1f}%)"
        )

    @staticmethod
    def get_available_vram() -> float:
        """Get available VRAM in GB"""
        if not torch.cuda.is_available():
            return 0.0

        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        allocated = torch.cuda.memory_allocated() / 1024**3
        return total - allocated

    @staticmethod
    def clear_cache():
        """Clear CUDA cache"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("CUDA cache cleared")
```

### Automatic Cleanup

```python
import gc
import torch

def cleanup_after_inference():
    """Cleanup after heavy inference"""

    # Clear Python references
    gc.collect()

    # Clear CUDA cache
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

# Usage
async def process_document(self, image_path: str, options: Dict[str, Any]):
    try:
        result = await self._process(image_path, options)
        return result
    finally:
        cleanup_after_inference()
```

### Memory Pressure Detection

```python
class MemoryPressureDetector:
    """Detect when memory is running low"""

    def __init__(self, warning_threshold: float = 0.8, critical_threshold: float = 0.95):
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    def get_pressure_level(self) -> str:
        """Get current memory pressure level"""
        if not torch.cuda.is_available():
            return "normal"

        usage = torch.cuda.memory_allocated() / torch.cuda.get_device_properties(0).total_memory

        if usage >= self.critical_threshold:
            return "critical"
        elif usage >= self.warning_threshold:
            return "warning"
        else:
            return "normal"

    async def handle_pressure(self):
        """Handle high memory pressure"""
        level = self.get_pressure_level()

        if level == "critical":
            logger.error("CRITICAL memory pressure! Unloading model...")
            await model_manager.unload_model(model_manager.active_gpu_model)
        elif level == "warning":
            logger.warning("High memory pressure detected. Clearing cache...")
            cleanup_after_inference()
```

---

## 🔄 Model Swapping

### Automatic Backend Switching

```python
# backend/orchestrator/router.py

async def route_document(
    self,
    image_path: str,
    options: Dict[str, Any] = None
) -> ProcessingResult:
    """Route document with automatic model swapping"""

    # Analyze complexity
    complexity = await self._analyze_complexity(image_path, options)

    # Determine target backend
    if complexity == DocumentComplexity.COMPLEX:
        target = "deepseek"
    elif complexity == DocumentComplexity.SIMPLE:
        target = "got_ocr"
    else:
        target = "cpu_surya"

    # Check memory pressure
    detector = MemoryPressureDetector()
    pressure = detector.get_pressure_level()

    if pressure == "critical":
        logger.warning("High memory pressure, forcing CPU backend")
        target = "cpu_surya"

    # Get model (auto-load if needed)
    backend_class = BACKEND_CLASSES[target]
    backend = await model_manager.get_model(target, backend_class)

    # Process
    result = await backend.process_document(image_path, options)
    return result
```

---

## 📈 Benchmarking

### Performance Test Suite

```python
# tests/benchmark/model_performance.py

import time
import torch
from pathlib import Path

class ModelBenchmark:
    """Benchmark model performance"""

    def __init__(self, model, processor, test_images_dir: str):
        self.model = model
        self.processor = processor
        self.test_images = list(Path(test_images_dir).glob("*.png"))

    def run_inference_benchmark(self, num_runs: int = 100):
        """Benchmark inference speed"""

        times = []

        for i in range(num_runs):
            img = Image.open(self.test_images[i % len(self.test_images)])

            start = time.perf_counter()

            with torch.no_grad():
                inputs = self.processor(
                    text="Extract text",
                    images=img,
                    return_tensors="pt"
                ).to('cuda')

                outputs = self.model.generate(**inputs, max_new_tokens=512)

            end = time.perf_counter()
            times.append(end - start)

        return {
            "mean": sum(times) / len(times),
            "median": sorted(times)[len(times) // 2],
            "min": min(times),
            "max": max(times),
            "std": torch.std(torch.tensor(times)).item()
        }

    def run_vram_benchmark(self):
        """Benchmark VRAM usage"""

        torch.cuda.reset_peak_memory_stats()

        # Run inference
        img = Image.open(self.test_images[0])
        inputs = self.processor(text="Extract text", images=img, return_tensors="pt").to('cuda')

        with torch.no_grad():
            outputs = self.model.generate(**inputs, max_new_tokens=2048)

        peak_vram = torch.cuda.max_memory_allocated() / 1024**3

        return {
            "peak_vram_gb": peak_vram,
            "current_vram_gb": torch.cuda.memory_allocated() / 1024**3
        }

# Usage
benchmark = ModelBenchmark(model, processor, "test_images/")
speed_results = benchmark.run_inference_benchmark()
vram_results = benchmark.run_vram_benchmark()

print(f"Average inference time: {speed_results['mean']:.3f}s")
print(f"Peak VRAM: {vram_results['peak_vram_gb']:.2f}GB")
```

---

## 🛡️ Fallback Strategies

### 1. GPU → CPU Fallback

```python
async def process_with_fallback(
    image_path: str,
    options: Dict[str, Any]
) -> ProcessingResult:
    """Process with automatic fallback"""

    try:
        # Try GPU backend first
        backend = await model_manager.get_model("deepseek", DeepSeekBackend)
        result = await backend.process_document(image_path, options)
        return result

    except torch.cuda.OutOfMemoryError:
        logger.error("GPU OOM! Falling back to CPU...")

        # Unload GPU model
        await model_manager.unload_model("deepseek")

        # Use CPU backend
        backend = await model_manager.get_model("surya", SuryaDoclingBackend)
        result = await backend.process_document(image_path, options)
        return result
```

### 2. Model Degradation

```python
# Try models in order of quality
MODEL_HIERARCHY = [
    ("deepseek", DeepSeekBackend, 14),      # 14GB VRAM
    ("got_ocr", GOTOCRBackend, 11),         # 11GB VRAM
    ("cpu_surya", SuryaDoclingBackend, 0),  # CPU fallback
]

async def process_with_degradation(image_path: str, options: Dict[str, Any]):
    """Try models from best to worst"""

    for model_name, backend_class, vram_required in MODEL_HIERARCHY:
        try:
            # Check if enough VRAM
            if vram_required > 0:
                available = VRAMMonitor.get_available_vram()
                if available < vram_required:
                    logger.warning(f"Insufficient VRAM for {model_name}, trying next...")
                    continue

            # Try this model
            backend = await model_manager.get_model(model_name, backend_class)
            result = await backend.process_document(image_path, options)
            return result

        except Exception as e:
            logger.error(f"Failed with {model_name}: {e}")
            continue

    raise RuntimeError("All backends failed!")
```

---

## 🔧 Configuration

### Model Config File

```yaml
# config/models.yaml

models:
  deepseek:
    name: "deepseek-ai/Janus-Pro-1B"
    type: "gpu"
    quantization: "fp16"
    max_batch_size: 4
    vram_required_gb: 14
    warmup: true

  got_ocr:
    name: "ucaslcl/GOT-OCR2_0"
    type: "gpu"
    quantization: "fp16"
    max_batch_size: 8
    vram_required_gb: 11
    warmup: true

  surya:
    name: "surya-ocr"
    type: "cpu"
    max_workers: 3
    ram_required_gb: 12

management:
  lazy_loading: true
  max_vram_usage_percent: 0.9
  auto_cleanup: true
  memory_pressure_threshold: 0.8
```

---

## 📚 Best Practices

### 1. Memory Management
- ✅ Always use FP16 or lower for GPU models
- ✅ Implement automatic cleanup after inference
- ✅ Monitor VRAM usage continuously
- ✅ Use lazy loading in production

### 2. Performance
- ✅ Warmup models after loading
- ✅ Use batch processing when possible
- ✅ Enable torch.compile for repeated inference
- ✅ Consider Flash Attention for long documents

### 3. Reliability
- ✅ Implement GPU → CPU fallback
- ✅ Handle OOM errors gracefully
- ✅ Test with different document sizes
- ✅ Monitor model performance metrics

---

## 🔗 Further Resources

- [PyTorch Memory Management](https://pytorch.org/docs/stable/notes/cuda.html)
- [Hugging Face Quantization](https://huggingface.co/docs/transformers/main/en/quantization)
- [bitsandbytes Documentation](https://github.com/TimDettmers/bitsandbytes)
- [Flash Attention](https://github.com/Dao-AILab/flash-attention)
- [Torch Compile](https://pytorch.org/tutorials/intermediate/torch_compile_tutorial.html)
