"""Open-Meteo access: forecasts, ensembles, archived forecasts, and upper-air profiles (no key).

All times are UTC. Free tier: 600 calls/min, 5,000/h, 10,000/day; long or wide
requests count as several calls, so every response is cached on disk.
"""
import time

import numpy as np
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import PRESSURE_LEVELS

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ENSEMBLE_URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
HISTORICAL_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"

# Free, non-commercial limits (open-meteo.com/en/terms and /pricing, read 2026-11-19).
DAILY_CALLS = 10_000
MONTHLY_CALLS = 300_000
# Members per ensemble system, control included.
ENSEMBLE_MEMBERS = {"gfs025": 31, "ecmwf_ifs025": 51, "icon_seamless": 40, "gem_global": 21}

LEVEL_VARS = {"temperature": "t_c", "relative_humidity": "rh_pct", "wind_speed": "wind_kmh",
              "geopotential_height": "height_m"}
PROFILE_SURFACE_VARS = ["precipitation", "temperature_2m"]
FORECAST_SURFACE_VARS = PROFILE_SURFACE_VARS + ["cloud_cover", "wind_gusts_10m"]
# Where the wind comes from, degrees clockwise from north. One level near crest height serves every elevation:
# direction in the free air changes little over the height of a ski mountain.
WIND_DIRECTION = "wind_direction_700hPa"
SURFACE_VARS = ["precipitation", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m",
                "surface_pressure"]


def call_weight(url: str, params: dict) -> float:
    """How many API calls one request counts as.

    The service counts fractions: variables / 10 times days / 14, each at least 1 (its examples: 15 variables over
    two weeks is 1.5 calls, over four weeks 3.0). It does not say how models or ensemble members count, so each
    model and each member is counted here as its own set of variables, which can only overstate the total.
    """
    variables = len(str(params.get("hourly", "")).split(","))
    models = str(params.get("models", "")).split(",")
    copies = sum(ENSEMBLE_MEMBERS.get(model, 1) for model in models) if url == ENSEMBLE_URL else len(models)
    if "start_date" in params:
        days = (pd.Timestamp(params["end_date"]) - pd.Timestamp(params["start_date"])).days + 1
    else:
        days = int(params.get("forecast_days", 7)) + int(params.get("past_days", 0))
    return max(1.0, variables * copies / 10) * max(1.0, days / 14)


def level_variables(levels=PRESSURE_LEVELS) -> list:
    return [f"{name}_{level}hPa" for name in LEVEL_VARS for level in levels]


def hourly_frame(payload: dict, suffix: str = "") -> pd.DataFrame:
    """The 'hourly' block as a UTC-indexed frame; ``suffix`` (a model name) is stripped from columns."""
    hourly = payload["hourly"]
    frame = pd.DataFrame({k: v for k, v in hourly.items() if k != "time"}, index=pd.to_datetime(hourly["time"]))
    frame.index.name = "time"
    if suffix:
        frame.columns = [c.removesuffix(f"_{suffix}") for c in frame.columns]
    return frame.astype(float)


def profile_arrays(frame: pd.DataFrame, levels=PRESSURE_LEVELS) -> dict:
    """Stack level columns into (n_time, n_level) arrays keyed t_c, rh_pct, wind_ms, height_m, p_hpa."""
    out = {}
    for name, key in LEVEL_VARS.items():
        columns = [f"{name}_{level}hPa" for level in levels]
        out[key] = frame.reindex(columns=columns).to_numpy(dtype=float)
    out["wind_ms"] = out.pop("wind_kmh") / 3.6
    out["p_hpa"] = np.broadcast_to(np.asarray(levels, float), out["t_c"].shape)
    return out


def historical_profile(lat: float, lon: float, start: str, end: str, model: str = "gfs_seamless",
                       pause_s: float = 0.0) -> pd.DataFrame:
    """Archived hourly analysis/short-lead profile plus surface fields at a point (2021-03-25 on)."""
    params = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "models": model,
              "hourly": ",".join(PROFILE_SURFACE_VARS + level_variables()), "wind_speed_unit": "kmh"}
    payload = get_json("om_profile", HISTORICAL_URL, params, timeout=400, retries=3)
    if pause_s:
        time.sleep(pause_s)
    return hourly_frame(payload)


def historical_surface(lat: float, lon: float, elevation_m: float, start: str, end: str, models: list,
                       variables: list) -> dict:
    """Archived short-lead surface fields per model: {model: frame}."""
    params = {"latitude": lat, "longitude": lon, "elevation": elevation_m, "start_date": start, "end_date": end,
              "models": ",".join(models), "hourly": ",".join(variables)}
    payload = get_json("om_hist", HISTORICAL_URL, params)
    return _split_models(payload, models)


def previous_runs(lat: float, lon: float, elevation_m: float, start: str, end: str, models: list,
                  lead_days: list, variable: str = "precipitation") -> dict:
    """Archived forecasts by lead day: {model: frame with columns lead0, lead1, ...}."""
    variables = [variable if d == 0 else f"{variable}_previous_day{d}" for d in lead_days]
    params = {"latitude": lat, "longitude": lon, "elevation": elevation_m, "start_date": start, "end_date": end,
              "models": ",".join(models), "hourly": ",".join(variables)}
    frames = _split_models(get_json("om_prev", PREVIOUS_RUNS_URL, params), models)
    rename = {v: f"lead{d}" for v, d in zip(variables, lead_days)}
    return {model: frame.rename(columns=rename) for model, frame in frames.items()}


def forecast(lat: float, lon: float, elevation_m: float, models: list, variables: list, days: int = 10,
             max_age_h: float = 3.0, past_days: int = 4) -> dict:
    params = {"latitude": lat, "longitude": lon, "elevation": elevation_m, "forecast_days": days,
              "past_days": past_days, "models": ",".join(models), "hourly": ",".join(variables)}
    return _split_models(get_json("om_fcst", FORECAST_URL, params, max_age_h), models)


def ensemble(lat: float, lon: float, elevation_m: float, model: str, variables: list, days: int = 10,
             max_age_h: float = 3.0) -> pd.DataFrame:
    """Ensemble members for one system; columns are '<variable>' (control) and '<variable>_memberNN'."""
    params = {"latitude": lat, "longitude": lon, "elevation": elevation_m, "forecast_days": days,
              "models": model, "hourly": ",".join(variables)}
    return hourly_frame(get_json("om_ens", ENSEMBLE_URL, params, max_age_h))


def _split_models(payload: dict, models: list) -> dict:
    frame = hourly_frame(payload)
    if len(models) == 1 and not any(c.endswith(models[0]) for c in frame.columns):
        return {models[0]: frame}
    out = {}
    for model in models:
        columns = [c for c in frame.columns if c.endswith(f"_{model}")]
        out[model] = frame[columns].rename(columns={c: c.removesuffix(f"_{model}") for c in columns})
    return out
