"""Per-station correction of forecast liquid by empirical quantile mapping.

A mapping is fitted for each (model, lead day) at each station and shrunk toward the
mapping pooled over all stations, more strongly where the station has few wet days.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

QUANTILES = np.concatenate([np.arange(0.05, 0.951, 0.05), [0.975, 0.99]])
WET_MM = 1.0
POOLED = "pooled"


@dataclass
class Correction:
    min_wet_days: int = 40
    maps: dict = field(default_factory=dict)

    def mapping(self, model: str, station: str, lead_day: int):
        """(forecast quantiles, observed quantiles, station weight) or None when nothing was fitted."""
        leads = sorted(lead for (m, lead) in self.maps if m == model)
        if not leads:
            return None
        # Lead days beyond the fitted range use the longest fitted lead.
        lead = min(leads, key=lambda fitted: (abs(fitted - lead_day), fitted))
        return self.maps[(model, lead)], station

    def apply(self, model: str, station: str, lead_day: int, values) -> np.ndarray:
        """Corrected daily liquid (mm). Unfitted models pass through unchanged; NaN stays NaN."""
        values = np.asarray(values, dtype=float)
        found = self.mapping(model, station, lead_day)
        if found is None:
            return values.copy()
        by_station, station = found
        pooled = _apply_map(by_station[POOLED], values)
        if station not in by_station:
            return pooled
        entry = by_station[station]
        weight = entry["n"] / (entry["n"] + self.min_wet_days)
        return weight * _apply_map(entry, values) + (1 - weight) * pooled

    def factor(self, model: str, station: str, lead_day: int, daily_mm) -> np.ndarray:
        """Multiplier that turns a raw daily total into the corrected one (1 where the raw total is ~0)."""
        daily_mm = np.asarray(daily_mm, dtype=float)
        corrected = self.apply(model, station, lead_day, daily_mm)
        return np.where(daily_mm > 0.05, corrected / np.where(daily_mm > 0.05, daily_mm, 1.0), 1.0)


def _fit_map(forecast: np.ndarray, observed: np.ndarray) -> dict:
    wet = np.maximum(forecast, observed) >= WET_MM
    fq = np.quantile(forecast[wet], QUANTILES)
    oq = np.quantile(observed[wet], QUANTILES)
    return {"fq": np.concatenate([[0.0], np.maximum.accumulate(fq)]),
            "oq": np.concatenate([[0.0], np.maximum.accumulate(oq)]), "n": int(wet.sum())}


def _apply_map(entry: dict, values: np.ndarray) -> np.ndarray:
    fq, oq = np.asarray(entry["fq"]), np.asarray(entry["oq"])
    # Strictly increasing forecast quantiles for interpolation; ties keep the largest observed value.
    keep = np.concatenate([np.diff(fq) > 1e-9, [True]])
    fq, oq = fq[keep], oq[keep]
    inside = np.interp(values, fq, oq)
    top_ratio = oq[-1] / fq[-1] if fq[-1] > 0 else 1.0
    out = np.where(values > fq[-1], values * top_ratio, inside)
    return np.where(np.isnan(values), np.nan, out)


def fit(pairs: pd.DataFrame, min_wet_days: int = 40) -> Correction:
    """Fit from rows of (model, station, lead_day, forecast_mm, observed_mm) daily totals."""
    pairs = pairs.dropna(subset=["forecast_mm", "observed_mm"])
    correction = Correction(min_wet_days=min_wet_days)
    for (model, lead), group in pairs.groupby(["model", "lead_day"]):
        forecast, observed = group["forecast_mm"].to_numpy(), group["observed_mm"].to_numpy()
        if (np.maximum(forecast, observed) >= WET_MM).sum() < min_wet_days:
            continue
        by_station = {POOLED: _fit_map(forecast, observed)}
        for station, rows in group.groupby("station"):
            f, o = rows["forecast_mm"].to_numpy(), rows["observed_mm"].to_numpy()
            if (np.maximum(f, o) >= WET_MM).sum() >= 10:
                by_station[station] = _fit_map(f, o)
        correction.maps[(model, int(lead))] = by_station
    return correction


def to_json(correction: Correction) -> dict:
    return {"min_wet_days": correction.min_wet_days,
            "maps": [{"model": model, "lead_day": lead,
                      "stations": {name: {"fq": list(map(float, e["fq"])), "oq": list(map(float, e["oq"])), "n": e["n"]}
                                   for name, e in by_station.items()}}
                     for (model, lead), by_station in correction.maps.items()]}


def from_json(payload: dict) -> Correction:
    correction = Correction(min_wet_days=payload["min_wet_days"])
    for item in payload["maps"]:
        correction.maps[(item["model"], item["lead_day"])] = item["stations"]
    return correction
