"""Build the 3D map's heightmap from the public Terrain Tiles on AWS (Mapzen terrarium, no key).

Writes data/terrain.bin (uint16 meters, row-major, north to south) and data/terrain.json for Tahoe, and the
same pair with a region suffix (terrain-mammoth) for the others: python tools/build_terrain.py [region].
Run once per region; the output is committed.

A region marked ``water`` also gets a water mask, data/terrain-<region>.water.bin: how much of each cell is water,
from 0 to 255, decided from the full-resolution tiles (sea floor and the sea itself read at or below 0 m there,
which the coarse grid's one sample per cell cannot tell from low shore) and from OpenStreetMap's lakes, reservoirs
and river surfaces, which stand above sea level. It is written as runs: a byte of the value (0 to 255 in sixteen
steps), then how many cells in a row have it, seven bits to a byte, low bits first, the top bit set on all but the
last byte.
"""
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parent.parent
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
# Lakes and rivers drawn as water: an outline at least this long (a lake of about 2 km2 and up; a smaller one is
# under half a cell and would not show), and every multipolygon, whose size is only known once it is put together.
LAKE_OUTLINE_M = 5000
ZOOM = 10
# Box (south, north, west, east), a ceiling just above the highest real peak inside it, and the grid's width
# (about 0.39 km a cell in both). Mammoth's box runs from Matterhorn Peak to Mt. Whitney.
REGIONS = {"tahoe": {"box": (38.33, 39.77, -120.96, -119.12), "max_m": 3400, "columns": 420},
           "mammoth": {"box": (36.22, 38.46, -120.24, -117.44), "max_m": 4450, "columns": 640},
           # Taller than the 2.24 degrees the guide advises: Sugarloaf to Mount Snow. Mount Washington is 1,917 m.
           "newengland": {"box": (42.28, 45.73, -74.015, -69.215), "max_m": 1950, "columns": 640},
           # A 355 km square around the circle holding Mt. Baker to Mt. Adams and Hurricane Ridge to Mission Ridge.
           # Mt. Rainier is 4,392 m on the tiles; Puget Sound and the Strait are sea level, clipped to 0.
           "seattle": {"box": (45.9172, 49.1053, -124.3165, -119.5965), "max_m": 4420, "columns": 640, "water": True}}


def stem(region: str) -> str:
    return "terrain" if region == "tahoe" else f"terrain-{region}"


def tile_xy(lat: float, lon: float, zoom: int) -> tuple:
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def lake_rings(box: tuple, session: requests.Session) -> list:
    """OpenStreetMap's standing and river water in the box, as polygons: [(outer rings, inner rings)], each ring
    a list of (lon, lat)."""
    south, north, west, east = box
    bbox = f"{south},{west},{north},{east}"
    query = (f'[out:json][timeout:240];(way["natural"="water"](if: length() > {LAKE_OUTLINE_M})({bbox});'
             f'way["waterway"="riverbank"](if: length() > {LAKE_OUTLINE_M})({bbox});'
             f'relation["natural"="water"]({bbox});relation["waterway"="riverbank"]({bbox}););out geom;')
    for server in OVERPASS:
        try:
            response = session.post(server, data={"data": query}, timeout=300)
            response.raise_for_status()
            elements = response.json()["elements"]
            break
        except (requests.RequestException, ValueError) as error:
            print("overpass", server, error)
    else:
        raise RuntimeError("no Overpass server answered")
    polygons = []
    for element in elements:
        if element["type"] == "way" and element.get("geometry"):
            polygons.append(([[(p["lon"], p["lat"]) for p in element["geometry"]]], []))
        elif element["type"] == "relation":
            parts = {"outer": [], "inner": []}
            for member in element.get("members", []):
                if member["type"] == "way" and member.get("geometry"):
                    parts["inner" if member.get("role") == "inner" else "outer"].append(
                        [(p["lon"], p["lat"]) for p in member["geometry"]])
            polygons.append((joined(parts["outer"]), joined(parts["inner"])))
    print(f"{len(polygons)} water polygons from OpenStreetMap")
    return polygons


