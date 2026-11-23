"""Build the 3D map's heightmap from the public Terrain Tiles on AWS (Mapzen terrarium, no key).

Writes data/terrain.bin (uint16 meters, row-major, north to south) and data/terrain.json for Tahoe, and the
same pair with a region suffix (terrain-mammoth) for the others: python tools/build_terrain.py [region].
Run once per region; the output is committed.
"""
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parent.parent
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 10
# Box (south, north, west, east), a ceiling just above the highest real peak inside it, and the grid's width
# (about 0.39 km a cell in both). Mammoth's box runs from Matterhorn Peak to Mt. Whitney.
REGIONS = {"tahoe": {"box": (38.33, 39.77, -120.96, -119.12), "max_m": 3400, "columns": 420},
           "mammoth": {"box": (36.22, 38.46, -120.24, -117.44), "max_m": 4450, "columns": 640},
           # Taller than the 2.24 degrees the guide advises: Sugarloaf to Mount Snow. Mount Washington is 1,917 m.
           "newengland": {"box": (42.28, 45.73, -74.015, -69.215), "max_m": 1950, "columns": 640},
           # A 355 km square around the circle holding Mt. Baker to Mt. Adams and Hurricane Ridge to Mission Ridge.
           # Mt. Rainier is 4,392 m on the tiles; Puget Sound and the Strait are sea level, clipped to 0.
           "seattle": {"box": (45.9172, 49.1053, -124.3165, -119.5965), "max_m": 4420, "columns": 640}}


def stem(region: str) -> str:
    return "terrain" if region == "tahoe" else f"terrain-{region}"


def tile_xy(lat: float, lon: float, zoom: int) -> tuple:
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def main(region: str = "tahoe") -> None:
    LAT_S, LAT_N, LON_W, LON_E = REGIONS[region]["box"]
    MAX_REAL_M, COLUMNS = REGIONS[region]["max_m"], REGIONS[region]["columns"]
    x0, y0 = tile_xy(LAT_N, LON_W, ZOOM)
    x1, y1 = tile_xy(LAT_S, LON_E, ZOOM)
    tx0, ty0, tx1, ty1 = int(x0), int(y0), int(x1), int(y1)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), dtype=np.float32)
    session = requests.Session()
    session.headers["User-Agent"] = "terrain-builder/0.1"
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            response = session.get(TILES.format(z=ZOOM, x=tx, y=ty), timeout=60)
            response.raise_for_status()
            rgb = np.asarray(Image.open(io.BytesIO(response.content)).convert("RGB"), dtype=np.float32)
            meters = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = meters
    # Sample on a regular latitude/longitude grid (tiles are Web Mercator).
    width_km = (LON_E - LON_W) * 111.32 * math.cos(math.radians((LAT_S + LAT_N) / 2))
    height_km = (LAT_N - LAT_S) * 110.57
    rows = int(round(COLUMNS * height_km / width_km))
    lats = np.linspace(LAT_N, LAT_S, rows)
    lons = np.linspace(LON_W, LON_E, COLUMNS)
    px = np.array([(tile_xy(LAT_N, lon, ZOOM)[0] - tx0) * 256 for lon in lons])
    py = np.array([(tile_xy(lat, LON_W, ZOOM)[1] - ty0) * 256 for lat in lats])
    ix = np.clip(np.round(px).astype(int), 0, mosaic.shape[1] - 1)
    iy = np.clip(np.round(py).astype(int), 0, mosaic.shape[0] - 1)
    sampled = mosaic[np.ix_(iy, ix)]
    # Replace the few bad pixels in the source (spikes above the highest peak here) with their neighborhood median.
    spikes = sampled > MAX_REAL_M
    sampled[spikes] = median_filter(sampled, size=5)[spikes]
    grid = np.clip(sampled, 0, MAX_REAL_M).astype("<u2")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / f"{stem(region)}.bin").write_bytes(grid.tobytes())
    meta = {"rows": rows, "columns": COLUMNS, "lat_s": LAT_S, "lat_n": LAT_N, "lon_w": LON_W, "lon_e": LON_E,
            "width_km": round(width_km, 2), "height_km": round(height_km, 2), "min_m": int(grid.min()),
            "max_m": int(grid.max()), "source": "Terrain Tiles on AWS (Mapzen terrarium); see tilezen/joerd attribution"}
    (ROOT / "data" / f"{stem(region)}.json").write_text(json.dumps(meta))
    print(meta)


if __name__ == "__main__":
    main(*sys.argv[1:2])
