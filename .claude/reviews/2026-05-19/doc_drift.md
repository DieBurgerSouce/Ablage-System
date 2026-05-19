# Doc & Roadmap Drift Review

**Date:** 2026-05-19
**Scope:** 22 uncommitted markdown files + RAG plan vs implementation gap
**Top finding:** A markdown auto-formatter (Prettier/remark with table plugin disabled) ran across most docs and **destroyed every pipe-table**, collapsing header/row pipes into a single run-on line. Three ANALYSIS_* files additionally lost 343 lines of real content.

---

## Per-file Diff Summary

| File | What changed | Classification | Notes |
|------|--------------|----------------|-------|
| `CLAUDE.md` | All 10+ pipe-tables collapsed to single lines (Tier-Routing, Auto-Swarm Strategy, Agent Routing, V3 CLI commands, Hooks, Workers, V3 Targets). Multi-line metadata joined. Stray ``` fence inserted in spawn example. Added "Knowledge System (READ FIRST)" header pointing to Obsidian Vault. | **Improvement** (Vault pointer) + **Drift** (formatter damage) | Knowledge-System block is intentional; rest is formatter regression |
| `README.md` | `<div align="center">` badges block collapsed to one line, badges concatenated. Component table flattened to run-on text. URLs wrapped in `<>`. | **Drift** | No content loss, pure cosmetic regression |
| `CHANGELOG.md` | New `Fixed` section added documenting Slack-Spam-Sweep, Qdrant scrape token, worker healthcheck, alert-rule hygiene (matches commits 438f2486 / 7e012828). Filenames like `documents.py` linkified to `<http://documents.py>` (broken). `\[Unreleased\]` backslash-escaped. | **Improvement** (new entries valid) + **Drift** (auto-link corruption) | Auto-link wrapper is incorrect — needs revert |
| `PlanRAGAblage.md` | Version/Status/Zielgruppe metadata block collapsed to one line. Kernfähigkeiten table flattened. Stray ``` fence inserted inside ASCII data-flow diagram (lines 110, breaks rendering). | **Drift** | RAG spec content otherwise intact |
| `ANALYSIS_DETAILED_FINDINGS.md` | **-185 / +31 lines.** All tables flattened. Plus large sections of real content removed (services-by-size detail, security feature breakdown). | **Drift + Stale-data** | Worst regression — substantive content lost |
| `ANALYSIS_ENTERPRISE_ROADMAP.md` | **-77 / +27.** Tables flattened, roadmap items truncated. | **Drift + Stale-data** | Roadmap detail lost |
| `ANALYSIS_EXECUTIVE_SUMMARY.md` | **-81 / +9.** All scorecards, strength/weakness tables, GoBD/GDPR/codebase metrics tables collapsed. | **Drift + Stale-data** | Numbers preserved but unreadable |
| `.claude/plan.md` | Bullet checkboxes escaped to `\[x\]`. Headings spaced. Inline section "What's needed (frontend)" inadvertently merged with list item 3 due to formatter line-join. `>10k` escaped to `&gt;10k`. | **Drift** | Minor semantic damage (frontend section merge) |
| `.claude/ORCHESTRATION_ENTERPRISE_PLAN.md` | Status/Ziel/Version metadata collapsed. Stray ``` fence inserted in code sample around line 121. | **Drift** | Cosmetic + one broken code-block |
| `.claude/plans/breezy-napping-hare.md` | +11 lines — likely roadmap status updates (the Cross-Instance Tracking Protocol target). | **Improvement** | Expected per CLAUDE.md protocol — must verify content |
| `Static_Knowledge/ADRs/002_gpu_fallback_mechanism.md` | Status/Date/DecisionMakers metadata collapsed to one line. Blank lines added before bullet lists (CommonMark-compliant). | **Drift** (metadata) + **Improvement** (list spacing) | Net neutral |
| `Static_Knowledge/ADRs/003_german_text_normalization.md` | Same metadata-collapse pattern. `<50ms` escaped to `&lt;50ms`. Trailing blank-line removed. | **Drift** | |
| `Static_Knowledge/ADRs/005_api_versioning_strategy.md` | Same metadata-collapse pattern. | **Drift** | |
| `Static_Knowledge/SOPs/004_security_incident_response.md` | Metadata collapsed. Roles table flattened (lost row separators). Markdown bold `**DPO (Data Protection Officer)**` mangled to `**DPO (Data Protection Officer**)` — bracket moved outside emphasis. | **Drift** | Bracket-move is a real bug |
| `Static_Knowledge/SOPs/005_database_backup_restore.md` | Metadata collapsed. List spacing added. | **Drift** | Minor |
| `Dynamic_Knowledge/Learnings/german_ocr_challenges.md` | Metadata collapsed. Stray ``` inserted inside Case 3 example block. Blank lines added before lists. | **Drift** | Broken example fence |
| `Dynamic_Knowledge/Learnings/gpu_oom_learnings.md` | Metadata collapsed. List spacing added. Incident #1 metadata join. | **Drift** | |
| `docs/INFRASTRUCTURE_STATUS.md` | Date/Status/Branch collapsed. Container-status table (19 rows) flattened — **major readability loss**. Scrape-targets table flattened. Stray ``` inserted in rebuild command block. | **Drift** | Operational reference impaired |
| `docs/OCR_EVALUATION_2025.md` | Header metadata collapsed. All 4 comparison tables (Backends, Tests, OSS Champions, Established Performers) flattened. | **Drift** | Comparative data unreadable |
| `docs/PADDLEOCR_COMMERCIAL_INFO.md` | Header collapsed. Tech-data table flattened. Stray ``` inside ASCII license box. | **Drift** | |
| `docs/guides/EINVOICE_GUIDE.md` | Components table flattened (factur-x vs Mustang). | **Drift** | |
| `docs/guides/STRUCTURED_LOGGING.md` | Only 3 lines added — blank lines before lists + one stray ``` fence inside JSON example (line 121). | **Drift** | Broken JSON example |

