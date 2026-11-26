"""Bogus Basin's lifts and trails, and its snow report, from its trails and grooming page and its conditions page
(bogusbasin.org/your-mountain/trails-grooming and bogusbasin.org/your-mountain/conditions-webcams).

Both pages are built on the server. The trails page carries its detailed report as JSON in the page: a list of the
lifts, each with the trails it serves, and each is a mountain area here, holding itself and its trails. Two groups
at the end of the list, "Terrain Parks" and "Uphill Access Routes", are not lifts (their type is not given) and are
areas with trails only; a group left with no trails is left out. The routes for walking up (ski touring) are not
trails and are not read. A status is one of the report's codes, said in plain words (OPEN "Open", STOPPED "On hold",
FORECAST "Expected"); a lift or trail out of its season is said as closed, and a code the reader has no words for is
carried as it stands. A trail's level the reader does not know fails; terrain parks have none.
Grooming is carried only where the report says one way or the other. A trail the report lists again under a second
lift is kept only under the first, so no trail is counted twice. The page's own count of lifts ("5/10 Open") has to
match what is read, so a change in the report's shape fails instead of showing wrong numbers. Its count of trails
is not used: it is one more than the trails its own list counts.

The conditions page gives the depth, the snowfall of the last 12, 24 and 48 hours and 7 days and the season's total
in inches, and the day and time they were last updated, in Boise's time and without a year: the year is taken from
the time of reading. It gives no word for the surface. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://bogusbasin.org/your-mountain/trails-grooming/",
        "snow": "https://bogusbasin.org/your-mountain/conditions-webcams/"}
NAME = "Bogus Basin"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Boise")
# The report's status codes, in plain words. A lift or trail out of its season is closed.
STATUSES = {"CLOSED": "Closed", "CLOSED_CONTEST": "Closed Contest", "DELAYED": "Delayed",
            "DELAYED_SECURING": "Delayed Securing", "DELAYED_TECHNICAL_ISSUE": "Delayed Technical Issue",
            "DELAYED_WEATHER": "Delayed Weather", "DELAYED_WIND": "Delayed Wind", "FORECAST": "Expected",
            "FORECAST_AURORA_SKI": "Expected Aurora Ski", "FORECAST_NIGHT_SKI": "Expected Night Ski", "OPEN": "Open",
            "OPEN_DOWNHILL_ONLY": "Open Downhill Only", "OPEN_PEDESTRIAN_ONLY": "Open Pedestrian Only",
            "OUT_OF_PERIOD": "Closed", "OUT_OF_PERIOD_SEASON_BEGINNING": "Closed",
            "OUT_OF_PERIOD_SEASON_ENDING": "Closed", "STOPPED": "On hold", "STOPPED_SECURING": "On hold Securing",
            "STOPPED_TECHNICAL_ISSUE": "On hold Technical Issue", "STOPPED_WEATHER": "On hold Weather",
            "STOPPED_WIND": "On hold Wind", "PARTIAL": "Partial"}
# The report's trail levels, in the words the app's difficulty symbols are keyed on. Terrain parks have none.
LEVELS = {"GREEN_CIRCLE": "Green", "BLUE_SQUARE": "Blue", "DOUBLE_BLUE_SQUARE": "Blue", "BLACK_DIAMOND": "Black",
          "DOUBLE_BLACK_DIAMOND": "Double black", "UNDEF": ""}
GROOMED = {"GROOMED": "Yes", "MORNING_GROOMED": "Yes", "EVENING_GROOMED": "Yes", "NOT_GROOMED": "No"}
# A group of trails that is not a lift has this for its type, and a route for walking up has this for its.
NOT_A_LIFT = "UNDEF"
UPHILL = "SKI_TOURING"
# The snow totals' labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Season Total": "SeasonTotalIn", "Total Depth": "BaseIn", "12H": "Last12HoursIn", "24H": "Last24HoursIn",
            "48H": "Last48HoursIn", "72H": "Last72HoursIn", "Last 7 Days": "Last7DaysIn"}
REPORT = re.compile(r"<x-filterable-lift-trail-status\s+data-data='([^']*)'")
LIFTS_COUNTED = re.compile(r"Today(?:&apos;|&#0?39;|&#8217;|['’])s Lifts</h2>\s*<p>\s*(\d+)\s*/\s*(\d+)\s+Open\s*"
                           r"</p>")
TOTALS = re.compile(r"<div class=\"site-post-snowzone-blocks-snow-totals\">(.*?)</dl>(.*?)</div>\s*</div>", re.S)
FIGURE = re.compile(r"<dt[^>]*>(.*?)</dt>\s*<dd>\s*<span class=\"value\">(.*?)</span>\s*"
                    r"<span class=\"unit\">(.*?)</dd>", re.S)
UPDATED = re.compile(r"Last update:\s*<span class=\"date\">\s*([A-Z][a-z]+)\.? (\d{1,2})(?:st|nd|rd|th), "
                     r"(\d{1,2}):(\d{2}) ([AP]M)\s*</span>")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(item: dict, difficulty: str | None) -> dict:
    code, name = item.get("openingStatus"), (item.get("title") or "").strip()
    if not code or not name:
        raise ValueError(f"a lift or trail has no name or no status: {item}")
    if code == "UNDEF":
        raise ValueError(f"{name} has no status")
    status = STATUSES.get(code, code)
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail.get("trailLevel") not in LEVELS:
        raise ValueError(f"{trail.get('title')} has a level the reader does not know: {trail.get('trailLevel')}")
    row = status_row(trail, LEVELS[trail["trailLevel"]])
    if trail.get("groomingStatus") in GROOMED:
        row["Grooming"] = GROOMED[trail["groomingStatus"]]
    return row


def lift_areas(page: str) -> list:
    """Each lift with the trails under it, and the groups that are not lifts with theirs, in the page's order."""
    found = REPORT.search(page)
    if not found:
        raise ValueError("the detailed report was not found in the page")
    try:
        report = json.loads(html.unescape(found.group(1)))
    except ValueError as error:
        raise ValueError(f"the detailed report does not read as JSON: {error}") from error
    if not isinstance(report, dict) or not isinstance(report.get("lifts"), list):
        raise ValueError("the detailed report has no list of lifts")
    areas, seen = [], set()
    try:
        for group in report["lifts"]:
            lifts = [] if group["liftType"] == NOT_A_LIFT else [status_row(group, None)]
            trails = []
            for trail in group.get("trails") or []:
                # A trail served by two lifts is listed under both: it is kept under the first.
                if trail["id"] not in seen and trail["trailType"] != UPHILL:
                    seen.add(trail["id"])
                    trails.append(trail_row(trail))
            if lifts or trails:
                areas.append({"Name": group["title"].strip(), "Lifts": lifts, "Trails": trails})
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the detailed report is not in the shape expected: {error!r}") from error
    lifts = [lift for area in areas for lift in area["Lifts"]]
    if not lifts or not seen:
        raise ValueError("the detailed report lists no lifts or no trails")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the detailed report lists a lift twice")
    counted = LIFTS_COUNTED.search(page)
    if not counted:
        raise ValueError("the page's count of lifts was not found")
    turning = sum(lift["StatusEnglish"].startswith("open") for lift in lifts)
    if (turning, len(lifts)) != (int(counted.group(1)), int(counted.group(2))):
        raise ValueError(f"the page counts {counted.group(1)} of {counted.group(2)} lifts open but {turning} of "
                         f"{len(lifts)} were read")
    return areas


