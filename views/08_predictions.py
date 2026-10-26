import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui
from core import data as D


def err(y, p):
    e = y - p
    return dict(mae=float(np.abs(e).mean()), rmse=float(np.sqrt((e ** 2).mean())), n=len(e))


def main():
    ui.header("Models", "Predictive analytics",
              "Retrospective predictions from the rebuilt Phase 6 models. Nothing here forecasts a future match.")
    mets, cfg, pr = D.metrics(), D.model_config(), D.predictions()
    cols = mets["prediction_columns"]
    sel = mets["selection"]
    ui.note(f"<b>Retrospective test predictions.</b> Models were trained on {cfg['splits']['train']['first_date']} – {cfg['splits']['train']['last_date']}, "
            f"compared on validation ({cfg['splits']['val']['first_date']} – {cfg['splits']['val']['last_date']}) and reported once on the held-out "
            f"test period ({cfg['splits']['test']['first_date']} – {cfg['splits']['test']['last_date']}). Models are <b>rebuilt</b> with fixed "
            "settings — not the original training run. Selection rule: " + ui.esc(sel["rule"]))

    model = st.sidebar.selectbox("Model", list(cols), index=list(cols).index("XGBoost"), key="f_model")
    split = st.sidebar.radio("Evaluation split", ["test", "validation"], key="f_split", horizontal=True,
                             help="Validation selects the model; test reports it. They are never pooled.")
    d = pr[pr.split == split]
    players = d.groupby("player").size().sort_values(ascending=False)
    who = st.sidebar.selectbox("Player", players.index, format_func=lambda n: f"{n} · {players[n]} matches", key="f_pred_player")
    ui.active_filters(Model=model, Split=split, Player=who)

    key = "val" if split == "validation" else "test"
    m = mets["metrics"][key][model]
    best_mae = min(mets["metrics"][key], key=lambda k: mets["metrics"][key][k]["mae"])
    ui.kpi_row([
        dict(label=f"{model} · MAE", value=f"{m['mae']:.2f}", tag=split, sub=f"best on this split: {best_mae.replace(' (train median)', '')}"),
        dict(label="RMSE", value=f"{m['rmse']:.2f}", sub="penalises large misses more"),
        dict(label="R²", value=f"{m['r2']:.3f}", sub="≈ 0 → little better than a constant"),
        dict(label="Player-matches", value=f"{m['n']:,}", sub=f"{d.match_id.nunique()} matches"),
    ])

    t1, t2, t3, t4, t5 = st.tabs(["Player view", "Model comparison", "Errors", "Feature importance", "Artifacts"])
    pc = cols[model]
    with t1:
        p = d[d.player == who].sort_values("start_date")
        feats = D.player_match()[["match_id", "player", "matches_before", "prev_pts", "avg_pts_prev5"]]
        p = p.merge(feats, on=["match_id", "player"], how="left")
        thin = int((p.matches_before < 5).sum())
        if thin:
            st.warning(f"{thin} of {len(p)} predictions for {who} were made with fewer than 5 earlier matches — "
                       "rolling features were missing and filled with training medians, so those predictions are near the median.")
        p = p.assign(n=range(1, len(p) + 1), date=p.start_date.dt.strftime("%d %b %Y"))
        fig = go.Figure()
        fig.add_scatter(x=p.n, y=p.pts, mode="lines+markers", name="Actual", line=dict(color=ui.series(0), width=2),
                        customdata=p[["date", "venue"]], hovertemplate="%{customdata[0]} · %{customdata[1]}<br>actual %{y:.1f}<extra></extra>")
        fig.add_scatter(x=p.n, y=p[pc], mode="lines+markers", name=f"{model} (retrospective)", line=dict(color=ui.series(1), width=2, dash="dot"),
                        hovertemplate="predicted %{y:.1f}<extra></extra>")
        starts = p.groupby("season").n.min()
        fig.update_xaxes(tickvals=starts.values, ticktext=[str(y) for y in starts.index])
        fig.update_layout(title=f"{who}: actual vs retrospective prediction ({split})", xaxis_title="Season (matches in order played)",
                          yaxis_title="Fantasy points", hovermode="x unified")
        ui.chart(fig, height=380)
        e = err(p.pts, p[pc])
        st.markdown(ui.chips([f"Player MAE {e['mae']:.1f}", f"Player RMSE {e['rmse']:.1f}", f"n = {e['n']}",
                              "⚠ small sample" if e["n"] < 10 else "sample ok for a description"]), unsafe_allow_html=True)
        out = p[["start_date", "season", "venue", "player", "pts", pc, "matches_before"]].rename(columns={pc: f"pred_{model}"})
        out["error"] = out.pts - out[f"pred_{model}"]
        st.dataframe(ui.dates(out.round(2)), hide_index=True, width="stretch")
        ui.download(out, f"retrospective_predictions_{who.replace(' ', '_')}")
    with t2:
        rows = [{"model": k.replace(" (train median)", ""), "split": s_, "MAE": v["mae"], "RMSE": v["rmse"], "R²": v["r2"]}
                for s_, sk in (("validation", "val"), ("test", "test")) for k, v in mets["metrics"][sk].items()]
        mt = pd.DataFrame(rows)
        c1, c2 = st.columns(2)
        for col, metric in ((c1, "MAE"), (c2, "RMSE")):
            q = mt[mt.split == split].sort_values(metric, ascending=False)
            with col:
                ui.chart(px.bar(q, x=metric, y="model", orientation="h", title=f"{metric} on {split} (lower is better)",
                                labels={metric: f"{metric} (points)", "model": ""}, text_auto=".2f"), height=340)
        for s_ in ("validation", "test"):
            st.markdown(f"**{s_.title()}**")
            st.dataframe(mt[mt.split == s_].drop(columns="split").round(4), hide_index=True, width="stretch")
        b = mets["test_paired_bootstrap"]["xgboost_minus_median_baseline"]
        ui.note(f"<b>Is XGBoost better than the median?</b> On test it is worse by {b['estimate']:+.2f} MAE points "
                f"(95% interval {b['ci95'][0]:+.2f} to {b['ci95'][1]:+.2f}, resampling whole matches). "
                f"Best by validation MAE: <b>{ui.esc(sel['best_by_validation_mae'])}</b>; best by validation RMSE: <b>{ui.esc(sel['best_by_validation_rmse'])}</b>. "
                "No model is called a champion: the MAE winner is a constant, and the RMSE winner explains under 2% of variance.")
    with t3:
        q = d.assign(pred=d[pc], resid=d.pts - d[pc])
        c1, c2 = st.columns(2)
        with c1:
            fig = px.scatter(q, x="pred", y="pts", opacity=0.3, title=f"Actual vs predicted — {model}, {split}",
                             labels={"pred": "Predicted points", "pts": "Actual points"}, hover_name="player")
            hi = max(q.pts.max(), q.pred.max())
            fig.add_scatter(x=[0, hi], y=[0, hi], mode="lines", name="perfect", line=dict(color=ui.series(1), dash="dash"))
            sel_p = q[q.player == who]
            fig.add_scatter(x=sel_p.pred, y=sel_p.pts, mode="markers", name=who, marker=dict(color=ui.series(2), size=9, line=dict(width=1, color="white")))
            ui.chart(fig, height=420)
        with c2:
            ui.chart(px.histogram(q, x="resid", nbins=70, title="Residuals (actual − predicted)", labels={"resid": "Residual (points)", "count": "Player-matches"}), height=420)
        ui.chart(px.box(q.assign(season=q.season.astype(str)), x="season", y="resid", points=False, title="Residuals by season",
                        labels={"season": "Season", "resid": "Residual (points)"}), height=320)
        ui.download(q[["start_date", "player", "pts", "pred", "resid"]], f"residuals_{model}_{split}", key="dl_res")
    with t4:
        fi = D.table("phase6_feature_importance_rebuilt.csv")
        c1, c2 = st.columns(2)
        with c1:
            ui.chart(px.bar(fi.sort_values("xgb_gain_share"), x="xgb_gain_share", y="feature", orientation="h", text_auto=".1%",
                            title="XGBoost gain share", labels={"xgb_gain_share": "Share of gain", "feature": ""}), height=320)
        with c2:
            ui.chart(px.bar(fi.sort_values("xgb_val_permutation_mae_increase"), x="xgb_val_permutation_mae_increase", y="feature", orientation="h",
                            error_x="xgb_val_permutation_mae_std", title="Permutation importance on validation (MAE increase)",
                            labels={"xgb_val_permutation_mae_increase": "MAE increase (points)", "feature": ""},
                            color_discrete_sequence=[ui.series(1)]), height=320)
        st.markdown("**Feature definitions** (all computed from the player's earlier matches only)")
        st.dataframe(pd.DataFrame([
            ("prev_pts", "points in the previous match"), ("avg_pts_prev3", "mean of the previous 3 matches (needs 3)"),
            ("avg_pts_prev5", "mean of the previous 5 matches (needs 5)"), ("std_pts_prev3", "population std of the previous 3"),
            ("trend_pts_prev3", "avg_pts_prev3 − avg_pts_prev5"), ("matches_before", "number of earlier IPL matches")],
            columns=["feature", "definition"]), hide_index=True, width="stretch")
        st.caption(f"Model feature list read from the saved config: {', '.join(cfg['predictors'])}. Missing values → training medians.")
    with t5:
        loaded, errors = D.load_models()
        rows = []
        f = D.player_match()
        sample = d.head(300).merge(f[["match_id", "player"] + D.PREDICTORS], on=["match_id", "player"])
        X = sample[D.PREDICTORS].fillna(cfg["imputation"]["medians"])
        for name, mdl in loaded.items():
            diff = float(np.abs(mdl.predict(X) - sample[cols[name]]).max())
            rows.append({"artifact": name, "status": "PASS" if diff < 1e-3 else "FAIL", "check": f"re-predicts {len(X)} saved rows",
                         "max abs diff": f"{diff:.2e}"})
        for name, e in errors.items():
            rows.append({"artifact": name, "status": "FAIL", "check": "load", "max abs diff": e})
        ui.status_table(pd.DataFrame(rows), ["artifact", "status", "check", "max abs diff"])
        st.json({k: cfg[k] for k in ("label", "hyperparameters", "seed", "library_versions", "selection_rule")}, expanded=False)
        ui.note("<b>What forecasting would need.</b> Confirmed upcoming fixtures and playing XIs, then the same six features computed "
                "from each player's latest matches. The saved models can score such rows, but the pipeline does not yet produce them, "
                "and with R² near zero a forecast would carry very wide uncertainty.")
        ui.download(d, f"all_predictions_{split}", label="Download all predictions (this split)", key="dl_allpred")


ui.guard(main)
