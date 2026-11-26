"""Build the 3D map's heightmap from the public Terrain Tiles on AWS (Mapzen terrarium, no key).

Writes data/terrain.bin (uint16 meters, row-major, north to south) and data/terrain.json for Tahoe, and the
same pair with a region suffix (terrain-mammoth) for the others: python tools/build_terrain.py [region].
Run once per region; the output is committed. python tools/build_terrain.py seattle --locator-water prints the
outline of the region's sea for the Avalanche tab's small map, from the water mask already built (see sea_outline).

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
from scipy.ndimage import binary_dilation, binary_fill_holes, label, median_filter

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
           "seattle": {"box": (45.9172, 49.1053, -124.3165, -119.5965), "max_m": 4420, "columns": 640, "water": True},
           # A 130 km square around the circle, 64 km in radius about 43.63 N 110.51 W, that holds Grand Targhee,
           # Teton Pass and Togwotee Pass (each 39 km from its middle) with 25 km to spare. The Grand Teton is
           # 4,199 m. Jackson Lake sits above the valley floor south of it, so its water comes from a mask.
           "tetons": {"box": (43.046, 44.214, -111.317, -109.703), "max_m": 4250, "columns": 334, "water": True},
           # A 162 km square around the circle, 81 km in radius about 40.885 N 111.69 W, that holds Powder Mountain
           # in the north and Sundance and Mt. Timpanogos in the south (each about 56 km from its middle) with
           # 25 km to spare. The highest ground is the western Uintas, Hayden Peak at 3,790 m. Utah Lake and the
           # canyon reservoirs sit above the Great Salt Lake, so the water comes from a mask.
           "wasatch": {"box": (40.157, 41.613, -112.652, -110.728), "max_m": 3850, "columns": 415, "water": True},
           # A 176 km square around the circle, 88 km in radius about 39.968 N 106.436 W, that holds Steamboat in
           # the north-west and Breckenridge in the south-east (each about 63 km from its middle) with 25 km to
           # spare. The highest ground is Grays Peak at 4,352 m and Longs Peak at 4,346 m. Its reservoirs (Dillon,
           # Granby, Green Mountain) are drawn as level ground for now: a water mask needs OpenStreetMap's outlines,
           # and the Overpass servers were down the day it was built (2026-11-24). Add "water": True and rebuild.
           "colorado": {"box": (39.172, 40.764, -107.466, -105.406), "max_m": 4400, "columns": 451},
           # A 254 km square around the circle, 127 km in radius about 41.285 N 122.115 W, that holds Mt. Ashland in
           # the north and Lassen Peak in the south-east (each about 102 km from its middle) with 25 km to spare.
           # Mt. Shasta is 4,322 m. Lake Shasta and the Sacramento Valley are far below the mountains; no water mask
           # was built, as the Overpass servers were down the day it was made (2026-11-24). Add "water": True and
           # rebuild.
           "shasta": {"box": (40.137, 42.433, -123.634, -120.596), "max_m": 4350, "columns": 640},
           # Canada. A 218 km square around the circle, 109 km in radius about 50.138 N 119.904 W, that holds Sun
           # Peaks in the north and Apex in the south (each 84 km from its middle) with 25 km to spare. The
           # Monashees at the box's east edge reach about 2,900 m. Okanagan Lake lies along the valley floor, the
           # lowest ground there is, so it is drawn as level ground and no mask is built.
           "okanagan": {"box": (49.153, 51.123, -121.431, -118.377), "max_m": 3100, "columns": 559},
           # A 264 km square around the circle, 132 km in radius about 50.06 N 123.88 W, that holds Mt. Washington
           # on Vancouver Island and the Duffey (each 107 km from its middle) with 25 km to spare. Wedge Mountain is
           # 2,892 m. The Strait of Georgia and Howe Sound are sea level, clipped to 0 and drawn as level ground.
           "bccoast": {"box": (48.866, 51.254, -125.729, -122.031), "max_m": 3000, "columns": 640},
           # A 380 km square around the circle, 190 km in radius about 46.54 N 72.47 W, that holds Tremblant in the
           # west and Le Massif in the east (each 165 km from its middle) with 25 km to spare: New England's size.
           # Nothing in it passes 1,200 m. The St. Lawrence is tidal below Québec and near sea level above it.
           "quebec": {"box": (44.822, 48.258, -74.95, -69.99), "max_m": 1350, "columns": 640},
           # A 302 km square around the circle, 151 km in radius about 50.181 N 117.321 W, that holds Rogers Pass in
           # the north and Kootenay Pass in the south (each about 126 km from its middle) with 25 km to spare. Mt.
           # Dawson is 3,377 m.
           "powderhighway": {"box": (48.815, 51.547, -119.439, -115.203), "max_m": 3500, "columns": 640},
           # A 298 km square around the circle, 149 km in radius about 50.369 N 116.078 W, that holds Kicking Horse
           # in the north and Fernie in the south (each about 124 km from its middle) with 25 km to spare. Mt.
           # Assiniboine is 3,618 m.
           "eastkootenays": {"box": (49.021, 51.717, -118.177, -113.979), "max_m": 3700, "columns": 640},
           # A 340 km square around the circle, 170 km in radius about 51.874 N 116.632 W, that holds Marmot Basin
           # in the north-west and Nakiska in the south-east (each about 145 km from its middle) with 25 km to
           # spare. Mt. Columbia is 3,747 m.
           "rockies": {"box": (50.345, 53.403, -119.105, -114.159), "max_m": 4000, "columns": 640},
           # The third collector's regions. Each is a square around the circle that holds every mountain with
           # 25 km to spare. Montana: 259 km, 104 km in radius about 45.931 N 110.462 W, Showdown in the north to
           # Lulu Pass in the south-east; Granite Peak in the Beartooths is 3,904 m.
           "montana": {"box": (44.768, 47.094, -112.134, -108.79), "max_m": 3950, "columns": 640},
           # Sun Valley: 152 km, 51 km in radius about 43.938 N 114.875 W, Banner Summit to Soldier Mountain.
           # Castle Peak in the White Clouds is 3,601 m and Hyndman Peak 3,660 m.
           "sunvalley": {"box": (43.258, 44.619, -115.821, -113.93), "max_m": 3750, "columns": 389},
           # Oregon: 255 km, 102 km in radius about 44.512 N 121.816 W, Mt. Hood to Willamette Pass. Mt. Hood is
           # 3,429 m. The Columbia and the Willamette Valley are the lowest ground and are drawn as level ground.
           "oregon": {"box": (43.368, 45.656, -123.42, -120.212), "max_m": 3480, "columns": 640},
           # New Mexico: 177 km, 63 km in radius about 36.294 N 105.904 W, Red River to Ski Santa Fe and Pajarito.
           # Wheeler Peak is 4,013 m; Culebra Peak, just inside Colorado at the box's north edge, is 4,282 m.
           "newmexico": {"box": (35.5, 37.088, -106.889, -104.919), "max_m": 4320, "columns": 453},
           # Alaska: 172 km, 61 km in radius about 61.231 N 149.345 W, Hatcher Pass to Summit Lake. Mt. Marcus Baker
           # at the box's east edge is 4,016 m. Cook Inlet and its arms are sea level, clipped to 0 and drawn as
           # level ground.
           "alaska": {"box": (60.458, 62.004, -150.951, -147.739), "max_m": 4050, "columns": 441},
           # Southwest Colorado: 250 km, 100 km in radius about 38.316 N 107.123 W, Aspen to Wolf Creek. Mt. Elbert
           # is 4,401 m and Uncompahgre Peak 4,365 m. Blue Mesa and the other reservoirs are drawn as level ground.
           "swcolorado": {"box": (37.193, 39.44, -108.555, -105.691), "max_m": 4420, "columns": 640},
           # The fourth collector's regions.
           # Western Idaho: a 267 km square around the circle, 134 km in radius about 44.392 N 117.129 W, that holds
           # every mountain (109 km from its middle at the furthest) with 25 km to spare.
           "westidaho": {"box": (43.192, 45.592, -118.809, -115.45), "max_m": 3050, "columns": 640},
           # Wyoming: a 517 km square around the circle, 258 km in radius about 42.859 N 108.159 W, that holds
           # every mountain (233 km from its middle at the furthest) with 25 km to spare.
           "wyoming": {"box": (40.538, 45.181, -111.325, -104.992), "max_m": 4250, "columns": 640},
           # Southern Utah: a 136 km square around the circle, 68 km in radius about 38.027 N 112.612 W, that holds
           # every mountain (43 km from its middle at the furthest) with 25 km to spare.
           "southutah": {"box": (37.419, 38.636, -113.384, -111.839), "max_m": 3760, "columns": 347},
           # Arizona: a 298 km square around the circle, 149 km in radius about 34.653 N 110.630 W, that holds
           # every mountain (124 km from its middle at the furthest) with 25 km to spare.
           "arizona": {"box": (33.313, 35.993, -112.259, -109.001), "max_m": 3900, "columns": 640},
           # Las Vegas: a 90 km square around the circle, 45 km in radius about 36.300 N 115.682 W, that holds
           # every mountain (0 km from its middle at the furthest) with 25 km to spare.
           "lasvegas": {"box": (35.896, 36.704, -116.184, -115.18), "max_m": 3680, "columns": 231},
           # Southern California: a 128 km square around the circle, 64 km in radius about 34.296 N 117.277 W, that holds
           # every mountain (39 km from its middle at the furthest) with 25 km to spare.
           "socal": {"box": (33.721, 34.871, -117.973, -116.58), "max_m": 3550, "columns": 328},
           # Juneau: a 90 km square around the circle, 45 km in radius about 58.266 N 134.511 W, that holds
           # every mountain (1 km from its middle at the furthest) with 25 km to spare.
           "juneau": {"box": (57.861, 58.67, -135.279, -133.742), "max_m": 2700, "columns": 231},
           # Valdez: a 90 km square around the circle, 45 km in radius about 61.160 N 145.726 W, that holds
           # every mountain (3 km from its middle at the furthest) with 25 km to spare.
           "valdez": {"box": (60.756, 61.564, -146.564, -144.888), "max_m": 3600, "columns": 231},
           # Inland Northwest: a 218 km square around the circle, 109 km in radius about 47.873 N 116.632 W, that holds
           # every mountain (84 km from its middle at the furthest) with 25 km to spare.
           "inlandnw": {"box": (46.894, 48.852, -118.091, -115.173), "max_m": 2750, "columns": 559},
           # Northwest Montana: a 364 km square around the circle, 182 km in radius about 47.096 N 114.153 W, that holds
           # every mountain (157 km from its middle at the furthest) with 25 km to spare.
           "nwmontana": {"box": (45.461, 48.73, -116.553, -111.753), "max_m": 3350, "columns": 640}}


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


# The sea for the small zone map: the salt water around this spot, inside these boxes (south, north, west, east), so
# the Sound, Hood Canal, Admiralty Inlet and the eastern Strait are kept and the open Pacific and the bays south of
# the Olympics are not. Channels are widened by this many cells (half a kilometer each) so they stay a pixel wide
# at the map's size, and the outline is simplified to within this many degrees.
SEA_OUTLINE = {"seattle": {"seed": (47.60, -122.45), "boxes": [(47.0, 48.45, -123.3, -122.0), (48.0, 48.45, -124.3, -122.0)],
                           "widen": 3, "tolerance": 0.04}}


def unrun(data: bytes, rows: int, columns: int) -> np.ndarray:
    """The water mask back from its runs (see runs)."""
    out, k = [], 0
    while k < len(data):
        value, count, shift = data[k], 0, 0
        k += 1
        while True:
            byte = data[k]
            k += 1
            count |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                break
        out.append(np.full(count, value, np.uint8))
    return np.concatenate(out).reshape(rows, columns)


def simplify(points: list, tolerance: float) -> list:
    """Douglas-Peucker on an open line of (x, y), without recursion."""
    keep, stack = {0, len(points) - 1}, [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        (x0, y0), (x1, y1) = points[a], points[b]
        length = math.hypot(x1 - x0, y1 - y0)
        far = [abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / length if length else math.hypot(x - x0, y - y0)
               for x, y in points[a + 1:b]]
        k = int(np.argmax(far))
        if far[k] > tolerance:
            keep.add(a + 1 + k)
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return [points[k] for k in sorted(keep)]


def outline(shape: np.ndarray) -> list:
    """The outer edge of the one region in a boolean grid, as (row, col) corners in order, walked along the cell
    edges with the region on the left."""
    rows, cols = shape.shape
    filled = lambda r, c: 0 <= r < rows and 0 <= c < cols and shape[r, c]
    r0, c0 = map(int, np.argwhere(shape)[0])
    # Start at the top edge of the first cell, heading east (the region is below, on the right in row-down terms).
    start = (r0, c0, 0)
    steps = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}  # east, south, west, north along corners
    r, c, heading = start
    path = []
    while True:
        path.append((r, c))
        # Try turning toward the region first, then straight, then away.
        for turn in (1, 0, 3, 2):
            h = (heading + turn) % 4
            dr, dc = steps[h]
            # The cell on the right of the edge from corner (r, c) heading h must be filled, the left one empty.
            right = {0: (r, c), 1: (r, c - 1), 2: (r - 1, c - 1), 3: (r - 1, c)}[h]
            left = {0: (r - 1, c), 1: (r, c), 2: (r, c - 1), 3: (r - 1, c - 1)}[h]
            if filled(*right) and not filled(*left):
                heading = h
                r, c = r + dr, c + dc
                break
        if (r, c) == start[:2]:
            break
    return path


def sea_outline(region: str) -> list:
    """The region's sea, from its water mask, as one simplified ring of [lon, lat]."""
    spec, meta = SEA_OUTLINE[region], json.loads((ROOT / "data" / f"{stem(region)}.json").read_text())
    rows, columns = meta["rows"], meta["columns"]
    wet = unrun((ROOT / "data" / meta["water_mask"]).read_bytes(), rows, columns) >= 128
    lats = np.linspace(meta["lat_n"], meta["lat_s"], rows)[:, None]
    lons = np.linspace(meta["lon_w"], meta["lon_e"], columns)[None, :]
    inside = np.zeros_like(wet)
    for south, north, west, east in spec["boxes"]:
        inside |= (lats >= south) & (lats <= north) & (lons >= west) & (lons <= east)
    parts, _ = label(wet & inside)
    seed = parts[int(round((meta["lat_n"] - spec["seed"][0]) / (meta["lat_n"] - meta["lat_s"]) * (rows - 1))),
                 int(round((spec["seed"][1] - meta["lon_w"]) / (meta["lon_e"] - meta["lon_w"]) * (columns - 1)))]
    sea = binary_fill_holes(binary_dilation(parts == seed, iterations=spec["widen"]) & inside)
    corners = outline(sea)
    # Corner (r, c) lies half a cell up and left of cell (r, c)'s center.
    to_lonlat = lambda r, c: (meta["lon_w"] + (c - 0.5) / (columns - 1) * (meta["lon_e"] - meta["lon_w"]),
                              meta["lat_n"] - (r - 0.5) / (rows - 1) * (meta["lat_n"] - meta["lat_s"]))
    # A closed ring is simplified as two halves, split at the corner farthest from where it starts.
    ring = [to_lonlat(r, c) for r, c in corners]
    half = max(range(len(ring)), key=lambda k: math.dist(ring[0], ring[k]))
    ring = simplify(ring[:half + 1], spec["tolerance"])[:-1] + simplify(ring[half:] + [ring[0]], spec["tolerance"])[:-1]
    return [[round(lon, 2), round(lat, 2)] for lon, lat in ring]


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
    if "--locator-water" in sys.argv:
        print(json.dumps(sea_outline(sys.argv[1]), separators=(",", ":")))
    else:
        main(*sys.argv[1:2])
