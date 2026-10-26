import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from components import ui
from core import data as D

MAX_COMPARE = 4  # categorical palette stays distinguishable for up to 4 series in lines/boxes


def hero(name, p, players, teams, role):
    info = players.set_index("player").loc[name]
    spans, t = [], teams.sort_values("season_year")
    for r in t.itertuples():  # run-length group consecutive seasons with the same team
        if spans and spans[-1][2] == r.team and spans[-1][1] == r.season_year - 1:
            spans[-1][1] = r.season_year
        else:
            spans.append([r.season_year, r.season_year, r.team])
    spans = spans[::-1]
    team_chips = "".join(f"<span>{a}{'' if a == b else f'–{b}'} · {ui.esc(tm)}</span>" for a, b, tm in spans[:6])
    more = len(spans) - 6
    alias = f" · also recorded as {ui.esc(info.merged_aliases)}" if info.merged_aliases else ""
    stats = [("Matches", f"{p.match_id.nunique()}"), ("Avg points", f"{p.pts.mean():.1f}"), ("Best", f"{p.pts.max():.0f}"),
             ("Volatility (sd)", f"{p.pts.std(ddof=1):.1f}" if len(p) > 1 else "–")]
    st.markdown(f"""<div class="dl-hero"><div class="row">{ui.avatar_html(name)}<div>
        <h2>{ui.esc(name)}</h2>
        <div class="meta">Cricsheet id {ui.esc(info.registry_id)}{alias} · {ui.esc(role)} (statistical rule) ·
        {p.start_date.min():%b %Y} – {p.start_date.max():%b %Y}</div>
        <div class="chips">{team_chips}{f'<span>+{more} earlier spells</span>' if more > 0 else ''}</div></div></div>
        <div class="stats">{''.join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in stats)}</div></div>""",
                unsafe_allow_html=True)


