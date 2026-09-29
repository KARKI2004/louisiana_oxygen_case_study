"""Conservative, upload-local evaluation and reconstruction. No I/O side effects."""
from dataclasses import dataclass
from io import StringIO
import csv
import hashlib
import json

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

SEED = 20260919
MIN_TRAIN = 48
MIN_BLOCKS = 5
MAX_BLOCKS = 40
MAX_ROWS = 100_000
MAX_BYTES = 10 * 1024 * 1024
METHODS = ['Linear interpolation', 'Training median', 'Random forest']
PREDICTORS = ['Temp Celsius', 'Sal psu', 'pH', 'Turbidity FNU']
MISSING = {'', 'na', 'nan', 'null', 'n/a'}


@dataclass
class Prepared:
    raw: pd.DataFrame
    time_col: str
    do_col: str
    step: pd.Timedelta
    y: pd.Series
    features: pd.DataFrame
    status: pd.Series
    gaps: pd.DataFrame
    max_steps: int
    fingerprint: str
    rf_reason: str


@dataclass
class Evaluation:
    fingerprint: str
    results: pd.DataFrame
    blocks: dict
    cutoff: int
    training_points: int
    rf_training_points: int


def read_csv(data: bytes) -> pd.DataFrame:
    if len(data) > MAX_BYTES:
        raise ValueError('CSV exceeds the 10 MB version 1 limit.')
    try:
        text = data.decode('utf-8-sig')
        reader = csv.reader(StringIO(text), strict=True)
        header = next(reader)
        if not header or any(not c.strip() for c in header) or len(set(header)) != len(header):
            raise ValueError('Column names must be nonempty and unique.')
        if any(c.startswith('oxy_') for c in header):
            raise ValueError('The oxy_ prefix is reserved for export fields. Use an original input CSV.')
        # Strings preserve input cell values, including NA markers and numeric precision.
        rows = list(reader)
        if any(len(row) != len(header) for row in rows):
            raise ValueError('Every CSV record must have the same number of fields as the header; blank or malformed records are not silently dropped.')
        raw = pd.DataFrame(rows, columns=header, dtype=str)
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise ValueError('Use a valid UTF-8, comma-separated CSV with a header.') from exc
    if not 3 <= len(raw) <= MAX_ROWS:
        raise ValueError('Version 1 accepts 3 to 100,000 source rows.')
    return raw


def parse_times(values):
    try:
        t = pd.DatetimeIndex(pd.to_datetime(values, format='mixed', errors='raise'))
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid or mixed-timezone timestamps. Use ISO dates with one consistent timezone or fixed local time.') from exc
    if t.hasnans:
        raise ValueError('Blank timestamps are unsupported; no rows were dropped.')
    if t.has_duplicates:
        raise ValueError('Duplicate timestamps are unsupported; resolve them explicitly before upload.')
    return t


def suggested_minutes(raw, column):
    t = parse_times(raw[column]).sort_values()
    return float(pd.Series(t[1:] - t[:-1]).mode().iloc[0].total_seconds() / 60)


def numeric(values):
    # Commas in quoted numeric cells match the original source's thousands convention.
    cleaned = values.str.strip()
    grouped = cleaned.str.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][+-]?\d+)?')
    cleaned = cleaned.where(~cleaned.str.contains(',', regex=False) | grouped)
    return pd.to_numeric(cleaned.str.replace(',', '', regex=False), errors='coerce')


