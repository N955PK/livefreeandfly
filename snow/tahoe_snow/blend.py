"""Combine models into one forecast and turn ensemble members into ranges and probabilities."""
import numpy as np
import pandas as pd

from tahoe_snow.config import MM_PER_IN

PERCENTILES = (10, 50, 90)
THRESHOLDS_IN = (6, 12)
MIN_MEMBERS = 10


def weighted_mean(by_model: pd.DataFrame, weights: dict | None = None) -> pd.Series:
    """Row-wise weighted mean across model columns; a model with NaN in a row is left out of that row."""
    weights = pd.Series({m: (weights or {}).get(m, 1.0) for m in by_model.columns}, dtype=float)
    present = by_model.notna()
    total = present.mul(weights, axis=1).sum(axis=1)
    return by_model.fillna(0.0).mul(weights, axis=1).sum(axis=1) / total.where(total > 0)


def robust_mean(by_model: pd.DataFrame, weights: dict | None = None, tz: str = "America/Los_Angeles") -> pd.Series:
    """Weighted hourly mean, rescaled so each local day's total equals the median of the models' day totals.

    The hourly shape comes from all models; the amount comes from the middle ones, so a single model with a
    runaway total cannot carry the blend.
    """
    mean = weighted_mean(by_model, weights)
    days = by_model.index.tz_localize("UTC").tz_convert(tz).tz_localize(None).normalize()
    totals = by_model.groupby(days).sum(min_count=1)
    average = totals.mean(axis=1)
    scale = (totals.median(axis=1) / average.where(average > 0)).fillna(1.0)
    return mean * scale.reindex(days).to_numpy()


def mean_direction(degrees) -> np.ndarray:
    """Mean of compass directions along the last axis, 0 to 360; NaN where there are none."""
    radians = np.radians(np.asarray(degrees, dtype=float))
    east, north = np.nansum(np.sin(radians), axis=-1), np.nansum(np.cos(radians), axis=-1)
    return np.where(np.isfinite(radians).any(axis=-1), np.degrees(np.arctan2(east, north)).round(6) % 360, np.nan)


def inverse_error_weights(errors: dict, floor: float = 0.1) -> dict:
    """Weights proportional to 1 / mean absolute error; equal weights when no error history exists."""
    if not errors:
        return {}
    inverse = {model: 1.0 / max(error, floor) for model, error in errors.items()}
    scale = sum(inverse.values())
    return {model: value / scale for model, value in inverse.items()}


def member_stats(members: pd.DataFrame) -> pd.DataFrame:
    """Percentiles and exceedance probabilities per row from ensemble-member totals in cm.

    Rows with fewer than MIN_MEMBERS members give NaN.
    """
    values = members.to_numpy(dtype=float)
    count = (~np.isnan(values)).sum(axis=1)
    enough = count >= MIN_MEMBERS
    out = pd.DataFrame(index=members.index)
    safe = np.where(enough[:, None], values, 0.0) if len(values) else values
    for q in PERCENTILES:
        out[f"p{q}_cm"] = np.where(enough, np.nanpercentile(safe, q, axis=1), np.nan) if len(values) else []
    for inches in THRESHOLDS_IN:
        hit = (values >= inches * MM_PER_IN / 10).sum(axis=1)
        out[f"prob_{inches}in"] = np.where(enough, hit / np.maximum(count, 1), np.nan)
    out["members"] = count
    return out


def local_day_totals(hourly: pd.DataFrame, tz: str = "America/Los_Angeles") -> pd.DataFrame:
    """Sum hourly UTC columns into local calendar days; a day missing more than one hour is NaN.

    (Days are 23 or 25 hours long when the clocks change.)
    """
    local = hourly.copy()
    local.index = local.index.tz_localize("UTC").tz_convert(tz).tz_localize(None)
    grouped = local.groupby(local.index.normalize())
    return grouped.sum(min_count=1).where(grouped.count() >= 23)
