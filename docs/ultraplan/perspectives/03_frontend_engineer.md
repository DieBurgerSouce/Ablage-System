# 03 — Frontend Engineer Perspektive

**Reviewer:** 15 Jahre React/TypeScript Senior. Bundle-Bloat-Hasser. Daten statt Buzzwords.
**Datum:** 2026-05-03
**Branch:** `feature/ocr-performance`
**Scope:** `frontend/` (299 Routen, 127 Features, 58 Test-Files)

---

## Verdict (1 Satz)

Solide TypeScript-Disziplin und konsistente Toolchain (Vite, TanStack, shadcn) treffen auf systematische Lücken bei Code-Splitting (nur 22 von 299 Routen `lazy()`), Component-Tests und Accessibility — produktionstauglich für Pilot, aber strukturell nicht skalierungsbereit.

---

## Quantitative Befunde

| Metrik | Wert | Quelle | Bewertung |
|--------|------|--------|-----------|
| Routen total | 299 | `frontend/src/app/routes/` | Hoch |
| Features | 127 | `frontend/src/features/` | Granular |
| Routen mit `lazy()` | **22 / 299 (7,4 %)** | `grep "lazy(" src/app/routes` | **Schwach** |
| Manual Vendor-Chunks | 4 (react/router/chart/ui) | `vite.config.ts:116-121` | Brauchbar |
| Bundle Source-Maps | aktiviert | `vite.config.ts:112` | Gut für Debug |
| `package.json` Version | `0.0.0` | `frontend/package.json` | Kein Release-Tag |
| `useState` in `.tsx` | **709** Files | `grep -rln useState` | Lokaler State dominiert |
| `useQuery`/`useMutation` in `.tsx` | **124** Files | `grep -rln useQuery\|useMutation` | Server-State sauber |
| `: any` (Production) | **17** Treffer | `00e_FRONTEND_AUDIT.md §2` | Sehr gut |
| Component-Tests `*.test.tsx` | **39** | `find src -name "*.test.tsx"` | FAANG sagte 3 — Aufwärts, aber dünn |
| Test-Files gesamt (`.test.{ts,tsx}`) | 58 | `00e_FRONTEND_AUDIT.md §2` | ~13 % Routen-Coverage |
| `value=""`-Crash-Pattern | **0 echt** (2 harmlos) | `grep -rn 'value=""' src` | Regel #7 eingehalten |
| axe-core Violations (Dec 2025) | **93** (1 critical, 85 serious, 7 moderate) | `browser-diagnostics/accessibility/*.json` | **Kritisch** |
| Lighthouse-Reports im Repo | 0 | `find browser-diagnostics` | Keine LCP/CLS/INP-Daten |
| FCP Dashboard (gemessen) | 1540 ms | `browser-diagnostics/performance/*.json` | Mittelmäßig |
| FCP Upload | 352 ms | dito | Gut |
| JS Heap auf `/upload` | bis **366 MB** total | dito | **Verdächtig hoch** |

---

## Top-3 Stärken

1. **Type-Safety auf Spitzenniveau.** 17 `: any` in 14 Files bei einer 127-Feature-Codebase ist FAANG-Niveau. Strict-TypeScript zahlt sich aus, der Compiler fängt Klassen von Bugs vor PR-Stage.
2. **shadcn-Disziplin & deutsche UX-Patterns.** Kein einziger echter `value=""`-Verstoß gegen CLAUDE.md Regel 7. Banking-Transactions (`features/banking/components/transactions/TransactionsPage.tsx:148-163`) nutzt konsistent `value="all"`. EmptyState (`components/ui/empty-state.tsx`, 64 Verwendungen in 15 Files) ist ein echter wiederverwendbarer Baustein, kein Copy-Paste.
3. **Toolchain-Konsistenz.** Vite + TanStack Router + TanStack Query + shadcn + VitePWA ist ein modernes, kohärentes Setup. PWA mit differenzierten Caching-Strategien (`vite.config.ts:25-94`: NetworkFirst für API, CacheFirst für Documents/Fonts, SWR für JS/CSS) ist durchdacht — kein Default-Copy-Paste.

---

## Top-5 Technische Lücken

