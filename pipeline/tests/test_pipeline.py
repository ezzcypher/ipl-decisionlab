"""Recovery checks for steps 1-3 + audits. Run: python3 -I tests/test_pipeline.py
Each test runs independently; the runner prints PASS/FAIL per test and exits non-zero on any failure."""
import hashlib, json, os, sys, traceback
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import rebuild as rb

INP, OUT, REP = ROOT / "inputs", ROOT / "rebuilt", ROOT / "reports"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
_cache = {}
def csv(p):
    if p not in _cache:
        _cache[p] = pd.read_csv(p, low_memory=False)
    return _cache[p]


def _recorded():
    return dict(reversed(l.split("  ", 1)) for l in (REP / "source_checksums.sha256").read_text().splitlines())


def test_sources_unchanged():
    """Every recorded source that is present is unchanged; the raw Cricsheet snapshot must be present.
    (The recovered archive and the two large original CSVs are not in the repo; their hashes are still recorded.)"""
    recorded = _recorded()
    assert (ROOT / "inputs/ipl_male_csv2.zip").exists(), "raw Cricsheet snapshot missing"
    present = [rel for rel in recorded if (ROOT / rel).exists()]
    assert "inputs/ipl_male_csv2.zip" in present
    for rel in present:
        assert sha(ROOT / rel) == recorded[rel], f"{rel} changed"


def test_rebuilt_files_byte_identical():
    """Rebuilt Phase 2/4/3 equal the recovered originals: compared with the file when present, else with its recorded hash."""
    recorded = _recorded()
    for stem in ["IPL_DecisionLab_Phase2_Cleaned", "IPL_DecisionLab_Team_Standardized", "IPL_DecisionLab_Phase3_PlayerMatch_Points"]:
        orig = INP / f"{stem}.csv"
        expect = sha(orig) if orig.exists() else recorded[f"inputs/{stem}.csv"]
        assert sha(OUT / f"{stem}_rebuilt.csv") == expect, stem


def test_super_overs_removed_per_delivery():
    raw, p2 = rb.load_raw(), csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv")
    assert (p2["innings"] > 2).sum() == 0
    assert len(raw) - len(p2) == (raw["innings"] > 2).sum() == 175
    assert p2["match_id"].nunique() == raw["match_id"].nunique() == 1243


def test_repeated_keys_kept_and_explained():
    p2 = csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv")
    assert p2.duplicated(["match_id", "innings", "ball"]).sum() == 42  # kept, not deduplicated
    a = pd.read_csv(REP / "duplicate_delivery_keys_audit_rebuilt.csv", dtype={"ball_text": str})
    assert len(a) == 84 and a["status"].str.startswith("CONFIRMED").all()
    texts = a.groupby(["match_id", "innings", "ball"])["ball_text"].apply(frozenset)
    assert all(t == {f"{int(k[2])}.1", f"{int(k[2])}.10"} for k, t in texts.items()), "a key is not an N.1 / N.10 collision"
    assert (a.groupby(["match_id", "innings", "ball"])["actual_delivery"].nunique() == 2).all()


def test_phase3_one_row_per_player_match_and_components():
    p3 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_rebuilt.csv")
    assert not p3.duplicated(["match_id", "player"]).any()
    assert (p3["pts"] == p3["total_batting_points"] + p3["wicket_points"] + p3["dot_ball_points"]).all()
    assert (p3["wicket_points"] % 25 == 0).all() and (p3["dot_ball_points"] % 0.5 == 0).all()
    assert len(p3) == 26759


def test_scoring_hand_checked_example():
    # BB McCullum, 2008-04-18 (match 335982): 158 runs, 10 fours, 13 sixes, not out
    # 158 + 10*1 + 13*2 + 4 (30) + 8 (50) + 16 (100) = 222
    p3 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_rebuilt.csv")
    row = p3[(p3.match_id == 335982) & (p3.player == "BB McCullum")].iloc[0]
    assert row["total_batting_points"] == 222 and row["pts"] == 222
    p2 = csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv")
    b = p2[(p2.match_id == 335982) & (p2.striker == "BB McCullum")]["runs_off_bat"]
    assert (b.sum(), (b == 4).sum(), (b == 6).sum()) == (158, 10, 13)


def test_reconstruction_fully_explained():
    q = json.loads((REP / "data_quality_audit_rebuilt.json").read_text())["scoring_discrepancies"]
    assert q["replay_of_reconstruction_rules_reproduces_pm_reconstructed_exactly"] is True
    assert q["rows_differing_without_any_attributed_cause"] == 0


