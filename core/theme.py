"""Design tokens, Streamlit CSS and Plotly template for the dark and light themes."""
import plotly.graph_objects as go

TOKENS = {
    "dark": dict(bg="#0b1020", surface="#121a2e", surface2="#18223a", border="#243050", text="#e8ecf5", text2="#a7b0c4",
                 muted="#8a94ab", accent="#8b7dff", accent2="#3987e5", grid="#1f2a44", hero1="#2a1f6e", hero2="#123a7a",
                 good="#0ca30c", warn="#fab219", bad="#e66767",
                 series=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]),
    "light": dict(bg="#f4f5f9", surface="#ffffff", surface2="#f7f8fb", border="#e4e7ee", text="#0f172a", text2="#475569",
                  muted="#5b6474", accent="#5b4cf0", accent2="#2a78d6", grid="#eef0f5", hero1="#5b4cf0", hero2="#2a78d6",
                  good="#0a7d0a", warn="#a86b00", bad="#c62f2f",
                  series=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]),
}
FONT = "Inter, system-ui, -apple-system, Segoe UI, sans-serif"
PLOT_FONT = "Arial, Helvetica, sans-serif"  # metric-stable font so Plotly automargin measures correctly


def tokens(mode):
    return TOKENS[mode]


def css(mode):
    t = TOKENS[mode]
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {{ --bg:{t['bg']}; --surface:{t['surface']}; --surface2:{t['surface2']}; --border:{t['border']}; --text:{t['text']};
        --text2:{t['text2']}; --muted:{t['muted']}; --accent:{t['accent']}; --accent2:{t['accent2']}; --good:{t['good']};
        --warn:{t['warn']}; --bad:{t['bad']}; --hero1:{t['hero1']}; --hero2:{t['hero2']}; }}
html, body, [class*="css"], .stApp, .stMarkdown, p, li, label {{ font-family:{FONT}; }}
.stApp {{ background: var(--bg); color: var(--text); }}
header[data-testid="stHeader"] {{ background: transparent; }}
section[data-testid="stSidebar"] > div {{ background: var(--surface); border-right: 1px solid var(--border); }}
section[data-testid="stSidebar"] * {{ color: var(--text); }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }}
h1, h2, h3, h4, h1 *, h2 *, h3 *, h4 * {{ color: var(--text) !important; letter-spacing: -0.01em; }}
h1 {{ font-weight: 800 !important; font-size: 1.9rem !important; }}
h3 {{ font-weight: 700 !important; font-size: 1.05rem !important; }}
p, li, span, label, .stCaption, [data-testid="stCaptionContainer"] {{ color: var(--text2); }}
a {{ color: var(--accent) !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--surface); border: 1px solid var(--border) !important; border-radius: 16px; }}
[data-testid="stExpander"] details {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }}
[data-testid="stExpander"] summary p {{ color: var(--text); font-weight: 600; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ color: var(--text2); padding: 8px 14px; }}
.stTabs [aria-selected="true"] {{ color: var(--text) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--accent); }}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, .stNumberInput input, .stTextInput input, .stDateInput input {{
    background: var(--surface2) !important; border-color: var(--border) !important; color: var(--text) !important; }}
div[data-baseweb="select"] span, div[data-baseweb="select"] div {{ color: var(--text); }}
div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li {{ background: var(--surface) !important; color: var(--text) !important; }}
span[data-baseweb="tag"] {{ background: color-mix(in srgb, var(--accent) 22%, transparent) !important; }}
span[data-baseweb="tag"] span {{ color: var(--text) !important; }}
.stButton button, .stDownloadButton button {{ background: var(--surface2); color: var(--text); border: 1px solid var(--border); border-radius: 10px; font-weight: 600; }}
.stButton button:hover, .stDownloadButton button:hover {{ border-color: var(--accent); color: var(--accent); }}
[data-testid="stMetric"] {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 14px 16px; }}
[data-testid="stMetricValue"] {{ color: var(--text); }}
code {{ color: var(--accent); background: var(--surface2); }}
hr {{ border-color: var(--border); }}

