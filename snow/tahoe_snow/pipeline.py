"""One forecast run: fetch, correct, convert to snow, blend, and write the site's JSON."""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tahoe_snow import biascorrect, blend, powder
from tahoe_snow.config import DATA, DET_MODELS, ENS_MODELS, M_PER_FT, MM_PER_IN, MODELS, RESORTS, STATIONS
from tahoe_snow.snow import features, phase, ratio
from tahoe_snow.snow.model import SnowModel
from tahoe_snow.sources import openmeteo

TZ = "America/Los_Angeles"
DAYS = 10
HISTORY_DAYS = 3
DETERMINISTIC_DAYS = 5
MAX_GAP_H = 6
DELTAS_C = np.arange(-4.0, 4.01, 1.0)
LAPSE_M_PER_C = 1000.0 / 6.5
DEFAULT_PHASE = ("wet-bulb logistic", {"center_c": 0.5, "width_c": 0.4})
CM_PER_IN = MM_PER_IN / 10
MPH_PER_MS = 2.23694
WINDOWS = {"next24": (0, 24), "next72": (0, 72), "days4to5": (72, 120), "days6to10": (120, 240)}
ENSEMBLE_VARS = ["precipitation", "temperature_2m"]


def load_snow_model() -> tuple:
    """The trained snow model when its files exist, else Kuchera with a default rain/snow split."""
    try:
        kind, params = phase.load()
    except FileNotFoundError:
        kind, params = DEFAULT_PHASE
    try:
        sidecar = json.loads((MODELS / "snow_ratio.json").read_text())
        return SnowModel(ratio.load(), kind, params), sidecar["model"]
    except FileNotFoundError:
        return SnowModel(ratio.Kuchera(), kind, params), "Kuchera (trained model not yet fitted)"


def load_correction() -> biascorrect.Correction | None:
    path = MODELS / "bias.json"
    return biascorrect.from_json(json.loads(path.read_text())) if path.exists() else None


def fill_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill short gaps in time (models that report upper-air fields every 3 or 6 hours)."""
    level_columns = [c for c in frame.columns if c.endswith("hPa")]
    frame = frame.copy()
    frame[level_columns] = frame[level_columns].interpolate(limit=MAX_GAP_H, limit_area="inside")
    return frame


def shifted(hourly: pd.DataFrame, delta_c: float) -> pd.DataFrame:
    """Hourly features for a column uniformly warmer by ``delta_c``."""
    out = hourly.copy()
    temperature_columns = [c for c in out.columns if c.startswith("t") and c != "tmax_col" and c[1:].isdigit()]
    out[temperature_columns + ["tw0", "tmax_col"]] += delta_c
    out["snow_level_m"] += delta_c * LAPSE_M_PER_C
    return out


def local_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return index.tz_localize("UTC").tz_convert(TZ).tz_localize(None).normalize()


def corrected_liquid(precip: pd.Series, model: str, station: str, today: pd.Timestamp,
                     correction: biascorrect.Correction | None) -> pd.Series:
    """Hourly liquid scaled so each local day's total equals the bias-corrected total."""
    if correction is None:
        return precip
    days = local_days(precip.index)
    totals = precip.groupby(days).transform("sum")
    lead = np.clip((days - today).days, 0, None)
    factor = np.ones(len(precip))
    for lead_day in np.unique(lead):
        mask = lead == lead_day
        factor[mask] = correction.factor(model, station, int(lead_day), totals.to_numpy()[mask])
    return precip * factor


def model_snow(frame: pd.DataFrame, model: str, resort, snow_model: SnowModel, today: pd.Timestamp,
               correction) -> dict:
    """Per-elevation hourly snow for one deterministic model, plus what the ensemble step needs."""
    profile = fill_profile(frame)
    if profile[[c for c in profile.columns if c.startswith("temperature_") and c.endswith("hPa")]].isna().all().all():
        return {}
    liquid = corrected_liquid(profile["precipitation"], model, resort.station, today, correction)
    out = {}
    for label, elev_m in resort.elevations().items():
        hourly = features.hourly_features(profile, elev_m)
        result = snow_model.snowfall(hourly, liquid, elev_m)
        result["wind_ms"] = hourly["wind0"]
        result["temp_c"] = hourly["t0"]
        # Snow per mm of liquid at each temperature offset, for converting ensemble members.
        per_mm = np.column_stack([
            (lambda r: (r["snow_fraction"] * r["slr"] / 10.0).to_numpy())(
                snow_model.snowfall(shifted(hourly, delta), liquid, elev_m)) for delta in DELTAS_C])
        out[label] = {"hourly": result, "per_mm": per_mm, "elev_m": elev_m}
    out["_liquid_factor"] = (liquid / profile["precipitation"].where(profile["precipitation"] > 0)).fillna(1.0)
    out["_t2m"] = profile["temperature_2m"]
    return out


