"""
Privat-Modul MANUELLER Test als Claude
- Login mit admin@localhost.com / admin123
- Systematisches Durchklicken aller Module
- Screenshots und detaillierte Dokumentation
"""

from playwright.sync_api import sync_playwright, Page
import time
from datetime import datetime
import json
import os

# Test-Ergebnisse
results = {
    "start": datetime.now().isoformat(),
    "tests": [],
    "errors": [],
    "screenshots": []
}

def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    results["tests"].append({"time": datetime.now().isoformat(), "msg": msg})

def error(msg: str):
    print(f"[ERROR] {msg}")
    results["errors"].append({"time": datetime.now().isoformat(), "msg": msg})

def screenshot(page: Page, name: str):
    path = f"C:/Users/benfi/Ablage_System/tests/e2e/screenshots/{name}.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.screenshot(path=path, full_page=True)
    results["screenshots"].append(path)
    log(f"Screenshot: {name}.png")
    return path

def run_manual_test():
    log("=== PRIVAT-MODUL MANUELLER TEST START ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="de-DE"
        )
        page = context.new_page()

        # Console-Errors sammeln
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # ========================================
        # SCHRITT 1: LOGIN
        # ========================================
        log("--- SCHRITT 1: Login ---")
        page.goto("http://localhost/login")
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        screenshot(page, "01_login_page")

        # Login-Formular ausfuellen
        email_input = page.locator('input[type="email"], input[name="email"]').first
        password_input = page.locator('input[type="password"]').first

        if email_input.is_visible() and password_input.is_visible():
            log("Login-Formular gefunden")
            email_input.fill("admin@localhost.com")
            password_input.fill("admin123")
            screenshot(page, "02_login_filled")

            # Submit
            submit_btn = page.locator('button[type="submit"]').first
            submit_btn.click()
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            current_url = page.url
            if "/login" not in current_url:
                log(f"Login erfolgreich! URL: {current_url}")
                screenshot(page, "03_after_login")
            else:
                error(f"Login fehlgeschlagen! Noch auf: {current_url}")
                screenshot(page, "03_login_failed")
                # Versuche trotzdem weiterzumachen
        else:
            error("Login-Formular nicht gefunden!")
            screenshot(page, "02_no_login_form")

        # ========================================
        # SCHRITT 2: PRIVAT-SEITE NAVIGATION
        # ========================================
        log("--- SCHRITT 2: Navigation zu /privat ---")
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        current_url = page.url
        log(f"Aktuelle URL: {current_url}")
        screenshot(page, "04_privat_page")

        if "/login" in current_url:
            error("Redirect zu Login - Auth-Problem!")
        else:
            log("Privat-Seite geladen")

        # Preufe was auf der Seite ist
        page_text = page.inner_text("body")
        log(f"Seiteninhalt (erste 500 Zeichen): {page_text[:500]}")

        # ========================================
        # SCHRITT 3: SPACES/BEREICHE FINDEN
        # ========================================
        log("--- SCHRITT 3: Spaces/Bereiche ---")

        # Suche nach Cards oder Listen
        cards = page.locator("[class*='card'], [class*='Card']").all()
        log(f"Gefundene Cards: {len(cards)}")

        for i, card in enumerate(cards[:5]):  # Max 5 Cards pruefen
            try:
                card_text = card.inner_text()[:100].replace("\n", " ")
                log(f"  Card {i+1}: {card_text}")
            except:
                pass

        # Klicke auf erste Card wenn vorhanden
        if len(cards) > 0:
            log("Klicke auf erste Card...")
            try:
                cards[0].click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                screenshot(page, "05_first_card_clicked")
                log(f"Nach Klick URL: {page.url}")
            except Exception as e:
                error(f"Klick fehlgeschlagen: {e}")

        # ========================================
        # SCHRITT 4: TABS PRUEFEN
        # ========================================
        log("--- SCHRITT 4: Tabs pruefen ---")

        # Suche nach Tabs
        tabs = page.locator("[role='tab'], button[data-state], [class*='TabsTrigger']").all()
        log(f"Gefundene Tabs: {len(tabs)}")

        tab_names = []
        for tab in tabs:
            try:
                text = tab.inner_text().strip()
                if text and len(text) < 30:
                    tab_names.append(text)
            except:
                pass

        if tab_names:
            log(f"Tab-Namen: {', '.join(tab_names)}")

            # Teste jeden Tab
            for i, tab in enumerate(tabs):
                try:
                    text = tab.inner_text().strip()
                    if text and len(text) < 30:
                        log(f"  Klicke Tab: {text}")
                        tab.click()
                        time.sleep(0.5)
                        page.wait_for_load_state("networkidle")
                        screenshot(page, f"06_tab_{i}_{text[:10]}")
                except Exception as e:
                    error(f"Tab-Klick fehlgeschlagen: {e}")
        else:
            log("Keine Tabs gefunden")

        # ========================================
        # SCHRITT 5: CREATE-BUTTONS PRUEFEN
        # ========================================
        log("--- SCHRITT 5: Create-Buttons ---")

        create_buttons = page.locator("button").filter(has_text="Erstellen").all()
        create_buttons += page.locator("button").filter(has_text="Neu").all()
        create_buttons += page.locator("button").filter(has_text="Hinzufuegen").all()

        log(f"Gefundene Create-Buttons: {len(create_buttons)}")

        if len(create_buttons) > 0:
            try:
                log("Klicke ersten Create-Button...")
                create_buttons[0].click()
                time.sleep(1)
                screenshot(page, "07_create_dialog")

                # Schliesse Dialog wieder
                close_btn = page.locator("button").filter(has_text="Abbrechen").first
                if close_btn.is_visible():
                    close_btn.click()
                    time.sleep(0.5)
                    log("Dialog geschlossen")
                else:
                    # ESC druecken
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
            except Exception as e:
                error(f"Create-Button Test fehlgeschlagen: {e}")

        # ========================================
        # SCHRITT 6: IMMOBILIEN DIREKT TESTEN
        # ========================================
        log("--- SCHRITT 6: Immobilien-Modul ---")

        # Zurueck zur Privat-Seite
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Finde Immobilien-Tab
        immo_tab = page.locator("[role='tab'], button").filter(has_text="Immobilien").first
        if immo_tab.is_visible():
            immo_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "08_immobilien")
            log("Immobilien-Tab geoeffnet")

            # Preufe Inhalt
            content = page.inner_text("body")
            if "Keine Immobilien" in content or len(content) < 100:
                log("Immobilien-Liste leer oder minimal")
            else:
                log(f"Immobilien-Inhalt: {content[:300]}")
        else:
            log("Immobilien-Tab nicht gefunden")

        # ========================================
        # SCHRITT 7: FAHRZEUGE
        # ========================================
        log("--- SCHRITT 7: Fahrzeuge-Modul ---")

        fahr_tab = page.locator("[role='tab'], button").filter(has_text="Fahrzeuge").first
        if fahr_tab.is_visible():
            fahr_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "09_fahrzeuge")
            log("Fahrzeuge-Tab geoeffnet")
        else:
            log("Fahrzeuge-Tab nicht gefunden")

        # ========================================
        # SCHRITT 8: VERSICHERUNGEN
        # ========================================
        log("--- SCHRITT 8: Versicherungen-Modul ---")

        vers_tab = page.locator("[role='tab'], button").filter(has_text="Versicherungen").first
        if vers_tab.is_visible():
            vers_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "10_versicherungen")
            log("Versicherungen-Tab geoeffnet")
        else:
            log("Versicherungen-Tab nicht gefunden")

        # ========================================
        # SCHRITT 9: FINANZEN
        # ========================================
        log("--- SCHRITT 9: Finanzen-Modul ---")

        fin_tab = page.locator("[role='tab'], button").filter(has_text="Finanzen").first
        if fin_tab.is_visible():
            fin_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "11_finanzen")
            log("Finanzen-Tab geoeffnet")

            # Preufe Sub-Tabs (Kredite/Anlagen)
            sub_tabs = page.locator("[role='tab'], button").filter(has_text="Kredite").all()
            sub_tabs += page.locator("[role='tab'], button").filter(has_text="Anlagen").all()
            log(f"Finanzen Sub-Tabs: {len(sub_tabs)}")
        else:
            log("Finanzen-Tab nicht gefunden")

        # ========================================
        # SCHRITT 10: FRISTEN
        # ========================================
        log("--- SCHRITT 10: Fristen-Modul ---")

        frist_tab = page.locator("[role='tab'], button").filter(has_text="Fristen").first
        if frist_tab.is_visible():
            frist_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "12_fristen")
            log("Fristen-Tab geoeffnet")
        else:
            log("Fristen-Tab nicht gefunden")

        # ========================================
        # SCHRITT 11: NOTFALL
        # ========================================
        log("--- SCHRITT 11: Notfall-Modul ---")

        notfall_tab = page.locator("[role='tab'], button").filter(has_text="Notfall").first
        if notfall_tab.is_visible():
            notfall_tab.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)
            screenshot(page, "13_notfall")
            log("Notfall-Tab geoeffnet")
        else:
            log("Notfall-Tab nicht gefunden")

        # ========================================
        # ZUSAMMENFASSUNG
        # ========================================
        log("=== TEST ABGESCHLOSSEN ===")
        log(f"Console-Errors: {len(console_errors)}")
        for err in console_errors[:10]:
            error(f"Console: {err[:100]}")

        results["console_errors"] = console_errors
        results["end"] = datetime.now().isoformat()

        # Speichere Ergebnisse
        results_path = "C:/Users/benfi/Ablage_System/tests/e2e/test_results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        log(f"Ergebnisse gespeichert: {results_path}")

        # Final Screenshot
        screenshot(page, "14_final")

        browser.close()

    # Ausgabe der Zusammenfassung
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"Tests durchgefuehrt: {len(results['tests'])}")
    print(f"Fehler: {len(results['errors'])}")
    print(f"Console-Errors: {len(results.get('console_errors', []))}")
    print(f"Screenshots: {len(results['screenshots'])}")

    if results['errors']:
        print("\nFEHLER:")
        for err in results['errors']:
            print(f"  - {err['msg']}")

    return results

if __name__ == "__main__":
    run_manual_test()
