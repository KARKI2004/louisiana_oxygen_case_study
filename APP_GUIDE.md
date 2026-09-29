# Local dissolved-oxygen app

The app is separate from the original case study. `analyze.py`, `create_brief.py`, the original README and requirements, saved CSV/JSON results, plots, source metadata, and PDF are unchanged. Do not run the original scripts merely to launch the app: they overwrite their own generated artifacts.

## Run

From the repository, with Python 3.11:

```bash
source .venv/bin/activate
python -m pip install -r requirements-app.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

Open http://127.0.0.1:8501. This is a local application, not a deployed service. It has no accounts, database, upload files on disk, model registry, or cross-upload learning. Uploaded data and evaluation results live in the session's memory; Streamlit also temporarily holds download bytes in memory. Do not expose the server publicly without a separate deployment/privacy review.

Select **Case Study Overview** to view original results and the original brief. Select **Process New Data** to upload data or try an example. The synthetic example is explicitly a software demonstration; its results are computed during evaluation. The input selector offers the **Original public CSV**, loaded unchanged, and a separate **Public regular segment** option that explicitly selects July 1–October 24, 2023 without altering measurements. The original full source is rejected by the single-grid check; no automatic subsetting occurs. It requires that source file in `input/`; see the original README for download instructions and attribution. No public measurements are bundled in a new example file.

## Five-stage navigation

**Upload a file → Check the record → Test the methods → Choose gaps → Review and download.** Only the current stage is shown. Back buttons retain input settings and prior choices. Changing a source or input setting clears prepared data, evaluation, selections, and download results. A new comparison requires a fresh manual choice. Method and gap selections start empty. The review stage computes the requested reconstruction once and reuses that result when switching the previewed gap; random forest is trained fresh from that input when preparing the review.

The default case-study page explains the Wilkinson Bayou context, repeated tests, daily-summary results, limitations, and potential adaptation to Lake Maurepas. It does not claim Lake Maurepas observations were studied.

## Supported inputs and explicit decisions

- One series in a UTF-8 comma-separated CSV with unique, nonblank headers; 10 MB input and 100,000 grid-row limits. Preserve station/depth distinctions by preparing separate files. Columns beginning `oxy_` are reserved for export fields; re-upload the original data rather than a processed export.
- Map timestamp and oxygen columns. **mg/L only**; no implicit conversion from percent saturation or other units.
- Use unambiguous ISO timestamps with one consistent timezone or fixed local time. Blank, invalid, duplicate, or off-grid timestamps block the workflow. Input order may be sorted, but timestamps are never shifted. Mixed offsets/timezones must be resolved outside the app.
- Confirm the interval using source knowledge. The most common spacing is only a suggestion. The supported interval is 1–360 minutes. Missing timestamp rows are inserted only on that exact confirmed grid, between the first and last input timestamps. The app cannot infer outages outside those boundaries.
- Blank, `NA`, `NaN`, `null`, and `N/A` values are missing (case insensitive, surrounding whitespace ignored). Numeric cells may use quoted comma thousands separators, matching the public source. Other nonnumeric values, infinity, negative DO, and DO above the chosen upper screening bound are excluded. The default bound is 25 mg/L, a conservative configurable screen, not a universal scientific limit.
- If there is a quality flag, select its exact accepted values. A rejected flag excludes the row for DO and predictors. Multiple quality flags must be combined into one explicit acceptance flag before upload. No automatic interpretation of source-specific flags is claimed. Confirm quality handling even when there are no flags.
- Invalid/flagged observations remain intact in original columns, but are absent from processed observations and are never reconstructed. A missing run containing such readings is unsupported in its entirety.
- Only interior gaps bounded by clean oxygen observations are fill candidates. Each must be at most **six samples and six hours**, and have adequate evaluation at its **exact duration**. This is an engineering scope limit, not evidence that six-hour filling is scientifically valid.
- Forest inputs must be independent measured temperature (°C), salinity (psu), pH, and turbidity (FNU), explicitly mapped and confirmed. Oxygen and timestamp columns cannot be mapped as predictors. Derived copies of oxygen are prohibited by the input contract; a program cannot establish measurement provenance from arbitrary CSV names alone.
- Forest predictor screens: −5–50 °C, 0–50 psu, 0–14 pH, and 0–10,000 FNU. These deliberately limit supported conditions; they are not instrument certifications. All four predictors must be valid in training rows, all shared test targets, and each chosen real gap. There is **no predictor imputation**. Absent timestamp rows therefore cannot be filled by the forest. Short oxygen-only blank gaps may qualify.
- The full original public file has minute-offset changes, absent-record outages, and a 619-row blank run. It is rejected as a single regular grid. The long run would also be ineligible even in an otherwise regular file; it is never presented as validated for filling.

## Evaluation and interpretation

The first 60% of the confirmed time span supplies training, and the last 40% supplies testing. At least 48 clean training observations and five test blocks per exact duration are required. These are conservative software availability floors, not guarantees of statistical adequacy. There are no p-values, confidence claims, or automatic rankings/recommendations.

Eligible real-gap sizes define tested durations. If there are no eligible real gaps, the app can demonstrate 1-, 3-, and 6-sample tests within the six-hour limit, but this does not authorize unsupported real gaps. A fixed-seed selection retains up to 40 disjoint test windows (including their observed endpoints) per duration. Different durations can overlap. Temporal autocorrelation and complete-block selection still limit effective sample size and generalization.

All methods use the same known blocks. Their target oxygen values are masked before prediction. The model and median use only the chronological training prefix; no test target or oxygen-derived feature enters fitting. The forest keeps calendar features and the four contemporaneous independent sensors. If any shared test block lacks those predictors, that forest result is unavailable instead of silently scoring on a different, easier subset. Interpolation uses the two clean oxygen endpoints, including the future endpoint: the comparison describes retrospective reconstruction with method-specific information, not real-time forecasting or an equal-input contest.

Results show point MAE, test block/point counts, fitting counts, and approximate low-hours MAE/bias **within each masked block**, not the original experiment's daily-summary metrics. Low hours count readings below the exploratory 2 mg/L threshold times the interval. They are not a continuous exposure measurement, a site-specific standard, or evidence of biological effects. True-low test-point counts expose limited/no low-oxygen coverage. Unavailable rows show candidate counts with blank errors. No error is calculated against genuine missing values. Leaving a gap unfilled has no prediction MAE and is not ranked against predicting methods.

Choose a method explicitly, then choose specific eligible gaps. No method or gap is preselected, and no fallback switches methods. Before download, the app shows filled/unfilled counts, a focused before/after table, and a plot distinguishing estimates from measurements. Use **Gap to preview** to inspect any selected gap. Full reasons for unsupported gaps are displayed below the gap tables. Comparison tables keep test counts beside each error; detailed settings and raw tables remain expandable. Model and median application fitting uses **all eligible observed readings in this upload** for retrospective reconstruction; evaluation used the earlier training prefix. The forest is created fresh each time application predictions are made and is never shared or persisted. This refitting distinction and possible seasonal distribution shifts remain limitations of the performance estimate.

## Export

A separate `oxygen_processed.csv` contains the original columns and original cell strings for every original row, in timestamp order. CSV quoting/line endings may be normalized; the original uploaded bytes are not overwritten. Observed values in the processed column also retain their original decimal precision (surrounding whitespace and valid thousands separators are removed). Evaluation uses floating-point arithmetic; reconstructed values are serialized from those computations. Added rows receive the inferred timestamp and blank original measurement/other cells.

| Field | Meaning |
|---|---|
| `oxy_source_row` | Original one-based data-row number; blank for inserted rows |
| `oxy_timestamp` | Parsed timestamp, ISO formatted |
| `oxy_original_DO` | Exact original DO cell string; blank for an inserted row |
| `oxy_processed_DO_mg_L` | Eligible observed value or chosen reconstruction; blank when unsupported/excluded/unselected |
| `oxy_original_status` | `observed`, `missing_blank`, `missing_timestamp`, `excluded_invalid_DO`, or `excluded_quality_flag` |
| `oxy_is_reconstructed` | True only for filled cells |
| `oxy_method` | Chosen method only for reconstructed cells |
| `oxy_gap_id`, `oxy_gap_samples`, `oxy_gap_hours` | Missing/excluded-run information |
| `oxy_unfilled_reason` | Why a gap remains unfilled, including eligible but unselected gaps |

The evaluation table can also be downloaded separately. Keep it with the source CSV and record your chosen mappings, bounds, flags, and interval if archiving a research run. The app is not a formal provenance or validation service.

## Checks

```bash
MPLCONFIGDIR=/tmp/oxygen-app-mpl python -B -m unittest discover -s tests -v
python -m pip check
```

Tests cover CSV-to-export flow for each method; exact preservation of original cell strings; unchanged observed numeric values; identical masks and counts; chronological training; invariance of predictions when hidden truths are replaced by extreme values; fresh per-upload application fitting; predictor availability; insufficient tests; invalid values/quality flags; irregular/duplicate/invalid timestamps; long/boundary gaps including a 619-sample run; and export labels. UI tests exercise the synthetic and public example flows and stale-result invalidation.

The tests establish implementation behavior, not scientific validation at a new site. Publication is outside this task; researcher review of site quality rules, predictors, thresholds, gap policies, and data rights is still needed before scientific use or deployment.
