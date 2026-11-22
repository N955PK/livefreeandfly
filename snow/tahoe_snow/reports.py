"""A running record of the resorts' own snow reports beside what the forecast had for the same day.

For the mountains whose resort publishes a report in its feed, each new report (one a morning, sometimes a second
when the resort revises it) appends one line per mountain: the snow the resort measured at its base, mid-mountain and
summit stakes (base depth, the last 24, 48 and 72 hours, since the lifts closed), how the resort describes the surface,
how much of the mountain is open and groomed, which subjects its written report raises (wind holds, delays,
avalanche work, powder, rain and so on), and the forecast's own figures for that ski day at each elevation.
After a few storms this shows where the forecast and the status run high or low against what the resort reported.

The report's words are the resort's own writing and are not kept: only the measurements and the subjects it raises.
Standard library only.
python -m tahoe_snow.reports reports.jsonl
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FEED = "https://mtnpowder.com/feed?resortId={id}"
FORECAST = "https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast.json"
LOCAL = ZoneInfo("America/Los_Angeles")
# Mountain: (feed id, the feed's name for its base, mid-mountain and summit stakes).
MOUNTAINS = {
    "palisades": (61, {"base": "BaseArea", "mid": "MidMountainArea", "summit": "SummitArea"}),
    "alpine": (61, {"base": "Station4", "mid": "Station5", "summit": "Station6"}),
    "mammoth": (60, {"base": "BaseArea", "mid": "MidMountainArea", "summit": "SummitArea"}),
    "june": (59, {"base": "BaseArea", "mid": "MidMountainArea", "summit": "SummitArea"}),
}
# What a stake reports, as (field in this record, field in the feed).
STAKE = (("base_in", "BaseIn"), ("last24_in", "Last24HoursIn"), ("last48_in", "Last48HoursIn"),
         ("last72_in", "Last72HoursIn"), ("since_close_in", "SinceLiftsClosedIn"))
COUNTS = (("open_lifts", "TotalOpenLifts"), ("lifts", "TotalLifts"), ("open_trails", "TotalOpenTrails"),
          ("trails", "TotalTrails"), ("groomed", "GroomedTrails"))
# Subjects a written report can raise, each by the words that give it away.
SUBJECTS = {
    "wind": r"\bwind(s|y)?\b|\bgust",
    "wind_hold": r"wind hold|on hold|holds? due to wind",
    "delay": r"delay|late opening|open(ing)? late",
    "avalanche_work": r"avalanche|patrol (is|are|will be) (working|doing)|mitigation|control work",
    "powder": r"\bpowder|\bpow\b|fresh snow|new snow",
    "rain": r"\brain|\bwet\b|\bslush",
    "firm": r"\bfirm\b|\bicy\b|hardpack|refroz",
    "visibility": r"visibility|whiteout|flat light|\bfog",
    "closed": r"\bclosed\b|closure|will not (open|operate)",
    "early_season": r"early[- ]season|low snow|thin cover",
}


def number(value) -> float | None:
    """A feed figure as a number; the feed writes "--" (and sometimes nothing) where it has none."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def plain(html: str | None) -> str:
    """The feed's rich text as plain words."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text.replace("&nbsp;", " ").replace("&amp;", "&")).strip()


def subjects(text: str) -> list[str]:
    """The subjects from SUBJECTS that the text raises, in SUBJECTS' order."""
    lowered = text.lower()
    return [name for name, pattern in SUBJECTS.items() if re.search(pattern, lowered)]


def stakes(report: dict, names: dict) -> dict:
    """Each elevation's stake readings; an elevation whose stake reports nothing at all is left out."""
    out = {}
    for level, name in names.items():
        area = report.get(name) or {}
        found = {field: number(area.get(source)) for field, source in STAKE}
        found = {field: value for field, value in found.items() if value is not None}
        if found:
            out[level] = found
    return out


def forecast_for(forecast: dict, key: str, day: str) -> dict:
    """The forecast's ski day ``day`` at each elevation: total, overnight and daytime snow, and the lift-hours wind."""
    resort = next((r for r in forecast.get("resorts", []) if r["key"] == key), None)
    out = {}
    for level, part in ((resort or {}).get("elevations") or {}).items():
        found = next((d for d in part.get("days", []) if d.get("date") == day), None)
        if found is None:
            continue
        powder = found.get("powder") or {}
        figures = {"snow_in": found.get("snow_in"), "night_in": powder.get("night_in"), "day_in": powder.get("day_in"),
                   "wind_mph": powder.get("wind_mph"), "gust_mph": powder.get("gust_mph"), "temp_f": powder.get("temp_f")}
        out[level] = {name: value for name, value in figures.items() if value is not None}
    return out


def row(key: str, feed: dict, forecast: dict, now: datetime) -> dict | None:
    """One mountain's line, or None when its feed carries no dated report."""
    report = feed.get("SnowReport") or {}
    stamp = report.get("LastUpdate")
    if not stamp:
        return None
    try:
        day = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z").astimezone(LOCAL).strftime("%Y-%m-%d")
    except ValueError:
        return None
    words = " ".join(plain(report.get(name)) for name in ("Report", "Alert", "LiftNotification", "News"))
    out = {"utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resort": key, "report": stamp, "day": day,
           "surface": None if report.get("BaseConditions") in (None, "", "N/A", "--") else report["BaseConditions"],
           "status": feed.get("OperatingStatus"), "stakes": stakes(report, MOUNTAINS[key][1]),
           "season_in": number(report.get("SeasonTotalIn")), "storm_in": number(report.get("StormTotalIn")),
           "subjects": subjects(words), "forecast": forecast_for(forecast, key, day),
           "forecast_utc": forecast.get("published_utc") or forecast.get("generated_utc")}
    out.update({field: number(report.get(source)) for field, source in COUNTS})
    return out


def seen(path: str) -> set:
    """The (mountain, report time) pairs already in the record."""
    try:
        with open(path) as handle:
            return {(line["resort"], line["report"]) for line in map(json.loads, filter(str.strip, handle))}
    except FileNotFoundError:
        return set()


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main(path: str) -> int:
    now, have = datetime.now(timezone.utc), seen(path)
    feeds = {feed_id: get(FEED.format(id=feed_id)) for feed_id in {spec[0] for spec in MOUNTAINS.values()}}
    forecast = get(FORECAST)
    found = [line for key, (feed_id, _) in MOUNTAINS.items()
             if (line := row(key, feeds.get(feed_id) or {}, forecast, now)) and (key, line["report"]) not in have]
    with open(path, "a") as handle:
        for line in found:
            handle.write(json.dumps(line, separators=(",", ":")) + "\n")
    print(f"{len(found)} new reports recorded: {', '.join(line['resort'] for line in found) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
