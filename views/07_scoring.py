import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D
from core import scoring


@st.cache_data(show_spinner=False)
def reconcile(pm):
    r = pm.apply(lambda x: scoring.score(x.runs, x.fours, x.sixes, x.batted, x.dismissed, x.wickets, x.dots)["total"], axis=1)
    return int(np.isclose(r, pm.pts).sum()), len(pm)


def breakdown(r):
    b = scoring.score(r.runs, r.fours, r.sixes, r.batted, r.dismissed, r.wickets, r.dots)
    rows = []
    if r.batted:
        rows += [("Runs off the bat", f"{r.runs} × 1", r.runs), ("Fours bonus", f"{r.fours} × 1", r.fours), ("Sixes bonus", f"{r.sixes} × 2", 2 * r.sixes)]
        for t, pts in ((30, 4), (50, 8), (100, 16)):
            if r.runs >= t:
                rows.append((f"{t}-run milestone", "stacks", pts))
        if r.runs == 0 and r.dismissed:
            rows.append(("Duck penalty", f"out for 0 ({r.dismissal})", -2))
    else:
        rows.append(("Batting", "did not face a ball", 0))
    rows += [("Credited wickets", f"{r.wickets} × 25", 25 * r.wickets), ("Dot balls bowled", f"{r.dots} × 0.5", 0.5 * r.dots)]
    df = pd.DataFrame(rows, columns=["item", "calculation", "points"])
    return df, b


