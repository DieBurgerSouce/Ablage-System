---
name: memory-updater
description: Orchestrates modular CLAUDE.md updates for changed files (LOCAL OVERRIDE)
model: sonnet
permissionMode: bypassPermissions
---

# Memory Updater (Local Override for Modular Structure)

This is a LOCAL OVERRIDE of the auto-memory plugin's memory-updater agent.
It uses the modular memory structure specific to this project.

## Project Memory Structure

```
CLAUDE.md                    # Quick Reference (< 250 lines) - POINTER ONLY
.claude/
  CLAUDE.md                  # Core Reference (< 600 lines)
  memory/                    # AUTO-MANAGED dynamic content
    PROJECT_STATUS.md        # Service health, deployments
    KNOWN_ISSUES.md          # Bug tracking
    RECENT_CHANGES.md        # Changelog
    DEPENDENCIES.md          # Tech stack versions
  Docs/                      # Detailed documentation (verbose content)
```

## Workflow

### Phase 1: Load Dirty Files
1. Read `.claude/auto-memory/dirty-files` using Read tool
2. Parse each line - two formats:
   - Plain path: `/path/to/file`
   - With commit context: `/path/to/file [hash: commit message]`
3. Extract file paths and commit context, deduplicate
4. If empty or missing: return "No changes to process"

### Phase 2: Route Changes to Memory Files

| File Pattern | Target Memory File | Section |
|--------------|-------------------|---------|
| `requirements*.txt`, `pyproject.toml` | `DEPENDENCIES.md` | python |
| `package.json`, `package-lock.json` | `DEPENDENCIES.md` | frontend |
| `docker-compose*.yml` | `DEPENDENCIES.md` | infrastructure |
| `alembic/versions/*.py` | `PROJECT_STATUS.md` | migrations |
| `infrastructure/*`, `*.tf` | `PROJECT_STATUS.md` | infrastructure |
| Bug fix commits | `KNOWN_ISSUES.md` | resolved |
| `app/services/*.py` (new) | `RECENT_CHANGES.md` | backend |
| `frontend/src/**` (new) | `RECENT_CHANGES.md` | frontend |
| Critical rule changes | `.claude/CLAUDE.md` | critical-rules |
| New enterprise features | `.claude/CLAUDE.md` | enterprise-features |

### Phase 3: Update Memory Files

**For `.claude/memory/RECENT_CHANGES.md`:**
```markdown
## Recent Changes

### 2026-01-10
- **feat**: Added Lexware entity linking
- **fix**: Fixed GPU memory management

### 2026-01-09
- **refactor**: Reorganized document services
```

**For `.claude/memory/DEPENDENCIES.md`:**
```markdown
## Tech Stack

### Python (Backend)
| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.110+ | API Framework |
| pydantic | 2.6+ | Validation |

### Frontend
| Package | Version | Purpose |
|---------|---------|---------|
| react | 18.x | UI Framework |
```

**For `.claude/memory/PROJECT_STATUS.md`:**
```markdown
## Service Health

| Service | Status | Notes |
|---------|--------|-------|
| Backend | OK | Running on :8000 |
| Frontend | OK | Nginx :80 |
| Celery | OK | 2 workers |

## Recent Migrations

| Migration | Description |
|-----------|-------------|
| 090 | Lexware streckengeschaeft merge |
| 089 | Lexware fields |
```

**For `.claude/memory/KNOWN_ISSUES.md`:**
```markdown
## Active Issues

- **GPU**: VRAM spikes during batch OCR (workaround: limit concurrency)

## Resolved

| Date | Issue | Fix |
|------|-------|-----|
| 2026-01-10 | Memory leak in OCR | Fixed in `ocr_task.py` |
```

### Phase 4: Update CLAUDE.md (ONLY IF NEEDED)

**IMPORTANT**: Root `CLAUDE.md` is a POINTER only. Never add content.

Only update `.claude/CLAUDE.md` AUTO-MANAGED sections if:
- New enterprise feature added → Update `enterprise-features` summary
- Critical rule changed → Update `critical-rules` table
- Project status changed → Update `project-status` table

**Format for updates:**
```markdown
<!-- AUTO-MANAGED: section-name -->
Content here (summaries only, link to memory/ or Docs/)
<!-- /AUTO-MANAGED: section-name -->
```

### Phase 5: Size Validation & Auto-Pruning

Before saving, verify limits:
- Root `CLAUDE.md`: < 300 lines
- `.claude/CLAUDE.md`: < 600 lines
- Memory files: < 100 lines each (trigger pruning at 100)
- Total chars: < 40k

**Auto-Pruning Trigger:**
If RECENT_CHANGES.md exceeds 100 lines OR has entries older than 30 days:

1. **Identify old entries**: Parse `## YYYY-MM-DD` headers
2. **Calculate cutoff**: TODAY - 30 days
3. **Archive old entries**:
   - Read `.claude/Docs/Archive/CHANGELOG-YYYY-MM.md`
   - Append old entries (sorted by date)
   - Create file if doesn't exist
4. **Remove from memory file**: Keep only last 30 days
5. **Update index**: Add entry to `.claude/Docs/Archive/INDEX.md`

**Archive file format**:
```markdown
# Changelog Archive: January 2026

> Archived from `.claude/memory/RECENT_CHANGES.md`

## 2025-12-10
- **feat**: Feature description
- **fix**: Bug fix description
```

**KNOWN_ISSUES.md Pruning**:
- Keep ALL active issues (never archive)
- Keep last 20 resolved issues
- Archive older resolved to `.claude/Docs/Archive/ISSUES-YYYY.md`

**Report pruning in summary**:
```
Pruning: Archived 45 entries (Nov-Dec 2025) to Archive/CHANGELOG-2025-12.md
```

### Phase 6: Cleanup (MANDATORY)
**ALWAYS execute this phase**, even if no updates were needed.

1. Clear `.claude/auto-memory/dirty-files` using Write tool (write empty string)
2. Return summary:
   ```
   Updated memory files:
   - .claude/memory/RECENT_CHANGES.md: +3 entries
   - .claude/memory/DEPENDENCIES.md: Updated Python packages

   No changes to CLAUDE.md (summaries current)

   Size: 28k/40k chars (70%)
   ```

## Tool Usage

- **Read**: dirty-files, memory files, CLAUDE.md
- **Write**: Clear dirty-files (empty string)
- **Edit**: Update AUTO-MANAGED sections
- **Bash**: Git commands only (read-only)
- **Glob**: Find files

## Error Handling

- Missing file: Skip, note in summary
- Non-git repo: Skip git phase
- Empty dirty files: Return "No changes to process"
- Size limit exceeded: Truncate and warn

## Token Efficiency

- Max 100 lines per file read (summaries)
- Skip: binary files, node_modules, vendor, .git
- Batch similar changes together

Keep responses concise. Focus on what was updated.
