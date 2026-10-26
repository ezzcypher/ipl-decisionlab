"""IPL DecisionLab — recovery audits (all statuses computed, nothing hard-coded).

Writes to ../reports. Usage: python3 -I src/audits.py
"""
import json, zipfile, hashlib, collections, datetime, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rebuild as rb

REP = rb.ROOT / "reports"
KEY = ["match_id", "innings", "ball"]
PM = ["match_id", "player"]


def raw_ball_strings():
    """Ball numbers exactly as written in all_matches.csv (pandas parses '6.10' as 6.1)."""
    with zipfile.ZipFile(rb.INP / "ipl_male_csv2.zip") as z:
        return pd.read_csv(z.open("all_matches.csv"), usecols=["match_id", "innings", "ball"], dtype={"ball": str})["ball"]


def duplicate_key_audit(raw):
    df = raw.assign(ball_text=raw_ball_strings(), raw_row=range(len(raw)))
    df = df[df["innings"] <= 2]
    d = df[df.duplicated(KEY, keep=False)].copy()
    d["over"] = d["ball"].astype(int)
    over_len = df.assign(over=df["ball"].astype(int)).groupby(["match_id", "innings", "over"]).size().rename("deliveries_in_over")
    d = d.join(over_len, on=["match_id", "innings", "over"])
    d["ball_text_collides"] = d.groupby(KEY)["ball_text"].transform("nunique") == 2
    d["is_wide_or_noball"] = d["wides"].notna() | d["noballs"].notna()
    d["status"] = d["ball_text_collides"].map({
        True: "CONFIRMED: distinct deliveries; source ball 'N.10' parsed as float N.1 (over had >=10 deliveries)",
        False: "UNRESOLVED"})
    cols = ["match_id", "season", "start_date", "innings", "ball", "ball_text", "actual_delivery", "deliveries_in_over",
            "bowler", "striker", "runs_off_bat", "extras", "wides", "noballs", "byes", "legbyes", "wicket_type",
            "is_wide_or_noball", "raw_row", "status"]
    return d.sort_values(KEY + ["raw_row"])[cols]


def identity_audit(raw):
    ids = rb.registry_ids()
    by_id = collections.defaultdict(set)
    for name, s in ids.items():
        for i in s:
            by_id[i].add(name)
    names = pd.concat([raw[c] for c in rb.PLAYER_COLS]).dropna()
    rows = []
    for pid, ns in by_id.items():
        if len(ns) > 1:
            for n in sorted(ns):
                rows.append(dict(registry_id=pid, name=n, deliveries_named=int((names == n).sum()),
                                 merged_in_pipeline=n in rb.ALIASES, merged_in_v1_1=n in rb.ALIASES or n in dict((b, a) for a, b in rb.IDENTITY_V11_PAIRS),
                                 verdict="CONFIRMED same person (shared registry id)"))
    for n in sorted(ids):  # "(2)" style names: compare with the base name
        if n.endswith(")") and " (" in n:
            base = n.rsplit(" (", 1)[0]
            same = bool(ids[n] & ids.get(base, set()))
            if not same:
                rows.append(dict(registry_id="|".join(sorted(ids[n])), name=n, deliveries_named=int((names == n).sum()),
                                 merged_in_pipeline=n in rb.ALIASES, merged_in_v1_1=n in rb.ALIASES,
                                 verdict=f"CONFIRMED different person from '{base}' (registry ids {sorted(ids[n])} vs {sorted(ids.get(base, []))})"))
    return pd.DataFrame(rows)


