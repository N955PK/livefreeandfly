"""How this season's snowpack compares with a usual one, at each mountain's snow sensor.

The usual year is the median over the sensor's record: the water in the snow on this date, and the season's
peak. SNOTEL publishes both; for a California pillow they come from its own daily history.
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


def water_year(index: pd.DatetimeIndex) -> pd.Index:
    return index.year + (index.month >= 10)


def from_history(swe_in: pd.Series, day: pd.Timestamp) -> dict | None:
    """The usual water on this date and the usual peak, as medians over the complete water years before this one."""
    swe = swe_in.dropna().rolling(5, center=True, min_periods=1).median()
    past = swe[water_year(swe.index) < water_year(pd.DatetimeIndex([day]))[0]]
    same_day = past[(past.index.month == day.month) & (past.index.day == day.day)]
    years = past.groupby(water_year(past.index))
    full = years.count() >= FULL_YEAR_DAYS
    if len(same_day) < MIN_YEARS or full.sum() < MIN_YEARS:
        return None
    peak_day = years.idxmax()[full]
    into_year = (peak_day - pd.to_datetime((peak_day.index - 1).astype(str) + "-10-01").values).dt.days.median()
    usual_peak = pd.Timestamp("2001-10-01") + pd.Timedelta(days=int(into_year))
    return {"normal_in": float(same_day.median()), "peak_in": float(years.max()[full].median()),
            "peak_date": usual_peak.strftime("%m-%d"), "years": int(full.sum())}


def snotel_normals(triplets: list, day: pd.Timestamp) -> dict:
    params = {"stationTriplets": ",".join(triplets), "elements": "WTEQ", "duration": "DAILY",
              "beginDate": (day - pd.Timedelta(days=4)).strftime("%Y-%m-%d"), "endDate": day.strftime("%Y-%m-%d"),
              "centralTendencyType": "MEDIAN"}
    out = {}
    for station in get_json("snotel", snotel.URL, params, 24.0):
        for series in station.get("data", []):
            medians = [value["median"] for value in series.get("values", []) if value.get("median") is not None]
            peak = (series.get("timingCentralTendencies") or {}).get("medianPeak")
            if medians and peak:
                out[station["stationTriplet"]] = {"normal_in": medians[-1], "peak_in": peak["value"],
                                                  "peak_date": f"{peak['month']:02d}-{peak['day']:02d}"}
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
    if water_in is None or not normal or not normal["peak_in"]:
        return None
    usual = normal["normal_in"]
    return {"water_in": water_in, "normal_in": round(usual, 1),
            "pct_normal": round(100 * water_in / usual) if usual >= MIN_NORMAL_IN else None,
            "peak_in": round(normal["peak_in"], 1), "pct_peak": round(100 * water_in / normal["peak_in"]),
            "peak_date": normal["peak_date"]}
