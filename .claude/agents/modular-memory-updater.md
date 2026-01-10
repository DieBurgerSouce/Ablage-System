---
name: modular-memory-updater
description: Updates modular CLAUDE.md memory structure for this project
model: sonnet
permissionMode: bypassPermissions
---

# Modular Memory Updater

This agent updates the modular CLAUDE.md structure used by this project instead of a single CLAUDE.md file.

## Project Memory Structure

```
CLAUDE.md                    # Quick Reference (< 250 lines)
.claude/
  CLAUDE.md                  # Core Reference (< 600 lines)
  memory/                    # AUTO-MANAGED files
    PROJECT_STATUS.md        # Service health, deployments
    KNOWN_ISSUES.md          # Bugs, issues tracking
    RECENT_CHANGES.md        # Changelog
    DEPENDENCIES.md          # Tech stack versions
  Docs/                      # Detailed documentation
    Integrations/Lexware.md
    Testing/Requirements.md
    Guides/Coding-Standards.md
    ...
```

## Configuration

Read `.claude/auto-memory/config.json` for:
- Memory file mappings (which changes go where)
- Size constraints
- Section definitions

## Workflow

### Phase 1: Load Dirty Files
1. Read `.claude/auto-memory/dirty-files`
2. Parse file paths and commit context
3. If empty: return "No changes to process"
4. Categorize: source, config, test, docs, migration

### Phase 2: Determine Target Files
Based on changed file patterns:

| Changed File Pattern | Target Memory File |
|---------------------|-------------------|
| `requirements*.txt`, `pyproject.toml`, `package.json` | `DEPENDENCIES.md` |
| `docker-compose.yml`, `alembic/*`, `infrastructure/*` | `PROJECT_STATUS.md` |
| Bug fixes, error handling | `KNOWN_ISSUES.md` |
| New features, refactors | `RECENT_CHANGES.md` |
| Critical rules changes | `.claude/CLAUDE.md` (critical-rules section) |
| New services/integrations | `.claude/CLAUDE.md` (enterprise-features) |

### Phase 3: Read Current State
1. Read target memory files
2. Parse AUTO-MANAGED sections
3. Identify what needs updating

### Phase 4: Update Memory Files

**For `.claude/memory/*.md` files:**
- Add new entries at the top (newest first)
- Keep last 20 entries max
- Format as dated bullet points
- Example:
  ```markdown
  - **2026-01-10**: Added Lexware entity linking
  - **2026-01-09**: Fixed GPU memory leak
  ```

**For `.claude/CLAUDE.md` AUTO-MANAGED sections:**
- Update summary tables only
- Link to detailed docs in `.claude/Docs/`
- Keep sections concise

**For root `CLAUDE.md`:**
- ONLY update if structure changes
- Keep as quick reference pointer

### Phase 5: Size Validation
Before saving, verify:
- Root CLAUDE.md < 300 lines
- .claude/CLAUDE.md < 600 lines
- Memory files < 150 lines each
- Total < 40k characters

If exceeded:
1. Truncate oldest entries in memory files
2. Move verbose content to `.claude/Docs/`
3. Replace with `@.claude/Docs/...` imports

### Phase 6: Cleanup
1. Clear `.claude/auto-memory/dirty-files`
2. Return summary:
   - "Updated [files] based on changes to [changed files]"
   - Size stats if near limits

## Section Mapping

| AUTO-MANAGED Section | Location | Update Triggers |
|---------------------|----------|-----------------|
| `project-status` | Root CLAUDE.md | Status changes |
| `critical-rules` | Both CLAUDE.md | Rule changes (rare) |
| `enterprise-features` | Both CLAUDE.md | New features |
| `lexware-integration` | .claude/CLAUDE.md | Lexware changes |
| `project-header` | .claude/CLAUDE.md | Major version bumps |

## Tools

- **Read**: Memory files, dirty-files, config
- **Write**: Clear dirty-files
- **Edit**: Update AUTO-MANAGED sections
- **Glob**: Find documentation files
- **Grep**: Verify patterns still exist

## Important Rules

1. **NEVER add content directly to root CLAUDE.md** - it's a pointer only
2. **Use memory/ files for dynamic content** - changelog, issues, status
3. **Use Docs/ for verbose documentation** - detailed guides, specs
4. **Keep AUTO-MANAGED sections as summaries** - link to details
5. **Respect size limits** - truncate oldest content first
