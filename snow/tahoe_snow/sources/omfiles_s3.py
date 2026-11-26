"""Archived GFS fields read straight from Open-Meteo's public S3 bucket (no key).

Pressure-level fields (0.25 degrees, hourly) are kept there from late 2023 on; reading a
small block costs a fraction of a second per file, against minutes through the API.
Columns follow the Open-Meteo API naming, with wind speed in km/h.
"""
from concurrent.futures import ThreadPoolExecutor

import math
import fsspec
import numpy as np
import omfiles
import pandas as pd

from tahoe_snow.config import PRESSURE_LEVELS, RAW

BUCKET = "openmeteo/data"
CHUNK_HOURS = 481
FIRST_PRESSURE_CHUNK = 982
# Sierra block on the 0.25-degree grid.
LAT0, LAT1, LON0, LON1 = 36.25, 40.25, -121.5, -118.0
SIERRA_BLOCK = (LAT0, LAT1, LON0, LON1)
# The Washington Cascades and Olympics, around the Seattle region's sensors.
CASCADES_BLOCK = (46.0, 49.0, -123.75, -120.25)
# The Tetons and the ranges around them.
TETONS_BLOCK = (43.0, 44.5, -111.75, -109.75)
# The Wasatch, Mt. Timpanogos to the Bear River Range's south end.
WASATCH_BLOCK = (40.0, 41.75, -112.25, -111.25)
# Colorado's I-70 corridor and the Park Range by Steamboat.
COLORADO_BLOCK = (39.25, 40.75, -107.0, -105.5)
# Canada's western regions, each around its stations' box.
OKANAGAN_BLOCK = (49.25, 51.0, -120.5, -118.5)
BCCOAST_BLOCK = (49.25, 51.0, -126.0, -122.0)
POWDERHIGHWAY_BLOCK = (49.0, 51.75, -118.5, -116.5)
EASTKOOTENAYS_BLOCK = (49.0, 51.5, -117.5, -114.75)
ROCKIES_BLOCK = (50.75, 53.0, -118.75, -115.0)
# The third collector's regions, each around its stations' box.
MONTANA_BLOCK = (44.75, 47.25, -111.75, -109.5)
SUNVALLEY_BLOCK = (43.25, 44.5, -115.5, -113.75)
OREGON_BLOCK = (43.25, 46.0, -122.5, -121.25)
NEWMEXICO_BLOCK = (35.5, 37.0, -106.75, -105.0)
ALASKA_BLOCK = (60.25, 62.0, -150.0, -148.75)
SWCOLORADO_BLOCK = (37.0, 39.5, -108.25, -106.0)


def block_around(bbox: tuple) -> tuple:
    """The block of the 0.25-degree grid that holds a box (south, north, west, east), its edges moved outward."""
    south, north, west, east = bbox
    return (math.floor(south * 4) / 4, math.ceil(north * 4) / 4, math.floor(west * 4) / 4, math.ceil(east * 4) / 4)


LEVEL_VARIABLES = ["temperature", "relative_humidity", "wind_u_component", "wind_v_component", "geopotential_height"]
PRECIP_SHAPE = (1536, 3072)
GRID_WIDTH = {"ncep_gfs025": 1440, "ncep_gfs013": 3072}


def chunk_times(chunk: int) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(0) + pd.Timedelta(hours=chunk * CHUNK_HOURS), periods=CHUNK_HOURS, freq="h")


