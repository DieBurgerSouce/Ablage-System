# Claude Code Essentials - Quick Reference

## 🚀 Getting Started in 60 Seconds

### 1. Start Development Environment
```bash
make dev
# Or: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### 2. Access Services
- **API**: http://localhost:8000/docs
- **Database**: pgAdmin at http://localhost:5050
- **Queue Monitor**: Flower at http://localhost:5555

### 3. Run Your First Test
```bash
make test
# Or: ./scripts/test.sh
```

## 📝 Custom Slash Commands (USE THESE!)

| Command | Purpose | Example Use Case |
|---------|---------|------------------|
| `/quick-test` | Test current file | After editing `ocr_service.py` |
| `/implement-agent` | Generate full agent | Create new OCR backend |
| `/debug-gpu` | GPU diagnostics | CUDA errors, OOM issues |
| `/review-pr` | Code review | Before pushing changes |
| `/ocr-benchmark` | Quality testing | Validate OCR accuracy |
| `/setup-dev` | Environment setup | Onboarding new developer |
| `/add-feature` | Feature workflow | Implementing new functionality |
| `/find-doc` | Find documentation | "GPU problems" → troubleshooting guide |

## 🔍 Finding Things Fast

### Documentation Search
```bash
# By tag
grep "#gpu" Meta_Layer/Indexes/documentation_index.md
grep "#critical" Meta_Layer/Indexes/code_index.md

# By topic
/find-doc  # Then ask: "GPU problems", "OCR quality", etc.
```

### Code Navigation
```bash
# Find agent implementations
find app/ -name "*agent*.py"

# Find tests
find tests/ -name "test_*.py"

# Search function
grep -r "def process_document" app/
```

### Key Documentation Indexes
- **All Docs**: `Meta_Layer/Indexes/documentation_index.md`
- **All Code**: `Meta_Layer/Indexes/code_index.md`
- **Tags**: `Meta_Layer/Tags/tag_system.md`

## 💻 VSCode Integration

### Keyboard Shortcuts
- `Ctrl+Shift+B` - Build (default: Build All)
- `Ctrl+Shift+T` - Test (default: Run Tests)
- `F5` - Start Debugging
- `Ctrl+Shift+P` → "Tasks" - Access all 20+ tasks

### Quick Tasks (Ctrl+Shift+P → Tasks: Run Task)
- **Run Tests** - Execute pytest
- **Lint Code** - Ruff + MyPy
- **Start Development Server** - Launch FastAPI with reload
- **Docker Compose - Up** - Start all services
- **Check GPU Status** - nvidia-smi

### Debug Configurations (F5)
- **FastAPI: Debug Server** - Debug backend API
- **Celery: Debug Worker** - Debug async tasks
- **pytest: Debug Current File** - Debug tests
- **Attach to Container: Backend** - Debug in Docker

### Code Snippets (Type prefix + Tab)
- `agent` → Full async agent class
- `router` → FastAPI router with CRUD
- `test` → Async test function (AAA pattern)
- `model` → SQLAlchemy model
- `schema` → Pydantic schema
- `task` → Celery task with retry

## 🛠️ Common Development Tasks

### Testing
```bash
# Quick test
make test                    # All tests
make test-unit              # Unit tests only (fast)
make test-gpu               # GPU tests only

# With options
./scripts/test.sh --coverage     # With coverage report
./scripts/test.sh --gpu          # GPU tests
./scripts/test.sh --parallel     # Parallel execution
```

### Code Quality
```bash
make lint                   # Check code quality
make lint-fix              # Auto-fix issues
make format                # Format code
```

### Docker
```bash
make dev                   # Start dev environment
make logs                  # Follow all logs
make shell-backend         # Open backend shell
make db-shell              # PostgreSQL shell
make clean                 # Remove containers
```

### Database
```bash
make db-migrate            # Run migrations
make db-reset              # Reset database (destroys data!)
make db-backup             # Backup to file
```

## 🐛 Debugging Quick Wins

### GPU Issues
```bash
make gpu-status            # Check GPU
make gpu-test              # Test GPU in container
nvidia-smi                 # Detailed GPU info
```

### Application Issues
```bash
make health                # Check service health
make urls                  # Show all service URLs
make logs-backend          # Backend logs only
```

### Common Fixes
```bash
# Services not starting?
make recreate              # Rebuild everything

# Database connection issues?
make db-migrate            # Ensure migrations applied

# GPU not detected?
/debug-gpu                 # Run GPU diagnostics
```

## 🚨 Pre-Commit Checklist

Before EVERY commit:
```bash
# 1. Run tests
make test

# 2. Check code quality
make lint

# 3. Verify changes
git status
git diff