/* native widgets — styled from tokens so they follow the in-app toggle (public CSS hooks only) */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label, .stCheckbox label p, .stToggle label p, .stRadio label p {{ color: var(--text) !important; }}
[data-testid="stSidebarNavLink"] span, [data-testid="stNavSectionHeader"] span, [data-testid="stNavSectionHeader"] {{ color: var(--text2) !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"], [data-testid="stSidebarNavLink"]:hover {{ background: var(--surface2) !important; }}
[data-testid="stSidebarNavLink"][aria-current="page"] span {{ color: var(--text) !important; }}
[data-testid="stAlertContainer"] {{ background: var(--surface) !important; border: 1px solid var(--border); color: var(--text) !important; }}
[data-testid="stAlertContainer"] p, [data-testid="stAlertContainer"] svg {{ color: var(--text) !important; fill: var(--text2); }}
div[data-baseweb="tooltip"], div[data-baseweb="tooltip"] > div, [data-testid="stTooltipContent"] {{ background: var(--surface2) !important; color: var(--text) !important; border:1px solid var(--border); }}
div[data-baseweb="popover"] > div, div[data-baseweb="popover"] ul, div[data-baseweb="popover"] li, div[data-baseweb="menu"],
ul[role="listbox"], li[role="option"] {{ background: var(--surface) !important; color: var(--text) !important; }}
li[role="option"]:hover, li[role="option"][aria-selected="true"] {{ background: var(--surface2) !important; }}
div[data-baseweb="calendar"], div[data-baseweb="calendar"] * {{ background-color: var(--surface) !important; color: var(--text) !important; }}
div[data-baseweb="calendar"] [aria-selected="true"] {{ background-color: var(--accent) !important; color: #fff !important; }}
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{ color: var(--text2) !important; }}
[data-testid="stNumberInputContainer"] button, [data-testid="stNumberInput"] button {{ background: var(--surface2) !important; color: var(--text) !important; }}
[data-testid="stFileUploaderDropzone"] {{ background: var(--surface2) !important; border: 1px dashed var(--border) !important; }}
[data-testid="stFileUploaderDropzone"] span, [data-testid="stFileUploaderDropzone"] small {{ color: var(--text2) !important; }}
[data-testid="stExpander"] details summary {{ background: var(--surface) !important; }}
[data-testid="stExpander"] details summary svg {{ fill: var(--text2); color: var(--text2); }}
.katex, .katex * {{ color: var(--text) !important; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--muted) !important; }}
[data-testid="stHeader"] button, [data-testid="stToolbar"] button, [data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {{ color: var(--text2) !important; }}
[data-testid="stPageLink"] a span, [data-testid="stPageLink-NavLink"] span {{ color: var(--accent) !important; }}
div[data-baseweb="checkbox"] > div {{ border-color: var(--border); }}
[data-testid="stMarkdownContainer"] p, [data-testid="stMarkdownContainer"] li {{ color: var(--text2); }}
[data-testid="stMarkdownContainer"] strong {{ color: var(--text); }}
div[role="dialog"], div[data-baseweb="modal"] > div {{ background: var(--surface) !important; color: var(--text) !important; }}

[data-testid="stPlotlyChart"] {{ border: 1px solid var(--border); border-radius: 16px; overflow: hidden; background: var(--surface); }}
section[data-testid="stSidebar"], [data-testid="stSidebarContent"] {{ background: var(--surface) !important; }}
[data-testid="stSelectbox"] [role="group"], [data-testid="stMultiSelect"] [role="group"], [data-testid="stDateInput"] [role="group"],
[data-testid="stNumberInputContainer"], [data-testid="stNumberInputField"], [data-testid="stDateInputField"], [data-testid="stTextInputRootElement"],
.stTextInput input, .stTextArea textarea {{ background: var(--surface2) !important; color: var(--text) !important; border-color: var(--border) !important; }}
[data-testid="stSelectbox"] input, [data-testid="stMultiSelect"] input {{ color: var(--text) !important; background: transparent !important; }}
[data-testid="stMultiSelectDropdown"], [data-testid$="Dropdown"], div:has(> [role="listbox"]), [role="listbox"],
[data-testid="stPopoverBody"], [role="dialog"] {{ background: var(--surface) !important; color: var(--text) !important; border-color: var(--border) !important; }}
[role="option"] {{ color: var(--text) !important; }}
[role="option"][data-focused="true"], [role="option"][aria-selected="true"], [role="option"]:hover {{ background: var(--surface2) !important; }}
[data-testid="stMarkdownContainer"] code, code, pre {{ background: var(--surface2) !important; color: var(--accent) !important; }}
[data-testid="stDateInputCalendar"], [data-testid="stDateInputCalendar"] * {{ background-color: var(--surface) !important; color: var(--text) !important; }}
[data-testid="stDateInputCalendar"] [aria-selected="true"], [data-testid="stDateInputCalendar"] [data-selected="true"] {{ background-color: var(--accent) !important; color: #fff !important; }}
[data-testid="stFileChip"], [data-testid="stFileUploaderFile"] {{ background: var(--surface) !important; color: var(--text) !important; border: 1px solid var(--border); }}
[data-testid="stFileUploaderDropzone"] button, [data-testid^="stBaseButton"] {{ background: var(--surface2) !important; color: var(--text) !important; border: 1px solid var(--border) !important; }}
[data-testid^="stBaseButton"]:hover {{ border-color: var(--accent) !important; color: var(--accent) !important; }}
[data-testid="stFileChip"] > div:first-child {{ background: var(--surface2) !important; color: var(--text) !important; }}
/* custom components */
.dl-brand {{ display:flex; align-items:center; gap:10px; margin: 4px 0 14px; }}
.dl-logo {{ width:34px; height:34px; border-radius:10px; background: linear-gradient(135deg, var(--accent), var(--accent2));
           display:flex; align-items:center; justify-content:center; color:#fff; font-weight:800; font-size:15px; }}
.dl-brand b {{ color: var(--text); font-size: 1.02rem; }} .dl-brand small {{ color: var(--muted); display:block; font-size:.72rem; }}
.dl-title {{ margin-bottom: 18px; }}
.dl-title .eyebrow {{ color: var(--accent); font-weight: 700; font-size: .74rem; letter-spacing: .08em; text-transform: uppercase; }}
.dl-title h1 {{ margin: 2px 0 4px; padding: 0; }}
.dl-title p {{ margin: 0; color: var(--text2); max-width: 900px; }}
.dl-kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 16px 18px; height: 100%; }}
.dl-kpi .label {{ color: var(--text2); font-size: .82rem; font-weight: 600; display:flex; justify-content:space-between; gap:8px; }}
.dl-kpi .value {{ color: var(--text); font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; margin-top: 6px; line-height: 1.15; }}
.dl-kpi .sub {{ color: var(--muted); font-size: .74rem; margin-top: 6px; line-height: 1.35; }}
.dl-kpi .tag {{ color: var(--accent); font-size: .7rem; font-weight: 700; white-space: nowrap; }}
.dl-chip {{ display:inline-block; padding: 3px 10px; border-radius: 999px; border:1px solid var(--border); background: var(--surface2);
           color: var(--text2); font-size: .74rem; margin: 0 6px 6px 0; }}
.dl-badge {{ display:inline-flex; align-items:center; gap:5px; padding: 2px 9px; border-radius: 999px; font-size: .72rem; font-weight: 700; }}
.dl-badge.pass {{ color: var(--good); background: color-mix(in srgb, var(--good) 14%, transparent); }}
.dl-badge.warn {{ color: var(--warn); background: color-mix(in srgb, var(--warn) 16%, transparent); }}
.dl-badge.fail {{ color: var(--bad); background: color-mix(in srgb, var(--bad) 14%, transparent); }}
.dl-badge.info {{ color: var(--accent2); background: color-mix(in srgb, var(--accent2) 14%, transparent); }}
.dl-note {{ border-left: 3px solid var(--accent); background: var(--surface); border-radius: 0 12px 12px 0; padding: 10px 14px;
           color: var(--text2); font-size: .86rem; margin: 6px 0 14px; border-top:1px solid var(--border); border-right:1px solid var(--border); border-bottom:1px solid var(--border); }}
.dl-note b {{ color: var(--text); }}
.dl-hero {{ border-radius: 22px; padding: 26px 28px; color: #fff; position: relative; overflow: hidden;
           background: radial-gradient(120% 140% at 0% 0%, var(--hero1) 0%, var(--hero2) 55%, #0b1020 120%); }}
.dl-hero .row {{ display:flex; gap: 22px; align-items:center; flex-wrap: wrap; }}
.dl-hero .row > div:last-child {{ flex: 1 1 320px; min-width: 0; }}
.dl-avatar {{ width: 96px; height: 96px; border-radius: 26px; display:flex; align-items:center; justify-content:center; font-size: 34px;
             font-weight: 800; color: #fff; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.28); flex: none; }}
.dl-avatar img {{ width: 100%; height: 100%; object-fit: cover; border-radius: 26px; }}
.dl-hero h2, .dl-hero h2 * {{ color:#fff !important; font-size: 2.1rem; font-weight: 800; margin: 0; line-height: 1.05; }}
.dl-hero .meta {{ color: rgba(255,255,255,.78); font-size: .86rem; margin-top: 6px; }}
.dl-hero .chips span {{ display:inline-block; padding:3px 10px; border-radius:999px; background: rgba(255,255,255,.14);
                       color:#fff; font-size:.74rem; margin: 8px 6px 0 0; border: 1px solid rgba(255,255,255,.18); }}
.dl-hero .stats {{ display:grid; grid-template-columns: repeat(4, minmax(90px, 1fr)); gap: 10px; margin-top: 20px; }}
.dl-hero .stat {{ background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); border-radius: 14px; padding: 10px 12px; }}
.dl-hero .stat b {{ display:block; font-size: 1.45rem; color:#fff; }} .dl-hero .stat span {{ color: rgba(255,255,255,.75); font-size:.72rem; }}
.dl-tablewrap {{ overflow:auto; border:1px solid var(--border); border-radius:14px; background: var(--surface); margin-bottom: 12px; }}
.dl-table {{ width:100%; border-collapse: collapse; font-size: .84rem; }}
.dl-table th {{ text-align:left; color: var(--muted); font-weight:600; padding: 10px 12px; border-bottom:1px solid var(--border); white-space:nowrap; position: sticky; top: 0; background: var(--surface); }}
.dl-table.wrap td {{ white-space: normal; max-width: none; }}
.dl-table td.num {{ text-align:right; font-variant-numeric: tabular-nums; white-space:nowrap; }}
.dl-table tbody tr:hover td {{ background: var(--surface2); }}
.dl-table td {{ color: var(--text); padding: 9px 12px; border-bottom:1px solid var(--border); vertical-align: top; white-space: nowrap; max-width: 340px; overflow: hidden; text-overflow: ellipsis; }}
.dl-table tr:last-child td {{ border-bottom: none; }}
@media (max-width: 760px) {{ .dl-kpi {{ margin-bottom: 10px; }} .dl-hero .stats {{ grid-template-columns: repeat(2, 1fr); }} .dl-kpi .value {{ font-size: 1.4rem; }} }}
</style>
"""


def plotly_template(mode):
    t = TOKENS[mode]
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family=PLOT_FONT, color=t["text2"], size=12),
        title=dict(font=dict(color=t["text"], size=14), x=0, xanchor="left"),
        paper_bgcolor=t["surface"], plot_bgcolor=t["surface"],  # explicit: never inherit the native theme colorway=t["series"],
        xaxis=dict(gridcolor=t["grid"], linecolor=t["border"], zerolinecolor=t["border"], tickfont=dict(color=t["text2"]),
                   title=dict(font=dict(color=t["text2"]))),
        yaxis=dict(gridcolor=t["grid"], linecolor=t["border"], zerolinecolor=t["border"], tickfont=dict(color=t["text2"]),
                   title=dict(font=dict(color=t["text2"]))),
        legend=dict(font=dict(color=t["text2"]), bgcolor="rgba(0,0,0,0)", orientation="h", x=1, xanchor="right", y=1.0, yanchor="bottom"),
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["border"], font=dict(color=t["text"], family=PLOT_FONT)),
        margin=dict(l=16, r=16, t=72, b=16), hovermode="closest",
        coloraxis=dict(colorbar=dict(tickfont=dict(color=t["text2"]))),
    )
    tpl.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    return tpl

