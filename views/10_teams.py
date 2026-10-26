import plotly.express as px
import streamlit as st
from components import ui
from core import data as D
from core import roles as R


def main():
    ui.header("Teams", "Teams & seasons",
              "Team batting and bowling by season under standardized franchise names. Match results are not in the data, so no wins or losses are shown.")
    team, pm, inn = D.table("team_season.parquet"), D.player_match(), D.table("innings.parquet")
    seasons = ui.season_filter(team.season_year)
    teams = ui.multi("Teams to compare", team.team.unique(), "f_team_compare")
    focus = st.sidebar.selectbox("Team profile", sorted(team.team.unique()), key="f_team_focus",
                                 index=sorted(team.team.unique()).index("Mumbai Indians"))
    role_f = ui.multi("Role (contributors chart)", R.ROLES, "f_roles")
    th = R.thresholds()
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Compare=teams, Profile=focus, Roles=role_f)

    t = team[team.season_year.between(*seasons)].assign(run_rate=lambda d: 6 * d.runs_scored / d.balls_faced,
                                                        economy=lambda d: 6 * d.runs_conceded / d.balls_bowled)
    ft = t[t.team == focus]
    if ui.empty_or(ft, f"{focus} did not play in the selected seasons."):
        return
    ui.kpi_row([
        dict(label="Seasons · matches", value=f"{len(ft)} · {int(ft.matches.sum())}", sub=f"{ft.season_year.min()}–{ft.season_year.max()}"),
        dict(label="Runs scored", value=f"{int(ft.runs_scored.sum()):,}", sub=f"run rate {6 * ft.runs_scored.sum() / ft.balls_faced.sum():.2f}"),
        dict(label="Wickets taken", value=f"{int(ft.wickets_taken.sum()):,}", sub=f"economy {6 * ft.runs_conceded.sum() / ft.balls_bowled.sum():.2f}"),
        dict(label="Names in source", value=str(len(set(", ".join(ft.original_names).split(", ")))), sub=", ".join(sorted(set(", ".join(ft.original_names).split(", "))))),
    ])
    c1, c2 = st.columns(2)
    with c1:
        m = ft.melt("season_year", ["runs_scored", "runs_conceded"], var_name="side", value_name="runs")
        m["side"] = m.side.map({"runs_scored": "scored", "runs_conceded": "conceded"})
        ui.chart(px.bar(m, x="season_year", y="runs", color="side", barmode="group", title=f"{focus}: runs scored vs conceded",
                        labels={"season_year": "Season", "runs": "Runs"}))
    with c2:
        m = ft.melt("season_year", ["wickets_taken", "wickets_lost"], var_name="side", value_name="wickets")
        m["side"] = m.side.map({"wickets_taken": "taken", "wickets_lost": "lost"})
        ui.chart(px.bar(m, x="season_year", y="wickets", color="side", barmode="group", title=f"{focus}: wickets taken vs lost",
                        labels={"season_year": "Season", "wickets": "Wickets"}))

    f = ui.apply(pm, seasons=seasons, teams=[focus])
    contrib = f.groupby("player").agg(points=("pts", "sum"), matches=("match_id", "nunique"), seasons=("season_year", "nunique")).reset_index()
    ev = R.evidence(f)
    ev["role"], _ = R.classify(ev, **th)
    contrib = contrib.merge(ev[["player", "role"]], on="player")
    contrib = contrib[ui.isin(contrib.role, role_f)]
    top = contrib.nlargest(15, "points").sort_values("points")
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(top, x="points", y="player", orientation="h", hover_data={"matches": True, "seasons": True}, color="role",
                     color_discrete_map=ui.role_colors(),
                     title=f"Top fantasy contributors for {focus} (statistical roles for matches with this team)",
                     labels={"points": "Total fantasy points", "player": ""})
        fig.update_yaxes(categoryorder="total ascending")
        ui.chart(None if top.empty else fig, height=460, empty="No contributors with the selected roles.")
    with c2:
        v = inn[(inn.batting_team == focus) & inn.season_year.between(*seasons)].groupby("venue").agg(
            innings=("match_id", "size"), avg_runs=("runs", "mean")).reset_index()
        v = v[v.innings >= 5].sort_values("avg_runs")
        ui.chart(None if v.empty else px.bar(v, x="avg_runs", y="venue", orientation="h", hover_data={"innings": True},
                                             title=f"{focus}: average innings total by venue (≥ 5 innings)", labels={"avg_runs": "Runs", "venue": ""}),
                 height=460, empty="Fewer than 5 innings at every venue in this range.")

    st.markdown("### Team comparison")
    cmp = t[ui.isin(t.team, teams)] if teams else t[t.team.isin(t.groupby("team").matches.sum().nlargest(4).index)]
    if not teams:
        st.caption("Showing the 4 teams with most matches in range — pick teams in the sidebar to compare others.")
    if cmp.team.nunique() > 8:
        keep = sorted(cmp.team.unique())[:8]
        st.warning("Colour stays distinguishable for up to 8 teams — showing the first 8 selected.")
        cmp = cmp[cmp.team.isin(keep)]
    c1, c2 = st.columns(2)
    with c1:
        ui.chart(px.line(cmp, x="season_year", y="run_rate", color="team", markers=True, title="Batting run rate",
                         labels={"season_year": "Season", "run_rate": "Runs per over"}))
    with c2:
        ui.chart(px.line(cmp, x="season_year", y="economy", color="team", markers=True, title="Bowling economy",
                         labels={"season_year": "Season", "economy": "Runs conceded per over"}))
    st.markdown("### Team-name normalization audit")
    ui.table(t[["season_year", "team", "original_names", "matches", "runs_scored", "wickets_taken", "run_rate", "economy"]].sort_values(
        ["team", "season_year"]).round(2), hide_index=True, width="stretch", height=360)
    ui.download(t, "team_season_stats")


ui.guard(main)