def main():
    ui.header("Fantasy scoring", "Fantasy points calculator & methodology",
              f"Exactly how every player-match score is calculated — scoring {scoring.VERSION}. No fielding points in this version.")
    pm = D.player_match()
    ok, n = reconcile(pm)
    ui.kpi_row([
        dict(label="Rows reproduced", value=f"{ok:,} / {n:,}", tag="live check", sub="this page's formula vs stored points"),
        dict(label="Batting component", value="runs + bonuses", sub="+1/run · +1/four · +2/six · 4/8/16 milestones · −2 duck"),
        dict(label="Bowling component", value="25 / wicket", sub="credited dismissal types only"),
        dict(label="Dot-ball component", value="0.5 / dot", sub="legal-for-batting ball, 0 runs, 0 extras"),
    ])
    st.latex(r"\text{Total} = \underbrace{R + F + 2S + 4[R\ge30] + 8[R\ge50] + 16[R\ge100] - 2[\text{duck}]}_{\text{batting}}"
             r" + \underbrace{25W}_{\text{bowling}} + \underbrace{0.5D}_{\text{dot balls}}")
    st.caption("R runs off the bat, F fours, S sixes, W credited wickets, D dot balls. [x] = 1 if true, else 0.")

    t1, t2, t3, t4 = st.tabs(["Rules", "Worked example", "Match breakdown", "Calculator"])
    with t1:
        ui.table(pd.DataFrame(scoring.RULES, columns=["component", "rule", "points", "condition"]), hide_index=True, width="stretch")
        ui.note("<b>Plain-language notes.</b><br>• Milestones <b>stack</b>: a century earns 4 + 8 + 16 = 28 bonus points.<br>"
                "• A <b>duck</b> needs three things: the player faced at least one delivery as striker, scored 0, and is recorded as dismissed — "
                "in any mode, including run out and retired. A non-striker run out without facing a ball gets no penalty.<br>"
                "• <b>Wickets</b> count only for: " + ", ".join(scoring.CREDITED_WICKETS) + ". Not credited: " + ", ".join(scoring.NOT_CREDITED) + ".<br>"
                "• A <b>dot ball</b> is any delivery that is not a wide, with 0 runs off the bat and 0 extras. Wides never count; no-balls always "
                "carry an extra, so they never count either; byes and leg-byes are not dots.<br>"
                "• Balls faced exclude wides. Super-over deliveries are excluded before scoring.")
        ui.download(pd.DataFrame(scoring.RULES, columns=["component", "rule", "points", "condition"]), "scoring_rules_v1", key="dl_rules")
        st.markdown("**Separate versions.** Any alternative system (e.g. with fielding points) must be added as a new version beside v1 — v1 is never edited.")
    with t2:
        ex = pm[(pm.match_id == 335982) & (pm.player == "BB McCullum")]
        if not ui.empty_or(ex, "Worked-example record not found."):
            r = ex.iloc[0]
            st.markdown(f"**BB McCullum, {r.start_date:%d %b %Y}, {r.team} vs {r.opponent}, {r.venue}** — a real record from the dataset.")
            st.markdown(ui.chips([f"{r.runs} runs", f"{r.balls_faced} balls", f"{r.fours} fours", f"{r.sixes} sixes",
                                  "not out" if not r.dismissed else f"out ({r.dismissal})", f"{r.legal_balls} balls bowled"]), unsafe_allow_html=True)
            df, b = breakdown(r)
            ui.table(df, hide_index=True, width="stretch")
            st.markdown(f"**Total = {b['batting']:g} batting + {b['bowling']:g} bowling + {b['dot']:g} dots = {b['total']:g} points** "
                        f"(stored value: {r.pts:g} ✓)" if np.isclose(b["total"], r.pts) else f"⚠ mismatch with stored {r.pts}")
    with t3:
        players = pm.groupby("player").match_id.nunique().sort_values(ascending=False)
        c1, c2 = st.columns(2)
        who = c1.selectbox("Player", players.index, key="f_sc_player")
        mt = pm[pm.player == who].sort_values("start_date", ascending=False)
        mid = c2.selectbox("Match", mt.match_id, format_func=lambda m: f"{mt.set_index('match_id').loc[m, 'start_date']:%d %b %Y} vs "
                                                                         f"{mt.set_index('match_id').loc[m, 'opponent']}", key="f_sc_match")
        r = mt[mt.match_id == mid].iloc[0]
        df, b = breakdown(r)
        c1, c2 = st.columns([3, 2])
        with c1:
            ui.table(df, hide_index=True, width="stretch")
            st.markdown(f"**{b['total']:g} points** · stored {r.pts:g} {'✓' if np.isclose(b['total'], r.pts) else '⚠'}")
            ui.download(df.assign(player=who, match_id=mid), f"score_breakdown_{who.replace(' ', '_')}_{mid}", key="dl_bd")
        with c2:
            comp = pd.DataFrame({"component": ["batting", "bowling", "dot balls"], "points": [b["batting"], b["bowling"], b["dot"]]})
            ui.chart(px.bar(comp, x="component", y="points", title="Components", labels={"component": "", "points": "Points"}), height=280)
    with t4:
        st.markdown("Enter a performance to see how it scores under v1.")
        c = st.columns(4)
        runs = c[0].number_input("Runs off the bat", 0, 250, 54, key="f_calc_runs")
        fours = c[1].number_input("Fours", 0, 40, 5, key="f_calc_4")
        sixes = c[2].number_input("Sixes", 0, 30, 2, key="f_calc_6")
        out = c[3].checkbox("Dismissed", True, key="f_calc_out")
        c = st.columns(4)
        batted = c[0].checkbox("Faced at least one ball", True, key="f_calc_batted")
        wk = c[1].number_input("Credited wickets", 0, 10, 1, key="f_calc_w")
        dots = c[2].number_input("Dot balls bowled", 0, 24, 8, key="f_calc_d")
        if 4 * fours + 6 * sixes > runs:
            st.warning("Boundaries add up to more runs than entered — check the inputs.")
        r = pd.Series(dict(runs=runs, fours=fours, sixes=sixes, batted=batted, dismissed=out, wickets=wk, dots=dots, dismissal="dismissed"))
        df, b = breakdown(r)
        ui.table(df, hide_index=True, width="stretch")
        st.markdown(f"### {b['total']:g} points")


ui.guard(main)
