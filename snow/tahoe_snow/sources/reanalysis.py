"""NCEP-DOE Reanalysis 2 upper-air series (1979 on, 6-hourly, 2.5 degrees) from NOAA PSL (no key).

Used only to give the long hand-measured snowfall record its upper-air predictors.
Columns follow the Open-Meteo naming so the same feature code runs on both.
"""
import re

import numpy as np
import pandas as pd

from tahoe_snow.cache import get_text

BASE = "https://psl.noaa.gov/thredds/dodsC/Datasets/ncep.reanalysis2/pressure"
LEVELS = [850, 700, 600, 500]
LEVEL_SLICE = "2:1:5"
# Grid block around the Sierra: latitudes 40.0 and 37.5 N, longitudes 240.0 and 242.5 E.
LAT_SLICE, LON_SLICE = "20:1:21", "96:1:97"
LATS, LONS = [40.0, 37.5], [-120.0, -117.5]
VARIABLES = {"air": "temperature", "rhum": "relative_humidity", "uwnd": "u", "vwnd": "v", "hgt": "geopotential_height"}
EPOCH = pd.Timestamp("1800-01-01")
MISSING_BELOW = -1e30
ROW = re.compile(r"^\[(\d+)\]\[(\d+)\]\[(\d+)\], (.+)$")


def parse_block(text: str, variable: str) -> pd.DataFrame:
    """Long table (time, level, lat, lon, value) from an OPeNDAP ASCII grid response."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{variable}.{variable}["))
    rows = []
    index = start + 1
    while index < len(lines) and (match := ROW.match(lines[index])):
        t, lev, lat = (int(g) for g in match.groups()[:3])
        for lon, value in enumerate(match.group(4).split(", ")):
            rows.append((t, lev, lat, lon, float(value)))
        index += 1
    times = next(lines[i + 1] for i, line in enumerate(lines) if line.startswith(f"{variable}.time["))
    hours = np.array([float(v) for v in times.split(", ")])
    frame = pd.DataFrame(rows, columns=["t", "level", "lat", "lon", "value"])
    frame["time"] = EPOCH + pd.to_timedelta(hours[frame["t"].to_numpy()], unit="h")
    frame["level"] = np.array(LEVELS)[frame["level"].to_numpy()]
    frame["lat"] = np.array(LATS)[frame["lat"].to_numpy()]
    frame["lon"] = np.array(LONS)[frame["lon"].to_numpy()]
    frame["value"] = frame["value"].where(frame["value"] > MISSING_BELOW)
    return frame.drop(columns="t")


def block(variable: str, year: int, last_index: int | None = None) -> pd.DataFrame:
    """One variable for one year over the Sierra block."""
    count = last_index if last_index is not None else (1463 if year % 4 == 0 else 1459)
    query = f"{variable}%5B0:1:{count}%5D%5B{LEVEL_SLICE}%5D%5B{LAT_SLICE}%5D%5B{LON_SLICE}%5D"
    text = get_text("r2", f"{BASE}/{variable}.{year}.nc.ascii?{query}", timeout=400, retries=3)
    return parse_block(text, variable)


def point_profile(blocks: dict, lat: float, lon: float) -> pd.DataFrame:
    """Bilinear interpolation of the block to a point; columns like 'temperature_700hPa'.

    ``blocks`` maps each variable in VARIABLES to its long table (any number of years).
    """
    wy = np.clip((lat - LATS[1]) / (LATS[0] - LATS[1]), 0.0, 1.0)
    wx = np.clip((lon - LONS[0]) / (LONS[1] - LONS[0]), 0.0, 1.0)
    weights = {(LATS[0], LONS[0]): wy * (1 - wx), (LATS[0], LONS[1]): wy * wx,
               (LATS[1], LONS[0]): (1 - wy) * (1 - wx), (LATS[1], LONS[1]): (1 - wy) * wx}
    fields = {}
    for variable, frame in blocks.items():
        cube = frame.pivot_table(index="time", columns=["level", "lat", "lon"], values="value")
        fields[variable] = sum(cube.xs((la, lo), axis=1, level=["lat", "lon"]) * w for (la, lo), w in weights.items())
    out = pd.DataFrame(index=fields["air"].index)
    for level in LEVELS:
        out[f"temperature_{level}hPa"] = fields["air"][level] - 273.15
        out[f"relative_humidity_{level}hPa"] = fields["rhum"][level].clip(0, 100)
        out[f"wind_speed_{level}hPa"] = np.hypot(fields["uwnd"][level], fields["vwnd"][level]) * 3.6
        out[f"geopotential_height_{level}hPa"] = fields["hgt"][level]
    out.index.name = "time"
    return out


def time_count(variable: str, year: int) -> int:
    """Number of time steps in a year file (the current year is partial)."""
    text = get_text("r2_meta", f"{BASE}/{variable}.{year}.nc.dds", max_age_h=24, timeout=120)
    return int(re.search(r"time = (\d+)", text).group(1))


def prefetch(first_year: int, last_year: int) -> None:
    """Download every variable and year into the cache."""
    for year in range(last_year, first_year - 1, -1):
        for variable in VARIABLES:
            last_index = time_count(variable, year) - 1 if year == last_year else None
            frame = block(variable, year, last_index)
            print(f"{variable} {year}: {len(frame)} rows", flush=True)


def load(first_year: int, last_year: int) -> dict:
    """All cached years per variable, concatenated."""
    out = {}
    for variable in VARIABLES:
        frames = [block(variable, year, time_count(variable, year) - 1 if year == last_year else None)
                  for year in range(first_year, last_year + 1)]
        out[variable] = pd.concat(frames, ignore_index=True)
    return out
