"""Snow-model predictors from an hourly upper-air profile.

The same hourly features feed training (averaged over an observation window,
weighted by model precipitation) and forecasting (hour by hour).
"""
import numpy as np
import pandas as pd

from tahoe_snow import physics
from tahoe_snow.sources.openmeteo import profile_arrays

HEIGHTS_AGL = (0, 500, 1000, 2000)
FEATURES = ([f"t{h}" for h in HEIGHTS_AGL] + [f"wind{h}" for h in HEIGHTS_AGL] + [f"rh{h}" for h in HEIGHTS_AGL]
            + ["tw0", "tmax_col", "lapse", "liquid_mm", "elev_m", "doy_sin", "doy_cos"])
REDUCED_FEATURES = ["t0", "t1000", "t2000", "wind0", "wind1000", "wind2000"]
MIN_MODEL_PRECIP_MM = 0.5


def levels_in(profile: pd.DataFrame) -> list:
    """Pressure levels present in a profile frame, highest pressure first."""
    return sorted({int(c.split("_")[-1][:-3]) for c in profile.columns if c.startswith("temperature_")
                   and c.endswith("hPa")}, reverse=True)


def hourly_features(profile: pd.DataFrame, elev_m: float, levels: list | None = None) -> pd.DataFrame:
    """Per-hour predictors at ``elev_m`` from a frame of pressure-level columns.

    ``levels`` restricts the calculation to a subset of the pressure levels in the frame.
    """
    arrays = profile_arrays(profile, levels or levels_in(profile))
    heights = arrays["height_m"]
    out = pd.DataFrame(index=profile.index)
    for agl in HEIGHTS_AGL:
        target = elev_m + agl
        out[f"t{agl}"] = physics.interp_profile(heights, arrays["t_c"], target)
        out[f"wind{agl}"] = physics.interp_profile(heights, arrays["wind_ms"], target)
        out[f"rh{agl}"] = physics.interp_profile(heights, arrays["rh_pct"], target)
    p0 = physics.interp_profile(heights, np.log(arrays["p_hpa"]), elev_m)
    out["tw0"] = physics.wet_bulb_c(out["t0"].to_numpy(), out["rh0"].to_numpy(), np.exp(p0))
    above = heights >= elev_m
    column_max = np.where(above, arrays["t_c"], -np.inf).max(axis=1)
    out["tmax_col"] = np.maximum(column_max, out["t0"].to_numpy())
    out["lapse"] = (out["t0"] - out["t2000"]) / 2.0
    out["precip"] = profile["precipitation"] if "precipitation" in profile else np.nan
    wet_bulb = physics.wet_bulb_c(arrays["t_c"], arrays["rh_pct"], arrays["p_hpa"])
    out["snow_level_m"] = physics.snow_level_m(heights, wet_bulb)
    return out


def window_features(hourly: pd.DataFrame, hours: int = 24) -> pd.DataFrame:
    """Precipitation-weighted means over the trailing ``hours``; row t covers (t - hours, t].

    Windows where the model is nearly dry use plain means and are flagged ``model_dry``.
    """
    hourly = hourly.asfreq("h")
    weights = hourly["precip"].fillna(0.0)
    names = [c for c in hourly.columns if c not in ("precip",)]
    valid = hourly[names].notna().all(axis=1)
    weights = weights.where(valid, 0.0)
    weight_sum = weights.rolling(hours, min_periods=hours).sum()
    count = valid.astype(float).rolling(hours, min_periods=hours).sum()
    out = pd.DataFrame(index=hourly.index)
    dry = weight_sum < MIN_MODEL_PRECIP_MM
    for name in names:
        values = hourly[name].where(valid, 0.0)
        weighted = (values * weights).rolling(hours, min_periods=hours).sum() / weight_sum.where(~dry)
        plain = values.rolling(hours, min_periods=hours).sum() / count.where(count > 0)
        out[name] = weighted.where(~dry, plain)
    wet = weights > 0.05
    out["tw0_max"] = hourly["tw0"].where(wet | dry.reindex(hourly.index)).rolling(hours, min_periods=1).max()
    out["model_precip_mm"] = weight_sum
    out["model_dry"] = dry
    out["hours_valid"] = count
    return out


def add_static(frame: pd.DataFrame, liquid_mm, elev_m, day_of_year) -> pd.DataFrame:
    frame = frame.copy()
    frame["liquid_mm"] = liquid_mm
    frame["elev_m"] = elev_m
    angle = 2 * np.pi * np.asarray(day_of_year, float) / 365.25
    frame["doy_sin"] = np.sin(angle)
    frame["doy_cos"] = np.cos(angle)
    return frame
