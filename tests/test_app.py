"""IPL DecisionLab Phase 7 tests.  Run:  python3 -m pytest -q tests   (or  python3 tests/test_app.py)"""
import ast
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from streamlit.testing.v1 import AppTest  # noqa: E402

from core import scoring  # noqa: E402

DATA = ROOT / "data"
PAGES = sorted(p.name for p in (ROOT / "views").glob("*.py"))


def app(theme="dark", page=None, state=None, env=None):
    if env:
        os.environ.update(env)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.session_state["theme"] = theme
    for k, v in (state or {}).items():
        at.session_state[k] = v
    at.run()
    if page:
        at.switch_page(f"views/{page}")
        at.run()
    return at


def text_of(at):
    return " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)


def pm():
    return pd.read_parquet(DATA / "player_match.parquet")


# 1-3 startup, every page, both themes ------------------------------------------------------------
def test_every_page_renders_in_both_themes():
    for theme in ("dark", "light"):
        for page in PAGES:
            at = app(theme, page)
            assert not at.exception, (theme, page, [e.value for e in at.exception][:1])
            assert not at.error, (theme, page, [e.value for e in at.error][:1])
            css = " ".join(m.value for m in at.markdown if "<style>" in m.value)
            from core.theme import tokens
            assert tokens(theme)["bg"] in css, f"{page}: {theme} tokens not applied"


def test_theme_contrast():
    from core.theme import tokens

    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    def ratio(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)

    for m in ("dark", "light"):
        t = tokens(m)
        for fg in ("text", "text2", "muted"):
            for bg in ("bg", "surface", "surface2"):
                assert ratio(t[fg], t[bg]) >= 4.5, (m, fg, bg, round(ratio(t[fg], t[bg]), 2))


# 4 filters and reset ----------------------------------------------------------------------------
def test_filters_change_kpis_and_reset_clears_them():
    at = app(page="01_overview.py")
    full = text_of(at)
    assert "295,557" in full
    at = app(page="01_overview.py", state={"f_seasons": (2024, 2024)})
    one = text_of(at)
    sub = pd.read_parquet(DATA / "season_summary.parquet").query("season_year == 2024")
    assert f"{int(sub.deliveries.sum()):,}" in one and "295,557" not in one
    reset = [b for b in at.button if b.label == "Reset filters"]
    assert reset, "reset button missing"
    reset[0].click().run()
    assert "f_seasons" not in at.session_state or tuple(at.session_state["f_seasons"]) == (2008, 2026)


def test_filter_helpers():
    from components import ui
    d = pm()
    f = ui.apply(d, seasons=(2010, 2011), teams=["Mumbai Indians"])
    assert len(f) and f.season_year.between(2010, 2011).all() and (f.team == "Mumbai Indians").all()
    assert ui.isin(d.team, []).all() and ui.isin(d.team, ["X"]).sum() == 0


# 5-6 KPI reconciliation and Phase 1 vs Phase 2 ----------------------------------------------------
def test_kpis_reconcile_with_source_summaries():
    man = json.loads((DATA / "manifest.json").read_text())
    se = pd.read_parquet(DATA / "season_summary.parquet")
    d = pm()
    assert int(se.deliveries.sum()) == man["cleaned_summary"]["rows"] == 295557
    assert int(se.matches.sum()) == man["cleaned_summary"]["matches"] == 1243
    assert int(se.runs.sum()) == man["cleaned_summary"]["total_runs"]
    assert int(se.dismissals.sum()) == man["cleaned_summary"]["dismissals"]
    assert d[d.batted].player.nunique() == man["cleaned_summary"]["unique_batters"]  # both use v1.1 identities
    assert len(d) == 26759 and d.match_id.nunique() == 1243
    inn = pd.read_parquet(DATA / "innings.parquet")
    assert int(inn.runs.sum()) == int(se.runs.sum())  # innings and season views agree
    text = text_of(app(page="01_overview.py"))
    for v in ("295,557", "1,243 · 19", f"{int(se.runs.sum()):,}", f"{int(se.dismissals.sum()):,}", "26,759", "302.0 pts"):
        assert v in text, v


