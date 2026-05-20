# Auto-Memory: Modular Structure Configuration

This project uses a **modular memory structure** instead of a single CLAUDE.md file.
The local `memory-updater` agent (`.claude/agents/memory-updater.md`) overrides the
default auto-memory plugin behavior to route updates to the correct files.

## Structure

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
  auto-memory/
    config.json              # This configuration
    dirty-files              # Tracked changes (auto-managed)
```

## Size Constraints

| File | Max Lines | Purpose |
|------|-----------|---------|
| `CLAUDE.md` (root) | 300 | Quick reference pointer |
| `.claude/CLAUDE.md` | 600 | Core reference |
| `.claude/memory/*.md` | 150 each | Dynamic content |
| Total chars | 40,000 | All CLAUDE.md files combined |

## Routing Rules

Changes are routed to memory files based on file patterns:

| Changed File | Target Memory File |
|--------------|-------------------|
| `requirements*.txt`, `pyproject.toml`, `package.json` | `DEPENDENCIES.md` |
| `docker-compose*.yml`, `alembic/*`, `infrastructure/*` | `PROJECT_STATUS.md` |
| Bug fixes (commit message) | `KNOWN_ISSUES.md` |
| Feature additions | `RECENT_CHANGES.md` |

## AUTO-MANAGED Sections

Use these markers for auto-managed content:

```markdown
<!-- AUTO-MANAGED: section-name -->
Content here
<!-- /AUTO-MANAGED: section-name -->
```

**IMPORTANT**: Use `/AUTO-MANAGED` for closing tag (with forward slash), not `END AUTO-MANAGED`.

## Configuration Options

`config.json` settings:

```json
{
  "triggerMode": "default",     // "default" or "gitmode"
  "modularStructure": true,     // Enable modular routing
  "memoryLayout": {...},        // File paths
  "memoryFiles": {...},         // Routing rules
  "sizeConstraints": {...}      // Size limits
}
```

## How It Works

1. **PostToolUse hook**: Tracks file edits to `dirty-files`
2. **Stop hook**: Detects dirty files, spawns `memory-updater` agent
3. **memory-updater agent**: LOCAL OVERRIDE routes to modular structure
4. **Cleanup**: Clears `dirty-files` after processing

## Manual Sync

If auto-memory misses changes, run manually:

```
/auto-memory:sync
```

## Auto-Pruning & Archiving

Memory files are automatically pruned to prevent them from growing too large.

### Pruning Rules

| File | Keep | Archive To |
|------|------|------------|
| `RECENT_CHANGES.md` | Last 30 days | `Archive/CHANGELOG-YYYY-MM.md` |
| `KNOWN_ISSUES.md` | Active + 20 resolved | `Archive/ISSUES-YYYY.md` |
| `PROJECT_STATUS.md` | Current only | No archive (always current) |
| `DEPENDENCIES.md` | Current only | No archive (always current) |

### Trigger Conditions

Pruning is triggered when:
1. Memory file exceeds 100 lines
2. Entries are older than 30 days
3. Manually via `/auto-memory:calibrate`

### Archive Structure

```
.claude/Docs/Archive/
├── INDEX.md                    # Searchable index
├── CHANGELOG-2026-01.md        # January 2026 changes
├── CHANGELOG-2025-12.md        # December 2025 changes
└── ISSUES-2025.md              # 2025 resolved issues
```

### Searching Archives

```bash
# Search all archives
grep -r "keyword" .claude/Docs/Archive/

# Search specific period
grep "OCR" .claude/Docs/Archive/CHANGELOG-2026-01.md
```

## Troubleshooting

**Memory files too large?**
- Run `/auto-memory:calibrate` to force pruning
- Check `config.json` pruning rules

**Updates not appearing?**
- Check `dirty-files` has content
- Verify `config.json` routing rules
- Run `/auto-memory:status`

**Wrong file updated?**
- Check routing rules in `config.json`
- Adjust `memoryFiles` patterns

**Archive not created?**
- Ensure `.claude/Docs/Archive/` directory exists
- Check pruning is enabled in `config.json`
