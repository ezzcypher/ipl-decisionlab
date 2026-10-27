# Data dictionary

Every file the project ships, what it contains, and where it comes from. Generated from the files themselves (sizes, shapes).

## Source data and licence

The only external dataset is the **Cricsheet all-IPL ball-by-ball CSV** (<https://cricsheet.org>), licensed under the
**Open Data Commons Attribution License (ODC-By 1.0)** — redistribution is allowed with attribution. A snapshot is committed
at `pipeline/inputs/ipl_male_csv2.zip` (SHA-256 in `pipeline/reports/source_checksums.sha256`) because Cricsheet updates
the file continuously; re-downloading it would give different data. See `NOTICE`.

## Pipeline inputs (`pipeline/inputs/`, committed)

| File | Size | Contents |
| --- | --- | --- |
| `pipeline/inputs/IPL_DecisionLab_Phase3_PlayerMatch_Points.csv` | 2.0 MB | Original Phase 3 scoring output (recovered) — rebuilt byte-identical. |
| `pipeline/inputs/IPL_DecisionLab_Phase5_Final_Features.csv` | 3.6 MB | Recovered Phase 5 features (built on the reconstruction) — used to recover feature definitions and reconcile old metrics. |
| `pipeline/inputs/IPL_DecisionLab_Phase6_Audit_Report.json` | 0.0 MB | Recovered original Phase 6 report — baselines reproduced, XGBoost claims not reproducible. |
| `pipeline/inputs/IPL_DecisionLab_Phase6_Final_Consistency_Audit.txt` | 0.0 MB | Recovered original Phase 6 text audit. |
| `pipeline/inputs/IPL_DecisionLab_Player_Mapping_Audit.csv` | 0.0 MB | Recovered one-row player-mapping audit (superseded by the registry-id audit). |
| `pipeline/inputs/IPL_DecisionLab_pm_reconstructed.csv` | 2.1 MB | Flawed reconstruction made during recovery — kept only to explain the discrepancies. |
| `pipeline/inputs/ipl_male_csv2.zip` | 6.5 MB | Raw Cricsheet snapshot (2,489 files incl. all_matches.csv; data to 31 May 2026). ODC-By 1.0. |

Not committed here (sizes 45 MB and 56 MB): the recovered original `IPL_DecisionLab_Phase2_Cleaned.csv` and
`IPL_DecisionLab_Team_Standardized.csv`. Their SHA-256 hashes are recorded, and the pipeline test checks the rebuilt files
against those hashes, so byte-identity is still verified without them. The Phase 2 file is published separately at
`data/IPL_DecisionLab_Phase2_Cleaned.csv` (next section); `pipeline/inputs/` stays without it so the pipeline's behaviour
is unchanged.

## Cleaned ball-by-ball data (`data/IPL_DecisionLab_Phase2_Cleaned.csv`, committed)

The Phase 2 cleaned delivery-level dataset, for anyone who wants the cleaned data without running the pipeline.
The dashboard does **not** read this file (it uses the parquet bundle below).

| Property | Value |
| --- | --- |
| Size | 45,521,417 bytes (45.5 MB) |
| Shape | 295,557 rows × 28 columns, one row per delivery |
| Coverage | 1,243 matches, 18 Apr 2008 – 31 May 2026 (`start_date`), 19 seasons, innings 1–2 only |
| Order | Sorted by `start_date`, `match_id`, `innings`, `ball` (stable) |
| SHA-256 | `4aaafe38c44bc5c3f50b34183a35105d4d5f405244901aa08a98dc55fd50b77f` — equals the recorded hash of the recovered original (`inputs/IPL_DecisionLab_Phase2_Cleaned.csv` in `pipeline/reports/source_checksums.sha256`) and of the pipeline's rebuild |
| Source / licence | Derived from the Cricsheet snapshot in `pipeline/inputs/ipl_male_csv2.zip`; ODC-By 1.0, attribution in `NOTICE` |

Columns: `match_id, season, start_date, venue, innings, ball, actual_delivery, batting_team, bowling_team, striker,
non_striker, bowler, runs_off_bat, extras, wides, noballs, byes, legbyes, penalty, non_boundary, wicket_type,
player_dismissed, other_wicket_type, other_player_dismissed, fielder_1, fielder_2, fielder_3, date_year`.

What Phase 2 does to the raw Cricsheet `all_matches.csv`: removes the 175 super-over deliveries (innings 3–6, 16 matches),
reduces 60 venue spellings to 38 names (the 28 renamed variants are listed in `pipeline/config/venue_map.json`), adds `actual_delivery` (the source writes the 10th
ball of an over as `N.10`, which a float `ball` reads as `N.1`; the 42 repeated keys are kept as distinct deliveries) and
`date_year`. Nothing is imputed; empty wicket/fielder cells mean "no such event".

What it does **not** do yet (later pipeline stages): `batting_team`/`bowling_team` keep the 19 original franchise names
(standardized to 15 in Phase 4), `season` keeps Cricsheet labels such as `2007/08` and `2020/21` (use `date_year` for the
calendar year), and player names are not yet merged by registry id (identity v1.1 is applied in the scoring stage).

Regenerate and verify:

```bash
python3 -I pipeline/src/rebuild.py      # writes pipeline/rebuilt/IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv (git-ignored)
sha256sum data/IPL_DecisionLab_Phase2_Cleaned.csv pipeline/rebuilt/IPL_DecisionLab_Phase2_Cleaned_rebuilt.csv
grep Phase2_Cleaned pipeline/reports/source_checksums.sha256   # all three hashes must be identical
```

`tests/test_upgrade.py::test_published_phase2_csv_matches_recorded_checksum` checks the committed file against the
recorded hash.

## Dashboard bundle (`data/`, committed — the app reads only this and `models/`)

| File | Size | Rows × cols | Contents |
| --- | --- | --- | --- |
| `data/audit_checks.parquet` | 8 KB | 27 × 9 | The 27 Part 1 data-quality checks: value, rows affected, status, evidence category. |
| `data/audit_comparison.parquet` | 4 KB | 13 × 4 | Phase 1 (raw) vs Phase 2 (cleaned) metrics with the cause of each change. |
| `data/audit_inventory.csv` | 2 KB | 26 × 3 | Inventory of the recovered project archive and the files found missing from it. |
| `data/audit_missing.parquet` | 5 KB | 55 × 6 | Missing and blank values per column, raw and cleaned. |
| `data/audit_over_anomalies.csv` | 1 KB | 8 × 8 | The 8 overs with 7 or 0 legal balls (kept as recorded). |
| `data/audit_player_identity.csv` | 1 KB | 7 × 6 | Player-name pairs checked against Cricsheet registry ids (merged or kept apart). |
| `data/audit_repeated_keys.csv` | 15 KB | 84 × 20 | The 84 rows behind the 42 repeated (match, innings, ball) keys, with the N.10 explanation. |
| `data/audit_schema.parquet` | 3 KB | 28 × 4 | Column-by-column dtype comparison, raw vs cleaned. |
| `data/audit_super_overs.csv` | 1 KB | 16 × 6 | The 16 matches whose 175 super-over deliveries were removed. |
| `data/audit_team_names.csv` | 1 KB | 19 × 6 | Every franchise name in the raw file, its row count, seasons and standard name. |
| `data/audit_venue_names.csv` | 4 KB | 60 × 5 | Every venue name in the raw file and its standard name. |
| `data/dismissal_season.parquet` | 3 KB | 148 × 3 | Dismissal-type counts per season. |
| `data/innings.parquet` | 43 KB | 2,480 × 13 | One row per innings: date, venue, teams, runs, wickets, legal balls, boundaries, extras. |
| `data/manifest.json` | 8 KB | JSON | Build manifest: raw/cleaned summaries, mappings, discrepancy summary, SHA-256 of every bundled file. |
| `data/model_experiments.json` | 6 KB | JSON | Offline experiments: 14 candidates on validation, the selected one, one test evaluation, artifact hashes. |
| `data/model_experiments_test_predictions.csv` | 310 KB | 4,992 × 7 | Test predictions of the selected experiment and the median baseline. |
| `data/over_season.parquet` | 8 KB | 380 × 6 | Runs, legal balls and dismissals per over number per season. |
| `data/phase6_feature_importance_rebuilt.csv` | 1 KB | 6 × 8 | XGBoost gain and permutation importance, random-forest impurity importance. |
| `data/phase6_metrics_rebuilt.json` | 5 KB | JSON | Rebuilt Phase 6 results: validation and test MAE/RMSE/R² per model, selection, bootstrap, legacy reconciliation. |
| `data/phase6_predictions_test_rebuilt.csv` | 753 KB | 4,992 × 13 | Retrospective test predictions (2024–2026) of all 6 models per player-match. |
| `data/phase6_predictions_val_rebuilt.csv` | 482 KB | 3,288 × 13 | Validation predictions (2022–2023) of all 6 models per player-match. |
| `data/player_images.csv` | 0 KB | 0 × 7 | Empty mapping schema for verified player photos (none shipped). |
| `data/player_match.parquet` | 650 KB | 26,759 × 36 | One row per player per match (v1.1 identities): fantasy points and components, Phase 5 form features, batting/bowling stats, team, opponent, venue, split label. Core table for most pages. |
| `data/player_team_seasons.parquet` | 23 KB | 3,339 × 5 | Team per player per season (players can change franchise), with original franchise names. |
| `data/players.parquet` | 37 KB | 805 × 9 | One row per player: matches, first/last match, Cricsheet registry id, merged aliases. |
| `data/runs_per_ball_season.parquet` | 3 KB | 132 × 3 | Distribution of runs off the bat per delivery, per season. |
| `data/scoring_discrepancies_rebuilt.csv` | 2,499 KB | 19,136 × 25 | Every player-match where the flawed reconstruction differs from the original scoring, with the cause flags. |
| `data/season_summary.parquet` | 12 KB | 19 × 18 | Per season: deliveries, legal balls, runs, extras by type, boundaries, dismissals, credited wickets, dots, matches. |
| `data/team_season.parquet` | 13 KB | 166 × 12 | Per team and season: runs scored/conceded, balls, wickets taken/lost, boundaries, original names. |
| `data/venue_summary.parquet` | 5 KB | 38 × 6 | Per venue: matches, average first-innings total, seasons covered. |

## `player_match.parquet` columns

| Column | Type | Meaning |
| --- | --- | --- |
| `match_id` | int64 | Cricsheet match id |
| `start_date` | datetime64[us] | match date |
| `venue` | str | standardized venue |
| `season` | str | season label as in source (e.g. 2007/08) |
| `player` | str | canonical player name (v1.1) |
| `total_batting_points` | float64 | batting component |
| `wicket_points` | float64 | bowling component (25 per credited wicket) |
| `dot_ball_points` | float64 | 0.5 per dot ball |
| `pts` | float64 | total fantasy points |
| `prev_pts` | float64 | points in previous match |
| `avg_pts_prev3` | float64 | mean of previous 3 (needs 3) |
| `avg_pts_prev5` | float64 | mean of previous 5 (needs 5) |
| `std_pts_prev3` | float64 | population std of previous 3 |
| `trend_pts_prev3` | float64 | avg_pts_prev3 − avg_pts_prev5 |
| `matches_before` | int64 | earlier IPL matches |
| `season_year` | int64 | calendar season (2007/08 → 2008) |
| `team` | str | standardized team played for |
| `team_original` | str | franchise name as in source |
| `opponent` | str | standardized opponent |
| `runs` | int64 | runs off the bat |
| `balls_faced` | int64 | balls faced (wides excluded) |
| `fours` | int64 | fours |
| `sixes` | int64 | sixes |
| `batted` | bool | faced ≥ 1 delivery |
| `dismissal` | str | how out (blank = not out) |
| `legal_balls` | int64 | legal balls bowled |
| `deliveries_bowled` | int64 | all deliveries bowled |
| `runs_conceded` | int64 | off bat + wides + no-balls |
| `wickets` | int64 | credited wickets |
| `dots` | int64 | dot balls bowled |
| `wides_bowled` | int64 | wides bowled |
| `noballs_bowled` | int64 | no-balls bowled |
| `bowled` | bool | bowled ≥ 1 delivery |
| `dismissed` | bool | recorded as dismissed |
| `bowling_points` | float64 | same as wicket_points |
| `split` | str | train / val / test window |

## Models (`models/`, committed)

| File | Contents |
| --- | --- |
| `models/xgboost_rebuilt.json` | Rebuilt XGBoost model (native format) |
| `models/ridge_rebuilt.joblib` | Rebuilt Ridge pipeline (scaler + ridge) |
| `models/preprocess_config_rebuilt.json` | Features, split windows, training medians, hyperparameters, seed, library versions, artifact hashes |
| `models/experiments/selected_experiment_model.joblib` | Offline experiment winner (HistGradientBoosting, absolute error) |

The random-forest artifact (6.5 MB) is not shipped; its predictions are in the prediction files and it is regenerated by
`pipeline/src/model.py`.