def test_season_map():
    m = json.loads((OUT / "season_map_rebuilt.json").read_text())
    assert m["2007/08"] == 2008 and m["2009"] == 2009 and m["2009/10"] == 2010 and m["2020/21"] == 2020
    p2 = csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv")
    yr = p2.groupby(p2["season"].astype(str))["date_year"].agg(["min", "max"])
    assert all(yr.loc[s, "min"] == yr.loc[s, "max"] == y for s, y in m.items())
    assert len(set(m.values())) == len(m) == 19


def test_identity_decisions():
    p3 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_rebuilt.csv")
    assert "Arshad Khan (2)" not in set(p3.player)  # merged: same Cricsheet registry id
    assert "Harmeet Singh (2)" in set(p3.player)    # kept: different registry id
    ident = csv(REP / "player_identity_audit_rebuilt.csv")
    assert ident.loc[ident.name == "Harmeet Singh (2)", "verdict"].str.contains("different person").all()


def test_audit_statuses_are_computed():
    q = json.loads((REP / "data_quality_audit_rebuilt.json").read_text())
    assert all(isinstance(v, bool) for v in q["checks"].values()), q["checks"]



# ---------------- Step 4: identity v1.1, delivery order, Phase 5 ----------------
import numpy as np

def test_identity_v11_evidence_and_effect():
    m = json.loads((OUT / "identity_map_v1.1_rebuilt.json").read_text())
    ids = rb.registry_ids()
    for e in m["evidence"]:
        assert ids[e["alias"]] == ids[e["canonical"]] == {e["registry_id"]}
        assert e["co_occurring_matches"] == 0
    v1 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_rebuilt.csv")
    v11 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_v1.1_rebuilt.csv")
    assert not set(m["v1.1_additions"]) & set(v11.player)
    assert "Harmeet Singh (2)" in set(v11.player) and "Harmeet Singh" in set(v11.player)
    # identity fix only renames: same rows, same points per match, same multiset of points
    assert len(v1) == len(v11)
    assert v1.groupby("match_id")["pts"].sum().equals(v11.groupby("match_id")["pts"].sum())
    renamed = v1.assign(player=v1.player.replace(m["v1.1_additions"])).sort_values(["match_id", "player"]).reset_index(drop=True)
    assert renamed.equals(v11.sort_values(["match_id", "player"]).reset_index(drop=True))


def test_delivery_order_dataset():
    d = pd.read_csv(OUT / "IPL_DecisionLab_Phase2_DeliveryOrder_rebuilt.csv", dtype={"ball_text": str})
    p2 = csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv")
    assert len(d) == len(p2) and (d.p2_row == np.arange(len(p2))).all()
    for c in ["match_id", "innings", "ball", "actual_delivery"]:  # original identifiers preserved and linked
        assert d[c].equals(p2[c]) or np.allclose(d[c], p2[c], equal_nan=True), c
    o = d.sort_values(["match_id", "innings", "delivery_seq"])
    g = o.groupby(["match_id", "innings"])
    assert g["raw_row"].apply(lambda s: s.is_monotonic_increasing).all(), "corrected order disagrees with source file order"
    assert g["delivery_seq"].apply(lambda s: (s.to_numpy() == np.arange(1, len(s) + 1)).all()).all()
    assert g["over"].apply(lambda s: s.is_monotonic_increasing and s.min() == 0 and set(s) == set(range(s.max() + 1))).all()
    ov = o.groupby(["match_id", "innings", "over"])
    assert ov["delivery_in_over"].apply(lambda s: (s.to_numpy() == np.arange(1, len(s) + 1)).all()).all()
    # wides/no-balls advance delivery_in_over but not the legal-ball count; actual_delivery = over + (legal balls before + 1)/10
    legal_before = o.legal_balls_in_over_so_far - o.is_legal.astype(int)
    assert (np.floor(o.actual_delivery).astype(int) == o.over).all()
    assert (((o.actual_delivery - o.over) * 10).round().astype(int) == legal_before + 1).all()
    assert (o.is_legal == ~(o.is_wide | o.is_noball)).all()
    tens = d[d.ball_text.str.endswith(".10")]
    assert len(tens) == 42 and (tens.delivery_in_over == 10).all()


