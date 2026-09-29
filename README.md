# Missing Data and Low-Oxygen Exposure in Louisiana Coastal Monitoring

**Author:** Suyog Karki  
Computer Science – Data Science, Southeastern Louisiana University

An independent data-science methods case study using public USGS observations from Wilkinson Bayou, Louisiana.

## Research question

When consecutive hourly dissolved-oxygen readings are missing, how well do common reconstruction methods preserve three daily summaries: average oxygen, minimum oxygen, and hours below 2 mg/L?

The 2 mg/L cutoff is an exploratory analytical threshold commonly associated with hypoxia. It is not presented as a site-specific Louisiana water-quality standard or evidence of biological harm.

## Why the question matters

Researchers use continuous sensors to characterize conditions between field visits. Missing readings can cause low-oxygen exposure to be understated, especially when an outage overlaps the lowest part of a daily cycle. Testing reconstruction against temporarily hidden observations measures summary errors under the simulated gap conditions.

## Data

- USGS station 292939089544400, Wilkinson Bayou cutoff north of Wilkinson Bay, Louisiana.
- Hourly, fixed mid-depth water-quality measurements from June 16, 2022 through October 24, 2023.
- 9,069 timestamped rows; 8,440 dissolved-oxygen observations.
- Dissolved oxygen ranged from 0.05 to 13.12 mg/L; 1,320 recorded observations were below 2 mg/L.
- The metadata states that USGS processed the data for fouling and drift, checked duplication, omissions, and general outliers, and removed or flagged measurements that did not meet its guidelines.
- The source includes real gaps. The controlled experiment uses only complete test days so every masked value has a known reference observation.

## Experiment

- Train before July 1, 2023; test on 113 complete days from July 1 through October 24, 2023.
- Randomly mask one consecutive 1-, 3-, or 6-hour block within each day, 20 times per duration, sampling with replacement. Gaps always retain an observed endpoint on each side; midnight and 23:00 are never masked. Boundary-crossing and multi-day outages are not tested.
- Use identical masks for every method: 6,780 gap scenarios and 27,120 method evaluations.
- Compare leaving the gap unfilled, training-period median, retrospective linear interpolation, and a random-forest regression model.
- The model uses water temperature, salinity, pH, turbidity, time of day, and season. It retains their recorded values while oxygen is masked; existing predictor gaps are filled using training medians. This does not simulate simultaneous failure of all sensors.

The source includes 619 readings at minute 37 rather than minute 00 before the test period; these are retained at their recorded times. Complete test days require exactly 24 on-the-hour observations. Daily bins follow the source's fixed UTC-6 timestamps, without daylight-saving conversion. “Hours below 2 mg/L” counts hourly readings strictly below 2, assigning one hour per reading; it is an approximate duration, not measured continuous exposure. For unfilled data, the mean and minimum use only remaining observations and low hours count only observed low readings (a lower bound, not an assumption that missing oxygen is safe). Point MAE is undefined for unfilled gaps and blank in the CSV.

The median and the model's feature imputer are fitted only on pre-July observations with recorded oxygen. Missing predictor values use training medians. The 113 complete oxygen test days include 568 missing salinity readings and 19 missing turbidity readings. The random forest uses 250 trees, minimum leaf size 4, and the recorded seed; there is no hyperparameter search in this script. Comparisons use different information appropriate to each method: interpolation uses surrounding oxygen, while the forest uses contemporaneous non-oxygen sensors and calendar features.

## Main result

For six-hour simulated gaps:

| Method | Daily-average MAE | Daily-minimum MAE | Low-hours MAE | Mean low-hours bias |
|---|---:|---:|---:|---:|
| Unfilled | 0.493 mg/L | 0.139 mg/L | 1.285 h/day | -1.285 h/day |
| Median | 0.505 mg/L | 0.139 mg/L | 1.285 h/day | -1.285 h/day |
| Linear interpolation | **0.202 mg/L** | 0.139 mg/L | **0.763 h/day** | -0.500 h/day |
| Random forest | 0.315 mg/L | **0.107 mg/L** | 0.935 h/day | -0.807 h/day |

MAE means mean absolute error. Negative low-hours bias means the method undercounted recorded hours below the threshold.

Linear interpolation best preserved the daily average and low-oxygen duration. The random forest better preserved the daily minimum and missed fewer low-oxygen days for six-hour gaps (50 of 1,800 low-day trials versus 81 for the other methods). It still produced larger errors in average oxygen and low-oxygen duration than interpolation. The more complex method did not dominate the simpler one.

Linear interpolation cannot create a minimum below its observed endpoints, so it cannot recover a fully hidden daily minimum. Its daily-minimum errors equal the unfilled baseline here. The low-day trial denominator of 1,800 represents 90 distinct low-oxygen days repeated 20 times, not 1,800 independent days.

## Researcher takeaway

