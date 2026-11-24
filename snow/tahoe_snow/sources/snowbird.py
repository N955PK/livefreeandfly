"""Snowbird's lifts and trails, and its snow report, from the reports its own mountain report page reads
(snowbird.com/the-mountain/mountain-report/lift-trail-report/).

The page is drawn in the browser from three reports on the resort's own API (api.snowbird.com/api/v1/dor/drupal):
the lifts, the trails and the snow reports, newest first. Each lift and trail names its part of the mountain
(Peruvian Gulch, Gad Valley, Mineral Basin), which is its mountain area here. The trail report also lists the summer
hiking and biking trails and the trails Snowbird marks as not for the status page; only the winter ski trails it
shows are kept.

The snow report is written by the resort each morning: one base depth, the new snow, the snowfall of the last 24,
48 and 72 hours and 7 days, the season's total, the resort's own words, and when it was posted, in Mountain time.
It gives no surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

API = "https://api.snowbird.com/api/v1/dor/drupal"
URLS = {"lifts": f"{API}/lifts", "trails": f"{API}/trails", "snow": f"{API}/snow-reports?sort=date&direction=desc"}
NAME = "Snowbird"
MOUNTAIN = ZoneInfo("America/Denver")
SEASONS = {"winter", "all"}
SKIED = {"alpine_trail"}
# The report's difficulty words, in the words the page's difficulty symbols are keyed on.
LEVELS = {"easiest": "Green", "more_difficult": "Blue", "most_difficult": "Black", "extreme": "Double black"}
# The snow report's computed snowfall, by the names the Ikon feed gives them.
SNOWFALL = {"24_hour": "Last24HoursIn", "48_hour": "Last48HoursIn", "72_hour": "Last72HoursIn", "7_day": "Last7DaysIn"}


def status_row(name, status, difficulty: str | None) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the report lists a lift or a trail with no name")
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"{name} has no status")
    words = status.replace("_", " ").strip().capitalize()
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail["difficulty"] not in LEVELS:
        raise ValueError(f"{trail['name']} has a difficulty the reader does not know: {trail['difficulty']}")
    row = status_row(trail["name"], trail["status"], LEVELS[trail["difficulty"]])
    row["Grooming"] = "Yes" if trail["groom_status"] == "groomed" else "No"
    return row


def listed(page: str, what: str) -> list:
    try:
        rows = json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the {what} report does not read as JSON: {error}") from error
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"the {what} report is not a list")
    return rows


def figure(value) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"a snow figure reads {value!r}, not a number")
    return int(value) if float(value).is_integer() else value


def snow_report(reports: list) -> dict | None:
    """The newest snow report in the shape of the Ikon feed's SnowReport: one set of figures for the whole mountain.
    None when there is no report."""
    if not reports:
        return None
    try:
        report = max(reports, key=lambda each: each["date"])
        if report["unit_of_measurement"] != "in":
            raise ValueError(f"the snow report's units are {report['unit_of_measurement']}, not inches")
        posted = datetime.strptime(report["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOUNTAIN)
        computed = report["computed"]
        area = {"Name": "Mountain", "BaseIn": figure(report["base_depth"]),
                **{ikon: figure(computed[field]) for field, ikon in SNOWFALL.items()},
                "OvernightIn": figure(report["overnight_amount"])}
        return {"LastUpdate": posted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
                "BaseConditions": None, "SeasonTotalIn": figure(computed["total"]), "BaseArea": area,
                "Report": report.get("report") or None}
    except (KeyError, TypeError) as error:
        raise ValueError(f"the snow report is not in the shape expected: {error!r}") from error


def parse(pages: dict, now: datetime) -> dict:
    lifts, trails = listed(pages["lifts"], "lift"), listed(pages["trails"], "trail")
    areas = {}
    try:
        for lift in lifts:
            if lift["season"] in SEASONS:
                area = areas.setdefault(lift["sector"]["name"], {"Name": lift["sector"]["name"], "Lifts": [], "Trails": []})
                area["Lifts"].append(status_row(lift["name"], lift["status"], None))
        for trail in trails:
            if trail["season"] in SEASONS and trail["type"] in SKIED and trail["include"] is True:
                area = areas.setdefault(trail["sector"]["name"], {"Name": trail["sector"]["name"], "Lifts": [], "Trails": []})
                area["Trails"].append(trail_row(trail))
    except (KeyError, TypeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Lifts"] for area in areas.values()):
        raise ValueError("the report lists no lifts")
    if not any(area["Trails"] for area in areas.values()):
        raise ValueError("the report lists no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": list(areas.values())}
    try:
        snow = snow_report(listed(pages["snow"], "snow"))
    except ValueError as error:
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
