"""How this season's snowpack compares with a usual one, at each mountain's snow sensor.

Three measures of a winter, each against the median over the sensor's own daily record: the snow depth on the
ground, the snow that has fallen so far, and the water the snowpack holds. The sensors weigh water and gauge
depth; snowfall is an estimate from the water gained on days cold enough to snow. Each measure also gives the
curves the page draws: the usual year, this year so far, and the ten winters before it, by day of the water year.
"""
import numpy as np
import pandas as pd

from tahoe_snow.config import ALL_STATIONS, MM_PER_IN, RESORTS
from tahoe_snow.sources import cdec, snotel

HISTORY_START = "1980-10-01"
MIN_YEARS = 10
FULL_YEAR_DAYS = 300
# Below this much in a usual year, a percent of normal is a ratio of two small numbers and means little.
MIN_NORMAL_IN = {"depth": 4.0, "snowfall": 10.0, "water": 1.0}
# Water that arrives on a day warmer than this is counted as rain, not snow.
SNOW_BELOW_C = 1.0
# Inches of snow per inch of water, by the day's mean temperature: Sierra cement near freezing, lighter when cold.
RATIO_BY_TEMP_C = ([-9.0, -1.0], [14.0, 8.0])
RATIO_UNKNOWN_TEMP = 10.0
CM_PER_IN = 2.54
PST_OFFSET_H = 8
STEP_DAYS = 3
PAST_YEARS = 10
RECORD_HOLD_DAYS = 15
YEAR_DAYS = 365


def water_year(index: pd.DatetimeIndex) -> pd.Index:
    return index.year + (index.month >= 10)


def day_of_water_year(index: pd.DatetimeIndex) -> pd.Index:
    """Days since October 1."""
    return (index - pd.to_datetime((water_year(index) - 1).astype(str) + "-10-01")).days


def sampled(by_day: pd.Series) -> list:
    """One value every few days from October 1, None where the sensor has nothing."""
    values = by_day[~by_day.index.duplicated()].reindex(range(0, YEAR_DAYS, STEP_DAYS)).clip(lower=0)
    return [None if pd.isna(value) else round(float(value), 1) for value in values]


def describe(daily_in: pd.Series, normal_by_day: pd.Series, day: pd.Timestamp, peak_in: float, peak_date: str,
             record: pd.Series) -> dict:
    """The usual reading on this date, the usual peak, and the curves, from daily readings and the usual year.
    Winters are named by the year they end in; the record is the complete winter with the highest peak."""
    year, into_year = water_year(daily_in.index), day_of_water_year(daily_in.index)
    this_year = water_year(pd.DatetimeIndex([day]))[0]
    by_day = pd.Series(daily_in.values, index=into_year)
    today = day_of_water_year(pd.DatetimeIndex([day]))[0]
    latest = by_day[year == this_year]
    return {"normal_in": float(normal_by_day.get(today, float("nan"))), "peak_in": peak_in, "peak_date": peak_date,
            "latest_in": None if latest.empty else round(float(latest.iloc[-1]), 1),
            "curve": {"step_days": STEP_DAYS, "normal": sampled(normal_by_day),
                      "years": {str(winter): sampled(by_day[year == winter])
                                for winter in range(this_year - PAST_YEARS, this_year + 1) if (year == winter).any()},
                      "record": {"year": str(water_year(record.index)[0]),
                                 "values": sampled(pd.Series(record.values, index=day_of_water_year(record.index)))}}}


