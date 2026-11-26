"""Ski Santa Fe's lifts and trails, and its snow report, from the reports its own lift and trail report page reads
(skisantafe.com/conditions/lift-trail-report).

The page is drawn in the browser from three reports on the resort's own site: the lifts, the trails and the
conditions. Each lift and trail names its part of the mountain (Lower Mountain, Upper Mountain), which is its mountain
area here, and its status in the resort's own word. A trail's difficulty is one of the report's five words, and one
the reader does not know fails. Each list has to be whole (all its rows on the one page asked for), and the
conditions report's own counts of lifts and trails have to match the lists, so a change in the reports' shape fails
instead of showing wrong numbers.

The conditions report carries the snow report: one base depth, the snowfall of the last 12, 24, 48 and 72 hours and
7 days, the storm's and the season's totals, in inches, and when the snow report was last written. It gives a summit
depth too, which is read only when it is more than nothing, and no word for the surface. Its times are in UTC, so no
time zone is needed. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import json
from datetime import datetime, timezone

API = "https://www.skisantafe.com/api"
URLS = {"lifts": f"{API}/lifts?limit=100", "trails": f"{API}/trails?limit=200", "conditions": f"{API}/conditions"}
NAME = "Ski Santa Fe"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The report's difficulty words, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"Green": "Green", "Blue": "Blue", "Black": "Black", "Double Black": "Double black", "Terrain Park": ""}
# The snow report's figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"baseDepth": "BaseIn", "snow12h": "Last12HoursIn", "snow24h": "Last24HoursIn", "snow48h": "Last48HoursIn",
            "snow72h": "Last72HoursIn", "snow7d": "Last7DaysIn"}


def read(page: str, what: str):
    try:
        return json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the {what} report does not read as JSON: {error}") from error


def listed(page: str, what: str) -> list:
    """The rows of a list, which has to be whole: as many rows as it says it has, and no page after this one."""
    report = read(page, what)
    rows = report.get("docs") if isinstance(report, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"the {what} report is not a list of rows")
    if report.get("totalDocs") != len(rows) or report.get("hasNextPage") is not False:
        raise ValueError(f"the {what} report says it has {report.get('totalDocs')} rows but gives {len(rows)}")
    return rows


def status_row(row: dict, difficulty: str | None) -> dict:
    name, status = row.get("name"), row.get("status")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the report lists a lift or a trail with no name")
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"{name} has no status")
    words = " ".join(status.split()).capitalize()
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail.get("difficulty") not in LEVELS:
        raise ValueError(f"{trail.get('name')} has a difficulty the reader does not know: {trail.get('difficulty')}")
    row = status_row(trail, LEVELS[trail["difficulty"]])
    # The report says "Groomed Today" or "Not Groomed".
    row["Grooming"] = "Yes" if str(trail.get("groomingStatus") or "").lower().startswith("groomed") else "No"
    return row


def area_of(areas: dict, row: dict) -> dict:
    name = row.get("area")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{row.get('name')} does not name its part of the mountain")
    return areas.setdefault(name.strip(), {"Name": name.strip(), "Lifts": [], "Trails": []})


def figure(value, what: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"the snow report's {what} reads {value!r}, not inches")
    return value


def snow_report(conditions: dict) -> dict:
    """The conditions report's snow figures in the shape of the Ikon feed's SnowReport."""
    try:
        said, written = conditions["weather"]["snowReport"], conditions["snowReportLastUpdated"]
        at = datetime.strptime(written, "%Y-%m-%dT%H:%M:%S.%f%z")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"the snow report is not in the shape expected: {error!r}") from error
    if not isinstance(said, dict):
        raise ValueError("the snow report is not in the shape expected")
    figures = {ikon: figure(said.get(field), field) for field, ikon in SNOWFALL.items()}
    if figures["BaseIn"] is None or figures["Last24HoursIn"] is None:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    report = {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
              "SeasonTotalIn": figure(said.get("seasonTotal"), "seasonTotal"),
              "StormTotalIn": figure(said.get("stormTotal"), "stormTotal"),
              "BaseArea": {"Name": "Base", **{ikon: value for ikon, value in figures.items() if value is not None}},
              "Report": None, "Alert": None}
    # The summit's depth reads 0 while the resort does not measure it.
    if figure(said.get("summitDepth"), "summitDepth"):
        report["SummitArea"] = {"Name": "Summit", "BaseIn": said["summitDepth"]}
    return report


def parse(pages: dict, now: datetime) -> dict:
    lifts, trails = listed(pages["lifts"], "lift"), listed(pages["trails"], "trail")
    conditions = read(pages["conditions"], "conditions")
    if not isinstance(conditions, dict):
        raise ValueError("the conditions report is not in the shape expected")
    if conditions.get("totalLifts") != len(lifts) or conditions.get("totalTrails") != len(trails):
        raise ValueError(f"the conditions report counts {conditions.get('totalLifts')} lifts and "
                         f"{conditions.get('totalTrails')} trails but {len(lifts)} and {len(trails)} were read")
    areas = {}
    for lift in lifts:
        area_of(areas, lift)["Lifts"].append(status_row(lift, None))
    for trail in trails:
        area_of(areas, trail)["Trails"].append(trail_row(trail))
    if not lifts or not trails:
        raise ValueError("the reports list no lifts or no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        feed["SnowReport"] = snow_report(conditions)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
