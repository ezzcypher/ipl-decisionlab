"""IPL DecisionLab — rebuilt Phase 2 / 4 / 3 pipeline (recovery workspace).

Reads pipeline/inputs (raw Cricsheet ZIP + recovered originals), writes *_rebuilt files to pipeline/rebuilt.
Usage (from the repo root): python3 -I pipeline/src/rebuild.py
"""
import json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
INP, OUT = ROOT / "inputs", ROOT / "rebuilt"

PLAYER_COLS = ["striker", "non_striker", "bowler", "player_dismissed"]
ALIASES = {"Arshad Khan (2)": "Arshad Khan"}  # Harmeet Singh (2) deliberately NOT merged (unresolved)
TEAM_MAP = {
    "Royal Challengers Bangalore": "Royal Challengers Bengaluru",
    "Kings XI Punjab": "Punjab Kings",
    "Delhi Daredevils": "Delhi Capitals",
    "Rising Pune Supergiant": "Rising Pune Supergiants",
}
SEASON_MAP = {"2007/08": 2008, "2009/10": 2010, "2020/21": 2020}  # all other labels are already the year
BOWLER_WICKETS = ["caught", "bowled", "lbw", "stumped", "caught and bowled", "hit wicket"]


def load_raw():
    with zipfile.ZipFile(INP / "ipl_male_csv2.zip") as z:
        return pd.read_csv(z.open("all_matches.csv"), low_memory=False)


def phase2(raw, venue_map):
    df = raw[raw["innings"] <= 2].copy()  # drop super overs
    df["venue"] = df["venue"].replace(venue_map)
    for c in PLAYER_COLS:
        df[c] = df[c].replace(ALIASES)
    df["start_date"] = pd.to_datetime(df["start_date"])
    df = df.sort_values(["start_date", "match_id", "innings", "ball"], kind="stable").reset_index(drop=True)
    df["date_year"] = df["start_date"].dt.year
    return df


def phase4(p2):
    df = p2.copy()
    df["batting_team_std"] = df["batting_team"].replace(TEAM_MAP)
    df["bowling_team_std"] = df["bowling_team"].replace(TEAM_MAP)
    return df


def phase3(p2, dot_pts=0.5, bonuses=True, roster_cols=PLAYER_COLS):
    """Original scoring by default (verified against recovered Phase 3). No fielding points.
    Non-default args exist only to replay the flawed reconstruction for the discrepancy audit."""
    keys = ["match_id", "start_date", "venue", "season"]
    bat = p2.groupby(["match_id", "striker"]).agg(
        runs=("runs_off_bat", "sum"),
        f4=("runs_off_bat", lambda s: (s == 4).sum()),
        f6=("runs_off_bat", lambda s: (s == 6).sum()),
    )
    bat.index.names = ["match_id", "player"]
    outs = p2.dropna(subset=["player_dismissed"]).groupby(["match_id", "player_dismissed"]).size()
    outs.index.names = ["match_id", "player"]
    bat["out"] = outs.reindex(bat.index).fillna(0)
    r = bat["runs"]
    bat["total_batting_points"] = (
        r + bat["f4"] + 2 * bat["f6"]
        + bonuses * (4 * (r >= 30) + 8 * (r >= 50) + 16 * (r >= 100) - 2 * ((r == 0) & (bat["out"] > 0)))
    )
    wk = p2[p2["wicket_type"].isin(BOWLER_WICKETS)].groupby(["match_id", "bowler"]).size() * 25
    legal = p2[p2["wides"].isna()]
    dots = legal[(legal["runs_off_bat"] == 0) & (legal["extras"] == 0)].groupby(["match_id", "bowler"]).size() * dot_pts
    for s in (wk, dots):
        s.index.names = ["match_id", "player"]

    # Player universe: everyone named in a player column of the match
    roster = pd.concat([p2[["match_id", c]].rename(columns={c: "player"}) for c in roster_cols]).dropna().drop_duplicates()
    pm = roster.merge(p2[keys].drop_duplicates("match_id"), on="match_id").set_index(["match_id", "player"])
    pm["total_batting_points"] = bat["total_batting_points"].reindex(pm.index).fillna(0).astype(float)
    pm["wicket_points"] = wk.reindex(pm.index).fillna(0).astype(float)
    pm["dot_ball_points"] = dots.reindex(pm.index).fillna(0).astype(float)
    pm["pts"] = pm[["total_batting_points", "wicket_points", "dot_ball_points"]].sum(axis=1)
    pm = pm.reset_index()
    pm["start_date"] = pm["start_date"].dt.strftime("%Y-%m-%d")
    cols = ["match_id", "start_date", "venue", "season", "player",
            "total_batting_points", "wicket_points", "dot_ball_points", "pts"]
    return pm[cols].sort_values(["start_date", "match_id", "player"], kind="stable").reset_index(drop=True)


