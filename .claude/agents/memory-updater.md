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
  CLAUDE.md                  # Core Reference (< 400 lines) - SUMMARIES ONLY
  memory/                    # AUTO-MANAGED dynamic content (< 100 lines each)
    PROJECT_STATUS.md        # Service health, deployments
    KNOWN_ISSUES.md          # Bug tracking
    RECENT_CHANGES.md        # Changelog (< 3KB!)
    DEPENDENCIES.md          # Tech stack versions
  Docs/                      # Detailed documentation (verbose content HERE)
    Frontend/
      Patterns.md            # Frontend patterns, hooks, infinite scroll (WRITE DETAILS HERE)
      Components.md          # UI component docs (WRITE DETAILS HERE)
    Integrations/
      Lexware.md             # Lexware import, entity linking (WRITE DETAILS HERE)
    Archive/
      CHANGELOG-YYYY-MM.md   # Archived changes
```

**CRITICAL**: `.claude/CLAUDE.md` contains SUMMARIES ONLY (< 400 lines, < 15KB).
All verbose content MUST go to `Docs/` subdirectories.

## Workflow

### Phase 1: Load Dirty Files
1. Read `.claude/auto-memory/dirty-files` using Read tool
2. Parse each line - two formats:
   - Plain path: `/path/to/file`
   - With commit context: `/path/to/file [hash: commit message]`
3. Extract file paths and commit context, deduplicate
4. If empty or missing: return "No changes to process"

### Phase 2: Route Changes to Target Files

**ROUTING PRIORITY** (check in order, stop at first match):

| File Pattern | Target File | Content Type |
|--------------|-------------|--------------|
| `frontend/src/**/components/**` | `Docs/Frontend/Components.md` | Component docs (verbose OK) |
| `frontend/src/**/hooks/**` | `Docs/Frontend/Patterns.md` | Hook patterns (verbose OK) |
| `frontend/src/**/*api*.ts` | `Docs/Frontend/Patterns.md` | API patterns (verbose OK) |
| `app/services/*lexware*` | `Docs/Integrations/Lexware.md` | Lexware details (verbose OK) |
| `app/services/*entity*` | `Docs/Integrations/Lexware.md` | Entity linking (verbose OK) |
| `app/api/v1/entities*` | `Docs/Integrations/Lexware.md` | Entity API (verbose OK) |
| `requirements*.txt`, `pyproject.toml` | `memory/DEPENDENCIES.md` | Version updates |
| `package.json` | `memory/DEPENDENCIES.md` | Frontend deps |
| `docker-compose*.yml` | `memory/DEPENDENCIES.md` | Infra deps |
| `alembic/versions/*.py` | `memory/PROJECT_STATUS.md` | Migration notes |
| Bug fix commits | `memory/KNOWN_ISSUES.md` | Resolved issues |
| `app/services/*.py` | `memory/RECENT_CHANGES.md` | 1-line summary ONLY |
| `frontend/src/**` | `memory/RECENT_CHANGES.md` | 1-line summary ONLY |

**NEVER write to `.claude/CLAUDE.md`** unless:
- New CRITICAL RULE added (security, GPU, etc.)
- Major new enterprise feature (e.g., new integration like "Datev")

For existing features (Lexware, Frontend patterns), update the Docs/ files instead.

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

### Phase 3b: Update Docs/ Files (Verbose Content)

**For Frontend changes** → Write to appropriate Docs/Frontend/ file:

```markdown
# In Docs/Frontend/Components.md - Add component documentation
## CategoryDocumentList Component

**Path**: `features/ablage/components/CategoryDocumentList.tsx`

**Architecture**: 8-component orchestration...
[Full verbose documentation here]
```

```markdown
# In Docs/Frontend/Patterns.md - Add pattern documentation
## Infinite Scroll Pattern

**Applied to**: KundenPage, LieferantenPage
[Full code examples here]
```

**For Lexware/Entity changes** → Write to `Docs/Integrations/Lexware.md`:
```markdown
## Entity API Updates

**New Endpoint**: `/api/v1/entities/folders`
[Full documentation here]
```

### Phase 4: Update CLAUDE.md (ALMOST NEVER)

**CRITICAL**: `.claude/CLAUDE.md` must stay under 400 lines / 15KB.

**DO NOT UPDATE `.claude/CLAUDE.md` for:**
- ❌ Frontend component changes → Use `Docs/Frontend/Components.md`
- ❌ Frontend pattern changes → Use `Docs/Frontend/Patterns.md`
- ❌ Lexware/Entity changes → Use `Docs/Integrations/Lexware.md`
- ❌ Bug fixes → Use `memory/KNOWN_ISSUES.md`
- ❌ Regular feature updates → Use `memory/RECENT_CHANGES.md`

**ONLY update `.claude/CLAUDE.md` if:**
- ✅ NEW critical security rule (add 1 line to critical-rules table)
- ✅ BRAND NEW integration (not Lexware updates, but e.g. "Datev" added)
- ✅ Architecture fundamentally changed

**When updating, use SUMMARY format only:**
```markdown
<!-- AUTO-MANAGED: section-name -->
**One-liner summary**. Details: See `Docs/path/to/file.md`
<!-- /AUTO-MANAGED: section-name -->
```

### Phase 5: Size Validation & Auto-Pruning

**STRICT SIZE LIMITS** (trigger pruning/error if exceeded):

| File | Max Lines | Max Size | Action if Exceeded |
|------|-----------|----------|-------------------|
| Root `CLAUDE.md` | 250 | 8KB | ERROR - never grow |
| `.claude/CLAUDE.md` | 400 | 15KB | ERROR - extract to Docs/ |
| `memory/RECENT_CHANGES.md` | 50 | 3KB | AUTO-PRUNE to Archive |
| `memory/KNOWN_ISSUES.md` | 80 | 5KB | Archive old resolved |
| `memory/PROJECT_STATUS.md` | 60 | 4KB | Truncate old entries |
| `memory/DEPENDENCIES.md` | 80 | 5KB | Remove outdated |
| `Docs/**/*.md` | 500 | 30KB | OK - verbose allowed |

**Auto-Pruning Trigger:**
If RECENT_CHANGES.md exceeds 50 lines OR has entries older than 14 days:

1. **Identify old entries**: Parse `## YYYY-MM-DD` headers
2. **Calculate cutoff**: TODAY - 14 days
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