def test_comparison_page_figures():
    c = pd.read_parquet(DATA / "audit_comparison.parquet").set_index("metric")
    man = json.loads((DATA / "manifest.json").read_text())
    assert c.loc["Rows", "phase1_raw"] - c.loc["Rows", "phase2_cleaned"] == c.loc["Super-over rows", "phase1_raw"] == 175
    assert c.loc["Rows", "phase1_raw"] == man["raw_summary"]["rows"]
    assert c.loc["Matches", "phase1_raw"] == c.loc["Matches", "phase2_cleaned"]
    assert c.loc["Repeated (match, innings, ball) keys", ["phase1_raw", "phase2_cleaned"]].tolist() == [42, 42]
    assert c.loc["Team names", ["phase1_raw", "phase2_cleaned"]].tolist() == [19, 15]
    checks = pd.read_parquet(DATA / "audit_checks.parquet")
    assert not checks[checks.category == "Reported, not reproduced"].status.eq("PASS").any(), "claims not reproduced must not PASS"
    assert set(checks.status) <= {"PASS", "WARN", "FAIL", "INFO", "NOT REPRODUCED"}


# 7 identity and images ---------------------------------------------------------------------------
def test_player_identity_and_avatar_fallback(tmp_path=None):
    from components import ui
    pl = pd.read_parquet(DATA / "players.parquet")
    assert (pl.registry_id.str.len() > 0).all()
    assert not {"Arshad Khan (2)", "Navdeep Saini", "Salil Arora"} & set(pl.player)
    assert "Harmeet Singh (2)" in set(pl.player)
    assert pl.player.is_unique
    imgs = pd.read_csv(DATA / "player_images.csv")
    assert {"player", "registry_id", "image_file", "source_url", "license", "attribution", "verified_by"} <= set(imgs.columns)
    assert len(imgs) == 0, "no verified photos are shipped; any added row must carry source/licence/verification"
    html = ui.avatar_html("V Kohli")
    assert ">VK<" in html and "<img" not in html
    assert ui.initials("Harmeet Singh (2)") == "HS" and ui.initials("AB de Villiers") == "AV"


# 8 scoring ---------------------------------------------------------------------------------------
def test_scoring_reproduces_every_stored_score():
    d = pm()
    r = d.apply(lambda x: scoring.score(x.runs, x.fours, x.sixes, x.batted, x.dismissed, x.wickets, x.dots), axis=1, result_type="expand")
    assert np.allclose(r["total"], d.pts) and np.allclose(r["batting"], d.total_batting_points)
    assert np.allclose(r["bowling"], d.wicket_points) and np.allclose(r["dot"], d.dot_ball_points)
    mc = d[(d.match_id == 335982) & (d.player == "BB McCullum")].iloc[0]
    assert (mc.runs, mc.fours, mc.sixes, mc.pts) == (158, 10, 13, 222)
    assert scoring.score(100, 0, 0, True, False)["batting"] == 128  # milestones stack
    assert scoring.score(0, 0, 0, True, True)["batting"] == -2 and scoring.score(0, 0, 0, False, True)["batting"] == 0


# 9 classification --------------------------------------------------------------------------------
def test_role_rule_is_participation_based():
    from core.data import classify
    s = pd.DataFrame({"balls_faced_pm": [20, 1, 12, 2, 20], "balls_bowled_pm": [0, 22, 15, 1, 0], "matches": [50, 50, 50, 50, 3]})
    assert classify(s).tolist() == ["Batter", "Bowler", "All-rounder", "Limited role", "Insufficient sample"]
    s2 = s.assign(avg_pts=[1, 1000, 5, 999, 7])  # fantasy points never change the role
    assert classify(s2).tolist() == classify(s).tolist()


# 10-12 models, retrospective predictions, split separation ---------------------------------------
def test_model_artifacts_reproduce_saved_predictions():
    import joblib
    from xgboost import XGBRegressor
    cfg = json.loads((ROOT / "models" / "preprocess_config_rebuilt.json").read_text())
    x = XGBRegressor(); x.load_model(ROOT / "models" / "xgboost_rebuilt.json")
    r = joblib.load(ROOT / "models" / "ridge_rebuilt.joblib")
    t = pd.read_csv(DATA / "phase6_predictions_test_rebuilt.csv").merge(pm()[["match_id", "player"] + cfg["predictors"]], on=["match_id", "player"])
    X = t[cfg["predictors"]].fillna(cfg["imputation"]["medians"])
    assert np.allclose(x.predict(X), t.pred_xgboost, atol=1e-4) and np.allclose(r.predict(X), t.pred_ridge, atol=1e-6)