def chunk_of(when) -> int:
    return int(pd.Timestamp(when).value // 3_600_000_000_000 // CHUNK_HOURS)


def grid_025(block: tuple = SIERRA_BLOCK) -> tuple:
    lat0, lat1, lon0, lon1 = block
    lats = np.arange(lat0, lat1 + 1e-9, 0.25)
    lons = np.arange(lon0, lon1 + 1e-9, 0.25)
    iy = slice(int(round((lat0 + 90) / 0.25)), int(round((lat1 + 90) / 0.25)) + 1)
    ix = slice(int(round((lon0 + 180) / 0.25)), int(round((lon1 + 180) / 0.25)) + 1)
    return lats, lons, iy, ix


def precip_indices(lats: np.ndarray, lons: np.ndarray) -> tuple:
    """Nearest points of the 0.117-degree surface grid for each 0.25-degree node."""
    ny, nx = PRECIP_SHAPE
    iy = np.round((lats + 90) / 180 * (ny - 1)).astype(int)
    ix = np.round((lons + 180) / 360 * nx).astype(int)
    return iy, ix


def read_block(model: str, variable: str, chunk: int, iy: slice, ix: slice) -> np.ndarray:
    """A (lat, lon, time) block for one chunk file, cached on disk. Missing files give NaN."""
    path = RAW / "om_s3" / f"{model}_{variable}_{chunk}_{iy.start}-{iy.stop}_{ix.start}-{ix.stop}.npy"
    if path.exists():
        return np.load(path)
    fs = fsspec.filesystem("s3", anon=True)
    try:
        reader = omfiles.OmFileReader.from_fsspec(fs, f"{BUCKET}/{model}/{variable}/chunk_{chunk}.om")
        if len(reader.shape) == 3:
            block = np.asarray(reader[iy, ix, :], dtype=np.float32)
        else:
            # Older files are flattened to (lat * lon, time).
            nx = GRID_WIDTH[model]
            block = np.stack([np.asarray(reader[row * nx + ix.start:row * nx + ix.stop, :], dtype=np.float32)
                              for row in range(iy.start, iy.stop)])
    except FileNotFoundError:
        block = np.full((iy.stop - iy.start, ix.stop - ix.start, CHUNK_HOURS), np.nan, dtype=np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, block)
    return block


def sierra_profiles(start: str, end: str, workers: int = 16) -> dict:
    """Hourly profile frames keyed by (lat, lon) for every 0.25-degree node in the Sierra block."""
    return block_profiles(start, end, SIERRA_BLOCK, PRESSURE_LEVELS, workers)


def block_profiles(start: str, end: str, block: tuple, levels: list, workers: int = 16) -> dict:
    """Hourly profile frames keyed by (lat, lon) for every 0.25-degree node in ``block``, on ``levels``."""
    lats, lons, iy, ix = grid_025(block)
    chunks = list(range(max(chunk_of(start), FIRST_PRESSURE_CHUNK), chunk_of(end) + 1))
    piy, pix = precip_indices(lats, lons)
    precip_slice = (slice(int(piy.min()), int(piy.max()) + 1), slice(int(pix.min()), int(pix.max()) + 1))
    jobs = [("ncep_gfs025", f"{name}_{level}hPa", chunk, iy, ix)
            for chunk in chunks for name in LEVEL_VARIABLES for level in levels]
    jobs += [("ncep_gfs013", "precipitation", chunk, *precip_slice) for chunk in chunks]
    with ThreadPoolExecutor(workers) as pool:
        blocks = dict(zip([(j[1], j[2]) for j in jobs], pool.map(lambda j: read_block(*j), jobs)))
    times = pd.DatetimeIndex(np.concatenate([chunk_times(c) for c in chunks]))

    def series(variable):
        return np.concatenate([blocks[(variable, chunk)] for chunk in chunks], axis=2)

    fields = {}
    for level in levels:
        fields[f"temperature_{level}hPa"] = series(f"temperature_{level}hPa")
        fields[f"relative_humidity_{level}hPa"] = series(f"relative_humidity_{level}hPa")
        fields[f"geopotential_height_{level}hPa"] = series(f"geopotential_height_{level}hPa")
        fields[f"wind_speed_{level}hPa"] = 3.6 * np.hypot(series(f"wind_u_component_{level}hPa"),
                                                          series(f"wind_v_component_{level}hPa"))
    precip = series("precipitation")
    out = {}
    keep = (times >= pd.Timestamp(start)) & (times <= pd.Timestamp(end) + pd.Timedelta(hours=23))
    for a, lat in enumerate(lats):
        for b, lon in enumerate(lons):
            frame = pd.DataFrame({name: values[a, b] for name, values in fields.items()}, index=times)
            frame["precipitation"] = precip[piy[a] - precip_slice[0].start, pix[b] - precip_slice[1].start]
            frame.index.name = "time"
            out[(round(float(lat), 3), round(float(lon), 3))] = frame[keep].astype(float)
    return out
