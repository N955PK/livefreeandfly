"""How this season's snowpack compares with a usual one, at each mountain's snow sensor.

The usual year is the median over the sensor's own daily record: the snow depth on each date, and the season's
peak. A sensor with no usable depth gauge is compared by the water it weighs. Each sensor also gives the curves
the page draws: the usual year, this year so far, and the ten winters before it, by day of the water year.
"""
import pandas as pd

from tahoe_snow.config import ALL_STATIONS, MM_PER_IN, RESORTS
from tahoe_snow.sources import cdec, snotel

HISTORY_START = "1990-10-01"
MIN_YEARS = 10
FULL_YEAR_DAYS = 300
# Below this much in a usual year, a percent of normal is a ratio of two small numbers and means little.
MIN_NORMAL_IN = {"depth": 4.0, "water": 1.0}
CM_PER_IN = 2.54
PST_OFFSET_H = 8
STEP_DAYS = 3
PAST_YEARS = 10
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


def describe(daily_in: pd.Series, normal_by_day: pd.Series, day: pd.Timestamp, peak_in: float, peak_date: str) -> dict:
    """The usual reading on this date, the usual peak, and the curves, from daily readings and the usual year.
    Winters are named by the year they end in."""
    year, into_year = water_year(daily_in.index), day_of_water_year(daily_in.index)
    this_year = water_year(pd.DatetimeIndex([day]))[0]
    by_day = pd.Series(daily_in.values, index=into_year)
    today = day_of_water_year(pd.DatetimeIndex([day]))[0]
    return {"normal_in": float(normal_by_day.get(today, float("nan"))), "peak_in": peak_in, "peak_date": peak_date,
            "curve": {"step_days": STEP_DAYS, "normal": sampled(normal_by_day),
                      "years": {str(winter): sampled(by_day[year == winter])
                                for winter in range(this_year - PAST_YEARS, this_year + 1) if (year == winter).any()}}}


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
    told = describe(smooth, normal_by_day, day, float(years.max()[full].median()), usual_peak.strftime("%m-%d"))
    return {**told, "years": int(full.sum())}


def history(station, day: pd.Timestamp) -> pd.DataFrame:
    end = day.strftime("%Y-%m-%d")
    if station.source == "cdec":
        return cdec.daily(station.triplet.split(":")[0], HISTORY_START, end, max_age_h=24.0)
    return snotel.daily(station.triplet, HISTORY_START, end, max_age_h=24.0)


def station_normal(station, day: pd.Timestamp) -> dict | None:
    """A sensor's usual year in snow depth, or in the water it weighs where it has no usable depth gauge."""
    frame = history(station, day)
    for measure, column, per_inch in (("depth", "depth_cm", CM_PER_IN), ("water", "swe_mm", MM_PER_IN)):
        if column in frame and (measure == "water" or station.depth):
            normal = from_history(frame[column] / per_inch, day)
            if normal:
                return {**normal, "measure": measure}
    return None


def normals(now: pd.Timestamp) -> dict:
    """The usual year at every sensor a mountain is paired with, keyed by the sensor's id."""
    day = (now - pd.Timedelta(hours=PST_OFFSET_H)).normalize()
    used = {ALL_STATIONS[resort.station] for resort in RESORTS.values() if resort.station}
    return {station.triplet: station_normal(station, day) for station in used}


def summary(observed: dict | None, normal: dict | None) -> dict | None:
    """Where the sensor's latest reading stands against its usual year."""
    now_in = (observed or {}).get(f"{(normal or {}).get('measure')}_in")
    if now_in is None or not normal["peak_in"] or pd.isna(normal["normal_in"]):
        return None
    usual = normal["normal_in"]
    return {"measure": normal["measure"], "now_in": now_in, "normal_in": round(usual, 1),
            "pct_normal": round(100 * now_in / usual) if usual >= MIN_NORMAL_IN[normal["measure"]] else None,
            "peak_in": round(normal["peak_in"], 1), "pct_peak": round(100 * now_in / normal["peak_in"]),
            "peak_date": normal["peak_date"]}
