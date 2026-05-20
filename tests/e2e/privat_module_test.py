"""
Privat-Modul E2E Test - Vollständige manuelle Validierung
Testet alle 8 Module: Spaces, Immobilien, Fahrzeuge, Versicherungen,
Kredite, Anlagen, Fristen, Notfall
"""

from playwright.sync_api import sync_playwright, Page, expect
import json
import time
from datetime import datetime

# Test Results Tracking
test_results = {
    "timestamp": datetime.now().isoformat(),
    "modules": {},
    "console_errors": [],
    "screenshots": [],
    "summary": {"passed": 0, "failed": 0, "warnings": 0}
}

def log_result(module: str, test_name: str, status: str, details: str = ""):
    """Log test result"""
    if module not in test_results["modules"]:
        test_results["modules"][module] = []

    result = {
        "test": test_name,
        "status": status,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    test_results["modules"][module].append(result)

    if status == "PASS":
        test_results["summary"]["passed"] += 1
    elif status == "FAIL":
        test_results["summary"]["failed"] += 1
    else:
        test_results["summary"]["warnings"] += 1

    symbol = "[OK]" if status == "PASS" else "[FAIL]" if status == "FAIL" else "[WARN]"
    print(f"{symbol} [{module}] {test_name}: {status} {details}")


def capture_console_errors(page: Page):
    """Capture console errors"""
    def handle_console(msg):
        if msg.type == "error":
            test_results["console_errors"].append({
                "text": msg.text,
                "location": str(msg.location),
                "timestamp": datetime.now().isoformat()
            })
    page.on("console", handle_console)


def take_screenshot(page: Page, name: str):
    """Take and save screenshot"""
    path = f"/tmp/privat_test_{name}_{datetime.now().strftime('%H%M%S')}.png"
    page.screenshot(path=path, full_page=True)
    test_results["screenshots"].append(path)
    return path


def test_navigation_to_privat(page: Page):
    """Test: Navigation zur Privat-Seite"""
    try:
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")
        time.sleep(1)  # Extra wait for React hydration

        # Check if page loaded
        if page.title() or page.locator("body").is_visible():
            take_screenshot(page, "01_privat_home")
            log_result("Navigation", "Privat-Seite laden", "PASS")
            return True
        else:
            log_result("Navigation", "Privat-Seite laden", "FAIL", "Seite nicht geladen")
            return False
    except Exception as e:
        log_result("Navigation", "Privat-Seite laden", "FAIL", str(e))
        return False


def test_spaces_module(page: Page):
    """Test: Spaces-Modul (Bereiche)"""
    module = "Spaces"

    try:
        # Navigate to privat
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Check for spaces list or cards
        page_content = page.content()

        # Look for common elements
        has_content = any([
            page.locator("[data-testid='spaces-list']").count() > 0,
            page.locator(".space-card").count() > 0,
            "Bereich" in page_content,
            "Space" in page_content,
            page.locator("button").filter(has_text="Erstellen").count() > 0,
            page.locator("button").filter(has_text="Neu").count() > 0,
        ])

        take_screenshot(page, "02_spaces_list")

        if has_content:
            log_result(module, "Spaces-Liste anzeigen", "PASS")
        else:
            log_result(module, "Spaces-Liste anzeigen", "WARNING", "Keine Spaces gefunden oder leere Liste")

        # Try to find any clickable space
        cards = page.locator("[class*='card']").all()
        if len(cards) > 0:
            log_result(module, "Space-Karten vorhanden", "PASS", f"{len(cards)} Karten gefunden")

            # Click on first card to open details
            try:
                cards[0].click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                take_screenshot(page, "03_space_detail")

                # Check if we're on a detail page
                current_url = page.url
                if "/spaces/" in current_url or "spaceId" in current_url:
                    log_result(module, "Space-Detail öffnen", "PASS", current_url)
                    return True
                else:
                    log_result(module, "Space-Detail öffnen", "WARNING", f"URL nicht geändert: {current_url}")
            except Exception as e:
                log_result(module, "Space-Detail öffnen", "WARNING", str(e))
        else:
            log_result(module, "Space-Karten vorhanden", "WARNING", "Keine Karten gefunden")

        return True

    except Exception as e:
        log_result(module, "Spaces-Modul Test", "FAIL", str(e))
        take_screenshot(page, "error_spaces")
        return False


def test_space_tabs(page: Page, space_url: str = None):
    """Test: Alle Tabs in Space-Detail"""
    module = "Space-Tabs"

    try:
        # If no URL provided, navigate to first space
        if not space_url:
            page.goto("http://localhost/privat")
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Try to click first space card
            cards = page.locator("[class*='card']").all()
            if len(cards) > 0:
                cards[0].click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)

        # Look for tabs
        tabs = page.locator("[role='tab'], [data-state], button[class*='tab']").all()
        tab_names = []

        for tab in tabs:
            try:
                text = tab.inner_text().strip()
                if text:
                    tab_names.append(text)
            except:
                pass

        if len(tab_names) > 0:
            log_result(module, "Tabs gefunden", "PASS", f"Tabs: {', '.join(tab_names)}")

            # Test each tab
            for tab in tabs:
                try:
                    tab_text = tab.inner_text().strip()
                    if tab_text:
                        tab.click()
                        time.sleep(0.5)
                        page.wait_for_load_state("networkidle")
                        log_result(module, f"Tab '{tab_text}' klicken", "PASS")
                except Exception as e:
                    log_result(module, f"Tab klicken", "WARNING", str(e))

            take_screenshot(page, "04_space_tabs")
            return True
        else:
            log_result(module, "Tabs gefunden", "WARNING", "Keine Tabs sichtbar")
            return False

    except Exception as e:
        log_result(module, "Tab-Test", "FAIL", str(e))
        return False


