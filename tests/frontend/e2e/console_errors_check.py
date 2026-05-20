"""
Check Console Errors on Privat Module Pages
"""

from playwright.sync_api import sync_playwright
import time
import json

BASE_URL = "http://localhost"

def check_console_errors():
    """Check for console errors on all privat module pages"""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        all_errors = {}
        all_warnings = {}

        # Capture console messages
        def handle_console(msg):
            url = page.url
            if msg.type == "error":
                if url not in all_errors:
                    all_errors[url] = []
                all_errors[url].append(msg.text)
            elif msg.type == "warning":
                if url not in all_warnings:
                    all_warnings[url] = []
                all_warnings[url].append(msg.text)

        page.on("console", handle_console)

        # Pages to test
        pages = [
            "/",
            "/privat",
            "/privat/fahrzeuge",
            "/privat/immobilien",
            "/privat/versicherungen",
            "/privat/finanzen",
            "/privat/fristen",
        ]

        for url in pages:
            print(f"Checking {url}...")
            try:
                page.goto(f"{BASE_URL}{url}", wait_until="networkidle", timeout=30000)
                time.sleep(2)  # Wait for any async errors
            except Exception as e:
                print(f"  Error loading page: {e}")

        browser.close()

        # Report
        print("\n" + "="*60)
        print("CONSOLE ERRORS REPORT")
        print("="*60)

        total_errors = sum(len(v) for v in all_errors.values())
        total_warnings = sum(len(v) for v in all_warnings.values())

        print(f"\nTotal Errors: {total_errors}")
        print(f"Total Warnings: {total_warnings}")

        if all_errors:
            print("\n--- ERRORS BY PAGE ---")
            for url, errors in all_errors.items():
                print(f"\n{url}:")
                unique_errors = list(set(errors))
                for err in unique_errors[:5]:  # Show max 5 unique errors per page
                    # Truncate long error messages
                    if len(err) > 150:
                        err = err[:150] + "..."
                    print(f"  - {err}")

        if all_warnings:
            print("\n--- WARNINGS BY PAGE (first 10) ---")
            shown = 0
            for url, warnings in all_warnings.items():
                if shown >= 10:
                    break
                print(f"\n{url}:")
                for warn in warnings[:3]:
                    if shown >= 10:
                        break
                    if len(warn) > 150:
                        warn = warn[:150] + "..."
                    print(f"  - {warn}")
                    shown += 1

        # Categorize errors
        print("\n--- ERROR CATEGORIES ---")
        error_categories = {
            "403 Forbidden": 0,
            "404 Not Found": 0,
            "500 Server Error": 0,
            "Network Error": 0,
            "React/JS Error": 0,
            "Other": 0,
        }

        for errors in all_errors.values():
            for err in errors:
                if "403" in err:
                    error_categories["403 Forbidden"] += 1
                elif "404" in err:
                    error_categories["404 Not Found"] += 1
                elif "500" in err:
                    error_categories["500 Server Error"] += 1
                elif "Failed to fetch" in err or "network" in err.lower():
                    error_categories["Network Error"] += 1
                elif "React" in err or "TypeError" in err or "Uncaught" in err:
                    error_categories["React/JS Error"] += 1
                else:
                    error_categories["Other"] += 1

        for cat, count in error_categories.items():
            if count > 0:
                print(f"  {cat}: {count}")

        return total_errors, total_warnings

if __name__ == "__main__":
    errors, warnings = check_console_errors()
    print(f"\n✅ Check complete: {errors} errors, {warnings} warnings")
