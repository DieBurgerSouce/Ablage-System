# Frontend Review

Date: 2026-05-19 | Scope: `frontend/src/` (1,556 .tsx files) | Stack: React 18 + TS 5 + TanStack + shadcn/ui

## High Priority

### H1 — console.log leaks in production code (71 instances, excluding `logger.ts`/stories/JSDoc)
Sensitive logging risks CLAUDE.md Rule 1 (no PII/customer data in logs). Replace with structured logger from `lib/logger.ts`.

| File:Line | Issue | Fix |
|-----------|-------|-----|
| `features/developer-portal/hooks/useDeveloperPortal.ts:435,439` | `console.log('Dokument-ID:', doc.id)` — logs document IDs | Use `logger.debug()` or gate behind dev flag |
| `features/document-hints/components/DocumentHintsPanel.tsx:160` | `console.log('Action type not handled:', ...)` | `logger.warn()` |
| `features/ocr-suite/components/OcrTemplateEditor.tsx:127` | `console.log('Saving template:', { templateName, ...zones })` — leaks template content | Remove or `logger.debug()` |
| `features/search/components/SmartSearchExample.tsx:23,42,178` | `console.log('Document clicked:', docId)` | Demo code — move to `.stories.tsx` |
| `features/agent-chat/AgentChatView.tsx:357` | `console.debug('Aktion ausgefuehrt:', action.action_type, action.params)` — leaks params | `logger.debug()` (params may contain PII) |
| `features/analytics/api/analytics-api.ts:59,75,91,107,146,232` | 6× `console.error('Failed to fetch ...', error)` | Use `logger.error()` consistently |
| `features/approval-enhanced/api/approval-enhanced-api.ts:29..218` | 13× `console.error` | Centralize via `lib/api/error-toast-handler.ts` |
| `features/smart-dashboard/api/smart-dashboard-api.ts:43..135` | 6× `console.error` | Same as above |
| `app/routes/admin.sso.tsx:110,131,449,469,496` | 5× `console.error('[SSO] ...')` | Use `logger.error('sso', ...)` namespace |
| `features/privat/hooks/useNetWorth.ts:479`, `features/privat/pages/NetWorthDashboard.tsx:348` | `console.error('Fehler beim ...')` — financial domain | High-risk; route through logger + remove error object stringification |

Action: replace all 71 with `logger.*` from `lib/logger.ts`. Add ESLint rule `no-console: ['error', { allow: [] }]` and except `lib/logger.ts`.

### H2 — TypeScript `as any` epidemic (305 occurrences in non-test code)
Violates CLAUDE.md Rule 4 (no `Any`). `as any` defeats the type system silently. Top offenders by domain: `features/imports/components/RuleTestingPanel.tsx`, `features/data-quality/components/DataQualityDashboard.tsx`, `features/dashboards/components/CreateDashboard.tsx`. Fix: extract proper interfaces, use `unknown` + type guards, or `z.infer<>` from existing zod schemas. Track with `grep -c 'as any'` reduction goal: 305 → 0 over a sprint.

### H3 — TanStack Query: mutations without cache invalidation (data-staleness bugs)
After mutate, UI shows stale data until reload. Files with mutations but zero `invalidateQueries`:

| File | Mutations | Invalidations |
|------|-----------|---------------|
| `features/ablage/hooks/use-duplicate-check.ts` | 2 | 0 |
| `features/accounting/hooks/use-elster-queries.ts` | 2 | 0 |
| `features/admin/audit/audit-api.ts` | 2 | 0 |
| `features/admin/dunning-templates/hooks.ts` | 3 | 0 |
| `features/audit/api/audit-chain-api.ts` | 3 | 0 |

Fix: add `onSuccess: () => queryClient.invalidateQueries({ queryKey: [...] })` per mutation.

### H4 — i18n adoption is 0% despite full setup
`lib/i18n/` (config.ts, i18n.ts, useTranslation.ts) and `locales/de.json|en.json` exist. **Zero `.tsx` files import `useTranslation`.** All 1,556 component files use hardcoded German strings (`<CardTitle>Verbindung wird hergestellt...</CardTitle>` in `admin.datev-connect.oauth-callback.tsx:101`, hundreds more). Rule 2 is satisfied (German is shown), but maintenance burden + future locale switch is impossible. Decision required: (a) drop unused i18n infra, or (b) commit to migration plan starting with high-traffic routes.

## Medium

### M1 — `key={index}` / `key={i}` anti-pattern (100+ instances, true count likely 150+)
Causes incorrect React reconciliation when list reorders/filters. Mostly in skeleton loaders (acceptable since order is static), but several in dynamic lists:

| File:Line | Context | Severity |
|-----------|---------|----------|
| `features/fraud/components/FraudAlertsTable.tsx:143` | `<TableRow key={index}>` — alerts can be sorted/filtered | High |
| `features/imports/components/RuleTestingPanel.tsx:194,211,247` | Test result lists | Medium |
| `components/streckengeschaeft/ClassificationDetail.tsx:549` | `<IndicatorCard key={i}>` — indicator list dynamic | High |
| `features/import-wizard/components/ImportWizard.tsx:519` | Warning list re-rendered after import | High |
| `components/onboarding/WelcomeModal.tsx:180,193` | Step list — order stable | Low |
| `features/datev/components/export/ExportPreview.tsx:104` | Preview rows | Medium |

