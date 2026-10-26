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
python3 tests/test_app.py          # or: python3 -m pytest -q tests  (if pytest is installed)
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
| Predictive analytics | Retrospective validation/test predictions, errors, feature importance, artifact check |
| Selection & auction support | Weighted, explainable ranking; shortlist export; optional user-supplied price data |
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
- No verified player photographs are shipped; avatars use initials. `data/player_images.csv` holds a mapping only for
  images with a recorded source, licence and verifier.
- The in-app theme toggle patches one internal Streamlit function (`core/theme_switch.py`), so Streamlit is pinned.

Data: [Cricsheet](https://cricsheet.org) all-IPL CSV, licensed ODC-By 1.0 — attribution required.
