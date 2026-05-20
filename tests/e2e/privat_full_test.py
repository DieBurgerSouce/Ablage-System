"""
Privat-Modul VOLLSTAENDIGER Test
- Schliesst Onboarding-Dialoge
- Login mit admin@localhost.com / admin123
- Testet alle Module systematisch
"""

from playwright.sync_api import sync_playwright, Page
import time
from datetime import datetime
import json
import os

results = {
    "start": datetime.now().isoformat(),
    "tests": [],
    "errors": [],
    "screenshots": [],
    "passed": 0,
    "failed": 0
}

def log(msg: str, status: str = "INFO"):
    ts = datetime.now().strftime('%H:%M:%S')
    prefix = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[INFO]"
    print(f"{ts} {prefix} {msg}")
    results["tests"].append({"time": ts, "msg": msg, "status": status})
    if status == "PASS":
        results["passed"] += 1
    elif status == "FAIL":
        results["failed"] += 1
        results["errors"].append(msg)

def screenshot(page: Page, name: str):
    path = f"C:/Users/benfi/Ablage_System/tests/e2e/screenshots/{name}.png"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.screenshot(path=path, full_page=True)
    results["screenshots"].append(path)
    return path


def close_any_dialogs(page: Page):
    """Schliesst alle offenen Dialoge/Modals"""
    # Methode 1: X-Button klicken
    close_buttons = page.locator("button[aria-label*='close'], button[aria-label*='Close'], button[class*='DialogClose']").all()
    for btn in close_buttons:
        try:
            if btn.is_visible():
                btn.click(timeout=2000)
                time.sleep(0.3)
                log("Dialog via X-Button geschlossen")
        except:
            pass

    # Methode 2: ESC druecken
    try:
        page.keyboard.press("Escape")
        time.sleep(0.3)
        page.keyboard.press("Escape")
        time.sleep(0.3)
    except:
        pass

    # Methode 3: Spezifisch den Willkommen-Dialog schliessen (X im Header)
    try:
        close_x = page.locator("button.absolute.right-4, button[class*='absolute'][class*='right']").first
        if close_x.is_visible():
            close_x.click(timeout=2000)
            time.sleep(0.3)
            log("Willkommen-Dialog geschlossen")
    except:
        pass

    # Methode 4: Overlay direkt wegklicken (force click ausserhalb)
    try:
        overlay = page.locator("[data-state='open'][class*='fixed'][class*='inset']").first
        if overlay.is_visible():
            # Klick auf das Overlay selbst um es zu schliessen
            page.mouse.click(10, 10)  # Ecke oben links
            time.sleep(0.3)
    except:
        pass


def skip_onboarding(page: Page):
    """Ueberspringt den Onboarding-Wizard komplett"""
    max_attempts = 10
    for i in range(max_attempts):
        # Preufe ob Dialog sichtbar
        dialog = page.locator("[role='dialog'], [class*='Dialog']").first
        if not dialog.is_visible():
            log("Kein Onboarding-Dialog mehr sichtbar")
            return True

        # Versuche X zu klicken
        try:
            # Der X-Button im Screenshot ist oben rechts im Dialog
            x_btn = page.locator("button").filter(has_text="").locator("svg[class*='lucide-x']").first
            if x_btn.is_visible():
                x_btn.click(timeout=2000)
                time.sleep(0.5)
                continue
        except:
            pass

        # Versuche "Weiter" zu klicken um durchzuklicken
        try:
            weiter_btn = page.locator("button").filter(has_text="Weiter").first
            if weiter_btn.is_visible():
                weiter_btn.click(timeout=2000)
                time.sleep(0.5)
                log(f"Onboarding Schritt {i+1} - Weiter geklickt")
                continue
        except:
            pass

        # Versuche "Fertig" oder "Schliessen" zu klicken
        try:
            finish_btn = page.locator("button").filter(has_text="Fertig").or_(
                page.locator("button").filter(has_text="Schliessen")).first
            if finish_btn.is_visible():
                finish_btn.click(timeout=2000)
                time.sleep(0.5)
                log("Onboarding abgeschlossen")
                return True
        except:
            pass

        # ESC als Fallback
        page.keyboard.press("Escape")
        time.sleep(0.3)

    return False