def member_snow(members: pd.DataFrame, parent: dict, label: str) -> pd.DataFrame:
    """Hourly snow (cm) per ensemble member, using the parent model's snow conversion.

    Each member's surface-temperature difference from the parent shifts the conversion.
    """
    precip = members.filter(regex=r"^precipitation")
    temps = members.filter(regex=r"^temperature_2m")
    index = precip.index.intersection(parent[label]["hourly"].index)
    rows = parent[label]["hourly"].index.get_indexer(index)
    per_mm = parent[label]["per_mm"][rows]
    factor = parent["_liquid_factor"].reindex(index).to_numpy()
    parent_t = parent["_t2m"].reindex(index).to_numpy()
    out = {}
    for column in precip.columns:
        suffix = column[len("precipitation"):]
        liquid = precip.loc[index, column].to_numpy() * factor
        t_column = f"temperature_2m{suffix}"
        delta = temps.loc[index, t_column].to_numpy() - parent_t if t_column in temps else np.zeros(len(index))
        delta = np.clip(np.nan_to_num(delta), DELTAS_C[0], DELTAS_C[-1])
        position = (delta - DELTAS_C[0]) / (DELTAS_C[1] - DELTAS_C[0])
        low = np.clip(np.floor(position).astype(int), 0, len(DELTAS_C) - 2)
        weight = position - low
        rate = per_mm[np.arange(len(index)), low] * (1 - weight) + per_mm[np.arange(len(index)), low + 1] * weight
        out[column] = liquid * rate
    return pd.DataFrame(out, index=index)


def window_sum(frame: pd.DataFrame, start: pd.Timestamp, hours: tuple) -> pd.Series:
    """Column sums over [start + hours[0], start + hours[1]); NaN for a column missing more than 10 %."""
    a, b = start + pd.Timedelta(hours=hours[0]), start + pd.Timedelta(hours=hours[1])
    piece = frame.loc[(frame.index >= a) & (frame.index < b)]
    expected = hours[1] - hours[0]
    return piece.sum().where(piece.notna().sum() >= 0.9 * expected)


def day_part(hourly: pd.DataFrame, summit: pd.DataFrame, day: pd.Timestamp) -> dict:
    """Powder-score inputs for the ski day ``day``: snow from 4 pm the day before to 4 pm that day."""
    end = (day + pd.Timedelta(hours=16)).tz_localize(TZ).tz_convert("UTC").tz_localize(None)
    start = end - pd.Timedelta(hours=24)
    piece = hourly.loc[(hourly.index > start) & (hourly.index <= end)]
    snow = piece["snow_cm"].fillna(0.0)
    if len(piece) < 20 or snow.sum() < 0.25:
        return {"snow_in": 0.0, "score": 0.0}
    slr = float((piece["slr"] * snow).sum() / snow.sum())
    half = len(piece) // 2
    first, second = piece.iloc[:half], piece.iloc[half:]

    def mean_slr(part):
        weight = part["snow_cm"].fillna(0.0)
        return float((part["slr"] * weight).sum() / weight.sum()) if weight.sum() > 0 else np.nan

    change = mean_slr(second) - mean_slr(first)
    last_snow = snow[snow > 0].index[-1]
    windy = summit.loc[(summit.index > start) & (summit.index <= last_snow + pd.Timedelta(hours=12)), "wind_ms"]
    liquid = piece["liquid_mm"].fillna(0.0)
    rain = liquid * (1 - piece["snow_fraction"].fillna(1.0))
    local_hour = piece.index.tz_localize("UTC").tz_convert(TZ).hour
    overnight = snow[(local_hour >= 16) | (local_hour < 9)].sum() / snow.sum()
    part = powder.DayPart(snow_in=float(snow.sum() / CM_PER_IN), slr=slr,
                          slr_change=0.0 if np.isnan(change) else change,
                          ridge_wind_mph=float(windy.mean() * MPH_PER_MS) if len(windy) else 0.0,
                          rain_share=float(rain.sum() / liquid.sum()) if liquid.sum() > 0 else 0.0,
                          late_rain_mm=float(rain.iloc[-6:].sum()), overnight_share=float(overnight))
    return {"snow_in": round(part.snow_in, 1), "slr": round(slr, 1), "slr_change": round(part.slr_change, 1),
            "ridge_wind_mph": round(part.ridge_wind_mph), "rain_share": round(part.rain_share, 2),
            "overnight_share": round(part.overnight_share, 2), "score": round(powder.score(part), 1)}