def joined(pieces: list) -> list:
    """Closed rings from a multipolygon's member ways, joined end to end."""
    rings, open_ = [], [list(piece) for piece in pieces]
    while open_:
        ring = open_.pop()
        while ring[0] != ring[-1]:
            for n, piece in enumerate(open_):
                if piece[0] == ring[-1]:
                    ring += piece[1:]
                elif piece[-1] == ring[-1]:
                    ring += piece[::-1][1:]
                else:
                    continue
                open_.pop(n)
                break
            else:
                break
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def water_mask(mosaic: np.ndarray, tx0: int, ty0: int, box: tuple, rows: int, columns: int,
               session: requests.Session) -> np.ndarray:
    """How much of each grid cell is water, 0 to 255 in sixteen steps: the share of the tile pixels nearest it that are sea (at or
    below 0 m) or inside an OpenStreetMap lake, reservoir or river surface."""
    south, north, west, east = box
    height, width = mosaic.shape
    wet = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(wet)
    pixel = lambda ring: [((tile_xy(lat, lon, ZOOM)[0] - tx0) * 256, (tile_xy(lat, lon, ZOOM)[1] - ty0) * 256)
                          for lon, lat in ring]
    for outers, inners in lake_rings(box, session):
        if not outers:
            continue
        # Each lake on its own layer, so its islands are cut from it alone.
        layer = Image.new("L", (width, height), 0)
        pen = ImageDraw.Draw(layer)
        for ring in outers:
            pen.polygon(pixel(ring), fill=255)
        for ring in inners:
            pen.polygon(pixel(ring), fill=0)
        wet.paste(255, mask=layer)
    water = (np.asarray(wet) > 0) | (mosaic <= 0)
    # Each tile pixel belongs to the grid cell nearest its center.
    n = 2 ** ZOOM
    lons = (tx0 * 256 + np.arange(width) + 0.5) / (256 * n) * 360 - 180
    lats = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (ty0 * 256 + np.arange(height) + 0.5) / (256 * n)))))
    cols = np.round((lons - west) / (east - west) * (columns - 1)).astype(int)
    rws = np.round((north - lats) / (north - south) * (rows - 1)).astype(int)
    keep_c, keep_r = (cols >= 0) & (cols < columns), (rws >= 0) & (rws < rows)
    cell = rws[keep_r][:, None] * columns + cols[keep_c][None, :]
    inside = water[np.ix_(keep_r, keep_c)]
    total = np.bincount(cell.ravel(), minlength=rows * columns)
    wet_count = np.bincount(cell.ravel(), weights=inside.ravel().astype(float), minlength=rows * columns)
    # Sixteen steps from dry to wet are plenty for the shore drawn between cells, and they run together more.
    return (17 * np.round(15 * wet_count / np.maximum(total, 1))).astype(np.uint8).reshape(rows, columns)


def runs(values: np.ndarray) -> bytes:
    """The mask as runs: the value byte, then how many cells in a row have it, seven bits to a byte, low bits first,
    the top bit set on every byte but the last."""
    flat, out, start = values.ravel(), bytearray(), 0
    while start < len(flat):
        end = start + 1
        while end < len(flat) and flat[end] == flat[start]:
            end += 1
        out.append(int(flat[start]))
        count = end - start
        while count >= 0x80:
            out.append(count & 0x7F | 0x80)
            count >>= 7
        out.append(count)
        start = end
    return bytes(out)


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
    if REGIONS[region].get("water"):
        mask = water_mask(mosaic, tx0, ty0, REGIONS[region]["box"], rows, COLUMNS, session)
        (ROOT / "data" / f"{stem(region)}.water.bin").write_bytes(runs(mask))
        print(f"water: {(mask >= 128).mean():.1%} of cells")
    meta = {"rows": rows, "columns": COLUMNS, "lat_s": LAT_S, "lat_n": LAT_N, "lon_w": LON_W, "lon_e": LON_E,
            "width_km": round(width_km, 2), "height_km": round(height_km, 2), "min_m": int(grid.min()),
            "max_m": int(grid.max()), "source": "Terrain Tiles on AWS (Mapzen terrarium); see tilezen/joerd attribution"}
    if REGIONS[region].get("water"):
        meta.update(water_mask=f"{stem(region)}.water.bin", water_source="the tiles' sea level and OpenStreetMap (ODbL)")
    (ROOT / "data" / f"{stem(region)}.json").write_text(json.dumps(meta))
    print(meta)


if __name__ == "__main__":
    main(*sys.argv[1:2])
