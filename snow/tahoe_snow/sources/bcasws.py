"""Snow-sensor readings from British Columbia's Automated Snow Weather Stations (no key).

The province publishes one file per measure for the whole network: a row an hour since October 1, stamped in UTC,
and a column a station headed by its id and name ("2F10P Silver Star Mountain"). Snow water is in millimeters,
depth in centimeters and air temperature in Celsius. A station that lacks a sensor has no column in that file, or
an empty one. Frames carry the SNOTEL reader's column names, but their index is UTC, not a station clock.
"""
import io

import pandas as pd

from tahoe_snow.cache import get_text

URL = "https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data/{name}.csv"
FILES = {"SW": "swe_mm", "SD": "depth_cm", "TA": "tobs_c"}
# Readings outside these are sensor faults (a pillow reading far below zero, a depth spike).
VALID = {"swe_mm": (-25.0, 5000.0), "depth_cm": (-5.0, 1500.0), "tobs_c": (-50.0, 45.0)}


def column(text: str, station_id: str) -> pd.Series:
    """One station's readings from a measure's file, or nothing where the file has no column for it."""
    table = pd.read_csv(io.StringIO(text), index_col=0, dtype=str)
    named = [name for name in table.columns if name.split(" ", 1)[0] == station_id]
    if not named:
        return pd.Series(dtype=float)
    series = pd.to_numeric(table[named[0]], errors="coerce")
    series.index = pd.to_datetime(table.index, errors="coerce")
    return series[series.index.notna()].dropna()


def parse(texts: dict, station_id: str) -> pd.DataFrame:
    """A station's hourly readings from the measures' files, ``{"SW": text, ...}``."""
    frames = {}
    for name, measure in FILES.items():
        series = column(texts[name], station_id) if name in texts else pd.Series(dtype=float)
        low, high = VALID[measure]
        frames[measure] = series.where(series.between(low, high))
    out = pd.DataFrame(frames).dropna(how="all").sort_index()
    out.index.name = "time_utc"
    return out


def hourly(station_id: str, start: str | None = None, end: str | None = None,
           max_age_h: float | None = None) -> pd.DataFrame:
    """Hourly readings since October 1, indexed by UTC. The dates are taken for the other readers' sake: the
    files hold the season whole."""
    texts = {name: get_text("bcasws", URL.format(name=name), None, max_age_h, suffix=".csv") for name in FILES}
    return parse(texts, station_id)