1. **Code-Splitting nur 7,4 % implementiert** (`frontend/src/app/routes/*.tsx`).
   22 von 299 Route-Files nutzen `lazy()` + `Suspense`. Banking, OCR-Backends und einige Detail-Routes splitten korrekt (z. B. `admin.banking.transactions.tsx:5`, `admin.ocr-review.tsx:5`). Aber **DATEV-Routen importieren direkt** (`admin.datev.export.tsx:6`, `admin.datev.config.tsx`, `admin.datev.history.tsx`, `admin.datev.vendors.tsx`). TanStack Router macht zwar route-basiertes Splitting per Default, das wird aber durch direkte Top-Level-Imports neutralisiert. Initialer Bundle wird dadurch unnötig groß. Erste-Load-Performance wurde nie gemessen (kein Lighthouse-Report im Repo).

2. **93 axe-core-Violations (Dec 2025), keine Folge-Audits** (`browser-diagnostics/accessibility/accessibility-2025-12-31T05-12-26.json`).
   - 46 × `color-contrast` (WCAG 2 AA verletzt)
   - 39 × `aria-progressbar-name` (Progressbars ohne Label)
   - 7 × `region` (Landmarks fehlen)
   - 1 × `button-name` (Combobox ohne Discernible Text, `#address-country` auf Dashboard)
   CLAUDE.md behauptet WCAG 2.1 AA — die einzige eingecheckte Messung sagt: nein. Der `AccessibilityProvider` (`components/accessibility/`) existiert, aber liefert ohne CI-Gate keine Garantie. Vier Monate keine neue Audit-Datei.

3. **Component-Test-Coverage strukturell dünn** (39 `*.test.tsx` Files für 127 Features).
   Cluster gut: Invoices (10), Banking (5), Auth-Routen (4). **0 Tests** für Risk-Scoring (6 Komponenten), Spotlight (4 Komponenten), Onboarding-Wizard (4 Steps), Dashboard, OCR-Review, Upload-Wizard, Privat-Modul, Kasse. FAANG-Audit2 (Dez 2025) sagte 3 Tests, jetzt 39 — Trendwende erkannt, aber bei 299 Routen viel zu wenig. **0 neue Test-Commits in 14 Tagen** (`00g_TEST_AUDIT.md §10`), 8 untracked Test-Files in Git-Status.

4. **State-Management-Mix riskant** (709 `useState`-Files vs. 124 `useQuery`-Files).
   Ratio 5,7 :1 lokaler vs. Server-State. Bei einem datenschweren Document-Management-System ist das ein Smell: Wahrscheinlich werden Server-Daten in `useState` kopiert (Stale-State, Sync-Bugs, doppelter Render). Stichprobe `features/banking/components/transactions/TransactionsPage.tsx:50-65` macht es richtig (Filter im `useState`, Daten via `useTransactions`-Query). Aber 709 ist zu viel für 124 Query-Files. Ein systematischer Sweep mit ESLint-Rule `no-server-state-in-usestate` fehlt.

5. **Self-rolled Error-Monitoring statt Sentry** (`frontend/src/main.tsx:38-62`).
   `sendErrorToMonitoring()` POSTet an `/api/v1/errors` — silent fail wenn Backend down (was im Live-Walk auf Port 8000 ja der Fall war, `00j_LIVE_SYSTEM_REPORT.md §1`). Keine Source-Map-Symbolisierung, kein Session-Replay, kein Release-Tracking, keine Web-Vitals. Source-Maps werden generiert (`vite.config.ts:112`), aber nirgendwo ausgewertet. Bei Pilot-Bug muss man manuell SQL gegen Errors-Tabelle queryen.

**Bonus-Lücke (Live-Walk-Befund):** `frontend/src/app/routes/forgot-password.tsx` hat den String **„Zuruck zur Anmeldung"** ohne ü-Umlaut (`00j_LIVE_SYSTEM_REPORT.md §4.1`). Direkter Verstoß gegen CLAUDE.md Regel 2 auf der drittwichtigsten Page. 5-Min-Fix, aber Indikator für fehlenden i18n-Lint.

---

## Empty/Loading/Error-States — Stichprobe

| Route | Loading | Error | Empty | Befund |
|-------|---------|-------|-------|--------|
| `admin.banking.transactions` | Skeleton (5×) | Card mit Fehlertext | Icon + CTA | Vollständig (`TransactionsPage.tsx:211-225`) |
| `admin.banking.reconciliation` | Lazy + Suspense | (geprüft via Hook) | EmptyState | Konsistent |
| `admin.datev.export` | `configsLoading` | Mutation-Errors | (Konfig-abhängig) | OK (`ExportPage.tsx:36-85`) |
| `admin.rechnungen.liste` | `isLoadingInvoices` | Toast | (Liste leer) | OK (`InvoiceListPage.tsx:74-213`) |
| `forgot-password` | Form-State | Toast | n/a | OK |
| `dashboard` | (FAANG-Verdacht) | global Toast | EmptyState | OK seit Dez |
| Generic 404 (`$.tsx`) | n/a | n/a | n/a | Vorhanden, getestet |

