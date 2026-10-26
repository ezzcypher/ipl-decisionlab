import io
import zipfile
import pandas as pd
import streamlit as st
from components import ui
from core import data as D
from core import scoring


def facts():
    man, mets, cfg, pm = D.manifest(), D.metrics(), D.model_config(), D.player_match()
    ck = D.table("audit_checks.parquet")
    s = D.player_stats(pm)
    s30 = s[s.matches >= 30]
    val, test, sel = mets["metrics"]["val"], mets["metrics"]["test"], mets["selection"]
    boot = mets["test_paired_bootstrap"]["xgboost_minus_median_baseline"]
    pr = D.predictions()
    t = pr[pr.split == "test"].assign(abs_err=lambda d: (d.pts - d.pred_ridge).abs())
    worst = t.groupby("player").agg(n=("pts", "size"), mae=("abs_err", "mean")).query("n >= 20").nlargest(5, "mae")
    return dict(man=man, mets=mets, cfg=cfg, pm=pm, ck=ck, s30=s30, val=val, test=test, sel=sel, boot=boot, worst=worst)


def report_md(F):
    r, c = F["man"]["raw_summary"], F["man"]["cleaned_summary"]
    sel, val, test, boot = F["sel"], F["val"], F["test"], F["boot"]
    n = F["ck"].status.value_counts()
    so, an, tn = D.table("audit_super_overs.csv"), D.table("audit_over_anomalies.csv"), D.table("audit_team_names.csv")
    se = D.table("season_summary.parquet")
    rr = lambda q: 6 * q.runs.sum() / q.legal_balls.sum()
    early, late = rr(se[se.season_year <= 2021]), rr(se[se.season_year >= 2022])
    rk = D.table("audit_repeated_keys.csv")
    try:
        ex = D.jsonfile("model_experiments.json")
    except D.MissingData:
        ex = None
    top_avg = F["s30"].nlargest(5, "avg_pts")[["player", "avg_pts"]]
    steady = F["s30"][F["s30"].avg_pts >= 30].nsmallest(5, "cv")[["player", "cv"]]
    L = ["# IPL DecisionLab — final report", "",
         "## Part 1 · Data quality audit",
         f"- Source: Cricsheet all-IPL ball-by-ball CSV (ODC-By 1.0), {r['rows']:,} rows × {r['columns']} columns, {r['matches']:,} matches, {r['first_date']} → {r['last_date']}.",
         f"- {len(F['ck'])} checks recomputed from source: {n.get('PASS', 0)} pass, {n.get('WARN', 0)} warn, {n.get('FAIL', 0)} fail, {n.get('INFO', 0)} informational, {n.get('NOT REPRODUCED', 0)} earlier claims not reproduced.",
         f"- No exact duplicate rows. {len(rk) // 2} repeated (match, innings, ball) keys are legitimate 10th deliveries (`N.10` read as `N.1`) and were kept.",
         f"- {int(so.super_over_rows.sum())} super-over deliveries in {len(so)} matches. {len(an)} overs carry an unusual legal-ball count in the source (unresolved, kept).",
         f"- Mapping: {int(tn.changed.sum())} franchise renames; 3 player aliases confirmed by Cricsheet registry ids; Harmeet Singh (2) is a different person; venue mapping recovered, not re-derived.",
         "", "## Part 2 · EDA and cleaning",
         f"- Cleaned data: {c['rows']:,} rows, {c['matches']:,} matches, {c['seasons']} seasons, {c['total_runs']:,} runs, {c['dismissals']:,} dismissals.",
         "- Cleaning removed super overs only; it renamed teams, venues and 3 player aliases and filled no blanks.",
         f"- Run rate {early:.2f} per over in 2008–2021 vs {late:.2f} in 2022–2026; see the EDA page for season, over and venue detail.",
         "", "## Part 3 · Fantasy scoring",
         f"- Version {scoring.VERSION}. Batting: runs + fours + 2×sixes + 4/8/16 stacking milestones − 2 duck. Bowling: 25 per credited wicket. Dot balls: 0.5.",
         f"- The formula reproduces all {len(F['pm']):,} stored player-match scores (live check on the scoring page).",
         "- Roles (Batter / Bowler / All-rounder / Unknown) use a configurable participation heuristic — share of matches batted/bowled and balls per match — never fantasy points; no official roles exist in the data.",
         "", "## Part 4 · Predictive modelling (rebuilt)",
         f"- Features: {', '.join(F['cfg']['predictors'])}; earlier matches only; training-median imputation.",
         f"- Split: train {F['cfg']['splits']['train']['first_date']}–{F['cfg']['splits']['train']['last_date']}, validation 2022–2023, test 2024–2026.",
         f"- Best by validation MAE: {sel['best_by_validation_mae']} ({val[sel['best_by_validation_mae']]['mae']:.2f}). Best by validation RMSE: {sel['best_by_validation_rmse']} ({val[sel['best_by_validation_rmse']]['rmse']:.2f}).",
         f"- Selected model on test: MAE {test[sel['selected_model']]['mae']:.2f}, RMSE {test[sel['selected_model']]['rmse']:.2f}, R² {test[sel['selected_model']]['r2']:.3f}.",
         f"- XGBoost minus median baseline, test MAE: {boot['estimate']:+.2f} (95% CI {boot['ci95'][0]:+.2f} to {boot['ci95'][1]:+.2f}).",
         *([f"- Offline experiments (train → validation selection, one test evaluation): {ex['selected']} — test MAE "
            f"{ex['test_after_selection']['selected']['mae']:.2f} vs median {ex['test_after_selection']['median_baseline']['mae']:.2f}, "
            f"RMSE {ex['test_after_selection']['selected']['rmse']:.2f} vs {ex['test_after_selection']['median_baseline']['rmse']:.2f}."] if ex else []),
         "", "## Part 5 · Selection and auction interpretation",
         "- Rankings are weighted z-scores of average, recent form, consistency and participation; the weights are the user's choice.",
         "- No auction price data exists in the source. Users can upload real prices (template provided); players match by Cricsheet id or exact name only.",
         "- Price per point = sold price ÷ fantasy points in the auction season; blank for missing/zero prices or no matches. Past value is not future value.",
         "", "## Part 6 · Conclusions",
         "- Reliable: totals, rates, distributions, player histories and the scoring breakdown.",
         "- Not reliable: match-level point forecasts — recent-form features explain under 2% of variance.",
         "- Highest averages (≥ 30 matches): " + ", ".join(f"{a.player} ({a.avg_pts:.1f})" for a in top_avg.itertuples()) + ".",
         "- Steadiest high scorers (avg ≥ 30, lowest CV): " + ", ".join(f"{a.player} ({a.cv:.2f})" for a in steady.itertuples()) + ".",
         "- Largest test errors (Ridge, ≥ 20 matches): " + ", ".join(f"{a.Index} ({a.mae:.1f})" for a in F["worst"].itertuples()) + ".",
         f"- Open issues: venue mapping provenance, {len(an)} unusual overs, original Phase 6 not reproducible.",
         "- Next: match context (venue, opposition, batting position, toss), playing-XI data, an absolute-error objective, real price data."]
    return "\n".join(L)


