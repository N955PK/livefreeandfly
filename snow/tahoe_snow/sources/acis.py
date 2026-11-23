"""A weather station's daily climate record from the Regional Climate Centers' ACIS service (no key).

Each row is one local calendar day as the station reports it: the snow that fell that day, the snow on the ground,
the water that fell (rain and melted snow, from the gauge), and the day's high and low. The record runs some days
behind; days not yet in it come back as missing. A trace counts as nothing in the figures, and is flagged.
"""
import numpy as np
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import MM_PER_IN

URL = "https://data.rcc-acis.org/StnData"
# ACIS element -> column, in the order they are asked for. Snow and water are in inches, temperatures in Fahrenheit.
ELEMENTS = {"snow": "snowfall_cm", "snwd": "depth_cm", "pcpn": "prec_mm", "maxt": "tmax_c", "mint": "tmin_c"}
MISSING, TRACE = "M", "T"


def _number(text: str) -> float:
    """One reported value: missing as NaN, a trace as 0. Anything else unreadable counts as missing."""
    if text == TRACE:
        return 0.0
    try:
        return float(text)
    except (TypeError, ValueError):
        return np.nan


def _convert(column: str, values: pd.Series) -> pd.Series:
    if column.endswith("_mm"):
        return values * MM_PER_IN
    if column.endswith("_cm"):
        return values * MM_PER_IN / 10.0
    return (values - 32.0) / 1.8


def parse(payload: dict) -> pd.DataFrame:
    """Daily rows indexed by date, in metric units, with ``snowfall_trace`` and ``prec_trace`` marking the days
    that had a trace (counted as 0)."""
    rows = payload.get("data") or []
    dates = pd.to_datetime([row[0] for row in rows])
    out = pd.DataFrame(index=dates)
    for n, column in enumerate(ELEMENTS.values(), start=1):
        out[column] = _convert(column, pd.Series([_number(row[n]) for row in rows], index=dates, dtype=float))
    for n, column in ((1, "snowfall_trace"), (3, "prec_trace")):
        out[column] = [row[n] == TRACE for row in rows]
    out.index.name = "date"
    return out.sort_index()


def daily(sid: str, start: str, end: str, max_age_h: float | None = None, timeout: float = 30,
          retries: int = 2) -> pd.DataFrame:
    """The station's daily record from ``start`` to ``end`` (inclusive, YYYY-MM-DD)."""
    body = {"sid": sid, "sdate": start, "edate": end, "elems": [{"name": name} for name in ELEMENTS]}
    return parse(get_json("acis", URL, None, max_age_h, timeout=timeout, retries=retries, json_body=body))


def latest_day(frame: pd.DataFrame) -> pd.Timestamp | None:
    """The last day the record has a snowfall or depth reading for, or None."""
    have = frame[["snowfall_cm", "depth_cm"]].notna().any(axis=1) if len(frame) else pd.Series(dtype=bool)
    return have[have].index[-1] if have.any() else None
