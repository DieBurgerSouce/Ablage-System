---
name: webapp-testing
description: Playwright-basiertes Web-App Testing fuer das Ablage-System. Nutze diesen Skill wenn du Frontend-Tests schreiben, UI-Verhalten debuggen, Screenshots aufnehmen oder Browser-Logs analysieren musst. Funktioniert mit Docker (localhost:80).
---

# Web Application Testing (Ablage-System)

Teste lokale Web-Anwendungen mit nativen Python Playwright-Scripts.

## Projekt-Kontext

- **Frontend**: React + TypeScript unter `http://localhost:80` (via Nginx)
- **Backend API**: `http://localhost:8000`
- **4 Display-Modi**: Dark, Light, Whitescreen, Blackscreen

## Helper Scripts

- `scripts/with_server.py` - Server-Lifecycle-Management

**Immer erst `--help` ausfuehren** bevor du den Quellcode liest!

## Entscheidungsbaum

```
Aufgabe → Statisches HTML?
    ├─ Ja → HTML direkt lesen, Selektoren identifizieren
    │        └─ Playwright-Script mit Selektoren schreiben
    │
    └─ Nein (dynamische App) → Docker laeuft?
        ├─ Nein → docker-compose up -d starten
        │
        └─ Ja → Reconnaissance-then-action:
            1. Navigieren + auf networkidle warten
            2. Screenshot oder DOM inspizieren
            3. Selektoren aus gerendertem State identifizieren
            4. Aktionen mit gefundenen Selektoren ausfuehren
```

## Beispiel: Frontend testen

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # Ablage-System Frontend
    page.goto('http://localhost:80')
    page.wait_for_load_state('networkidle')  # KRITISCH: Warten bis JS geladen

    # Display-Mode testen
    page.click('[data-testid="theme-toggle"]')
    page.screenshot(path='/tmp/dark-mode.png', full_page=True)

    browser.close()
```

## Reconnaissance-Then-Action Pattern

1. **DOM inspizieren**:
   ```python
   page.screenshot(path='/tmp/inspect.png', full_page=True)
   content = page.content()
   buttons = page.locator('button').all()
   ```

2. **Selektoren identifizieren** aus Ergebnissen

3. **Aktionen ausfuehren** mit gefundenen Selektoren

## Haeufiger Fehler

- **NICHT** DOM inspizieren BEVOR `networkidle` erreicht ist
- **IMMER** `page.wait_for_load_state('networkidle')` vor Inspektion

## Best Practices

- `sync_playwright()` fuer synchrone Scripts
- Browser immer schliessen
- Beschreibende Selektoren: `text=`, `role=`, CSS, IDs
- Waits hinzufuegen: `page.wait_for_selector()`, `page.wait_for_timeout()`

## Ablage-System spezifische Selektoren

```python
# Navigation
page.click('[data-testid="nav-documents"]')
page.click('[data-testid="nav-ocr"]')

# OCR Upload
page.set_input_files('[data-testid="file-upload"]', 'test.pdf')

# Display Mode Toggle
page.click('[data-testid="theme-toggle"]')
```

## Docker-Integration

```bash
# Sicherstellen dass Services laufen
docker-compose up -d

# Frontend-Logs pruefen
docker-compose logs -f frontend

# Bei Fehlern neu bauen
docker-compose build frontend && docker-compose up -d frontend
```
