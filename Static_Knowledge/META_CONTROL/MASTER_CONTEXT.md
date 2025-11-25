# MASTER CONTEXT - Ablage-System OCR

## Current Reality (2024-11-22)
- **Documentation**: 36 files complete in `.claude/Docs/`
- **Code**: 7 POC files created (4 Python, 3 config)
- **Status**: Proof of Concept implemented, not production
- **Next Milestone**: Test POC, then implement first OCR backend

## Quick Navigation
- [Project Status](PROJECT_STATUS.json) - Live tracking
- [GPU Manager](../../app/gpu_manager.py) - Critical component
- [German Validator](../../app/german_validator.py) - 100% accuracy
- [Main API](../../app/main.py) - Entry point

## Priority Actions
1. Run tests: `pytest tests/test_basic.py -v`
2. Start API: `python app/main.py`
3. Check GPU: Access http://localhost:8000/gpu/status
4. Validate German: POST to /validate/german

## Critical Constraints
- **Single GPU**: RTX 4080 16GB - bottleneck
- **German**: 100% umlaut accuracy required
- **On-Premises**: No cloud dependencies
- **GDPR**: Full compliance required

## What Works Now
- [x] Basic FastAPI structure
- [x] GPU detection and management
- [x] German text validation
- [x] Test framework

## What's Missing
- [ ] Actual OCR backends (DeepSeek, GOT-OCR, Surya)
- [ ] Database connection
- [ ] Real document processing
- [ ] Production deployment

## Token Budget
Keep this file under 2K tokens for Claude Code efficiency.