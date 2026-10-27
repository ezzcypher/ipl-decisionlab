"""Tests for the v2 upgrade: auction prices, supported theming, model leaderboard, experiments, themed tables.
Run: python3 tests/test_upgrade.py   (or python3 -m pytest -q tests)"""
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from test_app import app, pm  # noqa: E402

from core import auction as A  # noqa: E402

DATA = ROOT / "data"
FIX = ROOT / "tests" / "fixtures" / "auction_synthetic_demo.csv"
PLAYERS = pd.read_parquet(DATA / "players.parquet")
HDR = "player,registry_id,season,franchise,base_price,sold_price,auction_status,currency,source\n"


def parse(text):
    rows, issues, fatal = A.parse(text.encode())
    if fatal:
        return rows, issues, fatal
    rows, more = A.finalize(rows, PLAYERS)
    return rows, pd.concat([issues, more], ignore_index=True), fatal


# ---------------------------------------------------------------- auction
def test_template_and_schema():
    t = pd.read_csv(io.BytesIO(A.template_csv()), keep_default_na=False)
    assert list(t.columns) == list(A.COLUMNS) and t.player.str.startswith("EXAMPLE").all() and t.source.str.startswith("EXAMPLE").all()
    rows, issues, fatal = parse(A.template_csv().decode())
    assert not fatal and rows.example.all() and rows.matched_player.isna().all()  # examples never match a real player
    assert set(A.schema_table().column) == set(A.COLUMNS)


def test_rejects_bad_files():
    for text, expect in ((b"a,b\n1,2\n", "missing required columns"), (HDR.encode(), "no data rows"), (b"\x00\x01", "")):
        rows, issues, fatal = A.parse(text)
        assert fatal and expect in " ".join(issues.issue), (text, issues.issue.tolist())


def test_row_level_validation():
    text = HDR + "\n".join([
        "V Kohli,,2025,X,200,abc,sold,INR_lakh,src",          # 1 non-numeric
        "V Kohli,,2024,X,200,-5,sold,INR_lakh,src",           # 2 negative
        "V Kohli,,20x5,X,200,300,sold,INR_lakh,src",          # 3 bad season
        "V Kohli,,2023,X,200,,sold,INR_lakh,src",             # 4 sold without price
        "V Kohli,,2022,X,200,300,maybe,INR_lakh,src",         # 5 bad status
        "V Kohli,,2021,X,200,300,sold,,src",                  # 6 missing currency
        "V Kohli,,2020,X,200,300,sold,INR_lakh,",             # 7 missing source
        ",,2019,X,200,300,sold,INR_lakh,src",                 # 8 no identity
        "V Kohli,,2018,X,400,300,sold,INR_lakh,src",          # 9 sold < base (warning only)
        "V Kohli,,2017,X,200,0,sold,INR_lakh,src",            # 10 zero price (warning)
        "V Kohli,,2016,X,200,500,unsold,INR_lakh,src",        # 11 unsold with price (warning, price dropped)
    ])
    rows, issues, _ = parse(text)
    err = set(issues[issues.severity == "error"].row.dropna().astype(int))
    warn = set(issues[issues.severity == "warning"].row.dropna().astype(int))
    assert err == {1, 2, 3, 4, 5, 6, 7, 8}, err
    assert {9, 10, 11} <= warn and not ({9, 10, 11} & err)
    assert rows.set_index("row").loc[11, "sold_price"] != rows.set_index("row").loc[11, "sold_price"]  # NaN


def test_identity_matching_is_exact_and_id_first():
    kohli_id = PLAYERS.set_index("player").loc["V Kohli", "registry_id"]
    text = HDR + "\n".join([
        f",{kohli_id},2025,X,200,300,sold,INR_lakh,src",            # 1 id only
        "V Kohli,,2024,X,200,300,sold,INR_lakh,src",                # 2 exact name
        "Virat Kohli,,2023,X,200,300,sold,INR_lakh,src",            # 3 similar name → unmatched (no fuzzy)
        "v kohli,,2022,X,200,300,sold,INR_lakh,src",                # 4 case differs → unmatched
        "Navdeep Saini,,2023,X,100,200,sold,INR_lakh,src",          # 5 known alias → canonical NA Saini
        f"MS Dhoni,{kohli_id},2021,X,200,300,sold,INR_lakh,src",    # 6 id wins, conflict reported
        ",zzzzzzzz,2020,X,200,300,sold,INR_lakh,src",               # 7 unknown id
    ])
    rows, issues, _ = parse(text)
    r = rows.set_index("row")
    assert r.loc[1, "matched_player"] == "V Kohli" and r.loc[1, "matched_by"] == "registry id"
    assert r.loc[2, "matched_by"] == "exact name"
    assert pd.isna(r.loc[3, "matched_player"]) and pd.isna(r.loc[4, "matched_player"])
    assert r.loc[5, "matched_player"] == "NA Saini"
    assert r.loc[6, "matched_player"] == "V Kohli" and r.loc[6, "id_name_conflict"]
    assert r.loc[7, "matched_by"] == "unmatched (id not found)"
    assert 6 in set(issues[issues.issue.str.contains("different players")].row)


