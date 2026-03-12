"""Capture a screenshot of a page using Playwright.

Usage:
    uv run python scripts/screenshot.py [URL] [OUTPUT_PATH]

Defaults:
    URL:         http://localhost:8000/ui/
    OUTPUT_PATH: screenshots/page.png
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def screenshot(url: str = "http://localhost:8000/ui/", output: str = "screenshots/page.png") -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(url, wait_until="networkidle")
        page.screenshot(path=str(output_path), full_page=True)
        browser.close()

    print(f"Screenshot saved: {output_path}")
    return output_path


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/ui/"
    output = sys.argv[2] if len(sys.argv) > 2 else "screenshots/page.png"
    screenshot(url, output)
