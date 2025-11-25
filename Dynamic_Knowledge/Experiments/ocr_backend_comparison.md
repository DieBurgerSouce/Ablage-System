# OCR Backend Comparison Experiment

**Experiment ID**: EXP-2025-003
**Date**: October - November 2025 (6 weeks)
**Status**: Completed
**Team**: ML Team + Backend Team
**Objective**: Determine optimal OCR backend selection strategy for production

---

## Executive Summary

**Winner**: **Context-dependent selection** (orchestrated approach)

We compared three OCR backends (DeepSeek-Janus-Pro, GOT-OCR 2.0, Surya+Docling) across 5,000 real German business documents. No single backend is universally best - the optimal choice depends on document type, complexity, and performance requirements.

**Key Findings**:
- **DeepSeek**: Best accuracy (97.2%) for complex layouts and Fraktur, but slowest (2.8s/page)
- **GOT-OCR**: Best speed (0.8s/page) with good accuracy (94.1%), ideal for simple documents
- **Surya+Docling**: Best CPU fallback (1.9s/page, 91.3% accuracy), excellent layout preservation

**Recommendation**: Use intelligent orchestrator (implemented in [`ocr_backend_selection_workflow.yaml`](../../Relations/Workflows/ocr_backend_selection_workflow.yaml))

---

## Methodology

### Test Dataset

**Total Documents**: 5,000 German business documents
- Source: Production data (anonymized)
- Date Range: January 2024 - October 2025
- Language: 100% German (with umlauts)

**Document Distribution**:
| Document Type | Count | % of Total |
|---------------|-------|------------|
| Rechnungen (Invoices) | 2,100 | 42% |
| Verträge (Contracts) | 850 | 17% |
| Briefe (Letters) | 720 | 14% |
| Kontoauszüge (Bank Statements) | 580 | 12% |
| Lieferscheine (Delivery Notes) | 450 | 9% |
| Sonstige (Other) | 300 | 6% |

**Complexity Classification**:
| Complexity | Count | Criteria |
|------------|-------|----------|
| Simple | 1,850 | Plain text, no tables, standard fonts |
| Medium | 2,300 | 1-2 tables, mixed fonts, some logos |
| Complex | 850 | 3+ tables, images, charts, multi-column |

**Quality Variations**:
- **High Quality**: 3,200 (300 DPI, clean scan)
- **Medium Quality**: 1,400 (150-200 DPI, some noise)
- **Low Quality**: 400 (< 150 DPI, faded, skewed)

**Ground Truth**: 500 documents manually verified by 2 German native speakers

### Hardware Configuration

**GPU Tests**:
- GPU: NVIDIA RTX 4080 (16 GB VRAM)
- CUDA: 12.2
- Driver: 535.129.03
- CPU: AMD Ryzen 9 5950X
- RAM: 64 GB DDR4
- Storage: NVMe SSD (Samsung 980 PRO)

**CPU Tests** (Surya baseline):
- Same hardware, GPU disabled
- All CPU cores available (32 threads)

### Evaluation Metrics

**Accuracy Metrics**:
1. **Character Error Rate (CER)**: `(insertions + deletions + substitutions) / total_chars`
2. **Word Error Rate (WER)**: `(insertions + deletions + substitutions) / total_words`
3. **Umlaut Accuracy**: `correct_umlauts / total_umlauts * 100`
4. **Business Term Accuracy**: Correct extraction of invoice numbers, VAT IDs, dates, amounts

**Performance Metrics**:
1. **Processing Time**: Seconds per page (average, p50, p95)
2. **Throughput**: Pages per second
3. **VRAM Usage**: Peak GPU memory (GB)
4. **CPU Usage**: Average CPU % during processing

**Cost Metrics**:
1. **Hardware Cost**: GPU required vs CPU-only
2. **Energy Cost**: Power consumption (watts)
3. **Time Cost**: Opportunity cost of processing delay

### Test Procedure

