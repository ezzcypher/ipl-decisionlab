"""User-supplied IPL auction prices: schema, template, validation, identity matching, value metrics.

The project ships NO auction prices. Everything here operates only on a CSV the user uploads.
Matching never uses fuzzy names: Cricsheet registry id first, then an exact canonical name or exact known alias.
"""
import io
import numpy as np
import pandas as pd

COLUMNS = {
    "player": ("text", "Player name as written in your source. Required if registry_id is blank."),
    "registry_id": ("text", "Cricsheet registry id (preferred, stable). Download the player-ID lookup to fill it."),
    "season": ("integer", "Auction season, calendar year (e.g. 2025). Required."),
    "franchise": ("text", "Buying / retaining franchise (optional)."),
    "base_price": ("number ≥ 0", "Base price in `currency` units (optional)."),
    "sold_price": ("number ≥ 0", "Final price in `currency` units. Required when auction_status = sold or retained."),
    "auction_status": ("sold | unsold | retained | withdrawn", "Optional; blank means unknown."),
    "currency": ("text", "Unit of the prices, e.g. INR_lakh or INR_crore. Required; values are never converted."),
    "source": ("text", "Where the price comes from (URL or publication). Required. Rows marked EXAMPLE are examples."),
}
REQUIRED = ["season", "currency", "source"]
STATUSES = {"sold", "unsold", "retained", "withdrawn"}
EXAMPLE_MARKERS = ("EXAMPLE", "SYNTHETIC", "DEMO")


def template_csv():
    ex = pd.DataFrame([
        {"player": "EXAMPLE — Player name", "registry_id": "", "season": 2025, "franchise": "EXAMPLE — Franchise", "base_price": 200,
         "sold_price": 450, "auction_status": "sold", "currency": "INR_lakh", "source": "EXAMPLE — replace with a real, citable source"},
        {"player": "EXAMPLE — Another player", "registry_id": "", "season": 2025, "franchise": "", "base_price": 100,
         "sold_price": "", "auction_status": "unsold", "currency": "INR_lakh", "source": "EXAMPLE — not a real price"},
    ], columns=list(COLUMNS))
    return ex.to_csv(index=False).encode()


def schema_table():
    return pd.DataFrame([{"column": k, "type": t, "required": "yes" if k in REQUIRED else ("player or registry_id" if k in ("player", "registry_id") else "no"),
                          "description": d} for k, (t, d) in COLUMNS.items()])


def is_example(df):
    txt = df[["player", "source"]].astype(str).agg(" ".join, axis=1).str.upper()
    return txt.apply(lambda s: any(m in s for m in EXAMPLE_MARKERS))


def parse(raw_bytes_or_df):
    """Returns (rows, issues, fatal). rows keep a `row` number (1 = first data line); issues lists every problem."""
    try:
        df = raw_bytes_or_df.copy() if isinstance(raw_bytes_or_df, pd.DataFrame) else pd.read_csv(io.BytesIO(raw_bytes_or_df), dtype=str, keep_default_na=False)
    except Exception as e:  # noqa: BLE001 — malformed file
        return None, pd.DataFrame([{"row": None, "severity": "error", "issue": f"could not read CSV: {e}"}]), True
    df.columns = [c.strip().lower() for c in df.columns]
    issues = []
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing or not ({"player", "registry_id"} & set(df.columns)):
        msg = f"missing required columns: {', '.join(missing + ([] if {'player', 'registry_id'} & set(df.columns) else ['player or registry_id']))}"
        return None, pd.DataFrame([{"row": None, "severity": "error", "issue": msg}]), True
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[list(COLUMNS)].astype(str).apply(lambda s: s.str.strip())
    df.insert(0, "row", range(1, len(df) + 1))
    if df.empty:
        return df, pd.DataFrame([{"row": None, "severity": "error", "issue": "file has no data rows"}]), True
    df["valid"] = True

    def bad(mask, sev, text):
        for r in df.loc[mask, "row"]:
            issues.append({"row": int(r), "severity": sev, "issue": text})
        if sev == "error":
            df.loc[mask, "valid"] = False

    bad((df.player == "") & (df.registry_id == ""), "error", "neither player nor registry_id given")
    yr = pd.to_numeric(df.season, errors="coerce")
    bad(yr.isna() | (yr % 1 != 0) | ~yr.between(2008, 2100), "error", "season is not a valid year")
    df["season"] = yr
    bad(df.currency == "", "error", "currency missing")
    bad(df.source == "", "error", "source missing")
    for c in ("base_price", "sold_price"):
        v = pd.to_numeric(df[c].str.replace(",", ""), errors="coerce")
        bad((df[c] != "") & v.isna(), "error", f"{c} is not a number")
        bad(v < 0, "error", f"{c} is negative")
        df[c] = v
    st = df.auction_status.str.lower()
    bad((st != "") & ~st.isin(STATUSES), "error", "auction_status must be sold, unsold, retained or withdrawn")
    df["auction_status"] = st
    bad(st.isin(["sold", "retained"]) & df.sold_price.isna(), "error", "sold/retained row without sold_price")
    bad(st.isin(["unsold", "withdrawn"]) & df.sold_price.notna(), "warning", "unsold/withdrawn row has a sold_price (ignored)")
    df.loc[st.isin(["unsold", "withdrawn"]), "sold_price"] = np.nan
    bad(df.sold_price.notna() & df.base_price.notna() & (df.sold_price < df.base_price), "warning", "sold_price below base_price — check the source")
    bad(df.sold_price == 0, "warning", "sold_price is 0 — value metrics will be blank for this row")
    df["example"] = is_example(df)
    if df.example.any():  # one summary line, not one per row
        issues.append({"row": None, "severity": "warning",
                       "issue": f"{int(df.example.sum())} row(s) marked EXAMPLE/SYNTHETIC/DEMO — not real prices"})
    return df, pd.DataFrame(issues, columns=["row", "severity", "issue"]), False