def test_duplicates_excluded():
    text = HDR + "V Kohli,,2025,X,200,300,sold,INR_lakh,a\nV Kohli,,2025,Y,200,350,sold,INR_lakh,b\nV Kohli,,2025,X,1,2,sold,USD_m,c\n"
    rows, issues, _ = parse(text)
    assert rows.valid.tolist() == [False, False, True]  # same currency duplicate excluded; different currency kept
    assert (issues.issue.str.contains("duplicate")).sum() == 2


def test_value_metrics_definitions_and_zero_denominators():
    d = pm()
    rows, _, _ = parse(HDR + "V Kohli,,2024,X,200,1500,sold,INR_lakh,src\nV Kohli,,2017,X,200,0,sold,INR_lakh,src\n"
                             "B Kumar,,2008,X,10,20,sold,INR_lakh,src\n")
    v = A.value_table(rows, d).set_index("season")
    pts24 = d[(d.player == "V Kohli") & (d.season_year == 2024)].pts.sum()
    assert np.isclose(v.loc[2024, "season_pts"], pts24) and np.isclose(v.loc[2024, "price_per_point"], 1500 / pts24)
    assert np.isclose(v.loc[2024, "points_per_price_unit"], pts24 / 1500)
    prior = d[(d.player == "V Kohli") & (d.season_year < 2024)].pts
    assert int(v.loc[2024, "prior_matches"]) == len(prior) and np.isclose(v.loc[2024, "prior_avg"], prior.mean())
    assert np.isnan(v.loc[2017, "price_per_point"]) and v.loc[2017, "value_note"] == "no positive sold price"
    assert np.isnan(v.loc[2008, "price_per_point"]) and v.loc[2008, "value_note"] == "did not play that season"


def test_shortlist_score_formula():
    v = pd.DataFrame({"prior_avg": [10., 20, 30], "prior_cv": [.5, .5, .5], "sold_price": [100., 100, 100], "role": ["Batter", "Bowler", "Batter"]})
    s = A.shortlist_score(v, w_perf=1, w_cons=0, w_role=0, w_price=0)
    assert s.score.is_monotonic_increasing
    s2 = A.shortlist_score(v.assign(prior_avg=20.0), w_perf=0, w_cons=0, w_role=1, w_price=0, preferred_roles=["Bowler"])
    assert s2.score.idxmax() == 1
    s3 = A.shortlist_score(v.assign(prior_avg=20.0, sold_price=[50., 100, 150]), w_perf=0, w_cons=0, w_role=0, w_price=1)
    assert s3.score.is_monotonic_decreasing  # cheaper scores higher


def test_auction_page_with_and_without_upload():
    at = app(page="09_selection.py")
    assert not at.exception and any("unavailable until you upload" in i.value for i in at.info)
    at = app(page="09_selection.py", state={"auction_csv_bytes": FIX.read_bytes()})
    assert not at.exception and not at.error
    assert any("not real auction prices" in w.value for w in at.warning)
    labels = [d.label for d in at.get("download_button")]
    assert any("filtered auction table" in l for l in labels) and any("template" in l.lower() for l in labels)
    at = app(page="09_selection.py", state={"auction_csv_bytes": b"nonsense,cols\n1,2\n"})
    assert not at.exception and any("rejected" in e.value for e in at.error)
    at = app(page="09_selection.py", state={"auction_csv_bytes": FIX.read_bytes()})
    reset = [b for b in at.button if b.label == "Reset filters"]
    assert reset, "reset button missing"
    reset[0].click().run()
    assert "auction_csv_bytes" in at.session_state, "Reset filters must not discard the uploaded price file"


