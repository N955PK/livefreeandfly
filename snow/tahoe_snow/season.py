"""How this season's snowpack compares with a usual one, at each mountain's snow sensor.

The usual year is the median over the sensor's record: the water in the snow on each date, and the season's
peak. SNOTEL publishes both; for a California pillow they come from its own daily history. Each sensor also
gives the curves the page draws: the usual year, this year so far, and the ten winters before it, by day of the
water year.
"""
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import ALL_STATIONS, MM_PER_IN, RESORTS
from tahoe_snow.sources import cdec, snotel

HISTORY_START = "1990-10-01"
MIN_YEARS = 10
FULL_YEAR_DAYS = 300
# Below this much water in a usual year, a percent of normal is a ratio of two small numbers and means little.
MIN_NORMAL_IN = 1.0
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


def describe(swe_in: pd.Series, normal_by_day: pd.Series, day: pd.Timestamp, peak_in: float, peak_date: str) -> dict:
    """The usual water on this date, the usual peak, and the curves, from daily water and the usual year.
    Winters are named by the year they end in."""
    year, into_year = water_year(swe_in.index), day_of_water_year(swe_in.index)
    this_year = water_year(pd.DatetimeIndex([day]))[0]
    by_day = pd.Series(swe_in.values, index=into_year)
    today = day_of_water_year(pd.DatetimeIndex([day]))[0]
    return {"normal_in": float(normal_by_day.get(today, float("nan"))), "peak_in": peak_in, "peak_date": peak_date,
            "curve": {"step_days": STEP_DAYS, "normal": sampled(normal_by_day),
                      "years": {str(winter): sampled(by_day[year == winter])
                                for winter in range(this_year - PAST_YEARS, this_year + 1) if (year == winter).any()}}}


def from_history(swe_in: pd.Series, day: pd.Timestamp) -> dict | None:
    """A sensor's usual year as medians over the complete water years before this one."""
    swe = swe_in.dropna().rolling(5, center=True, min_periods=1).median()
    past = swe[water_year(swe.index) < water_year(pd.DatetimeIndex([day]))[0]]
    years = past.groupby(water_year(past.index))
    full = years.count() >= FULL_YEAR_DAYS
    complete = past[pd.Series(water_year(past.index), index=past.index).map(full).fillna(False).astype(bool)]
    if full.sum() < MIN_YEARS:
        return None
    normal_by_day = complete.groupby(day_of_water_year(complete.index)).median()
    peak_day = years.idxmax()[full]
    into_year = (peak_day - pd.to_datetime((peak_day.index - 1).astype(str) + "-10-01").values).dt.days.median()
    usual_peak = pd.Timestamp("2001-10-01") + pd.Timedelta(days=int(into_year))
    told = describe(swe, normal_by_day, day, float(years.max()[full].median()), usual_peak.strftime("%m-%d"))
    return {**told, "years": int(full.sum())}


def snotel_normals(triplets: list, day: pd.Timestamp) -> dict:
    start = pd.Timestamp(year=water_year(pd.DatetimeIndex([day]))[0] - PAST_YEARS - 1, month=10, day=1)
    params = {"stationTriplets": ",".join(triplets), "elements": "WTEQ", "duration": "DAILY",
              "beginDate": start.strftime("%Y-%m-%d"), "endDate": day.strftime("%Y-%m-%d"),
              "centralTendencyType": "MEDIAN"}
    out = {}
    for station in get_json("snotel", snotel.URL, params, 24.0):
        for series in station.get("data", []):
            frame = pd.DataFrame(series.get("values", []))
            peak = (series.get("timingCentralTendencies") or {}).get("medianPeak")
            if frame.empty or "median" not in frame or not peak:
                continue
            frame.index = pd.to_datetime(frame["date"])
            # The usual year is the same on every pass through the calendar, so any past year's dates carry all of it.
            usual = frame["median"].dropna()
            normal_by_day = usual.groupby(day_of_water_year(usual.index)).last()
            out[station["stationTriplet"]] = describe(frame["value"].dropna(), normal_by_day, frame.index[-1],
                                                      peak["value"], f"{peak['month']:02d}-{peak['day']:02d}")
    return out


def cdec_normal(station_id: str, day: pd.Timestamp) -> dict | None:
    history = cdec.daily(station_id, HISTORY_START, day.strftime("%Y-%m-%d"), max_age_h=24.0)
    return from_history(history["swe_mm"] / MM_PER_IN, day)


def normals(now: pd.Timestamp) -> dict:
    """The usual year at every sensor a mountain is paired with, keyed by the sensor's id."""
    day = (now - pd.Timedelta(hours=PST_OFFSET_H)).normalize()
    used = {ALL_STATIONS[resort.station] for resort in RESORTS.values() if resort.station}
    out = snotel_normals(sorted(s.triplet for s in used if s.source == "snotel"), day)
    for station in used:
        if station.source == "cdec":
            out[station.triplet] = cdec_normal(station.triplet.split(":")[0], day)
    return out


def summary(water_in: float | None, normal: dict | None) -> dict | None:
    if water_in is None or not normal or not normal["peak_in"] or pd.isna(normal["normal_in"]):
        return None
    usual = normal["normal_in"]
    return {"water_in": water_in, "normal_in": round(usual, 1),
            "pct_normal": round(100 * water_in / usual) if usual >= MIN_NORMAL_IN else None,
            "peak_in": round(normal["peak_in"], 1), "pct_peak": round(100 * water_in / normal["peak_in"]),
            "peak_date": normal["peak_date"]}