def discrepancy_audit(raw, p3_orig, p3_rec):
    """Replay the reconstruction's rules step by step and attribute every differing row."""
    raw_dt = raw.assign(start_date=pd.to_datetime(raw["start_date"]))
    v1 = rb.phase3(raw_dt[raw_dt["innings"] <= 2], dot_pts=1.0, bonuses=False, roster_cols=["striker", "bowler"])
    v2 = rb.phase3(raw_dt, dot_pts=1.0, bonuses=False, roster_cols=["striker", "bowler"])
    comp = ["total_batting_points", "wicket_points", "dot_ball_points", "pts"]
    replay_exact = v2[PM + comp].merge(p3_rec[PM + comp], on=PM, how="outer", indicator=True)
    replay_ok = bool((replay_exact["_merge"] == "both").all() and all((replay_exact[c + "_x"] == replay_exact[c + "_y"]).all() for c in comp))

    o = p3_orig.copy()
    o["key_player"] = o["player"]
    rec = p3_rec.assign(key_player=p3_rec["player"].replace(rb.ALIASES))
    m = o[PM[:1] + ["key_player", "player"] + comp].merge(
        rec[PM[:1] + ["key_player", "player"] + comp], on=["match_id", "key_player"], how="outer", suffixes=("_orig", "_rec"), indicator=True)
    m = m.merge(v1[PM + comp].assign(player=v1["player"].replace(rb.ALIASES)).rename(columns={"player": "key_player", **{c: c + "_v1" for c in comp}}), on=["match_id", "key_player"], how="left")
    # batting stats for the milestone / duck attribution
    p2 = rb.phase2(raw, {})
    runs = p2.groupby(["match_id", "striker"])["runs_off_bat"].sum().rename("runs")
    runs.index.names = ["match_id", "key_player"]
    outs = p2.dropna(subset=["player_dismissed"]).groupby(["match_id", "player_dismissed"]).size().rename("outs")
    outs.index.names = ["match_id", "key_player"]
    m = m.join(runs, on=["match_id", "key_player"]).join(outs, on=["match_id", "key_player"])
    both = m["_merge"] == "both"
    f = pd.DataFrame(index=m.index)
    f["dot_rate_1_vs_0.5"] = both & (m["dot_ball_points_v1"] != m["dot_ball_points_orig"])
    f["milestone_bonus_dropped"] = both & (m["runs"] >= 30)
    f["duck_penalty_dropped"] = both & (m["runs"] == 0) & (m["outs"] > 0)
    f["super_over_deliveries_included"] = both & (m[[c + "_rec" for c in comp]].values != m[[c + "_v1" for c in comp]].values).any(axis=1)
    f["alias_not_merged"] = both & (m["player_orig"] != m["player_rec"])
    f["non_striker_only_player_dropped"] = m["_merge"] == "left_only"
    f["only_in_reconstruction"] = m["_merge"] == "right_only"
    differs = ~both | (m["pts_orig"] != m["pts_rec"]) | f["alias_not_merged"]
    m = pd.concat([m, f], axis=1)
    m["any_cause"] = f.any(axis=1)
    out = m[differs].drop(columns=["_merge", "key_player"])
    summary = {
        "replay_of_reconstruction_rules_reproduces_pm_reconstructed_exactly": replay_ok,
        "rows_differing_total": int(differs.sum()),
        "rows_differing_without_any_attributed_cause": int((differs & ~m["any_cause"]).sum()),
        "rows_with_identical_pts_but_flagged": int((~differs & m["any_cause"]).sum()),
        "rows_by_cause_overlapping": {c: int((f[c] & differs).sum()) for c in f.columns},
    }
    return out, summary