Fix: use stable IDs (`item.id`, `item.uuid`, or `${name}-${type}`). Keep `key={i}` only in Skeleton arrays where length is fixed and never re-keyed.

### M2 — `useQuery` without `staleTime` (default = 0 → over-fetching)
Heuristic file scan shows many files with more queries than `staleTime` entries:

| File | Queries | staleTime |
|------|---------|-----------|
| `features/adhoc-reporting/hooks/use-adhoc-reporting-queries.ts` | 15 | 3 |
| `features/admin/companies/api/companies-admin-api.ts` | 13 | 6 |
| `features/admin/audit/audit-api.ts` | 6 | 2 |
| `features/ablage/hooks/use-ablage-multi-upload.ts` | 2 | 0 |
| `features/ablage/hooks/use-document-upload.ts` | 2 | 0 |

Good news: project has `QUERY_VOLATILE/STANDARD/SEMI_STATIC` constants (`features/ablage/hooks/use-ablage-queries.ts`). Apply these consistently across all hooks.

### M3 — `<img>` elements lacking `alt` (15 confirmed locations need verification)
Sampled instances at `OCRReviewModal.tsx:253`, `admin.ocr-training.batch.$id.tsx:417`, `SecuritySettingsTab.tsx:213`, `photo-upload.tsx:441`, `offline-document-list.tsx:269`, `CameraCapture.tsx:577,670`, `ImageDiffViewer.tsx:199,223`, `ImageViewer.tsx:182`, `FilePreviewRouter.tsx:302`, `BoundingBoxAnnotator.tsx:204`, `AnnotationOverlay.tsx:23`, `ValidationPDFViewer.tsx:329`. Verify each; add `alt="Dokumentvorschau"` etc. `components/ui/avatar.tsx:23` AvatarImage forwards props — OK if callers pass alt.

### M4 — Native `<option value="">` in `GenerateDocumentDialog.tsx:207`
NOT a Rule 7 violation (Rule 7 targets shadcn `<SelectItem>`, this is native HTML `<select>`). Still UX wart: placeholder fires onChange with `""`. Fix: `<option value="" disabled>Bitte wählen...</option>` and validate `value !== ""` on submit.

## Low

- **L1** — `aria-label` usage is sparse: only 15 occurrences across 5 files (`components/accessibility/index.tsx`, `BulkDropZone.tsx`, `BulkActionBar.tsx`, `InstallAppBanner.tsx`, `stories/Navigation.stories.tsx`). Icon-only buttons elsewhere likely lack labels. WCAG 2.1 AA non-compliance risk.
- **L2** — `console.log` in JSDoc examples (`websocket.ts:483/516/878`, `use-notification-navigation.tsx:38`, `use-voice-search.ts:58`) — harmless but inconsistent; convert to `// e.g. log(...)`.
- **L3** — `features/developer-portal/components/SdkDownloads.tsx:242,243` — `console.log` is inside a code-string template literal (educational). Move to dedicated `examples/` snippet file rather than mixing with component JSX.
- **L4** — `stories/Form.stories.tsx:330` — `console.log(values)` in Storybook is acceptable; document standard.
- **L5** — No `debugger` statements found.

## Large Files (Refactor Candidates)

| File | Lines | Recommendation |
|------|-------|----------------|
| `features/job-queue/__tests__/use-job-mutations.test.tsx` | 1,674 | Split per mutation domain |
| `features/validation/components/ValidationQueueDashboard.tsx` | 1,516 | Extract columns, filters, bulk-action bar to subcomponents |
| `features/ai-assistant/components/GlobalAIAssistantV2.tsx` | 1,147 | Extract message renderer, command palette, history |
| `features/finance/components/BudgetDashboard.tsx` | 1,063 | Split into BudgetOverview / BudgetCategoryList / BudgetChart |
| `features/upload/components/UploadWizard.tsx` | 1,052 | One file per wizard step |
| `features/personal/components/employee/EmployeeForm.tsx` | 1,002 | Split into FormSections + react-hook-form `useFieldArray` |
| `features/actions/components/PredictiveActionPanel.tsx` | 987 | Extract action-card, filter-bar |
| `features/knowledge-graph/views/TimelineView.tsx` | 913 | Extract timeline-item, group-header |
| `features/workflows/components/WorkflowBuilderEnhanced.tsx` | 907 | Extract node/edge renderers |
| `features/knowledge-graph/views/RiskNetworkView.tsx` | 900 | Extract graph-controls, legend |

Target: 600 LOC max per .tsx; extract pure-presentational subcomponents and custom hooks for data.

## Summary

71 production `console.*` calls (Rule 1 risk), 305 `as any` casts (Rule 4 violation), 0% i18n adoption despite full infrastructure, 100+ `key={index}` instances (mostly skeletons, but ~10 in dynamic lists), 5 hook files with mutations missing `invalidateQueries`, 10 components >900 LOC. Rule 7 (shadcn Select value="") clean — only finding was a native `<option>`. No `debugger` statements. Accessibility weak: ~15 `aria-label` usages across 1,556 .tsx files, ~30 `<img>` need alt verification. Prioritize: (1) console→logger sweep, (2) `as any` budget cap, (3) i18n decision (drop or migrate), (4) cache invalidation fixes in 5 mutation hook files.
