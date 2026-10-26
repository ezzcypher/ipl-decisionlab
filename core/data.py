"""Cached loaders for the compact data bundle. Every loader fails soft with a clear message."""
import json
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
import os
DATA = Path(os.environ.get("IPL_DL_DATA", ROOT / "data"))  # override only used by tests
MODELS = Path(os.environ.get("IPL_DL_MODELS", ROOT / "models"))
PREDICTORS = ["prev_pts", "avg_pts_prev3", "avg_pts_prev5", "std_pts_prev3", "trend_pts_prev3", "matches_before"]


class MissingData(Exception):
    pass


def _path(name, base=DATA):
    p = base / name
    if not p.exists():
        raise MissingData(f"Required file `{p.name}` is missing from `{base}`. Run `python3 -I scripts/build_data.py` locally.")
    return p


@st.cache_data(show_spinner=False)
def table(name):
    p = _path(name)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, dtype={"ball_text": str})


@st.cache_data(show_spinner=False)
def jsonfile(name, base="data"):
    return json.loads(_path(name, DATA if base == "data" else MODELS).read_text())


def player_match():
    return table("player_match.parquet")


def metrics():
    return jsonfile("phase6_metrics_rebuilt.json")


def model_config():
    return jsonfile("preprocess_config_rebuilt.json", base="models")


def manifest():
    return jsonfile("manifest.json")


@st.cache_data(show_spinner=False)
def predictions():
    v = table("phase6_predictions_val_rebuilt.csv").assign(split="validation")
    t = table("phase6_predictions_test_rebuilt.csv").assign(split="test")
    out = pd.concat([v, t], ignore_index=True)
    out["start_date"] = pd.to_datetime(out["start_date"])
    return out


@st.cache_resource(show_spinner=False)
def load_models():
    """Load saved artifacts; returns {name: model} for those that load, plus errors."""
    loaded, errors = {}, {}
    try:
        from xgboost import XGBRegressor
        m = XGBRegressor(); m.load_model(_path("xgboost_rebuilt.json", MODELS)); loaded["XGBoost"] = m
    except Exception as e:  # noqa: BLE001 — surfaced in the UI
        errors["XGBoost"] = str(e)
    try:
        import joblib
        loaded["Ridge regression"] = joblib.load(_path("ridge_rebuilt.joblib", MODELS))
    except Exception as e:  # noqa: BLE001
        errors["Ridge regression"] = str(e)
    return loaded, errors


def player_stats(pm):
    """Career aggregates per player from player-match rows (whatever filter was applied upstream)."""
    g = pm.groupby("player")
    s = g.agg(matches=("match_id", "nunique"), seasons=("season_year", "nunique"), total_pts=("pts", "sum"),
              avg_pts=("pts", "mean"), median_pts=("pts", "median"), max_pts=("pts", "max"), std_pts=("pts", "std"),
              bat_pts=("total_batting_points", "sum"), bowl_pts=("wicket_points", "sum"), dot_pts=("dot_ball_points", "sum"),
              runs=("runs", "sum"), balls_faced=("balls_faced", "sum"), fours=("fours", "sum"), sixes=("sixes", "sum"),
              innings_batted=("batted", "sum"), dismissals=("dismissed", "sum"), highest=("runs", "max"),
              innings_bowled=("bowled", "sum"), legal_balls=("legal_balls", "sum"), runs_conceded=("runs_conceded", "sum"),
              wickets=("wickets", "sum"), dots=("dots", "sum"), last_match=("start_date", "max"))
    s["std_pts"] = s["std_pts"].fillna(0)
    s["cv"] = (s["std_pts"] / s["avg_pts"].where(s["avg_pts"] > 0)).round(3)
    s["bat_avg"] = s["runs"] / s["dismissals"].where(s["dismissals"] > 0)
    s["strike_rate"] = 100 * s["runs"] / s["balls_faced"].where(s["balls_faced"] > 0)
    s["boundary_pct"] = 100 * (s["fours"] * 4 + s["sixes"] * 6) / s["runs"].where(s["runs"] > 0)
    s["overs"] = s["legal_balls"] // 6 + (s["legal_balls"] % 6) / 10
    s["economy"] = 6 * s["runs_conceded"] / s["legal_balls"].where(s["legal_balls"] > 0)
    s["bowl_avg"] = s["runs_conceded"] / s["wickets"].where(s["wickets"] > 0)
    s["bowl_sr"] = s["legal_balls"] / s["wickets"].where(s["wickets"] > 0)
    s["dot_pct"] = 100 * s["dots"] / s["legal_balls"].where(s["legal_balls"] > 0)
    s["balls_faced_pm"] = s["balls_faced"] / s["matches"]
    s["balls_bowled_pm"] = s["legal_balls"] / s["matches"]
    teams = pm.sort_values("start_date").groupby("player")["team"].agg(lambda x: x.iloc[-1])
    s["latest_team"] = teams
    return s.reset_index()


def classify(stats, bat_bpm=8.0, bowl_bpm=9.0, min_matches=10):
    """Transparent, configurable role rule (no role metadata in the source data).
    Bats regularly  : balls faced per match >= bat_bpm
    Bowls regularly : legal balls bowled per match >= bowl_bpm
    """
    bats = stats["balls_faced_pm"] >= bat_bpm
    bowls = stats["balls_bowled_pm"] >= bowl_bpm
    role = pd.Series("Limited role", index=stats.index)
    role[bats & ~bowls] = "Batter"
    role[bowls & ~bats] = "Bowler"
    role[bats & bowls] = "All-rounder"
    role[stats["matches"] < min_matches] = "Insufficient sample"
    return role
