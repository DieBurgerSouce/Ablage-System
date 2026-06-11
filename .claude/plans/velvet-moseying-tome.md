> **Status (W1-048, 2026-06-11)**: UMGESETZT als `/docu` (`.claude/commands/docu.md` existiert; Name weicht vom Plan-Titel `/doco` ab).
> Plan archivierbar; Abweichungen ggü. Plan bei Bedarf direkt am Command pflegen.

# Plan: `/doco` Slash Command - Session-Dokumentation & Commit Agent

## Context

After each Claude Code session, the user types "document and commit" as free-text. This is error-prone, inconsistent, and pollutes the main context. Goal: A dedicated `/doco` command that spawns a specialized agent with fresh context to analyze all uncommitted changes, update memory files + CHANGELOG.md, create intelligent staged Conventional Commits, and prune the bloated RECENT_CHANGES.md.

## Files to Create

### 1. `.claude/commands/doco.md` (~40 lines)
- User-facing slash command that instructs Claude to spawn the `session-documenter` agent via Task tool
- Short description of what happens

### 2. `.claude/agents/session-documenter.md` (~280 lines)
- YAML frontmatter: `model: sonnet`, `permissionMode: bypassPermissions`
- Complete 7-phase workflow (Reconnaissance, Analyse, Docs Prep, Pruning, Code Commits, Docs Commit, Summary)

## Agent Workflow Summary

| Phase | Action | Tools |
|-------|--------|-------|
| 1. Reconnaissance | `git status`, `git diff --stat`, `git log -5` | Bash |
| 2. Analyse | Categorize files into scope-buckets, form 2-5 commit groups | Bash, Read |
| 3. Docs Prep | Read memory files + CHANGELOG, prepare updates | Read |
| 4. Pruning | If RECENT_CHANGES.md > 50 lines: archive old entries to `.claude/Docs/Archive/` | Read, Write, Edit |
| 5. Code Commits | Selective `git add` + conventional commits per scope-group | Bash |
| 6. Docs Commit | Write memory updates, stage + commit docs | Edit, Write, Bash |
| 7. Summary | Report to user: commits, updates, pruning results | - |

## Scope-Buckets (from plan)

| Bucket | Pattern | Prefix |
|--------|---------|--------|
| ocr | `app/agents/ocr/*`, `app/services/ocr/*`, `app/ml/*` | feat/fix(ocr) |
| api | `app/api/*` | feat/fix(api) |
| security | `app/core/security/*`, `*credential*`, `*pii*` | fix/feat(security) |
| frontend | `frontend/*` | feat/fix(frontend) |
| db | `app/db/*`, `alembic/*` | feat/fix(db) |
| services | `app/services/*` (catch-all) | feat/fix(services) |
| workers | `app/workers/*` | feat/fix(workers) |
| infra | `docker-compose*`, `infrastructure/*`, `requirements.txt` | chore(infra) |
| orchestration | `.claude/orchestration/*`, `.claude/hooks/*` | feat/fix(orchestration) |
| tests | `tests/*` | test(scope) |

## Key Design Decisions

- **Sonnet model**: Good analytical ability for diff-parsing + categorization. Haiku too weak, Opus too expensive.
- **bypassPermissions**: Agent needs `git add`, `git commit`, and Edit access without user prompts.
- **Commit order**: infra -> db -> services -> api -> frontend -> tests (dependencies first)
- **Pruning threshold**: 50 lines max for RECENT_CHANGES.md, 14-day cutoff, archive to `.claude/Docs/Archive/CHANGELOG-YYYY-MM.md`
- **Buckets < 3 files**: Merged into related buckets
- **100+ files**: Only `--stat` + `--name-only`, max 30 full diffs
- **Co-Authored-By**: Every commit ends with `Co-Authored-By: claude-flow <ruv@ruv.net>`

## Reused Patterns

| Source | What's reused |
|--------|--------------|
| `.claude/agents/memory-updater.md` | YAML frontmatter format, routing table structure, pruning logic, size limits, archive format |
| `.claude/memory/RECENT_CHANGES.md` | Date format `## YYYY-MM-DD` |
| `CHANGELOG.md` | Keep a Changelog format, `[Unreleased]` structure |
| `.claude/commands/quick-test.md` | Command file format (plain markdown instructions) |

## Verification

1. `/doco` recognized in Claude Code
2. Agent spawns with fresh context
3. Clean tree -> "Keine Aenderungen" + exit
4. Dirty tree -> 2-6 conventional commits that pass pre-commit hooks
5. RECENT_CHANGES.md updated with new dated entry
6. CHANGELOG.md `[Unreleased]` section updated
7. First run: RECENT_CHANGES.md pruned from ~3700 to ~50 lines
