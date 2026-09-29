# Editorial redesign verification — September 28, 2026

The app runs locally at http://127.0.0.1:8502. No deployment or publication was performed.

## Changes

- Site title: Louisiana Oxygen Readings. The sidebar contains only Case Study Overview and Process New Data, each with a purpose description. The case study opens by default.
- The study now reads as a short article: missing-hour context, Wilkinson Bayou source, four labeled data tiles, coverage audit, methods, daily-summary results, and monitoring implications. Lake Maurepas is discussed only as a possible application of the approach, not as the study location.
- Charts and tables have explanatory titles and reading guidance. Repeated tests, ties, undefined point error, sample counts, and the limits of the evidence remain explicit. Original results and figures are reused.
- Processing uses five directional stages with Back controls. Mapping and confirmations are in the main form; quality settings and forest predictors are optional panels. New inputs/settings invalidate later results. Method and gap choices are manual.
- Review includes a selectable gap chart, neighboring measurements, highlighted reconstructed rows, human-readable status labels, remaining-gap reasons, and a separate labeled download. A prepared reconstruction is reused while changing preview gaps, avoiding repeated forest fitting for display changes.

## Verification

All **19 tests passed**: 12 analysis/export checks and 7 UI checks. They cover masked-target leakage, exact observed-value preservation, export labels, gap and predictor eligibility, fresh per-upload forest fitting, staged forward/back navigation, page switching, empty initial choices, method changes, and invalidation after input changes. `pip check` reported no broken requirements.

Chrome was reviewed at a 1470 × 779 desktop viewport. Both pages, the case-study results, all five processing stages, and the highlighted before/after preview were inspected. The unchanged full public CSV was rejected for irregular timestamps. The explicitly selected July–October segment reached evaluation with 40 test blocks for each of its one- and three-hour gap lengths (40 and 120 test points). Manual interpolation selection for both gaps yielded four reconstructed values while retaining 2,767 original observations. A browser download event was received. A final visual check selected only the three-hour gap, confirming that the one-hour gap remains unfilled unless selected.

The real upload branch was exercised in UI tests using the original CSV bytes. The browser used the built-in unchanged public CSV and explicit regular-segment choices; native file-picker transfer remains unverified because of the previously encountered Chrome extension permission limitation. Export bytes and labels are checked by automated tests.

SHA-256 checks against the pre-redesign baseline confirmed that `oxygen_workflow.py`, `analyze.py`, `create_brief.py`, `summary.csv`, `trials.csv`, `audit.json`, both original plots, and the PDF brief were unchanged. Existing user modifications and staged changes were preserved. The original analysis was not rerun because it overwrites its saved artifacts.

## Remaining scope limits

Version 1 supports one compatible regular dissolved-oxygen series in mg/L. Boundary gaps, gaps longer than six readings or six hours, inadequate exact-duration tests, and unsupported predictor conditions remain unavailable. The 619-row source blank run is not validated for filling. Hidden-block errors describe these tests, not guaranteed performance during real outages or at another site. Random forest requires complete independent predictors and is trained from each input separately.

---

The earlier implementation verification is retained below as history.

# Version 1 implementation verification

Verified locally on September 27, 2026, using the repository's Python 3.11 environment and Streamlit 1.64.0. Nothing was published, deployed, committed, or pushed.

## Preservation

Before/after SHA-256 comparison confirmed no changes to `analyze.py`, `create_brief.py`, `summary.csv`, `trials.csv`, `audit.json`, both original PNGs, the PDF brief, `source_metadata.xml`, `README.md`, or `requirements.txt`. Existing staged repository changes were left alone. The original command-line analysis remains separate; it was not executed because it overwrites published artifacts.

New implementation: `app.py`, `oxygen_workflow.py`, `requirements-app.txt`, `.streamlit/config.toml`, two explicitly synthetic example CSVs, tests, and app documentation. Streamlit was installed into the existing local virtual environment; the original pinned analysis packages remained installed. `pip check` reported no broken requirements.

## Audit basis

The input source hash matches the original audit. It contains 9,069 timestamped rows, 8,440 observed DO readings, and 629 blanks. The original experiment fits its median, predictor imputer, and forest on 5,673 observed pre-July readings, then tests 113 complete later days. Forest inputs are temperature, salinity, pH, turbidity, and cyclic calendar features, without oxygen-derived features. No direct target leakage was found in that code. It evaluates simulated gaps only; its all-row forest predictions are not a genuine-gap output workflow.

