---
name: test-webapp
description: Vollständiger WebApp-Test wie ein QA-Engineer - nutzt Playwright MCP für echte Browser-Automatisierung
argument-hint: "[focus-bereich] z.B. 'navigation', 'forms', 'ocr-upload', 'all'"
allowed-tools:
  - mcp__playwright__*
  - Bash
  - Read
  - Write
---

# WebApp Tester - Vollständiger QA-Durchlauf

Du bist jetzt ein erfahrener QA-Engineer der das Ablage-System systematisch testet.

## Skill laden

@.claude/skills/webapp-tester-mcp.md

## PFLICHT-Preconditions (W2-Playbook — VOR allem anderen ausführen!)

Reproduzierbarkeit + 0 PII-Egress: Es wird AUSSCHLIESSLICH gegen die geseedete
Test-Instanz getestet (synthetische Daten). Details: `.claude/Docs/Testing/QA_AGENT_PLAYBOOK.md`

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
docker compose -f docker-compose.yml -f docker-compose.test.yml exec -T backend python - < scripts/seed_e2e.py
curl -X POST http://localhost:8000/api/v1/test/reset-state
```

Login: `admin@localhost.com` / `admin123` (Seed-Standard).
Abschlussbericht zusätzlich nach `docs/qa-reports/<YYYY-MM-DD>-qa-agent.md` schreiben
(Bug-Report-Format aus dem Playbook, inkl. Journey-IDs J1-J6).

## Kontext

- **Frontend**: http://localhost:80 (React + TypeScript via Nginx)
- **Backend API**: http://localhost:8000 (FastAPI)
- **Ziel**: Vollständiger, menschenähnlicher Test der gesamten Anwendung

## Deine Aufgabe

Führe einen **systematischen 4-Phasen-Test** durch:

### Phase 1: Reconnaissance (Erkundung)
1. Navigiere zu http://localhost:80
2. Warte auf vollständiges Laden (networkidle)
3. Erstelle einen Accessibility Snapshot
4. Identifiziere ALLE interaktiven Elemente
5. Dokumentiere die Seitenstruktur
6. Mache einen Screenshot als Baseline

### Phase 2: Funktionale Tests
Teste systematisch:

**Navigation:**
- [ ] Alle Hauptnavigations-Links funktionieren
- [ ] Breadcrumbs korrekt
- [ ] Browser Back/Forward funktioniert

**Formulare:**
- [ ] Login/Auth Flow (falls vorhanden)
- [ ] Dokument-Upload funktioniert
- [ ] Suchfunktion funktioniert
- [ ] Validierung zeigt Fehlermeldungen

**Kernfunktionen:**
- [ ] OCR-Verarbeitung startet
- [ ] Dokumente werden angezeigt
- [ ] Filter/Sortierung funktioniert

### Phase 3: Edge Cases & Deutsch
Teste kritische Szenarien:

**Deutsche Zeichen (KRITISCH):**
- [ ] Eingabe: "Müller-Strauß GmbH"
- [ ] Eingabe: "Größenordnung €1.234,56"
- [ ] Korrekte Darstellung UND Verarbeitung

**Error Handling:**
- [ ] Leere Formulare → Fehlermeldung?
- [ ] Ungültige Eingaben → Handling?
- [ ] API Fehler → User-Feedback?

**Display Modes:**
- [ ] Dark Mode Toggle
- [ ] Light Mode Toggle
- [ ] Screenshot von jedem Mode

### Phase 4: Dokumentation
Erstelle einen strukturierten Bericht:

```markdown
# Testbericht Ablage-System
Datum: [HEUTE]
Tester: Claude (WebApp Tester MCP)

## Zusammenfassung
- Getestete Seiten: X
- Gefundene Fehler: Y
- Kritische Fehler: Z

## Ergebnisse
[Details zu jedem Test]

## Screenshots
[Pfade zu allen erstellten Screenshots]

## Empfehlungen
[Konkrete Verbesserungsvorschläge]
```

## Fokus-Bereich (optional)

Falls ein spezifischer Bereich angegeben wurde ("$ARGUMENTS"), fokussiere dich darauf:
- `navigation` → Nur Navigations-Tests
- `forms` → Nur Formular-Tests
- `ocr-upload` → Nur OCR-Upload-Flow
- `german` → Nur Deutsche Zeichensatz-Tests
- `all` oder leer → Vollständiger Durchlauf

## Wichtige Regeln

1. **IMMER** `browser_snapshot` VOR jeder Interaktion
2. **IMMER** auf `networkidle` warten nach Navigation
3. **NIEMALS** blind klicken ohne vorherigen State-Check
4. **ALLE** Screenshots in `/tmp/webapp-test/` speichern
5. **JEDEN** Fehler mit Screenshot dokumentieren

## Los geht's!

Starte jetzt mit Phase 1: Reconnaissance.
Berichte nach jeder Phase kurz den Status bevor du zur nächsten übergehst.
