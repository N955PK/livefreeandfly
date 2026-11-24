"""Build the 3D map's highway lines from OpenStreetMap via Overpass (ODbL; no key).

Writes data/roads.json for Tahoe and data/roads-<region>.json for the others, over the box of that region's
terrain file: [{"route": "I-80", "lines": [[[lon, lat], ...], ...]}, ...]. python tools/build_roads.py [region].
Route names match the Caltrans chain-control feed (I-80, US-50, SR-89, ...).
Run once per region, after build_terrain.py; the output is committed.
"""
import json
import sys
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
SERVERS = ["https://overpass.kumi.systems/api/interpreter", "https://overpass-api.de/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
ROUTES = {
    "tahoe": {"I 80": "I-80", "US 50": "US-50", "CA 89": "SR-89", "CA 28": "SR-28", "CA 267": "SR-267",
              "CA 88": "SR-88", "CA 4": "SR-4", "CA 20": "SR-20", "CA 49": "SR-49", "NV 431": "NV-431",
              "NV 207": "NV-207", "NV 28": "NV-28", "US 395": "US-395", "I 580": "I-580"},
    "mammoth": {"US 395": "US-395", "CA 203": "SR-203", "CA 158": "SR-158", "CA 120": "SR-120", "CA 108": "SR-108",
                "CA 167": "SR-167", "CA 168": "SR-168", "CA 182": "SR-182", "CA 270": "SR-270", "US 6": "US-6"},
    # OSM tags concurrent routes as "I 93;US 3"; the query and the split on ";" in main() already match each.
    "newengland": {"I 93": "I-93", "I 89": "I-89", "I 91": "I-91", "I 95": "I-95", "US 2": "US-2", "US 4": "US-4",
                   "US 302": "US-302", "VT 100": "VT-100", "VT 108": "VT-108", "NH 16": "NH-16", "NH 112": "NH-112",
                   "ME 26": "ME-26", "ME 27": "ME-27"},
    # OpenStreetMap writes Washington's state routes "SR 410", as Washington does; the map draws them with the plain
    # white marker (REGIONS.seattle.plainStateRoutes in the page), not California's spade.
    "seattle": {"I 5": "I-5", "I 90": "I-90", "I 405": "I-405", "US 2": "US-2", "US 12": "US-12", "US 97": "US-97",
                "US 101": "US-101", "SR 410": "SR-410", "SR 542": "SR-542", "SR 20": "SR-20", "SR 530": "SR-530",
                "SR 706": "SR-706", "SR 503": "SR-503", "SR 141": "SR-141"},
    # The roads to Jackson and over its passes: the Snake River highways, Teton Pass (WY 22) and the road to Teton
    # Village (WY 390), Togwotee Pass (US 26/287), and Idaho's side to Driggs and Grand Targhee.
    "tetons": {"US 26": "US-26", "US 89": "US-89", "US 191": "US-191", "US 287": "US-287", "WY 22": "WY-22",
               "WY 390": "WY-390", "ID 33": "ID-33", "ID 31": "ID-31", "ID 32": "ID-32"},
    # The Wasatch Front's interstates, the roads behind the range, and the canyon roads to the lifts: Little and
    # Big Cottonwood (UT 210, UT 190), Park City (UT 224), Provo Canyon and Sundance (US 189, UT 92), Ogden Canyon
    # and Snowbasin (UT 39, UT 226, UT 167) and Powder Mountain (UT 158). OpenStreetMap writes Utah's state routes
    # as "SR" on most ways and "UT" on some, so both are asked for.
    "wasatch": {"I 15": "I-15", "I 80": "I-80", "I 84": "I-84", "I 215": "I-215", "US 40": "US-40",
                "US 189": "US-189", "US 89": "US-89", "SR 210": "UT-210", "SR 190": "UT-190", "SR 224": "UT-224",
                "SR 92": "UT-92", "SR 39": "UT-39", "SR 226": "UT-226", "SR 167": "UT-167", "SR 158": "UT-158",
                "UT 210": "UT-210", "UT 190": "UT-190", "UT 224": "UT-224", "UT 92": "UT-92", "UT 39": "UT-39",
                "UT 226": "UT-226", "UT 167": "UT-167", "UT 158": "UT-158"},
    # I-70 over the Divide and Vail Pass, the roads to Winter Park and Steamboat (US 40) and over Loveland Pass
    # (US 6), to Breckenridge (CO 9) and from Copper to Leadville (CO 91), and the Colorado River road (CO 131).
    # OpenStreetMap writes Colorado's state routes as "CO" on most ways and "SH" on some, so both are asked for.
    "colorado": {"I 70": "I-70", "US 40": "US-40", "US 6": "US-6", "US 24": "US-24", "US 34": "US-34",
                 "CO 9": "CO-9", "CO 91": "CO-91", "CO 131": "CO-131", "CO 14": "CO-14",
                 "SH 9": "CO-9", "SH 91": "CO-91", "SH 131": "CO-131", "SH 14": "CO-14"},
    # I-5 through the Sacramento canyon and over Siskiyou Summit, US 97 north of Mt. Shasta, the McCloud and Lassen
    # roads (CA 89, CA 44), CA 299 across the south, CA 3 through the Trinities and the Mt. Ashland turn-off's CA 96.
    "shasta": {"I 5": "I-5", "US 97": "US-97", "CA 89": "SR-89", "CA 44": "SR-44", "CA 299": "SR-299",
               "CA 3": "SR-3", "CA 96": "SR-96", "CA 36": "SR-36", "OR 66": "OR-66"},
    # British Columbia's highways as OpenStreetMap writes them: "BC 97", the Yellowhead as "YH 5" and the
    # Trans-Canada as "TCH 1". The Okanagan's valley road (97), the Connector (97C), the roads toward Big White (33)
    # and Apex (3A), Vernon's Highway 6, and the Yellowhead and Trans-Canada through Kamloops toward Sun Peaks.
    "okanagan": {"BC 97": "BC-97", "BC 97C": "BC-97C", "BC 33": "BC-33", "BC 3A": "BC-3A", "BC 6": "BC-6",
                 "BC 97A": "BC-97A", "BC 3": "BC-3", "YH 5": "BC-5", "BC 5": "BC-5", "TCH 1": "TCH-1"},
}
TOLERANCE_DEG = 0.0004
# The Sierra crest as (lat, lon), north to south, set a little west of the passes. Mammoth's map keeps only the
# roads east of it: the page reads road status for the east side alone, and the west-side roads dead-end.
CREST = {"mammoth": [(38.46, -119.74), (38.33, -119.66), (37.91, -119.28), (37.65, -119.08), (37.21, -118.63),
                     (36.58, -118.31), (36.22, -118.12)]}


def east_of(geometry: list, crest: list) -> list:
    """The runs of a way's (lon, lat) points that lie east of the crest."""
    lats, lons = np.array(crest)[::-1].T
    points = np.array(geometry)
    keep = points[:, 0] >= np.interp(points[:, 1], lats, lons)
    runs = np.split(np.arange(len(points)), np.flatnonzero(np.diff(keep)) + 1)
    return [[geometry[i] for i in run] for run in runs if keep[run[0]] and len(run) >= 2]


def simplify(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Douglas-Peucker."""
    if len(points) < 3:
        return points
    start, end = points[0], points[-1]
    segment = end - start
    length = np.hypot(*segment)
    offsets = points - start
    distance = np.hypot(*offsets.T) if length == 0 else np.abs(segment[0] * offsets[:, 1] - segment[1] * offsets[:, 0]) / length
    worst = int(distance.argmax())
    if distance[worst] <= tolerance:
        return np.array([start, end])
    return np.vstack([simplify(points[:worst + 1], tolerance)[:-1], simplify(points[worst:], tolerance)])


def chain(ways: list) -> list:
    """Join ways that share end points into longer lines."""
    lines = [list(map(tuple, way)) for way in ways]
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(lines):
            for j, b in enumerate(lines):
                if i == j:
                    continue
                if a[-1] == b[0]:
                    lines[i] = a + b[1:]
                elif a[-1] == b[-1]:
                    lines[i] = a + b[-2::-1]
                elif a[0] == b[-1]:
                    lines[i] = b + a[1:]
                elif a[0] == b[0]:
                    lines[i] = b[::-1] + a[1:]
                else:
                    continue
                del lines[j]
                merged = True
                break
            if merged:
                break
    return lines


def main(region: str = "tahoe") -> None:
    suffix = "" if region == "tahoe" else f"-{region}"
    box = json.loads((ROOT / "data" / f"terrain{suffix}.json").read_text())
    BBOX = (box["lat_s"], box["lon_w"], box["lat_n"], box["lon_e"])
    routes = ROUTES[region]
    pattern = "|".join(routes)
    query = f"""[out:json][timeout:120];
way["highway"~"^(motorway|trunk|primary|secondary)$"]["ref"~"(^|;) ?({pattern})( ?;|$)"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
out geom;"""
    response = None
    for server in SERVERS:
        try:
            response = requests.post(server, data={"data": query}, headers={"User-Agent": "roads-builder/0.1"}, timeout=180)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            print(server, "failed:", str(error)[:80])
            response = None
    if response is None:
        raise SystemExit("no Overpass server answered")
    by_route = {}
    for way in response.json()["elements"]:
        refs = [ref.strip() for ref in way["tags"]["ref"].split(";")]
        geometry = [(round(p["lon"], 5), round(p["lat"], 5)) for p in way["geometry"]]
        pieces = east_of(geometry, CREST[region]) if region in CREST else [geometry]
        for ref in refs:
            if ref in routes:
                by_route.setdefault(routes[ref], []).extend(pieces)
    out = []
    for route, ways in sorted(by_route.items()):
        lines = [simplify(np.array(line), TOLERANCE_DEG).round(5).tolist() for line in chain(ways)]
        lines = [line for line in lines if len(line) >= 2]
        out.append({"route": route, "lines": lines})
        print(route, len(ways), "ways ->", len(lines), "lines,", sum(len(line) for line in lines), "points")
    (ROOT / "data" / f"roads{suffix}.json").write_text(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main(*sys.argv[1:2])
