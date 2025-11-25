# Ablage-System OCR - Claude Code Context

## Project Overview
Enterprise-grade German document processing system with GPU-accelerated OCR.
- **Status**: Proof of Concept (4 files implemented)
- **Hardware**: RTX 4080 16GB VRAM
- **Language**: German-first (100% umlaut accuracy required)
- **Philosophy**: "Feinpoliert und durchdacht"

## Essential Commands
```bash
# Start API server
python app/main.py

# Run tests
pytest tests/test_basic.py -v

# Check GPU status
python -c "from app.gpu_manager import GPUManager; print(GPUManager().get_detailed_status())"

# Validate German text
python -c "from app.german_validator import GermanValidator; v = GermanValidator(); print(v.validate_umlauts('Müller GmbH'))"
```

## Current Structure (Minimal POC)
```
app/
  main.py              # FastAPI application
  gpu_manager.py       # GPU resource management (CRITICAL)
  german_validator.py  # German text validation
tests/
  test_basic.py        # Smoke tests
```

## Critical Information
- **GPU Manager**: Single point of failure - manages RTX 4080
- **German Validation**: 100% accuracy required for business
- **Backends**: Not yet implemented (using mock responses)

## Next Steps
1. [OK] Basic API running
2. [OK] GPU detection working
3. [OK] German validation implemented
4. [ ] Implement first OCR backend (GOT-OCR)
5. [ ] Process first real document

## Known Issues
- No actual OCR backends implemented yet
- Using mock responses for testing
- Full 131-file structure not created (intentional - POC first)

## Configuration
```python
GPU_REQUIREMENTS = {
    "deepseek": 12,  # GB
    "got_ocr": 10,   # GB
    "surya": 0       # CPU only
}

GERMAN_REQUIREMENTS = {
    "umlaut_accuracy": 100,  # Percent
    "date_format": "DD.MM.YYYY",
    "currency_format": "1.234,56 €"
}
```

## References
- Full documentation: `.claude/Docs/`
- Implementation plan: `.claude/claude code structure preperation.md`
- Bootstrap script: `bootstrap_project.py`