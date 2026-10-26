"""Reusable UI pieces: page header, KPI cards, badges, notes, charts, downloads, avatars, filters."""
import html
import re
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from core.theme import tokens, plotly_template

TEMPLATES = {m: plotly_template(m) for m in ("dark", "light")}
px.defaults.color_discrete_sequence = tokens("light")["series"]  # constant; remapped per theme in chart()
_SWAP = {"dark": dict(zip(tokens("light")["series"], tokens("dark")["series"])), "light": {}}


def _recolor(fig):
    """Swap light-palette slots for the same slots stepped for the dark surface (race-free, per figure)."""
    swap = _SWAP[mode()]
    if not swap:
        return
    for tr in fig.data:
        for part in ("marker", "line"):
            obj = getattr(tr, part, None)
            c = getattr(obj, "color", None) if obj is not None else None
            if isinstance(c, str) and c in swap:
                obj.color = swap[c]

ROOT = Path(__file__).resolve().parent.parent
esc = html.escape


def mode():
    return st.session_state.get("theme", "dark")


def header(eyebrow, title, desc=""):
    st.markdown(f'<div class="dl-title"><div class="eyebrow">{esc(eyebrow)}</div><h1>{esc(title)}</h1>'
                f'<p>{esc(desc)}</p></div>', unsafe_allow_html=True)


def kpi(label, value, sub="", tag="", help_text=""):
    t = f'<span class="tag">{esc(tag)}</span>' if tag else ""
    title = f' title="{esc(help_text)}"' if help_text else ""
    return (f'<div class="dl-kpi"{title}><div class="label"><span>{esc(label)}</span>{t}</div>'
            f'<div class="value">{esc(str(value))}</div><div class="sub">{esc(sub)}</div></div>')


def kpi_row(items, cols=4):
    """items: list of dicts for kpi(); rendered in a responsive grid of `cols`."""
    for i in range(0, len(items), cols):
        cs = st.columns(cols)
        for c, it in zip(cs, items[i:i + cols]):
            c.markdown(kpi(**it), unsafe_allow_html=True)
        st.write("")


def badge(status):
    s = str(status).upper()
    cls = {"PASS": "pass", "WARN": "warn", "FAIL": "fail", "NOT REPRODUCED": "warn"}.get(s, "info")
    icon = {"pass": "✓", "warn": "!", "fail": "✕", "info": "i"}[cls]
    return f'<span class="dl-badge {cls}">{icon} {esc(s)}</span>'


def note(text_html):
    st.markdown(f'<div class="dl-note">{text_html}</div>', unsafe_allow_html=True)


def chips(items):
    return "".join(f'<span class="dl-chip">{esc(str(i))}</span>' for i in items)


def chart(fig, height=360, empty="No data for the current filters.", key=None):
    if fig is None:
        st.info(empty)
        return
    fig.update_layout(template=TEMPLATES[mode()], height=height, legend_title_text="")
    _recolor(fig)
    fig.update_xaxes(automargin=True); fig.update_yaxes(automargin=True)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}, key=key)


def empty_or(df, msg="No rows match the current filters."):
    if df is None or len(df) == 0:
        st.info(msg)
        return True
    return False


def download(df, name, label="Download CSV", key=None):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=f"{name}.csv", mime="text/csv",
                       key=key or f"dl_{name}", width="content")


def series(i):
    s = tokens(mode())["series"]
    return s[i % len(s)]