def prepare(raw, time_col, do_col, minutes, *, units='mg/L', upper_do=25.0,
            flag_col=None, accepted_flags=(), predictor_map=None, rf_confirmed=False):
    if units != 'mg/L':
        raise ValueError('Version 1 supports mg/L only; convert other units explicitly before upload.')
    if time_col == do_col or time_col not in raw or do_col not in raw:
        raise ValueError('Map distinct timestamp and dissolved oxygen columns.')
    if not np.isfinite(minutes) or minutes < 1 or minutes > 360:
        raise ValueError('Version 1 supports sampling intervals from 1 to 360 minutes.')
    if not np.isfinite(upper_do) or not 2 < upper_do <= 100:
        raise ValueError('The upper oxygen screening bound must be greater than 2 and at most 100 mg/L.')
    t = parse_times(raw[time_col])
    step = pd.Timedelta(minutes=minutes)
    if ((t.asi8 - t.min().value) % step.value != 0).any():
        raise ValueError('Irregular timestamps do not share the confirmed sampling grid. No timestamps were shifted. Select a regular segment outside the app; the full public source includes minute-37 readings and is unsupported as one grid.')
    count = (t.max().value - t.min().value) // step.value + 1
    if count > MAX_ROWS:
        raise ValueError('The implied grid exceeds 100,000 timestamps; use a shorter regular segment.')
    grid = pd.date_range(t.min(), t.max(), freq=step)
    original = raw.copy()
    original.index = t
    original['oxy_source_row'] = np.arange(1, len(raw) + 1).astype(str)
    frame = original.reindex(grid)
    present = frame.oxy_source_row.notna()
    frame.loc[~present, time_col] = [x.isoformat() for x in grid[~present]]
    frame = frame.fillna('')
    y = numeric(frame[do_col]).astype(float)
    blank = frame[do_col].str.strip().str.lower().isin(MISSING)
    valid = np.isfinite(y) & y.between(0, upper_do) & ~blank
    status = pd.Series('observed', index=grid)
    status.loc[blank] = 'missing_blank'
    status.loc[~present] = 'missing_timestamp'
    status.loc[present & ~blank & ~valid] = 'excluded_invalid_DO'
    if flag_col:
        if flag_col in (time_col, do_col) or flag_col not in raw:
            raise ValueError('The quality flag must be a separate column.')
        approved = frame[flag_col].isin(accepted_flags)
        status.loc[present & ~approved] = 'excluded_quality_flag'
        valid &= approved
    y = y.where(valid)
    feature = pd.DataFrame(index=grid)
    rf_reason = 'Random forest requires four independently measured predictors with confirmed units and quality.'
    mapping = predictor_map or {}
    if rf_confirmed and set(mapping) == set(PREDICTORS):
        cols = list(mapping.values())
        if len(set(cols)) != 4 or any(c not in raw or c in (time_col, do_col, flag_col) for c in cols):
            raise ValueError('Forest predictors must be four distinct non-oxygen measurement columns.')
        for name, col in mapping.items():
            feature[name] = numeric(frame[col])
        limits = {'Temp Celsius': (-5, 50), 'Sal psu': (0, 50), 'pH': (0, 14), 'Turbidity FNU': (0, 10000)}
        for name, (lo, hi) in limits.items():
            feature[name] = feature[name].where(feature[name].between(lo, hi))
        if flag_col:
            feature.loc[~approved, :] = np.nan
        rf_reason = ''
    minute = grid.hour * 60 + grid.minute + grid.second / 60
    for name, angle in [('hour', 2*np.pi*minute/1440), ('year', 2*np.pi*grid.dayofyear/365.25)]:
        feature[name+'_sin'] = np.sin(angle)
        feature[name+'_cos'] = np.cos(angle)
    max_steps = min(6, int(pd.Timedelta(hours=6) / step))
    records = []
    missing = y.isna().to_numpy()
    starts = np.flatnonzero(missing & ~np.r_[False, missing[:-1]])
    for gap_id, start in enumerate(starts, 1):
        stop = start
        while stop < len(grid) and missing[stop]:
            stop += 1
        n = stop-start
        reason = ''
        if status.iloc[start:stop].str.startswith('excluded').any():
            reason = 'Contains invalid or quality-excluded readings; version 1 does not replace them.'
        elif start == 0 or stop == len(grid):
            reason = 'Boundary gap: two observed endpoints are required.'
        elif n > max_steps:
            reason = 'Exceeds version 1 limit of 6 samples and 6 hours; not evaluated for filling.'
        records.append(dict(gap_id=gap_id, start=grid[start], end=grid[stop-1], start_pos=start,
                            stop_pos=stop, samples=n, hours=n*minutes/60,
                            blank_rows=int((status.iloc[start:stop]=='missing_blank').sum()),
                            absent_rows=int((status.iloc[start:stop]=='missing_timestamp').sum()),
                            excluded_rows=int(status.iloc[start:stop].str.startswith('excluded').sum()),
                            reason=reason))
    columns=['gap_id','start','end','start_pos','stop_pos','samples','hours','blank_rows','absent_rows','excluded_rows','reason']
    gaps = pd.DataFrame(records, columns=columns)
    digest = hashlib.sha256()
    digest.update(frame.to_csv(index=True).encode())
    digest.update(y.to_numpy().tobytes())
    digest.update(feature.to_numpy().tobytes())
    digest.update(json.dumps([time_col, do_col, minutes, upper_do, flag_col, list(accepted_flags), mapping, rf_confirmed], sort_keys=True).encode())
    return Prepared(frame, time_col, do_col, step, y, feature, status, gaps, max_steps, digest.hexdigest(), rf_reason)