def from_history(daily_in: pd.Series, day: pd.Timestamp) -> dict | None:
    """A sensor's usual year as medians over the complete water years before this one."""
    smooth = daily_in.dropna().rolling(5, center=True, min_periods=1).median()
    past = smooth[water_year(smooth.index) < water_year(pd.DatetimeIndex([day]))[0]]
    years = past.groupby(water_year(past.index))
    full = years.count() >= FULL_YEAR_DAYS
    complete = past[pd.Series(water_year(past.index), index=past.index).map(full).fillna(False).astype(bool)]
    if full.sum() < MIN_YEARS:
        return None
    normal_by_day = complete.groupby(day_of_water_year(complete.index)).median()
    peak_day = years.idxmax()[full]
    into_year = (peak_day - pd.to_datetime((peak_day.index - 1).astype(str) + "-10-01").values).dt.days.median()
    usual_peak = pd.Timestamp("2001-10-01") + pd.Timedelta(days=int(into_year))
    # The record winter is judged on a level that holds for two weeks, so a gauge's stray spike cannot claim it.
    steady = past.rolling(RECORD_HOLD_DAYS, center=True, min_periods=RECORD_HOLD_DAYS // 2).median()
    record_year = steady.groupby(water_year(steady.index)).max()[full].idxmax()
    told = describe(smooth, normal_by_day, day, float(years.max()[full].median()), usual_peak.strftime("%m-%d"),
                    steady[water_year(steady.index) == record_year].dropna())
    return {**told, "years": int(full.sum())}


def history(station, day: pd.Timestamp) -> pd.DataFrame:
    end = day.strftime("%Y-%m-%d")
    if station.source == "cdec":
        return cdec.daily(station.triplet.split(":")[0], HISTORY_START, end, max_age_h=24.0)
    return snotel.daily(station.triplet, HISTORY_START, end, max_age_h=24.0)


def snowfall_in(frame: pd.DataFrame) -> pd.Series:
    """Snow fallen so far each winter, in inches: each day's water gain on a day cold enough to snow, times a
    snow ratio for that day's temperature, added up from October 1."""
    gain = cdec.pillow_gains(frame["swe_mm"]) / MM_PER_IN
    temp = frame["tavg_c"].reindex(gain.index) if "tavg_c" in frame else pd.Series(np.nan, index=gain.index)
    ratio = np.where(temp.isna(), RATIO_UNKNOWN_TEMP, np.interp(temp.fillna(0.0), *RATIO_BY_TEMP_C))
    new = gain * ratio * (temp.isna() | (temp <= SNOW_BELOW_C))
    return new.groupby(water_year(new.index)).cumsum()


def station_normal(station, day: pd.Timestamp) -> dict:
    """A sensor's usual year by each measure it can give. A sensor with no usable depth gauge has no depth."""
    frame = history(station, day)
    series = {"depth": frame["depth_cm"] / CM_PER_IN if station.depth and "depth_cm" in frame else None,
              "snowfall": snowfall_in(frame), "water": frame["swe_mm"] / MM_PER_IN}
    found = {measure: from_history(daily, day) for measure, daily in series.items() if daily is not None}
    return {measure: normal for measure, normal in found.items() if normal}


def normals(now: pd.Timestamp) -> dict:
    """The usual year at every sensor a mountain is paired with, keyed by the sensor's id."""
    day = (now - pd.Timedelta(hours=PST_OFFSET_H)).normalize()
    used = {ALL_STATIONS[resort.station] for resort in RESORTS.values() if resort.station}
    return {station.triplet: station_normal(station, day) for station in used}


def summary(observed: dict | None, normal: dict | None) -> dict | None:
    """Where the sensor stands against its usual year, by measure. Depth and water are its latest readings."""
    out = {}
    for measure, usual in (normal or {}).items():
        now_in = usual["latest_in"] if measure == "snowfall" else (observed or {}).get(f"{measure}_in")
        if now_in is None or not usual["peak_in"] or pd.isna(usual["normal_in"]):
            continue
        out[measure] = {"now_in": now_in, "normal_in": round(usual["normal_in"], 1),
                        "pct_normal": (round(100 * now_in / usual["normal_in"])
                                       if usual["normal_in"] >= MIN_NORMAL_IN[measure] else None),
                        "peak_in": round(usual["peak_in"], 1), "pct_peak": round(100 * now_in / usual["peak_in"]),
                        "peak_date": usual["peak_date"]}
    return out or None