---

## RAG Plan vs Reality Gap

**Spec source:** `PlanRAGAblage.md` v1.0.0 (2025-12-03)
**Impl source:** `app/services/rag/` (16 files, 9 399 LOC), `app/api/v1/rag.py` (1700+ LOC, ~30 endpoints), `alembic/versions/033_add_rag_tables.py`

### Done (spec promises met or exceeded)

- **DB schema (Sec 2.2):** Migration 033 creates all six required tables (`rag_document_chunks`, `rag_customer_cards`, `rag_chat_sessions`, `rag_chat_messages`, `rag_llm_models`, `rag_batch_jobs`) plus `rag_semantic_search()` / `rag_hybrid_search()` Postgres functions.
- **Chunking (Sec 3.2):** `chunking_service.py` (624 LOC) with `ChunkConfig`, document-chunking, embedding generation, rechunk-API.
- **Search (Sec 5.2):** `search_service.py` implements semantic, hybrid (vector + keyword), keyword-only, and reranking; `qdrant_service.py` adds an alternative vector backend with batch upsert + retry.
- **Chat (Sec 5.3):** `chat_service.py` + streaming endpoint (`POST /rag/chat/stream`), session CRUD, source-attribution.
- **Customer Cards (Sec 5.4):** `customer_card_service.py` with generate/refresh/search/sync-all.
- **LLM Router (Sec 3.1):** `llm_service.py` has `ModelRouter`, `LLMContextType` enum, generate/stream/health/list/pull.
- **Metrics (Sec 10):** `metrics.py` (975 LOC) — Prometheus instrumentation.
- **Extensions not in spec:** A/B-Testing router (`ab_testing_router.py`, 552 LOC), Tool Registry + Action Dispatcher (`tool_registry.py`, `action_dispatcher.py`, `ai_action_service.py` 1270 LOC), Vector-Sync between Qdrant and pgvector (`vector_sync_service.py`), full BI sub-API (`/rag/bi/*` 6 endpoints: invoices, entity-stats, payment-prediction, trends, enhanced-chat).

### Missing or partial vs spec

| Spec section | Status |
|---|---|
| 6.1 Docker Compose for Ollama / TEI / Reranker services | **Not verified** — spec defines dedicated containers (`ollama-realtime`, `ollama-analysis`, `tei-embedding`, `tei-reranker`); need to grep `docker-compose.yml` to confirm. |
| 7.1 Customer-Card nightly batch job (Celery Beat) | `sync_all_cards()` exists in service, but Beat-schedule registration not visible from this review. |
| 8.1/8.2 Report generators | `excel_generator.py` (390 LOC) and `word_generator.py` (410 LOC) present; **PDF generator missing** (spec promised Excel/PDF/Word). |
| 9 Prompt Templates | `prompt_templates.py` (549 LOC) exists — needs content audit vs spec templates. |
| 10.2 Grafana Dashboard JSON | Not searched here — likely missing from `infrastructure/grafana/`. |
| 11 Test suite (RAG-specific) | Not enumerated; check `tests/unit/rag/` and integration coverage. |
| 13.2 Performance benchmarks (<500ms search, <15s 8B-LLM, <60s 14B-LLM) | No benchmark artifacts in repo — never validated. |

