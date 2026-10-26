import pandas as pd
import plotly.express as px
import streamlit as st
from components import ui
from core import data as D


def main():
    ui.header("Part 1 vs Part 2", "Raw vs cleaned data",
              "What changed between the raw Cricsheet file (Phase 1) and the cleaned dataset (Phase 2), and which transformation caused it.")
    cmp, miss, sch = D.table("audit_comparison.parquet"), D.table("audit_missing.parquet"), D.table("audit_schema.parquet")
    ui.note("<b>Precomputed.</b> Every figure here was computed by the build step directly from the raw file and the verified, "
            "byte-identical rebuilt Phase 2 file — same columns, same definitions. Fewer rows is not treated as an improvement by itself.")
    metric = ui.multi("Metrics to chart", cmp.metric.unique(), "f_cmp_metrics")
    ui.active_filters(Metrics=metric)

    t = cmp.copy()
    t["change"] = t.phase2_cleaned - t.phase1_raw
    t["change_pct"] = (100 * t.change / t.phase1_raw.where(t.phase1_raw != 0)).round(3)
    st.markdown("### Before / after")
    ui.table(t.rename(columns={"phase1_raw": "Phase 1 · raw", "phase2_cleaned": "Phase 2 · cleaned"}), hide_index=True, width="stretch",
                 column_config={"Phase 1 · raw": st.column_config.NumberColumn(format="%d"), "Phase 2 · cleaned": st.column_config.NumberColumn(format="%d")})
    ui.download(t, "part1_vs_part2_comparison")

    sel = t[ui.isin(t.metric, metric)] if metric else t[t.metric.isin(["Team names", "Venue names", "Season labels", "Super-over rows",
                                                                      "Repeated (match, innings, ball) keys", "Exact duplicate rows"])]
    m = sel.melt(["metric", "cause"], ["phase1_raw", "phase2_cleaned"], var_name="stage", value_name="value")
    m["stage"] = m.stage.map({"phase1_raw": "Phase 1 · raw", "phase2_cleaned": "Phase 2 · cleaned"})
    ui.chart(px.bar(m, x="value", y="metric", color="stage", barmode="group", orientation="h", hover_data={"cause": True},
                    title="Selected metrics before and after cleaning", labels={"value": "Count", "metric": ""}),
             height=max(300, 70 * sel.shape[0]))

    st.markdown("### Missing values per column")
    mm = miss.pivot(index="column", columns="dataset", values="missing_pct").reset_index().fillna(0)
    mm["difference (pp)"] = (mm["Phase 2 · cleaned"] - mm["Phase 1 · raw"]).round(4)
    long = miss[miss.missing > 0]
    ui.chart(px.bar(long, x="missing_pct", y="column", color="dataset", barmode="group", orientation="h",
                    title="Missing values (% of rows) — columns with any blanks", labels={"missing_pct": "% of rows", "column": ""}), height=560)
    ui.table(mm, hide_index=True, width="stretch")
    ui.note("Percentages barely move because cleaning removed rows (super overs) and renamed values — it did not fill blanks. "
            "Blanks in `wides`, `wicket_type`, `fielder_*` mean <i>not applicable</i>.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Schema changes")
        ui.table(sch, hide_index=True, width="stretch", height=380)
    with c2:
        st.markdown("### Records excluded: super overs")
        so = D.table("audit_super_overs.csv")
        ui.table(so, hide_index=True, width="stretch", height=380)
        st.caption(f"{int(so.super_over_rows.sum())} deliveries from {len(so)} matches. The matches themselves stay in the data.")

    st.markdown("### Mapping changes")
    tn, vn = D.table("audit_team_names.csv"), D.table("audit_venue_names.csv")
    idt = D.table("audit_player_identity.csv")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Teams**")
        ui.table(tn[tn.changed][["name", "standardized", "rows"]], hide_index=True, width="stretch")
    with c2:
        st.markdown("**Players**")
        ui.table(idt[["name", "registry_id", "merged_in_v1_1", "verdict"]], hide_index=True, width="stretch")
    with c3:
        st.markdown("**Venues** (precomputed mapping)")
        ui.table(vn[vn.changed][["venue", "standardized", "matches"]], hide_index=True, width="stretch", height=300)

    st.markdown("### Still unresolved after cleaning")
    ck = D.table("audit_checks.parquet")
    ui.status_table(ck[ck.status.isin(["WARN", "FAIL", "NOT REPRODUCED"])], ["id", "check", "value", "status", "category", "evidence"])


ui.guard(main)
