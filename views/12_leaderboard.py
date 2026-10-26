import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D

SHORT = {"Median baseline (train median)": "Training-median baseline"}


def metric_rows(df, cols):
    out = []
    for name, c in cols.items():
        e = df.pts - df[c]
        ss = ((df.pts - df.pts.mean()) ** 2).sum()
        out.append({"model": SHORT.get(name, name), "MAE": float(e.abs().mean()), "RMSE": float(np.sqrt((e ** 2).mean())),
                    "R²": float(1 - (e ** 2).sum() / ss) if ss else np.nan, "n": len(df)})
    return pd.DataFrame(out)


def main():
    ui.header("Models", "Model leaderboard",
              "All six rebuilt models on separate validation and test splits, read from the saved prediction files — nothing is retrained here.")
    mets, cfg, pr = D.metrics(), D.model_config(), D.predictions()
    cols = mets["prediction_columns"]
    sp = cfg["splits"]
    min_n = st.sidebar.number_input("Minimum rows per season/player group", 5, 200, st.session_state.get("f_lb_min", 30), key="f_lb_min")
    ui.active_filters(**{"Min group size": min_n})

    rows = []
    for split, k in (("validation", "val"), ("test", "test")):
        d = pr[pr.split == split]
        m = metric_rows(d, cols).assign(split=split, period=f"{sp[k]['first_date']} → {sp[k]['last_date']}", matches=d.match_id.nunique())
        rows.append(m)
    lb = pd.concat(rows, ignore_index=True)
    # reconcile with the saved report (fails loudly rather than showing drifted numbers)
    for split, k in (("validation", "val"), ("test", "test")):
        for name in cols:
            r = lb[(lb.split == split) & (lb.model == SHORT.get(name, name))].iloc[0]
            if not np.isclose(r.MAE, mets["metrics"][k][name]["mae"]) or not np.isclose(r.RMSE, mets["metrics"][k][name]["rmse"]):
                st.error(f"Leaderboard does not reconcile with the saved metrics for {name} ({split}).")
                return
    val = lb[lb.split == "validation"]
    best_mae, best_rmse = val.loc[val.MAE.idxmin(), "model"], val.loc[val.RMSE.idxmin(), "model"]
    ui.kpi_row([
        dict(label="Best by validation MAE", value=best_mae, tag="selection rule", sub=f"{val.MAE.min():.2f} points"),
        dict(label="Best by validation RMSE", value=best_rmse, sub=f"{val.RMSE.min():.2f} points"),
        dict(label="Best validation R²", value=f"{val['R²'].max():.3f}", sub="< 0.02 for every model"),
        dict(label="Training window", value=f"{sp['train']['rows']:,} rows", sub=f"{sp['train']['first_date']} → {sp['train']['last_date']}"),
    ])
    ui.note("<b>How to read this.</b> MAE and RMSE are errors in fantasy points — <b>lower is better</b>. RMSE punishes big misses more. "
            "R² is the share of match-to-match variance explained: near 0 means little explanatory power; <b>negative</b> means worse than "
            "predicting the split's own mean. The model is chosen on <b>validation MAE only</b>; test numbers are reported afterwards and never "
            "used to choose. The 2024–2026 test values are <b>retrospective predictions</b>, not forecasts.")

    t1, t2, t3, t4, t5, t6 = st.tabs(["Leaderboard", "Actual vs predicted", "Errors", "By season", "By player", "Experiments"])
    with t1:
        for split in ("validation", "test"):
            st.markdown(f"**{split.title()}** · {lb[lb.split == split].period.iloc[0]} · {int(lb[lb.split == split].n.iloc[0]):,} player-matches, "
                        f"{int(lb[lb.split == split].matches.iloc[0])} matches")
            ui.table(lb[lb.split == split].sort_values("MAE")[["model", "MAE", "RMSE", "R²", "n"]].round(4), key=f"lb_{split}", sort=False)
        long = lb.melt(["model", "split"], ["MAE", "RMSE"], var_name="metric", value_name="points")
        ui.chart(px.bar(long, x="points", y="model", color="split", facet_col="metric", barmode="group", orientation="h",
                        title="Error by model — validation vs test (lower is better)", labels={"points": "Points", "model": ""}), height=420)
        ui.download(lb, "model_leaderboard")
    with t2:
        c1, c2 = st.columns(2)
        model = c1.selectbox("Model", list(cols), index=list(cols).index("Ridge regression"), key="f_lb_model")
        split = c2.radio("Split", ["validation", "test"], horizontal=True, key="f_lb_split")
        d = pr[pr.split == split].assign(pred=lambda x: x[cols[model]])
        fig = px.scatter(d, x="pred", y="pts", opacity=0.25, hover_name="player", title=f"{model}: actual vs predicted ({split})",
                         labels={"pred": "Predicted points", "pts": "Actual points"})
        hi = float(max(d.pts.max(), d.pred.max()))
        fig.add_scatter(x=[0, hi], y=[0, hi], mode="lines", name="perfect", line=dict(dash="dash", color=ui.series(1)))
        ui.chart(fig, height=440)
    with t3:
        d = pr[pr.split == st.session_state.get("f_lb_split", "validation")]
        res = pd.concat([pd.DataFrame({"model": SHORT.get(n, n), "residual": d.pts - d[c]}) for n, c in cols.items()])
        ui.chart(px.box(res, x="model", y="residual", points=False, title="Residual distribution by model (actual − predicted)",
                        labels={"model": "", "residual": "Residual (points)"}), height=420)
        fi = D.table("phase6_feature_importance_rebuilt.csv")
        m = fi.melt("feature", ["xgb_gain_share", "rf_impurity_importance"], var_name="measure", value_name="importance")
        m["measure"] = m.measure.map({"xgb_gain_share": "XGBoost gain share", "rf_impurity_importance": "Random forest impurity"})
        ui.chart(px.bar(m, x="importance", y="feature", color="measure", barmode="group", orientation="h",
                        title="Feature importance (tree models)", labels={"importance": "Share", "feature": ""}), height=360)
        st.caption("Ridge has no comparable importance; baselines use a single feature by construction.")
    with t4:
        rows = []
        for (split, season), g in pr.groupby(["split", "season"]):
            if len(g) >= min_n:
                rows.append(metric_rows(g, cols).assign(split=split, season=season))
        bs = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        if not ui.empty_or(bs, "No season meets the minimum group size."):
            ui.chart(px.line(bs, x="season", y="MAE", color="model", markers=True, facet_col="split", title="MAE by season",
                             labels={"season": "Season", "MAE": "MAE (points)"}), height=380)
            ui.table(bs[["split", "season", "model", "MAE", "RMSE", "R²", "n"]].round(3), key="lb_season")
            ui.download(bs, "model_metrics_by_season", key="dl_bs")
    with t5:
        split = st.radio("Split ", ["validation", "test"], horizontal=True, key="f_lb_psplit")
        d = pr[pr.split == split]
        g = d.groupby("player")
        keep = g.size()[g.size() >= min_n].index
        if len(keep) == 0:
            st.info(f"No player has ≥ {min_n} rows in {split}.")
        else:
            bp = pd.concat([metric_rows(d[d.player == p], cols).assign(player=p) for p in keep], ignore_index=True)
            piv = bp.pivot(index="player", columns="model", values="MAE").round(2)
            piv["best model (MAE)"] = piv.idxmin(axis=1)
            ui.table(piv.reset_index().merge(g.size().rename("n").reset_index(), on="player"), key="lb_player")
            st.caption(f"Players with ≥ {min_n} rows. Per-player R² is not shown — with few rows and near-constant predictions it is not meaningful.")
            ui.download(piv.reset_index(), f"model_mae_by_player_{split}", key="dl_bp")
    with t6:
        try:
            ex = D.jsonfile("model_experiments.json")
        except D.MissingData:
            ex = None
            st.info("No experiment report found. Run `python3 -I scripts/model_experiments.py` locally to generate one.")
    if ex is not None:
        with t6:
            ui.note(f"<b>{ui.esc(ex['label'])}.</b> Selection rule: {ui.esc(ex['selection_rule'])}. Candidates were fit on train and compared on "
                    "validation only; the test split was evaluated once, after the rule picked a candidate.")
            v = pd.DataFrame(ex["validation_leaderboard"])
            ui.table(v[["candidate", "features", "val_mae", "val_rmse", "val_r2", "val_n"]].round(4), key="exp_val", sort=False)
            t = ex["test_after_selection"]
            b = t["selected_minus_median_mae"]
            ui.kpi_row([
                dict(label="Selected candidate", value=ex["selected"].split(" · ")[0], sub=ex["selected"]),
                dict(label="Test MAE · selected", value=f"{t['selected']['mae']:.2f}", tag="test", sub=f"median baseline {t['median_baseline']['mae']:.2f}"),
                dict(label="Test RMSE · selected", value=f"{t['selected']['rmse']:.2f}", sub=f"median baseline {t['median_baseline']['rmse']:.2f}"),
                dict(label="MAE difference vs median", value=f"{b['estimate']:+.2f}", sub=f"95% CI {b['ci95'][0]:+.2f} to {b['ci95'][1]:+.2f} (match resampling)"),
            ])
            better_rmse = t["selected"]["rmse"] < t["median_baseline"]["rmse"]
            st.markdown(f"**Result.** The selected candidate lowers test MAE by {-b['estimate']:.2f} points versus the median baseline "
                        f"but {'also lowers' if better_rmse else 'raises'} RMSE ({t['selected']['rmse']:.2f} vs {t['median_baseline']['rmse']:.2f}) and has "
                        f"R² {t['selected']['r2']:.3f}. A small, real improvement in typical error — not useful match-level forecasting.")
    with st.expander("Limitations", expanded=False):
        st.markdown("- Features describe only recent fantasy form; no venue, opposition, batting position, toss or playing-XI information.\n"
                    "- Every model explains under 2% of variance; individual-match errors of 20–30 points are typical.\n"
                    "- Models are rebuilt with fixed, untuned settings; the original Phase 6 run could not be recovered.\n"
                    "- Players with fewer than 5 earlier matches get median-imputed features, so their predictions sit near the median.\n"
                    "- No future fixtures, line-ups, injuries or pitch conditions exist in the data; nothing here is a forecast.")


ui.guard(main)
