---
name: modular-memory-processor
description: Process file changes and update modular CLAUDE.md memory structure. Routes updates to appropriate memory files (PROJECT_STATUS.md, KNOWN_ISSUES.md, RECENT_CHANGES.md, DEPENDENCIES.md) instead of bloating the main CLAUDE.md.
---

# Modular Memory Processor

Process changed files and route updates to the correct memory file in the modular structure.

## Memory File Routing

| Change Type | Target File | Section |
|-------------|-------------|---------|
| Dependencies changed | `.claude/memory/DEPENDENCIES.md` | tech-stack |
| Docker/infra changed | `.claude/memory/PROJECT_STATUS.md` | service-health |
| Bug fixed | `.claude/memory/KNOWN_ISSUES.md` | resolved |
| New bug found | `.claude/memory/KNOWN_ISSUES.md` | active |
| Feature added | `.claude/memory/RECENT_CHANGES.md` | changelog |
| Migration added | `.claude/memory/PROJECT_STATUS.md` | migrations |
| Critical rule change | `.claude/CLAUDE.md` | critical-rules |

## Algorithm

### 1. Parse Context
Read context from memory-updater:
- Changed files list
- File categories (source, config, test, docs)
- Commit messages (if available)

### 2. Classify Changes

```python
ROUTING = {
    # Dependencies
    "requirements*.txt": ("DEPENDENCIES.md", "python"),
    "pyproject.toml": ("DEPENDENCIES.md", "python"),
    "package.json": ("DEPENDENCIES.md", "frontend"),
    "docker-compose.yml": ("DEPENDENCIES.md", "infrastructure"),

    # Status
    "alembic/versions/*.py": ("PROJECT_STATUS.md", "migrations"),
    "infrastructure/*": ("PROJECT_STATUS.md", "infrastructure"),

    # Issues
    "**/test_*.py": ("KNOWN_ISSUES.md", "testing"),

    # Changelog
    "app/services/*.py": ("RECENT_CHANGES.md", "backend"),
    "frontend/src/**": ("RECENT_CHANGES.md", "frontend"),
}
```

### 3. Update Memory Files

**Format for memory files:**
```markdown
<!-- AUTO-MANAGED: section-name -->
## Section Name

| Date | Change | File |
|------|--------|------|
| 2026-01-10 | Added X | `path/to/file` |
| 2026-01-09 | Fixed Y | `path/to/file` |

<!-- /AUTO-MANAGED: section-name -->
```

**For changelog (RECENT_CHANGES.md):**
```markdown
## Recent Changes

### 2026-01-10
- **feat**: Added Lexware entity linking (`app/services/entity_*.py`)
- **fix**: Fixed GPU memory leak (`app/workers/ocr_task.py`)

### 2026-01-09
- **refactor**: Reorganized document services
```

### 4. Prune Old Entries

Keep only:
- Last 30 days of changes in RECENT_CHANGES.md
- Last 20 resolved issues in KNOWN_ISSUES.md
- Current tech stack in DEPENDENCIES.md (no history)
- Current status in PROJECT_STATUS.md (no history)

### 5. Update CLAUDE.md Summaries

Only if major changes:
- New enterprise feature → Update enterprise-features section
- New critical rule → Update critical-rules section
- Major version bump → Update project-header

**NEVER add verbose content to CLAUDE.md** - keep summaries and link to memory files or Docs/.

### 6. Validate Size

```
MAX_LINES = {
    "CLAUDE.md": 300,
    ".claude/CLAUDE.md": 600,
    ".claude/memory/*.md": 150 each,
}
```

If exceeded:
1. Truncate oldest entries
2. Archive to `.claude/Docs/Archive/`
3. Log warning

## Output

Return brief summary:
```
Updated .claude/memory/RECENT_CHANGES.md:
  - Added 3 changelog entries from today's commits

Updated .claude/memory/DEPENDENCIES.md:
  - Updated Python dependencies (pydantic 2.6.0 → 2.7.0)

No changes needed for CLAUDE.md (summaries still current)
```

## Critical Rules

1. **Route to memory files** - NEVER add new content directly to CLAUDE.md
2. **Keep summaries short** - Link to details in memory/ or Docs/
3. **Date entries** - Always include date for changelog/issues
4. **Prune regularly** - Remove entries older than 30 days
5. **Validate sizes** - Check against limits before saving
