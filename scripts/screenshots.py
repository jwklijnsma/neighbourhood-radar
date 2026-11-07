"""Take README screenshots of a running instance in demo mode.

    OL_DEMO=1 uvicorn app.main:app --port 8080 &
    python scripts/screenshots.py http://localhost:8080 docs/screenshots

Needs: pip install playwright && playwright install --with-deps chromium
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots")

LAYERS_ON = [
    "p2000", "traffic", "bridges", "roadworks", "drips", "busalerts", "transit",
    "trains", "charging", "safety", "weather", "water", "aircraft",
]
PREFS = {
    "lat": 52.9594,
    "lon": 5.9189,
    "radius": 12,
    "enabled": {name: True for name in LAYERS_ON},
}


def open_app(browser, **ctx):
    context = browser.new_context(**ctx)
    # Same key the app uses for per-browser preferences.
    context.add_init_script(
        f"try {{ localStorage.setItem('neighbourhood-radar:v1', {json.dumps(json.dumps(PREFS))}); }} catch (e) {{}}"
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector(".layers li")
    # Slow sources (air, bus alerts) fill in the background after the first request:
    # give them a moment, then reload so every layer is on the first paint.
    page.wait_for_timeout(2500)
    page.reload()
    page.wait_for_selector(".nearby li button")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)  # let tiles fade in
    return context, page, errors


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    all_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        ctx, page, errs = open_app(browser, viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.screenshot(path=OUT / "desktop.png")
        page.locator(".nearby li button", has_text="Brug open").first.click()
        page.wait_for_timeout(1200)
        page.screenshot(path=OUT / "popup.png")
        all_errors += errs
        ctx.close()

        ctx, page, errs = open_app(browser, viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                   color_scheme="dark")
        page.screenshot(path=OUT / "dark.png")
        all_errors += errs
        ctx.close()

        ctx, page, errs = open_app(browser, viewport={"width": 390, "height": 844}, device_scale_factor=3,
                                   is_mobile=True, has_touch=True)
        page.screenshot(path=OUT / "mobile.png")
        all_errors += errs
        ctx.close()

        browser.close()

    for f in sorted(OUT.glob("*.png")):
        print(f"{f}  {f.stat().st_size // 1024} KB")
    if all_errors:
        print("page errors:", *all_errors, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