def main():
    ui.header("Players", "Player explorer", "Every player in the verified data — profile, form, splits and side-by-side comparison.")
    pm, players, ts = D.player_match(), D.table("players.parquet"), D.table("player_team_seasons.parquet")
    players = players.sort_values(["matches", "player"], ascending=[False, True])
    label = {r.player: f"{r.player} · {r.matches} matches" for r in players.itertuples()}
    seasons = ui.season_filter(pm.season_year)
    opp = ui.multi("Opponent", pm.opponent.unique(), "f_opponents")
    ven = ui.multi("Venue", pm.venue.unique(), "f_venues")
    dmin, dmax = pm.start_date.min().date(), pm.start_date.max().date()
    dates = st.sidebar.date_input("Date range", value=st.session_state.get("f_dates", (dmin, dmax)), min_value=dmin, max_value=dmax, key="f_dates")

    c1, c2 = st.columns([2, 3])
    plist = list(players.player)
    name = c1.selectbox("Search player", plist, index=plist.index("V Kohli") if "V Kohli" in plist else 0,
                        format_func=lambda n: label[n], key="f_player")
    others = c2.multiselect(f"Compare with (up to {MAX_COMPARE - 1})", [n for n in players.player if n != name], max_selections=MAX_COMPARE - 1,
                            format_func=lambda n: label[n], key="f_compare", placeholder="Add players to compare")
    ui.active_filters(Player=name, Compare=others, Seasons=f"{seasons[0]}–{seasons[1]}", Opponent=opp, Venue=ven,
                      Dates=f"{dates[0]} → {dates[1]}" if len(dates) == 2 else None)

    f = ui.apply(pm, seasons=seasons, opponents=opp, venues=ven, dates=dates)
    p = f[f.player == name].sort_values("start_date")
    if p.empty:
        st.info(f"{name} has no matches under the current filters. Widen the season, date, opponent or venue filters.")
        return
    stt = D.player_stats(f)
    stt["role"] = D.classify(stt)
    role = stt.set_index("player").loc[name, "role"]
    hero(name, p, players, ts[ts.player == name], role)
    st.write("")

    me = stt.set_index("player").loc[name]
    elig = stt[stt.matches >= 10]
    rank = int((elig.avg_pts > me.avg_pts).sum() + 1) if name in set(elig.player) else None
    last5 = p.tail(5).pts.mean()
    ui.kpi_row([
        dict(label="Median points", value=f"{me.median_pts:.1f}", sub=f"mean {me.avg_pts:.1f}"),
        dict(label="Recent form", value=f"{last5:.1f}", sub=f"mean of last {min(5, len(p))} matches in view"),
        dict(label="Rank by average", value=f"#{rank} of {len(elig)}" if rank else "–", sub="players with ≥ 10 matches in view"),
        dict(label="Consistency (CV)", value=f"{me.cv:.2f}" if pd.notna(me.cv) else "–", sub="sd ÷ mean · lower = steadier"),
        dict(label="Batting", value=f"{int(me.runs):,} runs", sub=f"SR {me.strike_rate:.1f} · avg {me.bat_avg:.1f}" if pd.notna(me.bat_avg) else f"SR {me.strike_rate:.1f}" if pd.notna(me.strike_rate) else "did not bat"),
        dict(label="Bowling", value=f"{int(me.wickets)} wkts", sub=f"econ {me.economy:.2f} · {me.overs:.1f} overs" if pd.notna(me.economy) else "did not bowl"),
        dict(label="Points split", value=f"{100 * me.bat_pts / me.total_pts:.0f}% bat" if me.total_pts > 0 else "–",
             sub=f"bowling {100 * me.bowl_pts / me.total_pts:.0f}% · dots {100 * me.dot_pts / me.total_pts:.0f}%" if me.total_pts > 0 else ""),
        dict(label="Sample", value=f"{int(me.matches)} matches", sub=f"{int(me.seasons)} seasons · ⚠ small sample" if me.matches < 10 else f"{int(me.seasons)} seasons"),
    ])

    tabs = st.tabs(["Form", "Seasons", "Splits", "Matches", "Compare"])
    with tabs[0]:
        q = p.assign(n=range(1, len(p) + 1), date=p.start_date.dt.strftime("%d %b %Y"),
                     roll3=p.pts.rolling(3, min_periods=3).mean(), roll5=p.pts.rolling(5, min_periods=5).mean())
        fig = go.Figure()
        fig.add_bar(x=q.n, y=q.pts, name="Match points", marker_color=ui.series(0), opacity=0.5,
                    customdata=q[["date", "opponent", "venue"]], hovertemplate="%{customdata[0]}<br>%{y:.1f} pts vs %{customdata[1]}<br>%{customdata[2]}<extra></extra>")
        fig.add_scatter(x=q.n, y=q.roll3, name="3-match rolling mean", mode="lines", line=dict(color=ui.series(1), width=2), hoverinfo="skip")
        fig.add_scatter(x=q.n, y=q.roll5, name="5-match rolling mean", mode="lines", line=dict(color=ui.series(2), width=2), hoverinfo="skip")
        starts = q.groupby("season_year").n.min()
        fig.update_xaxes(tickvals=starts.values, ticktext=[str(y) for y in starts.index])
        fig.update_layout(title="Fantasy points by match (in order played)", xaxis_title="Season (ticks mark each season's first match in view)",
                          yaxis_title="Points", bargap=0.15, hovermode="x unified")
        ui.chart(fig, height=400)
        st.caption("Rolling means here include the current match (descriptive). Model features use only earlier matches.")
    with tabs[1]:
        se = p.groupby("season_year").agg(matches=("match_id", "nunique"), batting=("total_batting_points", "mean"),
                                          bowling=("wicket_points", "mean"), dots=("dot_ball_points", "mean"), team=("team", "first")).reset_index()
        m = se.melt(["season_year", "matches", "team"], ["batting", "bowling", "dots"], var_name="component", value_name="avg")
        ui.chart(px.bar(m, x="season_year", y="avg", color="component", title="Average points per match by season (stacked components)",
                        labels={"season_year": "Season", "avg": "Points per match"}, hover_data={"matches": True, "team": True}), height=380)
        st.dataframe(se.round(2), hide_index=True, width="stretch")
    with tabs[2]:
        c1, c2 = st.columns(2)
        for col, by in ((c1, "opponent"), (c2, "venue")):
            g = p.groupby(by).agg(matches=("match_id", "nunique"), avg_pts=("pts", "mean")).reset_index()
            g = g[g.matches >= 2].sort_values("avg_pts")
            with col:
                ui.chart(None if g.empty else px.bar(g.tail(12), x="avg_pts", y=by, orientation="h", hover_data={"matches": True},
                                                     title=f"Average points by {by} (≥ 2 matches)", labels={"avg_pts": "Points per match", by: ""}),
                         height=420, empty=f"Not enough matches per {by}.")
    with tabs[3]:
        cols = ["start_date", "season_year", "team", "opponent", "venue", "runs", "balls_faced", "fours", "sixes", "dismissal",
                "legal_balls", "runs_conceded", "wickets", "dots", "total_batting_points", "wicket_points", "dot_ball_points", "pts"]
        tbl = p[cols].sort_values("start_date", ascending=False)
        ui.paged(tbl, "pe_matches")
        ui.download(tbl, f"player_{name.replace(' ', '_')}_matches")
    with tabs[4]:
        names = [name] + others
        if len(names) == 1:
            st.info("Add players in **Compare with** above to see them on the same charts.")
        else:
            cp = f[f.player.isin(names)]
            se = cp.groupby(["player", "season_year"]).pts.mean().reset_index()
            ui.chart(px.line(se, x="season_year", y="pts", color="player", markers=True, category_orders={"player": names},
                             title="Average points per match by season", labels={"season_year": "Season", "pts": "Points per match"}))
            ui.chart(px.box(cp, x="player", y="pts", color="player", category_orders={"player": names}, points=False,
                            title="Distribution of match points", labels={"pts": "Points", "player": ""}))
            tb = stt[stt.player.isin(names)].set_index("player").loc[names][
                ["role", "matches", "avg_pts", "median_pts", "max_pts", "std_pts", "cv", "runs", "strike_rate", "wickets", "economy"]].round(2)
            st.dataframe(tb, width="stretch")
            ui.download(tb.reset_index(), "player_comparison", key="dl_cmp")


ui.guard(main)