# 4. Commit (hooks run automatically)
git add .
git commit -m "feat(ocr): add DeepSeek backend"
```

Git hooks will automatically check:
- ✓ Ruff linting
- ✓ Code formatting
- ✓ MyPy type checking
- ✓ No debugging code
- ✓ No secrets

## 📊 Performance Targets (Keep These in Mind)

### Response Time Targets
- Health Check: **< 50ms**
- Document Upload: **< 500ms**
- OCR Processing: **< 2s** (GPU), **< 10s** (CPU)

### GPU Limits (RTX 4080)
- Max VRAM Usage: **13.6GB** (85% of 16GB)
- Optimal Batch Size: **16-32** documents
- Processing Rate: **100+ pages/minute**

### Coverage Requirements
- Overall: **80%** minimum
- Critical Paths: **95%+** required
- New Code: **100%** before merge

## 🔒 Security Reminders

### NEVER:
- ❌ Log sensitive data (documents, PII, secrets)
- ❌ Commit `.env` files or secrets
- ❌ Use hardcoded credentials
- ❌ Skip input validation
- ❌ Use `print()` instead of `logger`

### ALWAYS:
- ✅ Use environment variables for secrets
- ✅ Validate all user input
- ✅ Use parameterized SQL queries
- ✅ Enable HTTPS in production
- ✅ Use structured logging (structlog)

## 🎯 German Language Requirements

### User-Facing Text
```python
# ✅ CORRECT
ERROR_MESSAGES = {
    "not_found": "Dokument nicht gefunden",
    "invalid_input": "Ungültige Eingabe"
}

# ❌ WRONG
ERROR_MESSAGES = {
    "not_found": "Document not found"
}
```

### OCR Quality
- Umlaut Accuracy: **>95%** required
- Encoding: **UTF-8** mandatory
- ß vs ss: Must handle correctly

## 🆘 Getting Help

### Quick Help Commands
```bash
make help                  # Show all Makefile targets
/find-doc                 # Search documentation
grep "#yourtopic" Meta_Layer/Indexes/documentation_index.md
```

### Common Questions
1. **"How do I implement an agent?"**
   - Use `/implement-agent` OR
   - Read `Static_Knowledge/Architecture/agent_implementation_patterns.md`

2. **"GPU not working?"**
   - Use `/debug-gpu` OR
   - Read `Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md`

3. **"Tests failing?"**
   - Check `pytest` output carefully
   - Use `./scripts/test.sh -v` for verbose
   - Debug with VSCode: F5 → "pytest: Debug Current File"

4. **"Code review needed?"**
   - Use `/review-pr` OR
   - Read `Static_Knowledge/Checklists/code_review_checklist.md`

## 📚 Key Files to Bookmark

### Must-Read Documentation
1. `CLAUDE.md` - Main project instructions
2. `GETTING_STARTED.md` - Onboarding guide
3. `.claude/.clauderc` - Quick reference (this guide's parent)
4. `Meta_Layer/Indexes/documentation_index.md` - Find all docs

### Architecture & Patterns
1. `Static_Knowledge/Architecture/agent_implementation_patterns.md`
2. `Static_Knowledge/Patterns/async_patterns.md`
3. `Relations/Integration_Maps/component_integration_map.md`

### Troubleshooting
1. `Execution_Layer/Troubleshooting/gpu_troubleshooting_guide.md`
2. `Execution_Layer/Troubleshooting/ocr_quality_troubleshooting.md`

## 🎓 Learning Path for New Developers

### Day 1: Setup
1. Run `make setup` (installs everything)
2. Read `GETTING_STARTED.md`
3. Run `/setup-dev` for guided setup
4. Start dev environment: `make dev`
5. Run first test: `make test`

### Day 2: Code Exploration
1. Read `CLAUDE.md` completely
2. Browse `Meta_Layer/Indexes/documentation_index.md`
3. Try slash commands (`/find-doc`, `/quick-test`)
4. Read one agent implementation in `app/services/`

### Day 3: First Contribution
1. Use `/add-feature` for workflow guidance
2. Implement small feature with tests
3. Run `/review-pr` before pushing
4. Create PR

## 💡 Pro Tips

### Productivity Hacks
- **Use Makefile**: `make` + Tab shows all commands
- **Use Slash Commands**: Faster than manual lookup
- **Use VSCode Tasks**: `Ctrl+Shift+P` → Tasks
- **Tag-Based Search**: Faster than full-text search

### Avoid Common Mistakes
- Don't skip tests (pre-push hook will catch it anyway)
- Don't use `--no-verify` on commits (defeats hooks)
- Don't forget `await` in async functions
- Don't exceed 85% GPU memory (13.6GB)
- Don't use English for user messages

### Time Savers
```bash
# Alias these in your shell
alias ad='make dev'           # Start development
alias at='make test'          # Run tests
alias al='make lint'          # Lint code
alias alogs='make logs'       # Follow logs
```

---

**Remember**: This is an enterprise system. Quality > Speed. Security is paramount. Tests are mandatory. German accuracy is non-negotiable.

**Philosophy**: "Feinpoliert und durchdacht" - Every detail matters.