**Net assessment:** RAG layer is ~85 % implemented and goes beyond spec in agent/action tooling and A/B routing. Three gaps: PDF report generator, formal Beat-schedule for card sync, and never-run performance benchmarks against the v1.0.0 targets.

---

## Recommended Commit Grouping

Do **not** commit the formatter blast as-is. Recommended sequence:

1. **Revert formatter damage** — checkout original versions of 20 files where the only change is table-flattening / metadata-collapse / stray fences / `&lt;` escaping / `<http://...>` auto-linking. Files: `CLAUDE.md`, `README.md`, `PlanRAGAblage.md`, all `Static_Knowledge/*`, all `Dynamic_Knowledge/*`, all `docs/*`, `.claude/ORCHESTRATION_ENTERPRISE_PLAN.md`.
2. **Restore ANALYSIS files** — `git checkout HEAD -- ANALYSIS_*.md` (343 lines of substantive content lost; this is not formatter, content was deleted).
3. **Commit `CHANGELOG.md` (cherry-picked)** — keep the new `Fixed`/`Added` entries for Slack-Spam-Sweep, but revert the `<http://documents.py>` auto-link corruption. Message: `docs(changelog): document alerting hygiene + new test additions`.
4. **Commit `CLAUDE.md` Knowledge-System block separately** — extract just the new top-of-file Vault-pointer block (lines 1-13) onto a clean base. Message: `docs(claude): add Obsidian Vault knowledge-system pointer`.
5. **Commit `.claude/plan.md` content updates** — after reverting formatter escapes, keep any real plan-content additions. Message: `docs(plan): update feature roadmap status`.
6. **Commit `.claude/plans/breezy-napping-hare.md`** — the +11 lines are roadmap status per Cross-Instance Tracking Protocol. Message: `docs(roadmap): update sprint-0 task status`.
7. **Configure `.prettierignore` or disable table-formatting** — root cause fix. Add `*.md` to `.prettierignore` or set `proseWrap: preserve` and disable any `remark-gfm` table normalization. Otherwise the next save will repeat the damage.

---

## Stale / Obsolete Content

- **`ANALYSIS_*.md` (3 files):** Dated 2025-12-31, claim "PRODUCTION-READY (92-95 %)". As of 2026-05-19 the system has been through Sprint-0 hardening (5 commits visible) — these analysis docs are 5 months stale and should either be archived under `docs/archive/2025-12/` or regenerated.
- **`docs/INFRASTRUCTURE_STATUS.md`:** Dated 2026-01-05, "19/19 healthy". Latest commit 438f2486 mentions "21 Container healthy". Container count drifted; refresh required.
- **`docs/OCR_EVALUATION_2025.md`:** Recommends Surya GPU. Verify against current `OCR_BACKEND` env / actual backend in production.
- **`PlanRAGAblage.md`:** Version 1.0.0 / 2025-12-03, "Planning → Implementation Ready". Implementation is now ~85 % done — bump to v1.1 and add an "Implementation Status" appendix referencing `app/services/rag/`.
- **Static_Knowledge ADR-002/003 (2025-01-22):** Content still accurate, but `Last Updated` should bump if any related code changed.
- **CLAUDE.md "Project Config" defaults** (hierarchical, 8 agents): still aligned with current orchestration.

---

## Summary

The 22-file diff is dominated by a single mechanical cause — a markdown formatter pass that flattened pipe-tables, collapsed multi-line metadata, escaped HTML entities, and inserted stray ``` fences inside ASCII art and code examples. This is a **drift event, not an intent change**. Only four files carry meaningful intent: `CLAUDE.md` (new Vault pointer), `CHANGELOG.md` (Slack-Spam-Sweep entries), `.claude/plan.md` (roadmap updates), `.claude/plans/breezy-napping-hare.md` (sprint status). The three `ANALYSIS_*.md` files additionally lost 343 lines of real content and need full revert. The RAG implementation has substantially outpaced its v1.0.0 spec; the spec should be marked "Implementation in Progress" with three known gaps (PDF report generator, Beat-schedule wiring, performance benchmark validation). Recommend reverting the formatter blast, fixing prettier config, then committing the four intent-bearing files as small, separate commits.
