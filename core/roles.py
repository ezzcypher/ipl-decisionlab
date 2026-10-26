"""Statistical (heuristic) role classification — the source data has no official role metadata.

A player "bats regularly" when they faced a ball in at least `bat_share` of their matches AND faced at least
`bat_bpm` balls per match; "bowls regularly" likewise with legal balls bowled. Fantasy points are never used.
Batter = bats only · Bowler = bowls only · All-rounder = both · Unknown = neither, or fewer than `min_matches`.
Wicketkeeping is not inferred.
"""
import pandas as pd
import streamlit as st

ROLES = ["Batter", "Bowler", "All-rounder", "Unknown"]
DEFAULTS = dict(min_matches=10, bat_share=0.5, bat_bpm=8.0, bowl_share=0.5, bowl_bpm=9.0)
LABEL = "statistical role (heuristic, not official)"


def evidence(pm):
    """Participation evidence per player from player-match rows (respects upstream filters)."""
    g = pm.groupby("player")
    e = g.agg(matches=("match_id", "nunique"), matches_batted=("balls_faced", lambda s: int((s > 0).sum())),
              matches_bowled=("legal_balls", lambda s: int((s > 0).sum())), balls_faced=("balls_faced", "sum"),
              legal_balls=("legal_balls", "sum")).reset_index()
    e["bat_share"] = e.matches_batted / e.matches
    e["bowl_share"] = e.matches_bowled / e.matches
    e["balls_faced_pm"] = e.balls_faced / e.matches
    e["balls_bowled_pm"] = e.legal_balls / e.matches
    return e


def classify(ev, min_matches=10, bat_share=0.5, bat_bpm=8.0, bowl_share=0.5, bowl_bpm=9.0):
    """Returns (role, reason) Series aligned with `ev`."""
    bats = (ev.bat_share >= bat_share) & (ev.balls_faced_pm >= bat_bpm)
    bowls = (ev.bowl_share >= bowl_share) & (ev.balls_bowled_pm >= bowl_bpm)
    role = pd.Series("Unknown", index=ev.index)
    role[bats & ~bowls] = "Batter"
    role[bowls & ~bats] = "Bowler"
    role[bats & bowls] = "All-rounder"
    few = ev.matches < min_matches
    role[few] = "Unknown"
    reason = pd.Series("", index=ev.index)
    reason[few] = "fewer than " + str(min_matches) + " matches"
    reason[~few & ~bats & ~bowls] = "neither batting nor bowling meets the thresholds"
    reason[~few & bats & ~bowls] = "bats regularly; bowling below threshold"
    reason[~few & bowls & ~bats] = "bowls regularly; batting below threshold"
    reason[~few & bats & bowls] = "both batting and bowling meet the thresholds"
    return role, reason


def add_roles(stats, pm, th):
    ev = evidence(pm)
    ev["role"], ev["role_reason"] = classify(ev, **th)
    return stats.merge(ev[["player", "matches_batted", "matches_bowled", "bat_share", "bowl_share", "role", "role_reason"]], on="player", how="left")


def thresholds(where=None):
    """Shared, configurable thresholds (same session keys on every page)."""
    box = (where or st.sidebar).expander("Role rule (heuristic)", expanded=False)
    with box:
        th = dict(
            min_matches=int(st.number_input("Minimum matches", 1, 100, st.session_state.get("f_role_min", DEFAULTS["min_matches"]), key="f_role_min")),
            bat_share=st.slider("Batted in ≥ share of matches", 0.0, 1.0, st.session_state.get("f_role_bshare", DEFAULTS["bat_share"]), 0.05, key="f_role_bshare"),
            bat_bpm=st.slider("Balls faced per match ≥", 0.0, 25.0, st.session_state.get("f_role_bbpm", DEFAULTS["bat_bpm"]), 0.5, key="f_role_bbpm"),
            bowl_share=st.slider("Bowled in ≥ share of matches", 0.0, 1.0, st.session_state.get("f_role_wshare", DEFAULTS["bowl_share"]), 0.05, key="f_role_wshare"),
            bowl_bpm=st.slider("Legal balls bowled per match ≥", 0.0, 24.0, st.session_state.get("f_role_wbpm", DEFAULTS["bowl_bpm"]), 0.5, key="f_role_wbpm"),
        )
        st.caption("Heuristic from participation only — not official roles. Wicketkeeping is not inferred.")
    return th


def describe(th):
    return (f"Batter: batted in ≥ {th['bat_share']:.0%} of matches and ≥ {th['bat_bpm']:g} balls faced per match. "
            f"Bowler: bowled in ≥ {th['bowl_share']:.0%} of matches and ≥ {th['bowl_bpm']:g} legal balls per match. "
            f"All-rounder: both. Unknown: neither, or fewer than {th['min_matches']} matches.")


def sensitivity(ev, th, param, values):
    rows = []
    for v in values:
        r, _ = classify(ev, **{**th, param: v})
        c = r.value_counts()
        rows += [{"threshold": v, "role": k, "players": int(c.get(k, 0))} for k in ROLES]
    return pd.DataFrame(rows)
