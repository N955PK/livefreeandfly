"""One forecast run: fetch, correct, convert to snow, blend, and write the site's JSON."""
import functools
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tahoe_snow import biascorrect, blend, cache, config, powder, season, usage
from tahoe_snow.config import ALL_STATIONS, DATA, DET_MODELS, ENS_MODELS, M_PER_FT, MM_PER_IN, MODELS, REGIONS, RESORTS
from tahoe_snow.snow import features, phase, ratio
from tahoe_snow.snow.model import SnowModel
from tahoe_snow.sources import cdec, openmeteo, snotel

# Two weeks. Past day 10 only the models that run that far are in the blend (ICON stops near 7 days, GEM at 10).
DAYS = 14
HISTORY_DAYS = 7
DETERMINISTIC_DAYS = 5
MAX_GAP_H = 6
DELTAS_C = np.arange(-4.0, 4.01, 1.0)
LAPSE_M_PER_C = 1000.0 / 6.5
DEFAULT_PHASE = ("wet-bulb logistic", {"center_c": 0.5, "width_c": 0.4})
CM_PER_IN = MM_PER_IN / 10
MPH_PER_MS = 2.23694
WINDOWS = {"next24": (0, 24), "next72": (0, 72), "days4to5": (72, 120), "days6to10": (120, 240)}
# The regions the single forecast.json still covers.
HOME_REGIONS = ("tahoe", "mammoth")
ENSEMBLE_VARS = ["precipitation", "temperature_2m"]


def load_snow_model() -> tuple:
    """The trained snow model when its files exist, else Kuchera with a default rain/snow split."""
    try:
        kind, params = phase.load()
    except FileNotFoundError:
        kind, params = DEFAULT_PHASE
    try:
        sidecar = json.loads((MODELS / "snow_ratio.json").read_text())
        described = (f"trained on {sidecar['events']} hand-measured Sierra snow days at "
                     f"{sidecar['stations']} stations, {sidecar['first_date'][:4]} to {sidecar['last_date'][:4]}")
        return SnowModel(ratio.load(), kind, params), described
    except FileNotFoundError:
        return SnowModel(ratio.Kuchera(), kind, params), "Kuchera (trained model not yet fitted)"


def load_corrections() -> dict:
    """The liquid correction for each region that has one fitted (bias.json for Tahoe, bias_<region>.json)."""
    out = {}
    for region in {resort.region for resort in RESORTS.values()}:
        path = MODELS / ("bias.json" if region == "tahoe" else f"bias_{region}.json")
        if path.exists():
            out[region] = biascorrect.from_json(json.loads(path.read_text()))
    return out


def load_weights() -> dict:
    """Blend weights per model from held-out water error; equal weights when the file is absent."""
    path = MODELS / "weights.json"
    return json.loads(path.read_text()) if path.exists() else {}


def fill_profile(frame: pd.DataFrame) -> pd.DataFrame:
    """Fill short gaps in time (models that report upper-air fields every 3 or 6 hours)."""
    level_columns = [c for c in frame.columns if c.endswith("hPa") and c != openmeteo.WIND_DIRECTION]
    frame = frame.copy()
    frame[level_columns] = frame[level_columns].interpolate(limit=MAX_GAP_H, limit_area="inside")
    if openmeteo.WIND_DIRECTION in frame:
        frame[openmeteo.WIND_DIRECTION] = frame[openmeteo.WIND_DIRECTION].ffill(limit=MAX_GAP_H)
    return frame


def shifted(hourly: pd.DataFrame, delta_c: float) -> pd.DataFrame:
    """Hourly features for a column uniformly warmer by ``delta_c``."""
    out = hourly.copy()
    temperature_columns = [c for c in out.columns if c.startswith("t") and c != "tmax_col" and c[1:].isdigit()]
    out[temperature_columns + ["tw0", "tmax_col"]] += delta_c
    out["snow_level_m"] += delta_c * LAPSE_M_PER_C
    return out