def make_forest():
    return RandomForestRegressor(n_estimators=250, min_samples_leaf=4, random_state=SEED, n_jobs=1)


def choose_blocks(p, size, cutoff):
    """Disjoint windows, including endpoints, per duration; no repeated random masks."""
    valid = p.y.notna().to_numpy()
    candidates = [i for i in range(cutoff+1, len(valid)-size)
                  if valid[i-1:i+size+1].all()]
    rng = np.random.default_rng(SEED + size)
    rng.shuffle(candidates)
    occupied = np.zeros(len(valid), dtype=bool)
    blocks = []
    for start in candidates:
        stop = start+size
        if not occupied[start-1:stop+1].any():
            blocks.append((start, stop))
            occupied[start-1:stop+1] = True
            if len(blocks) == MAX_BLOCKS:
                break
    return sorted(blocks)


def predict_blocks(p, method, blocks, cutoff, forest_factory=make_forest):
    """Mask all targets before any model sees data. Truth is read only by scoring."""
    hidden = p.y.copy()
    for start, stop in blocks:
        hidden.iloc[start:stop] = np.nan
    training = hidden.iloc[:cutoff].notna()
    if method == 'Linear interpolation':
        # Explicit endpoint formula cannot bridge excluded or genuine missing sections.
        return [np.linspace(hidden.iloc[a-1], hidden.iloc[b], b-a+2)[1:-1] for a,b in blocks]
    if method == 'Training median':
        median = hidden.iloc[:cutoff].loc[training].median()
        return [np.full(b-a, median) for a,b in blocks]
    x = p.features.iloc[:cutoff]
    training &= np.isfinite(x).all(axis=1)
    model = forest_factory()
    model.fit(x.loc[training], hidden.iloc[:cutoff].loc[training])
    return [model.predict(p.features.iloc[a:b]) for a,b in blocks]


def evaluate(p, forest_factory=make_forest):
    cutoff = int(len(p.y)*0.6)
    ntrain = int(p.y.iloc[:cutoff].notna().sum())
    rf_train = int((p.y.iloc[:cutoff].notna() & np.isfinite(p.features.iloc[:cutoff]).all(axis=1)).sum()) if not p.rf_reason else 0
    sizes = sorted(set(p.gaps.loc[p.gaps.reason.eq(''), 'samples'].astype(int)))
    if not sizes:
        sizes = [s for s in (1,3,6) if s <= p.max_steps]
    blocks_by_size = {size: choose_blocks(p,size,cutoff) for size in sizes}
    rows=[]
    for size, blocks in blocks_by_size.items():
        for method in METHODS:
            reason = ''
            if ntrain < MIN_TRAIN:
                reason = f'Need {MIN_TRAIN} clean training observations in the first 60% of the time span; found {ntrain}.'
            elif len(blocks) < MIN_BLOCKS:
                reason = f'Need {MIN_BLOCKS} disjoint test blocks of this duration; found {len(blocks)}.'
            elif method == 'Random forest':
                if p.rf_reason:
                    reason = p.rf_reason
                elif rf_train < MIN_TRAIN:
                    reason = f'Need {MIN_TRAIN} training rows with all four valid predictors; found {rf_train}.'
                elif any(not np.isfinite(p.features.iloc[a:b]).all().all() for a,b in blocks):
                    reason = 'Required predictors are missing/invalid in shared test blocks. No subset ranking or predictor imputation is used.'
            row=dict(method=method, samples=size, gap_hours=size*p.step.total_seconds()/3600,
                     test_blocks=len(blocks), test_points=len(blocks)*size,
                     training_points=rf_train if method=='Random forest' else (ntrain if method=='Training median' else 0),
                     status='unavailable' if reason else 'evaluated', reason=reason,
                     point_mae_mg_L=np.nan, low_hours_mae=np.nan, low_hours_bias=np.nan,
                     true_low_test_points=0)
            if not reason:
                predictions = predict_blocks(p,method,blocks,cutoff,forest_factory)
                truths = [p.y.iloc[a:b].to_numpy() for a,b in blocks]
                row['point_mae_mg_L'] = float(np.abs(np.concatenate(predictions)-np.concatenate(truths)).mean())
                low_errors = [(np.sum(estimate<2)-np.sum(truth<2))*p.step.total_seconds()/3600 for estimate,truth in zip(predictions,truths)]
                row['low_hours_mae'] = float(np.abs(low_errors).mean())
                row['low_hours_bias'] = float(np.mean(low_errors))
                row['true_low_test_points'] = int(sum(np.sum(truth<2) for truth in truths))
            rows.append(row)
    return Evaluation(p.fingerprint,pd.DataFrame(rows),blocks_by_size,cutoff,ntrain,rf_train)


