"""Browser checks (needs Playwright + Chromium and a running app):
    streamlit run app.py &   python3 tests/browser_check.py [http://localhost:8501]

For every page, at desktop and phone width, in both themes:
  * no exception box and no JS error, no horizontal overflow;
  * theme consistency: every visible element with an opaque background must match the selected theme
    (no dark boxes in light mode, no white boxes in dark mode) — popovers/dropdowns are opened and checked too;
  * the theme survives navigation and a filter change.
"""
import sys
import time
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8501"
FIXTURE = str(__import__("pathlib").Path(__file__).resolve().parent / "fixtures" / "auction_synthetic_demo.csv")
NAV = ["Executive overview", "Part 1 · Data quality audit", "Part 2 · EDA & cleaning", "Part 1 vs Part 2", "Player explorer",
       "Batting · bowling · all-round", "Fantasy points calculator", "Predictive analytics", "Model leaderboard",
       "Selection & auction support", "Teams & seasons", "Methodology & final report"]

MISMATCH_JS = """(light) => {
  const lum = c => { const m = c.match(/[\\d.]+/g); if (!m) return null; const [r,g,b,a] = m.map(Number);
                     if (a !== undefined && a < 0.5) return null; return (0.2126*r + 0.7152*g + 0.0722*b) / 255; };
  const skip = e => e.closest('.dl-hero, svg, canvas, .js-plotly-plot .bg, [role=switch], [data-testid=stSliderThumb], .dl-logo, .dl-badge, [data-testid=stLogo], img, .katex, [data-baseweb=slider], [data-testid=stSlider]');
  const bad = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect(); if (r.width < 24 || r.height < 14) continue;
    const s = getComputedStyle(e); if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') continue;
    if (skip(e)) continue;
    const L = lum(s.backgroundColor); if (L === null) continue;
    if (light ? L < 0.35 : L > 0.65) {
      if (e.tagName === 'BUTTON' && L > 0.25 && L < 0.75) continue;  // accent-coloured buttons are fine in both themes
      bad.push((e.getAttribute('data-testid') || e.getAttribute('role') || e.tagName) + ' ' + s.backgroundColor);
    }
  }
  return [...new Set(bad)].slice(0, 8);
}"""


def settle(pg, t=2.5):
    time.sleep(t)
    for _ in range(60):
        if pg.locator("[data-testid='stStatusWidget']").count() == 0:
            break
        time.sleep(0.5)
    time.sleep(1)


def main():
    fails, checked = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width in (1440, 390):
            for light in (False, True):
                pg = b.new_page(viewport={"width": width, "height": 1000})
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(BASE)
                pg.wait_for_selector("[data-testid='stApp']", timeout=60000)
                settle(pg, 4)

                def sidebar():
                    if pg.locator("[data-testid='stExpandSidebarButton']").count() and pg.locator("[data-testid='stExpandSidebarButton']").is_visible():
                        pg.locator("[data-testid='stExpandSidebarButton']").click(); time.sleep(1)
                if light:
                    sidebar()
                    pg.get_by_text("Dark mode").click()
                    settle(pg)
                for name in NAV:
                    sidebar()
                    pg.get_by_role("link", name=name).first.click()
                    settle(pg)
                    tag = f"{name} @{width}px {'light' if light else 'dark'}"
                    if pg.locator("[data-testid='stException']").count():
                        fails.append(f"{tag}: exception box")
                    over = pg.evaluate("(() => { const m = document.querySelector('[data-testid=stMain]') || document.body; return m.scrollWidth - m.clientWidth; })()")
                    if over > 2:
                        fails.append(f"{tag}: horizontal overflow {over}px")
                    bad = pg.evaluate(MISMATCH_JS, light)
                    # open the first dropdown on the page and check its popover too
                    cb = pg.get_by_role("combobox")
                    if width > 700 and cb.count():
                        try:
                            cb.first.click(timeout=3000); time.sleep(0.8)
                            bad += [f"(dropdown) {x}" for x in pg.evaluate(MISMATCH_JS, light)]
                            pg.keyboard.press("Escape"); time.sleep(0.3)
                        except Exception:  # noqa: BLE001 — a hidden combobox is not a failure
                            pass
                    if bad:
                        fails.append(f"{tag}: theme mismatch {bad[:4]}")
                    checked += 1
                    print(("ok " if not bad else "BAD"), tag)
                # popovers and widgets that only appear after interaction
                if width > 700:
                    probes = []
                    pg.get_by_role("link", name="Player explorer").first.click(); settle(pg)
                    pg.locator("[data-testid='stDateInputField']").first.click(); time.sleep(1.2)
                    probes += [f"(calendar) {x}" for x in pg.evaluate(MISMATCH_JS, light)]
                    pg.keyboard.press("Escape")
                    pg.locator("[data-testid='stTooltipIcon']").first.hover(); time.sleep(1)
                    probes += [f"(tooltip) {x}" for x in pg.evaluate(MISMATCH_JS, light)]
                    pg.get_by_role("link", name="Selection & auction support").first.click(); settle(pg)
                    pg.get_by_role("tab", name="Auction prices & value").click(); settle(pg)
                    pg.locator("input[type=file]").first.set_input_files(FIXTURE); settle(pg, 4)
                    probes += [f"(auction upload) {x}" for x in pg.evaluate(MISMATCH_JS, light)]
                    if pg.locator("[data-testid='stException']").count():
                        probes.append("auction upload raised an exception")
                    if probes:
                        fails.append(f"interactive probes {'light' if light else 'dark'}: {probes[:4]}")
                    print(("ok " if not probes else "BAD"), f"interactive probes @{width}px {'light' if light else 'dark'}")
                # theme persists after a filter change
                if width > 700:
                    pg.get_by_role("link", name="Executive overview").first.click(); settle(pg)
                    pg.get_by_role("button", name="Reset filters").first.click(); settle(pg)
                    bg = pg.evaluate("getComputedStyle(document.querySelector('[data-testid=stApp]')).backgroundColor")
                    v = sum(int(x) for x in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]) / 3
                    if (v > 200) != light:
                        fails.append(f"theme not preserved after filter change ({bg})")
                if errs:
                    fails.append(f"JS errors: {errs[:2]}")
                pg.close()
        b.close()
    print(f"\n{checked} page renders checked")
    print("FAILURES:" if fails else "all browser checks passed", *fails, sep="\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
