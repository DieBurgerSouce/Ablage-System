# Quick Test Command

Run the test suite for the current file or module.

**Instructions:**
1. Identify the current file context
2. Find corresponding test file in tests/
3. Run pytest with appropriate flags:
   - `-v` for verbose output
   - `--cov` for coverage
   - `-x` to stop on first failure
4. If tests fail, analyze output and suggest fixes
5. Show coverage report

**Example:**
```bash
# For app/services/ocr_service.py
pytest tests/services/test_ocr_service.py -v --cov=app.services.ocr_service --cov-report=term-missing -x
```

**After running:**
- Show pass/fail status
- Highlight coverage gaps
- Suggest improvements if coverage <80%
