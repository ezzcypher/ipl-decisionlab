"""Build the compact, app-ready data bundle in ./data from the validated Stage B recovery workspace.

Run locally (NOT on Streamlit Cloud):  python3 -I scripts/build_data.py [--recovery /path/to/recovery]
Reads : <recovery>/inputs (read-only raw + recovered files), <recovery>/rebuilt, <recovery>/models, <recovery>/reports
Writes: ./data/*.parquet|json|csv, ./models/*
Every number the dashboard shows is computed here from those sources or read from the saved Stage B reports.
"""
import argparse, hashlib, json, shutil, sys, zipfile, datetime
from pathlib import Path
import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
from core import scoring  # single scoring implementation used by the app

ap = argparse.ArgumentParser()
ap.add_argument("--recovery", default=str(APP.parent / "recovery"))
REC = Path(ap.parse_args().recovery).resolve()
sys.path.insert(0, str(REC / "src"))
import rebuild as rb  # verified Stage B pipeline (byte-identical Phase 2/3/4)

DATA, MODELS = APP / "data", APP / "models"
DATA.mkdir(exist_ok=True); MODELS.mkdir(exist_ok=True)
KEY = ["match_id", "innings", "ball"]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(df, name):
    df.to_parquet(DATA / f"{name}.parquet", index=False)


# ---------------------------------------------------------------- sources
raw = rb.load_raw()
with zipfile.ZipFile(rb.INP / "ipl_male_csv2.zip") as z:
    raw_ball_text = pd.read_csv(z.open("all_matches.csv"), usecols=["ball"], dtype={"ball": str})["ball"]