def test_phase5_definitions_replay_recovered_features():
    old = csv(INP / "IPL_DecisionLab_Phase5_Final_Features.csv")
    new = rb.phase5(csv(INP / "IPL_DecisionLab_pm_reconstructed.csv"))
    assert list(new.columns) == list(old.columns)
    assert (new[["match_id", "player"]].to_numpy() == old[["match_id", "player"]].to_numpy()).all()
    for c in ["prev_pts", "avg_pts_prev3", "avg_pts_prev5", "std_pts_prev3", "trend_pts_prev3", "matches_before"]:
        assert np.allclose(new[c], old[c], atol=1e-9, equal_nan=True) and (new[c].isna() == old[c].isna()).all(), c


def test_phase5_rebuilt_matches_definition_and_has_no_lookahead():
    f = csv(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv")
    v11 = csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_v1.1_rebuilt.csv")
    assert len(f) == len(v11) and not f.duplicated(["match_id", "player"]).any()
    again = rb.phase5(v11)
    for c in ["prev_pts", "avg_pts_prev3", "std_pts_prev3", "matches_before"]:
        assert np.allclose(again[c], f[c], equal_nan=True), c
    # perturbation: changing one match's points must not change that row's features, only later rows of that player
    rng = np.random.default_rng(0)
    for i in rng.choice(len(v11), 25, replace=False):
        mod = v11.copy(); mod.loc[i, "pts"] += 1000
        g = rb.phase5(mod)
        key = (v11.loc[i, "match_id"], v11.loc[i, "player"])
        row = (g.match_id == key[0]) & (g.player == key[1])
        changed = ~np.isclose(g["avg_pts_prev3"], again["avg_pts_prev3"], equal_nan=True) | ~np.isclose(g["prev_pts"], again["prev_pts"], equal_nan=True)
        assert not changed[row].any(), "feature depends on current match"
        later = (g.player == key[1]) & (pd.to_datetime(g.start_date) > pd.to_datetime(v11.loc[i, "start_date"]))
        assert not (changed & ~later).any(), "feature changed outside the player's later matches"
    assert (f.season_year == f.season.astype(str).map(json.loads((OUT / "season_map_rebuilt.json").read_text()))).all()


# ---------------- Step 5-6: Phase 6 rebuilt ----------------
MOD = ROOT / "models"
import model as md

def _cfg():
    return json.loads((MOD / "preprocess_config_rebuilt.json").read_text())

def _mets():
    return json.loads((REP / "phase6_metrics_rebuilt.json").read_text())


def test_splits_chronological_disjoint_and_complete():
    f = csv(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv")
    s = md.split(f)
    assert sum(map(len, s.values())) == len(f)
    assert s["train"].start_date.max() < s["val"].start_date.min() <= s["val"].start_date.max() < s["test"].start_date.min()
    ms = {k: set(v.match_id) for k, v in s.items()}
    assert not (ms["train"] & ms["val"] or ms["val"] & ms["test"] or ms["train"] & ms["test"])
    cfg = _cfg()
    assert {k: len(v) for k, v in s.items()} == {k: v["rows"] for k, v in cfg["splits"].items()}
    med = s["train"][md.PREDICTORS].median()
    assert all(np.isclose(cfg["imputation"]["medians"][c], med[c]) for c in md.PREDICTORS)
    assert np.isclose(cfg["median_baseline_value"], s["train"]["pts"].median())
    assert cfg["features_sha256"] == sha(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv")


def test_saved_models_reproduce_saved_predictions():
    import joblib
    from xgboost import XGBRegressor
    cfg = _cfg()
    for name, h in cfg["artifacts"].items():
        assert sha(MOD / name) == h, name
    xgb = XGBRegressor(); xgb.load_model(MOD / "xgboost_rebuilt.json")
    loaded = {"pred_xgboost": xgb, "pred_ridge": joblib.load(MOD / "ridge_rebuilt.joblib"),
              "pred_random_forest": joblib.load(MOD / "random_forest_rebuilt.joblib")}
    for part in ("val", "test"):
        p = pd.read_csv(REP / f"phase6_predictions_{part}_rebuilt.csv")
        f = csv(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv")
        X = p[["match_id", "player"]].merge(f, on=["match_id", "player"], how="left")[md.PREDICTORS].fillna(cfg["imputation"]["medians"])
        for col, m in loaded.items():
            assert np.allclose(m.predict(X), p[col], atol=1e-4), (part, col)
        assert np.allclose(p.pred_median_baseline, cfg["median_baseline_value"])
        assert np.allclose(p.pred_last_match, X.prev_pts) and np.allclose(p.pred_rolling3, X.avg_pts_prev3)


def test_reported_metrics_reconcile_with_saved_predictions():
    r = _mets()
    for part in ("val", "test"):
        p = pd.read_csv(REP / f"phase6_predictions_{part}_rebuilt.csv")
        for name, col in r["prediction_columns"].items():
            m = md.metrics(p.pts, p[col])
            for k in ("mae", "rmse", "r2", "n"):
                assert np.isclose(m[k], r["metrics"][part][name][k], atol=1e-12), (part, name, k)
    val = r["metrics"]["val"]
    assert r["selection"]["best_by_validation_mae"] == min(val, key=lambda k: val[k]["mae"])
    assert r["selection"]["best_by_validation_rmse"] == min(val, key=lambda k: val[k]["rmse"])
    assert r["selection"]["selected_model"] == r["selection"]["best_by_validation_mae"]
    txt = (REP / "phase6_model_report_rebuilt.txt").read_text()
    for part in ("val", "test"):
        for name, m in r["metrics"][part].items():
            assert f"{m['mae']:8.4f}" in txt and f"{m['rmse']:8.4f}" in txt, (part, name)


def test_feature_importance_matches_saved_model():
    from xgboost import XGBRegressor
    xgb = XGBRegressor(); xgb.load_model(MOD / "xgboost_rebuilt.json")
    gain = pd.Series(xgb.get_booster().get_score(importance_type="gain")).reindex(md.PREDICTORS).fillna(0)
    imp = pd.read_csv(REP / "phase6_feature_importance_rebuilt.csv")
    assert list(imp.feature) == md.PREDICTORS
    assert np.allclose(imp.xgb_gain_share, gain / gain.sum()) and np.isclose(imp.xgb_gain_share.sum(), 1)


def test_plots_are_valid_pngs():
    for name in _mets()["plots"].values():
        b = (REP / name).read_bytes()
        assert b[:8] == b"\x89PNG\r\n\x1a\n" and len(b) > 10_000, name


def test_legacy_metrics_reconcile_with_recovered_reports():
    leg = _mets()["legacy_reconciliation_on_recovered_phase5"]
    old = json.loads((INP / "IPL_DecisionLab_Phase6_Audit_Report.json").read_text())
    lb = {d["model_heuristic"]: d for d in old["backtesting_leaderboard_validation_split"]}
    pairs = {"Overall Training Median Heuristic": "Median baseline (train median)", "Last Match Heuristic": "Last-match baseline",
             "3-Match Rolling Average Heuristic": "3-match rolling-average baseline"}
    for o, n in pairs.items():
        for k in ("mae", "rmse", "r2"):
            assert round(leg[f"val:{n}"][k], 4) == lb[o][k], (o, k)
    t = old["out_of_sample_generalization_test_split"][0]
    assert round(leg["test:Median baseline (train median)"]["mae"], 4) == t["test_mae"]
    assert round(leg["test:Median baseline (train median)"]["rmse"], 4) == t["test_rmse"]
    assert [leg["rows"][k] for k in ("train", "val", "test")] == [d["rows"] for d in old["chronological_splitting"]["splits"]]
    assert leg["train_medians"] == old["missing_value_handling"]["computed_medians"]
    txt = (INP / "IPL_DecisionLab_Phase6_Final_Consistency_Audit.txt").read_text()
    assert f"MAE:  {round(leg['test:Last-match baseline']['mae'], 4)}" in txt
    assert f"MAE:  {round(leg['test:3-match rolling-average baseline']['mae'], 4)}" in txt


def test_xgboost_retrain_is_deterministic():
    from xgboost import XGBRegressor
    f = csv(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv"); s = md.split(f); cfg = _cfg()
    X = s["train"][md.PREDICTORS].fillna(cfg["imputation"]["medians"])
    m = XGBRegressor(**cfg["hyperparameters"]["xgboost"]).fit(X, s["train"]["pts"])
    p = pd.read_csv(REP / "phase6_predictions_test_rebuilt.csv")
    Xt = s["test"][md.PREDICTORS].fillna(cfg["imputation"]["medians"])
    assert np.array_equal(m.predict(Xt), p.pred_xgboost.to_numpy(dtype=np.float32))


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn(); print(f"PASS  {name}")
        except Exception:
            failed += 1; print(f"FAIL  {name}\n{traceback.format_exc()}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
