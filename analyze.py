"""Evaluate reconstruction methods on hourly Louisiana dissolved-oxygen data."""
from pathlib import Path
import argparse, hashlib, json, platform
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--data", type=Path,
                    default=ROOT / "input" / "Water quality & dissolved carbon in LA salt marsh.csv",
                    help="USGS CSV path (default: input/Water quality & dissolved carbon in LA salt marsh.csv)")
args = parser.parse_args()

d = pd.read_csv(args.data, thousands=",")
d["timestamp"] = pd.to_datetime(d["Timestamp_UTCminus6"], format="mixed")
d = d.sort_values("timestamp").set_index("timestamp")
assert len(d) == 9069 and d.index.is_unique and d.index.is_monotonic_increasing

minute = d.index.hour * 60 + d.index.minute
doy = d.index.dayofyear
feature_cols = ["Temp Celsius", "Sal psu", "pH", "Turbidity FNU"]
X = d[feature_cols].copy()
X["hour_sin"] = np.sin(2*np.pi*minute/1440)
X["hour_cos"] = np.cos(2*np.pi*minute/1440)
X["year_sin"] = np.sin(2*np.pi*doy/365.25)
X["year_cos"] = np.cos(2*np.pi*doy/365.25)

train = (d.index < "2023-07-01") & d.DO.notna()
model = make_pipeline(
    SimpleImputer(strategy="median"),
    RandomForestRegressor(n_estimators=250, min_samples_leaf=4,
                          random_state=20260919, n_jobs=-1),
)
model.fit(X.loc[train], d.loc[train, "DO"])
pred = pd.Series(model.predict(X), index=d.index)
training_median = float(d.loc[train, "DO"].median())

# Only fully observed, 24-hour test days provide known reference values.
test = d.loc["2023-07-01":]
complete_days = []
for date, day in test.groupby(test.index.normalize()):
    expected = pd.date_range(date, periods=24, freq="h")
    if len(day) == 24 and day.index.equals(expected) and day.DO.notna().all():
        complete_days.append((date, day))
assert len(complete_days) >= 90

rng = np.random.default_rng(20260919)
threshold = 2.0  # exploratory analytical threshold, not a site-specific standard
rows = []
for date, day in complete_days:
    y = day.DO.to_numpy()
    for hours in [1, 3, 6]:
        for repeat in range(20):
            # Retain an observed value on each side for retrospective interpolation.
            start = int(rng.integers(1, 24-hours))
            stop = start + hours
            missing = y.copy()
            missing[start:stop] = np.nan
            methods = {
                "Unfilled": missing.copy(),
                "Training median": missing.copy(),
                "Linear interpolation": pd.Series(missing).interpolate().to_numpy(),
                "Random forest": missing.copy(),
            }
            methods["Training median"][start:stop] = training_median
            methods["Random forest"][start:stop] = pred.loc[day.index].to_numpy()[start:stop]
            for method, estimate in methods.items():
                assert np.array_equal(estimate[:start], y[:start])
                assert np.array_equal(estimate[stop:], y[stop:])
                err = estimate[start:stop] - y[start:stop]
                true_low_hours = int((y < threshold).sum())
                # NaNs are not counted: the unfilled baseline is observed low hours only.
                estimated_low_hours = int(np.count_nonzero(estimate < threshold))
                rows.append({
                    "date": str(date.date()), "gap_hours": hours, "repeat": repeat,
                    "gap_start": str(day.index[start]), "gap_end_exclusive": str(day.index[stop]),
                    "method": method,
                    "point_mae": float(np.mean(np.abs(err))) if method != "Unfilled" else np.nan,
                    "daily_mean_error": float(np.nanmean(estimate)-np.mean(y)),
                    "daily_minimum_error": float(np.nanmin(estimate)-np.min(y)),
                    "true_low_hours": true_low_hours,
                    "estimated_low_hours": estimated_low_hours,
                    "low_hours_error": estimated_low_hours-true_low_hours,
                    "missed_low_day": int(true_low_hours > 0 and estimated_low_hours == 0),
                    "false_low_day": int(true_low_hours == 0 and estimated_low_hours > 0),
                })

