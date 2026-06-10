# QA-Agent-Playbook (W2 / Plan-Item 0e)

Reproduzierbare, agentische QA-Läufe gegen das Ablage-System mit Playwright MCP
(`/test-webapp`) — explorativ Bugs finden, die geskriptete Specs nicht abdecken.

## Harte Regeln (PII / Reproduzierbarkeit)

1. **NUR gegen die geseedete Test-Instanz testen** (`docker-compose.test.yml`-Override,
   synthetische Daten aus `scripts/seed_e2e.py`). NIEMALS gegen eine Instanz mit
   echten Dokumenten/Kundendaten → damit ist „0 PII-Egress" prozedural erfüllt,
   ein lokales LLM (Ollama) ist nicht nötig.
2. **Pflicht-Preconditions vor JEDEM Lauf** (deterministischer Ausgangszustand):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
   docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T backend python - < scripts/seed_e2e.py
   curl -X POST http://localhost:8000/api/v1/test/reset-state   # gated, nur bei TESTING=true
   ```
3. Login: `admin@localhost.com` / `admin123` (Seed-Standard, synthetisch).
4. Jeder Lauf erzeugt einen Report nach `docs/qa-reports/<YYYY-MM-DD>-qa-agent.md` (committet).

## Test-Journeys (Pilot-relevant, in dieser Reihenfolge)

| ID | Journey | Kernfrage |
|----|---------|-----------|
| J1 | Login/Auth | Login, Logout, falsches Passwort (deutsche Fehlermeldung?), Session-Ablauf |
| J2 | Upload → OCR-Status | PDF hochladen, Statuswechsel sichtbar (pending→processing→completed), Fehlerfall sichtbar? |
| J3 | Suche & Filter | Dokument per Name/Inhalt finden, Umlaute („Müller-Strauß"), Filter kombinieren |
| J4 | Banking/Reconciliation | CSV-Import, Transaktionsliste, Zahlungsabgleich-Vorschläge |
| J5 | **Company-Wechsel (Multi-Tenant!)** | Firma wechseln, KEINE Daten der anderen Firma sichtbar, kein 500er ohne Firmenauswahl |
| J6 | Fehlerfälle | Ungültige Eingaben, 404-Routen, leere Formulare, doppelte Submits |

## Bug-Report-Format (pro Fund)

```markdown
### [SEVERITY] Kurztitel
- **Journey:** J2
- **Repro:** 1. ... 2. ... 3. ...
- **Erwartet:** ...
- **Tatsächlich:** ... (inkl. HTTP-Status, deutsche/englische Fehlermeldung)
- **Screenshot:** /tmp/webapp-test/<name>.png
- **Console/Network-Errors:** ...
```

Severity: `CRITICAL` (Datenverlust/Leak/Crash), `HIGH` (Kernflow blockiert),
`MEDIUM` (falsches Verhalten mit Workaround), `LOW` (Kosmetik/Inkonsistenz).

## Abgrenzung zu den anderen Harness-Stufen

- **Schemathesis** (`make api-fuzz`): API-Schicht, 5xx-Jagd, deterministisch in CI.
- **Playwright-Specs** (`tests/frontend/e2e/`): geskriptete Regression, CI.
- **Dieser QA-Agent**: explorativ, menschenähnlich, findet UX-/Flow-Brüche —
  Ergebnisse fließen als neue Specs oder Fixes zurück.
