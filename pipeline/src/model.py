"""IPL DecisionLab — Phase 6 REBUILT models (not a reproduction of the original training run).

Input : rebuilt/IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv
Output: models/*_rebuilt.*, reports/phase6_*_rebuilt.*
Usage : python3 -I src/model.py
"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import joblib, sklearn, xgboost
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.inspection import permutation_importance
from xgboost import XGBRegressor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rebuild as rb

MOD, REP = rb.ROOT / "models", rb.ROOT / "reports"
FEATURES_FILE = rb.OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv"
PREDICTORS = ["prev_pts", "avg_pts_prev3", "avg_pts_prev5", "std_pts_prev3", "trend_pts_prev3", "matches_before"]
TARGET = "pts"
SPLITS = {"train": ("2008-01-01", "2021-12-31"), "val": ("2022-01-01", "2023-12-31"), "test": ("2024-01-01", "2026-12-31")}
SEED = 42
# Fixed, untuned settings (original hyperparameters unrecovered). Documented in preprocess config.
HYPER = {
    "ridge": {"alpha": 1.0},
    "random_forest": {"n_estimators": 300, "min_samples_leaf": 20, "random_state": SEED, "n_jobs": 1},
    "xgboost": {"n_estimators": 300, "learning_rate": 0.05, "max_depth": 4, "subsample": 0.8, "colsample_bytree": 0.8,
                "min_child_weight": 1, "tree_method": "hist", "objective": "reg:squarederror", "random_state": SEED, "n_jobs": 1},
}
SELECTION_RULE = "Lowest validation MAE among all candidates (baselines included); RMSE leader reported separately. Test set never used for selection."
INK, INK2, SURF, BLUE, ORANGE = "#0b0b0b", "#52514e", "#fcfcfb", "#2a78d6", "#eb6834"


def split(f):
    d = pd.to_datetime(f["start_date"])
    return {k: f[(d >= a) & (d <= b)].copy() for k, (a, b) in SPLITS.items()}


def metrics(y, p):
    e = np.asarray(y) - np.asarray(p)
    ss = ((np.asarray(y) - np.mean(y)) ** 2).sum()
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt((e ** 2).mean())), "r2": float(1 - (e ** 2).sum() / ss), "n": int(len(e))}


def baseline_preds(X, train_target_median):
    return {"Median baseline (train median)": np.full(len(X), train_target_median),
            "Last-match baseline": X["prev_pts"].to_numpy(),
            "3-match rolling-average baseline": X["avg_pts_prev3"].to_numpy()}


def paired_bootstrap_mae_diff(df, a, b, reps=2000, seed=SEED):
    """MAE(a) - MAE(b) on the test set, resampling whole matches. Returns point estimate and 95% interval."""
    ea, eb = (df[TARGET] - df[a]).abs(), (df[TARGET] - df[b]).abs()
    per = pd.DataFrame({"m": df["match_id"], "d": ea - eb}).groupby("m")["d"].agg(["sum", "count"])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(per), size=(reps, len(per)))
    s, c = per["sum"].to_numpy(), per["count"].to_numpy()
    boot = s[idx].sum(1) / c[idx].sum(1)
    return {"estimate": float(s.sum() / c.sum()), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
            "resampling_unit": "match", "reps": reps, "seed": seed}


def style(ax, title):
    ax.set_facecolor(SURF)
    ax.set_title(title, color=INK, fontsize=11, loc="left")
    ax.tick_params(colors=INK2, labelsize=9)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#d6d5d0")
    ax.grid(color="#ebeae6", linewidth=0.6)
    ax.set_axisbelow(True)


def plots(test, sel, imp):
    out = {}
    fig, ax = plt.subplots(figsize=(7, 6), facecolor=SURF)
    ax.scatter(test["pred_xgboost"], test[TARGET], s=8, alpha=0.25, color=BLUE, edgecolors="none", label="XGBoost (rebuilt)")
    lim = [min(test[TARGET].min(), 0), test[TARGET].max()]
    ax.plot(lim, lim, color=INK2, linewidth=1, linestyle="--", label="Perfect prediction")
    ax.axvline(test["pred_median_baseline"].iloc[0], color=ORANGE, linewidth=2, label="Median baseline")
    style(ax, "Actual vs predicted fantasy points — test 2024–2026 (rebuilt)")
    ax.set_xlabel("Predicted points", color=INK2); ax.set_ylabel("Actual points", color=INK2)
    ax.legend(frameon=False, fontsize=9, labelcolor=INK)
    out["actual_vs_predicted"] = REP / "phase6_actual_vs_predicted_rebuilt.png"
    fig.tight_layout(); fig.savefig(out["actual_vs_predicted"], dpi=130); plt.close(fig)

    r = test[TARGET] - test["pred_xgboost"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.5), facecolor=SURF)
    a1.hist(r, bins=60, color=BLUE, edgecolor=SURF, linewidth=0.5)
    a1.axvline(0, color=INK2, linewidth=1)
    style(a1, "XGBoost residuals (actual − predicted), test")
    a1.set_xlabel("Residual (points)", color=INK2); a1.set_ylabel("Player-matches", color=INK2)
    a2.scatter(test["pred_xgboost"], r, s=8, alpha=0.25, color=BLUE, edgecolors="none")
    a2.axhline(0, color=INK2, linewidth=1)
    style(a2, "Residual vs predicted, test")
    a2.set_xlabel("Predicted points", color=INK2); a2.set_ylabel("Residual (points)", color=INK2)
    out["residuals"] = REP / "phase6_residuals_rebuilt.png"
    fig.tight_layout(); fig.savefig(out["residuals"], dpi=130); plt.close(fig)

    o = imp.sort_values("xgb_gain_share")
    fig, ax = plt.subplots(figsize=(7, 4), facecolor=SURF)
    ax.barh(o["feature"], o["xgb_gain_share"], color=BLUE, height=0.6)
    for y, v in enumerate(o["xgb_gain_share"]):
        ax.text(v + 0.005, y, f"{v:.1%}", va="center", color=INK, fontsize=9)
    style(ax, "XGBoost gain share by feature (rebuilt model)")
    ax.set_xlabel("Share of total gain", color=INK2)
    ax.grid(axis="y", visible=False)
    out["feature_importance"] = REP / "phase6_feature_importance_rebuilt.png"
    fig.tight_layout(); fig.savefig(out["feature_importance"], dpi=130); plt.close(fig)
    return out


def legacy_reconciliation():
    """Baselines on the RECOVERED (reconstructed-scoring) Phase 5, to reconcile the old JSON/TXT figures."""
    old = pd.read_csv(rb.INP / "IPL_DecisionLab_Phase5_Final_Features.csv")
    s = split(old)
    med = s["train"][PREDICTORS].median()
    res = {}
    for part in ("val", "test"):
        X = s[part][PREDICTORS].fillna(med)
        for name, p in baseline_preds(X, s["train"][TARGET].median()).items():
            res[f"{part}:{name}"] = metrics(s[part][TARGET], p)
    res["rows"] = {k: len(v) for k, v in s.items()}
    res["matches"] = {k: int(v["match_id"].nunique()) for k, v in s.items()}
    res["train_medians"] = med.round(2).to_dict()
    return res


def main():
    MOD.mkdir(exist_ok=True); REP.mkdir(exist_ok=True)
    f = pd.read_csv(FEATURES_FILE)
    s = split(f)
    assert sum(len(v) for v in s.values()) == len(f), "rows outside split windows"
    med = s["train"][PREDICTORS].median()
    X = {k: v[PREDICTORS].fillna(med) for k, v in s.items()}
    y = {k: v[TARGET] for k, v in s.items()}
    y_med = float(y["train"].median())

    models = {
        "ridge": make_pipeline(StandardScaler(), Ridge(**HYPER["ridge"])),
        "random_forest": RandomForestRegressor(**HYPER["random_forest"]),
        "xgboost": XGBRegressor(**HYPER["xgboost"]),
    }
    for m in models.values():
        m.fit(X["train"], y["train"])
    joblib.dump(models["ridge"], MOD / "ridge_rebuilt.joblib")
    joblib.dump(models["random_forest"], MOD / "random_forest_rebuilt.joblib", compress=3)
    models["xgboost"].save_model(MOD / "xgboost_rebuilt.json")

    labels = {"ridge": "Ridge regression", "random_forest": "Random forest", "xgboost": "XGBoost"}
    cols = {"Median baseline (train median)": "pred_median_baseline", "Last-match baseline": "pred_last_match",
            "3-match rolling-average baseline": "pred_rolling3", **{labels[k]: f"pred_{k}" for k in models}}
    preds, mets = {}, {}
    for part in ("val", "test"):
        p = baseline_preds(X[part], y_med)
        p.update({labels[k]: m.predict(X[part]) for k, m in models.items()})
        out = s[part][["match_id", "start_date", "season", "season_year", "venue", "player", TARGET]].copy()
        for name, v in p.items():
            out[cols[name]] = np.asarray(v, dtype=float)
        out.to_csv(REP / f"phase6_predictions_{part}_rebuilt.csv", index=False)
        preds[part] = out
        mets[part] = {name: metrics(out[TARGET], out[cols[name]]) for name in p}

    val = mets["val"]
    best_mae = min(val, key=lambda k: val[k]["mae"])
    best_rmse = min(val, key=lambda k: val[k]["rmse"])
    test = preds["test"]
    sel_col = cols[best_mae]
    boot = {"xgboost_minus_median_baseline": paired_bootstrap_mae_diff(test, "pred_xgboost", "pred_median_baseline")}
    if sel_col != "pred_median_baseline":
        boot["selected_minus_median_baseline"] = paired_bootstrap_mae_diff(test, sel_col, "pred_median_baseline")

    booster = models["xgboost"].get_booster()
    gain = pd.Series(booster.get_score(importance_type="gain")).reindex(PREDICTORS).fillna(0)
    total_gain = pd.Series(booster.get_score(importance_type="total_gain")).reindex(PREDICTORS).fillna(0)
    perm = permutation_importance(models["xgboost"], X["val"], y["val"], scoring="neg_mean_absolute_error",
                                  n_repeats=10, random_state=SEED)
    imp = pd.DataFrame({"feature": PREDICTORS,
                        "xgb_gain_share": (gain / gain.sum()).to_numpy(),
                        "xgb_mean_gain": gain.to_numpy(),
                        "xgb_total_gain_share": (total_gain / total_gain.sum()).to_numpy(),
                        "xgb_sklearn_feature_importances_": models["xgboost"].feature_importances_,
                        "rf_impurity_importance": models["random_forest"].feature_importances_,
                        "xgb_val_permutation_mae_increase": perm.importances_mean,
                        "xgb_val_permutation_mae_std": perm.importances_std})
    imp.to_csv(REP / "phase6_feature_importance_rebuilt.csv", index=False)
    figs = plots(test, sel_col, imp)

    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    config = {
        "label": "REBUILT — retrained with documented settings; NOT an exact reproduction of the original Phase 6 run",
        "features_file": FEATURES_FILE.name, "features_sha256": sha(FEATURES_FILE),
        "scoring_version": "v1 rules (no fielding) + v1.1 identity fixes",
        "target": TARGET, "predictors": PREDICTORS,
        "splits": {k: {"from": a, "to": b, "rows": len(s[k]), "matches": int(s[k]["match_id"].nunique()),
                       "first_date": s[k]["start_date"].min(), "last_date": s[k]["start_date"].max()} for k, (a, b) in SPLITS.items()},
        "imputation": {"method": "training-split median per predictor", "medians": {k: float(v) for k, v in med.items()}},
        "median_baseline_value": y_med,
        "hyperparameters": HYPER, "tuning": "none (fixed settings)", "seed": SEED,
        "selection_rule": SELECTION_RULE,
        "library_versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__,
                             "scikit-learn": sklearn.__version__, "xgboost": xgboost.__version__},
        "artifacts": {p.name: sha(p) for p in sorted(MOD.iterdir()) if p.name != "preprocess_config_rebuilt.json"},
    }
    (MOD / "preprocess_config_rebuilt.json").write_text(json.dumps(config, indent=2))
    report = {
        "label": config["label"],
        "metrics": mets,
        "selection": {"rule": SELECTION_RULE, "best_by_validation_mae": best_mae, "best_by_validation_rmse": best_rmse,
                      "selected_model": best_mae, "selected_model_test": mets["test"][best_mae],
                      "best_by_test_mae_for_reference_only": min(mets["test"], key=lambda k: mets["test"][k]["mae"]),
                      "best_by_test_rmse_for_reference_only": min(mets["test"], key=lambda k: mets["test"][k]["rmse"])},
        "test_paired_bootstrap": boot,
        "prediction_columns": cols,
        "plots": {k: v.name for k, v in figs.items()},
        "legacy_reconciliation_on_recovered_phase5": legacy_reconciliation(),
    }
    (REP / "phase6_metrics_rebuilt.json").write_text(json.dumps(report, indent=2))
    lines = [f"IPL DecisionLab — Phase 6 model report (REBUILT)", config["label"], "",
             f"Selection rule: {SELECTION_RULE}",
             f"Best by validation MAE : {best_mae}", f"Best by validation RMSE: {best_rmse}", ""]
    for part in ("val", "test"):
        lines.append(f"{part.upper()} ({config['splits'][part]['first_date']} to {config['splits'][part]['last_date']}, "
                     f"{config['splits'][part]['rows']} rows, {config['splits'][part]['matches']} matches)")
        for name, m in sorted(mets[part].items(), key=lambda kv: kv[1]["mae"]):
            lines.append(f"  {name:34s} MAE {m['mae']:8.4f}  RMSE {m['rmse']:8.4f}  R2 {m['r2']:8.4f}")
        lines.append("")
    for k, v in boot.items():
        lines.append(f"Test paired bootstrap {k}: {v['estimate']:+.4f} MAE points, 95% CI [{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}] (match resampling)")
    (REP / "phase6_model_report_rebuilt.txt").write_text("\n".join(lines) + "\n")
    print(json.dumps({"val": {k: {m: round(x, 4) for m, x in v.items() if m != "n"} for k, v in mets["val"].items()},
                      "test": {k: {m: round(x, 4) for m, x in v.items() if m != "n"} for k, v in mets["test"].items()},
                      "selection": report["selection"], "bootstrap": boot,
                      "importance": imp[["feature", "xgb_gain_share", "xgb_val_permutation_mae_increase"]].round(4).to_dict("records")}, indent=1))


if __name__ == "__main__":
    main()
