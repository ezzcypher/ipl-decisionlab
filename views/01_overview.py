import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui
from core import data as D


def main():
    ui.header("Executive overview", "IPL DecisionLab",
              "Ball-by-ball IPL data 2008–2026, fantasy points per player-match, and an honest view of what the models can predict.")
    man, pm, season, mets = D.manifest(), D.player_match(), D.table("season_summary.parquet"), D.metrics()
    seasons = ui.season_filter(season.season_year)
    mm = ui.min_matches(20)
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", **{"Min matches (charts)": mm})

    s = season[season.season_year.between(*seasons)]
    p = ui.apply(pm, seasons=seasons)
    if ui.empty_or(p):
        return
    top = p.loc[p.pts.idxmax()]
    rng = f"{p.start_date.min():%d %b %Y} – {p.start_date.max():%d %b %Y}"
    ui.kpi_row([
        dict(label="Delivery records", value=f"{int(s.deliveries.sum()):,}", tag="cleaned",
             sub=f"Super overs excluded · raw file has {man['raw_summary']['rows']:,} rows", help_text="Rows in Phase 2 cleaned data"),
        dict(label="Matches · seasons", value=f"{int(s.matches.sum()):,} · {len(s)}", sub=rng),
        dict(label="Unique batters · bowlers", value=f"{p[p.batted].player.nunique():,} · {p[p.bowled].player.nunique():,}",
             sub="Faced ≥ 1 ball · bowled ≥ 1 ball (v1.1 identities)"),
        dict(label="Total runs", value=f"{int(s.runs.sum()):,}", sub=f"Off the bat {int(s.runs_off_bat.sum()):,} + extras {int(s.extras.sum()):,}"),
        dict(label="Wickets", value=f"{int(s.dismissals.sum()):,}", sub=f"All dismissals · {int(s.bowler_wickets.sum()):,} credited to bowlers"),
        dict(label="Player-match fantasy scores", value=f"{len(p):,}", sub="One row per player per match (scoring v1)"),
        dict(label="Highest fantasy score", value=f"{top.pts:,.1f} pts", sub=f"{top.player} · {top.start_date:%d %b %Y}"),
        dict(label="Core-field completeness", value=f"{man['cleaned_summary']['core_columns_complete_pct']:.1f}%", tag="all seasons",
             sub="12 identifier/run columns; sparse columns (wides, fielders…) are blank by design"),
    ])

    sel = mets["selection"]
    val, test = mets["metrics"]["val"], mets["metrics"]["test"]
    st.markdown("### Model scorecard")
    st.caption("Fixed — unaffected by filters. Selection uses the 2022–2023 validation split only; test is 2024–2026.")
    tm = test[sel["selected_model"]]
    ui.kpi_row([
        dict(label="Best by validation MAE", value=sel["best_by_validation_mae"].replace(" (train median)", ""), tag="selected",
             sub=f"Val MAE {val[sel['best_by_validation_mae']]['mae']:.2f} pts"),
        dict(label="Best by validation RMSE", value=sel["best_by_validation_rmse"], sub=f"Val RMSE {val[sel['best_by_validation_rmse']]['rmse']:.2f} pts"),
        dict(label="Selected model · test MAE / RMSE", value=f"{tm['mae']:.2f} / {tm['rmse']:.2f}", tag="test", sub=f"{tm['n']:,} player-matches, 2024–2026"),
        dict(label="Selected model · test R²", value=f"{tm['r2']:.3f}", sub="≈ 0: features explain almost none of match-to-match variance"),
    ])

    c1, c2 = st.columns(2)
    with c1:
        ui.chart(px.bar(s, x="season_year", y="runs", title="Runs per season", labels={"season_year": "Season", "runs": "Runs"},
                        hover_data={"matches": True, "runs_off_bat": True, "extras": True}))
    with c2:
        ui.chart(px.bar(s, x="season_year", y="dismissals", title="Wickets per season (all dismissals)",
                        labels={"season_year": "Season", "dismissals": "Wickets"}, color_discrete_sequence=[ui.series(1)],
                        hover_data={"bowler_wickets": True, "matches": True}))

    team = D.table("team_season.parquet")
    t = team[team.season_year.between(*seasons)].assign(run_rate=lambda d: 6 * d.runs_scored / d.balls_faced)
    hm = t.pivot(index="team", columns="season_year", values="run_rate")
    fig = go.Figure(go.Heatmap(z=hm.values, x=hm.columns, y=hm.index, colorscale=ui.seq_scale(), colorbar=dict(title="RPO"),
                               hovertemplate="%{y}<br>%{x}: %{z:.2f} runs/over<extra></extra>"))
    fig.update_layout(title="Team batting run rate by season (runs per 6 legal balls; blank = did not play)", xaxis_title="Season", yaxis_title="")
    ui.chart(fig, height=430)

    st_ = D.player_stats(p)
    st_ = st_[st_.matches >= mm]
    c1, c2 = st.columns(2)
    with c1:
        tp = st_.nlargest(12, "total_pts").sort_values("total_pts")
        ui.chart(None if tp.empty else px.bar(tp, x="total_pts", y="player", orientation="h", title=f"Top fantasy performers (total points, ≥ {mm} matches)",
                                              labels={"total_pts": "Total fantasy points", "player": ""}, hover_data={"matches": True, "avg_pts": ":.1f"}), height=420)
    with c2:
        ui.chart(None if st_.empty else px.scatter(st_, x="avg_pts", y="std_pts", size="matches", hover_name="player", title="Consistency: average vs volatility",
                                                   labels={"avg_pts": "Average points per match", "std_pts": "Std. deviation of points"},
                                                   hover_data={"matches": True, "latest_team": True}, size_max=16), height=420)
    trend = p.groupby("season_year").pts.agg(["mean", "median"]).reset_index().melt("season_year", var_name="stat", value_name="points")
    ui.chart(px.line(trend, x="season_year", y="points", color="stat", markers=True, title="Fantasy scoring trend: points per player-match",
                     labels={"season_year": "Season", "points": "Points", "stat": ""}), height=320)

    c1, c2 = st.columns(2)
    with c1:
        rows = [{"model": k.replace(" (train median)", ""), "metric": m.upper(), "value": v[m]} for k, v in val.items() for m in ("mae", "rmse")]
        fig = px.bar(pd.DataFrame(rows), x="value", y="model", color="metric", barmode="group", orientation="h",
                     title="Validation error by model (lower is better)", labels={"value": "Points", "model": ""})
        ui.chart(fig, height=380)
    with c2:
        cmp = D.table("audit_comparison.parquet")
        c = cmp[cmp.metric.isin(["Super-over rows", "Team names", "Venue names", "Player names (any role)"])]
        c = c.melt(["metric", "cause"], ["phase1_raw", "phase2_cleaned"], var_name="stage", value_name="count")
        c["stage"] = c.stage.map({"phase1_raw": "Phase 1 · raw", "phase2_cleaned": "Phase 2 · cleaned"})
        ui.chart(px.bar(c, x="count", y="metric", color="stage", barmode="group", orientation="h", log_x=True, hover_data={"cause": True},
                        title="Data-quality changes (log scale; all seasons)", labels={"count": "Count", "metric": ""}), height=380)
    c1, c2 = st.columns(2)
    with c1:
        ui.download(s, "overview_season_summary", label="Download season summary CSV")
    with c2:
        ui.download(st_.sort_values("total_pts", ascending=False), "overview_player_summary", label="Download player summary CSV", key="dl_ov_pl")
    ui.note("<b>Reading this page.</b> Delivery, run and wicket KPIs come from the cleaned Phase 2 data; fantasy KPIs from scoring v1 with "
            "v1.1 identity fixes. Model metrics are read from the saved rebuilt Phase 6 report and never mix validation and test.")


ui.guard(main)