def recover_venue_map(raw, p2_orig):
    """Raw venue -> venue used in the recovered Phase 2, joined on match_id.
    Provenance: derived FROM the recovered Phase 2 (no original mapping code survives)."""
    j = raw[["match_id", "venue"]].drop_duplicates().merge(
        p2_orig[["match_id", "venue"]].drop_duplicates(), on="match_id", suffixes=("_raw", "_p3"))
    per_raw = j.groupby("venue_raw")["venue_p3"].nunique()
    assert (per_raw == 1).all(), f"non-functional venue mapping: {per_raw[per_raw > 1].to_dict()}"
    return dict(j.drop_duplicates("venue_raw").set_index("venue_raw")["venue_p3"].pipe(lambda s: s[s.index != s.values]))


def registry_ids():
    """Cricsheet registry id(s) for every player name, from the *_info.csv files in the raw ZIP."""
    import collections
    ids = collections.defaultdict(set)
    with zipfile.ZipFile(INP / "ipl_male_csv2.zip") as z:
        for n in z.namelist():
            if n.endswith("_info.csv"):
                for line in z.read(n).decode().splitlines():
                    if line.startswith("info,registry,people,"):
                        name, pid = line[len("info,registry,people,"):].rsplit(",", 1)
                        ids[name].add(pid)
    return ids


# v1.1 identity fixes: each pair must share one Cricsheet registry id (checked in identity_map_v11).
IDENTITY_V11_PAIRS = [("NA Saini", "Navdeep Saini"), ("S Arora", "Salil Arora")]


def identity_map_v11(p2):
    """alias -> canonical (canonical = name with more deliveries). Raises unless registry ids match
    and the two names never appear in the same match."""
    ids = registry_ids()
    named = pd.concat([p2[["match_id", c]].rename(columns={c: "player"}) for c in PLAYER_COLS]).dropna()
    counts = named["player"].value_counts()
    out, evidence = {}, []
    for a, b in IDENTITY_V11_PAIRS:
        assert len(ids[a]) == 1 and ids[a] == ids[b], f"registry mismatch {a}:{ids[a]} {b}:{ids[b]}"
        both = set(named.loc[named.player == a, "match_id"]) & set(named.loc[named.player == b, "match_id"])
        assert not both, f"{a} and {b} both appear in matches {both}"
        canon, alias = (a, b) if counts[a] >= counts[b] else (b, a)
        out[alias] = canon
        evidence.append({"alias": alias, "canonical": canon, "registry_id": next(iter(ids[a])),
                         "deliveries_named": {a: int(counts[a]), b: int(counts[b])},
                         "matches": {n: int(named.loc[named.player == n, "match_id"].nunique()) for n in (a, b)},
                         "co_occurring_matches": 0})
    return out, evidence