# ---------------------------------------------------------------- theme
def test_no_private_streamlit_apis():
    pat = re.compile(r"st\._config|streamlit\.runtime|AppSession|_create_new_session_message|streamlit\.config\b")
    for f in [ROOT / "app.py", *ROOT.glob("core/*.py"), *ROOT.glob("components/*.py"), *ROOT.glob("views/*.py")]:
        assert not pat.search(f.read_text()), f"private Streamlit API used in {f.name}"
    assert not (ROOT / "core" / "theme_switch.py").exists()


def test_theme_css_covers_widgets_and_charts_follow_theme():
    from core.theme import css, tokens
    for m in ("dark", "light"):
        c = css(m)
        for hook in ("stSidebar", "stSelectbox", "stMultiSelect", "stNumberInputContainer", "stDateInputCalendar", "role=\"listbox\"",
                     "stTooltipContent", "stAlertContainer", "stFileUploaderDropzone", "stPlotlyChart", ".katex", "dl-table"):
            assert hook in c, (m, hook)
        assert tokens(m)["surface"] in c
    for m in ("dark", "light"):
        at = app(m, "12_leaderboard.py")
        specs = [json.loads(p.proto.spec) for p in at.get("plotly_chart")]
        assert specs, "no charts rendered"
        for sp in specs:
            lay = sp["layout"]
            assert lay["paper_bgcolor"] == tokens(m)["surface"] and lay["plot_bgcolor"] == tokens(m)["surface"], m
            assert lay["font"]["color"] == tokens(m)["text2"] and lay["xaxis"]["gridcolor"] == tokens(m)["grid"]


def test_theme_persists_across_navigation_and_filters():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=180)
    at.run()
    at.toggle(key="theme_toggle").set_value(False).run()
    assert at.session_state["theme"] == "light"
    for page in ("views/05_player_explorer.py", "views/12_leaderboard.py", "views/01_overview.py"):
        at.switch_page(page).run()
        assert at.session_state["theme"] == "light" and "#f4f5f9" in " ".join(m.value for m in at.markdown if "<style>" in m.value)
    at.session_state["f_seasons"] = (2015, 2016)
    at.run()
    assert at.session_state["theme"] == "light"


def test_team_filters_do_not_leak_between_pages():
    keys = {"views/03_eda.py": "f_eda_teams", "views/06_roles.py": "f_teams", "views/09_selection.py": "f_sel_teams",
            "views/10_teams.py": "f_team_compare"}
    for f, k in keys.items():
        assert f'"{k}"' in (ROOT / f).read_text(), (f, k)
    at = app(page="10_teams.py", state={"f_team_compare": ["Mumbai Indians"]})
    at.switch_page("views/09_selection.py").run()
    assert not at.exception
    assert not at.session_state["f_sel_teams"] if "f_sel_teams" in at.session_state else True


def test_upload_size_is_limited():
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "maxUploadSize = 5" in cfg