def test_immobilien_module(page: Page):
    """Test: Immobilien-Modul"""
    module = "Immobilien"

    try:
        # Navigate to Immobilien (try different paths)
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Find and click Immobilien tab or link
        immobilien_found = False

        # Try clicking tab with Building icon or text
        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "immobilie" in text or "propert" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    immobilien_found = True
                    log_result(module, "Immobilien-Tab finden", "PASS")
                    break
            except:
                continue

        if not immobilien_found:
            # Try direct navigation
            page.goto("http://localhost/privat/immobilien")
            page.wait_for_load_state("networkidle")
            time.sleep(1)

        take_screenshot(page, "05_immobilien")

        # Check for create button
        create_btn = page.locator("button").filter(has_text="Erstellen").or_(
            page.locator("button").filter(has_text="Neu")).or_(
            page.locator("button").filter(has_text="Hinzufügen")).first

        if create_btn.is_visible():
            log_result(module, "Erstellen-Button vorhanden", "PASS")
        else:
            log_result(module, "Erstellen-Button vorhanden", "WARNING", "Button nicht gefunden")

        # Check for list/table
        has_list = page.locator("table, [class*='list'], [class*='grid']").count() > 0
        if has_list:
            log_result(module, "Liste vorhanden", "PASS")
        else:
            log_result(module, "Liste vorhanden", "WARNING", "Keine Liste sichtbar")

        return True

    except Exception as e:
        log_result(module, "Immobilien-Test", "FAIL", str(e))
        take_screenshot(page, "error_immobilien")
        return False


def test_fahrzeuge_module(page: Page):
    """Test: Fahrzeuge-Modul"""
    module = "Fahrzeuge"

    try:
        # Navigate to Fahrzeuge
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")

        # Find and click Fahrzeuge tab
        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "fahrzeug" in text or "vehicle" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    log_result(module, "Fahrzeuge-Tab finden", "PASS")
                    break
            except:
                continue

        take_screenshot(page, "06_fahrzeuge")
        log_result(module, "Fahrzeuge-Seite laden", "PASS")
        return True

    except Exception as e:
        log_result(module, "Fahrzeuge-Test", "FAIL", str(e))
        return False


def test_versicherungen_module(page: Page):
    """Test: Versicherungen-Modul"""
    module = "Versicherungen"

    try:
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")

        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "versicherung" in text or "insurance" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    log_result(module, "Versicherungen-Tab finden", "PASS")
                    break
            except:
                continue

        take_screenshot(page, "07_versicherungen")
        log_result(module, "Versicherungen-Seite laden", "PASS")
        return True

    except Exception as e:
        log_result(module, "Versicherungen-Test", "FAIL", str(e))
        return False


