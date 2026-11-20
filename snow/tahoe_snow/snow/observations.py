"""Bulk station tables used to train and test the snow model."""
import pandas as pd

from tahoe_snow.config import SIERRA_BBOX, STATIONS, TABLES
from tahoe_snow.sources import ghcn, snotel

MANUAL_START = "1979-01-01"
SNOTEL_START = "1998-10-01"
MIN_ELEV_M = 1500.0


def pull_manual(end: str) -> tuple:
    """Hand-measured daily snowfall and liquid for Sierra stations at or above 1,500 m."""
    stations = ghcn.find_stations(SIERRA_BBOX, MIN_ELEV_M, last_year_at_least=2000)
    frames = []
    for row in stations.itertuples():
        start = max(MANUAL_START, f"{row.first_year}-01-01")
        frame = ghcn.daily(row.station, start, end)
        if frame.empty or "snow_mm" not in frame or "prcp_mm" not in frame:
            continue
        frame = frame.reset_index()
        frame.insert(0, "station", row.station)
        frames.append(frame)
        print(f"{row.station} {row.name}: {len(frame)} days", flush=True)
    table = pd.concat(frames, ignore_index=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    stations.to_parquet(TABLES / "manual_stations.parquet")
    table.to_parquet(TABLES / "manual_daily.parquet")
    return stations, table


def pull_snotel(end: str) -> pd.DataFrame:
    """Daily gains at the Tahoe SNOTEL stations."""
    frames = []
    for station in STATIONS.values():
        raw = snotel.daily(station.triplet, SNOTEL_START, end)
        gains = snotel.daily_gains(raw).reset_index()
        gains.insert(0, "station", station.triplet)
        frames.append(gains)
        print(f"{station.triplet} {station.name}: {len(gains)} days", flush=True)
    table = pd.concat(frames, ignore_index=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    table.to_parquet(TABLES / "snotel_daily.parquet")
    return table
