"""Optional browser checks (needs Playwright + Chromium and a running app):
    streamlit run app.py &   python3 tests/browser_check.py [http://localhost:8501]
Checks every page at desktop and phone width, in both themes: no exception box, no JS error,
no horizontal overflow, and that the theme toggle switches native widgets (sidebar background).
"""
import sys
import time
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
PATHS = ["", "data_audit", "eda", "comparison", "player_explorer", "roles", "scoring", "predictions", "selection", "teams", "methodology"]


def settle(pg):
    time.sleep(3)
    for _ in range(40):
        if pg.locator("[data-testid='stStatusWidget']").count() == 0:
            break
        time.sleep(0.5)
    time.sleep(1)


def main():
    fails = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width in (1440, 390):
            for light in (False, True):
                pg = b.new_page(viewport={"width": width, "height": 900})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE)
                pg.wait_for_selector("[data-testid='stApp']", timeout=60000)
                settle(pg)
                if light:
                    if width < 700:
                        pg.locator("[data-testid='stExpandSidebarButton']").first.click()
                        time.sleep(1)
                    pg.get_by_text("Dark mode").click()
                    settle(pg)
                    bg = pg.evaluate("getComputedStyle(document.querySelector('[data-testid=stSidebar]')).backgroundColor")
                    rgb = [int(v) for v in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]]
                    if sum(rgb) / 3 < 200:  # light sidebar expected
                        fails.append(f"theme toggle did not switch sidebar ({bg})")
                for path in PATHS:
                    pg.goto(f"{BASE}/{path}")
                    settle(pg)
                    exc = pg.locator("[data-testid='stException']").count()
                    over = pg.evaluate("(() => { const m = document.querySelector('[data-testid=stMain]') || document.body;"
                                       " return m.scrollWidth - m.clientWidth; })()")
                    tag = f"{path or 'overview'} @{width}px {'light' if light else 'dark'}"
                    if exc:
                        fails.append(f"{tag}: exception box")
                    if over > 2:
                        fails.append(f"{tag}: horizontal overflow {over}px")
                    print(f"{'ok ' if not exc and over <= 2 else 'BAD'} {tag}")
                if errs:
                    fails.append(f"JS errors: {errs[:2]}")
                pg.close()
        b.close()
    print("\nFAILURES:" if fails else "\nall browser checks passed", *fails, sep="\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