→ Kein systematisches Loch in Listen-Routes. Sub-Standard nur bei nicht-stichprobierten OCR-Review/Upload (keine Test-Coverage zur Verifikation).

## Mobile (375 px) — Komplexe Routen

Live-Walk (`00j_LIVE_SYSTEM_REPORT.md §2`) hat nur Auth-Pages getestet — Banking/DATEV/Finanzen **nicht verifiziert**. Code-Inspektion `TransactionsPage.tsx:130` zeigt `grid gap-4 md:grid-cols-2 lg:grid-cols-4` (responsiv), aber 4-Spalten-Filter auf 375 px stapeln vertikal. Tabelle nutzt `useVirtualizer` — auf Mobile mit Touch-Scroll und horizontalem Overflow ein Risiko. **KRITISCH ungetestet** für Pilot-Use-Case „Geschäftsführer am Handy abends".

---

## Note für „Frontend Engineering Quality": **6,5 / 10**

Begründung:
- **+** Type-Safety (17 `any`), Toolchain-Wahl, shadcn-Disziplin, Empty-State-System, Pilot-Blocker behoben (5/6 von FAANG).
- **−** 7 % Code-Splitting (sollte 80 %+ sein bei 299 Routen).
- **−** 93 axe-Violations ohne CI-Gate, keine Folge-Messung in vier Monaten.
- **−** 39 Component-Tests bei 127 Features (~30 %, sollte 70 %+ sein).
- **−** State-Management-Mix nicht überprüft.
- **−** Self-rolled Error-Monitoring blind bei Backend-Down.
- **−** Mobile-Verhalten komplexer Routen ungetestet.
- **−** Umlaut-Bug auf Forgot-Password.

Ein 8/10 (wie der Audit-Report sagt) wäre angemessen, **wenn** Lighthouse-Scores existieren würden, axe-Violations adressiert wären und Code-Splitting konsequent. Solange diese Daten fehlen, ist 6,5 die ehrliche Note.

---

## 3 Konkrete Refactoring-Empfehlungen

### R1 — Code-Splitting flächendeckend (Aufwand: 2–3 Tage)

**Aktion:** Alle 277 Route-Files ohne `lazy()` umstellen auf das Pattern aus `admin.banking.transactions.tsx`. Generator-Skript: AST-Transform mit `ts-morph`, `import { Foo } from '@/features/...'` ersetzen durch `const Foo = lazy(() => import('@/features/...').then(m => ({ default: m.Foo })))` plus `<Suspense fallback={<LazyLoadFallback />}>`.

**Messbarer Erfolg:** Initial JS-Bundle vor/nach mit `vite build --mode=analyze`. Ziel: −40 % Initial-Chunk, LCP < 2 s auf 4G.

### R2 — A11y-Regression-Gate in CI (Aufwand: 1 Tag)

**Aktion:** `@axe-core/playwright` als Vitest- und Playwright-Plugin einziehen, `.github/workflows/a11y.yml` mit Top-10-Routen (Login, Dashboard, Upload, OCR-Review, Banking-Transactions, Invoice-List, DATEV-Export, Forgot-Password, Onboarding, 404). PR-Block bei neuen `serious`/`critical`-Findings. Bestehende 93 als Baseline ignorieren, nur Regressions-Gate.

**Messbarer Erfolg:** Erste 4 Wochen: keine neuen Violations. Quartal: 50 % der bestehenden 93 abgebaut. Color-Contrast (46 Violations) zuerst — meist 1-Token-Fix in `tailwind.config.js`.

### R3 — Sentry-Wiring + Source-Map-Upload (Aufwand: 0,5 Tage)

**Aktion:** `@sentry/react` mit `BrowserTracing` + `Replay` integrieren in `frontend/src/main.tsx:38-62` (existierender `sendErrorToMonitoring` als Fallback behalten). `vite-plugin-sentry` für Source-Map-Upload bei Build. Self-hostable Sentry-Instanz auf gleicher On-Premises-Hardware (kein Cloud-Verstoß gegen CLAUDE.md Regel 6).

**Messbarer Erfolg:** Beim ersten Pilot-Bug Stack-Trace mit symbolisiertem File:Line statt minified `chunk-1ab2.js:1:42891`. Web-Vitals (LCP, CLS, INP) automatisch erfasst — schließt die Lighthouse-Daten-Lücke.

---

**Wortzahl:** ~1280
