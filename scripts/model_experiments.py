"""Offline model-improvement experiments (never run by the dashboard).

    python3 -I scripts/model_experiments.py

Protocol (fixed before looking at any test number):
  1. Fit every candidate on the training split (2008–2021) only.
  2. Score on validation (2022–2023). Selection rule: lowest validation MAE; ties → the simpler candidate.
  3. Only then evaluate the selected candidate — and the training-median baseline for reference — once on test (2024–2026).
Extra features use each player's EARLIER matches only. The original rebuilt artifacts in models/ are never touched;
outputs go to models/experiments/ and data/model_experiments*.
"""
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent
DATA, OUT = ROOT / "data", ROOT / "models" / "experiments"
BASE = ["prev_pts", "avg_pts_prev3", "avg_pts_prev5", "std_pts_prev3", "trend_pts_prev3", "matches_before"]
EXTRA = ["exp_mean_pts", "exp_median_pts", "last10_mean_pts", "season_prior_mean_pts", "days_since_last",
         "prior_bat_share", "prior_balls_faced_pm", "prior_balls_bowled_pm"]
SEED = 42


def add_history_features(pm):
    """All features are computed from strictly earlier matches of the same player."""
    f = pm.sort_values(["player", "start_date", "match_id"], kind="stable").reset_index(drop=True)
    g = f.groupby("player")
    prev = g["pts"].shift(1)
    by = prev.groupby(f["player"])
    f["exp_mean_pts"] = by.transform(lambda s: s.expanding().mean())
    f["exp_median_pts"] = by.transform(lambda s: s.expanding().median())
    f["last10_mean_pts"] = by.transform(lambda s: s.rolling(10, min_periods=3).mean())
    f["season_prior_mean_pts"] = f.groupby(["player", "season_year"])["pts"].transform(lambda s: s.shift(1).expanding().mean())
    f["days_since_last"] = (f["start_date"] - g["start_date"].shift(1)).dt.days
    cum = lambda c: g[c].transform(lambda s: s.shift(1).cumsum())
    tot = cum("pts")
    f["prior_bat_share"] = (cum("total_batting_points") / tot.where(tot > 0)).clip(-1, 2)
    n = f["matches_before"].where(f["matches_before"] > 0)
    f["prior_balls_faced_pm"] = cum("balls_faced") / n
    f["prior_balls_bowled_pm"] = cum("legal_balls") / n
    return f


def metrics(y, p):
    e = np.asarray(y) - np.asarray(p)
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "r2": float(1 - (e ** 2).sum() / ((np.asarray(y) - np.mean(y)) ** 2).sum()), "n": int(len(e))}


def boot_diff(df, a, b, reps=2000):
    per = pd.DataFrame({"m": df.match_id, "d": (df.pts - df[a]).abs() - (df.pts - df[b]).abs()}).groupby("m")["d"].agg(["sum", "count"])
    idx = np.random.default_rng(SEED).integers(0, len(per), size=(reps, len(per)))
    s, c = per["sum"].to_numpy(), per["count"].to_numpy()
    bt = s[idx].sum(1) / c[idx].sum(1)
    return {"estimate": float(s.sum() / c.sum()), "ci95": [float(np.percentile(bt, 2.5)), float(np.percentile(bt, 97.5))], "unit": "match"}


