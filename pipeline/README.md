# Pipeline — raw data to dashboard bundle

Everything the dashboard shows is produced here from the committed raw Cricsheet snapshot.

| Step | Script | Reads | Writes |
| --- | --- | --- | --- |
| 1. Clean, score, features | `src/rebuild.py` | `inputs/ipl_male_csv2.zip`, `config/venue_map.json` | `rebuilt/` Phase 2 cleaned, Phase 4 team-standardized, Phase 3 points (v1), identity map v1.1, Phase 3 v1.1, delivery order, Phase 5 features |
| 2. Audits | `src/audits.py` | raw ZIP, `rebuilt/`, recovered Phase 3 + reconstruction in `inputs/` | `reports/` data-quality JSON, repeated keys, identity audit, scoring discrepancies, provenance |
| 3. Models | `src/model.py` | `rebuilt/` Phase 5 v1.1, recovered Phase 5 (for reconciling old metrics) | `models/` Ridge, random forest, XGBoost + config; `reports/` metrics, predictions, importance, plots |
| 4. Tests | `tests/test_pipeline.py` | all of the above | — (21 checks) |
| 5. App bundle | `../scripts/build_data.py` | `rebuilt/`, `reports/`, `models/` | `../data/`, `../models/` |

Run from the repository root:

```bash
pip install -r requirements-dev.txt
python3 -I pipeline/src/rebuild.py && python3 -I pipeline/src/audits.py && python3 -I pipeline/src/model.py
python3 -I pipeline/tests/test_pipeline.py
python3 -I scripts/build_data.py
```

`rebuilt/`, `models/` and most of `reports/` are regenerated, so they are git-ignored. `reports/source_checksums.sha256`
records the SHA-256 of every recovered source, including the two large originals not committed
(`IPL_DecisionLab_Phase2_Cleaned.csv`, 45 MB; `IPL_DecisionLab_Team_Standardized.csv`, 56 MB). The byte-identity test
compares against the file when present and against its recorded hash otherwise. If you have the original Phase 2 file,
put it in `inputs/` and `rebuild.py` re-derives the venue mapping from it and checks it equals `config/venue_map.json`.

What is **not** here: the original Colab notebooks for Phases 1–6 were lost. This code is the rebuilt pipeline, verified
against the original outputs. Phase 6 models are retrained with fixed settings, not the original run.