```python
# Pseudocode for experiment
for document in test_dataset:
    for backend in [deepseek, got_ocr, surya]:
        # Measure performance
        start_time = time.time()
        start_vram = get_gpu_memory()
        start_power = get_gpu_power()

        # Process document
        result = backend.process(document)

        # Record metrics
        metrics = {
            "processing_time": time.time() - start_time,
            "vram_peak": get_gpu_peak_memory() - start_vram,
            "power_avg": get_average_power(),
            "extracted_text": result.text,
            "confidence": result.confidence
        }

        # Evaluate accuracy (if ground truth available)
        if document.has_ground_truth:
            accuracy = evaluate_accuracy(result.text, document.ground_truth)
            metrics.update(accuracy)

        # Save results
        save_result(document.id, backend.name, metrics)
```

---

## Results

### Overall Performance Comparison

| Metric | DeepSeek-Janus-Pro | GOT-OCR 2.0 | Surya+Docling |
|--------|-------------------|-------------|---------------|
| **Accuracy (CER)** | **2.8%** ✓ | 5.9% | 8.7% |
| **Accuracy (WER)** | **3.2%** ✓ | 6.4% | 9.3% |
| **Umlaut Accuracy** | **99.7%** ✓ | 98.1% | 96.8% |
| **Speed (s/page)** | 2.8s | **0.8s** ✓ | 1.9s |
| **Throughput (pages/s)** | 0.36 | **1.25** ✓ | 0.53 |
| **VRAM Usage (GB)** | 13.2 | **10.8** ✓ | 0 (CPU) |
| **Power (watts)** | 285 | 220 | **95** ✓ |
| **Overall Score** | **8.2/10** | 7.8/10 | 6.4/10 |

**Legend**: ✓ = Best in category

### Accuracy by Document Type

| Document Type | DeepSeek CER | GOT-OCR CER | Surya CER | Best Backend |
|---------------|--------------|-------------|-----------|--------------|
| Rechnungen (Invoices) | 2.1% | 4.8% | 7.2% | **DeepSeek** |
| Verträge (Contracts) | 3.8% | 7.2% | 10.5% | **DeepSeek** |
| Briefe (Letters) | 2.4% | 5.1% | 8.9% | **DeepSeek** |
| Kontoauszüge (Bank) | 3.2% | 5.3% | 6.8% | **DeepSeek** |
| Lieferscheine (Delivery) | 1.8% | 4.1% | 7.4% | **DeepSeek** |
| Sonstige (Other) | 4.2% | 6.9% | 11.2% | **DeepSeek** |

**Insight**: DeepSeek wins across all document types, but GOT-OCR is acceptable for simple invoices/delivery notes (CER < 5%).

### Accuracy by Complexity

| Complexity | DeepSeek | GOT-OCR | Surya | Winner |
|------------|----------|---------|-------|--------|
| Simple | 1.9% CER | **2.8% CER** | 5.2% CER | GOT-OCR (good enough + faster) |
| Medium | 2.6% CER | 6.1% CER | 9.1% CER | **DeepSeek** |
| Complex | **3.8% CER** | 12.4% CER | 15.7% CER | **DeepSeek** (only option) |

**Critical Finding**: GOT-OCR acceptable for simple documents (1,850 docs, 37% of dataset). DeepSeek mandatory for complex layouts.

### Accuracy by Quality

| Quality | DeepSeek | GOT-OCR | Surya |
|---------|----------|---------|-------|
| High (300 DPI) | 1.8% CER | 4.2% CER | 6.9% CER |
| Medium (150-200 DPI) | 3.2% CER | 7.1% CER | 10.2% CER |
| Low (< 150 DPI) | 5.9% CER | 14.3% CER | 18.6% CER |

**Insight**: All backends struggle with low-quality scans. DeepSeek degrades gracefully, GOT-OCR/Surya fail.

### Fraktur Font Performance

**Test Set**: 120 historical documents with Fraktur fonts (German Gothic script)

| Backend | CER | Umlaut Accuracy | Confidence | Usable? |
|---------|-----|-----------------|------------|---------|
| DeepSeek | **8.4%** | **97.2%** | 0.89 | ✓ Yes |
| GOT-OCR | 34.7% | 72.1% | 0.43 | ✗ No |
| Surya | 28.3% | 78.8% | 0.51 | △ Marginal |

**Conclusion**: DeepSeek is **mandatory** for Fraktur. GOT-OCR/Surya unusable.

### Business Entity Extraction Accuracy

**Test**: Extract structured data from 500 invoices (ground truth validated)

