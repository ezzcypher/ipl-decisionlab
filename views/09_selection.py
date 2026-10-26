import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import auction as A
from core import data as D
from core import roles as R

UPLOAD_KEY = "auction_csv_bytes"  # not an f_ key: "Reset filters" keeps the uploaded file


def z(s):
    return A.zscore(s)


def performance_tab(pm, pr, mets, seasons, role_f, teams, th):
    with st.expander("Ranking weights", expanded=False):
        c = st.columns(4)
        w_avg = c[0].slider("Average points", 0.0, 1.0, 0.4, 0.05, key="f_w_avg")
        w_form = c[1].slider("Recent form (last 5)", 0.0, 1.0, 0.3, 0.05, key="f_w_form")
        w_cons = c[2].slider("Consistency (low CV)", 0.0, 1.0, 0.2, 0.05, key="f_w_cons")
        w_part = c[3].slider("Participation (matches)", 0.0, 1.0, 0.1, 0.05, key="f_w_part")
    f = ui.apply(pm, seasons=seasons)
    s = R.add_roles(D.player_stats(f), f, th)
    form = f.sort_values("start_date").groupby("player").pts.apply(lambda x: x.tail(5).mean()).rename("form_last5")
    s = s.merge(form, on="player")
    s = s[(s.matches >= th["min_matches"]) & ui.isin(s.role, role_f) & ui.isin(s.latest_team, teams)].copy()
    if ui.empty_or(s, "No players meet the filters. Lower the minimum matches or widen the seasons."):
        return
    s["score"] = w_avg * z(s.avg_pts) + w_form * z(s.form_last5) - w_cons * z(s.cv.fillna(s.cv.max())) + w_part * z(s.matches)
    est = pr[pr.split == "test"].groupby("player")[mets["prediction_columns"]["Ridge regression"]].mean().rename("ridge_test_mean")
    s = s.merge(est, on="player", how="left").sort_values("score", ascending=False)
    s.insert(0, "rank", range(1, len(s) + 1))
    st.latex(r"\text{score} = %.2f\,z(\text{avg}) + %.2f\,z(\text{form}_5) - %.2f\,z(\text{CV}) + %.2f\,z(\text{matches})" % (w_avg, w_form, w_cons, w_part))
    st.caption("z(x) = (x − mean) ÷ sd across the players shown. Higher CV = more volatile, so it is subtracted. Historical evidence only — not a forecast.")
    top = s.head(15)
    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(top, x="score", y="player", color="role", orientation="h", color_discrete_map=ui.role_colors(),
                     hover_data={"avg_pts": ":.1f", "form_last5": ":.1f", "cv": ":.2f", "matches": True},
                     title="Top 15 by weighted score", labels={"score": "Weighted score (z units)", "player": ""})
        fig.update_yaxes(categoryorder="total ascending")
        ui.chart(fig, height=460)
    with c2:
        ui.chart(px.scatter(s, x="avg_pts", y="cv", color="role", hover_name="player", size="matches", size_max=14, color_discrete_map=ui.role_colors(),
                            title="Reward vs risk", labels={"avg_pts": "Average points", "cv": "Volatility (CV)"}), height=460)
    cols = ["rank", "player", "role", "latest_team", "score", "matches", "avg_pts", "form_last5", "cv", "ridge_test_mean", "median_pts", "max_pts"]
    ui.table(s[cols].rename(columns={"ridge_test_mean": "ridge_mean_2024_26_retro"}), key="rank_tbl")
    short = st.multiselect("Shortlist", s.player, key="f_shortlist", placeholder="Pick players to shortlist")
    c1, c2 = st.columns(2)
    with c1:
        ui.download(s[cols], "ranked_players", label="Download ranking CSV")
    with c2:
        if short:
            ui.download(s[s.player.isin(short)][cols], "shortlist", label=f"Download shortlist ({len(short)})", key="dl_short")


