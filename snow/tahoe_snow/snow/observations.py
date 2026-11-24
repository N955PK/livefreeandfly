"""Bulk station tables used to train and test the snow model."""
import pandas as pd

from tahoe_snow.cache import get_json
from tahoe_snow.config import (COLORADO_BBOX, COLORADO_STATIONS, M_PER_FT, MAMMOTH_STATIONS, SEATTLE_BBOX,
                               SEATTLE_STATIONS, SIERRA_BBOX, STATIONS,
                               TABLES, TETONS_BBOX, TETONS_STATIONS, WASATCH_BBOX, WASATCH_STATIONS, Station)
from tahoe_snow.sources import cdec, ghcn, snotel

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


def pull_region(stations: dict, table: str, end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at a region's snow sensors: pillow water at the CDEC sites, the usual set at SNOTEL."""
    frames = []
    for station in stations.values():
        if station.source == "cdec":
            raw = cdec.daily(station.triplet.split(":")[0], start, end)
            gains = cdec.pillow_gains(raw["swe_mm"]).rename_axis("date").reset_index()
        else:
            gains = snotel.daily_gains(snotel.daily(station.triplet, start, end)).reset_index()
        gains.insert(0, "station", station.triplet)
        frames.append(gains)
        print(f"{station.triplet} {station.name}: {len(gains)} days", flush=True)
    out = pd.concat(frames, ignore_index=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    out.to_parquet(TABLES / f"{table}.parquet")
    return out


def pull_mammoth(end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at the snow sensors around Mammoth."""
    return pull_region(MAMMOTH_STATIONS, "mammoth_daily", end, start)


def pull_seattle(end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at the SNOTEL stations paired with the Seattle region's mountains."""
    return pull_region(SEATTLE_STATIONS, "seattle_daily", end, start)


def pull_tetons(end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at the SNOTEL stations the Tetons' water correction is fitted to."""
    return pull_region(TETONS_STATIONS, "tetons_daily", end, start)


def pull_wasatch(end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at the SNOTEL stations the Wasatch's water correction is fitted to."""
    return pull_region(WASATCH_STATIONS, "wasatch_daily", end, start)


def pull_colorado(end: str, start: str = "2020-10-01") -> pd.DataFrame:
    """Daily gains at the SNOTEL stations Colorado's water correction is fitted to."""
    return pull_region(COLORADO_STATIONS, "colorado_daily", end, start)


def box_stations(states, bbox: tuple) -> dict:
    """Every active SNOTEL station of ``states`` (one, or several) inside ``bbox`` (lat0, lat1, lon0, lon1), from
    the NRCS list."""
    lat0, lat1, lon0, lon1 = bbox
    found = {}
    for state in [states] if isinstance(states, str) else states:
        listed = get_json("snotel_meta", snotel.STATIONS_URL, {"stationTriplets": f"*:{state}:SNTL", "activeOnly": "true"})
        found.update({row["stationTriplet"]: Station(row["stationTriplet"], row["name"], row["latitude"],
                                                     row["longitude"], round(row["elevation"] * M_PER_FT, 1))
                      for row in listed if lat0 < row["latitude"] < lat1 and lon0 < row["longitude"] < lon1})
    return found


# The boxes a region's rain/snow split and snow ratio are fitted or checked in: the states its SNOTEL stations are
# listed under, the box, and the lowest hand-measured station taken.
BOXES = {"cascades": ("WA", SEATTLE_BBOX, 600.0), "tetonbox": (("WY", "ID"), TETONS_BBOX, 1500.0),
         "wasatchbox": ("UT", WASATCH_BBOX, 1500.0), "coloradobox": ("CO", COLORADO_BBOX, 2000.0)}


def pull_box(name: str, end: str, start: str = "2023-10-01") -> pd.DataFrame:
    """Daily gains at every SNOTEL station in a box, for the winters the upper-air archive covers: what the
    region's rain/snow split is fitted to."""
    states, bbox, _ = BOXES[name]
    stations = box_stations(states, bbox)
    pd.DataFrame([{"station": s.triplet, "name": s.name, "lat": s.lat, "lon": s.lon, "elev_m": s.elev_m}
                  for s in stations.values()]).to_parquet(TABLES / f"{name}_stations.parquet")
    return pull_region(stations, f"{name}_daily", end, start)


def pull_box_manual(name: str, end: str, start: str = "2023-11-01") -> tuple:
    """Hand-measured daily snowfall and liquid in a box, for the winters the upper-air archive covers."""
    _, bbox, min_elev_m = BOXES[name]
    stations = ghcn.find_stations(bbox, min_elev_m, last_year_at_least=int(start[:4]))
    frames = []
    for row in stations.itertuples():
        frame = ghcn.daily(row.station, start, end)
        if frame.empty or "snow_mm" not in frame or "prcp_mm" not in frame:
            continue
        frame = frame.reset_index()
        frame.insert(0, "station", row.station)
        frames.append(frame)
    table = pd.concat(frames, ignore_index=True)
    stations.to_parquet(TABLES / f"{name}_manual_stations.parquet")
    table.to_parquet(TABLES / f"{name}_manual_daily.parquet")
    return stations, table


def pull_cascades(end: str, start: str = "2023-10-01") -> pd.DataFrame:
    """Daily gains at every SNOTEL station in the Seattle box."""
    return pull_box("cascades", end, start)


def pull_cascades_manual(end: str, start: str = "2023-11-01") -> tuple:
    """Hand-measured daily snowfall and liquid in the Seattle box."""
    return pull_box_manual("cascades", end, start)


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
