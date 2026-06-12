# Manifest w3b-tsc-zero (2026-06-12)

Branch: `fix/w3b-tsc-zero` (Worktree `.claude/worktrees/w2-frontend`, abgezweigt von `fix/w3-frontend`)

## Erledigt
1. **apiClient-Doppel-Prefix BESTAETIGT + Massenfix**: baseURL `/api/v1` + Call-Sites mit
   `/api/v1/...` ergaben zur Laufzeit `/api/v1/api/v1/...` → 404 (axios 1.13.2 `getUri`-Repro,
   nginx proxyt `/api/` 1:1). 160 Call-Sites in 44 Dateien gefixt; raw-fetch/Browser-URLs/
   WebSockets bewusst unveraendert. 3 neue Vitest-Regressionstests
   (`src/lib/api/__tests__/api-url-prefix.test.ts`) inkl. statischem Guard ueber src/**.
2. **tsc 352 → 0** (`npx tsc -b --force`), in 17 Commits mit Zaehler im Body.
   Echte Kontrakt-Drifts gegen Backend-Schemas behoben (Retirement, ESG, Spesen,
   Kassenbuch, Company, 2FA, Dunning, DATEV-Kontierung, Estate-Planning u. v. m.),
   Lib-Migrationen (Zod v4, react-query v5, recharts v3, react-resizable-panels v4,
   @xyflow/react v12, dompurify/mammoth-Typen), kein `any`-Teppich.

## Wuensche / Befunde ausserhalb der Zone (frontend/**)

### W3B-TSC-B1: Backend-Bug Kilometergeld-Endpoint (P2, 500er)
`app/api/v1/expenses.py::calculate_mileage` liest `data.rate_per_km`, aber das
Request-Schema `MileageCalculationRequest` (app/db/schemas.py:5586, Alias
`MileageCalculateRequest`) hat nur `kilometers` + `vehicle_type` → AttributeError/500
bei jedem Aufruf von POST /expenses/mileage. Fix-Vorschlag: entweder `rate_per_km`
ins Schema aufnehmen oder den Satz aus `vehicle_type` ableiten.
(Frontend wurde auf das dokumentierte Schema {kilometers, vehicle_type} ausgerichtet.)

### Hinweis
`features/datev/components/connect/KontierungPage.tsx` zeigte Phantomfelder
(`document_info.filename/lieferant/betrag`), die der Suggestions-Endpoint nicht liefert —
Frontend zeigt jetzt ehrlich nur `document_id`. Falls die Anzeige gewuenscht ist,
braeuchte der Backend-Endpoint (GET /datev/connect/kontierung/{id}/suggestions)
eine angereicherte Response (Dokument-Metadaten-Join).