def local_days(index: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    return index.tz_localize("UTC").tz_convert(tz).tz_localize(None).normalize()


def corrected_liquid(precip: pd.Series, model: str, station: str | None, today: pd.Timestamp,
                     correction: biascorrect.Correction | None, tz: str) -> pd.Series:
    """Hourly liquid scaled so each local day's total equals the bias-corrected total.

    A place with no station is left as the models have it: a map borrowed from other stations did no better
    than that in testing, and at Gem Pass it did worse.
    """
    if correction is None or station is None:
        return precip
    days = local_days(precip.index, tz)
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
    liquid = corrected_liquid(profile["precipitation"], model, resort.station, today, correction,
                              REGIONS[resort.region].tz)
    out = {}
    for label, elev_m in resort.elevations().items():
        hourly = features.hourly_features(profile, elev_m)
        result = snow_model.snowfall(hourly, liquid, elev_m)
        result["wind_ms"] = hourly["wind0"]
        result["wind_from_deg"] = profile[openmeteo.WIND_DIRECTION] if openmeteo.WIND_DIRECTION in profile else np.nan
        result["temp_c"] = hourly["t0"]
        result["cloud_pct"] = profile["cloud_cover"] if "cloud_cover" in profile else np.nan
        # Gusts: at the base, the model's own surface gust. Higher up that field runs low, so the estimate is
        # the faster of the wind at this height and the wind 500 m above it, which gusts mix down from.
        # (Tested against five winters of measured gusts at the Palisades sensor; see the testing page.)
        surface_gust = profile["wind_gusts_10m"] / 3.6 if "wind_gusts_10m" in profile else np.nan
        result["gust_ms"] = surface_gust if label == "base" else np.maximum(hourly["wind0"], hourly["wind500"])
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


SKI_DAY_START_H, SKI_DAY_END_H = 8, 16


def day_part(hourly: pd.DataFrame, summit: pd.DataFrame, day: pd.Timestamp, members: pd.DataFrame | None = None,
             recenter: bool = True, by_model: pd.DataFrame | None = None, *, tz: str) -> dict:
    """The ski day ``day``: snow from 4 pm the day before to 4 pm that day, split into overnight and daytime,
    with the powder score and the conditions during lift hours (8 am to 4 pm)."""
    def utc(hour: int, back_days: int = 0) -> pd.Timestamp:
        local = day - pd.Timedelta(days=back_days) + pd.Timedelta(hours=hour)
        return local.tz_localize(tz).tz_convert("UTC").tz_localize(None)

    start, opening, end = utc(SKI_DAY_END_H, back_days=1), utc(SKI_DAY_START_H), utc(SKI_DAY_END_H)
    piece = hourly.loc[(hourly.index > start) & (hourly.index <= end)]
    lifts = hourly.loc[(hourly.index > opening) & (hourly.index <= end)]
    out = {"snow_in": 0.0, "score": 0.0}
    if len(lifts) >= 6:
        def mean(column, scale=1.0, shift=0.0):
            value = lifts[column].mean()
            return None if not np.isfinite(value) else round(float(value) * scale + shift)

        gust = lifts["gust_ms"].max()
        out.update({"wind_mph": mean("wind_ms", MPH_PER_MS), "sky_pct": mean("cloud_pct"),
                    "wind_from_deg": _round(blend.mean_direction(lifts["wind_from_deg"]).reshape(1), -1)[0],
                    "gust_mph": None if not np.isfinite(gust) else round(float(gust) * MPH_PER_MS),
                    "temp_f": mean("temp_c", 1.8, 32.0),
                    "snowing_hours": int((lifts["snow_cm"].fillna(0.0) > 0.1).sum())})
    snow = piece["snow_cm"].fillna(0.0)
    if len(piece) < 20:
        return out
    night = float(snow[piece.index <= opening].sum())
    out.update({"night_in": round(night / CM_PER_IN, 1), "day_in": round((float(snow.sum()) - night) / CM_PER_IN, 1)})
    if by_model is not None:
        each = by_model.loc[(by_model.index > start) & (by_model.index <= end)]
        sums = each.sum().where(each.notna().sum() >= 20)
        out["models"] = {model: _round([value / CM_PER_IN])[0] for model, value in sums.items()}
    if members is not None and len(members.columns):
        window = members.loc[(members.index > start) & (members.index <= end)]
        totals = window.sum().where(window.notna().sum() >= 20)
        out["pm_in"] = spread(float(snow.sum()), totals, recenter)["pm_in"]
    if snow.sum() < 0.25:
        return out
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
    part = powder.DayPart(snow_in=float(snow.sum() / CM_PER_IN), slr=slr,
                          slr_change=0.0 if np.isnan(change) else change,
                          ridge_wind_mph=float(windy.mean() * MPH_PER_MS) if len(windy) else 0.0,
                          rain_share=float(rain.sum() / liquid.sum()) if liquid.sum() > 0 else 0.0,
                          late_rain_mm=float(rain.iloc[-6:].sum()),
                          overnight_share=float(night / snow.sum()))
    out.update({"snow_in": round(part.snow_in, 1), "slr": round(slr, 1), "slr_change": round(part.slr_change, 1),
                "ridge_wind_mph": round(part.ridge_wind_mph), "rain_share": round(part.rain_share, 2),
                "overnight_share": round(part.overnight_share, 2), "score": round(powder.score(part), 1)})
    return out


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


def observed(resort, now: pd.Timestamp, hours: pd.DatetimeIndex) -> dict | None:
    """What the resort's snow sensor has measured: the latest readings, three-day gains, and the hourly
    depth over the page's history window (settled depth, not board totals). None without a paired station.
    A sensor with no usable depth gauge reports water alone; the depth fields are then None."""
    if resort.station is None:
        return None
    station = ALL_STATIONS[resort.station]
    start = (hours[0] - pd.Timedelta(hours=24 + snotel_offset_h(resort))).strftime("%Y-%m-%d")
    end = (now + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        frame = cdec.hourly(station.triplet.split(":")[0], start, end, max_age_h=1.0) if station.source == "cdec" \
            else snotel.hourly(station.triplet, start, end, max_age_h=1.0)
    except (RuntimeError, ValueError):
        return None
    frame = frame.reindex(columns=["depth_cm", "swe_mm", "tobs_c"])
    if not station.depth:
        frame["depth_cm"] = np.nan
    frame = frame.dropna(subset=["depth_cm", "swe_mm"], how="all")
    if frame.empty:
        return None
    frame.index = frame.index + pd.Timedelta(hours=snotel_offset_h(resort))   # station clock (standard time) to UTC
    frame = frame[frame.index <= now]
    last = frame.index[-1]

    def gain(column: str, hours: int) -> float | None:
        window = frame.loc[frame.index >= last - pd.Timedelta(hours=hours), column].dropna()
        # The readings must reach both ends of the window, or the gain is over some shorter time.
        slack = pd.Timedelta(hours=6)
        start = last - pd.Timedelta(hours=hours)
        if len(window) < 2 or window.index[0] > start + slack or window.index[-1] < last - slack:
            return None
        return float(window.iloc[-1] - window.iloc[0])

    def inches(value, per_inch: float, digits: int = 0):
        return None if value is None or not np.isfinite(value) else round(value / per_inch, digits)

    temp = frame["tobs_c"].dropna()
    # A depth sensor that has been silent for six hours is not a current reading.
    depth = frame["depth_cm"].dropna()
    depth = depth[depth.index >= last - pd.Timedelta(hours=6)]
    return {"station": station.name, "elevation_ft": int(round(station.elev_m / M_PER_FT, -1)),
            "as_of_utc": last.strftime("%Y-%m-%dT%H:00:00Z"),
            "depth_in": None if depth.empty else inches(float(depth.iloc[-1]), 2.54),
            "water_in": inches(None if frame["swe_mm"].dropna().empty else float(frame["swe_mm"].dropna().iloc[-1]),
                               MM_PER_IN, 1),
            "depth_gain_24h_in": inches(gain("depth_cm", 24), 2.54),
            "depth_gain_72h_in": inches(gain("depth_cm", 72), 2.54),
            "water_gain_24h_in": inches(gain("swe_mm", 24), MM_PER_IN, 1),
            "water_gain_72h_in": inches(gain("swe_mm", 72), MM_PER_IN, 1),
            "temp_f": None if temp.empty else round(float(temp.iloc[-1]) * 1.8 + 32),
            "depth_in_hourly": _round(frame["depth_cm"][~frame.index.duplicated()].reindex(hours) / 2.54, 0)}


def water_correction(resort, correction) -> str | None:
    """Which liquid correction the resort gets: its station's own curve, the one pooled over its region's
    stations, or none."""
    if correction is None or resort.station is None:
        return None
    return "station" if correction.fitted(resort.station) else "pooled"


def snotel_offset_h(resort) -> int:
    """Hours the mountain's sensor clock runs behind UTC: its region's standard time."""
    return REGIONS[resort.region].std_offset_h


def _round(values, digits=1) -> list:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in np.asarray(values, dtype=float)]


def resort_forecast(resort, snow_model: SnowModel, correction, now: pd.Timestamp, weights: dict) -> tuple:
    """Site payload and archive rows for one resort."""
    tz = REGIONS[resort.region].tz
    today = now.tz_localize("UTC").tz_convert(tz).tz_localize(None).normalize()
    variables = openmeteo.FORECAST_SURFACE_VARS + openmeteo.level_variables() + [openmeteo.WIND_DIRECTION]
    frames = openmeteo.forecast(resort.lat, resort.lon, resort.summit_m, DET_MODELS, variables, days=DAYS,
                                past_days=HISTORY_DAYS + 1)
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
    midnight = today.tz_localize(tz).tz_convert("UTC").tz_localize(None)
    # A week back, so the page can show recent history and total the storm in progress.
    hours = pd.date_range(midnight - pd.Timedelta(hours=HISTORY_DAYS * 24), now + pd.Timedelta(hours=DAYS * 24 - 1),
                          freq="h")
    payload = {"key": resort.key, "name": resort.name, "lat": resort.lat, "lon": resort.lon,
               "region": resort.region, "tz": tz, "kind": resort.kind, "pass": resort.pass_group,
               "station": ALL_STATIONS[resort.station].name if resort.station else None,
               "weak_station_match": resort.weak_match, "water_correction": water_correction(resort, correction),
               "observed": observed(resort, now, hours), "elevations": {},
               "models": list(models)}
    archive = []
    summit_blend = None
    for label, elev_m in resort.elevations().items():
        snow = pd.DataFrame({m: r[label]["hourly"]["snow_cm"] for m, r in models.items()}).reindex(hours)
        fields = {name: (functools.partial(blend.robust_mean, tz=tz) if name in ("snow_cm", "liquid_mm")
                         else blend.weighted_mean)(
            pd.DataFrame({m: r[label]["hourly"][name] for m, r in models.items()}).reindex(hours), weights)
            for name in ("snow_cm", "liquid_mm", "slr", "snow_fraction", "snow_level_m", "wind_ms", "temp_c",
                         "cloud_pct", "gust_ms")}
        blended = pd.DataFrame(fields)
        blended["wind_from_deg"] = blend.mean_direction(
            pd.DataFrame({m: r[label]["hourly"]["wind_from_deg"] for m, r in models.items()}).reindex(hours))
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
        daily = blend.local_day_totals(blended[["snow_cm", "liquid_mm"]], tz)
        by_model = blend.local_day_totals(snow, tz)
        member_days = blend.local_day_totals(members, tz) if len(members.columns) else pd.DataFrame()
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
                     "powder": day_part(blended, summit_blend if summit_blend is not None else blended, day,
                                        members, recenter=lead <= DETERMINISTIC_DAYS, by_model=snow, tz=tz)}
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
                       "wind_from_deg": _round(blended["wind_from_deg"], -1),
                       "gust_mph": _round(blended["gust_ms"] * MPH_PER_MS, 0),
                       "cloud_pct": _round(blended["cloud_pct"], 0),
                       "temp_f": _round(blended["temp_c"] * 1.8 + 32, 0)}}
    payload["hours_utc"] = [h.strftime("%Y-%m-%dT%H:00:00Z") for h in hours]
    return payload, archive


