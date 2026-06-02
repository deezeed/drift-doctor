from pathlib import Path
from playwright.sync_api import sync_playwright

html_path = Path(__file__).parent / "report_full.html"
out_path = Path(__file__).parent / "report_screenshot.png"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 920, "height": 520})
    page.goto(html_path.as_uri())
    page.wait_for_load_state("networkidle")
    page.screenshot(path=str(out_path), full_page=True)
    browser.close()

print(f"Screenshot saved: {out_path}")