def test_published_phase2_csv_matches_recorded_checksum():
    f = ROOT / "data" / "IPL_DecisionLab_Phase2_Cleaned.csv"
    recorded = {ln.split()[1]: ln.split()[0] for ln in (ROOT / "pipeline/reports/source_checksums.sha256").read_text().splitlines() if ln.strip()}
    h = hashlib.sha256()
    with open(f, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == recorded["inputs/IPL_DecisionLab_Phase2_Cleaned.csv"]
    head = pd.read_csv(f, nrows=0).columns
    assert len(head) == 28 and list(head[:6]) == ["match_id", "season", "start_date", "venue", "innings", "ball"]


def test_public_app_hides_error_details():
    import tomllib
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert cfg["client"]["showErrorDetails"] is False


def test_csv_export_neutralises_formulas():
    from components.ui import csv_safe
    df = pd.DataFrame({"player": ["=HYPERLINK(\"x\")", "+1", "-2+3", "@SUM(A1)", "\tcmd", "V Kohli", None],
                       "pts": [-4.0, 1, 2, 3, 4, 5, 6]})
    out = csv_safe(df)
    assert out.player.tolist()[:5] == ["'=HYPERLINK(\"x\")", "'+1", "'-2+3", "'@SUM(A1)", "'\tcmd"]
    assert out.player.iloc[5] == "V Kohli" and pd.isna(out.player.iloc[6])
    assert out.pts.tolist() == df.pts.tolist()           # numbers, incl. negatives, unchanged
    assert df.player.iloc[0].startswith("=")             # input not mutated
    assert csv_safe(pd.DataFrame(columns=["=evil"])).columns[0] == "'=evil"


# ---------------------------------------------------------------- tables
def test_table_component_formatting():
    from components.ui import _fmt
    assert _fmt(1234567, "runs") == "1,234,567" and _fmt(2024, "season") == "2024" and _fmt(335982, "match_id") == "335982"
    assert _fmt(np.nan, "x") == "–" and _fmt(True, "met") == "✓" and _fmt(-0.0021, "r2") == "-0.002" and _fmt(24.0579, "mae") == "24.06"
    assert _fmt(pd.Timestamp("2024-03-22"), "start_date") == "2024-03-22"


# ---------------------------------------------------------------- leaderboard & experiments
def test_leaderboard_reconciles_with_saved_files():
    mets = json.loads((DATA / "phase6_metrics_rebuilt.json").read_text())
    assert len(mets["prediction_columns"]) == 6
    at = app(page="12_leaderboard.py")
    assert not at.exception and not at.error, [e.value for e in at.error]
    txt = " ".join(m.value for m in at.markdown)
    assert "lower is better" in txt and "negative" in txt and "retrospective predictions" in txt
    for split, k in (("validation", "val"), ("test", "test")):
        d = pd.read_csv(DATA / f"phase6_predictions_{k}_rebuilt.csv")
        for name, col in mets["prediction_columns"].items():
            e = d.pts - d[col]
            assert np.isclose(e.abs().mean(), mets["metrics"][k][name]["mae"]) and np.isclose(np.sqrt((e ** 2).mean()), mets["metrics"][k][name]["rmse"])
            assert np.isclose(1 - (e ** 2).sum() / ((d.pts - d.pts.mean()) ** 2).sum(), mets["metrics"][k][name]["r2"])
    assert "champion" not in txt.lower().replace("no model is called a champion", "")


def test_experiments_protocol_and_original_artifacts_untouched():
    ex = json.loads((DATA / "model_experiments.json").read_text())
    v = pd.DataFrame(ex["validation_leaderboard"])
    assert ex["selected"] == v.sort_values(["val_mae", "n_features"]).iloc[0]["candidate"]
    assert all("test" not in c for c in v.columns), "validation leaderboard must not contain test metrics"
    assert set(ex["test_after_selection"]) == {"selected", "median_baseline", "selected_minus_median_mae"}
    for name, h in ex["original_artifacts_sha256"].items():
        assert hashlib.sha256((ROOT / "models" / name).read_bytes()).hexdigest() == h, name
    cfg = json.loads((ROOT / "models" / "preprocess_config_rebuilt.json").read_text())
    for name, h in cfg["artifacts"].items():
        if (ROOT / "models" / name).exists():
            assert hashlib.sha256((ROOT / "models" / name).read_bytes()).hexdigest() == h, name
    tp = pd.read_csv(DATA / "model_experiments_test_predictions.csv")
    assert np.isclose((tp.pts - tp.pred_selected).abs().mean(), ex["test_after_selection"]["selected"]["mae"])


def test_experiment_features_use_only_earlier_matches():
    sys.path.insert(0, str(ROOT / "scripts"))
    import model_experiments as mx
    d = pm()
    base = mx.add_history_features(d)
    rng = np.random.default_rng(1)
    for i in rng.choice(len(d), 8, replace=False):
        mod = d.copy(); mod.loc[i, "pts"] += 1000; mod.loc[i, "total_batting_points"] += 1000
        g = mx.add_history_features(mod)
        key = (d.loc[i, "match_id"], d.loc[i, "player"])
        a = base[(base.match_id == key[0]) & (base.player == key[1])][mx.EXTRA].to_numpy(float)
        b = g[(g.match_id == key[0]) & (g.player == key[1])][mx.EXTRA].to_numpy(float)
        assert np.allclose(a, b, equal_nan=True), "a history feature depends on the current match"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f) and f.__module__ == "__main__"]
    failed = 0
    for n, f in tests:
        t = time.time()
        try:
            f(); print(f"PASS  {n}  ({time.time() - t:.1f}s)")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"FAIL  {n}: {type(e).__name__}: {str(e)[:400]}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
