"""Snow-sensor observations from the California Data Exchange Center (no key).

Frames match the SNOTEL reader's: the same column names and units, and the same dating. CDEC dates a daily
value by the midnight that starts the day (checked against its hourly readings), where the SNOTEL reader's
value dated D is the reading at the end of D, so daily rows are moved back a day here. Hourly readings carry
their own Pacific Standard Time stamps.
"""
import numpy as np
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import MM_PER_IN

URL = "https://cdec.water.ca.gov/dynamicapp/req/JSONDataServlet"
# CDEC sensor number -> column. Snow water content and depth are in inches, temperatures in Fahrenheit.
DAILY_SENSORS = {3: "swe_mm", 18: "depth_cm", 30: "tavg_c"}
HOURLY_SENSORS = {3: "swe_mm", 18: "depth_cm", 4: "tobs_c"}
REVISED_WATER = {82: "swe_mm"}
MISSING_BELOW = -9000
# A pillow's reading wanders by a few millimeters from day to day. Dips smaller than this are treated as that
# wander, not as snow lost and regained.
PILLOW_HYSTERESIS_MM = 5.0
# Readings outside these are sensor faults (a pillow reading far below zero, a depth spike).
VALID = {"swe_mm": (-25.0, 5000.0), "depth_cm": (-5.0, 1500.0), "tavg_c": (-50.0, 45.0), "tobs_c": (-50.0, 45.0)}


def _convert(column: str, values: pd.Series) -> pd.Series:
    if column.endswith("_mm"):
        return values * MM_PER_IN
    if column.endswith("_cm"):
        return values * MM_PER_IN / 10.0
    return (values - 32.0) / 1.8


def parse(payload: list, sensors: dict) -> pd.DataFrame:
    frames = {}
    for sensor, column in sensors.items():
        rows = {row["date"]: row["value"] for row in payload
                if row["SENSOR_NUM"] == sensor and row["value"] is not None and row["value"] > MISSING_BELOW}
        series = _convert(column, pd.Series(rows, dtype=float))
        low, high = VALID[column]
        frames[column] = series.where(series.between(low, high))
    out = pd.DataFrame(frames)
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def _fetch(station_id: str, sensors: dict, duration: str, start: str, end: str, max_age_h: float | None) -> list:
    params = {"Stations": station_id, "SensorNums": ",".join(map(str, sensors)), "dur_code": duration,
              "Start": start, "End": end}
    return get_json("cdec", URL, params, max_age_h, timeout=300)


def daily(station_id: str, start: str, end: str, max_age_h: float | None = None) -> pd.DataFrame:
    """Daily readings dated like the SNOTEL reader's: the value dated D is the reading at the end of D."""
    frame = parse(_fetch(station_id, DAILY_SENSORS, "D", start, end, max_age_h), DAILY_SENSORS)
    frame.index = frame.index - pd.Timedelta(days=1)
    # The daily mean temperature is dated by its own day, so it moves forward again.
    if "tavg_c" in frame:
        frame["tavg_c"] = frame["tavg_c"].shift(-1)
    frame.index.name = "date"
    return frame


def daily_revised_water(station_id: str, start: str, end: str, max_age_h: float | None = None) -> pd.Series:
    """The pillow's daily water (mm) after CDEC's own corrections, dated like ``daily``. It has the spikes and
    drift of the raw readings taken out, and trails them by some days."""
    frame = parse(_fetch(station_id, REVISED_WATER, "D", start, end, max_age_h), REVISED_WATER)
    frame.index = frame.index - pd.Timedelta(days=1)
    frame.index.name = "date"
    return frame["swe_mm"].dropna()


def hourly(station_id: str, start: str, end: str, max_age_h: float | None = None) -> pd.DataFrame:
    """Hourly readings, indexed by PST timestamps."""
    frame = parse(_fetch(station_id, HOURLY_SENSORS, "H", start, end, max_age_h), HOURLY_SENSORS)
    frame.index.name = "time_pst"
    return frame


def pillow_gains(swe_mm: pd.Series, hysteresis_mm: float = PILLOW_HYSTERESIS_MM) -> pd.Series:
    """Daily water gain (mm) from a snow pillow's daily readings, with the sensor's jitter taken out.

    These pillows are not quality-controlled the way SNOTEL's are, and adding up every day-to-day rise counts
    the jitter as snow (about 20 % too much over a week at these stations). So single-day spikes are removed
    with a three-day median, and the gain is the rise of a level that follows the reading up at once but comes
    down only after the reading has dropped by more than ``hysteresis_mm``. Gaps restart the level.
    """
    series = swe_mm.asfreq("D")
    smooth = series.rolling(3, center=True, min_periods=2).median().where(series.notna())
    gains = np.full(len(smooth), np.nan)
    level = np.nan
    for i, value in enumerate(smooth.to_numpy()):
        if np.isnan(value):
            level = np.nan
        elif np.isnan(level):
            level = value
        elif value > level:
            gains[i] = value - level
            level = value
        else:
            gains[i] = 0.0
            if value < level - hysteresis_mm:
                level = value + hysteresis_mm
    return pd.Series(gains, index=smooth.index, name="swe_gain_mm").dropna()
