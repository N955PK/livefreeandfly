"""Training tables for the snow model: one row per station-day with observed snow, liquid, and predictors."""
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from tahoe_snow.config import SIERRA_BBOX, STATIONS, TABLES
from tahoe_snow.snow import features
from tahoe_snow.sources import ghcn, openmeteo, reanalysis

PROFILE_START = "2021-03-25"
CELL_DEG = 0.5
LOCAL_TZ = "America/Los_Angeles"
PST_OFFSET_H = 8

MIN_LIQUID_MM = 2.5
MIN_SNOW_MM = 25.0
SLR_RANGE = (2.0, 40.0)
ALL_SNOW_WET_BULB_C = 0.5
SNOTEL_MIN_SWE_MM = 5.0


def cell_of(lat: float, lon: float) -> tuple:
    return (round(round(lat / CELL_DEG) * CELL_DEG, 3), round(round(lon / CELL_DEG) * CELL_DEG, 3))


def season_of(dates) -> np.ndarray:
    """Winter label: Oct 2022 through Sep 2023 is season 2023."""
    dates = pd.DatetimeIndex(dates)
    return np.where(dates.month >= 10, dates.year + 1, dates.year)


def winter_spans(start: str, end: str) -> list:
    """(start, end) date strings covering Oct 1 to May 31 of each winter inside [start, end]."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    spans = []
    for year in range(start.year - 1, end.year + 1):
        lo, hi = max(pd.Timestamp(year, 10, 1), start), min(pd.Timestamp(year + 1, 5, 31), end)
        if lo < hi:
            # Month-sized pieces keep each request small enough for the archive to serve.
            for piece in pd.period_range(lo, hi, freq="M"):
                a, b = max(piece.start_time.normalize(), lo), min(piece.end_time.normalize(), hi)
                spans.append((a.strftime("%Y-%m-%d"), b.strftime("%Y-%m-%d")))
    return spans


def cell_profile(cell: tuple, end: str, pause_s: float = 1.0) -> pd.DataFrame:
    """Hourly archived profile for a cell over every winter since the archive begins."""
    pieces = []
    for a, b in winter_spans(PROFILE_START, end):
        started = time.time()
        pieces.append(openmeteo.historical_profile(cell[0], cell[1], a, b, pause_s=pause_s))
        if time.time() - started > 2 * pause_s + 1:
            print(f"  {cell} {a}: {time.time() - started:.0f} s", flush=True)
    frame = pd.concat(pieces)
    return frame[~frame.index.duplicated()].sort_index()


def manual_window_end_utc(dates: pd.DatetimeIndex, obs_hour: pd.Series) -> pd.DatetimeIndex:
    """UTC end of each observation day: the observation hour, local clock time, on the report date."""
    hour = obs_hour.fillna(ghcn.DEFAULT_OBS_HOUR).clip(0, 24).astype(int).to_numpy()
    local = pd.DatetimeIndex(dates) + pd.to_timedelta(hour, unit="h")
    aware = local.tz_localize(LOCAL_TZ, ambiguous="NaT", nonexistent="shift_forward")
    return aware.tz_convert("UTC").tz_localize(None)


def station_obs_hour(daily: pd.DataFrame, station: str) -> pd.Series:
    """Observation hour per day: the record's own, else the station's usual hour.

    Airport stations (USW) report calendar days in local standard time.
    """
    recorded = daily["snow_obs_hour"].fillna(daily["prcp_obs_hour"])
    if station.startswith("USW"):
        return pd.Series(24.0, index=daily.index)
    usual = recorded.mode()
    return recorded.fillna(usual.iloc[0] if len(usual) else ghcn.DEFAULT_OBS_HOUR)


def manual_events(daily: pd.DataFrame, station: pd.Series, windows: pd.DataFrame,
                  start: str = PROFILE_START) -> pd.DataFrame:
    """Events at one hand-measured station. ``windows`` is window_features() for its profile cell."""
    daily = daily[daily.index >= start]
    if daily.empty:
        return pd.DataFrame()
    obs_hour = station_obs_hour(daily, station["station"])
    end_utc = manual_window_end_utc(daily.index, obs_hour)
    rows = windows.reindex(end_utc)
    rows.index = daily.index
    out = features.add_static(rows, daily["prcp_mm"], station["elev_m"], daily.index.day_of_year)
    out["snow_mm"] = daily["snow_mm"]
    out["trace"] = daily["snow_trace"].astype(bool) | daily["prcp_trace"].astype(bool)
    return _finish(out, station["station"], "manual", daily.index)


def snotel_events(gains: pd.DataFrame, triplet: str, windows: pd.DataFrame) -> pd.DataFrame:
    """Events at one SNOTEL station; liquid is the SWE gain, snow is the depth gain."""
    gains = gains[gains.index >= PROFILE_START]
    end_utc = gains.index + pd.Timedelta(days=1, hours=PST_OFFSET_H)
    rows = windows.reindex(end_utc)
    rows.index = gains.index
    out = features.add_static(rows, gains["swe_gain_mm"], STATIONS[triplet].elev_m, gains.index.day_of_year)
    out["snow_mm"] = gains["depth_gain_cm"] * 10.0
    out["prec_gain_mm"] = gains["prec_gain_mm"]
    out["trace"] = False
    return _finish(out, triplet, "snotel", gains.index)


def _finish(out: pd.DataFrame, station: str, source: str, dates) -> pd.DataFrame:
    out = out.copy()
    out.insert(0, "station", station)
    out.insert(1, "source", source)
    out.insert(2, "date", pd.DatetimeIndex(dates))
    out["season"] = season_of(dates)
    out["slr"] = out["snow_mm"] / out["liquid_mm"].where(out["liquid_mm"] > 0)
    return out.reset_index(drop=True)


def ratio_filter(events: pd.DataFrame, min_liquid_mm: float = MIN_LIQUID_MM) -> pd.DataFrame:
    """All-snow, measurable events with complete predictors: the rows a ratio model may learn from."""
    keep = (
        (events["liquid_mm"] >= min_liquid_mm)
        & (events["snow_mm"] >= MIN_SNOW_MM)
        & events["slr"].between(*SLR_RANGE)
        & (events["tw0_max"] <= ALL_SNOW_WET_BULB_C)
        & ~events["trace"]
        & (events["hours_valid"] >= 24)
        & events[features.FEATURES].notna().all(axis=1)
    )
    return events[keep].reset_index(drop=True)


def build(end: str, cells: list | None = None) -> pd.DataFrame:
    """Assemble the event table from the cached observation tables, for all cells or only ``cells``."""
    stations = pd.read_parquet(TABLES / "manual_stations.parquet")
    manual = pd.read_parquet(TABLES / "manual_daily.parquet").set_index("date")
    snotel = pd.read_parquet(TABLES / "snotel_daily.parquet").set_index("date")
    stations = stations[stations["last_year"] >= int(PROFILE_START[:4])]
    jobs = [(row["station"], "manual", row["lat"], row["lon"], row["elev_m"], row) for _, row in stations.iterrows()]
    jobs += [(s.triplet, "snotel", s.lat, s.lon, s.elev_m, None) for s in STATIONS.values()]
    profiles, frames = {}, []
    for name, source, lat, lon, elev_m, row in jobs:
        cell = cell_of(lat, lon)
        if cells is not None and cell not in cells:
            continue
        if cell not in profiles:
            profiles[cell] = cell_profile(cell, end)
            print(f"profile {cell}: {len(profiles[cell])} hours", flush=True)
        windows = features.window_features(features.hourly_features(profiles[cell], elev_m))
        if source == "manual":
            events = manual_events(manual[manual["station"] == name], row, windows)
        else:
            events = snotel_events(snotel[snotel["station"] == name], name, windows)
        if not events.empty:
            events["cell_lat"], events["cell_lon"] = cell
            frames.append(events)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(TABLES / "events.parquet")
    return table


def profile_cells() -> list:
    """Cells needed for training, Tahoe SNOTEL cells first, then by number of hand-measured stations."""
    stations = pd.read_parquet(TABLES / "manual_stations.parquet") if (TABLES / "manual_stations.parquet").exists() \
        else ghcn.find_stations(SIERRA_BBOX, 1500.0, 2000)
    stations = stations[stations["last_year"] >= int(PROFILE_START[:4])]
    first = list(dict.fromkeys(cell_of(s.lat, s.lon) for s in STATIONS.values()))
    counts = pd.Series([cell_of(r.lat, r.lon) for r in stations.itertuples()]).value_counts()
    return first + [cell for cell in counts.index if cell not in first]


def prefetch(end: str, workers: int = 1) -> None:
    """Download every training profile into the cache."""
    def one(cell):
        for attempt in range(6):
            try:
                frame = cell_profile(cell, end)
                print(f"done {cell}: {len(frame)} hours", flush=True)
                return
            except RuntimeError as error:
                print(f"retry {cell} ({attempt}): {str(error)[:80]}", flush=True)
                time.sleep(120)
        print(f"FAILED {cell}", flush=True)
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, profile_cells()))


LONG_START = "1979-01-02"


def build_long(last_year: int) -> pd.DataFrame:
    """Hand-measured events since 1979 with predictors from the coarse long-record reanalysis.

    The reanalysis is 6-hourly on four levels with no precipitation field, so predictors are
    plain 24-hour means of the time-interpolated series.
    """
    stations = pd.read_parquet(TABLES / "manual_stations.parquet")
    manual = pd.read_parquet(TABLES / "manual_daily.parquet").set_index("date")
    blocks = reanalysis.load(1979, last_year)
    frames = []
    for _, row in stations.iterrows():
        profile = reanalysis.point_profile(blocks, row["lat"], row["lon"]).resample("h").interpolate()
        windows = features.window_features(features.hourly_features(profile, row["elev_m"]))
        events = manual_events(manual[manual["station"] == row["station"]], row, windows, start=LONG_START)
        if not events.empty:
            frames.append(events)
    table = pd.concat(frames, ignore_index=True)
    table.to_parquet(TABLES / "events_long.parquet")
    return table