def spread(total_cm: float, members: pd.Series, recenter: bool) -> dict:
    """Range and exceedance chances from ensemble-member totals (cm).

    With ``recenter`` the members are scaled so their mean matches the blended total (the coarse
    global ensembles run drier than the blend); the scale is capped at 0.5 to 2.
    """
    values = members.dropna().to_numpy(dtype=float)
    empty = {"low_in": None, "high_in": None, "pm_in": None, "prob_6in": None, "prob_12in": None,
             "members": int(len(values))}
    if len(values) < blend.MIN_MEMBERS:
        return empty
    if recenter and np.isfinite(total_cm) and values.mean() > 0.25:
        values = values * np.clip(total_cm / values.mean(), 0.5, 2.0)
    low, high = np.percentile(values, [10, 90])
    if np.isfinite(total_cm):
        low, high = min(low, total_cm), max(high, total_cm)
    return {"low_in": round(float(low) / CM_PER_IN, 1), "high_in": round(float(high) / CM_PER_IN, 1),
            "pm_in": round(float(values.std()) / CM_PER_IN, 1),
            "prob_6in": round(float((values >= 6 * CM_PER_IN).mean()), 2),
            "prob_12in": round(float((values >= 12 * CM_PER_IN).mean()), 2), "members": int(len(values))}


def _round(values, digits=1) -> list:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in np.asarray(values, dtype=float)]


