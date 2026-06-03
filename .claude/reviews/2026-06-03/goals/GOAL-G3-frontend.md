<!--
/goal-Prompt — Strom G3: Frontend Mocks -> echt
WELLE 1 — laeuft parallel mit G1, G2, G4 (nur frontend/src/**, komplett unabhaengig). Worktree/Branch: feature/g3-frontend-mocks
Hinweis: einige Empty-States verschwinden automatisch, sobald G1 die fehlenden Endpoints liefert.
Den Text ab "===" als /goal in eine Claude-Code-Session einfügen.
-->

=== GOAL G3 ===

Setze den Remediation-Strom **G3 "Frontend Mocks -> echt"** im Repo `C:\Users\benfi\Ablage_System` um. Arbeite AUSSCHLIESSLICH innerhalb von `frontend/src/**` (konfliktfreie Parallelitaet via git-worktree). Aendere KEINE Backend-Dateien.

## Kontext
Mehrere Frontend-Views zeigen erfundene Mock-/Zufallsdaten (Math.random, generateMock*) als echt an oder taeuschen Aktionen vor, die nicht persistieren. Quelle: `.claude/reviews/2026-06-03/MOCK_DATA_REGISTER.md` (M18-M23). Die echten API-Hooks existieren in den meisten Faellen bereits ungenutzt.

## Constraints (verbindlich)
- ALLE user-facing Texte DEUTSCH (UTF-8 Umlaute korrekt).
- mypy-Aequivalent fuer TS: `npx tsc --noEmit` muss sauber sein, KEINE `any`-Typen einfuehren.
- Rule 1/8: KEIN PII-Logging (keine USt-IdNr., Kundennr., IBANs in logger.*).
- Rule 7 (shadcn Select): NIEMALS `value=""` - vorhandene Werte 'alle'/'all'/'auto' beibehalten.
- KEINE random-Zufallsdaten/generateMock im Render-Pfad der genannten Views (Definition-of-Done).
- KEINE erfundenen Daten als echt darstellen -> stattdessen ehrlicher Empty-State.
- Tests MUESSEN vor Abschluss gruen sein (`npx vitest run`).

## Aufgaben

### 1. M18 Knowledge-Graph (RiskNetworkView.tsx, FinancialChainView.tsx, DocumentFamilyView.tsx)
Die 3 Views unter `frontend/src/features/knowledge-graph/views/` rufen bereits die echten Hooks `useRiskNetwork`/`useFinancialChain`/`useDocumentFamily` (aus `../hooks/use-knowledge-graph-queries.ts`, die `knowledge-graph-api.ts` nutzen) auf, fallen aber bei leeren API-Daten auf `generateMock*()` zurueck.
- Entferne `generateMockRiskNetwork`/`generateMockFinancialChain`/`generateMockDocumentFamily` samt Hilfsdaten (`seededRandom`, `GERMAN_COMPANIES`, `COMMUNITY_NAMES`, `COMMUNITY_COLORS`, Mock-Typen) UND die ungenutzten lokalen Hooks `useRiskNetworkData`/`useFinancialChainData`/`useDocumentFamilyData`.
- Ersetze im `useMemo`-Mapping den `return generateMock...()`-Fallback durch leere Strukturen (`{entities:[],edges:[],communities:[]}` bzw. `{documents:[],links:[]}`). Benenne die Variable `mockData` in `graphData`/`networkData`/`familyData` um.
- `isLoading`/`error` aus `useQuery` bleiben durchgereicht; vorhandene Lade-/Fehler-/Empty-Card-Bloecke wiederverwenden, sodass bei leeren echten Daten der Empty-State greift statt Mock.

### 2. M18 Tests (`frontend/src/features/knowledge-graph/__tests__/KnowledgeGraphViews.test.tsx`)
Die Tests 'rendert ... wenn Daten vorhanden' setzen `data:null` und erwarten Mock-Fallback (Kommentare 'faellt auf Mock-Daten zurueck'). Nach Mock-Entfernung anpassen:
- Diese Faelle auf echte befuellte `data`-Objekte umstellen (mind. 1 Entity/Stage/Dokument) -> ReactFlow-Container rendert.
- Je View einen Test ergaenzen: `data` mit leeren Arrays -> Empty-State-Text sichtbar ('Keine Risiko-Daten verfuegbar' / 'Keine Finanzketten ... gefunden' / 'Keine Dokumentenfamilie gefunden').
- Lade-/Fehler-Tests unveraendert lassen. Bestehende `vi.mock`-Struktur + `createQueryWrapper` wiederverwenden.

### 3. M19 Streckengeschaeft-Validierung (`frontend/src/app/routes/streckengeschaeft.validierung.tsx`)
Hardcodiertes `mockData`-Array (6 ValidationItems, Z.27-88) + `useState(mockData)` entfernen.
- Liste via `useDropShipmentList({isConfirmed:false})` aus `features/drop-shipment/hooks` laden und `DropShipmentClassification` -> Tabellenschema mappen (confidence = `confidenceScore*100`, status aus `isConfirmed`, vatId aus `parties[].vatId`, vatIdValid konservativ `null` wenn unbekannt - NICHTS erfinden).
- Approve -> `useConfirmClassification().mutateAsync({classificationId})`. Reject -> `useOverrideClassification().mutateAsync({classificationId, newClassificationType:'domestic', reason:'Manuell abgelehnt'})` (Backend hat keinen dedizierten Reject-Status; im Code kommentieren + an G1 als Folge melden).
- Toast erst in `onSuccess` der Mutation. `isLoading` -> Spinner, `error` -> Fehler-Card, leere `items` -> `EmptyState`.
- Filter-Selects bleiben (Werte 'alle'/'hoch'/'mittel'/'niedrig' sind bereits Rule-7-konform). KEIN PII in Logs.

### 4. M20 Reports (`frontend/src/features/reports/api/report-data-api.ts`)
Entferne `_getFallbackData` + `_fallbackCostAnalysis`/`_fallbackCashflowForecast`/`_fallbackDocumentVolume` (Math.random, Z.126-293). Im finalen catch von `fetchReportData` statt synthetischer Daten einen typisierten Fehler werfen (eigene Error-Klasse mit `templateId`). Konsumierende Report-View auf Empty-State/Hinweis umstellen ('Berichtsdaten derzeit nicht verfuegbar'). `logger.warn` als Telemetrie beibehalten (nur `templateId`, keine Nutzdaten). Rueckgabetyp bleibt typsicher oder wirft.

### 5. M21 Import-Wizard (`frontend/src/features/import-wizard/api/wizard-api.ts`)
In `useEmailPreview` + `useFolderPreview` den 404-Zweig entfernen, der ein Fake-`ImportPreviewResponse` ({itemCount:0, warnings:['Vorschau-Funktion noch nicht verfuegbar']}) liefert. Stattdessen 404 als `WizardApiError(statusCode:404)` durchreichen; Vorschau-Komponente zeigt echten Empty-State ('Vorschau noch nicht verfuegbar'), nicht ein Fake-0-Items-Ergebnis. `enabled`/`retry:false` beibehalten.

### 6. M22 StatusChangeDropdown (`frontend/src/features/ablage/components/StatusChangeDropdown.tsx`)
In `handlePaymentStatusChange` wird fuer status != 'bezahlt' nur `logger.warn` ausgegeben, danach aber faelschlich `onSuccess()` aufgerufen.
- `STATUS_OPTIONS` um `supported:boolean` erweitern (nur 'bezahlt' = true).
- Nicht unterstuetzte `DropdownMenuItem` `disabled` rendern mit Hinweis ('noch nicht verfuegbar'), onClick no-op.
- `onSuccess()` NUR nach erfolgreicher `bulkMarkAsPaid.mutateAsync`; bei nicht unterstuetztem Status frueh `return` ohne `onSuccess()`. logger ohne PII.

### 7. M23 Job-Queue-Charts (`SuccessRateChart.tsx`, `QueueLengthChart.tsx`, `JobThroughputChart.tsx` + `components/tabs/OverviewTab.tsx`)
In allen 3 Charts `generateMockData()` (Math.random) loeschen; `return data || generateMockData()` -> `return data ?? []`. Bei leerem `chartData` && `!isLoading`: Empty-State im CardContent ('Keine Daten fuer den gewaehlten Zeitraum') statt leerem/zufaelligem Diagramm.
- WICHTIG: `OverviewTab.tsx` (Z.352-353) rendert `JobThroughputChart`/`SuccessRateChart` OHNE `data`-Prop -> sie zeigen aktuell IMMER Zufallsdaten. Echte Daten aus vorhandenen Hooks (`useJobStats`) durchreichen; falls kein 24h-Verlaufs-Endpoint existiert, Chart leer (Empty-State) lassen und als Folgepunkt vermerken statt Mock. `QueueLengthChart` bekommt bereits echte Daten.

### 8. Optional/Folgepunkt: Token sessionStorage -> httpOnly-Cookie
NICHT eigenmaechtig umsetzen (betrifft Auth-Client + Backend Set-Cookie/CSRF). Nur die Stelle im api-client dokumentieren und als Abhaengigkeit zu G2/G1 vermerken. Kein Code-Change in G3.

## Reihenfolge
1->2 (Views + Tests zusammen, sonst rotes vitest) -> 3 (M19) -> 4 -> 5 -> 6 -> 7 -> 8 (nur Notiz).

## Definition of Done
- `cd frontend && npx vitest run` gruen (inkl. neuer Empty-State-Tests).
- `cd frontend && npx tsc --noEmit` ohne Fehler, keine `any`.
- `cd frontend && npm run lint` sauber (keine ungenutzten Imports nach Mock-Entfernung).
- `grep -rn 'generateMock|Math.random'` in den 3 Knowledge-Graph-Views, 3 Job-Queue-Charts, report-data-api.ts, wizard-api.ts, streckengeschaeft.validierung.tsx = 0 Treffer.
- Approve/Reject im Streckengeschaeft loest echte PATCH-Mutation aus (kein reiner lokaler State).
- Alle neuen Texte DEUTSCH, keine PII in Logs, nur frontend/src/** geaendert.
