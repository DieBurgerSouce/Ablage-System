# Development Map of Content

## Quick Navigation
- [Setup](#setup)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Debugging](#debugging)

## Setup
1. [SOP: Installing OCR Backends](../../Static_Knowledge/SOPs/001_installing_ocr_backends.md)
2. [GPU Management Skill](../../Static_Knowledge/Skills/gpu_management_skill.yaml)
3. Environment: `.env.example`

## Development Workflow
- Code in `app/`
- Tests in `tests/`
- Run: `pytest tests/ -v`
- Lint: `ruff check .`
- Type check: `mypy app/`

## Testing
- [test_basic.py](../../tests/test_basic.py) - 7 smoke tests
- Fixtures in `tests/fixtures/`
- Coverage target: 80%+

## Debugging
- [Error Log](../../Dynamic_Knowledge/Logs/error_log.jsonl)
- [Code Hotspots](../../Dynamic_Knowledge/Bookmarks/code_hotspots.yaml)
- [GPU OOM Learnings](../../Dynamic_Knowledge/Learnings/gpu_oom_learnings.md)