def resort_forecast(resort, snow_model: SnowModel, correction, now: pd.Timestamp, weights: dict) -> tuple:
    """Site payload and archive rows for one resort."""
    today = now.tz_localize("UTC").tz_convert(TZ).tz_localize(None).normalize()
    variables = openmeteo.PROFILE_SURFACE_VARS + openmeteo.level_variables()
    frames = openmeteo.forecast(resort.lat, resort.lon, resort.summit_m, DET_MODELS, variables, days=DAYS)
    models = {}
    for model, frame in frames.items():
        if frame["precipitation"].notna().sum() == 0:
            continue
        result = model_snow(frame, model, resort, snow_model, today, correction)
        if result:
            models[model] = result
    if not models:
        raise RuntimeError(f"no usable model for {resort.name}")
    ensembles = {}
    for system, parent in ENS_MODELS.items():
        if parent not in models:
            continue
        try:
            ensembles[system] = (openmeteo.ensemble(resort.lat, resort.lon, resort.mid_m, system, ENSEMBLE_VARS,
                                                    days=DAYS), parent)
        except RuntimeError:
            continue
    midnight = today.tz_localize(TZ).tz_convert("UTC").tz_localize(None)
    # Three days back, so the page can total the storm in progress.
    hours = pd.date_range(midnight - pd.Timedelta(hours=HISTORY_DAYS * 24), now + pd.Timedelta(hours=DAYS * 24 - 1),
                          freq="h")
    payload = {"key": resort.key, "name": resort.name, "lat": resort.lat, "lon": resort.lon,
               "station": STATIONS[resort.station].name,
               "weak_station_match": resort.weak_match, "elevations": {}, "models": list(models)}
    archive = []
    summit_blend = None
    for label, elev_m in resort.elevations().items():
        snow = pd.DataFrame({m: r[label]["hourly"]["snow_cm"] for m, r in models.items()}).reindex(hours)
        fields = {name: blend.weighted_mean(
            pd.DataFrame({m: r[label]["hourly"][name] for m, r in models.items()}).reindex(hours), weights)
            for name in ("snow_cm", "liquid_mm", "slr", "snow_fraction", "snow_level_m", "wind_ms", "temp_c")}
        blended = pd.DataFrame(fields)
        if label == "summit":
            summit_blend = blended
        members = pd.concat([member_snow(frame, models[parent], label).add_prefix(f"{system}:")
                             for system, (frame, parent) in ensembles.items()], axis=1).reindex(hours) \
            if ensembles else pd.DataFrame(index=hours)
        windows = {}
        for name, span in WINDOWS.items():
            total = float(window_sum(blended[["snow_cm"]], now, span).iloc[0])
            recenter = span[1] <= DETERMINISTIC_DAYS * 24
            windows[name] = {"snow_in": _round([total / CM_PER_IN])[0],
                             **spread(total, window_sum(members, now, span), recenter)}
        daily = blend.local_day_totals(blended[["snow_cm", "liquid_mm"]])
        by_model = blend.local_day_totals(snow)
        member_days = blend.local_day_totals(members) if len(members.columns) else pd.DataFrame()
        days = []
        for day in daily.index:
            lead = int((day - today).days)
            if not np.isfinite(daily.loc[day, "snow_cm"]):
                continue
            row = member_days.loc[day] if day in member_days.index else pd.Series(dtype=float)
            stats = spread(daily.loc[day, "snow_cm"], row, recenter=lead <= DETERMINISTIC_DAYS)
            entry = {"date": day.strftime("%Y-%m-%d"), "lead_day": lead,
                     "snow_in": _round([daily.loc[day, "snow_cm"] / CM_PER_IN])[0],
                     "liquid_in": _round([daily.loc[day, "liquid_mm"] / MM_PER_IN], 2)[0],
                     "low_in": stats["low_in"], "high_in": stats["high_in"], "pm_in": stats["pm_in"],
                     "prob_6in": stats["prob_6in"], "prob_12in": stats["prob_12in"],
                     "by_model": {m: _round([by_model.loc[day, m] / CM_PER_IN])[0] for m in by_model.columns},
                     "past": bool(day < today),
                     "powder": day_part(blended, summit_blend if summit_blend is not None else blended, day)}
            days.append(entry)
            for model in by_model.columns:
                archive.append({"resort": resort.key, "elevation": label, "date": entry["date"], "lead_day": lead,
                                "model": model, "snow_cm": _round([by_model.loc[day, model]], 2)[0]})
            archive.append({"resort": resort.key, "elevation": label, "date": entry["date"], "lead_day": lead,
                            "model": "blend", "snow_cm": _round([daily.loc[day, "snow_cm"]], 2)[0],
                            "liquid_mm": _round([daily.loc[day, "liquid_mm"]], 2)[0],
                            "low_in": stats["low_in"], "high_in": stats["high_in"],
                            "prob_6in": stats["prob_6in"], "prob_12in": stats["prob_12in"]})
        payload["elevations"][label] = {
            "elevation_ft": int(round(elev_m / M_PER_FT, -1)), "windows": windows, "days": days,
            "hourly": {"snow_in": _round(blended["snow_cm"] / CM_PER_IN, 2), "slr": _round(blended["slr"]),
                       "snow_level_ft": _round(blended["snow_level_m"] / M_PER_FT, -1),
                       "wind_mph": _round(blended["wind_ms"] * MPH_PER_MS, 0),
                       "temp_f": _round(blended["temp_c"] * 1.8 + 32, 0)}}
    payload["hours_utc"] = [h.strftime("%Y-%m-%dT%H:00Z") for h in hours]
    return payload, archive


def run(now: datetime | None = None) -> dict:
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None).floor("h")
    snow_model, ratio_name = load_snow_model()
    correction = load_correction()
    resorts, archive, failed = [], [], []
    for resort in RESORTS.values():
        try:
            payload, rows = resort_forecast(resort, snow_model, correction, now, weights={})
            resorts.append(payload)
            archive.extend(rows)
            print(f"{resort.name}: {payload['elevations']['summit']['windows']['next72']}", flush=True)
        except RuntimeError as error:
            failed.append(resort.key)
            print(f"{resort.name}: FAILED {error}", flush=True)
    if not resorts:
        raise SystemExit("no resort forecast could be produced")
    forecast = {"generated_utc": now.strftime("%Y-%m-%dT%H:00Z"), "snow_ratio_model": ratio_name,
                "rain_snow_split": {"kind": snow_model.phase_kind, "params": snow_model.phase_params},
                "bias_corrected": correction is not None, "deterministic_days": DETERMINISTIC_DAYS,
                "failed_resorts": failed, "powder_formula": powder.FORMULA, "resorts": resorts}
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "forecast.json").write_text(json.dumps(forecast, separators=(",", ":")))
    folder = DATA / "archive" / now.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{now.strftime('%d_%H')}z.json").write_text(json.dumps(
        {"generated_utc": forecast["generated_utc"], "rows": archive}, separators=(",", ":")))
    return forecast
