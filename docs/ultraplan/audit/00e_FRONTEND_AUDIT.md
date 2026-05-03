# 00e FRONTEND AUDIT — Pilot-Reality-Check

Stand: 2026-05-03
Branch: `feature/ocr-performance`
Scope: `frontend/src/` (299 Routen, 127 Features)
Bezug: FAANG-Audit2 Dezember 2025

---

## 1. FAANG-Pilot-Blocker (kritischer Abschnitt)

| # | Blocker | Dezember 2025 | Mai 2026 | Beleg |
|---|---------|---------------|----------|-------|
| 1 | 404-Page | OFFEN | **BEHOBEN** | `frontend/src/app/routes/$.tsx` (72 LOC, deutsch, navigiert zu `/`, zeigt URL-Hint, Zurueck-Button) |
| 2 | Empty-States | OFFEN | **BEHOBEN** | `frontend/src/components/ui/empty-state.tsx` (wiederverwendbar, 6 Varianten: default, search, error, upload, folder, document) + Test in `__tests__/empty-state.test.tsx`. 64 Verwendungen in 15 Files. Spezialisierungen wie `features/smart-inbox/components/InboxEmptyState.tsx` |
| 3 | Error-Monitoring | TODO | **TEILWEISE** | `main.tsx` Zeilen 38-62: Eigener `sendErrorToMonitoring()` POSTet an `/api/v1/errors`. Keine Sentry/LogRocket/Datadog/PostHog-Integration im src-Tree (nur 1 Treffer in `finanzen.tsx`, vermutlich Kommentar). Self-rolled Endpoint, keine externe APM-Pipeline |
| 4 | Onboarding-Flow | OFFEN | **BEHOBEN** | `frontend/src/components/onboarding/`: WelcomeModal, CompanySetupWizard, 4 Steps (CompanyInfo, AccountingSettings, UserInvite, Completion), localStorage-Key `ablage_onboarding_complete`, Test fuer company-setup-utils |
| 5 | 2FA-Frontend | OFFEN | **BEHOBEN** | `frontend/src/components/auth/TwoFactorInput.tsx` (TOTP-Code-Eingabe) + Test `__tests__/TwoFactorInput.test.tsx`. Zusaetzlich `SessionExpiredModal.tsx` |
| 6 | Password-Reset-UI | OFFEN | **BEHOBEN** | `frontend/src/app/routes/forgot-password.tsx` + `reset-password.$token.tsx` (Token-basiert, nutzt `authService.reset...`, deutsche UX, Loading/Success/Error-States). Beide Routen mit Tests im `__tests__/routes/` |

