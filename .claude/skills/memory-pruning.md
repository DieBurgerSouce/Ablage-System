---
name: memory-pruning
description: Prunes and archives old entries from memory files to keep them under size limits. Transfers older content to archive while maintaining searchable index.
---

# Memory Pruning Skill

Automatically prune memory files and transfer old content to archive.

## Trigger Conditions

This skill should be invoked:
1. When a memory file exceeds 100 lines
2. When entries are older than 30 days
3. Manually via `/auto-memory:calibrate`

## Algorithm

### 1. Check File Sizes

```python
THRESHOLDS = {
    "RECENT_CHANGES.md": {
        "max_lines": 100,
        "keep_days": 30,
        "archive_to": "Archive/CHANGELOG-{year}-{month}.md"
    },
    "KNOWN_ISSUES.md": {
        "max_lines": 80,
        "keep_resolved": 20,  # Keep last 20 resolved issues
        "archive_to": "Archive/ISSUES-{year}.md"
    },
    "PROJECT_STATUS.md": {
        "max_lines": 100,
        "no_archive": True  # Always current, no history
    },
    "DEPENDENCIES.md": {
        "max_lines": 120,
        "no_archive": True  # Current state only
    }
}
```

### 2. Parse Entries by Date

For RECENT_CHANGES.md:
```markdown
## 2026-01-10
### Features
- Entry 1
- Entry 2

## 2026-01-09
...
```

Extract date from `## YYYY-MM-DD` headers.

### 3. Determine What to Archive

```
TODAY = 2026-01-10

Keep in RECENT_CHANGES.md:
- 2026-01-10 (today) ✓
- 2026-01-09 (1 day ago) ✓
- ...
- 2025-12-11 (30 days ago) ✓
- 2025-12-10 (31 days ago) → ARCHIVE

Archive to:
- Archive/CHANGELOG-2025-12.md
- Archive/CHANGELOG-2025-11.md
```

### 4. Transfer to Archive

**Archive file format** (CHANGELOG-2026-01.md):
```markdown
# Changelog Archive: January 2026

> Archived from `.claude/memory/RECENT_CHANGES.md`
> Archive Date: 2026-02-01

## 2026-01-31
- Feature X added
- Bug Y fixed

## 2026-01-30
...
```

**Append to existing archive** (don't overwrite):
1. Read existing archive file
2. Merge new entries (sorted by date)
3. Write combined file

### 5. Update Index

After archiving, update `.claude/Docs/Archive/INDEX.md`:

```markdown
# Archive Index

Quick reference to archived documentation.

## Changelogs

| Period | File | Entries |
|--------|------|---------|
| Jan 2026 | `CHANGELOG-2026-01.md` | 45 |
| Dec 2025 | `CHANGELOG-2025-12.md` | 62 |
| Nov 2025 | `CHANGELOG-2025-11.md` | 38 |

## Issues

| Year | File | Resolved |
|------|------|----------|
| 2025 | `ISSUES-2025.md` | 127 |

## Search Tips

- Use `grep -r "keyword" .claude/Docs/Archive/` to search archives
- Each archive preserves original date headers
```

### 6. Prune Memory File

After archiving:
1. Remove archived entries from memory file
2. Keep only recent entries (last 30 days)
3. Update AUTO-MANAGED section

### 7. Report Summary

```
Memory Pruning Complete:

RECENT_CHANGES.md:
  - Before: 156 lines
  - Archived: 89 lines (Dec 2025)
  - After: 67 lines

Archived to:
  - .claude/Docs/Archive/CHANGELOG-2025-12.md (+89 lines)

Index updated: .claude/Docs/Archive/INDEX.md
```

## KNOWN_ISSUES.md Pruning

Different logic for issues:

1. **Active Issues**: Keep ALL (never archive active)
2. **Resolved Issues**: Keep last 20, archive older

```markdown
## Active Issues
- [ACTIVE] GPU memory spike... (KEEP)

## Resolved
| Date | Issue | Fix |
| 2026-01-10 | ... | ... | (KEEP - recent)
| 2025-11-15 | ... | ... | (ARCHIVE - old)
```

## Edge Cases

- **Empty archive**: Create new file with header
- **Duplicate dates**: Merge entries under same date
- **Malformed dates**: Keep in place, log warning
- **No entries to archive**: Report "No pruning needed"

## Tools

- **Read**: Memory files, existing archives
- **Write**: New archive files
- **Edit**: Update memory files, INDEX.md
- **Glob**: Find existing archive files