Saved trial MAE aggregates matched `summary.csv`; methods share masks. Original limitations include repeated/overlapping masks, complete-day selection, a single seasonal holdout, interior gaps only, and retained contemporaneous sensors. The new workflow preserves those results and uses stricter forest predictor eligibility rather than silently reusing the old predictor-imputation assumption.

## Automated checks

The full suite passed **16 tests** (12 workflow tests and 4 Streamlit UI tests), including a follow-up export precision regression check. The local health endpoint also returned `ok`.

```bash
MPLCONFIGDIR=/tmp/oxygen-app-mpl .venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

Coverage includes:

- CSV ingestion through reconstruction and export for each method; original cell strings and observed numeric readings remain unchanged. A follow-up check found that high-precision observed values were rounded in the processed CSV column, although original columns were intact. Export now preserves their original decimal text in the processed column too; a regression test checks decimal and scientific notation and confirms serialization does not mutate the preview data.
- Replacing hidden truths with extreme values leaves predictions unchanged; chronological forest training excludes test rows, and feature columns exclude oxygen.
- Shared test blocks, correct test-point counts, and disjoint windows/endpoints within each duration.
- No authorization from inadequate tests, wrong-duration results, or a different input/configuration.
- Missing forest predictors, fresh independent application models, and fitting only eligible observations from the same input.
- Boundary, long, and 619-sample gaps stay unfilled. A four-sample gap at a two-hour interval exceeds the six-hour limit.
- Invalid/flagged values remain excluded; duplicate/invalid/off-grid timestamps are rejected; ragged CSV records are not silently discarded or shifted.
- No method or gap is preselected; previews/downloads require explicit selections; changed settings remove stale result eligibility.
- The upload branch accepts a supplied file byte stream and rejects the deliberately problematic CSV. AppTest supplies the file-uploader result, not an OS file-picker interaction.

## Local examples and browser checks

The live server was bound only to `127.0.0.1:8501`. In Chrome, the case-study page and plots rendered, and the synthetic example was run through unit/source confirmation, gap inspection, evaluation, explicit interpolation selection, gap selection, preview, and download. The browser reported a successful download event. The preview visibly distinguishes reconstructed points from measurements.

For the synthetic input, selecting every eligible interpolation gap produces 600 output timestamps from 598 original rows: **8 filled points and 12 remaining missing points**. The two boundary points and ten-point long gap remain missing. Shared tests use 40 blocks / 40 points for one-sample gaps, 40 / 80 for two-sample gaps, and 36 / 108 for three-sample gaps. All three methods evaluate with its complete sensor predictors; the forest cannot fill its absent-row gap.

The real July–October public segment contains 2,767 original rows and 2,771 grid timestamps. It exposes a one-hour absent-row gap and a three-hour absent-row gap. Median/interpolation have 40 test blocks per duration (40 and 120 points). The forest cannot fill either real gap because the inserted timestamp rows have no predictors. Its one-hour test is also unavailable because shared test targets lack predictors. The full public source is explicitly rejected as an irregular grid, without moving timestamps.

**Browser automation limitation:** Chrome extension permissions blocked setting files in the native file chooser; native computer-control permission was also unavailable. Thus the file-picker transfer itself was not verified. Upload processing was tested through the real app branch with file bytes supplied by the test harness, and the live browser used the built-in compatible example. macOS also denied reading the downloaded file from Downloads; export bytes and labels were checked in the automated tests, while the browser download event was verified separately.

## Remaining limits

See `APP_GUIDE.md` for the complete eligibility and export contract. The key decisions are mg/L only, one regular grid, at most six samples and six hours, a 60/40 chronological split, at least 48 training readings and five disjoint test blocks per duration, and complete independent forest predictors with explicit units/quality confirmation. These thresholds define software scope, not scientific validity. Missingness during real outages, temporal dependence, seasonal shifts, and uncommon low-oxygen conditions can make measured test error unrepresentative. Arbitrary CSV sensor provenance cannot be independently established by this app.

Before publication or scientific use, the researcher should review site-specific quality rules, units, predictor provenance, thresholds, and the suitability of these gap constraints. Hosting, access controls, and publication approval remain a separate task.
