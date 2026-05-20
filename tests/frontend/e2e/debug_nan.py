"""
Debug: Find NaN text on /privat page
"""

from playwright.sync_api import sync_playwright
import time

BASE_URL = "http://localhost"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})

    page.goto(f"{BASE_URL}/privat")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # Screenshot
    page.screenshot(path="/tmp/privat_debug.png", full_page=True)

    # Find NaN
    content = page.content()
    if "NaN" in content:
        print("NaN found in page content!")
        # Find context around NaN
        idx = content.find("NaN")
        print(f"Context: ...{content[max(0,idx-50):idx+50]}...")

        # Check for visible NaN elements
        nan_locators = page.locator("text=NaN").all()
        print(f"Found {len(nan_locators)} NaN elements")
        for i, loc in enumerate(nan_locators):
            try:
                text = loc.inner_text()
                parent = loc.locator("..").first.inner_html()[:200]
                print(f"  {i+1}. Text: '{text}', Parent HTML: {parent}...")
            except:
                print(f"  {i+1}. Could not get details")

    browser.close()