def run_full_test():
    log("=== PRIVAT-MODUL VOLLSTAENDIGER TEST ===")

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
        # SCHRITT 1: Login
        # ========================================
        log("--- SCHRITT 1: Login ---")
        page.goto("http://localhost/login")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(1)

        # Check if already logged in (redirected away from login)
        if "/login" not in page.url:
            log("Bereits eingeloggt", "PASS")
        else:
            # Login durchfuehren
            try:
                email = page.locator('input[type="email"], input[name="email"]').first
                password = page.locator('input[type="password"]').first

                email.fill("admin@localhost.com")
                password.fill("admin123")

                submit = page.locator('button[type="submit"]').first
                submit.click()

                page.wait_for_url(lambda url: "/login" not in str(url), timeout=10000)
                log("Login erfolgreich", "PASS")
            except Exception as e:
                log(f"Login fehlgeschlagen: {e}", "FAIL")

        screenshot(page, "01_after_login")

        # ========================================
        # SCHRITT 2: Zu /privat navigieren
        # ========================================
        log("--- SCHRITT 2: Navigation zu /privat ---")
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(2)

        screenshot(page, "02_privat_with_dialog")

        # ========================================
        # SCHRITT 3: Onboarding-Dialog schliessen
        # ========================================
        log("--- SCHRITT 3: Onboarding-Dialog schliessen ---")
        skip_onboarding(page)
        time.sleep(1)

        # Nochmal ESC zur Sicherheit
        for _ in range(3):
            page.keyboard.press("Escape")
            time.sleep(0.3)

        screenshot(page, "03_privat_clean")

        # ========================================
        # SCHRITT 4: Privat-Seite pruefen
        # ========================================
        log("--- SCHRITT 4: Privat-Seite pruefen ---")

        # Preufe ob Tabs vorhanden
        uebersicht_tab = page.locator("[role='tab']").filter(has_text="Uebersicht").or_(
            page.locator("button").filter(has_text="Uebersicht")).first
        bereiche_tab = page.locator("[role='tab']").filter(has_text="Bereiche").or_(
            page.locator("button").filter(has_text="Bereiche")).first

        if uebersicht_tab.is_visible():
            log("Uebersicht-Tab vorhanden", "PASS")
        else:
            log("Uebersicht-Tab nicht gefunden", "FAIL")

        if bereiche_tab.is_visible():
            log("Bereiche-Tab vorhanden", "PASS")
        else:
            log("Bereiche-Tab nicht gefunden", "FAIL")

        # Preufe Cards
        page_text = page.inner_text("body")

        checks = [
            ("Dokumente" in page_text, "Dokumente-Card vorhanden"),
            ("Immobilien" in page_text, "Immobilien-Card vorhanden"),
            ("Fahrzeuge" in page_text, "Fahrzeuge-Card vorhanden"),
            ("Versicherungen" in page_text, "Versicherungen-Card vorhanden"),
            ("Finanz" in page_text, "Finanzen-Card vorhanden"),
            ("Fristen" in page_text, "Fristen-Card vorhanden"),
        ]

        for condition, name in checks:
            if condition:
                log(name, "PASS")
            else:
                log(name, "FAIL")

        # ========================================
        # SCHRITT 5: Bereiche-Tab testen
        # ========================================
        log("--- SCHRITT 5: Bereiche-Tab ---")
        try:
            bereiche_tab.click(timeout=5000)
            page.wait_for_load_state("networkidle", timeout=60000)
            time.sleep(1)
            screenshot(page, "04_bereiche_tab")
            log("Bereiche-Tab geoeffnet", "PASS")

            # Preufe ob Spaces/Bereiche angezeigt werden
            bereiche_content = page.inner_text("body")
            if "Bereich" in bereiche_content or "Space" in bereiche_content:
                log("Bereiche-Inhalt geladen", "PASS")
            else:
                log("Bereiche-Inhalt nicht gefunden", "FAIL")

        except Exception as e:
            log(f"Bereiche-Tab Fehler: {e}", "FAIL")

        # ========================================
        # SCHRITT 6: Immobilien-Card klicken
        # ========================================
        log("--- SCHRITT 6: Immobilien-Card ---")

        # Zurueck zu Uebersicht
        try:
            uebersicht_tab.click(timeout=5000)
            time.sleep(1)
        except:
            pass

        try:
            immo_card = page.locator("[class*='card']").filter(has_text="Immobilien").first
            if immo_card.is_visible():
                immo_card.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(1)
                screenshot(page, "05_immobilien")
                log("Immobilien-Card geklickt", "PASS")

                # Preufe URL oder Inhalt
                if "/immobilien" in page.url or "Immobilien" in page.inner_text("body"):
                    log("Immobilien-Seite geladen", "PASS")
            else:
                log("Immobilien-Card nicht sichtbar", "FAIL")
        except Exception as e:
            log(f"Immobilien-Test Fehler: {e}", "FAIL")

        # ========================================
        # SCHRITT 7: Fahrzeuge-Card
        # ========================================
        log("--- SCHRITT 7: Fahrzeuge-Card ---")
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(1)
        skip_onboarding(page)
        page.keyboard.press("Escape")
        time.sleep(0.5)

        try:
            fahr_card = page.locator("[class*='card']").filter(has_text="Fahrzeuge").first
            if fahr_card.is_visible():
                fahr_card.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(1)
                screenshot(page, "06_fahrzeuge")
                log("Fahrzeuge-Card geklickt", "PASS")
            else:
                log("Fahrzeuge-Card nicht sichtbar", "FAIL")
        except Exception as e:
            log(f"Fahrzeuge-Test Fehler: {e}", "FAIL")

        # ========================================
        # SCHRITT 8: Versicherungen-Card
        # ========================================
        log("--- SCHRITT 8: Versicherungen-Card ---")
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(1)
        skip_onboarding(page)
        page.keyboard.press("Escape")
        time.sleep(0.5)

        try:
            vers_card = page.locator("[class*='card']").filter(has_text="Versicherungen").first
            if vers_card.is_visible():
                vers_card.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(1)
                screenshot(page, "07_versicherungen")
                log("Versicherungen-Card geklickt", "PASS")
            else:
                log("Versicherungen-Card nicht sichtbar", "FAIL")
        except Exception as e:
            log(f"Versicherungen-Test Fehler: {e}", "FAIL")

        # ========================================
        # SCHRITT 9: Finanzen-Card
        # ========================================
        log("--- SCHRITT 9: Finanzen-Card ---")
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(1)
        skip_onboarding(page)
        page.keyboard.press("Escape")
        time.sleep(0.5)

        try:
            fin_card = page.locator("[class*='card']").filter(has_text="Finanzen").first
            if fin_card.is_visible():
                fin_card.click(timeout=5000)
                page.wait_for_load_state("networkidle", timeout=60000)
                time.sleep(1)
                screenshot(page, "08_finanzen")
                log("Finanzen-Card geklickt", "PASS")
            else:
                log("Finanzen-Card nicht sichtbar", "FAIL")
        except Exception as e:
            log(f"Finanzen-Test Fehler: {e}", "FAIL")

        # ========================================
        # ZUSAMMENFASSUNG
        # ========================================
        log("=== TEST ABGESCHLOSSEN ===")
        results["console_errors"] = console_errors
        results["end"] = datetime.now().isoformat()

        screenshot(page, "09_final")
        browser.close()

    # Ergebnisse ausgeben
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"Bestanden: {results['passed']}")
    print(f"Fehlgeschlagen: {results['failed']}")
    print(f"Console-Errors: {len(results.get('console_errors', []))}")

    if results['errors']:
        print("\nFEHLER:")
        for err in results['errors']:
            print(f"  - {err}")

    if results.get('console_errors'):
        print("\nCONSOLE-ERRORS (erste 5):")
        for err in results['console_errors'][:5]:
            print(f"  - {err[:100]}")

    # Speichern
    with open("C:/Users/benfi/Ablage_System/tests/e2e/full_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return results


if __name__ == "__main__":
    run_full_test()
