"""IPL DecisionLab — Phase 7 dashboard entry point.  Run: streamlit run app.py"""
import streamlit as st
from core import theme, theme_switch

st.set_page_config(page_title="IPL DecisionLab", page_icon="🏏", layout="wide", initial_sidebar_state="auto")

if "theme" not in st.session_state:
    st.session_state.theme = "dark"
mode = st.session_state.theme
theme_switch.install()  # native widgets follow this session's theme (see core/theme_switch.py)
st.markdown(theme.css(mode), unsafe_allow_html=True)

st.logo("assets/logo.svg", icon_image="assets/icon.svg", size="large")
with st.sidebar:
    dark = st.toggle("Dark mode", value=mode == "dark", key="theme_toggle")
    if dark != (mode == "dark"):
        st.session_state.theme = "dark" if dark else "light"
        st.rerun()

P = "views/"
nav = st.navigation({
    "Overview": [st.Page(P + "01_overview.py", title="Executive overview", icon=":material/space_dashboard:", default=True)],
    "Data": [st.Page(P + "02_data_audit.py", title="Part 1 · Data quality audit", icon=":material/fact_check:"),
             st.Page(P + "03_eda.py", title="Part 2 · EDA & cleaning", icon=":material/query_stats:"),
             st.Page(P + "04_comparison.py", title="Part 1 vs Part 2", icon=":material/compare_arrows:")],
    "Players": [st.Page(P + "05_player_explorer.py", title="Player explorer", icon=":material/person_search:"),
                st.Page(P + "06_roles.py", title="Batting · bowling · all-round", icon=":material/sports_cricket:"),
                st.Page(P + "07_scoring.py", title="Fantasy points calculator", icon=":material/calculate:")],
    "Models & decisions": [st.Page(P + "08_predictions.py", title="Predictive analytics", icon=":material/insights:"),
                           st.Page(P + "09_selection.py", title="Selection & auction support", icon=":material/how_to_reg:"),
                           st.Page(P + "10_teams.py", title="Teams & seasons", icon=":material/groups:")],
    "Report": [st.Page(P + "11_methodology.py", title="Methodology & final report", icon=":material/menu_book:")],
})
st.session_state["_page"] = nav.title
with st.sidebar:
    st.markdown("---")
    st.markdown("**Filters**")
nav.run()
with st.sidebar:
    st.markdown("---")
    st.caption("Data: Cricsheet.org (ODC-By 1.0) · scoring v1 + identity v1.1 · models labelled *rebuilt*.")
