# Changelog

## v2 — Phase 7 upgrade (branch `upgrade/v2`)

### Added
- **Auction prices & value** tab on Selection: CSV upload with schema validation, downloadable template and player-ID lookup,
  registry-id/exact-name matching with unmatched report, season/franchise/currency/role filters, sold-vs-base, price
  distributions, price-vs-performance, player comparison, price-per-point with explicit denominator, configurable
  pre-auction shortlist score, filtered/shortlist CSV exports. No prices are bundled or invented.
- **Model leaderboard** page (12th page): all 6 models, validation and test MAE/RMSE/R², sizes, date ranges, actual vs
  predicted, residuals, feature importance, by season and by player with a minimum group size, limitations panel.
- **Offline experiments** (`scripts/model_experiments.py`): 14 candidates incl. history features and absolute-error
  objectives; selection on validation only; one test evaluation. Selected: HistGradientBoosting (absolute error) —
  test MAE 23.78 vs 24.06 for the median (−0.28, 95% CI −0.41 to −0.15) but RMSE 33.03 vs 32.63 and R² −0.065.
- **Roles**: Batter / Bowler / All-rounder / Unknown from participation shares and balls per match; shared configurable
  thresholds; evidence and threshold-sensitivity views; role distribution and role-based comparisons; role filters on
  Player explorer, Batting·bowling, Selection and Teams; role label + reason on each profile.
- Tests: `tests/test_upgrade.py` (15), extended `tests/test_app.py` (18), `tests/browser_check.py` theme audit.

### Changed
- Theme switch no longer patches Streamlit internals: token CSS via public hooks, themed HTML tables replace canvas
  grids, explicit Plotly colours per figure. `core/theme_switch.py` removed.
- Limitations panel and R² explanation on Predictive analytics.

### Unchanged
- Phase 1–6 data, scoring v1 rules, v1.1 identities and the rebuilt Phase 6 model artifacts (hash-verified).
