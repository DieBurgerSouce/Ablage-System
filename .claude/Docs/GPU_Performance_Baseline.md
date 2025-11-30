# GPU Performance Baseline Documentation

## System Configuration

| Component | Specification |
|-----------|---------------|
| GPU | NVIDIA RTX 4080 |
| VRAM | 16GB GDDR6X |
| CUDA Version | 12.1+ |
| cuDNN Version | 8.9+ |
| Platform | Windows 11 / Docker |

## VRAM Safety Thresholds

| Threshold | Value | Description |
|-----------|-------|-------------|
| Maximum | 13.6GB | 85% of 16GB - hard limit |
| Warning | 12.0GB | 75% - triggers optimization |
| Optimal | 10.0GB | Safe operating range |
| Recovery | OOM event | Triggers fallback chain |

## Backend Performance Baselines

### DeepSeek-Janus-Pro (Primary - Best Quality)

| Metric | Windows (bfloat16) | Linux (4-bit) | Target |
|--------|-------------------|---------------|--------|
| VRAM Required | ~14GB | ~12GB | <13.6GB |
| VRAM Peak | ~14GB | ~12GB | <13.6GB |
| Throughput | 0.3-0.5 p/s | 0.5-0.8 p/s | >0.5 p/s |
| German Accuracy | 95% | 95% | >90% |
| Fraktur Accuracy | 90% | 90% | >85% |
| Table Accuracy | 92% | 92% | >85% |

**Windows Notes:**
- BitsAndBytes 4-bit quantization not available on Windows
- Uses GPTQ/AWQ quantization if available
- Falls back to bfloat16 with memory optimization
- Recommended: Install `auto-gptq` for Windows

**Best For:**
- Complex table structures
- Handwritten text and Fraktur fonts
- Mixed German/English documents
- Documents requiring semantic understanding

### GOT-OCR 2.0 (Secondary - Fast + Tables)

| Metric | Value | Target |
|--------|-------|--------|
| VRAM Required | 10GB | <13.6GB |
| VRAM Peak | ~10GB | <13.6GB |
| Throughput | 1-2 p/s | >1.0 p/s |
| German Accuracy | 85-90% | >85% |
| Table Accuracy | 90% | >85% |
| Formula Accuracy | 88% | >80% |

**Best For:**
- Documents with tables
- Mathematical formulas
- Fast processing needs
- Standard document layouts

### Surya GPU (Tertiary - Fast)

| Metric | Value | Target |
|--------|-------|--------|
| VRAM Required | 8GB | <13.6GB |
| VRAM Peak | ~8GB | <13.6GB |
| Throughput | 1.5-2 p/s | >1.5 p/s |
| German Accuracy | 85% | >80% |
| Layout Detection | 90% | >85% |

**Best For:**
- High-volume processing
- Standard text documents
- When speed is priority

### Surya+Docling (CPU Fallback)

| Metric | Value | Target |
|--------|-------|--------|
| VRAM Required | 0GB | N/A |
| CPU Usage | High | N/A |
| Throughput | 0.2-0.5 p/s | >0.2 p/s |
| German Accuracy | 80% | >75% |
| Layout Analysis | Good | Acceptable |

**Best For:**
- When GPU unavailable
- OOM recovery fallback
- Layout analysis priority
- Low-priority batch processing

## Fallback Chain

```
DeepSeek → GOT-OCR → Surya GPU → Surya+Docling (CPU)
   │           │          │              │
   │           │          │              └── Always available
   │           │          └── Requires 8GB VRAM
   │           └── Requires 10GB VRAM
   └── Requires 12-14GB VRAM
```

### Fallback Triggers

1. **GPU Unavailable**: Immediately use Surya+Docling (CPU)
2. **Insufficient VRAM**: Skip backends exceeding available VRAM
3. **OOM During Processing**:
   - Clear GPU cache
   - Reduce batch size by 50%
   - Retry with smaller batch
   - If still OOM: fall to next backend
4. **Backend Load Failure**: Skip to next backend in chain

## Windows Quantization Options

### Priority Order (Windows)
1. **GPTQ** (`auto-gptq` package) - Best Windows option
2. **AWQ** (`autoawq` package) - Alternative
3. **bfloat16** - Last resort (high VRAM usage)

### Installation
```bash
# Option 1: GPTQ (recommended for Windows)
pip install auto-gptq

# Option 2: AWQ
pip install autoawq

# Verify installation
python -c "from auto_gptq import AutoGPTQForCausalLM; print('GPTQ OK')"
```

## Benchmark Commands

```bash
# Full benchmark (all backends)
python scripts/run_benchmark_suite.py

# Quick benchmark (fewer documents)
python scripts/run_benchmark_suite.py --quick

# Specific backend
python scripts/run_benchmark_suite.py --backend surya_gpu

# With HTML report
python scripts/run_benchmark_suite.py --html-report benchmark_report.html
```

## Monitoring Commands

```bash
# Real-time VRAM monitor
python scripts/vram_monitor.py --duration 300

# Docker GPU validation
python scripts/validate_docker_gpu.py

# GPU diagnostics
python scripts/gpu_diagnostics.py
```

## Test Document Categories

| Category | Count | Purpose |
|----------|-------|---------|
| Invoices | 6 | Business documents, IBAN, VAT |
| Fraktur | 6 | Historical German fonts |
| Tables | 6 | Structured data |
| Contracts | 6 | Formal documents |
| Forms | 3 | Government forms |
| Handwritten | 3 | Handwriting recognition |
| Mixed | 3 | Combined elements |

**Total: 33 documents**

## Performance Optimization Tips

### Reduce VRAM Usage
1. Use quantized models (GPTQ/AWQ)
2. Enable `low_cpu_mem_usage=True`
3. Clear cache between documents: `torch.cuda.empty_cache()`
4. Use smaller batch sizes
5. Process documents sequentially, not in parallel

### Improve Throughput
1. Enable Flash Attention 2 (Linux/WSL2)
2. Use `torch.inference_mode()` instead of `torch.no_grad()`
3. Warm up models before processing
4. Batch similar-sized documents together

### Improve Accuracy
1. Preprocess images (normalize, denoise)
2. Use appropriate backend for document type
3. Enable post-processing with German spell-check
4. Use entity extraction for structured data

## Troubleshooting

### OOM Errors
```python
# Check current VRAM usage
import torch
print(f"Allocated: {torch.cuda.memory_allocated() / 1024**3:.2f}GB")
print(f"Reserved: {torch.cuda.memory_reserved() / 1024**3:.2f}GB")

# Clear cache
torch.cuda.empty_cache()
```

### Backend Not Loading
1. Check VRAM availability
2. Verify model files downloaded
3. Check quantization library installed
4. Review logs for specific error

### Poor German Accuracy
1. Verify language set to "de"
2. Check document quality (resolution, contrast)
3. Try DeepSeek for complex layouts
4. Enable post-processing spell-check

---

*Last Updated: 2024-11-30*
*Maintained by: Ablage-System Development Team*
