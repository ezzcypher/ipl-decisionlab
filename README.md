# IPL DecisionLab

Interactive IPL fantasy-analytics dashboard (Phase 7). Ball-by-ball data 2008–2026, verified fantasy scoring,
data-quality audit, player profiles, role analytics, retrospective model evaluation and selection support.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Python 3.11+ (verified on 3.13). The app reads only `data/` and `models/` (about 5 MB), so it runs on Streamlit
Community Cloud without the raw data.

## Tests

```bash
python3 tests/test_app.py          # core app: pages, KPIs, scoring, roles, models, exports
python3 tests/test_upgrade.py      # v2: auction validation, theming, leaderboard, experiments
streamlit run app.py & python3 tests/browser_check.py   # optional, needs Playwright: theme audit in a real browser
```

## Rebuild the data bundle (local only)

`data/` is generated from the validated Stage B recovery workspace (raw Cricsheet ZIP + byte-verified rebuilt files):

```bash
python3 -I scripts/build_data.py --recovery /path/to/recovery
```

The raw data and the large rebuilt CSVs stay out of the repository (see `.gitignore`).

## Pages

| Page | What it shows |
|---|---|
| Executive overview | KPIs, season trends, team run-rate heatmap, top performers, consistency, model scorecard |
| Part 1 · Data quality audit | 27 checks recomputed from the raw file, evidence categories, repeated keys, mappings, earlier-report claims |
| Part 2 · EDA & cleaning | Distributions, season/over/venue trends, outliers, cleaning decisions |
| Part 1 vs Part 2 | Before/after metrics, missing values, schema, excluded records, mapping changes, unresolved issues |
| Player explorer | Searchable profiles for all 805 players, form, seasons, splits, match table, comparison |
| Batting · bowling · all-round | Role statistics with a configurable, transparent participation rule |
| Fantasy points calculator | Exact formula, rules, real worked example, per-match breakdown, calculator, live reconciliation |
| Predictive analytics | Retrospective validation/test predictions, errors, feature importance, artifact check, limitations |
| Model leaderboard | All 6 models: validation and test MAE/RMSE/R², sizes, date ranges, by season, by player, experiments |
| Selection & auction support | Weighted ranking + shortlist; auction-price upload, validation, price/performance analytics |
| Teams & seasons | Team batting/bowling by season, contributors, venues, name-normalization audit |
| Methodology & final report | Parts 1–6 in plain language; Markdown/ZIP downloads |

## Scoring (v1, no fielding points)

`total = R + F + 2S + 4[R≥30] + 8[R≥50] + 16[R≥100] − 2[duck] + 25W + 0.5D` — milestones stack; duck = faced ≥ 1 ball,
0 runs, dismissed (any mode); W counts caught, bowled, lbw, stumped, caught and bowled, hit wicket; D = non-wide ball with
0 runs off the bat and 0 extras. The formula reproduces all 26,759 stored player-match scores.

## Honesty notes

- Models are **rebuilt** with fixed settings; the original Phase 6 run could not be recovered.
- Best by validation MAE: median baseline. Best by validation RMSE: Ridge. Test R² ≤ 0.02. No model is called a champion.
- Predictions are retrospective (2024–2026 test period). No fixtures, line-ups, injuries or prices are invented.
- No auction price data exists in the source; value metrics appear only for prices the user uploads.
- Roles are a statistical heuristic (see below); there is no official role metadata and wicketkeeping is not inferred.
- No verified player photographs are shipped; avatars use initials. `data/player_images.csv` holds a mapping only for
  images with a recorded source, licence and verifier.

## Theme behaviour

The sidebar **Dark mode** toggle stores the choice in the session, so it survives navigation and filter changes. The app does
not touch Streamlit's internal theme: `.streamlit/config.toml` sets one native base (dark), and every visible element —
sidebar, inputs, dropdowns, calendar, tooltips, alerts, tabs, file uploader, tables and LaTeX — is styled from the same colour
tokens (`core/theme.py`) through public CSS hooks (`data-testid` and ARIA roles). Tables use a themed HTML table
(`components.ui.table`: sortable, paginated) because canvas grids cannot follow CSS. Plotly charts get explicit per-theme
colours on every figure. `tests/browser_check.py` opens all 12 pages in both themes at desktop and phone width and fails on any
element whose background does not match the selected theme, including opened dropdowns, the date picker and the uploader.
*Limitation:* Streamlit's own ⋮ → Settings → Theme menu changes only the native base; the app's toggle remains authoritative
for everything visible. If a future Streamlit release renames a `data-testid`, the browser check will report the mismatch.

## Auction price CSV (user-supplied)

No prices ship with the project. Download the template on the Selection page (or `templates/auction_prices_template.csv`).

| column | type | required | notes |
|---|---|---|---|
| player | text | player or registry_id | as written in your source |
| registry_id | text | player or registry_id | Cricsheet id — preferred; download the player-ID lookup on the page |
| season | integer | yes | auction season (calendar year) |
| franchise | text | no | |
| base_price | number ≥ 0 | no | in `currency` units |
| sold_price | number ≥ 0 | when sold/retained | in `currency` units |
| auction_status | sold / unsold / retained / withdrawn | no | |
| currency | text | yes | e.g. `INR_lakh`; currencies are never converted or mixed |
| source | text | yes | citation; rows marked EXAMPLE / SYNTHETIC / DEMO trigger a "not real prices" banner |

Matching: registry id first, then an exact canonical name or exact known alias — never similarity. Unmatched rows are listed.
Errors (excluded): non-numeric or negative prices, invalid season or status, sold without price, missing currency/source,
duplicate player + season + currency. Warnings: sold below base, zero price, unsold with a price.
**Price per point** = sold price ÷ fantasy points scored in the auction season (blank when price ≤ 0, the player did not
play, or season points ≤ 0). The shortlist score uses only pre-auction seasons plus price; its formula and weights are shown.
`tests/fixtures/auction_synthetic_demo.csv` is synthetic test data, not real prices.

## Role classification (heuristic)

Bats regularly = batted in ≥ 50% of matches **and** ≥ 8 balls faced per match. Bowls regularly = bowled in ≥ 50% of matches
**and** ≥ 9 legal balls per match. Batter / Bowler / All-rounder accordingly; **Unknown** when neither holds or the player has
fewer than 10 matches in view. All thresholds are adjustable in the sidebar (shared across pages); the Evidence tab shows each
player's evidence and how threshold changes move the counts. Fantasy points never decide a role.

## Model experiments (offline)

`python3 -I scripts/model_experiments.py` fits candidates on 2008–2021, selects by validation MAE (2022–2023), then evaluates
the selected candidate once on 2024–2026. Results go to `data/model_experiments.json` and `models/experiments/`; the rebuilt
Phase 6 artifacts are never modified (hash-checked by the tests).

Data: [Cricsheet](https://cricsheet.org) all-IPL CSV, licensed ODC-By 1.0 — attribution required.