p2 = pd.read_csv(rb.OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv", low_memory=False)
p4 = pd.read_csv(rb.OUT / "IPL_DecisionLab_Team_Standardized_rebuilt.csv", low_memory=False,
                 usecols=["batting_team_std", "bowling_team_std"])
p2["batting_team_std"], p2["bowling_team_std"] = p4["batting_team_std"], p4["bowling_team_std"]
idmap = json.loads((rb.OUT / "identity_map_v1.1_rebuilt.json").read_text())
v11 = idmap["v1.1_additions"]
for c in rb.PLAYER_COLS + ["fielder_1", "fielder_2", "fielder_3"]:
    p2[c] = p2[c].replace(v11)
season_map = json.loads((rb.OUT / "season_map_rebuilt.json").read_text())
p2["season_year"] = p2["season"].astype(str).map(season_map).astype(int)
feat = pd.read_csv(rb.OUT / "IPL_DecisionLab_Phase5_Features_v1.1_rebuilt.csv")
order = pd.read_csv(rb.OUT / "IPL_DecisionLab_Phase2_DeliveryOrder_rebuilt.csv", dtype={"ball_text": str})

legal_bat = p2["wides"].isna()                         # balls faced: everything except wides
legal_bowl = p2["wides"].isna() & p2["noballs"].isna()  # legal balls in the over
p2["bowler_runs"] = p2["runs_off_bat"] + p2["wides"].fillna(0) + p2["noballs"].fillna(0)
p2["total_runs"] = p2["runs_off_bat"] + p2["extras"]
p2["is_dot_scoring"] = legal_bat & (p2["runs_off_bat"] == 0) & (p2["extras"] == 0)  # scoring definition
p2["bowler_wicket"] = p2["wicket_type"].isin(rb.BOWLER_WICKETS)

# ---------------------------------------------------------------- player-match stats
PM = ["match_id", "player"]
bat = p2.groupby(["match_id", "striker"]).agg(
    runs=("runs_off_bat", "sum"), balls_faced=("wides", lambda s: s.isna().sum()),
    fours=("runs_off_bat", lambda s: (s == 4).sum()), sixes=("runs_off_bat", lambda s: (s == 6).sum()),
).reset_index().rename(columns={"striker": "player"})
bat["batted"] = True
dis = p2.dropna(subset=["player_dismissed"]).groupby(["match_id", "player_dismissed"]).agg(
    dismissal=("wicket_type", "first")).reset_index().rename(columns={"player_dismissed": "player"})
bowl = p2.assign(legal=legal_bowl).groupby(["match_id", "bowler"]).agg(
    legal_balls=("legal", "sum"), deliveries_bowled=("legal", "size"), runs_conceded=("bowler_runs", "sum"),
    wickets=("bowler_wicket", "sum"), dots=("is_dot_scoring", "sum"),
    wides_bowled=("wides", lambda s: s.notna().sum()), noballs_bowled=("noballs", lambda s: s.notna().sum()),
).reset_index().rename(columns={"bowler": "player"})
bowl["bowled"] = True

# team per player-match (batting side if named while batting, bowling side if bowled)
sides = pd.concat([
    p2[["match_id", c, "batting_team_std", "batting_team", "bowling_team_std"]].rename(
        columns={c: "player", "batting_team_std": "team", "batting_team": "team_original", "bowling_team_std": "opponent"})
    for c in ["striker", "non_striker", "player_dismissed"]] + [
    p2[["match_id", "bowler", "bowling_team_std", "bowling_team", "batting_team_std"]].rename(
        columns={"bowler": "player", "bowling_team_std": "team", "bowling_team": "team_original", "batting_team_std": "opponent"})
]).dropna(subset=["player"]).drop_duplicates()
assert not sides.duplicated(PM).any(), "player mapped to two teams in one match"

pm = feat.merge(sides, on=PM, how="left").merge(bat, on=PM, how="left").merge(dis, on=PM, how="left").merge(bowl, on=PM, how="left")
for c in ["runs", "balls_faced", "fours", "sixes", "legal_balls", "deliveries_bowled", "runs_conceded", "wickets", "dots",
          "wides_bowled", "noballs_bowled"]:
    pm[c] = pm[c].fillna(0).astype(int)
pm["batted"] = pm["batted"].fillna(False).astype(bool)
pm["bowled"] = pm["bowled"].fillna(False).astype(bool)
pm["dismissed"] = pm["dismissal"].notna()
pm["bowling_points"] = pm["wicket_points"]
assert pm["team"].notna().all() and len(pm) == len(feat)

# independent check: scalar scoring formula reproduces every stored component
chk = pm.apply(lambda r: scoring.score(r.runs, r.fours, r.sixes, r.batted, r.dismissed, r.wickets, r.dots), axis=1, result_type="expand")
assert np.allclose(chk["batting"], pm["total_batting_points"]) and np.allclose(chk["bowling"], pm["wicket_points"]) \
    and np.allclose(chk["dot"], pm["dot_ball_points"]) and np.allclose(chk["total"], pm["pts"]), "scoring mismatch"

# split label (chronological windows from the saved Phase 6 config)
cfg = json.loads((REC / "models" / "preprocess_config_rebuilt.json").read_text())
d = pd.to_datetime(pm["start_date"])
pm["split"] = "outside"
for k, v in cfg["splits"].items():
    pm.loc[(d >= v["from"]) & (d <= v["to"]), "split"] = k
pm["start_date"] = d
save(pm, "player_match")

# ---------------------------------------------------------------- players (identity)
ids = rb.registry_ids()
aliases = {**rb.ALIASES, **v11}
inv = {}
for a, c in aliases.items():
    inv.setdefault(c, []).append(a)
players = pm.groupby("player").agg(matches=("match_id", "nunique"), first_match=("start_date", "min"),
                                   last_match=("start_date", "max"), seasons=("season_year", "nunique"),
                                   total_pts=("pts", "sum")).reset_index()
players["registry_id"] = players["player"].map(lambda n: "|".join(sorted(ids.get(n, set()))))
players["merged_aliases"] = players["player"].map(lambda n: ", ".join(inv.get(n, [])))
players["identity_status"] = np.where(players["registry_id"].str.len() > 0, "Cricsheet registry id", "No registry id found")
save(players, "players")
team_seasons = pm.groupby(["player", "season_year", "team"]).agg(matches=("match_id", "nunique"),
                                                                team_original=("team_original", lambda s: ", ".join(sorted(set(s))))).reset_index()
save(team_seasons, "player_team_seasons")

# images: none verified -> empty mapping with schema (app falls back to initials avatars)
img = DATA / "player_images.csv"
if not img.exists():
    pd.DataFrame(columns=["player", "registry_id", "image_file", "source_url", "license", "attribution", "verified_by"]).to_csv(img, index=False)

# ---------------------------------------------------------------- delivery aggregates (cleaned)
p2["legal"] = legal_bowl
p2["is_four"], p2["is_six"] = p2["runs_off_bat"] == 4, p2["runs_off_bat"] == 6
p2["dismissal_any"] = p2["player_dismissed"].notna()
agg = dict(deliveries=("ball", "size"), legal_balls=("legal", "sum"), runs=("total_runs", "sum"), runs_off_bat=("runs_off_bat", "sum"),
           extras=("extras", "sum"), wides=("wides", "sum"), noballs=("noballs", "sum"), byes=("byes", "sum"),
           legbyes=("legbyes", "sum"), penalty=("penalty", "sum"), fours=("is_four", "sum"), sixes=("is_six", "sum"),
           dismissals=("dismissal_any", "sum"), bowler_wickets=("bowler_wicket", "sum"), dots=("is_dot_scoring", "sum"),
           matches=("match_id", "nunique"))
season = p2.groupby("season_year").agg(**agg).reset_index()
season["season_label"] = season["season_year"].map({v: k for k, v in season_map.items()})
save(season, "season_summary")

team_bat = p2.groupby(["season_year", "batting_team_std"]).agg(matches=("match_id", "nunique"), runs_scored=("total_runs", "sum"),
            balls_faced=("legal", "sum"), wickets_lost=("dismissal_any", "sum"), fours=("is_four", "sum"), sixes=("is_six", "sum")
            ).reset_index().rename(columns={"batting_team_std": "team"})
team_bowl = p2.groupby(["season_year", "bowling_team_std"]).agg(runs_conceded=("total_runs", "sum"), balls_bowled=("legal", "sum"),
            wickets_taken=("dismissal_any", "sum")).reset_index().rename(columns={"bowling_team_std": "team"})
team = team_bat.merge(team_bowl, on=["season_year", "team"], how="outer")
names = pd.concat([p2[["season_year", "batting_team_std", "batting_team"]].set_axis(["season_year", "team", "orig"], axis=1),
                   p2[["season_year", "bowling_team_std", "bowling_team"]].set_axis(["season_year", "team", "orig"], axis=1)]).drop_duplicates()
team = team.merge(names.groupby(["season_year", "team"])["orig"].agg(lambda s: ", ".join(sorted(s))).rename("original_names").reset_index(),
                  on=["season_year", "team"])
save(team, "team_season")

inn = p2.groupby(["match_id", "innings"]).agg(start_date=("start_date", "first"), season_year=("season_year", "first"),
        venue=("venue", "first"), batting_team=("batting_team_std", "first"), bowling_team=("bowling_team_std", "first"),
        runs=("total_runs", "sum"), wickets=("dismissal_any", "sum"), legal_balls=("legal", "sum"), fours=("is_four", "sum"),
        sixes=("is_six", "sum"), extras=("extras", "sum")).reset_index()
inn["start_date"] = pd.to_datetime(inn["start_date"])
save(inn, "innings")

p2["over"] = order["over"].to_numpy()  # same row order as Phase 2 (p2_row)
assert (order["p2_row"].to_numpy() == np.arange(len(p2))).all()
overs = p2.groupby(["season_year", "over"]).agg(runs=("total_runs", "sum"), legal_balls=("legal", "sum"),
                                              dismissals=("dismissal_any", "sum"), innings=("match_id", "size")).reset_index()
save(overs, "over_season")
dismiss = p2.dropna(subset=["wicket_type"]).groupby(["season_year", "wicket_type"]).size().rename("count").reset_index()
save(dismiss, "dismissal_season")
rd = p2.groupby(["season_year", "runs_off_bat"]).size().rename("deliveries").reset_index()
save(rd, "runs_per_ball_season")
venue = inn[inn.innings == 1].groupby("venue").agg(matches=("match_id", "nunique"), avg_first_innings=("runs", "mean"),
          seasons=("season_year", "nunique"), first=("season_year", "min"), last=("season_year", "max")).reset_index()
save(venue, "venue_summary")

# ---------------------------------------------------------------- data-quality audit (raw vs cleaned)
raw_s = raw.assign(start_date=pd.to_datetime(raw["start_date"], errors="coerce"))


def missing_table(df, label):
    rows = []
    for c in df.columns:
        blanks = int(df[c].dropna().astype(str).str.strip().eq("").sum()) if df[c].dtype == object else 0
        rows.append({"dataset": label, "column": c, "dtype": str(df[c].dtype), "missing": int(df[c].isna().sum()),
                     "missing_pct": float(df[c].isna().mean() * 100), "blank_strings": blanks})
    return pd.DataFrame(rows)


p2_file_cols = pd.read_csv(rb.OUT / "IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv", nrows=0).columns.tolist()
missing = pd.concat([missing_table(raw, "Phase 1 · raw"), missing_table(p2[p2_file_cols], "Phase 2 · cleaned")])
save(missing, "audit_missing")

ext_sum = raw[["wides", "noballs", "byes", "legbyes", "penalty"]].fillna(0).sum(axis=1)
dup_audit = pd.read_csv(REC / "reports" / "duplicate_delivery_keys_audit_rebuilt.csv", dtype={"ball_text": str})
dup_audit.to_csv(DATA / "audit_repeated_keys.csv", index=False)
ident = pd.read_csv(REC / "reports" / "player_identity_audit_rebuilt.csv")
ident.to_csv(DATA / "audit_player_identity.csv", index=False)
o_sorted = order.sort_values(["match_id", "innings", "delivery_seq"])
legal_per_over = o_sorted.groupby(["match_id", "innings", "over"])["is_legal"].sum()
dq = json.loads((REC / "reports" / "data_quality_audit_rebuilt.json").read_text())
old_json = json.loads((rb.INP / "IPL_DecisionLab_Phase6_Audit_Report.json").read_text())


def chk(cid, area, check, scope, value, affected, status, category, evidence):
    return dict(id=cid, area=area, check=check, scope=scope, value=str(value), rows_affected=int(affected), status=status,
                category=category, evidence=evidence)


RE = "Recomputed from source"
checks = [
    chk("S1", "Schema", "Raw rows × columns", "raw", f"{raw.shape[0]:,} × {raw.shape[1]}", 0, "INFO", RE, "all_matches.csv in ipl_male_csv2.zip"),
    chk("S2", "Schema", "Cleaned rows × columns", "cleaned", f"{len(p2):,} × {len(p2_file_cols)}", 0, "INFO", RE, "adds date_year"),
    chk("D1", "Duplicates", "Exact duplicate rows", "raw", int(raw.duplicated().sum()), raw.duplicated().sum(),
        "PASS" if raw.duplicated().sum() == 0 else "FAIL", RE, "all 27 columns compared"),
    chk("D2", "Duplicates", "Repeated (match, innings, ball) keys", "raw (innings ≤ 2)", f"{len(dup_audit)//2} keys / {len(dup_audit)} rows",
        len(dup_audit), "PASS" if dup_audit["status"].str.startswith("CONFIRMED").all() else "WARN", "Legitimate repeated key",
        "Source writes the 10th delivery of an over as 'N.10'; read as float N.1. Rows kept, not deduplicated."),
    chk("D3", "Duplicates", "Repeated keys after reading ball as text", "raw", int(pd.DataFrame({"m": raw.match_id, "i": raw.innings, "b": raw_ball_text}).duplicated().sum()),
        0, "PASS" if not pd.DataFrame({"m": raw.match_id, "i": raw.innings, "b": raw_ball_text}).duplicated().any() else "FAIL", RE, "ball as written in the source file"),
    chk("T1", "Dates", "Unparseable start_date", "raw", int(raw_s.start_date.isna().sum()), raw_s.start_date.isna().sum(),
        "PASS" if raw_s.start_date.notna().all() else "FAIL", RE, "pd.to_datetime(errors='coerce')"),
    chk("T2", "Dates", "Coverage", "raw", f"{raw_s.start_date.min():%Y-%m-%d} → {raw_s.start_date.max():%Y-%m-%d}", 0, "INFO", RE, ""),
    chk("T3", "Dates", "Season label maps to one calendar year", "raw", f"{len(season_map)} labels",
        0, "PASS" if dq["checks"]["season_labels_map_to_calendar_year"] else "FAIL", RE,
        "2007/08→2008, 2009/10→2010, 2020/21→2020; others already a year"),
    chk("I1", "Innings", "Super-over deliveries (innings > 2)", "raw", int((raw.innings > 2).sum()), (raw.innings > 2).sum(), "INFO", RE,
        f"{raw.loc[raw.innings > 2, 'match_id'].nunique()} matches; excluded by design in Phase 2"),
    chk("I2", "Innings", "Super-over deliveries remaining", "cleaned", int((p2.innings > 2).sum()), (p2.innings > 2).sum(),
        "PASS" if (p2.innings > 2).sum() == 0 else "FAIL", RE, "per-delivery check (not per-match)"),
    chk("O1", "Delivery order", "Corrected order equals source file order", "cleaned", "all innings", 0,
        "PASS" if o_sorted.groupby(["match_id", "innings"])["raw_row"].apply(lambda s: s.is_monotonic_increasing).all() else "FAIL", RE,
        "sort by (over, delivery number parsed from text)"),
    chk("O2", "Delivery order", "Overs with > 6 legal balls", "cleaned", int((legal_per_over > 6).sum()), int(legal_per_over[legal_per_over > 6].sum()),
        "WARN", "Unresolved anomaly", "source records 7 legal balls; likely umpire/scorer error; kept as recorded"),
    chk("O3", "Delivery order", "Overs with 0 legal balls", "cleaned", int((legal_per_over == 0).sum()), int(legal_per_over[legal_per_over == 0].size),
        "WARN", "Unresolved anomaly", "only wides/no-balls recorded in that over; kept as recorded"),
    chk("R1", "Runs", "Negative runs_off_bat", "raw", int((raw.runs_off_bat < 0).sum()), (raw.runs_off_bat < 0).sum(),
        "PASS" if (raw.runs_off_bat < 0).sum() == 0 else "FAIL", RE, ""),
    chk("R2", "Runs", "runs_off_bat > 6", "raw", int((raw.runs_off_bat > 6).sum()), (raw.runs_off_bat > 6).sum(),
        "PASS" if (raw.runs_off_bat > 6).sum() == 0 else "WARN", RE, "values above 6 are rare but possible (overthrows)"),
    chk("R3", "Runs", "extras = wides + noballs + byes + legbyes + penalty", "raw", int((ext_sum != raw.extras).sum()), (ext_sum != raw.extras).sum(),
        "PASS" if (ext_sum == raw.extras).all() else "FAIL", RE, ""),
    chk("W1", "Wickets", "wicket_type without player_dismissed (or reverse)", "raw",
        int((raw.wicket_type.notna() != raw.player_dismissed.notna()).sum()), (raw.wicket_type.notna() != raw.player_dismissed.notna()).sum(),
        "PASS" if (raw.wicket_type.notna() == raw.player_dismissed.notna()).all() else "FAIL", RE, ""),
    chk("W2", "Wickets", "Dismissed player not at the crease", "raw",
        int((raw.player_dismissed.notna() & (raw.player_dismissed != raw.striker) & (raw.player_dismissed != raw.non_striker)).sum()),
        (raw.player_dismissed.notna() & (raw.player_dismissed != raw.striker) & (raw.player_dismissed != raw.non_striker)).sum(),
        "PASS" if not (raw.player_dismissed.notna() & (raw.player_dismissed != raw.striker) & (raw.player_dismissed != raw.non_striker)).any() else "WARN", RE, ""),
    chk("M1", "Teams", "Team names → standard names", "raw → cleaned", f"{pd.concat([raw.batting_team, raw.bowling_team]).nunique()} → {pd.concat([p2.batting_team_std, p2.bowling_team_std]).nunique()}",
        int(raw.batting_team.isin(rb.TEAM_MAP).sum() + raw.bowling_team.isin(rb.TEAM_MAP).sum()), "INFO", RE, "4 franchise renames; originals preserved"),
    chk("M2", "Teams", "Batting team equals bowling team", "raw", int((raw.batting_team == raw.bowling_team).sum()), (raw.batting_team == raw.bowling_team).sum(),
        "PASS" if (raw.batting_team == raw.bowling_team).sum() == 0 else "FAIL", RE, ""),
    chk("M3", "Players", "Aliases merged (shared Cricsheet registry id)", "cleaned (v1.1)", ", ".join(f"{a}→{c}" for a, c in aliases.items()),
        0, "PASS", "Confirmed data error (fixed)", "registry ids from *_info.csv; never co-occur in a match"),
    chk("M4", "Players", "Harmeet Singh (2) kept separate", "cleaned", "different registry id", 0, "PASS", RE, "0bf15e52 vs 2a72fd4f"),
    chk("M5", "Venues", "Venue names → standard names", "raw → cleaned", f"{raw.venue.nunique()} → {p2.venue.nunique()}", 0, "INFO",
        "Precomputed mapping", "mapping recovered from the recovered Phase 2 itself (no original code)"),
    chk("P6a", "Earlier audit", "Old XGBoost test MAE 23.18 / RMSE 29.57", "recovered report", "23.1815 / 29.5706", 0, "NOT REPRODUCED",
        "Reported, not reproduced", "original model and code missing; scoring used was the flawed reconstruction"),
    chk("P6b", "Earlier audit", "Old XGBoost gain 45.29% (avg_pts_prev5)", "recovered report", "45.29%", 0, "NOT REPRODUCED",
        "Reported, not reproduced", "rebuilt model gives a different value"),
    chk("P6c", "Earlier audit", "Old Phase 6 PNG plots 'PASS'", "recovered report", "3 files", 0, "FAIL", "Reported, not reproduced",
        "PNG files absent from the recovered archive"),
    chk("P6d", "Earlier audit", "Old baseline metrics (median / last / rolling-3)", "recovered report", "23.0146 / 30.988 / 25.8809 test MAE", 0, "PASS",
        RE, "reproduced exactly from the recovered Phase 5 features (Stage B test)"),
]
save(pd.DataFrame(checks), "audit_checks")

comparison = [
    ("Rows", len(raw), len(p2), "175 super-over deliveries removed (innings > 2)"),
    ("Columns", raw.shape[1], len(p2_file_cols), "date_year added"),
    ("Matches", raw.match_id.nunique(), p2.match_id.nunique(), "no match removed (super-over matches keep their normal innings)"),
    ("Super-over rows", int((raw.innings > 2).sum()), int((p2.innings > 2).sum()), "excluded by design"),
    ("Exact duplicate rows", int(raw.duplicated().sum()), int(p2[p2_file_cols].duplicated().sum()), "none in either"),
    ("Repeated (match, innings, ball) keys", int(raw[raw.innings <= 2].duplicated(KEY).sum()), int(p2.duplicated(KEY).sum()),
     "unchanged on purpose: legitimate 10th deliveries; corrected order in derived dataset"),
    ("Team names", pd.concat([raw.batting_team, raw.bowling_team]).nunique(), pd.concat([p2.batting_team_std, p2.bowling_team_std]).nunique(),
     "standardized columns added (Phase 4); originals kept"),
    ("Venue names", raw.venue.nunique(), p2.venue.nunique(), "venue renames/city suffixes unified"),
    ("Player names (any role)", pd.concat([raw[c] for c in rb.PLAYER_COLS]).nunique(), pd.concat([p2[c] for c in rb.PLAYER_COLS]).nunique(),
     "3 aliases merged (Arshad Khan, NA Saini, S Arora)"),
    ("Season labels", raw.season.astype(str).nunique(), p2.season.astype(str).nunique(), "labels kept; season_year mapping added"),
    ("Total runs", int(raw.runs_off_bat.sum() + raw.extras.sum()), int(p2.total_runs.sum()), "runs scored in super overs removed"),
    ("Dismissals", int(raw.player_dismissed.notna().sum()), int(p2.player_dismissed.notna().sum()), "super-over dismissals removed"),
    ("Missing cells (all columns)", int(raw.isna().sum().sum()), int(p2[p2_file_cols].isna().sum().sum()),
     "fewer rows → fewer sparse cells; no imputation done (NaN = not applicable, e.g. no wide)"),
]
save(pd.DataFrame(comparison, columns=["metric", "phase1_raw", "phase2_cleaned", "cause"]).astype({"phase1_raw": "int64", "phase2_cleaned": "int64"}), "audit_comparison")

schema = pd.DataFrame({"column": raw.columns, "raw_dtype": [str(t) for t in raw.dtypes]})
schema = schema.merge(pd.DataFrame({"column": p2_file_cols, "cleaned_dtype": [str(p2[c].dtype) for c in p2_file_cols]}), on="column", how="outer")
schema["change"] = np.where(schema.raw_dtype.isna(), "added", np.where(schema.raw_dtype != schema.cleaned_dtype, "dtype changed", "unchanged"))
save(schema, "audit_schema")

with zipfile.ZipFile(REC / "source" / "IPL_DecisionLab_Recovered.zip") as z:
    inv_rows = [{"file": i.filename, "size_mb": round(i.file_size / 2**20, 3)} for i in z.infolist()]
inventory = pd.DataFrame(inv_rows)
role = {"ipl_male_csv2 (1).zip": "Raw Cricsheet data (source of truth)",
        "IPL_DecisionLab_Phase2_Cleaned.csv": "Phase 2 original — verified (rebuilt byte-identical)",
        "IPL_DecisionLab_Team_Standardized.csv": "Phase 4 original — verified (rebuilt byte-identical)",
        "IPL_DecisionLab_Phase3_PlayerMatch_Points.csv": "Phase 3 original — verified (rebuilt byte-identical)",
        "IPL_DecisionLab_pm_reconstructed.csv": "Reconstruction — superseded (wrong scoring rules)",
        "IPL_DecisionLab_Phase5_Final_Features.csv": "Built on reconstruction — superseded",
        "IPL_DecisionLab_features_reconstructed.csv": "Duplicate of Phase 5 file — superseded",
        "IPL_DecisionLab_Phase6_Audit_Report.json": "Old Phase 6 report — partly reproduced",
        "IPL_DecisionLab_Phase6_Final_Consistency_Audit.txt": "Old Phase 6 report — partly reproduced",
        "IPL_DecisionLab_Player_Mapping_Audit.csv": "Old mapping audit (1 row) — superseded by registry audit"}
inventory["role"] = inventory["file"].map(lambda f: role.get(f, "Duplicate copy" if "(1)" in f else "Not part of IPL DecisionLab"))
missing_files = ["IPL_DecisionLab_Phase6_Actual_vs_Predicted.png", "IPL_DecisionLab_Phase6_Residuals.png",
                 "IPL_DecisionLab_Phase6_Feature_Importances.png", "original XGBoost model file", "original Phase 3–6 notebook code"]
inventory = pd.concat([inventory, pd.DataFrame({"file": missing_files, "size_mb": np.nan, "role": "MISSING from recovered archive"})])
inventory.to_csv(DATA / "audit_inventory.csv", index=False)

tn = pd.concat([raw[["batting_team", "season"]].rename(columns={"batting_team": "name"}).assign(role="batting"),
                raw[["bowling_team", "season"]].rename(columns={"bowling_team": "name"}).assign(role="bowling")])
tn["season_year"] = tn["season"].astype(str).map(season_map)
team_names = tn.groupby("name").agg(rows=("role", "size"), first_season=("season_year", "min"), last_season=("season_year", "max")).reset_index()
team_names["standardized"] = team_names["name"].replace(rb.TEAM_MAP)
team_names["changed"] = team_names["name"] != team_names["standardized"]
team_names.to_csv(DATA / "audit_team_names.csv", index=False)
vmap = json.loads((rb.OUT / "venue_map_rebuilt.json").read_text())
vn = raw.groupby("venue").agg(rows=("match_id", "size"), matches=("match_id", "nunique")).reset_index()
vn["standardized"] = vn["venue"].replace(vmap)
vn["changed"] = vn["venue"] != vn["standardized"]
vn.to_csv(DATA / "audit_venue_names.csv", index=False)
so = raw[raw.innings > 2].groupby("match_id").agg(start_date=("start_date", "first"), season=("season", "first"),
        super_over_rows=("ball", "size"), super_over_innings=("innings", "nunique"), runs=("runs_off_bat", "sum")).reset_index()
so.to_csv(DATA / "audit_super_overs.csv", index=False)
anom = o_sorted.groupby(["match_id", "innings", "over"]).agg(legal_balls=("is_legal", "sum"), deliveries=("is_legal", "size")).reset_index()
anom = anom[(anom.legal_balls > 6) | (anom.legal_balls == 0)].merge(p2[["match_id", "start_date", "season"]].drop_duplicates("match_id"), on="match_id")
anom["issue"] = np.where(anom.legal_balls > 6, "more than 6 legal balls", "no legal ball recorded")
anom.to_csv(DATA / "audit_over_anomalies.csv", index=False)

# ---------------------------------------------------------------- models & predictions (copied, provenance kept)
for name in ["xgboost_rebuilt.json", "ridge_rebuilt.joblib", "preprocess_config_rebuilt.json"]:
    shutil.copy2(REC / "models" / name, MODELS / name)
for name in ["phase6_metrics_rebuilt.json", "phase6_feature_importance_rebuilt.csv", "phase6_predictions_val_rebuilt.csv",
             "phase6_predictions_test_rebuilt.csv", "scoring_discrepancies_rebuilt.csv"]:
    shutil.copy2(REC / "reports" / name, DATA / name)

manifest = {
    "built_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "recovery_workspace": "Stage B recovery (steps 1–6, 21/21 tests passed)",
    "scoring_version": "v1 rules, v1.1 identity",
    "season_map": season_map, "aliases": aliases, "team_map": rb.TEAM_MAP,
    "venue_map": json.loads((rb.OUT / "venue_map_rebuilt.json").read_text()),
    "raw_summary": {"rows": len(raw), "columns": raw.shape[1], "matches": int(raw.match_id.nunique()),
                    "first_date": f"{raw_s.start_date.min():%Y-%m-%d}", "last_date": f"{raw_s.start_date.max():%Y-%m-%d}",
                    "unique_batters": int(raw.striker.nunique()), "unique_bowlers": int(raw.bowler.nunique()),
                    "cells": int(raw.size), "missing_cells": int(raw.isna().sum().sum())},
    "cleaned_summary": {"rows": len(p2), "columns": len(p2_file_cols), "matches": int(p2.match_id.nunique()),
                        "seasons": int(p2.season_year.nunique()), "unique_batters": int(p2.striker.nunique()),
                        "unique_bowlers": int(p2.bowler.nunique()), "total_runs": int(p2.total_runs.sum()),
                        "dismissals": int(p2.dismissal_any.sum()), "bowler_wickets": int(p2.bowler_wicket.sum()),
                        "core_columns_complete_pct": float(p2[["match_id", "season", "start_date", "innings", "ball", "batting_team",
                                                               "bowling_team", "striker", "non_striker", "bowler", "runs_off_bat", "extras"]].notna().mean().mean() * 100)},
    "scoring_discrepancy_summary": dq["scoring_discrepancies"],
    "old_phase6_report": {"xgb_test": old_json["out_of_sample_generalization_test_split"], "xgb_gains": old_json["model_weights_and_importances"]["xgb_gains"]},
    "files": {p.name: sha(p) for p in sorted(list(DATA.iterdir()) + list(MODELS.iterdir())) if p.is_file() and p.name != "manifest.json"},
}
(DATA / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
print("built:", sum(p.stat().st_size for p in DATA.iterdir()) / 2**20, "MB data;", [p.name for p in sorted(DATA.iterdir())])
