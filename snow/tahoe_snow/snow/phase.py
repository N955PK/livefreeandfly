"""Rain/snow split: the fraction of each hour's liquid that falls as snow.

Fitted against SNOTEL days, where observed snow fraction = SWE gain / precipitation gain.
"""
import json
from itertools import product

import numpy as np
import pandas as pd

from tahoe_snow.config import MODELS

MIN_PRECIP_MM = 5.0
PARAMS_FILE = "snow_phase.json"

# Candidate forms and the parameter grids searched for each.
GRIDS = {
    "air temperature threshold": {"threshold_c": np.arange(-1.0, 3.01, 0.25)},
    "wet-bulb snow level ramp": {"depth_m": np.arange(50.0, 601.0, 50.0), "offset_m": np.arange(-300.0, 301.0, 100.0)},
    "wet-bulb logistic": {"center_c": np.arange(-0.5, 2.01, 0.25), "width_c": np.arange(0.2, 1.21, 0.2)},
}


def hourly_fraction(hourly: pd.DataFrame, elev_m: float, kind: str, params: dict) -> np.ndarray:
    """Snow fraction (0 to 1) per hour from hourly features at ``elev_m``."""
    if kind == "air temperature threshold":
        out = (hourly["t0"].to_numpy() < params["threshold_c"]).astype(float)
        return np.where(hourly["t0"].isna(), np.nan, out)
    if kind == "wet-bulb snow level ramp":
        # All snow at and above the (offset) snow level, falling linearly to none `depth_m` below it.
        level = hourly["snow_level_m"].to_numpy() + params["offset_m"]
        return np.clip((elev_m - (level - params["depth_m"])) / params["depth_m"], 0.0, 1.0)
    if kind == "wet-bulb logistic":
        return 1.0 / (1.0 + np.exp((hourly["tw0"].to_numpy() - params["center_c"]) / params["width_c"]))
    raise ValueError(kind)


def daily_fraction(hourly: pd.DataFrame, fraction: np.ndarray, hours: int = 24) -> pd.Series:
    """Precipitation-weighted mean fraction over the trailing ``hours``; NaN where the model is dry."""
    weights = hourly["precip"].fillna(0.0).where(~np.isnan(fraction), 0.0)
    total = weights.rolling(hours, min_periods=hours).sum()
    snow = (weights * np.nan_to_num(fraction)).rolling(hours, min_periods=hours).sum()
    return snow / total.where(total >= 0.5)


def observed(gains: pd.DataFrame) -> pd.DataFrame:
    """Observed daily snow fraction at a SNOTEL station on days with enough precipitation.

    The precipitation gauge undercatches in wind, so liquid is the larger of the gauge and pillow gains.
    """
    liquid = np.maximum(gains["prec_gain_mm"], gains["swe_gain_mm"])
    keep = (liquid >= MIN_PRECIP_MM) & gains["swe_gain_mm"].notna() & gains["prec_gain_mm"].notna()
    out = pd.DataFrame({"liquid_mm": liquid, "fraction": (gains["swe_gain_mm"] / liquid).clip(0.0, 1.0)})
    return out[keep]


def error_mm(observed_days: pd.DataFrame, predicted_fraction: pd.Series) -> np.ndarray:
    """Per-day error in snow water (mm)."""
    return ((predicted_fraction - observed_days["fraction"]) * observed_days["liquid_mm"]).to_numpy()


def grid(kind: str) -> list:
    names = list(GRIDS[kind])
    return [dict(zip(names, (float(v) for v in values))) for values in product(*(GRIDS[kind][n] for n in names))]


def save(kind: str, params: dict, extra: dict | None = None) -> None:
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / PARAMS_FILE).write_text(json.dumps({"kind": kind, "params": params, **(extra or {})}, indent=2))


def load() -> tuple:
    spec = json.loads((MODELS / PARAMS_FILE).read_text())
    return spec["kind"], spec["params"]