def delivery_order(raw, venue_map):
    """Derived dataset: corrected within-over delivery order, linked to Phase 2 rows and raw rows.
    The source writes deliveries as '<over>.<n>' with n counting EVERY delivery in the over (wides and
    no-balls included); pandas reads '6.10' as 6.1, which is the collision. Original columns untouched."""
    with zipfile.ZipFile(INP / "ipl_male_csv2.zip") as z:
        text = pd.read_csv(z.open("all_matches.csv"), usecols=["ball"], dtype={"ball": str})["ball"]
    p2 = phase2(raw.assign(raw_row=range(len(raw)), ball_text=text), venue_map)
    d = p2[["raw_row", "match_id", "innings", "ball", "ball_text", "actual_delivery", "wides", "noballs"]].copy()
    d.insert(0, "p2_row", d.index)
    parts = d["ball_text"].str.split(".", expand=True)
    d["over"] = parts[0].astype(int)
    d["delivery_in_over"] = parts[1].astype(int)
    d["is_wide"] = d["wides"].notna()
    d["is_noball"] = d["noballs"].notna()
    d["is_legal"] = ~(d["is_wide"] | d["is_noball"])
    d = d.drop(columns=["wides", "noballs"])
    order = d.sort_values(["match_id", "innings", "over", "delivery_in_over"], kind="stable")
    order["delivery_seq"] = order.groupby(["match_id", "innings"]).cumcount() + 1
    order["legal_balls_in_over_so_far"] = order.groupby(["match_id", "innings", "over"])["is_legal"].cumsum()
    return order.sort_values("p2_row").reset_index(drop=True)


def phase5(pm):
    """Feature definitions recovered by replay against the recovered Phase 5 (all strictly from earlier matches)."""
    f = pm.sort_values(["player", "start_date", "match_id"], kind="stable").reset_index(drop=True)
    g = f.groupby("player")["pts"]
    prev = g.shift(1)
    roll = lambda w, fn: prev.groupby(f["player"]).transform(lambda s: s.rolling(w, min_periods=w).apply(fn, raw=True))
    f["prev_pts"] = prev
    f["avg_pts_prev3"] = roll(3, np.mean)
    f["avg_pts_prev5"] = roll(5, np.mean)
    f["std_pts_prev3"] = roll(3, np.std)  # population std (ddof=0), as in the original
    f["trend_pts_prev3"] = f["avg_pts_prev3"] - f["avg_pts_prev5"]
    f["matches_before"] = g.cumcount()
    return f


def main():
    OUT.mkdir(exist_ok=True)
    raw = load_raw()
    # Venue mapping: recovered from the original Phase 2 output when it is available (45 MB, not in the repo);
    # otherwise the committed copy of that same mapping (pipeline/config/venue_map.json) is used.
    orig_p2, saved = INP / "IPL_DecisionLab_Phase2_Cleaned.csv", ROOT / "config" / "venue_map.json"
    if orig_p2.exists():
        vmap = recover_venue_map(raw, pd.read_csv(orig_p2, usecols=["match_id", "venue"]))
        if saved.exists():
            assert vmap == json.loads(saved.read_text()), "recovered venue map differs from config/venue_map.json"
    else:
        vmap = json.loads(saved.read_text())
    (OUT / "venue_map_rebuilt.json").write_text(json.dumps(vmap, indent=2, sort_keys=True))
    p2 = phase2(raw, vmap)
    p2.to_csv(OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv", index=False)
    phase4(p2).to_csv(OUT / "IPL_DecisionLab_Team_Standardized_rebuilt.csv", index=False)
    phase3(p2).to_csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_rebuilt.csv", index=False)

    # --- Step 4: v1.1 identity, delivery order, Phase 5 ---
    imap, evidence = identity_map_v11(p2)
    (OUT / "identity_map_v1.1_rebuilt.json").write_text(json.dumps({"applied_on_top_of_v1": ALIASES, "v1.1_additions": imap,
                                                                     "evidence": evidence}, indent=2))
    p2v11 = p2.copy()
    for c in PLAYER_COLS:
        p2v11[c] = p2v11[c].replace(imap)
    p3v11 = phase3(p2v11)
    p3v11.to_csv(OUT / "IPL_DecisionLab_Phase3_PlayerMatch_Points_v1.1_rebuilt.csv", index=False)
    delivery_order(raw, vmap).to_csv(OUT / "IPL_DecisionLab_Phase2_DeliveryOrder_rebuilt.csv", index=False)
    f = phase5(p3v11)
    f["season_year"] = f["season"].astype(str).map(lambda s: SEASON_MAP.get(s) or int(s))
    f.to_csv(OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv", index=False)
    print("rebuilt:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
