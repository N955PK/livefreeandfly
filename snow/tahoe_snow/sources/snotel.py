"""SNOTEL observations from the NRCS AWDB REST API (no key).

Daily values are midnight readings in Pacific Standard Time (UTC-8, no daylight
saving): the value dated D is the reading at the end of D (midnight starting D+1),
so the gain during D is value(D) - value(D-1). Hourly readings carry their own
timestamps and confirm this.
"""
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import MM_PER_IN

URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
ELEMENTS = {"WTEQ": "swe_mm", "SNWD": "depth_cm", "PREC": "prec_mm", "TAVG": "tavg_c", "TMAX": "tmax_c",
            "TMIN": "tmin_c", "TOBS": "tobs_c"}
# AWDB quality flags that mark a value as suspect.
BAD_FLAGS = {"S", "N"}


def _convert(column: str, values: pd.Series) -> pd.Series:
    if column.endswith("_mm"):
        return values * MM_PER_IN
    if column.endswith("_cm"):
        return values * MM_PER_IN / 10.0
    return (values - 32.0) / 1.8


def parse(payload: list, time_key: str = "date") -> pd.DataFrame:
    frames = {}
    for block in payload[0]["data"] if payload else []:
        column = ELEMENTS.get(block["stationElement"]["elementCode"])
        if column is None:
            continue
        rows = [(v["date"], v.get("value")) for v in block["values"] if v.get("qcFlag") not in BAD_FLAGS]
        series = pd.Series(dict(rows), dtype=float)
        frames[column] = _convert(column, series)
    out = pd.DataFrame(frames)
    out.index = pd.to_datetime(out.index)
    out.index.name = time_key
    return out.sort_index()


def daily(triplet: str, start: str, end: str, max_age_h: float | None = None) -> pd.DataFrame:
    params = {"stationTriplets": triplet, "elements": "WTEQ,SNWD,PREC,TAVG,TMAX,TMIN", "duration": "DAILY",
              "beginDate": start, "endDate": end, "returnFlags": "true"}
    return parse(get_json("snotel", URL, params, max_age_h))


def hourly(triplet: str, start: str, end: str, max_age_h: float | None = None) -> pd.DataFrame:
    """Hourly readings, indexed by PST timestamps."""
    params = {"stationTriplets": triplet, "elements": "WTEQ,SNWD,PREC,TOBS", "duration": "HOURLY",
              "beginDate": start, "endDate": end, "returnFlags": "true"}
    return parse(get_json("snotel", URL, params, max_age_h), time_key="time_pst")


def daily_gains(frame: pd.DataFrame) -> pd.DataFrame:
    """Per-day gains: row D holds the change over day D, from the reading dated D-1 to the one dated D."""
    out = pd.DataFrame(index=frame.index)
    for column in ("swe_mm", "depth_cm", "prec_mm"):
        if column in frame:
            out[column.replace("_", "_gain_")] = frame[column] - frame[column].shift(1)
    for column in ("tavg_c", "tmax_c", "tmin_c"):
        if column in frame:
            out[column] = frame[column]
    consecutive = (frame.index.to_series() - frame.index.to_series().shift(1)) == pd.Timedelta(days=1)
    return out[consecutive.to_numpy()]