def phase_quality(raw, p2):
    so_rows = int((raw["innings"] > 2).sum())
    so_matches = sorted(raw.loc[raw["innings"] > 2, "match_id"].unique().tolist())
    seasons = sorted(raw["season"].astype(str).unique())
    season_map = {s: rb.SEASON_MAP[s] if s in rb.SEASON_MAP else int(s) for s in seasons}
    yr = raw.assign(y=pd.to_datetime(raw["start_date"]).dt.year).groupby(raw["season"].astype(str))["y"].agg(["min", "max"])
    def side(df):
        return {
            "rows": len(df), "matches": int(df["match_id"].nunique()),
            "super_over_rows(innings>2)": int((df["innings"] > 2).sum()),
            "exact_duplicate_rows": int(df.duplicated().sum()),
            "repeated_match_innings_ball_keys": int(df.duplicated(KEY).sum()),
            "team_names": int(pd.concat([df["batting_team"], df["bowling_team"]]).nunique()),
            "venue_names": int(df["venue"].nunique()),
            "alias_names_present": {a: int((df[rb.PLAYER_COLS] == a).sum().sum()) for a in rb.ALIASES},
            "season_labels": sorted(df["season"].astype(str).unique()),
        }
    p1, p2s = side(raw), side(p2)
    checks = {
        "super_over_deliveries_removed": p2s["super_over_rows(innings>2)"] == 0 and p1["rows"] - p2s["rows"] == so_rows,
        "all_matches_kept": p1["matches"] == p2s["matches"],
        "no_exact_duplicates": p2s["exact_duplicate_rows"] == 0,
        "repeated_keys_all_explained": None,  # filled by caller from duplicate audit
        "season_labels_map_to_calendar_year": all(yr.loc[s, "min"] == yr.loc[s, "max"] == season_map[s] for s in seasons),
    }
    return {"phase1_raw": p1, "phase2_cleaned": p2s, "super_over_matches": so_matches,
            "super_over_rows_removed": so_rows, "season_map": season_map, "checks": checks}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    REP.mkdir(exist_ok=True)
    raw = rb.load_raw()
    p2 = pd.read_csv(rb.OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv", low_memory=False)

    dup = duplicate_key_audit(raw)
    dup.to_csv(REP / "duplicate_delivery_keys_audit_rebuilt.csv", index=False)

    ident = identity_audit(raw)
    ident.to_csv(REP / "player_identity_audit_rebuilt.csv", index=False)

    disc, disc_sum = discrepancy_audit(raw, pd.read_csv(rb.INP / "IPL_DecisionLab_Phase3_PlayerMatch_Points.csv"),
                                       pd.read_csv(rb.INP / "IPL_DecisionLab_pm_reconstructed.csv"))
    disc.to_csv(REP / "scoring_discrepancies_rebuilt.csv", index=False)

    q = phase_quality(raw, p2)
    q["checks"]["repeated_keys_all_explained"] = bool(len(dup) and dup["status"].str.startswith("CONFIRMED").all())
    q["duplicate_keys"] = {"keys": int(dup[KEY].drop_duplicates().shape[0]), "rows": len(dup),
                           "confirmed": int(dup["status"].str.startswith("CONFIRMED").sum()),
                           "unresolved": int((dup["status"] == "UNRESOLVED").sum()),
                           "rows_flagged_wide_or_noball": int(dup["is_wide_or_noball"].sum()),
                           "kept_in_phase2": True}
    q["scoring_discrepancies"] = disc_sum
    q["player_identity"] = ident.to_dict("records")
    q["generated_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    (REP / "data_quality_audit_rebuilt.json").write_text(json.dumps(q, indent=2, default=str))
    (rb.OUT / "season_map_rebuilt.json").write_text(json.dumps(q["season_map"], indent=2))

    # provenance: original vs rebuilt, byte-level
    pairs = {"Phase 2 Cleaned": "IPL_DecisionLab_Phase2_Cleaned", "Phase 4 Team Standardized": "IPL_DecisionLab_Team_Standardized",
             "Phase 3 PlayerMatch Points": "IPL_DecisionLab_Phase3_PlayerMatch_Points"}
    prov = {}
    for label, stem in pairs.items():
        a, b = rb.INP / f"{stem}.csv", rb.OUT / f"{stem}_rebuilt.csv"
        prov[label] = {"recovered_file": a.name, "recovered_sha256": sha(a), "rebuilt_file": b.name, "rebuilt_sha256": sha(b),
                       "byte_identical": sha(a) == sha(b), "rebuilt_by": "src/rebuild.py"}
    prov["Phase 2 Cleaned"]["caveat"] = "Venue mapping (venue_map_rebuilt.json) was recovered from the recovered Phase 2 itself; no original venue-mapping code survives."
    prov["reconstructed (NOT original)"] = {
        "IPL_DecisionLab_pm_reconstructed.csv": "Replayable from raw incl. super overs, dot=1, no milestone/duck, roster striker+bowler, no alias merge",
        "IPL_DecisionLab_Phase5_Final_Features.csv": "Built on pm_reconstructed (pts identical on all rows) -> superseded",
        "IPL_DecisionLab_Phase6_*": "Metrics computed on reconstructed scoring -> superseded"}
    prov["new derived outputs (v1.1, no original counterpart)"] = {
        n: {"sha256": sha(rb.OUT / n), "rebuilt_by": "src/rebuild.py"} for n in [
            "IPL_DecisionLab_Phase3_PlayerMatch_Points_v1.1_rebuilt.csv", "IPL_DecisionLab_Phase2_DeliveryOrder_rebuilt.csv",
            "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv", "identity_map_v1.1_rebuilt.json"]}
    prov["phase6_models"] = "see models/preprocess_config_rebuilt.json (artifact hashes, settings, versions) — REBUILT, not original"
    (REP / "provenance_rebuilt.json").write_text(json.dumps(prov, indent=2))
    print(json.dumps({"checks": q["checks"], "duplicate_keys": q["duplicate_keys"], "scoring": disc_sum,
                      "identity": ident[["name", "registry_id", "merged_in_pipeline", "verdict"]].to_dict("records"),
                      "byte_identical": {k: v["byte_identical"] for k, v in prov.items() if isinstance(v, dict) and "byte_identical" in v}}, indent=1))


if __name__ == "__main__":
    main()