def initials(name):
    parts = [p for p in re.split(r"[\s.]+", re.sub(r"\(.*?\)", "", name)) if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"


@st.cache_data(show_spinner=False)
def image_map():
    p = ROOT / "data" / "player_images.csv"
    if not p.exists():
        return {}
    df = pd.read_csv(p)
    df = df[df["verified_by"].notna() & df["image_file"].notna()]
    return {r.player: r._asdict() for r in df.itertuples(index=False)}


def avatar_html(player):
    m = image_map().get(player)
    if m:
        f = ROOT / "assets" / "players" / str(m["image_file"])
        if f.exists():
            import base64
            b64 = base64.b64encode(f.read_bytes()).decode()
            return f'<div class="dl-avatar"><img src="data:image/{f.suffix[1:]};base64,{b64}" alt="{esc(player)}"/></div>'
    return f'<div class="dl-avatar" aria-label="{esc(player)} (no verified photo)">{esc(initials(player))}</div>'


def paged(df, key, page_size=25):
    """Sortable dataframe with simple pagination for large tables."""
    if empty_or(df):
        return
    pages = max(1, -(-len(df) // page_size))
    c1, c2 = st.columns([1, 5])
    p = c1.number_input("Page", 1, pages, 1, key=f"{key}_page") if pages > 1 else 1
    c2.caption(f"{len(df):,} rows · page {p} of {pages} · click a column header to sort")
    st.dataframe(dates(df.iloc[(p - 1) * page_size: p * page_size]), width="stretch", hide_index=True)


# ---------------------------------------------------------------- filters (shared keys = consistent across pages)
FILTER_KEYS = ["f_seasons", "f_teams", "f_players", "f_roles", "f_venues", "f_opponents", "f_min_matches", "f_dates"]


def reset_filters():
    for k in list(st.session_state):
        if k.startswith("f_"):
            del st.session_state[k]


def season_filter(years):
    years = sorted(int(y) for y in years)
    v = st.session_state.get("f_seasons", (years[0], years[-1]))
    v = (max(years[0], min(v[0], years[-1])), min(years[-1], max(v[1], years[0])))
    return st.sidebar.select_slider("Season range", options=years, value=v, key="f_seasons",
                                    help="Calendar season year (2007/08 → 2008, 2009/10 → 2010, 2020/21 → 2020)")


def multi(label, options, key, help_text=None):
    return st.sidebar.multiselect(label, sorted(options), key=key, help=help_text, placeholder="All")


def min_matches(default=10, key="f_min_matches"):
    return st.sidebar.number_input("Minimum matches", 1, 200, st.session_state.get(key, default), key=key,
                                   help="Players with fewer matches in the filtered data are hidden")


def active_filters(**vals):
    shown = [f"{k}: {v}" for k, v in vals.items() if v not in (None, [], (), "")]
    c1, c2 = st.columns([6, 1])
    c1.markdown(chips(shown) if shown else '<span class="dl-chip">No filters applied</span>', unsafe_allow_html=True)
    if c2.button("Reset filters", key=f"reset_{st.session_state.get('_page', '')}"):
        reset_filters()
        st.rerun()


def apply(pm, seasons=None, teams=None, players=None, venues=None, opponents=None, dates=None):
    m = pd.Series(True, index=pm.index)
    if seasons:
        m &= pm["season_year"].between(*seasons)
    if teams:
        m &= pm["team"].isin(teams)
    if players:
        m &= pm["player"].isin(players)
    if venues:
        m &= pm["venue"].isin(venues)
    if opponents:
        m &= pm["opponent"].isin(opponents)
    if dates and len(dates) == 2:
        m &= pm["start_date"].between(pd.Timestamp(dates[0]), pd.Timestamp(dates[1]))
    return pm[m]


def guard(fn):
    """Render a page, turning missing data into a clear message instead of a traceback."""
    from core.data import MissingData
    try:
        fn()
    except MissingData as e:
        st.error(f"Data unavailable — {e}")


def seq_scale():
    """Single-hue sequential scale: low values recede toward the surface in both themes."""
    return [[0, "#dbe8fb"], [1, "#104281"]] if mode() == "light" else [[0, "#16233f"], [1, "#6da7ec"]]


def status_table(df, cols, status_col="status"):
    """HTML table with icon+label badges (status never by colour alone)."""
    head = "".join(f"<th>{esc(c)}</th>" for c in cols)
    body = ""
    for _, r in df.iterrows():
        body += "<tr>" + "".join(f"<td>{badge(r[c]) if c == status_col else esc(str(r[c]))}</td>" for c in cols) + "</tr>"
    st.markdown(f'<div class="dl-tablewrap"><table class="dl-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
                unsafe_allow_html=True)


def isin(s, vals):
    """Boolean mask; an empty selection means 'all'."""
    return s.isin(vals) if vals else pd.Series(True, index=s.index)


def dates(df):
    """Show datetime columns as plain dates in tables."""
    out = df.copy()
    for c in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[c]):
            out[c] = out[c].dt.date
    return out


ROLE_ORDER = ["Batter", "Bowler", "All-rounder", "Limited role", "Insufficient sample"]


def role_colors():
    """Fixed colour per role, so a role keeps its colour on every chart and filter state."""
    return {r: series(i) for i, r in enumerate(ROLE_ORDER)}
