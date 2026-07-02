# 07 — Frontend (Spec)

## F1: Token-Ablauf-Redirect (Fix H) — LAUFZEIT-UNVERIFIZIERT
### IST (belegt)
Code vorhanden: `AuthContext.tsx:125-145` `addEventListener('session-expired', ...)` -> `setUser(null)`;
`SessionExpiredModal.tsx` oeffnet bei Event; `PortalLayout.tsx` Listener fuer `portal-session-expired`.
ABER: synthetischer Browser-Test (`window.dispatchEvent(new Event('session-expired'))` + sessionStorage.clear)
fuehrte NICHT zum Redirect auf /login (pathname blieb "/"). Ursache unbestaetigt (Bundle-Cache des Browsers
ODER Router-Re-Eval ODER der synthetische Event repliziert den echten 401-Interceptor-Flow nicht).
### ZIEL / Verifikations-Szenario (echtes 401, nicht synthetisch)
1. Frisch einloggen (frischer Bundle nach Rebuild).
2. Token serverseitig invalidieren (z.B. Refresh-Token loeschen / kurze Ablaufzeit) ODER eine geschuetzte Query
   erzwingen, die echt 401 liefert -> Axios-Interceptor feuert `session-expired`.
3. ERWARTET: App navigiert zu /login (Guard greift), Modal nicht auf totem Shell haengend.
### TDD-Anker
- Playwright-E2E `token_expiry_redirects_to_login` (echter 401 -> /login).
- Unit (vitest) `AuthContext_session_expired_sets_user_null`.
### DoD
- [ ] E2E: echter 401 -> Redirect /login (Belegausgabe).
- [ ] Portal: `portal-session-expired` -> /portal/login.

## F2: Frontend-Pfad-Fixes (13) — VERIFIZIERT-OK (Quelle), Live-OK fuer streckengeschaeft/compliance
Belegt: streckengeschaeft-Modul (9 Calls ASCII->Umlaut) Live 0 Konsolenfehler; retention stats->statistics Live 200;
audit-chain 422 (kein 5xx). Quelle in frontend/src committet. KEIN weiterer Handlungsbedarf ausser Regressionsschutz.
### DoD
- [ ] E2E-Smoke je Modul (streckengeschaeft/compliance/calendar-sync) -> 0 Konsolen-5xx/404.

## F3: ~80 Frontend-Feature-Luecken — Entscheidungs-Matrix (Produktentscheidung)
### IST (belegt)
~80 Frontend-API-Aufrufe ohne Backend-Pendant (404). Cluster (Auswahl): `mlops/*`, `ocr-feedback/*`,
`ocr/queue/*`, `relationships/*`, `privat/estate-planning/*`, `privat/spaces`+`privat/dashboard`,
`automation/rules`, Dashboard-Widget-Summaries (`portfolio/summary`, `insurance/summary`, ...),
`finance/de/ust/*` (Verb-Schema-Drift), Error-Sink `/errors`+`/errors/frontend`.
### ZIEL — pro Cluster EINE Entscheidung (nicht raten)
```
fuer jeden Cluster:
  if Feature soll existieren:  Backend-Endpoint spezifizieren + bauen (eigener Spec/PR)
  elif Frontend-Code ist tot:  FE-Code entfernen (kein toter 404-Call)
  else:                        als bewusste Roadmap-Luecke markieren (UI zeigt Empty-State, kein Fehler)
```
### DoD
- [ ] Matrix mit Entscheidung je Cluster (implement / remove / roadmap) + Begruendung.
- [ ] Nach Umsetzung: Browser-E2E der betroffenen Seiten -> keine 404 in der Konsole.

## F4: Sonstige (Doku, kein Block)
- 0/302 Routen mit `beforeLoad`-Guard (admin nur Backend-403) -> Guard-Spec optional.
- Token in sessionStorage (kein httpOnly) -> separater Security-Track (nicht hier).