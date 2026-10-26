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
    t = tokens(mode())
    # explicit layout values (not only template ones) so the host's native theme can never override them
    fig.update_layout(paper_bgcolor=t["surface"], plot_bgcolor=t["surface"], font_color=t["text2"], title_font_color=t["text"],
                      legend_font_color=t["text2"], hoverlabel=dict(bgcolor=t["surface2"], bordercolor=t["border"], font_color=t["text"]))
    ax = dict(automargin=True, gridcolor=t["grid"], linecolor=t["border"], zerolinecolor=t["border"],
              tickfont_color=t["text2"], title_font_color=t["text2"])
    fig.update_xaxes(**ax); fig.update_yaxes(**ax)
    if fig.data and any(getattr(tr, "type", "") == "heatmap" for tr in fig.data):
        fig.update_traces(colorbar=dict(tickfont=dict(color=t["text2"]), title=dict(font=dict(color=t["text2"]))), selector=dict(type="heatmap"))
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=", 1)[-1]))  # facet titles: "metric=MAE" → "MAE"
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}, key=key)


def empty_or(df, msg="No rows match the current filters."):
    if df is None or len(df) == 0:
        st.info(msg)
        return True
    return False


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(df):
    """Neutralise spreadsheet formula injection (OWASP CSV injection): text cells that start with
    = + - @ TAB or CR get a leading apostrophe. Numeric columns are untouched, so negative numbers stay numbers."""
    out = df.copy()
    for c in out.columns:
        if not (pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c])):
            continue
        out[c] = out[c].map(lambda v: "'" + v if isinstance(v, str) and v.startswith(_FORMULA_START) else v)
    out.columns = [("'" + c) if isinstance(c, str) and c.startswith(_FORMULA_START) else c for c in out.columns]
    return out


def download(df, name, label="Download CSV", key=None):
    st.download_button(label, csv_safe(df).to_csv(index=False).encode(), file_name=f"{name}.csv", mime="text/csv",
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


def _fmt(v, col):
    if v is None or (isinstance(v, float) and v != v) or v is pd.NaT:
        return "–"
    if isinstance(v, (bool,)) or type(v).__name__ == "bool_":
        return "✓" if v else "–"
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    plain = any(k in col.lower() for k in ("id", "season", "year", "rank", "innings", "over"))
    if isinstance(v, (int,)) or type(v).__name__.startswith("int"):
        return str(v) if plain else f"{v:,}"
    if isinstance(v, float) or type(v).__name__.startswith("float"):
        if plain and float(v).is_integer():
            return str(int(v))
        if abs(v) < 1:
            return f"{v:.3f}".rstrip("0").rstrip(".") if v else "0"
        return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
    return str(v)


def table(data, key=None, page_size=15, height=None, sort=True, **_ignored):
    """Themed, sortable, paginated HTML table (follows the in-app theme, unlike canvas-based grids)."""
    df = pd.DataFrame(data)
    if not isinstance(df.index, pd.RangeIndex):
        df = df.reset_index(drop=df.index.name is None and not isinstance(df.index, pd.MultiIndex))
    if empty_or(df):
        return
    n = st.session_state.get("_tbl_counter", 0) + 1
    st.session_state["_tbl_counter"] = n
    key = key or f"tbl{n}"
    if sort and len(df) > 8:
        c1, c2, c3 = st.columns([3, 2, 5])
        col = c1.selectbox("Sort by", ["(original order)"] + list(df.columns), key=f"{key}_sort", label_visibility="collapsed")
        desc = c2.toggle("Descending", True, key=f"{key}_desc")
        if col != "(original order)":
            df = df.sort_values(col, ascending=not desc, kind="stable", na_position="last")
    else:
        c3 = st.container()
    pages = max(1, -(-len(df) // page_size))
    p = 1
    if pages > 1:
        p = st.session_state.get(f"{key}_page", 1)
        p = min(max(1, p), pages)
    view = df.iloc[(p - 1) * page_size: p * page_size]
    head = "".join(f"<th>{esc(str(c))}</th>" for c in view.columns)
    num = [pd.api.types.is_numeric_dtype(view[c]) and not pd.api.types.is_bool_dtype(view[c]) for c in view.columns]
    body = "".join("<tr>" + "".join(f'<td class="{"num" if nm else ""}" title="{esc(_fmt(v, str(c)))}">{esc(_fmt(v, str(c)))}</td>' for v, c, nm in zip(r, view.columns, num)) + "</tr>"
                   for r in view.itertuples(index=False))
    style = f' style="max-height:{int(height)}px"' if height else ""
    st.markdown(f'<div class="dl-tablewrap"{style}><table class="dl-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
                unsafe_allow_html=True)
    if pages > 1:
        a, b = st.columns([1, 4])
        a.number_input("Page", 1, pages, key=f"{key}_page", label_visibility="collapsed")
        b.caption(f"{len(df):,} rows · page {p} of {pages}")
    else:
        st.caption(f"{len(df):,} rows")


def paged(df, key, page_size=25):
    table(df, key=key, page_size=page_size)


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
    st.markdown(f'<div class="dl-tablewrap"><table class="dl-table wrap"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>',
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


ROLE_ORDER = ["Batter", "Bowler", "All-rounder", "Unknown"]


def role_colors():
    """Fixed colour per role, so a role keeps its colour on every chart and filter state."""
    return {r: series(i) for i, r in enumerate(ROLE_ORDER)}
