import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D

CATEGORY_HELP = {
    "Recomputed from source": "Re-run by the build step on the raw Cricsheet file or the verified rebuilt data.",
    "Legitimate repeated key": "Looks like a duplicate key, but the evidence shows distinct, valid deliveries.",
    "Confirmed data error (fixed)": "A real problem in the source, corrected with documented evidence.",
    "Unresolved anomaly": "Recorded as-is in the source; cannot be confirmed or corrected from the available data.",
    "Precomputed mapping": "A mapping recovered from an earlier output rather than re-derived independently.",
    "Reported, not reproduced": "A claim from the earlier Phase 6 report that could not be independently reproduced.",
}


def main():
    ui.header("Part 1 · original data", "Data quality audit",
              "Checks on the raw Cricsheet ball-by-ball file (Phase 1), recomputed from source — not copied from earlier reports.")
    checks, man = D.table("audit_checks.parquet"), D.manifest()
    areas = ui.multi("Check area", checks.area.unique(), "f_audit_area")
    cats = ui.multi("Evidence category", checks.category.unique(), "f_audit_cat")
    stats = ui.multi("Status", checks.status.unique(), "f_audit_status")
    ui.active_filters(Area=areas, Category=cats, Status=stats)

    c = checks[ui.isin(checks.area, areas) & ui.isin(checks.category, cats) & ui.isin(checks.status, stats)]
    rs = man["raw_summary"]
    n = checks.status.value_counts()
    ui.kpi_row([
        dict(label="Raw dataset", value=f"{rs['rows']:,} × {rs['columns']}", sub=f"{rs['matches']:,} matches · {rs['first_date']} → {rs['last_date']}"),
        dict(label="Checks passed", value=f"{n.get('PASS', 0)} / {len(checks)}", sub=f"{n.get('INFO', 0)} informational"),
        dict(label="Warnings · failures", value=f"{n.get('WARN', 0)} · {n.get('FAIL', 0)}", sub="WARN = unresolved source anomaly"),
        dict(label="Not reproduced", value=str(n.get("NOT REPRODUCED", 0)), sub="Earlier-report claims without surviving evidence"),
    ])
    with st.expander("How to read the evidence categories", expanded=False):
        for k, v in CATEGORY_HELP.items():
            st.markdown(f"**{k}** — {v}")

    st.markdown("### Validation summary")
    if not ui.empty_or(c):
        ui.status_table(c, ["id", "area", "check", "scope", "value", "rows_affected", "status", "category", "evidence"])
        ui.download(c, "part1_validation_checks")

    tabs = st.tabs(["Schema & files", "Missing values", "Repeated delivery keys", "Delivery order", "Team & player mapping", "Earlier report"])
    with tabs[0]:
        sch = D.table("audit_schema.parquet")
        raw_cols = sch[sch.raw_dtype.notna()][["column", "raw_dtype"]]
        st.markdown(f"**{len(raw_cols)} raw columns.** Numeric extras (`wides`, `noballs`, …) are floats because they are blank when not applicable.")
        st.dataframe(raw_cols, hide_index=True, width="stretch", height=300)
        inv = D.table("audit_inventory.csv")
        st.markdown("**Recovered archive inventory**")
        st.dataframe(inv, hide_index=True, width="stretch")
        ui.download(inv, "part1_file_inventory", key="dl_inv")
    with tabs[1]:
        m = D.table("audit_missing.parquet")
        m = m[m.dataset == "Phase 1 · raw"].sort_values("missing_pct", ascending=False)
        fig = px.bar(m, x="missing_pct", y="column", orientation="h", title="Missing values by column — raw file",
                     labels={"missing_pct": "Missing (% of rows)", "column": ""}, hover_data={"missing": ":,", "blank_strings": True})
        fig.update_yaxes(categoryorder="total ascending")
        ui.chart(fig, height=620)
        ui.note("<b>Blank ≠ error.</b> `wides`, `byes`, `wicket_type`, `fielder_*` are blank on deliveries where they do not apply. "
                "`other_wicket_type` and `other_player_dismissed` are blank on every row. Identifier and run columns are complete.")
        ui.download(m, "part1_missing_values", key="dl_miss")
    with tabs[2]:
        rk = D.table("audit_repeated_keys.csv")
        ui.note("<b>42 repeated keys, all legitimate.</b> The source numbers every delivery in an over, wides and no-balls included. "
                "When an over reaches its 10th delivery the source writes <code>6.10</code>, which a numeric reader turns into <code>6.1</code> — "
                "colliding with the real first ball. Both rows are distinct deliveries (different <code>actual_delivery</code>), so they are "
                "<b>kept, not deduplicated</b>.")
        ui.kpi_row([dict(label="Keys", value=str(rk[["match_id", "innings", "ball"]].drop_duplicates().shape[0]), sub="(match, innings, ball)"),
                    dict(label="Rows involved", value=str(len(rk)), sub="2 per key"),
                    dict(label="Wide / no-ball rows", value=str(int(rk.is_wide_or_noball.sum())), sub="extras that lengthened the over"),
                    dict(label="Unresolved", value=str(int((rk.status == "UNRESOLVED").sum())), sub="keys without an explanation")])
        ui.chart(px.histogram(rk.drop_duplicates(["match_id", "innings", "ball"]), x="deliveries_in_over", title="Deliveries in the affected overs",
                              labels={"deliveries_in_over": "Deliveries in over (incl. wides/no-balls)", "count": "Overs"}), height=280)
        st.dataframe(rk.drop(columns=["status"]), hide_index=True, width="stretch", height=360)
        ui.download(rk, "part1_repeated_delivery_keys", key="dl_rk")
    with tabs[3]:
        an = D.table("audit_over_anomalies.csv")
        ui.note("<b>Interpretation.</b> <code>ball</code> = over + n/10 where n counts <i>every</i> delivery. <code>actual_delivery</code> = over + "
                "(legal balls already bowled + 1)/10, so a wide and the re-bowled ball share a label. Sorting by (over, n read as text) reproduces "
                "the source file order in every innings. The corrected order lives in a separate derived dataset; original identifiers are untouched.")
        st.markdown("**Overs the source records with an unusual legal-ball count** (unresolved; kept as recorded)")
        st.dataframe(an, hide_index=True, width="stretch")
        ui.download(an, "part1_over_anomalies", key="dl_an")
    with tabs[4]:
        tn = D.table("audit_team_names.csv")
        st.markdown("**Franchise names in the raw file** — 4 renames are mapped to the current name; originals are preserved.")
        st.dataframe(tn, hide_index=True, width="stretch")
        idt = D.table("audit_player_identity.csv")
        st.markdown("**Player identity audit** — Cricsheet registry ids decide whether two names are one person.")
        st.dataframe(idt, hide_index=True, width="stretch")
        vn = D.table("audit_venue_names.csv")
        st.markdown("**Venue names** — mapping recovered from the original Phase 2 output (precomputed, not independently derived).")
        st.dataframe(vn.sort_values(["standardized", "venue"]), hide_index=True, width="stretch", height=320)
        c1, c2, c3 = st.columns(3)
        with c1: ui.download(tn, "part1_team_names", key="dl_tn")
        with c2: ui.download(idt, "part1_player_identity", key="dl_id")
        with c3: ui.download(vn, "part1_venue_names", key="dl_vn")
    with tabs[5]:
        old = man["old_phase6_report"]
        ui.note("<b>Earlier Phase 6 claims.</b> The recovered report was built on a reconstructed scoring table that used the wrong rules "
                "(dot ball = 1 point, no milestone bonuses or duck penalty, super-over balls included). Its baseline numbers reproduce exactly; "
                "its XGBoost numbers cannot be reproduced because the model and code were lost.")
        st.dataframe(pd.DataFrame(old["xgb_test"]), hide_index=True, width="stretch")
        disc = man["scoring_discrepancy_summary"]
        st.markdown(f"**Reconstruction vs original scoring:** {disc['rows_differing_total']:,} player-match rows differ; "
                    f"{disc['rows_differing_without_any_attributed_cause']} unexplained.")
        st.dataframe(pd.DataFrame([{"cause": k, "rows": v} for k, v in disc["rows_by_cause_overlapping"].items()]), hide_index=True)


ui.guard(main)