def auction_tab(pm, players, th, role_f):
    st.markdown("#### Auction prices — your data only")
    ui.note("<b>No auction prices ship with this project.</b> Upload a CSV of <i>real</i> historical prices with a citable source. Prices are never "
            "converted between currencies or invented. Players are matched by Cricsheet registry id, or by an exact name — never by similarity.")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download CSV template", A.template_csv(), "auction_prices_template.csv", "text/csv", key="dl_tpl")
    c2.download_button("Download player-ID lookup", players[["player", "registry_id", "merged_aliases", "matches", "first_match", "last_match"]]
                       .assign(first_match=lambda d: d.first_match.dt.date, last_match=lambda d: d.last_match.dt.date).to_csv(index=False).encode(),
                       "player_registry_ids.csv", "text/csv", key="dl_ids")
    if c3.button("Clear uploaded prices", key="clear_prices"):
        st.session_state.pop(UPLOAD_KEY, None)
        st.rerun()
    with st.expander("CSV schema"):
        ui.table(A.schema_table(), key="schema_tbl", sort=False)
    up = st.file_uploader("Upload auction prices (CSV)", type="csv", key="auction_uploader")
    if up is not None:
        st.session_state[UPLOAD_KEY] = up.getvalue()
    raw = st.session_state.get(UPLOAD_KEY)
    if raw is None:
        st.info("Auction-value calculations are unavailable until you upload a price file. The performance shortlist works without it.")
        return

    rows, issues, fatal = A.parse(raw)
    if fatal:
        st.error("The file was rejected: " + "; ".join(issues.issue))
        return
    rows, more = A.finalize(rows, players)
    issues = pd.concat([issues, more], ignore_index=True)
    issues = issues.assign(_o=issues.severity.map({"error": 0, "warning": 1})).sort_values(["_o", "row"], na_position="first").drop(columns="_o")
    if rows.example.any():
        st.warning(f"⚠ {int(rows.example.sum())} row(s) are marked EXAMPLE / SYNTHETIC / DEMO. They are **not real auction prices** — "
                   "every chart below that uses them is illustrative only.")
    n_err, n_warn = int((issues.severity == "error").sum()), int((issues.severity == "warning").sum())
    ui.kpi_row([
        dict(label="Rows in file", value=str(len(rows)), sub=f"{int(rows.valid.sum())} valid"),
        dict(label="Matched players", value=str(int((rows.valid & rows.matched_player.notna()).sum())),
             sub=f"{int((rows.matched_by == 'registry id').sum())} by id · {int((rows.matched_by == 'exact name').sum())} by exact name"),
        dict(label="Unmatched", value=str(int(rows.matched_player.isna().sum())), sub="reported below, never guessed"),
        dict(label="Errors · warnings", value=f"{n_err} · {n_warn}", sub="error rows are excluded"),
    ])
    if len(issues):
        with st.expander(f"Validation report ({len(issues)} issues)", expanded=n_err > 0):
            ui.table(issues, key="issues_tbl")
            ui.download(issues, "auction_validation_issues", key="dl_issues")
    um = rows[rows.matched_player.isna()]
    if len(um):
        with st.expander(f"Unmatched players ({len(um)})"):
            ui.table(um[["row", "player", "registry_id", "season", "matched_by"]], key="um_tbl")
            ui.download(um, "auction_unmatched", key="dl_um")

    v = A.value_table(rows, pm)
    if ui.empty_or(v, "No valid, matched rows to analyse."):
        return
    ev = R.evidence(pm)
    ev["role"], _ = R.classify(ev, **th)
    v = v.merge(ev[["player", "role"]], left_on="matched_player", right_on="player", how="left", suffixes=("", "_r")).drop(columns="player_r")
    v["role"] = v.role.fillna("Unknown")
    cur = sorted(v.currency.unique())
    c1, c2, c3 = st.columns(3)
    currency = c1.selectbox("Currency (prices are never mixed)", cur, key="f_auc_cur")
    seas = c2.multiselect("Auction season", sorted(v.season.astype(int).unique()), key="f_auc_season", placeholder="All")
    fr = c3.multiselect("Franchise", sorted(x for x in v.franchise.unique() if x), key="f_auc_fr", placeholder="All")
    q = v[(v.currency == currency) & ui.isin(v.season.astype(int), seas) & ui.isin(v.franchise, fr) & ui.isin(v.role, role_f)]
    search = st.text_input("Search player", key="f_auc_search", placeholder="Type part of a name")
    if search:
        q = q[q.matched_player.str.contains(search, case=False, regex=False) | q.player.str.contains(search, case=False, regex=False)]
    if ui.empty_or(q):
        return
    unit = currency.replace("_", " ")
    label = "illustrative (EXAMPLE rows)" if q.example.any() else "actual historical prices (user-supplied)"
    st.caption(f"Showing {len(q)} rows · {label} · unit: {unit}. Season points = fantasy points scored in the auction season itself.")
    cols = ["season", "matched_player", "role", "franchise", "auction_status", "base_price", "sold_price", "season_matches", "season_pts",
            "season_avg", "prior_matches", "prior_avg", "price_per_point", "points_per_price_unit", "value_note", "matched_by"]
    ui.table(q[cols], key="auction_tbl")
    st.caption("Sources in view: " + " · ".join(sorted(q.source.unique())[:6]))
    ui.download(q[cols + ["source"]], "auction_prices_filtered", label="Download filtered auction table")

    sold = q[q.sold_price.notna()]
    c1, c2 = st.columns(2)
    with c1:
        b = sold[sold.base_price.notna()]
        fig = None if b.empty else px.scatter(b, x="base_price", y="sold_price", color="role", color_discrete_map=ui.role_colors(), hover_name="matched_player",
                                              hover_data={"franchise": True, "season": True}, title=f"Sold vs base price ({unit})",
                                              labels={"base_price": f"Base price ({unit})", "sold_price": f"Sold price ({unit})"})
        if fig is not None:
            hi = float(max(b.base_price.max(), b.sold_price.max()))
            fig.add_scatter(x=[0, hi], y=[0, hi], mode="lines", name="sold = base", line=dict(dash="dash", color=ui.series(4)))
        ui.chart(fig, height=380, empty="No rows with both base and sold price.")
    with c2:
        ui.chart(None if sold.empty else px.box(sold.assign(season=sold.season.astype(int).astype(str)), x="season", y="sold_price", points="all",
                                                hover_name="matched_player", title=f"Sold price by season ({unit})",
                                                labels={"season": "Auction season", "sold_price": f"Sold price ({unit})"}), height=380)
    c1, c2 = st.columns(2)
    with c1:
        fb = sold[sold.franchise != ""]
        ui.chart(None if fb.empty else px.box(fb, x="franchise", y="sold_price", points="all", hover_name="matched_player",
                                              title=f"Sold price by franchise ({unit})", labels={"franchise": "", "sold_price": f"Sold price ({unit})"}),
                 height=380, empty="No franchise column in the file.")
    with c2:
        pp = sold[sold.season_matches > 0]
        ui.chart(None if pp.empty else px.scatter(pp, x="sold_price", y="season_avg", size="season_matches", color="role", color_discrete_map=ui.role_colors(),
                                                  hover_name="matched_player", hover_data={"season": True, "season_pts": ":.0f"},
                                                  title="Price vs performance in the auction season",
                                                  labels={"sold_price": f"Sold price ({unit})", "season_avg": "Fantasy points per match that season"}),
                 height=380, empty="No priced player played in the auction season.")
    ui.note("<b>Value metrics.</b> Price per point = sold price ÷ total fantasy points scored in the auction season; points per price unit is the "
            "inverse. Blank when the price is missing or zero, the player did not play, or season points ≤ 0. Past value is not future value.")

    names = st.multiselect("Compare players", sorted(q.matched_player.unique()), max_selections=4, key="f_auc_cmp", placeholder="Pick up to 4")
    if names:
        cmpd = q[q.matched_player.isin(names)]
        ui.chart(px.bar(cmpd.assign(season=cmpd.season.astype(int).astype(str)), x="season", y="sold_price", color="matched_player", barmode="group",
                        category_orders={"matched_player": names}, title=f"Sold price by season ({unit})",
                        labels={"season": "Auction season", "sold_price": f"Sold price ({unit})", "matched_player": ""}), height=340)

    priced = q[q.sold_price.notna() & (q.sold_price > 0) & q.prior_avg.notna()]
    st.markdown("#### Auction shortlist score")
    if len(priced) < 5:
        st.info("The shortlist score needs at least 5 priced players with pre-auction history in the current view.")
        return
    c = st.columns(5)
    w = dict(w_perf=c[0].slider("Prior avg points", 0.0, 1.0, 0.5, 0.05, key="f_aw_perf"),
             w_cons=c[1].slider("Prior consistency", 0.0, 1.0, 0.2, 0.05, key="f_aw_cons"),
             w_role=c[2].slider("Role preference", 0.0, 1.0, 0.1, 0.05, key="f_aw_role"),
             w_price=c[3].slider("Price (cheaper ↑)", 0.0, 1.0, 0.2, 0.05, key="f_aw_price"))
    pref = c[4].multiselect("Preferred roles", R.ROLES, key="f_aw_pref")
    sc = A.shortlist_score(priced, preferred_roles=pref, **w).sort_values("score", ascending=False)
    st.latex(r"\text{score} = %.2f\,z(\overline{pts}_{prior}) - %.2f\,z(CV_{prior}) + %.2f\,[\text{preferred role}] - %.2f\,z(\text{price})"
             % (w["w_perf"], w["w_cons"], w["w_role"], w["w_price"]))
    st.caption("Uses only evidence available before each auction (seasons before the auction season) plus the price paid. "
               "A decision aid with your weights — not an official or market valuation.")
    scols = ["matched_player", "season", "role", "franchise", "sold_price", "prior_matches", "prior_avg", "prior_cv", "score"]
    ui.table(sc[scols], key="auc_score")
    pick = st.multiselect("Auction shortlist", sc.matched_player.unique(), key="f_auc_short", placeholder="Pick players")
    if pick:
        ui.download(sc[sc.matched_player.isin(pick)][scols], "auction_shortlist", label=f"Download auction shortlist ({len(pick)})", key="dl_auc_short")


def main():
    ui.header("Decisions", "Selection & auction support",
              "Rank players on historical evidence with weights you control, and analyse auction prices you supply. A decision aid — not a guarantee.")
    pm, pr, mets, players = D.player_match(), D.predictions(), D.metrics(), D.table("players.parquet")
    seasons = ui.season_filter(pm.season_year)
    role_f = ui.multi("Role", R.ROLES, "f_roles")
    teams = ui.multi("Latest team in view", pm.team.unique(), "f_teams")
    th = R.thresholds()
    ui.active_filters(Seasons=f"{seasons[0]}–{seasons[1]}", Roles=role_f, Teams=teams, **{"Min matches": th["min_matches"]})
    t1, t2 = st.tabs(["Performance shortlist", "Auction prices & value"])
    with t1:
        performance_tab(pm, pr, mets, seasons, role_f, teams, th)
    with t2:
        auction_tab(pm, players, th, role_f)


ui.guard(main)
