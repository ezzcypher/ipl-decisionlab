import plotly.express as px
import streamlit as st
from components import ui
from core import data as D

ROLES = ["Batter", "Bowler", "All-rounder", "Limited role", "Insufficient sample"]


def main():
    ui.header("Players", "Batting · bowling · all-round",
              "Role-specific statistics. Roles come from a transparent participation rule — the source data has no role metadata.")
    pm = D.player_match()
    seasons = ui.season_filter(pm.season_year)
    teams = ui.multi("Team", pm.team.unique(), "f_teams", "Only matches played for these teams")
    mm = ui.min_matches(20)
    with st.sidebar.expander("Classification rule", expanded=True):
        bat = st.slider("Bats regularly: balls faced per match ≥", 2.0, 20.0, 8.0, 0.5, key="f_bat_bpm")
        bowl = st.slider("Bowls regularly: legal balls per match ≥", 3.0, 24.0, 9.0, 0.5, key="f_bowl_bpm")
    roles = ui.multi("Role", ROLES, "f_roles")
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Teams=teams, **{"Min matches": mm, "Bat ≥": bat, "Bowl ≥": bowl}, Roles=roles)

    f = ui.apply(pm, seasons=seasons, teams=teams)
    s = D.player_stats(f)
    s["role"] = D.classify(s, bat, bowl, mm)
    s = s[ui.isin(s.role, roles)]
    if ui.empty_or(s):
        return
    ui.note(f"<b>Rule.</b> Batter: ≥ {bat:g} balls faced per match and &lt; {bowl:g} legal balls bowled per match. Bowler: the reverse. "
            f"All-rounder: both. Limited role: neither. Players with &lt; {mm} matches in view are <i>Insufficient sample</i>. "
            "Fantasy points never decide the role.")
    cnt = s.role.value_counts()
    ui.kpi_row([dict(label=r, value=str(int(cnt.get(r, 0))), sub="players in view") for r in ROLES[:4]])

    tb, tw, ta, te = st.tabs(["Batting", "Bowling", "All-round", "Evidence"])
    q = s[s.matches >= mm]
    with tb:
        b = q[q.innings_batted > 0].copy()
        b = b[b.role.isin(["Batter", "All-rounder"]) | (b.balls_faced >= 100)]
        if not ui.empty_or(b):
            ui.chart(px.scatter(b, x="strike_rate", y="bat_avg", size="runs", color="role", color_discrete_map=ui.role_colors(), hover_name="player", size_max=18,
                                hover_data={"runs": ":,", "matches": True, "highest": True},
                                title="Batting average vs strike rate (size = runs)", labels={"strike_rate": "Strike rate (runs per 100 balls)",
                                                                                              "bat_avg": "Batting average (runs per dismissal)"}), height=440)
            cols = ["player", "role", "matches", "runs", "balls_faced", "bat_avg", "strike_rate", "fours", "sixes", "boundary_pct", "highest", "bat_pts", "avg_pts", "cv"]
            ui.paged(b.sort_values("runs", ascending=False)[cols].round(2), "bat")
            ui.download(b[cols], "batting_stats", key="dl_bat")
            st.caption("Average needs ≥ 1 dismissal (blank otherwise). Balls faced exclude wides. Boundary % = runs from 4s and 6s ÷ runs.")
    with tw:
        w = q[q.legal_balls >= 60].copy()
        if not ui.empty_or(w, "No bowler with ≥ 10 overs in view."):
            ui.chart(px.scatter(w, x="economy", y="bowl_sr", size="wickets", color="role", color_discrete_map=ui.role_colors(), hover_name="player", size_max=18,
                                hover_data={"wickets": True, "overs": True, "dot_pct": ":.1f"},
                                title="Economy vs bowling strike rate (size = wickets; ≥ 10 overs)",
                                labels={"economy": "Economy (runs per over)", "bowl_sr": "Strike rate (balls per wicket)"}), height=440)
            cols = ["player", "role", "matches", "overs", "wickets", "runs_conceded", "economy", "bowl_avg", "bowl_sr", "dot_pct", "bowl_pts", "dot_pts", "avg_pts"]
            ui.paged(w.sort_values("wickets", ascending=False)[cols].round(2), "bowl")
            ui.download(w[cols], "bowling_stats", key="dl_bowl")
            st.caption("Runs conceded = runs off the bat + wides + no-balls (byes/leg-byes not charged). Wickets = credited dismissal types only.")
    with ta:
        a = q.assign(bat_ppm=q.bat_pts / q.matches, bowl_ppm=(q.bowl_pts + q.dot_pts) / q.matches)
        ui.chart(px.scatter(a, x="bat_ppm", y="bowl_ppm", color="role", color_discrete_map=ui.role_colors(), hover_name="player", category_orders={"role": ROLES},
                            hover_data={"matches": True, "balls_faced_pm": ":.1f", "balls_bowled_pm": ":.1f"},
                            title="Batting vs bowling contribution (fantasy points per match)",
                            labels={"bat_ppm": "Batting points per match", "bowl_ppm": "Bowling + dot points per match"}), height=460)
        ar = a[a.role == "All-rounder"].sort_values("avg_pts", ascending=False)
        cols = ["player", "matches", "balls_faced_pm", "balls_bowled_pm", "runs", "strike_rate", "wickets", "economy", "bat_ppm", "bowl_ppm", "avg_pts", "cv"]
        if not ui.empty_or(ar, "No all-rounders under the current rule and filters."):
            st.dataframe(ar[cols].round(2), hide_index=True, width="stretch")
            ui.download(ar[cols], "allrounders", key="dl_ar")
            pick = st.selectbox("Match-by-match contribution", ar.player, key="f_ar_player")
            pp = f[f.player == pick].sort_values("start_date")
            m = pp.melt(["start_date"], ["total_batting_points", "wicket_points", "dot_ball_points"], var_name="component", value_name="points")
            m["component"] = m.component.map({"total_batting_points": "batting", "wicket_points": "wickets", "dot_ball_points": "dot balls"})
            ui.chart(px.bar(m, x="start_date", y="points", color="component", title=f"{pick}: points per match by component",
                            labels={"start_date": "Match date", "points": "Points"}), height=360)
    with te:
        pick = st.selectbox("Inspect a player's classification", s.sort_values("matches", ascending=False).player, key="f_role_player")
        r = s.set_index("player").loc[pick]
        st.markdown(f"**{pick} → {r.role}**")
        st.dataframe([{"criterion": "Balls faced per match", "value": round(r.balls_faced_pm, 2), "threshold": f"≥ {bat:g}", "met": bool(r.balls_faced_pm >= bat)},
                      {"criterion": "Legal balls bowled per match", "value": round(r.balls_bowled_pm, 2), "threshold": f"≥ {bowl:g}", "met": bool(r.balls_bowled_pm >= bowl)},
                      {"criterion": "Matches in view", "value": int(r.matches), "threshold": f"≥ {mm}", "met": bool(r.matches >= mm)}],
                     hide_index=True, width="stretch")
        ui.download(s, "role_classification_evidence", key="dl_ev")


ui.guard(main)