def posted(said: re.Match, now: datetime) -> str:
    """When the snow totals were updated. The page gives no year: it is the one that puts the day just behind now."""
    month, day, hour, minute, half = said.groups()
    here = now.astimezone(LOCAL_TIME)
    for year in (here.year, here.year - 1):
        try:
            at = datetime.strptime(f"{year} {month[:3]} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
        except ValueError as error:
            raise ValueError(f"the snow totals' date could not be read: {error}") from error
        at = at.replace(tzinfo=LOCAL_TIME)
        if at - here <= timedelta(days=1):
            break
    return at.astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow totals in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    block = TOTALS.search(page)
    if not block:
        raise ValueError("the snow totals were not found")
    figures = {}
    for label, said, unit in FIGURE.findall(block.group(1)):
        label = words(label)
        if label not in SNOWFALL or SNOWFALL[label] in figures:
            raise ValueError(f"the snow totals have a figure the reader does not know, or have it twice: {label}")
        if not NUMBER.fullmatch(said.strip()) or "inches" not in words(unit):
            raise ValueError(f"the snow totals' {label} reads {said!r} {words(unit)!r}, not a number of inches")
        value = float(said)
        figures[SNOWFALL[label]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow totals have no depth or no 24 hour snowfall")
    updated = UPDATED.search(block.group(2))
    if not updated:
        raise ValueError("the snow totals do not say when they were updated")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": posted(updated, now), "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
