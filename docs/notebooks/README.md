# Jupyter Notebooks

This directory contains Jupyter notebooks for OCR experiments, data analysis, and prototyping.

## Structure

```
notebooks/
├── experiments/          # OCR backend experiments and comparisons
├── analysis/            # Data analysis and quality metrics
├── prototypes/          # Proof-of-concept implementations
├── tutorials/           # Tutorial notebooks
└── templates/           # Notebook templates
```

## Getting Started

### 1. Install Jupyter

```bash
pip install jupyter jupyterlab ipykernel
```

### 2. Start Jupyter Lab

```bash
# From project root
jupyter lab --notebook-dir=notebooks

# Or use the script
./scripts/start_jupyter.sh
```

### 3. Access

Open http://localhost:8888 in your browser.

## Available Kernels

- **Python 3.11 (ablage-ocr)**: Main project environment with all dependencies

## Notebook Templates

Use templates to get started quickly:

- `templates/ocr_experiment_template.ipynb`: OCR backend testing
- `templates/data_analysis_template.ipynb`: Data analysis
- `templates/gpu_benchmark_template.ipynb`: GPU performance testing

## Best Practices

### 1. Keep Notebooks Clean

- Clear outputs before committing
- Use meaningful cell names
- Add markdown explanations
- Keep cells focused (one task per cell)

### 2. Use Relative Paths

```python
import sys
from pathlib import Path

# Add project root to path
project_root = Path.cwd().parent
sys.path.insert(0, str(project_root))

# Now you can import project modules
from app.services.ocr import OCRService
```

### 3. Load Environment Variables

```python
from dotenv import load_dotenv

# Load from project root .env
load_dotenv(project_root / ".env")
```

### 4. GPU Management

```python
import torch

# Check GPU availability
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0)}")

# Monitor GPU memory
torch.cuda.empty_cache()
print(f"Memory allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GB")
```

### 5. German Text Handling

```python
# Ensure UTF-8 encoding
import locale
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

# Test umlauts
test_text = "Müller, Größe, Straße"
print(test_text)
```

## Example Notebooks

### OCR Backend Comparison

```python
# Compare DeepSeek, GOT-OCR, and Surya on same document
from app.services.ocr import DeepSeekOCR, GOTOCR, SuryaOCR

backends = [DeepSeekOCR(), GOTOCR(), SuryaOCR()]
test_image = "tests/fixtures/sample_de.pdf"

results = {}
for backend in backends:
    result = await backend.process(test_image)
    results[backend.name] = {
        "text": result.text,
        "confidence": result.confidence,
        "processing_time": result.processing_time
    }

# Visualize results
import pandas as pd
df = pd.DataFrame(results).T
df.plot.bar(y='processing_time', title='OCR Processing Time by Backend')
```

### German Text Quality Analysis

```python
from app.utils.german_validator import GermanValidator

validator = GermanValidator()

# Test umlaut accuracy
test_words = ["Müller", "größer", "Straße", "Übung"]
for word in test_words:
    is_valid = validator.validate_umlauts(word)
    print(f"{word}: {'✅' if is_valid else '❌'}")
```

### GPU Performance Profiling

```python
import torch
from torch.profiler import profile, ProfilerActivity

with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as prof:
    result = model.process(image)

print(prof.key_averages().table(sort_by="cuda_time_total", row_limit=10))
```

## Git Integration

### Jupyter Notebook Diffing

Install nbdime for better notebook diffs:

```bash
pip install nbdime
nbdime config-git --enable
```

### Clear Outputs Before Committing

Use pre-commit hook (already configured) or manually:

```bash
jupyter nbconvert --clear-output --inplace notebooks/**/*.ipynb
```

## Sharing Notebooks

### Export to HTML

```bash
jupyter nbconvert --to html notebooks/experiments/ocr_comparison.ipynb
```

### Export to Python Script

```bash
jupyter nbconvert --to script notebooks/experiments/ocr_comparison.ipynb
```

### Create Presentation

```bash
jupyter nbconvert --to slides notebooks/experiments/ocr_comparison.ipynb --post serve
```

## Troubleshooting

### Kernel Won't Start

```bash
# Reinstall kernel
python -m ipykernel install --user --name=ablage-ocr
```

### Import Errors

```python
# Verify project root is in path
import sys
print(sys.path)

# Add if missing
sys.path.insert(0, '/path/to/project/root')
```

### GPU Not Available

```bash
# Check CUDA in Jupyter
import torch
print(torch.cuda.is_available())

# If false, restart Jupyter with GPU access
# (Ensure running inside Docker with GPU support or on host with CUDA)
```

## Security Notes

- **Never commit notebooks with sensitive data** (API keys, passwords, PII)
- **Clear outputs** before committing (contains execution results)
- **Use environment variables** for secrets, not hardcoded values
- **Review notebooks** before sharing externally

## Extensions

Recommended JupyterLab extensions:

```bash
# Variable inspector
pip install lckr-jupyterlab-variableinspector

# Code formatter
pip install jupyterlab-code-formatter black isort

# Git integration
pip install jupyterlab-git

# Table of contents
pip install jupyterlab-toc
```

---

**Happy Experimenting! 📊**

*Remember: Notebooks are for exploration. Production code goes in `app/`.*