trials = pd.DataFrame(rows)
trials.to_csv(ROOT/"trials.csv", index=False)
for c in ["daily_mean_error", "daily_minimum_error", "low_hours_error"]:
    trials[c.replace("_error", "_absolute_error")] = trials[c].abs()
summary = trials.groupby(["gap_hours", "method"]).agg(
    trials=("repeat", "size"),
    point_mae=("point_mae", "mean"),
    daily_mean_mae=("daily_mean_absolute_error", "mean"),
    daily_minimum_mae=("daily_minimum_absolute_error", "mean"),
    low_hours_mae=("low_hours_absolute_error", "mean"),
    low_hours_bias=("low_hours_error", "mean"),
    true_low_day_trials=("true_low_hours", lambda x: int((x > 0).sum())),
    missed_low_days=("missed_low_day", "sum"),
    false_low_days=("false_low_day", "sum"),
).reset_index()
summary["missed_low_day_rate"] = summary.missed_low_days / summary.true_low_day_trials
summary.to_csv(ROOT/"summary.csv", index=False)

plt.rcParams.update({"font.size": 10.5, "axes.spines.top": False, "axes.spines.right": False})
colors = {"Unfilled":"#777777", "Training median":"#b07926",
          "Linear interpolation":"#16766d", "Random forest":"#7352a0"}
fig, axes = plt.subplots(1, 3, figsize=(13, 4.1), layout="constrained")
specs = [("daily_mean_mae", "Daily average", "MAE (mg/L)"),
         ("daily_minimum_mae", "Daily minimum", "MAE (mg/L)"),
         ("low_hours_mae", "Hours below 2 mg/L", "MAE (hours/day)")]
for ax, (metric, title, ylabel) in zip(axes, specs):
    for method, color in colors.items():
        s = summary[summary.method == method]
        ax.plot(s.gap_hours, s[metric], "o-", label=method, color=color)
    ax.set(title=title, xlabel="Simulated gap (hours)", ylabel=ylabel, xticks=[1,3,6])
axes[-1].legend(fontsize=8.5)
fig.savefig(ROOT/"method_comparison.png", dpi=180)
plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 4.2), layout="constrained")
daily = d.DO.resample("D").agg(["mean", "min", "max"])
ax.fill_between(daily.index, daily["min"], daily["max"], color="#16766d", alpha=.18,
                label="Observed daily range")
ax.plot(daily.index, daily["mean"], color="#16766d", linewidth=1, label="Observed daily mean")
ax.axhline(threshold, color="#b24c3d", linestyle="--", label="Exploratory 2 mg/L threshold")
ax.axvline(pd.Timestamp("2023-07-01"), color="#7352a0", linestyle=":", label="Test period begins")
ax.set(ylabel="Dissolved oxygen (mg/L)", title="Wilkinson Bayou, Louisiana • hourly USGS observations")
ax.legend(fontsize=8.5, ncol=2)
fig.savefig(ROOT/"data_context.png", dpi=180)
plt.close(fig)

audit = {
    "source_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
    "source_rows": len(d), "observed_do_rows": int(d.DO.notna().sum()),
    "training_do_rows": int(train.sum()), "complete_test_days": len(complete_days),
    "do_range_mg_l": [float(d.DO.min()), float(d.DO.max())],
    "observations_below_2_mg_l": int((d.DO < threshold).sum()),
    "seed": 20260919, "python": platform.python_version(),
    "matplotlib": matplotlib.__version__,
    "pandas": pd.__version__, "numpy": np.__version__, "sklearn": sklearn.__version__,
}
(ROOT/"audit.json").write_text(json.dumps(audit, indent=2))
print(summary.round(4).to_string(index=False))
print(json.dumps(audit))