def main():
    ui.header("Report", "Methodology, formulas & final report", "The complete analysis in plain language, with the numbers computed from the same data as every other page.")
    F = facts()
    md = report_md(F)
    parts = md.split("\n## ")
    tabs = st.tabs(["Part 1 · Audit", "Part 2 · EDA", "Part 3 · Scoring", "Part 4 · Models", "Part 5 · Selection", "Part 6 · Conclusions"])
    for tab, part in zip(tabs, parts[1:]):
        with tab:
            title, body = part.split("\n", 1)
            st.markdown(f"### {title}")
            st.markdown(body)
    with tabs[0]:
        st.page_link("views/02_data_audit.py", label="Open the full Part 1 audit report →")
    with tabs[1]:
        st.page_link("views/03_eda.py", label="Open the full Part 2 EDA report →")
        st.page_link("views/04_comparison.py", label="Open Part 1 vs Part 2 comparison →")
    with tabs[2]:
        ui.table(pd.DataFrame(scoring.RULES, columns=["component", "rule", "points", "condition"]), hide_index=True, width="stretch")
        st.page_link("views/07_scoring.py", label="Worked examples and calculator →")
    with tabs[3]:
        mt = pd.DataFrame([{"split": s_, "model": k, **{m: v[m] for m in ("mae", "rmse", "r2")}}
                           for s_, sk in (("validation", "val"), ("test", "test")) for k, v in F["mets"]["metrics"][sk].items()])
        ui.table(mt.round(4), hide_index=True, width="stretch")
        st.page_link("views/08_predictions.py", label="Predictions, errors and feature importance →")

    st.markdown("### Downloads")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("IPL_DecisionLab_final_report.md", md)
        for name in ["audit_checks.parquet", "audit_comparison.parquet", "audit_missing.parquet"]:
            z.writestr(name.replace(".parquet", ".csv"), D.table(name).to_csv(index=False))
        for name in ["audit_repeated_keys.csv", "audit_player_identity.csv", "audit_team_names.csv", "audit_venue_names.csv",
                     "audit_over_anomalies.csv", "audit_super_overs.csv", "phase6_feature_importance_rebuilt.csv"]:
            z.writestr(name, D.table(name).to_csv(index=False))
    c1, c2 = st.columns(2)
    c1.download_button("Download summary report (Markdown)", md.encode(), "IPL_DecisionLab_final_report.md", "text/markdown")
    c2.download_button("Download report + audit tables (ZIP)", buf.getvalue(), "IPL_DecisionLab_report_bundle.zip", "application/zip")


ui.guard(main)
