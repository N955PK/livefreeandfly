"""Nevada road status from the Nevada 511 developer feed (nvroads.com, free key in NV511_KEY).

Writes the winter road conditions and full closures near the map regions as one small file the page reads:
points along each affected road, in the shape of the Caltrans chain-control points the map already colors
roads from, and one row per affected stretch for the list under the map. Standard library only, so the job
that runs it needs no install step. python -m tahoe_snow.sources.nv511 out.json
"""
import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://www.nvroads.com/api/v2/get/{resource}?key={key}&format=json"
# The Nevada side of the Tahoe and Mammoth maps.
BOX = {"lat_s": 37.0, "lat_n": 39.8, "lon_w": -120.2, "lon_e": -118.0}
POINT_EVERY_KM = 2.0
CLOSED = re.compile(r"clos|holding", re.I)
CHAINS = re.compile(r"chain|snow tire", re.I)
ROUTE = re.compile(r"^\s*(I|US|SR|NV)[\s-]*(\d+)", re.I)


def route_name(roadway: str) -> str | None:
    """'SR-431', 'NV 431', 'I-580' as the map names them: Nevada state routes are NV-431."""
    found = ROUTE.match(roadway or "")
    if not found:
        return None
    kind = found.group(1).upper()
    return f"{'NV' if kind == 'SR' else kind}-{found.group(2)}"


def status_of(text: str) -> str | None:
    if CLOSED.search(text or ""):
        return "closed"
    return "chains" if CHAINS.search(text or "") else None


def decode(polyline: str) -> list[tuple[float, float]]:
    """Google encoded polyline to [(lat, lon), ...]."""
    out, at, lat, lon = [], 0, 0, 0
    while at < len(polyline):
        pair = []
        for _ in range(2):
            value, shift = 0, 0
            while True:
                chunk = ord(polyline[at]) - 63
                at += 1
                value |= (chunk & 0x1F) << shift
                shift += 5
                if chunk < 0x20:
                    break
            pair.append(~(value >> 1) if value & 1 else value >> 1)
        lat, lon = lat + pair[0], lon + pair[1]
        out.append((lat / 1e5, lon / 1e5))
    return out


def lines_of(encoded) -> list[list[tuple[float, float]]]:
    parts = [encoded] if isinstance(encoded, str) else (encoded or [])
    return [line for line in (decode(part) for part in parts if part) if line]


def km_between(a, b) -> float:
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0])))


def spaced(line, every_km: float = POINT_EVERY_KM) -> list[tuple[float, float]]:
    """Both ends of the line and a point every few km between them."""
    out, since = [line[0]], 0.0
    for a, b in zip(line, line[1:]):
        since += km_between(a, b)
        if since >= every_km:
            out.append(b)
            since = 0.0
    if out[-1] != line[-1]:
        out.append(line[-1])
    return out


def inside(point) -> bool:
    return BOX["lat_s"] <= point[0] <= BOX["lat_n"] and BOX["lon_w"] <= point[1] <= BOX["lon_e"]


def stretch(route, status, text, where, since, lines) -> dict | None:
    """One affected stretch of road: its row for the list and its points for the map, or None outside the maps."""
    points = [p for line in lines for p in spaced(line) if inside(p)]
    if not points:
        return None
    middle = points[len(points) // 2]
    return {"row": {"route": route, "status": status, "text": text, "where": where, "since": since,
                    "lat": round(middle[0], 4), "lon": round(middle[1], 4)},
            "points": [{"route": route, "status": status, "name": where, "lat": round(lat, 4), "lon": round(lon, 4)}
                       for lat, lon in points]}


def from_conditions(rows: list) -> list[dict]:
    out = []
    for row in rows:
        route, status = route_name(row.get("RoadwayName")), status_of(row.get("Overall Status"))
        if route and status:
            where = (row.get("LocationDescription") or "").strip()
            out.append(stretch(route, status, row["Overall Status"].strip(), where, row.get("LastUpdated"),
                               lines_of(row.get("EncodedPolyline"))))
    return [item for item in out if item]


def from_events(rows: list) -> list[dict]:
    """Full closures only; roadwork and crashes that leave a lane open are not road status."""
    out = []
    for row in rows:
        route = route_name(row.get("RoadwayName"))
        if not route or not row.get("IsFullClosure"):
            continue
        lines = lines_of(row.get("EncodedPolyline"))
        if not lines and row.get("Latitude") and row.get("Longitude"):
            lines = [[(float(row["Latitude"]), float(row["Longitude"]))]]
        where = (row.get("Description") or "").strip()
        out.append(stretch(route, "closed", "Closed", where, row.get("StartDate"), lines))
    return [item for item in out if item]


def build(conditions: list, events: list, now: datetime) -> dict:
    found = from_conditions(conditions) + from_events(events)
    return {"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "rows": [item["row"] for item in found],
            "points": [point for item in found for point in item["points"]]}


def fetch(resource: str, key: str) -> list:
    request = urllib.request.Request(URL.format(resource=resource, key=key), headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(out_path: str) -> int:
    key = os.environ.get("NV511_KEY", "")
    if not key:
        print("NV511_KEY is not set; nothing written.")
        return 0
    status = build(fetch("roadconditions", key), fetch("event", key), datetime.now(timezone.utc))
    with open(out_path, "w") as handle:
        json.dump(status, handle, separators=(",", ":"))
    print(f"{len(status['rows'])} affected stretches, {len(status['points'])} points")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
