# Manifest w3-frontend (Welle 3)

Branch: `fix/w3-frontend` (Worktree `.claude/worktrees/w2-frontend`)

## Tabu-Datei-Wuensche

Keine — alle Aenderungen lagen in `frontend/**`.

## Cross-Stream-Befund (NEU, bitte triagieren)

**Doppelter `/api/v1`-Prefix bei apiClient-Aufrufen (potenziell tote Features).**

- `apiClient` (frontend/src/lib/api/client.ts) hat `baseURL = VITE_API_URL || '/api/v1'`;
  `VITE_API_URL` ist in keinem Build gesetzt (nur auskommentiert in `.env.example`).
- 20+ Dateien rufen trotzdem `apiClient.get('/api/v1/...')` auf → Axios kombiniert zu
  `/api/v1/api/v1/...` (Pfad beginnend mit `/` ist fuer Axios NICHT absolut).
- Betroffen u. a.: saved-filters, developer-portal (Webhooks), gobd-api, push-api,
  diverse Dashboard-Widgets (Approvals/CashPosition/Compliance/ImportSync/MLOps/
  Portfolio/Proactive/PropertyKPIs), MobileNav/QuickActions, admin/sso,
  admin/correction-workbench, admin/custom-fields, admin/rules, smart-queue.
- Verdacht: Diese Aufrufe laufen im Stack auf 404 (sofern nginx nicht umschreibt).
  NICHT in W3 frontend-seitig massengefixt (Blast-Radius; Laufzeitverifikation
  gegen Container noetig — Stack-Interaktion war fuer W3-Streams untersagt).
- Empfehlung: per curl gegen den laufenden Container je 1 Endpunkt verifizieren,
  dann Frontend-Sweep (Prefix entfernen) ODER nginx-Rewrite dokumentieren.

## Ehrlicher Reststand tsc (W1-005)

- Start 1188 → **362** Fehler (`npx tsc --noEmit -p tsconfig.app.json`).
- Erledigt: alle toten Router-Links (TS2820/Routen-TS2353/Routen-TS2322 = 0),
  AxiosResponse-`.data`-Bugs (8 API-Module), Lineage/xyflow v12, Privat/Steuern,
  Reports, Workflow-Versionen, Imports-Modul (inkl. ehrlicher
  sourceType/stopOnMatch-Bereinigung), KI-Assistent, TS6133 261→0, TS7006 64→0,
  TS2304/TS2307/TS2300/TS2503 = 0.
- Rest: ~362 verteilte API-Typ-Drift-Fehler (TS2339/TS2322/TS2345) in ~100 Dateien,
  groesste Cluster: StructuredReviewPanel (22), RetirementPlanningPage (12),
  SupplierRatingsPage (12), use-document-upload (11), SupplierRankingDashboard (10),
  NotificationPreferencesPage (10). Muster sind dieselben wie in den erledigten
  Clustern (Feld-Drift FE↔BE); Folge-Slot einplanbar.