**Fazit Blocker**: 5 von 6 vollstaendig BEHOBEN. Nur Error-Monitoring (#3) ist TEILWEISE — Self-rolled Backend-Endpoint statt Sentry/LogRocket. Fuer Pilot ausreichend, fuer Skalierung suboptimal (kein Source-Map-Stack-Beautify, kein Session-Replay, keine Release-Tracking-Pipeline).

---

## 2. Quantitative Befunde

| Metrik | Wert | Bewertung |
|--------|------|-----------|
| Routen | 299 | Sehr gross, ungewoehnliche Route-zu-Feature-Ratio (2.35) |
| Features | 127 | Granular |
| Test-Files (`*.test.{ts,tsx}`) | 58 | **Niedrig** bei 299 Routen (~19% Coverage-Indikator) |
| `: any`-Treffer | **17** in 14 Files | Hervorragend bei dieser Codebase-Groesse |
| `value=""` in `.tsx` | 2 (1 Kommentar in `admin.sso.tsx`, 1 native `<option>` in `GenerateDocumentDialog.tsx`) | **Kein shadcn-Select-Verstoss** |
| Code-Splitting | Aktiv | `vite.config.ts` manualChunks: react-vendor, router-vendor, chart-vendor, ui-vendor |
| PWA / Service Worker | Aktiv | VitePWA mit NetworkFirst (API), CacheFirst (Docs/Images/Fonts), StaleWhileRevalidate (JS/CSS) |
| Source Maps | Aktiv (`sourcemap: true`) | Gut fuer Debugging, ggf. mit Sentry-Upload kombinieren |
| `lazy()` / dyn. Imports im Routes-Tree | Nicht im Audit-Scope geprueft | TanStack Router macht Code-Splitting per Default per Route |
| Spotlight | Vollstaendig | 9 Files: hooks, api, types, 3 Components (Dialog, Results, ResultItem, RecentSearches) |
| Risk-Scoring | Vollstaendig | 6 Komponenten: RiskScoreGauge, RiskFactorBreakdown, HighRiskEntitiesTable, RiskAlertBanner, RiskDashboard, RiskTrendChart + page + api + hooks + README + Demo. **Spec erfuellt.** |
| Accessibility-Audit-Files | **Keine** Lighthouse/axe-Reports im Repo | Gap |

---

## 3. Detail-Notizen

**main.tsx** ist solide aufgebaut: ErrorBoundary global, ThemeProvider, AccessibilityProvider, QueryClientProvider, AuthProvider, CompanyProvider, PWAProvider, Toaster (sonner) mit deutschen PWA-Update-Toasts, Service-Worker mit Stundenintervall-Update-Check, strukturierter Logger. Kein TODO-Kommentar fuer Monitoring sichtbar — die self-rolled Loesung ist absichtlich eingebaut.

**404-Page** ist nicht nur vorhanden, sondern designed: Glass-Card mit Gradient, FileQuestion-Icon, deutsche Texte ("Seite nicht gefunden"), Primaer-Button zur Startseite, Sekundaer-Button "Zurueck". Test vorhanden in `__tests__/routes/$.test.tsx`.

**EmptyState-Komponente** unter `components/ui/empty-state.tsx` ist mit 6 Varianten + Default-Icons + Test echter shadcn-konformer Baustein. Konsistent in 15 Files konsumiert (Dashboard, Tables, Drawer, Spotlight, SmartInbox, Search-Page).

**`value=""`-Pattern**: Nur 2 Treffer, keiner in shadcn `<Select>`. `admin.sso.tsx` ist ein erklaerender Kommentar ueber CLAUDE.md Rule 7. `GenerateDocumentDialog.tsx` Zeile 207 ist ein **natives** `<select>`-Element mit `<option value="">Bitte waehlen...</option>` — das ist HTML-Standard und bricht nichts. **Kein wartender Crash.**

**Onboarding** existiert nicht als Route, sondern als Modal + Wizard, der via `localStorage.ablage_onboarding_complete` getrackt wird. Pragmatisch, aber nicht im Routen-Tree sichtbar.

**Tests**: 58 Test-Files, davon ein grosser Cluster fuer Invoices (10 Tests), Banking (5 Tests), Auth-Routen (4 Tests). Lebenswichtige Bereiche (Documents, Risk-Scoring, Spotlight) haben kaum Tests — nur DocumentCard, RiskScoreBadge, ActivityFeed.

**Accessibility**: Provider und Lib (`lib/accessibility`, `components/accessibility`) vorhanden inklusive `ARIA_LABELS_DE`, High-Contrast-Mode, Reduced-Motion. **Aber**: Keine Audit-Reports (axe/Lighthouse) im Repo. Frontend hat keinen `frontend/browser-diagnostics/`-Ordner. Bewertbar nur ueber Code, nicht ueber Messung.

---

## 4. Top-3 Staerken

1. **Pilot-Blocker substanziell adressiert**: 5/6 Dezember-Blocker komplett behoben mit produktionsreifen, deutschsprachigen, designten Komponenten. Auth-Flow (Login, 2FA, Password-Reset, Forgot-Password) ist vollstaendig.
2. **Type-Safety auf Spitzenniveau**: Nur 17 `: any`-Treffer in einer ~127-Feature/299-Routen-Codebase. Das ist FAANG-Niveau und uebertrifft viele Enterprise-Frontends.
3. **Hochwertige Plattform-Infrastruktur**: PWA mit differenzierten Caching-Strategien, ErrorBoundary global, Source-Maps in Production, Code-Splitting in 4 Vendor-Chunks, deutsche i18n, A11y-Provider mit High-Contrast/Reduced-Motion. Toolchain (Vite + TanStack Router/Query + shadcn) ist modern und konsistent.

---

## 5. Top-5 Luecken

1. **Kein externes APM (Sentry/LogRocket/Datadog/PostHog)**: Self-rolled `/api/v1/errors`-POST ohne Source-Map-Symbolisierung, ohne Session-Replay, ohne Release-Tracking, ohne Performance-Metriken (LCP/CLS/INP). **Pilot-Risiko**: Bei Bugs muss man manuell DB queryen statt im UI Stacks zu sehen.
2. **Test-Coverage strukturell ausbaufaehig**: 58 Tests bei 299 Routen ist niedrig. Risk-Scoring (6 Komponenten) hat 0 Tests, Spotlight (4 Komponenten) hat 0 Tests, Onboarding-Wizard hat nur einen Utils-Test, kein Wizard-Flow-Test. E2E-Layer (Playwright) wurde nicht im Frontend-Scope geprueft.
3. **Kein Onboarding als Route**: WelcomeModal lebt nur im localStorage. Bei Browser-Wechsel/Inkognito-Modus wird User wieder onboarded. Kein Backend-User-Profile-Feld `onboarding_completed_at`. Pilot-Kunden mit mehreren Geraeten erleben Friktion.
4. **Keine Accessibility-Audit-Artefakte**: Trotz `AccessibilityProvider` keine eingecheckten axe-/Lighthouse-Reports, kein CI-Job zur Regression. WCAG 2.1 AA Behauptung in CLAUDE.md ist nicht messbar.
5. **`299 Routen / 127 Features` ist verdaechtig hoch**: Ratio 2.35 deutet auf viele Detail-/Sub-Routes oder fehlendes Route-Grouping. Bundle-Splitting via TanStack Router laeuft, aber Cognitive-Load fuer neue Entwickler ist hoch. Kein Routing-Index-Doc gefunden. Risiko: Tote Routen, doppelte Pfade.

---

## 6. Note: Frontend Pilot-Readiness

**Note: 8 / 10**

Begruendung: Die Dezember-2025-Blocker sind bis auf einen substantiell behoben. Das Frontend ist deutsch, polished, type-safe, PWA-faehig, hat Code-Splitting, A11y-Provider, ErrorBoundary, 2FA, Password-Reset, Onboarding-Wizard und eine echte 404-Page. Kein blockierender Pattern-Verstoss (kein shadcn `value=""`-Crash). Ein Pilot mit 1-3 Kundenfirmen ist sofort moeglich.

Punktabzug: Externes APM fehlt (-1), Test-Coverage strukturell duenn (-0.5), keine A11y-Audit-Artefakte (-0.5). Fuer Skalierung auf 10+ Kunden sollte vor Q3 ein Sentry/PostHog plus erweiterte Test-Suite kommen, sonst wird Bug-Triage zur Engpass-Operation.

---

## Appendix: gelesene Schluesseldateien (absolute Pfade)

- `C:\Users\benfi\Ablage_System\frontend\src\app\routes\$.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\main.tsx`
- `C:\Users\benfi\Ablage_System\frontend\vite.config.ts`
- `C:\Users\benfi\Ablage_System\frontend\src\components\ui\empty-state.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\components\onboarding\WelcomeModal.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\components\auth\TwoFactorInput.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\app\routes\forgot-password.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\app\routes\reset-password.$token.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\app\routes\admin.sso.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\features\templates\components\GenerateDocumentDialog.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\features\spotlight\components\SpotlightDialog.tsx`
- `C:\Users\benfi\Ablage_System\frontend\src\features\risk-scoring\components\` (6 Komponenten verifiziert)
- `C:\Users\benfi\Ablage_System\frontend\src\components\accessibility\index.tsx`