def candidates():
    c = [("Training median (constant)", "const", None, [])]
    for a in (1.0, 10.0, 100.0, 1000.0):
        c.append((f"Ridge α={a:g} · base features", "sk", make_pipeline(StandardScaler(), Ridge(alpha=a)), BASE))
        c.append((f"Ridge α={a:g} · base + history", "sk", make_pipeline(StandardScaler(), Ridge(alpha=a)), BASE + EXTRA))
    for depth, leaf in ((3, 50), (None, 100)):
        c.append((f"HistGB absolute-error · depth {depth} · leaf {leaf}", "sk",
                  HistGradientBoostingRegressor(loss="absolute_error", max_depth=depth, min_samples_leaf=leaf, learning_rate=0.05,
                                                max_iter=300, random_state=SEED), BASE + EXTRA))
    for depth in (3, 5):
        c.append((f"XGBoost absolute-error · depth {depth}", "xgb",
                  XGBRegressor(objective="reg:absoluteerror", n_estimators=300, learning_rate=0.05, max_depth=depth, subsample=0.8,
                               colsample_bytree=0.8, random_state=SEED, n_jobs=1), BASE + EXTRA))
    c.append(("Player expanding median (no model)", "col", "exp_median_pts", []))
    return c


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pm = pd.read_parquet(DATA / "player_match.parquet")
    f = add_history_features(pm)
    tr, va, te = (f[f.split == s].copy() for s in ("train", "val", "test"))
    med = tr[BASE + EXTRA].median()
    y_med = float(tr.pts.median())
    X = {k: d[BASE + EXTRA].fillna(med) for k, d in (("train", tr), ("val", va), ("test", te))}
    results, fitted = [], {}
    for name, kind, est, cols in candidates():
        if kind == "const":
            pv = np.full(len(va), y_med)
        elif kind == "col":
            pv = va[est].fillna(y_med).to_numpy()
        else:
            est.fit(X["train"][cols], tr.pts)
            pv = est.predict(X["val"][cols])
            fitted[name] = (est, cols)
        results.append({"candidate": name, "features": "base" if cols == BASE else ("base + history" if cols else "–"),
                        "n_features": len(cols), **{f"val_{k}": v for k, v in metrics(va.pts, pv).items()}})
    res = pd.DataFrame(results).sort_values(["val_mae", "n_features"]).reset_index(drop=True)
    sel = res.iloc[0]["candidate"]  # rule applied BEFORE any test evaluation
    # one-shot test evaluation of the selected candidate and the median reference
    kind = next(k for n, k, _, _ in candidates() if n == sel)
    if kind == "const":
        pt = np.full(len(te), y_med)
    elif kind == "col":
        pt = te["exp_median_pts"].fillna(y_med).to_numpy()
    else:
        est, cols = fitted[sel]
        pt = est.predict(X["test"][cols])
        (joblib.dump(est, OUT / "selected_experiment_model.joblib") if kind == "sk" else est.save_model(OUT / "selected_experiment_model.json"))
    tp = te[["match_id", "start_date", "season_year", "player", "pts"]].assign(pred_selected=pt, pred_median_baseline=y_med)
    tp.to_csv(DATA / "model_experiments_test_predictions.csv", index=False)
    vbest = float(res.iloc[0]["val_mae"])
    vmed = float(res.loc[res.candidate == "Training median (constant)", "val_mae"].iloc[0])
    report = {
        "label": "EXPERIMENTS — separate from the rebuilt Phase 6 models (which are unchanged)",
        "protocol": __doc__.strip(),
        "selection_rule": "lowest validation MAE; ties → fewer features",
        "selected": sel,
        "selected_beats_median_on_validation": bool(vbest < vmed),
        "validation_mae_improvement_vs_median": vmed - vbest,
        "validation_leaderboard": res.to_dict("records"),
        "test_after_selection": {"selected": metrics(te.pts, pt), "median_baseline": metrics(te.pts, np.full(len(te), y_med)),
                                 "selected_minus_median_mae": boot_diff(tp, "pred_selected", "pred_median_baseline")},
        "extra_features": EXTRA,
        "rows": {"train": len(tr), "val": len(va), "test": len(te)},
        "versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__},
        "original_artifacts_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT / "models").glob("*rebuilt*"))},
    }
    (DATA / "model_experiments.json").write_text(json.dumps(report, indent=2, default=str))
    print(res[["candidate", "val_mae", "val_rmse", "val_r2"]].round(4).to_string())
    print("selected:", sel, "| test:", {k: round(v, 4) for k, v in report["test_after_selection"]["selected"].items()},
          "| median test:", {k: round(v, 4) for k, v in report["test_after_selection"]["median_baseline"].items()})
    print("bootstrap selected − median (test MAE):", report["test_after_selection"]["selected_minus_median_mae"])


if __name__ == "__main__":
    main()
