"""Snow-pillow readings from Alberta River Basins (no key).

Each pillow has a file of its last five days of snow water, in millimeters, every 15 or 60 minutes. The stamps
carry no zone: they are read as Mountain Standard Time (UTC-7), the clock the file's own creation time agreed
with when this was written (2026-11-24), and the caller moves them to UTC as it does a SNOTEL station's. There is
no depth and no temperature, and no longer record is published. Frames carry the SNOTEL reader's column names.
"""
import pandas as pd

from tahoe_snow.cache import get_json

URL = "https://rivers.alberta.ca/apps/Basins/data/figures/river/abrivers/stationdata/M_SW_{station}_table.json"
# Readings outside these are sensor faults.
VALID = (-25.0, 5000.0)


def parse(payload: list) -> pd.DataFrame:
    table = payload[0]
    if table.get("ts_unitsymbols") != ["mm"]:
        raise ValueError(f"snow water is not in millimeters: {table.get('ts_unitsymbols')}")
    rows = {stamp: value for stamp, value in table["data"] if value is not None}
    series = pd.Series(rows, dtype=float)
    series.index = pd.to_datetime(series.index)
    out = pd.DataFrame({"swe_mm": series.where(series.between(*VALID))}).dropna().sort_index()
    out.index.name = "time_mst"
    return out


def hourly(station_id: str, start: str | None = None, end: str | None = None,
           max_age_h: float | None = None) -> pd.DataFrame:
    """The last five days' readings, indexed by MST timestamps. The dates are taken for the other readers' sake."""
    return parse(get_json("abrivers", URL.format(station=station_id), None, max_age_h))
