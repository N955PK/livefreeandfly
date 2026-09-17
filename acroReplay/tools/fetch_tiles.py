#!/usr/bin/env python3
"""Bundle aerial-imagery tiles for offline use in the cockpit (the phone has no internet on the Hub's Wi-Fi).

    python tools/fetch_tiles.py --lat 36.936 --lon -121.790            # KWVI area, default rings

Writes web/tiles/{z}/{x}/{y}.jpg plus web/tiles/index.json (its presence tells the app to use the bundle).
Rings mirror web/tiles.js LEVELS: z16 within 1.5 km, z14 within 9 km, z12 within 45 km, z10 within 160 km,
z8 within 640 km.
Roughly 400 tiles / 10 MB. Imagery: Esri World Imagery, falling back to USGS. Check the providers' terms
before bundling large areas.
"""

import argparse
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

LEVELS = [(16, 1500), (14, 9000), (12, 45000), (10, 160000), (8, 640000)]
SOURCES = [
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
]
EARTH_RADIUS_M = 6378137.0


def tile_index(lat, lon, z):
    n = 2 ** z
    lat_r = math.radians(lat)
    return (int((lon + 180) / 360 * n), int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n))


def tiles_for(lat0, lon0, levels):
    m_per_deg_lat = EARTH_RADIUS_M * math.pi / 180
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat0))
    seen = []
    for z, radius in levels:
        d_lat, d_lon = radius / m_per_deg_lat, radius / m_per_deg_lon
        x0, y0 = tile_index(lat0 + d_lat, lon0 - d_lon, z)
        x1, y1 = tile_index(lat0 - d_lat, lon0 + d_lon, z)
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield z, x, y
        seen.append(radius)


def fetch(url, dest):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "acroReplay tile bundler"})
            with urllib.request.urlopen(req, timeout=20) as r:
                dest.write_bytes(r.read())
                return True
        except Exception:  # noqa: BLE001 - retry any transport error, then fall through to the next source
            time.sleep(0.5 * (attempt + 1))
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "web" / "tiles"))
    args = ap.parse_args()
    out = Path(args.out)
    todo = list(tiles_for(args.lat, args.lon, LEVELS))
    print(f"{len(todo)} tiles → {out}")
    ok = 0
    for i, (z, x, y) in enumerate(todo, 1):
        dest = out / str(z) / str(x) / f"{y}.jpg"
        if dest.exists():
            ok += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if any(fetch(src.format(z=z, x=x, y=y), dest) for src in SOURCES):
            ok += 1
        if i % 50 == 0:
            print(f"  {i}/{len(todo)}")
    (out / "index.json").write_text(json.dumps({"lat": args.lat, "lon": args.lon, "levels": LEVELS, "tiles": ok}))
    print(f"done: {ok}/{len(todo)} tiles")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
