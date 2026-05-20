"""
Test: Privat-Modul spaceId-Fix Verification
Testet ob Modul-Seiten ohne spaceId in der URL korrekt funktionieren
"""

from playwright.sync_api import sync_playwright
import time

BASE_URL = "http://localhost"
TEST_USER = {"email": "admin@localhost.com", "password": "admin123"}

def test_privat_module_pages():
    """Testet alle Privat-Modul-Seiten ohne spaceId in der URL"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        results = {
            "passed": [],
            "failed": [],
            "console_errors": []
        }

        # Capture console errors
        page.on("console", lambda msg: results["console_errors"].append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)

        try:
            # 1. Login
            print("1. Login...")
            page.goto(f"{BASE_URL}/login")
            page.wait_for_load_state("networkidle")

            page.fill('#email', TEST_USER["email"])
            page.fill('#password', TEST_USER["password"])
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Check login success
            if "/login" in page.url:
                results["failed"].append("Login failed")
                print("   FAILED: Login failed")
            else:
                results["passed"].append("Login successful")
                print("   PASSED: Login successful")

            # 2. Test Privat Dashboard
            print("2. Testing /privat...")
            page.goto(f"{BASE_URL}/privat")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Check for spaces section
            spaces_heading = page.locator("text=Meine Bereiche").first
            if spaces_heading.is_visible():
                results["passed"].append("/privat loads correctly")
                print("   PASSED: /privat loads correctly")
            else:
                results["failed"].append("/privat does not show 'Meine Bereiche'")
                print("   FAILED: /privat does not show 'Meine Bereiche'")

            # Check for NaN undefined bug fix
            nan_check = page.locator("text=NaN").count()
            undefined_check = page.locator("text=undefined").count()
            if nan_check == 0 and undefined_check == 0:
                results["passed"].append("No NaN/undefined visible")
                print("   PASSED: No NaN/undefined visible")
            else:
                results["failed"].append(f"NaN or undefined still visible (NaN: {nan_check}, undefined: {undefined_check})")
                print(f"   FAILED: NaN or undefined still visible")

            # 3. Test direct module URLs (without spaceId)
            module_urls = [
                ("/privat/fahrzeuge", "Fahrzeuge"),
                ("/privat/immobilien", "Immobilien"),
                ("/privat/versicherungen", "Versicherungen"),
                ("/privat/finanzen", "Finanzen"),
                ("/privat/fristen", "Fristen"),
            ]

            for url, name in module_urls:
                print(f"3. Testing {url}...")
                page.goto(f"{BASE_URL}{url}")
                page.wait_for_load_state("networkidle")
                time.sleep(2)

                # Check for loading or content
                error_text = page.locator("text=Kein Bereich ausgewählt").first
                no_spaces_text = page.locator("text=Noch keine Bereiche").first

                # Screenshot for debugging
                page.screenshot(path=f"/tmp/privat_{name.lower()}.png")

                # If we have spaces, we should not see error
                if error_text.is_visible():
                    results["failed"].append(f"{url}: Shows 'Kein Bereich ausgewählt' error")
                    print(f"   FAILED: {url} shows error")
                elif no_spaces_text.is_visible():
                    results["passed"].append(f"{url}: Correctly shows 'No spaces' message")
                    print(f"   PASSED: {url} shows no-spaces message (expected if no spaces)")
                else:
                    # Check for list/content
                    results["passed"].append(f"{url}: Page loaded correctly")
                    print(f"   PASSED: {url} loaded correctly")

            # 4. Test SpaceDetail with tabs
            print("4. Testing SpaceDetail with module tabs...")

            # First get a space ID
            page.goto(f"{BASE_URL}/privat")
            page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Look for space link
            space_links = page.locator('a[href*="/privat/spaces/"]')
            if space_links.count() > 0:
                # Click first space
                first_space = space_links.first
                space_href = first_space.get_attribute("href")
                print(f"   Found space: {space_href}")
                first_space.click()
                page.wait_for_load_state("networkidle")
                time.sleep(2)

                # Check for tabs
                tabs = ["Übersicht", "Immobilien", "Fahrzeuge", "Versicherungen", "Finanzen", "Fristen"]
                for tab_name in tabs:
                    tab = page.locator(f'button:text("{tab_name}")')
                    if tab.is_visible():
                        tab.click()
                        time.sleep(1)

                        # Check for errors
                        error_visible = page.locator("text=Kein Bereich ausgewählt").is_visible()
                        if error_visible:
                            results["failed"].append(f"SpaceDetail Tab '{tab_name}': Shows error")
                            print(f"   FAILED: Tab '{tab_name}' shows error")
                        else:
                            results["passed"].append(f"SpaceDetail Tab '{tab_name}': Works correctly")
                            print(f"   PASSED: Tab '{tab_name}' works")
            else:
                print("   SKIPPED: No spaces found for SpaceDetail test")

        finally:
            browser.close()

        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        print(f"Passed: {len(results['passed'])}")
        print(f"Failed: {len(results['failed'])}")
        print(f"Console Errors: {len(results['console_errors'])}")

        if results['failed']:
            print("\nFailed tests:")
            for f in results['failed']:
                print(f"  - {f}")

        if results['console_errors']:
            print("\nConsole Errors:")
            for e in results['console_errors'][:10]:  # Show first 10
                print(f"  - {e}")

        return results

if __name__ == "__main__":
    test_privat_module_pages()