def match(df, players):
    """Adds `matched_player` and `matched_by`. Registry id first; then exact canonical name or exact known alias."""
    reg = {}
    for r in players.itertuples():
        for i in str(r.registry_id).split("|"):
            if i:
                reg[i] = r.player
    names = {p: p for p in players.player}
    for r in players.itertuples():
        for a in (r.merged_aliases.split(", ") if isinstance(r.merged_aliases, str) else []):
            if a:
                names[a] = r.player
    out = df.copy()
    by_id = out.registry_id.map(reg)
    by_name = out.player.map(names)
    out["matched_player"] = by_id.where(out.registry_id != "", by_name)
    out["matched_by"] = np.where(out.registry_id != "", np.where(by_id.notna(), "registry id", "unmatched (id not found)"),
                                 np.where(by_name.notna(), "exact name", "unmatched (no exact name)"))
    named = out.player.map(names)
    out["id_name_conflict"] = (out.registry_id != "") & by_id.notna() & named.notna() & (named != by_id)
    return out


def finalize(df, players):
    """Parse → match → duplicate check. Returns (rows, issues)."""
    m = match(df, players)
    issues = []
    for r in m.loc[m.id_name_conflict, "row"]:
        issues.append({"row": int(r), "severity": "warning", "issue": "registry_id and player name point to different players (id used)"})
    for r in m.loc[m.valid & m.matched_player.isna(), "row"]:
        issues.append({"row": int(r), "severity": "warning", "issue": "player not matched to the dataset (kept, excluded from value metrics)"})
    cand = m.valid & m.matched_player.notna()
    dup = cand & m[cand].duplicated(["matched_player", "season", "currency"], keep=False).reindex(m.index, fill_value=False)
    for r in m.loc[dup, "row"]:
        issues.append({"row": int(r), "severity": "error", "issue": "duplicate player + season + currency (all copies excluded)"})
    m.loc[dup, "valid"] = False
    return m, pd.DataFrame(issues, columns=["row", "severity", "issue"])


def value_table(rows, pm):
    """Season performance next to price. Price per point = sold_price ÷ fantasy points scored in the auction season."""
    ok = rows[rows.valid & rows.matched_player.notna()].copy()
    if ok.empty:
        return ok
    season = pm.groupby(["player", "season_year"]).agg(season_matches=("match_id", "nunique"), season_pts=("pts", "sum"),
                                                       season_avg=("pts", "mean")).reset_index()
    ok = ok.merge(season, left_on=["matched_player", "season"], right_on=["player", "season_year"], how="left", suffixes=("", "_pm"))
    prior = []
    for r in ok.itertuples():
        h = pm[(pm.player == r.matched_player) & (pm.season_year < r.season)]
        prior.append((len(h), h.pts.mean() if len(h) else np.nan, h.pts.std(ddof=0) / h.pts.mean() if len(h) > 1 and h.pts.mean() > 0 else np.nan))
    ok[["prior_matches", "prior_avg", "prior_cv"]] = pd.DataFrame(prior, index=ok.index)
    ok["season_matches"] = ok.season_matches.fillna(0).astype(int)
    ok["season_pts"] = ok.season_pts.fillna(0.0)
    pos = ok.sold_price.notna() & (ok.sold_price > 0)
    ok["price_per_point"] = np.where(pos & (ok.season_pts > 0), ok.sold_price / ok.season_pts.where(ok.season_pts > 0), np.nan)
    ok["points_per_price_unit"] = np.where(pos, ok.season_pts / ok.sold_price.where(pos), np.nan)
    ok["value_note"] = np.select([~pos, ok.season_matches == 0, ok.season_pts <= 0],
                                 ["no positive sold price", "did not play that season", "non-positive season points"], "")
    return ok.drop(columns=["player_pm", "season_year"], errors="ignore")


def zscore(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd == sd else s * 0.0


def shortlist_score(v, w_perf=0.5, w_cons=0.2, w_role=0.1, w_price=0.2, preferred_roles=()):
    """Pre-auction evidence only: prior average, prior consistency, role preference, price (cheaper = higher)."""
    s = v.copy()
    s["role_bonus"] = s.role.isin(preferred_roles).astype(float) if preferred_roles else 0.0
    s["score"] = (w_perf * zscore(s.prior_avg.fillna(s.prior_avg.median())) - w_cons * zscore(s.prior_cv.fillna(s.prior_cv.max()))
                  + w_role * s.role_bonus - w_price * zscore(s.sold_price))
    return s
