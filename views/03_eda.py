import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui
from core import data as D


def main():
    ui.header("Part 2 · cleaned data", "Exploratory analysis & cleaning",
              "Distributions, trends and outliers in the cleaned Phase 2 data (super overs excluded, names standardized, v1.1 identities).")
    season, inn = D.table("season_summary.parquet"), D.table("innings.parquet")
    seasons = ui.season_filter(season.season_year)
    teams = ui.multi("Batting team", inn.batting_team.unique(), "f_teams", "Applies to innings, over and team charts")
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Teams=teams)

    s = season[season.season_year.between(*seasons)].copy()
    i = inn[inn.season_year.between(*seasons) & ui.isin(inn.batting_team, teams)]
    if ui.empty_or(i):
        return
    s["run_rate"] = 6 * s.runs / s.legal_balls
    s["boundary_run_pct"] = 100 * (4 * s.fours + 6 * s.sixes) / s.runs_off_bat
    s["dot_pct"] = 100 * s.dots / s.legal_balls
    ui.kpi_row([
        dict(label="Innings", value=f"{len(i):,}", sub=f"{i.match_id.nunique():,} matches"),
        dict(label="Average innings total", value=f"{i.runs.mean():.1f}", sub=f"median {i.runs.median():.0f} runs"),
        dict(label="Run rate", value=f"{6 * i.runs.sum() / i.legal_balls.sum():.2f}", sub="runs per 6 legal balls"),
        dict(label="Sixes per innings", value=f"{i.sixes.mean():.2f}", sub=f"fours {i.fours.mean():.2f}"),
    ])

    t1, t2, t3, t4, t5 = st.tabs(["Season trends", "Runs, extras & wickets", "Innings & overs", "Players & venues", "Outliers & cleaning"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            ui.chart(px.line(s, x="season_year", y="run_rate", markers=True, title="Run rate by season (all teams)",
                             labels={"season_year": "Season", "run_rate": "Runs per over"}))
        with c2:
            m = s.melt("season_year", ["boundary_run_pct", "dot_pct"], var_name="metric", value_name="pct")
            m["metric"] = m.metric.map({"boundary_run_pct": "Runs from boundaries (% of bat runs)", "dot_pct": "Dot balls (% of legal balls)"})
            ui.chart(px.line(m, x="season_year", y="pct", color="metric", markers=True, title="Boundary share and dot-ball rate",
                             labels={"season_year": "Season", "pct": "%"}))
        st.caption("Season charts use all teams; the team filter applies to innings-level charts.")
    with t2:
        rpb = D.table("runs_per_ball_season.parquet")
        r = rpb[rpb.season_year.between(*seasons)].groupby("runs_off_bat").deliveries.sum().reset_index()
        c1, c2 = st.columns(2)
        with c1:
            ui.chart(px.bar(r, x="runs_off_bat", y="deliveries", title="Runs off the bat per delivery",
                            labels={"runs_off_bat": "Runs off bat", "deliveries": "Deliveries"}))
        with c2:
            ex = s[["wides", "noballs", "byes", "legbyes", "penalty"]].sum().rename_axis("type").reset_index(name="runs")
            ui.chart(px.bar(ex, x="type", y="runs", title="Extras by type (runs)", labels={"type": "", "runs": "Runs"},
                            color_discrete_sequence=[ui.series(1)]))
        dis = D.table("dismissal_season.parquet")
        d = dis[dis.season_year.between(*seasons)].groupby("wicket_type")["count"].sum().sort_values().reset_index()
        d["credited to bowler"] = d.wicket_type.isin(["caught", "bowled", "lbw", "stumped", "caught and bowled", "hit wicket"]).map({True: "yes", False: "no"})
        ui.chart(px.bar(d, x="count", y="wicket_type", color="credited to bowler", orientation="h", title="Dismissal types",
                        labels={"count": "Dismissals", "wicket_type": ""}), height=340)
    with t3:
        c1, c2 = st.columns(2)
        with c1:
            ii = i.assign(innings=i.innings.map({1: "1st innings", 2: "2nd innings"}))
            ui.chart(px.box(ii, x="innings", y="runs", color="innings", points=False, title="Innings totals",
                            labels={"runs": "Runs", "innings": ""}))
        with c2:
            ui.chart(px.histogram(i, x="runs", nbins=50, title="Distribution of innings totals", labels={"runs": "Runs", "count": "Innings"}))
        ov = D.table("over_season.parquet")
        ov = ov[ov.season_year.between(*seasons)]
        hm = ov.assign(rpo=6 * ov.runs / ov.legal_balls).pivot(index="season_year", columns="over", values="rpo")
        fig = go.Figure(go.Heatmap(z=hm.values, x=hm.columns + 1, y=hm.index, colorscale=ui.seq_scale(), colorbar=dict(title="RPO"),
                                   hovertemplate="Season %{y}, over %{x}: %{z:.2f} runs/over<extra></extra>"))
        fig.update_layout(title="Run rate by over and season (all teams)", xaxis_title="Over", yaxis_title="Season")
        ui.chart(fig, height=440)
    with t4:
        pm = ui.apply(D.player_match(), seasons=seasons, teams=teams)
        c1, c2 = st.columns(2)
        with c1:
            b = pm[pm.batted]
            ui.chart(px.histogram(b, x="runs", nbins=60, title="Runs per batting innings", labels={"runs": "Runs", "count": "Innings"}))
        with c2:
            w = pm[pm.legal_balls >= 12]
            w = w.assign(economy=6 * w.runs_conceded / w.legal_balls)
            ui.chart(px.histogram(w, x="economy", nbins=60, title="Economy per bowling spell (≥ 2 overs)",
                                  labels={"economy": "Runs per over", "count": "Spells"}, color_discrete_sequence=[ui.series(1)]))
        ven = D.table("venue_summary.parquet")
        mv = st.slider("Minimum matches at venue", 5, 80, 20, key="f_venue_min")
        v = ven[ven.matches >= mv].sort_values("avg_first_innings")
        ui.chart(None if v.empty else px.bar(v, x="avg_first_innings", y="venue", orientation="h", title="Average first-innings total by venue (all seasons)",
                                             labels={"avg_first_innings": "Runs", "venue": ""}, hover_data={"matches": True, "first": True, "last": True}),
                 height=max(320, 24 * len(v)))
    with t5:
        st.markdown("**Highest innings totals**")
        ui.table(ui.dates(i.nlargest(10, "runs")[["start_date", "batting_team", "bowling_team", "venue", "innings", "runs", "wickets", "sixes"]]),
                     hide_index=True, width="stretch")
        pm = ui.apply(D.player_match(), seasons=seasons, teams=teams)
        st.markdown("**Highest individual fantasy scores**")
        ui.table(ui.dates(pm.nlargest(10, "pts")[["start_date", "player", "team", "opponent", "runs", "wickets", "pts"]]), hide_index=True, width="stretch")
        st.markdown("**Cleaning decisions and their consequences**")
        ck = D.table("audit_checks.parquet").set_index("id")
        ui.table(pd.DataFrame([
            ("Exclude super overs (innings > 2)", "175 deliveries, 16 matches", "Totals and fantasy points reflect regulation innings only"),
            ("Keep 42 repeated delivery keys", "84 rows", "No real delivery lost; corrected order in a derived dataset"),
            ("Standardize 4 franchise names", f"{ck.loc['M1', 'rows_affected']:,} team cells", "Team trends join across renames; originals kept"),
            ("Standardize venue names", ck.loc["M5", "value"] + " names", "Venue splits combine renamed grounds (mapping recovered, not re-derived)"),
            ("Merge 3 player aliases (registry ids)", "Arshad Khan, NA Saini, S Arora", "Rolling form no longer resets at a name change"),
            ("Keep Harmeet Singh (2) separate", "1 match", "Different person per Cricsheet registry"),
            ("No imputation of blanks", "sparse columns", "Blank means 'not applicable', not missing"),
        ], columns=["decision", "scope", "consequence"]), hide_index=True, width="stretch")
        ui.download(i, "part2_innings_filtered", label="Download filtered innings CSV")


ui.guard(main)