The preferred treatment depends on the scientific summary. Interpolation was strongest for average conditions and approximate exposure duration in this experiment. The random forest preserved minima and low-day detection somewhat better during long gaps. All methods undercounted low-oxygen hours on average. Reconstructed values should therefore remain identified as estimates, and incomplete days should be evaluated against the intended analysis rather than accepted through a single universal rule.

## Limits

- This is one coastal salt-marsh station, not Lake Maurepas.
- Complete-day selection and a single July-October test period limit generalization to other seasons and incomplete days.
- Simulated gaps may not represent real equipment failures, storms, fouling, or missingness related to extreme conditions.
- Interpolation uses observations after the gap, so it supports retrospective analysis rather than real-time prediction.
- The model assumes non-oxygen sensors remain available and uses no external weather or hydrologic data.
- Repeated masks overlap and are not independent environmental samples; results are descriptive, with no significance claim.
- Source observations are the evaluation reference, not independently revalidated truth.
- The analysis does not establish regulatory compliance, ecological impact, causation, or a safe gap length.

## Reproduce

### Try the Process New Data page

Use [the bundled synthetic CSV](examples/compatible.csv) to test **Process New Data**. Download it from the page’s **Try an example dataset** section and upload it through the CSV control. It contains invented readings and several kinds of gaps so you can review both eligible and unsupported cases.

The [same compatible example is available in Google Sheets](https://docs.google.com/spreadsheets/d/1FjAOMsvJLyI15ajZxg2zrHWyXPIqfyMgsrKPijchWAA/edit?gid=1921450387#gid=1921450387). Open the sheet and choose **File → Download → Comma-separated values (.csv)** if you want to upload a copy from Sheets. Access for other people depends on the sheet's sharing settings.

Use Python 3.11 or 3.12 (reviewed with 3.11). Download `Water quality & dissolved carbon in LA salt marsh.csv` from the [USGS data release](https://doi.org/10.5066/P13GBADQ) and place it in the top-level `input/` folder, beside `input/.gitkeep`. Keep the original filename. The downloaded metadata may also be kept in `input/`; the repository already contains an unchanged copy as `source_metadata.xml`. Then run from the project folder:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python analyze.py
python create_brief.py
```

On Windows, activate with `.venv\Scripts\activate`. To use a CSV elsewhere, pass `--data "/path/to/file.csv"`. The scripts overwrite generated files beside the code. The PDF table reads `summary.csv`; regenerate the analysis before the brief. The analysis uses a fixed random seed and records the source SHA-256 and runtime versions in `audit.json`. The review rerun used Python 3.11.15 on macOS; the original audit recorded Python 3.12.14. Forest summary MAEs differed by at most 0.000041 mg/L, while all displayed six-hour values and low-hour counts agreed. The original and revised analysis code agree in the review environment. Exact cross-environment forest reproduction is not established. Dependencies for analysis and PDF generation are included; transitive dependencies are not fully locked.

## Project files

| File | Purpose |
|---|---|
| `analyze.py` | Load, validate, split, simulate gaps, evaluate, and plot |
| `create_brief.py` | Generate the one-page PDF from results |
| `requirements.txt` | Python dependencies |
| `source_metadata.xml` | Original USGS metadata, retained unchanged |
| `input/.gitkeep` | Keeps the input folder in Git; downloaded files inside it stay local |
| `audit.json` | Source checksum, counts, seed, and runtime versions |
| `trials.csv` | Generated locally by `analyze.py` and ignored by Git; one row per method and simulated gap, with signed errors as estimate minus reference |
| `summary.csv` | Errors and low-day detection counts by method and gap duration |
| `method_comparison.png` | Daily-summary MAE comparison; coincident lines can hide methods |
| `data_context.png` | Available-observation daily summaries, including incomplete days; blank periods have no DO |
| `Louisiana_Oxygen_Gap_Case_Study.pdf` | One-page research brief |
| `.gitignore` | Excludes raw download, virtual environment, and local caches |

The downloaded input files are ignored by Git and should not be committed. No reconstructed time series is exported: trial rows identify the method and masked interval, and their summaries include estimates.

## Sources

- Mize, S. V., Myers, R. D., He, S., Stagg, C. L., and Fromenthal, E. N. (2025). *High resolution water quality and dissolved carbon data from a coastal Louisiana salt marsh from 2022 to 2023*, version 2.0. U.S. Geological Survey. https://doi.org/10.5066/P13GBADQ
- U.S. EPA, *Hypoxia 101*: https://www.epa.gov/ms-htf/hypoxia-101
- Lake Maurepas Monitoring Project: https://www.southeastern.edu/college-of-science-and-technology/center-for-environmental-research/lakemaurepas/

## Connection to Lake Maurepas

This case study demonstrates a reproducible way to test how missing sensor readings affect research summaries. With researcher-approved Maurepas data, the same workflow could use actual sensor frequency, outage patterns, monitoring depths, biological questions, and thresholds chosen by the project team. It does not claim that the Lake Maurepas team currently needs or lacks such a workflow.
