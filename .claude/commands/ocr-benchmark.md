# OCR Benchmark Command

Run comprehensive OCR quality benchmarks.

**Instructions:**
1. Prepare test dataset:
   - German documents with ground truth
   - Mix of: invoices, forms, letters
   - Include: Umlauts, Fraktur, poor quality scans
2. Test all backends:
   ```python
   backends = ['deepseek', 'got_ocr', 'surya']
   for backend in backends:
       results[backend] = benchmark_backend(backend, test_dataset)
   ```
3. Measure metrics:
   - Character accuracy
   - Word accuracy
   - **Umlaut accuracy (MUST be >95%)**
   - Processing time
   - GPU memory usage
4. Generate comparison report
5. Check against SLAs:
   - Processing time: <3s per A4 page
   - Umlaut accuracy: >95%
   - GPU VRAM: <13.6GB (85%)
6. Identify quality issues using [ocr_quality_troubleshooting.md](../Execution_Layer/Troubleshooting/ocr_quality_troubleshooting.md)

**Report Format:**
```markdown
## OCR Benchmark Results

| Backend  | Char Acc | Word Acc | Umlaut Acc | Time/Page | GPU Mem |
|----------|----------|----------|------------|-----------|---------|
| DeepSeek | 98.5%    | 97.2%    | **99.8%**  | 1.8s      | 11.2GB  |
| GOT-OCR  | 96.3%    | 94.1%    | 95.3%      | 0.9s      | 9.1GB   |
| Surya    | 91.2%    | 88.5%    | 87.1%      | 3.2s      | 0GB     |

**Recommendation:** DeepSeek for production (best umlaut accuracy)
```