def add_season(resorts: list, now: pd.Timestamp, last: dict | None = None) -> dict:
    """Each mountain's snowpack against a usual year, and each sensor's curves by its name. A sensor network
    that cannot be reached leaves both out, unless ``last`` (the forecast published before this one) has them:
    a sensor's usual year changes once a day, so the last figures stand in until the network answers again."""
    try:
        normals = season.normals(now, [payload["key"] for payload in resorts])
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"season: FAILED {error}", flush=True)
        normals = {}
    before = {payload["key"]: payload.get("season") for payload in (last or {}).get("resorts", [])}
    curves = {ALL_STATIONS[triplet].name: {measure: usual["curve"] for measure, usual in normal.items()}
              for triplet, normal in normals.items() if normal}
    for payload in resorts:
        station = RESORTS[payload["key"]].station
        if station and not normals.get(station):
            payload["season"] = before.get(payload["key"])
            name = ALL_STATIONS[station].name
            if name in (last or {}).get("season_curves", {}):
                curves[name] = last["season_curves"][name]
        else:
            payload["season"] = season.summary(payload["observed"], normals.get(station))
    return curves


def write_whole(path, document: dict) -> None:
    """Write a JSON file so a reader never sees half of it: to a temporary file beside it, then into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, separators=(",", ":")))
    os.replace(temporary, path)


def read_region(key: str) -> dict | None:
    """A region's published forecast, or None when it has not been built or its file cannot be read (it then
    counts as never built and is rebuilt)."""
    path = DATA / "forecast" / f"{key}.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (ValueError, OSError) as error:
        print(f"{path.name}: unreadable, treated as not built ({error})", flush=True)
        return None


def read_legacy() -> dict | None:
    """The single forecast file every region used to share, where it is still published and readable."""
    path = DATA / "forecast.json"
    try:
        return json.loads(path.read_text()) if path.exists() else None
    except (ValueError, OSError):
        return None


def write_index() -> dict:
    """Every region and every mountain, and when each region's forecast was last published, in ``index.json``."""
    regions = {}
    for key, region in REGIONS.items():
        forecast = read_region(key)
        regions[key] = {"name": region.name, "tz": region.tz, "every_h": region.every_h,
                        "published_utc": forecast["published_utc"] if forecast else None}
    resorts = [{"key": r.key, "name": r.name, "region": r.region, "kind": r.kind, "pass": r.pass_group,
                "lat": r.lat, "lon": r.lon, "tz": REGIONS[r.region].tz,
                "station": ALL_STATIONS[r.station].name if r.station else None, "weak_station_match": r.weak_match}
               for r in RESORTS.values()]
    index = {"regions": regions, "resorts": resorts}
    write_whole(DATA / "index.json", index)
    return index


