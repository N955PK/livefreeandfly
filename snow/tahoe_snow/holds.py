"""A running record of lift holds beside the wind that was forecast for the same hour.

For the mountains whose resort publishes live lift status, each run during lift hours appends one line per
mountain: how many lifts are open, held, expected, and closed, which lifts are held and in what words, and the
summit wind the published forecast has for that hour. After a few storms this shows what wind actually produces
holds at each mountain, which the outlook's wind thresholds are then set from. Standard library only.
python -m tahoe_snow.holds holds.jsonl
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FEED = "https://mtnpowder.com/feed?resortId={id}"
FORECAST = "https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast.json"
ALPINE_AREAS = {"Summit Peak", "Scott/Lakeview Peak", "Sherwood Bowl"}
# Mountain: (feed id, whether one of the feed's areas belongs to it).
MOUNTAINS = {
    "palisades": (61, lambda area: area not in ALPINE_AREAS),
    "alpine": (61, lambda area: area in ALPINE_AREAS),
    "mammoth": (60, lambda area: True),
    "june": (59, lambda area: True),
}
LIFT_HOURS = (8, 17)
LOCAL = ZoneInfo("America/Los_Angeles")


def group_of(status: str) -> str:
    if status.startswith("open"):
        return "open"
    if re.search("hold|delay", status):
        return "hold"
    return "soon" if re.search("expect|sched", status) else "closed"


def lift_counts(feed: dict, mine) -> dict | None:
    """Counts by group and the held lifts with the resort's word for each; None when the season has not begun."""
    lifts = [lift for area in feed.get("MountainAreas") or [] if mine(area.get("Name"))
             for lift in area.get("Lifts") or []]
    if not lifts or all("season" in (lift.get("StatusEnglish") or "") for lift in lifts):
        return None
    out = {"open": 0, "hold": 0, "soon": 0, "closed": 0, "held": {}}
    for lift in lifts:
        group = group_of(lift.get("StatusEnglish") or "")
        out[group] += 1
        if group == "hold":
            out["held"][lift.get("Name")] = lift.get("Status")
    return out


def summit_wind(forecast: dict, key: str, now: datetime) -> dict:
    """The forecast's summit wind for the hour containing ``now``; empty when the forecast does not reach it."""
    resort = next((r for r in forecast.get("resorts", []) if r["key"] == key), None)
    stamp = now.strftime("%Y-%m-%dT%H:00:00Z")
    if resort is None or stamp not in resort.get("hours_utc", []):
        return {}
    at, hourly = resort["hours_utc"].index(stamp), resort["elevations"]["summit"]["hourly"]
    return {name: hourly[name][at] for name in ("wind_mph", "gust_mph", "wind_from_deg") if name in hourly}


def rows(feeds: dict, forecast: dict, now: datetime) -> list[dict]:
    out = []
    for key, (feed_id, mine) in MOUNTAINS.items():
        counts = lift_counts(feeds.get(feed_id) or {}, mine)
        if counts is not None:
            out.append({"utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resort": key, **counts,
                        **summit_wind(forecast, key, now),
                        "forecast_utc": forecast.get("published_utc") or forecast.get("generated_utc")})
    return out


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(path: str) -> int:
    now = datetime.now(timezone.utc)
    if not LIFT_HOURS[0] <= now.astimezone(LOCAL).hour < LIFT_HOURS[1]:
        print("Outside lift hours; nothing recorded.")
        return 0
    feeds = {feed_id: get(FEED.format(id=feed_id)) for feed_id in {spec[0] for spec in MOUNTAINS.values()}}
    found = rows(feeds, get(FORECAST), now)
    with open(path, "a") as handle:
        for row in found:
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(f"{len(found)} mountains recorded; held: {sum(row['hold'] for row in found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