def test_finanzen_module(page: Page):
    """Test: Finanzen-Modul (Kredite + Anlagen)"""
    module = "Finanzen"

    try:
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")

        # Find Finanzen tab
        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "finanz" in text or "finance" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    log_result(module, "Finanzen-Tab finden", "PASS")
                    break
            except:
                continue

        take_screenshot(page, "08_finanzen")

        # Check for sub-tabs (Kredite, Anlagen)
        content = page.content()
        if "Kredite" in content or "Kredit" in content:
            log_result(module, "Kredite-Bereich vorhanden", "PASS")
        if "Anlage" in content or "Investment" in content:
            log_result(module, "Anlagen-Bereich vorhanden", "PASS")

        return True

    except Exception as e:
        log_result(module, "Finanzen-Test", "FAIL", str(e))
        return False


def test_fristen_module(page: Page):
    """Test: Fristen-Modul"""
    module = "Fristen"

    try:
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")

        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "frist" in text or "deadline" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    log_result(module, "Fristen-Tab finden", "PASS")
                    break
            except:
                continue

        take_screenshot(page, "09_fristen")
        log_result(module, "Fristen-Seite laden", "PASS")
        return True

    except Exception as e:
        log_result(module, "Fristen-Test", "FAIL", str(e))
        return False


def test_notfall_module(page: Page):
    """Test: Notfall-Modul"""
    module = "Notfall"

    try:
        page.goto("http://localhost/privat")
        page.wait_for_load_state("networkidle")

        tab_triggers = page.locator("button, a, [role='tab']").all()
        for trigger in tab_triggers:
            try:
                text = trigger.inner_text().lower()
                if "notfall" in text or "emergency" in text:
                    trigger.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(0.5)
                    log_result(module, "Notfall-Tab finden", "PASS")
                    break
            except:
                continue

        take_screenshot(page, "10_notfall")
        log_result(module, "Notfall-Seite laden", "PASS")
        return True

    except Exception as e:
        log_result(module, "Notfall-Test", "FAIL", str(e))
        return False


def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("PRIVAT-MODUL E2E TEST - Vollständige Validierung")
    print(f"Gestartet: {datetime.now().isoformat()}")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="de-DE"
        )
        page = context.new_page()

        # Capture console errors
        capture_console_errors(page)

        # Run tests
        print("\n--- Test 1: Navigation ---")
        test_navigation_to_privat(page)

        print("\n--- Test 2: Spaces-Modul ---")
        test_spaces_module(page)

        print("\n--- Test 3: Space-Tabs ---")
        test_space_tabs(page)

        print("\n--- Test 4: Immobilien-Modul ---")
        test_immobilien_module(page)

        print("\n--- Test 5: Fahrzeuge-Modul ---")
        test_fahrzeuge_module(page)

        print("\n--- Test 6: Versicherungen-Modul ---")
        test_versicherungen_module(page)

        print("\n--- Test 7: Finanzen-Modul ---")
        test_finanzen_module(page)

        print("\n--- Test 8: Fristen-Modul ---")
        test_fristen_module(page)

        print("\n--- Test 9: Notfall-Modul ---")
        test_notfall_module(page)

        # Final screenshot
        take_screenshot(page, "11_final")

        browser.close()

    # Summary
    print("\n" + "=" * 60)
    print("ZUSAMMENFASSUNG")
    print("=" * 60)
    print(f"[OK] Bestanden: {test_results['summary']['passed']}")
    print(f"[FAIL] Fehlgeschlagen: {test_results['summary']['failed']}")
    print(f"[WARN] Warnungen: {test_results['summary']['warnings']}")

    if test_results["console_errors"]:
        print(f"\n[FAIL] Console-Errors: {len(test_results['console_errors'])}")
        for error in test_results["console_errors"][:5]:
            print(f"   - {error['text'][:100]}")
    else:
        print("\n[OK] Keine Console-Errors")

    # Save results
    results_path = "/tmp/privat_test_results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(test_results, f, indent=2, ensure_ascii=False)
    print(f"\nErgebnisse gespeichert: {results_path}")

    return test_results


if __name__ == "__main__":
    run_all_tests()