def eligibility(p, evaluation, method):
    if p.fingerprint != evaluation.fingerprint:
        raise ValueError('Evaluation does not belong to this input and configuration. Evaluate again.')
    if method not in METHODS:
        raise ValueError('Select one supported method.')
    gaps = p.gaps.copy()
    for i,g in gaps.iterrows():
        reason = g.reason
        result = evaluation.results
        matching = result[(result.method==method)&(result.samples==g.samples)&(result.status=='evaluated')]
        if not reason and matching.empty:
            reason = 'This method has no adequate evaluation for this exact gap duration.'
        if not reason and method=='Random forest' and not np.isfinite(p.features.iloc[g.start_pos:g.stop_pos]).all().all():
            reason = 'Required predictors are missing/invalid during this real gap; forest filling is unsupported.'
        gaps.loc[i,'reason'] = reason
    gaps['eligible'] = gaps.reason.eq('')
    return gaps


def export_fills(p, evaluation, method, selected_ids, forest_factory=make_forest):
    gaps = eligibility(p,evaluation,method)
    selected = set(selected_ids)
    allowed = set(gaps.loc[gaps.eligible,'gap_id'])
    if not selected <= allowed:
        raise ValueError('Selection contains an unsupported gap. Nothing was filled.')
    output = p.raw.copy()
    output['oxy_timestamp'] = [t.isoformat() for t in p.y.index]
    output['oxy_original_DO'] = p.raw[p.do_col]
    output['oxy_processed_DO_mg_L'] = p.y.copy()
    output['oxy_original_status'] = p.status
    output['oxy_is_reconstructed'] = False
    output['oxy_method'] = ''
    output['oxy_gap_id'] = pd.Series(pd.NA, index=p.y.index, dtype='Int64')
    output['oxy_gap_samples'] = pd.Series(pd.NA, index=p.y.index, dtype='Int64')
    output['oxy_gap_hours'] = np.nan
    output['oxy_unfilled_reason'] = ''
    model = None
    if selected and method == 'Random forest':
        observed = p.y.notna() & np.isfinite(p.features).all(axis=1)
        model = forest_factory()
        model.fit(p.features.loc[observed],p.y.loc[observed])
    median = p.y.dropna().median()
    for g in gaps.itertuples():
        idx = p.y.index[g.start_pos:g.stop_pos]
        output.loc[idx,'oxy_gap_id'] = g.gap_id
        output.loc[idx,'oxy_gap_samples'] = g.samples
        output.loc[idx,'oxy_gap_hours'] = g.hours
        if g.gap_id not in selected:
            output.loc[idx,'oxy_unfilled_reason'] = g.reason or 'Eligible but not selected by the researcher.'
            continue
        if method == 'Linear interpolation':
            values = np.linspace(p.y.iloc[g.start_pos-1],p.y.iloc[g.stop_pos],g.samples+2)[1:-1]
        elif method == 'Training median':
            values = np.full(g.samples,median)
        else:
            values = model.predict(p.features.loc[idx])
        output.loc[idx,'oxy_processed_DO_mg_L'] = values
        output.loc[idx,'oxy_is_reconstructed'] = True
        output.loc[idx,'oxy_method'] = method
    return output.reset_index(drop=True)


def to_csv_bytes(output):
    # Float arithmetic is used for evaluation, but exporting a measured value
    # must not round its original decimal text to binary float precision.
    serialized = output.copy()
    observed = serialized.oxy_original_status.eq('observed') & ~serialized.oxy_is_reconstructed
    serialized['oxy_processed_DO_mg_L'] = serialized.oxy_processed_DO_mg_L.astype(object)
    serialized.loc[observed, 'oxy_processed_DO_mg_L'] = (
        serialized.loc[observed, 'oxy_original_DO'].str.strip().str.replace(',', '', regex=False)
    )
    return serialized.to_csv(index=False).encode('utf-8')