def write_home_forecast() -> dict | None:
    """The Tahoe and Eastern Sierra files as the single ``forecast.json`` the page and the reports still read, once
    both exist. It is stamped with the older of the two, so a stale half shows as stale."""
    parts = [read_region(key) for key in HOME_REGIONS]
    if not all(parts):
        return None
    forecast = {**parts[0], "generated_utc": min(p["generated_utc"] for p in parts),
                "published_utc": min(p["published_utc"] for p in parts),
                "usage": max(parts, key=lambda p: p["published_utc"])["usage"],
                "failed_resorts": [key for p in parts for key in p["failed_resorts"]],
                "resorts": [r for p in parts for r in p["resorts"]],
                "season_curves": {name: curve for p in parts for name, curve in p["season_curves"].items()}}
    write_whole(DATA / "forecast.json", forecast)
    return forecast


def due(now: datetime | None = None) -> str | None:
    """The region most overdue for a new forecast, by the fraction of its interval since it was generated, among
    those at or past their interval; a region never built is the most overdue. None when nothing is due."""
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None)
    late = {}
    for key, region in REGIONS.items():
        forecast = read_region(key)
        if forecast is None:
            late[key] = float("inf")
            continue
        age_h = (now - pd.Timestamp(forecast["generated_utc"]).tz_localize(None)) / pd.Timedelta(hours=1)
        if age_h >= region.every_h:
            late[key] = age_h / region.every_h
    return max(late, key=late.get) if late else None