def test_validation_and_test_are_separate_and_metrics_reconcile():
    cfg = json.loads((ROOT / "models" / "preprocess_config_rebuilt.json").read_text())
    mets = json.loads((DATA / "phase6_metrics_rebuilt.json").read_text())
    v = pd.read_csv(DATA / "phase6_predictions_val_rebuilt.csv", parse_dates=["start_date"])
    t = pd.read_csv(DATA / "phase6_predictions_test_rebuilt.csv", parse_dates=["start_date"])
    assert v.start_date.max() < t.start_date.min() and not set(v.match_id) & set(t.match_id)
    assert v.start_date.min() >= pd.Timestamp(cfg["splits"]["val"]["from"]) and t.start_date.max() <= pd.Timestamp(cfg["splits"]["test"]["to"])
    for df, k in ((v, "val"), (t, "test")):
        for name, col in mets["prediction_columns"].items():
            assert np.isclose(np.abs(df.pts - df[col]).mean(), mets["metrics"][k][name]["mae"])
    val = mets["metrics"]["val"]
    assert mets["selection"]["best_by_validation_mae"] == min(val, key=lambda k: val[k]["mae"]) == "Median baseline (train median)"
    assert mets["selection"]["best_by_validation_rmse"] == min(val, key=lambda k: val[k]["rmse"]) == "Ridge regression"
    assert max(m["r2"] for m in mets["metrics"]["test"].values()) < 0.02  # backs the "under 2% of variance" wording
    at = app(page="08_predictions.py")
    txt = text_of(at)
    assert "Retrospective" in txt and "rebuilt" in txt and "champion" in txt.lower()


# 13 CSV exports ----------------------------------------------------------------------------------
def test_downloads_present_and_reflect_filters():
    at = app(page="05_player_explorer.py", state={"f_seasons": (2016, 2016)})
    assert len(at.get("download_button")) >= 1
    from components import ui
    f = ui.apply(pm(), seasons=(2016, 2016))
    p = f[f.player == "V Kohli"]
    csv = pd.read_csv(io.StringIO(p.to_csv(index=False)))
    assert len(csv) == len(p) and csv.season_year.eq(2016).all()
    for page in PAGES:
        src = (ROOT / "views" / page).read_text()
        assert "download" in src, f"{page} has no CSV export"


# 14 missing files and empty data -----------------------------------------------------------------
def test_missing_data_shows_message_not_traceback(tmp=Path("/tmp/claude-0/ipl_dl_empty")):
    tmp.mkdir(parents=True, exist_ok=True)
    code = (f"import os, sys; os.environ['IPL_DL_DATA']={str(tmp)!r}; sys.path.insert(0, {str(ROOT)!r});"
            f"from streamlit.testing.v1 import AppTest;"
            f"at=AppTest.from_file({str(ROOT / 'app.py')!r}, default_timeout=120); at.run();"
            f"bad=[]\n"
            f"for p in {PAGES!r}:\n"
            f"    at.switch_page('views/'+p); at.run()\n"
            f"    bad += [p] if at.exception or not at.error else []\n"
            f"print('BAD', bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600).stdout
    assert "BAD []" in out, out[-500:]


def test_empty_filter_state_is_handled():
    at = app(page="09_selection.py", state={"f_min_matches": 200, "f_seasons": (2008, 2008)})
    assert not at.exception and any("No players meet" in i.value for i in at.info)
    at = app(page="05_player_explorer.py", state={"f_seasons": (2008, 2008), "f_player": "Shubman Gill"})
    assert not at.exception and any("no matches" in i.value for i in at.info)


# 15 large-table performance ----------------------------------------------------------------------
def test_large_table_performance():
    from core.data import player_stats
    d = pm()
    t = time.time(); s = player_stats(d); dt = time.time() - t
    assert len(s) == d.player.nunique() and dt < 3, dt
    t = time.time(); app(page="05_player_explorer.py"); dt = time.time() - t
    assert dt < 30, dt


# 17 README and dependencies ----------------------------------------------------------------------
def test_requirements_cover_imports_and_readme_runs():
    req = {l.split("==")[0].strip().lower() for l in (ROOT / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")}
    alias = {"sklearn": "scikit-learn", "yaml": "pyyaml"}
    std = set(sys.stdlib_module_names) | {"core", "components", "scripts", "rebuild"}
    used = set()
    for f in list((ROOT / "views").glob("*.py")) + list((ROOT / "core").glob("*.py")) + list((ROOT / "components").glob("*.py")) + [ROOT / "app.py"]:
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Import):
                used |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                used.add(n.module.split(".")[0])
    missing = {alias.get(u, u) for u in used - std} - req
    assert not missing, missing
    readme = (ROOT / "README.md").read_text()
    assert "streamlit run app.py" in readme and "pip install -r requirements.txt" in readme


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for n, f in tests:
        t = time.time()
        try:
            f(); print(f"PASS  {n}  ({time.time() - t:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"FAIL  {n}: {type(e).__name__}: {str(e)[:300]}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