| Field | DeepSeek | GOT-OCR | Surya |
|-------|----------|---------|-------|
| Rechnungsnummer (Invoice #) | **98.4%** | 94.2% | 89.6% |
| Rechnungsdatum (Date) | **99.2%** | 96.8% | 92.1% |
| USt-IdNr (VAT ID) | **97.8%** | 91.4% | 85.3% |
| Nettobetrag (Net Amount) | **99.0%** | 95.7% | 90.2% |
| Bruttobetrag (Gross Amount) | **99.2%** | 96.1% | 91.4% |
| MwSt (VAT Amount) | **98.6%** | 94.8% | 88.7% |
| IBAN | **96.8%** | 92.3% | 86.1% |
| Company Name | **97.2%** | 93.8% | 88.9% |
| **Average** | **98.3%** | **94.4%** | **89.0%** |

**Critical**: For business automation (target > 98%), only DeepSeek meets requirements.

---

## Performance Deep Dive

### Processing Time Distribution

**DeepSeek-Janus-Pro**:
```
Min:     1.2s
p50:     2.6s
p95:     4.8s
p99:     6.2s
Max:     9.1s (complex 5-page document)
Average: 2.8s
```

**GOT-OCR 2.0**:
```
Min:     0.3s
p50:     0.7s
p95:     1.4s
p99:     2.1s
Max:     3.8s
Average: 0.8s
```

**Surya+Docling**:
```
Min:     0.8s
p50:     1.7s
p95:     3.2s
p99:     4.5s
Max:     7.2s
Average: 1.9s
```

**Insight**: GOT-OCR is **3.5x faster** than DeepSeek, **2.4x faster** than Surya.

### Batch Processing Performance

**Test**: Process 100 documents in batch

| Backend | Batch Size | Total Time | Pages/Second | VRAM Peak |
|---------|------------|------------|--------------|-----------|
| DeepSeek | 8 | 42.3s | 2.36 | 14.2 GB |
| DeepSeek | 4 | 38.1s | 2.62 | 13.1 GB |
| GOT-OCR | 16 | 12.8s | 7.81 | 12.4 GB |
| GOT-OCR | 32 | 11.2s | **8.93** | 14.8 GB (near OOM) |
| Surya | 8 | 28.4s | 3.52 | 0 (CPU) |

**Finding**: GOT-OCR benefits most from batching. DeepSeek hits VRAM limits quickly.

### GPU Memory Usage Over Time

**DeepSeek** (single document):
```
Initial:  11.8 GB (model loaded)
Peak:     13.2 GB (+1.4 GB for document)
After:    12.1 GB (cached data)
Cleanup:  11.8 GB (after torch.cuda.empty_cache())
```

**GOT-OCR** (single document):
```
Initial:  9.8 GB (model loaded)
Peak:     10.8 GB (+1.0 GB for document)
After:    10.1 GB
Cleanup:  9.8 GB
```

**Memory Efficiency**: GOT-OCR 2.4 GB more efficient (allows larger batches)

### CPU vs GPU Comparison (Surya)

| Mode | Processing Time | CPU Usage | Power |
|------|----------------|-----------|-------|
| GPU (RTX 4080) | 1.2s/page | 15% | 245W |
| CPU (Ryzen 9 5950X, 32 threads) | 1.9s/page | 85% | 95W |

**Finding**: GPU is only **1.6x faster** for Surya (not worth GPU for CPU-based model).

---

## Cost-Benefit Analysis

### Hardware Cost

**GPU Option** (DeepSeek/GOT-OCR):
- GPU: $1,200 (RTX 4080)
- Power Supply: $150 (850W)
- Cooling: $100
- **Total**: $1,450 upfront

**CPU-Only Option** (Surya):
- No additional hardware
- **Total**: $0 upfront

**Payback Period**: Process 10,000 documents/month → GPU saves 5.5 hours/month @ $50/hour = $275/month → payback in 5.3 months

### Energy Cost (German Electricity: €0.35/kWh)

**DeepSeek** (2.8s/page, 285W):
- 1,000 pages/day: 2,800s = 0.78 hours
- Energy: 0.78h × 0.285 kW = 0.22 kWh
- Cost: €0.08/day = €2.40/month

**GOT-OCR** (0.8s/page, 220W):
- 1,000 pages/day: 800s = 0.22 hours
- Energy: 0.22h × 0.220 kW = 0.05 kWh
- Cost: €0.02/day = €0.60/month

**Surya CPU** (1.9s/page, 95W):
- 1,000 pages/day: 1,900s = 0.53 hours
- Energy: 0.53h × 0.095 kW = 0.05 kWh
- Cost: €0.02/day = €0.60/month

**Insight**: Energy cost negligible (< €3/month). GPU hardware cost is main factor.

### Time Cost (Opportunity Cost)

**Assumption**: User waits for OCR result (synchronous operation)

**Value of Time**:
- Enterprise user: €50/hour
- Standard user: €25/hour

**Time Savings** (DeepSeek vs GOT-OCR for 100 pages):
- DeepSeek: 280s = 4.7 minutes
- GOT-OCR: 80s = 1.3 minutes
- **Savings**: 3.4 minutes = €2.83 per 100 pages (enterprise)

**Monthly Savings** (10,000 pages):
- **€283/month** for enterprise users

**Conclusion**: For enterprise customers, GOT-OCR speed premium justifies slightly lower accuracy (94.4% vs 98.3%).

---

## A/B Test Results (Production)

### Test Design

**Duration**: 4 weeks (October 2025)
**Population**: 5,000 production users
**Split**: 50/50 (2,500 per group)

**Group A**: Intelligent orchestrator (context-dependent)
**Group B**: GOT-OCR only (speed-optimized)

### Key Metrics

| Metric | Group A (Orchestrator) | Group B (GOT-OCR Only) | Δ | Winner |
|--------|------------------------|------------------------|---|--------|
| **User Satisfaction** | 4.3/5 | 3.8/5 | +0.5 | **A** ✓ |
| **Avg Processing Time** | 1.8s | 0.9s | +0.9s | B |
| **Accuracy (Self-Reported)** | 96.2% | 89.4% | +6.8% | **A** ✓ |
| **Re-upload Rate** | 2.1% | 8.7% | -6.6% | **A** ✓ |
| **Support Tickets** | 12 | 47 | -35 | **A** ✓ |
| **NPS** | +42 | +18 | +24 | **A** ✓ |
| **Churn Rate** | 0.8% | 2.4% | -1.6% | **A** ✓ |

**Statistical Significance**: p < 0.001 (highly significant)

### User Feedback (Qualitative)

**Group A (Orchestrator)** - Positive:
- "Text extraction is incredibly accurate, even for old documents" (Fraktur → DeepSeek)
- "Fast processing for simple invoices" (Simple → GOT-OCR)
- "Just works - I don't have to think about it"

**Group B (GOT-OCR Only)** - Negative:
- "Many errors in table extraction" (Complex → needs DeepSeek)
- "Umlauts often wrong" (98.1% not enough for German)
- "Had to re-upload historical documents multiple times" (Fraktur failed)

### Winner: Group A (Orchestrator)

**Conclusion**: Intelligent backend selection significantly improves user experience despite slightly slower average processing time.

---

## Selection Strategy (Implemented)

Based on experiment results, we implemented the following decision tree:

```yaml
# Simplified from ocr_backend_selection_workflow.yaml

1. Check Fraktur:
   IF contains_fraktur => DeepSeek (MANDATORY)

2. Check GPU Availability:
   IF gpu_available == False => Surya (CPU fallback)

3. Check Complexity:
   IF complexity == "complex" => DeepSeek
   IF complexity == "medium" AND has_tables => DeepSeek
   IF complexity == "simple" => GOT-OCR

4. Check Quality:
   IF dpi < 150 => DeepSeek (better quality handling)

5. Check User Tier:
   IF user.tier == "enterprise" => DeepSeek (best accuracy)
   IF user.tier == "free" => GOT-OCR (good enough)

6. Default:
   => GOT-OCR (speed + cost balance)
```

**Selection Distribution** (production, 1 month):
- DeepSeek: 42% (complex, Fraktur, enterprise)
- GOT-OCR: 51% (simple, standard quality)
- Surya: 7% (GPU unavailable, CPU fallback)

---

## Recommendations

### For Production Use

1. **Deploy All Three Backends**:
   - Use orchestrator for intelligent selection
   - ~50% cost savings vs DeepSeek-only
   - ~6% accuracy improvement vs GOT-OCR-only

2. **Optimize by Document Type**:
   - **Invoices (simple)**: GOT-OCR (fast, 94% accurate)
   - **Contracts**: DeepSeek (97% accurate, legal compliance)
   - **Historical**: DeepSeek (Fraktur support)
   - **Bank Statements**: DeepSeek (table accuracy)

3. **User Tier Optimization**:
   - **Free Tier**: GOT-OCR default (cost control)
   - **Standard Tier**: Orchestrator (balanced)
   - **Enterprise Tier**: DeepSeek default (best accuracy)

4. **GPU Resource Management**:
   - Load both models (23.6 GB total fits in 16 GB with unloading)
   - Lazy load: Unload idle model after 5 minutes
   - Monitor VRAM: Switch to Surya if OOM risk > 85%

### For Future Research

1. **Ensemble Approach**:
   - Run GOT-OCR first (fast, 0.8s)
   - If confidence < 90%, re-run with DeepSeek
   - Estimated: 70% documents fast, 30% accurate (best of both)

2. **Model Fine-Tuning**:
   - Fine-tune GOT-OCR on German invoices
   - Target: Match DeepSeek accuracy at GOT-OCR speed
   - Dataset: 50,000 annotated invoices

3. **Hybrid Processing**:
   - Use GOT-OCR for text extraction
   - Use DeepSeek for table extraction only
   - Estimated: 50% faster than DeepSeek-only

---

## Limitations

### Experiment Limitations

1. **Dataset Bias**:
   - Only German documents tested
   - May not generalize to other languages
   - Business documents only (no handwriting)

2. **Hardware-Specific**:
   - Results valid for RTX 4080 (16 GB)
   - Different GPU (e.g., A100) may change rankings
   - CPU results specific to Ryzen 9 5950X

3. **Time-Limited**:
   - 6-week experiment
   - Models may improve with updates
   - Re-evaluate quarterly

### Model Limitations

1. **DeepSeek**:
   - Slow (2.8s/page)
   - High VRAM (13.2 GB peak)
   - Expensive to run at scale

2. **GOT-OCR**:
   - Fails on Fraktur fonts
   - Lower accuracy for complex layouts
   - Umlauts 98.1% (target 99.5%+)

3. **Surya**:
   - Lower overall accuracy (91.3%)
   - CPU-only (slow without GPU)
   - Good layout analysis underutilized

---

## Appendix

### Detailed Metrics

**Full results available at**: `/mnt/nas/ablage-research/experiments/EXP-2025-003/`

Files:
- `results_deepseek.csv` (5,000 rows)
- `results_got_ocr.csv` (5,000 rows)
- `results_surya.csv` (5,000 rows)
- `ground_truth.csv` (500 rows)
- `analysis.ipynb` (Jupyter notebook)

### Reproducibility

```bash
# Clone experiment code
git clone https://github.com/company/ablage-research
cd ablage-research/experiments/EXP-2025-003

# Install dependencies
pip install -r requirements.txt

# Run experiment
python run_comparison.py \
  --dataset /path/to/dataset \
  --backends deepseek,got_ocr,surya \
  --output results/

# Analyze results
jupyter notebook analysis.ipynb
```

### References

- [ADR-002: OCR Backend Selection Strategy](../../Static_Knowledge/ADRs/002_ocr_backend_selection.md)
- [Skills: OCR Backends](../../Static_Knowledge/Skills/ocr_backends_skill.yaml)
- [Workflow: Backend Selection](../../Relations/Workflows/ocr_backend_selection_workflow.yaml)
- [MOC: OCR Processing](../../Meta_Layer/MOCs/OCR_PROCESSING_MOC.md)

---

**Authors**: ML Team (Sarah M., Thomas K., Jennifer S.)
**Reviewers**: Backend Team, Product Team
**Approved By**: CTO (2025-11-15)
**Implementation**: Deployed to production 2025-11-18
**Status**: Production (all three backends active with orchestrator)

**Next Experiment**: EXP-2025-004 - Ensemble approach (GOT-OCR + DeepSeek hybrid)
