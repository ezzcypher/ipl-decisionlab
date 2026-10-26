import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D


def z(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd else s * 0


def main():
    ui.header("Decisions", "Selection & auction support",
              "Rank players on historical evidence with weights you control. A decision aid — not a guarantee of future returns.")
    pm, pr, mets = D.player_match(), D.predictions(), D.metrics()
    seasons = ui.season_filter(pm.season_year)
    roles = ui.multi("Role", ["Batter", "Bowler", "All-rounder", "Limited role"], "f_roles")
    teams = ui.multi("Latest team in view", pm.team.unique(), "f_teams")
    mm = ui.min_matches(15)
    with st.sidebar.expander("Ranking weights", expanded=True):
        w_avg = st.slider("Average points", 0.0, 1.0, 0.4, 0.05, key="f_w_avg")
        w_form = st.slider("Recent form (last 5)", 0.0, 1.0, 0.3, 0.05, key="f_w_form")
        w_cons = st.slider("Consistency (low CV)", 0.0, 1.0, 0.2, 0.05, key="f_w_cons")
        w_part = st.slider("Participation (matches)", 0.0, 1.0, 0.1, 0.05, key="f_w_part")
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Roles=roles, Teams=teams, **{"Min matches": mm})

    f = ui.apply(pm, seasons=seasons)
    s = D.player_stats(f)
    s["role"] = D.classify(s, min_matches=mm)
    form = f.sort_values("start_date").groupby("player").pts.apply(lambda x: x.tail(5).mean()).rename("form_last5")
    s = s.merge(form, on="player")
    s = s[(s.matches >= mm) & ui.isin(s.role, roles) & ui.isin(s.latest_team, teams)].copy()
    if ui.empty_or(s, "No players meet the filters. Lower the minimum matches or widen the seasons."):
        return
    s["cv_filled"] = s.cv.fillna(s.cv.max())
    s["score"] = w_avg * z(s.avg_pts) + w_form * z(s.form_last5) - w_cons * z(s.cv_filled) + w_part * z(s.matches)
    est = pr[pr.split == "test"].groupby("player")[mets["prediction_columns"]["Ridge regression"]].mean().rename("ridge_test_mean")
    s = s.merge(est, on="player", how="left").sort_values("score", ascending=False)
    s.insert(0, "rank", range(1, len(s) + 1))

    st.latex(r"\text{score} = %.2f\,z(\text{avg}) + %.2f\,z(\text{form}_5) - %.2f\,z(\text{CV}) + %.2f\,z(\text{matches})" % (w_avg, w_form, w_cons, w_part))
    st.caption("z(x) = (x − mean) ÷ sd across the players shown, so weights trade off comparable units. Higher CV = more volatile, so it is subtracted.")
    ui.note("<b>Auction decision-support prototype.</b> The data contains no auction prices, base prices, purses or availability, so this page "
            "shows no value-for-money metric. Upload a price file below to enable one — its source and season are shown alongside.")

    top = s.head(15)
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(top.sort_values("score"), x="score", y="player", color="role", orientation="h", color_discrete_map=ui.role_colors(),
                        hover_data={"avg_pts": ":.1f", "form_last5": ":.1f", "cv": ":.2f", "matches": True},
                     title="Top 15 by weighted score", labels={"score": "Weighted score (z units)", "player": ""})
        fig.update_yaxes(categoryorder="total ascending")
        ui.chart(fig, height=460)
    with c2:
        ui.chart(px.scatter(s, x="avg_pts", y="cv", color="role", hover_name="player", color_discrete_map=ui.role_colors(), size="matches", size_max=14,
                            title="Reward vs risk", labels={"avg_pts": "Average points", "cv": "Volatility (CV)"}), height=460)

    cols = ["rank", "player", "role", "latest_team", "score", "matches", "avg_pts", "form_last5", "cv", "ridge_test_mean", "median_pts", "std_pts", "max_pts"]
    edit = s[cols].round(2)
    edit.insert(0, "shortlist", False)
    st.markdown("### Ranked players · tick to shortlist")
    ed = st.data_editor(edit, hide_index=True, width="stretch", height=420, disabled=cols, key="f_shortlist_editor",
                        column_config={"ridge_test_mean": st.column_config.NumberColumn("Ridge mean (2024–26, retrospective)", format="%.1f",
                                                                                         help="Mean retrospective test prediction; blank if not in test period")})
    short = ed[ed.shortlist]
    c1, c2 = st.columns(2)
    with c1:
        ui.download(s[cols], "ranked_players", label="Download ranking CSV")
    with c2:
        if len(short):
            ui.download(short.drop(columns="shortlist"), "shortlist", label=f"Download shortlist ({len(short)})", key="dl_short")
        else:
            st.caption("Tick players to build a downloadable shortlist.")

    st.markdown("### Optional: your auction price data")
    up = st.file_uploader("CSV with columns player, price, season, source", type="csv", key="f_prices")
    if up is not None:
        try:
            p = pd.read_csv(up)
            need = {"player", "price", "season", "source"}
            if not need <= set(p.columns):
                st.error(f"Missing columns: {', '.join(sorted(need - set(p.columns)))}")
            else:
                v = s.merge(p, on="player", how="inner")
                v["points_per_price_unit"] = v.avg_pts / v.price.replace(0, np.nan)
                st.success(f"Matched {len(v)} of {len(p)} priced players. Prices as supplied by you; sources: {', '.join(map(str, p.source.unique()[:5]))}.")
                st.dataframe(v[["player", "season", "price", "source", "avg_pts", "points_per_price_unit"]].sort_values("points_per_price_unit", ascending=False),
                             hide_index=True, width="stretch")
        except Exception as e:  # noqa: BLE001 — bad user file
            st.error(f"Could not read the file: {e}")


ui.guard(main)