def refresh_season(now: datetime | None = None) -> dict | None:
    """Bring each published region's season figures and curves up to date from the snow sensors alone, then the
    merged forecast. The forecasts themselves, and the time they were made, are left as they are."""
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None).floor("h")
    for key in REGIONS:
        forecast = read_region(key)
        if forecast:
            forecast["season_curves"] = add_season(forecast["resorts"], now, forecast)
            write_whole(DATA / "forecast" / f"{key}.json", forecast)
    return write_home_forecast()


def run(region: str, now: datetime | None = None) -> dict:
    """Forecast one region's mountains and publish ``forecast/<region>.json``, the index, the merged forecast, and
    the region's archive file. If no mountain succeeds nothing is written."""
    now = pd.Timestamp(now or datetime.now(timezone.utc)).tz_convert("UTC").tz_localize(None).floor("h")
    first_request = len(cache.REQUESTS)
    snow_model, ratio_name = load_snow_model()
    corrections = load_corrections()
    weights = load_weights()
    resorts, archive, failed = [], [], []
    for resort in config.resorts_in(region):
        try:
            payload, rows = resort_forecast(resort, snow_model, corrections.get(resort.region), now, weights=weights)
            resorts.append(payload)
            archive.extend(rows)
            print(f"{resort.name}: {payload['elevations']['summit']['windows']['next72']}", flush=True)
        except RuntimeError as error:
            failed.append(resort.key)
            print(f"{resort.name}: FAILED {error}", flush=True)
    stamp = now.to_pydatetime()
    ran = {**usage.of_run(cache.REQUESTS[first_request:]), "region": region}
    ledger_path = DATA / "archive" / "usage.json"
    if not resorts:
        usage.record(ran, stamp, ledger_path)      # what it asked for still counts against the allowance
        raise SystemExit(f"no resort forecast could be produced for {region}")
    season_curves = add_season(resorts, now, read_region(region) or read_legacy())
    forecast = {"generated_utc": now.strftime("%Y-%m-%dT%H:00:00Z"),
                "published_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "snow_ratio_model": ratio_name,
                "rain_snow_split": {"kind": snow_model.phase_kind, "params": snow_model.phase_params},
                "bias_corrected": "tahoe" in corrections, "deterministic_days": DETERMINISTIC_DAYS,
                "failed_resorts": failed, "powder_formula": powder.FORMULA, "resorts": resorts,
                "season_curves": season_curves,
                "usage": usage.summary(usage.record(ran, stamp, ledger_path), stamp)}
    write_whole(DATA / "forecast" / f"{region}.json", forecast)
    write_index()
    write_home_forecast()
    folder = DATA / "archive" / now.strftime("%Y/%m")
    folder.mkdir(parents=True, exist_ok=True)
    # Compact archive for grading: forecasts for today onward, as columns and rows.
    upcoming = [row for row in archive if row["lead_day"] >= 0]
    columns = list(dict.fromkeys(key for row in upcoming for key in row))
    (folder / f"{now.strftime('%d_%H')}z_{region}.json").write_text(json.dumps(
        {"generated_utc": forecast["generated_utc"], "columns": columns,
         "rows": [[row.get(column) for column in columns] for row in upcoming]}, separators=(",", ":")))
    return forecast
