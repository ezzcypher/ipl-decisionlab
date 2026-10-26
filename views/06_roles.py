import numpy as np
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D
from core import roles as R


def main():
    ui.header("Players", "Batting · bowling · all-round",
              "Role-specific statistics. Roles are a transparent participation heuristic — the source data has no official role metadata.")
    pm = D.player_match()
    seasons = ui.season_filter(pm.season_year)
    teams = ui.multi("Team", pm.team.unique(), "f_teams", "Only matches played for these teams")
    th = R.thresholds()
    roles = ui.multi("Role", R.ROLES, "f_roles")
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Teams=teams, Roles=roles, **{"Min matches": th["min_matches"]})

    f = ui.apply(pm, seasons=seasons, teams=teams)
    if ui.empty_or(f):
        return
    s_all = R.add_roles(D.player_stats(f), f, th)
    s = s_all[ui.isin(s_all.role, roles)]
    ui.note(f"<b>Rule ({R.LABEL}).</b> {ui.esc(R.describe(th))} Fantasy points never decide the role. Wicketkeeping is not inferred.")
    cnt = s_all.role.value_counts()
    ui.kpi_row([dict(label=r, value=str(int(cnt.get(r, 0))), sub="players in view (before role filter)") for r in R.ROLES])
    if ui.empty_or(s, "No players with the selected roles."):
        return

    tb, tw, ta, tr, te = st.tabs(["Batting", "Bowling", "All-round", "Role distribution", "Evidence & thresholds"])
    q = s[s.matches >= th["min_matches"]]
    with tb:
        b = q[(q.balls_faced >= 60)].copy()
        if not ui.empty_or(b, "No player with ≥ 60 balls faced in view."):
            ui.chart(px.scatter(b, x="strike_rate", y="bat_avg", size="runs", color="role", color_discrete_map=ui.role_colors(), hover_name="player",
                                size_max=18, hover_data={"runs": ":,", "matches": True, "highest": True},
                                title="Batting average vs strike rate (size = runs; ≥ 60 balls faced)",
                                labels={"strike_rate": "Strike rate (runs per 100 balls)", "bat_avg": "Batting average (runs per dismissal)"}), height=440)
            cols = ["player", "role", "matches", "matches_batted", "runs", "balls_faced", "bat_avg", "strike_rate", "fours", "sixes", "boundary_pct", "highest", "bat_pts", "avg_pts", "cv"]
            ui.table(b.sort_values("runs", ascending=False)[cols], key="bat")
            ui.download(b[cols], "batting_stats", key="dl_bat")
            st.caption("Average needs ≥ 1 dismissal (blank otherwise). Balls faced exclude wides. Boundary % = runs from 4s and 6s ÷ runs.")
    with tw:
        w = q[q.legal_balls >= 60].copy()
        if not ui.empty_or(w, "No bowler with ≥ 10 overs in view."):
            ui.chart(px.scatter(w, x="economy", y="bowl_sr", size="wickets", color="role", color_discrete_map=ui.role_colors(), hover_name="player",
                                size_max=18, hover_data={"wickets": True, "overs": True, "dot_pct": ":.1f"},
                                title="Economy vs bowling strike rate (size = wickets; ≥ 10 overs)",
                                labels={"economy": "Economy (runs per over)", "bowl_sr": "Strike rate (balls per wicket)"}), height=440)
            cols = ["player", "role", "matches", "matches_bowled", "overs", "wickets", "runs_conceded", "economy", "bowl_avg", "bowl_sr", "dot_pct", "bowl_pts", "dot_pts", "avg_pts"]
            ui.table(w.sort_values("wickets", ascending=False)[cols], key="bowl")
            ui.download(w[cols], "bowling_stats", key="dl_bowl")
            st.caption("Runs conceded = runs off the bat + wides + no-balls (byes/leg-byes not charged). Wickets = credited dismissal types only.")
    with ta:
        a = q.assign(bat_ppm=q.bat_pts / q.matches, bowl_ppm=(q.bowl_pts + q.dot_pts) / q.matches)
        ui.chart(px.scatter(a, x="bat_ppm", y="bowl_ppm", color="role", color_discrete_map=ui.role_colors(), hover_name="player",
                            category_orders={"role": R.ROLES}, hover_data={"matches": True, "balls_faced_pm": ":.1f", "balls_bowled_pm": ":.1f"},
                            title="Batting vs bowling contribution (fantasy points per match)",
                            labels={"bat_ppm": "Batting points per match", "bowl_ppm": "Bowling + dot points per match"}), height=460)
        ar = a[a.role == "All-rounder"].sort_values("avg_pts", ascending=False)
        cols = ["player", "matches", "bat_share", "bowl_share", "balls_faced_pm", "balls_bowled_pm", "runs", "strike_rate", "wickets", "economy", "bat_ppm", "bowl_ppm", "avg_pts", "cv"]
        if not ui.empty_or(ar, "No statistical all-rounders under the current rule and filters."):
            ui.table(ar[cols], key="ar")
            ui.download(ar[cols], "allrounders", key="dl_ar")
            pick = st.selectbox("Match-by-match contribution", ar.player, key="f_ar_player")
            pp = f[f.player == pick].sort_values("start_date")
            m = pp.melt(["start_date"], ["total_batting_points", "wicket_points", "dot_ball_points"], var_name="component", value_name="points")
            m["component"] = m.component.map({"total_batting_points": "batting", "wicket_points": "wickets", "dot_ball_points": "dot balls"})
            ui.chart(px.bar(m, x="start_date", y="points", color="component", title=f"{pick}: points per match by component",
                            labels={"start_date": "Match date", "points": "Points"}), height=360)
    with tr:
        c1, c2 = st.columns(2)
        dist = s_all.role.value_counts().reindex(R.ROLES).fillna(0).rename_axis("role").reset_index(name="players")
        with c1:
            ui.chart(px.bar(dist, x="role", y="players", color="role", color_discrete_map=ui.role_colors(), text_auto=True,
                            title="Players per statistical role", labels={"role": "", "players": "Players"}), height=360)
        with c2:
            known = f.merge(s_all[["player", "role"]], on="player")
            ui.chart(px.box(known, x="role", y="pts", color="role", color_discrete_map=ui.role_colors(), points=False,
                            category_orders={"role": R.ROLES}, title="Fantasy points per match by role", labels={"role": "", "pts": "Points"}), height=360)
        per = known.groupby("role").agg(players=("player", "nunique"), matches=("match_id", "size"), avg_pts=("pts", "mean"),
                                        median_pts=("pts", "median"), batting=("total_batting_points", "mean"), bowling=("wicket_points", "mean"),
                                        dots=("dot_ball_points", "mean")).reindex(R.ROLES).dropna(how="all").reset_index()
        ui.table(per, key="role_perf", sort=False)
        st.caption("Role-based comparison of points per player-match. Roles come from participation, so differences in points are an outcome, not the rule.")
    with te:
        ev = R.evidence(f)
        c1, c2 = st.columns(2)
        with c1:
            sens = R.sensitivity(ev, th, "bowl_bpm", np.arange(0, 24.5, 1.5))
            ui.chart(px.line(sens, x="threshold", y="players", color="role", color_discrete_map=ui.role_colors(), markers=True,
                             title="How the bowling threshold changes roles", labels={"threshold": "Legal balls bowled per match ≥", "players": "Players"}), height=340)
        with c2:
            sens = R.sensitivity(ev, th, "bat_bpm", np.arange(0, 25.5, 1.5))
            ui.chart(px.line(sens, x="threshold", y="players", color="role", color_discrete_map=ui.role_colors(), markers=True,
                             title="How the batting threshold changes roles", labels={"threshold": "Balls faced per match ≥", "players": "Players"}), height=340)
        base, _ = R.classify(ev, **R.DEFAULTS)
        cur, _ = R.classify(ev, **th)
        changed = ev.assign(default_role=base, current_role=cur)[base != cur]
        st.markdown(f"**{len(changed)} players** have a different role under your thresholds than under the defaults.")
        if len(changed):
            ui.table(changed[["player", "matches", "default_role", "current_role", "balls_faced_pm", "balls_bowled_pm"]], key="changed")
        pick = st.selectbox("Inspect a player's classification", s_all.sort_values("matches", ascending=False).player, key="f_role_player")
        r = s_all.set_index("player").loc[pick]
        st.markdown(f"**{pick} → {r.role}** ({R.LABEL}) — {r.role_reason}.")
        ui.table([{"criterion": "Matches in view", "value": int(r.matches), "threshold": f"≥ {th['min_matches']}", "met": bool(r.matches >= th["min_matches"])},
                  {"criterion": "Share of matches batted", "value": round(r.bat_share, 3), "threshold": f"≥ {th['bat_share']:.2f}", "met": bool(r.bat_share >= th["bat_share"])},
                  {"criterion": "Balls faced per match", "value": round(r.balls_faced_pm, 2), "threshold": f"≥ {th['bat_bpm']:g}", "met": bool(r.balls_faced_pm >= th["bat_bpm"])},
                  {"criterion": "Share of matches bowled", "value": round(r.bowl_share, 3), "threshold": f"≥ {th['bowl_share']:.2f}", "met": bool(r.bowl_share >= th["bowl_share"])},
                  {"criterion": "Legal balls bowled per match", "value": round(r.balls_bowled_pm, 2), "threshold": f"≥ {th['bowl_bpm']:g}", "met": bool(r.balls_bowled_pm >= th["bowl_bpm"])}],
                 key="ev_tbl", sort=False)
        ui.download(s_all, "role_classification_evidence", key="dl_ev")


ui.guard(main)
