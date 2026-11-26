"""Showdown Montana's lifts and trails, and its snow report, from the two documents its snow report page draws
(www.showdownmontana.com/snow-report).

The page holds no figures itself: two scripts on showdown-task.web.app (``trail-status.js`` and ``snow-report.js``)
each fetch one document from the resort's Firestore database, ``trailstatus/current`` and ``snowreport/current``, and
draw them. The addresses here are the scripts' own, with the public browser key the scripts send. A document is
Firestore's typed JSON ({"stringValue": ...}, {"arrayValue": ...}), read here the way the scripts read it.

The trail status document lists the lifts, each open or not, and the parts of the mountain ("Northside", "Main
Face", "Ruby Bowl"), each with its trails: open or not, groomed or not, and a difficulty letter. The lifts are an
area of their own, named for the resort, ahead of the parts. The document counts its lifts, its lifts open, its
trails, its trails open and its trails groomed, and every count has to match what was read, so a change in the
document's shape fails instead of showing wrong numbers.

The snow report document gives the depth at the base and at the summit, the snowfall overnight, of the last 24 hours
and 7 days and of the storm, and the season's total, in inches as the resort's staff typed them, with the two words
for the surface and the moment it was written. A figure left empty stays empty. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import json
import re
from datetime import datetime, timezone

BASE = "https://firestore.googleapis.com/v1/projects/showdown-task/databases/(default)/documents/"
# The public browser key the page's two scripts send with their requests.
KEY = "AIzaSyCD6TSjPNneD0iGt99aBdjirOHh0OAStdA"
URLS = {"trails": f"{BASE}trailstatus/current?key={KEY}", "snow": f"{BASE}snowreport/current?key={KEY}"}
NAME = "Showdown"
# The resort's time zone. Both documents give the moment they were written as a count from 1970, which needs none.
TIME_ZONE = "America/Denver"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The trails' difficulty letters, in the words the app's difficulty symbols are keyed on.
LEVELS = {"g": "Green", "b": "Blue", "k": "Black"}
# The snow report's fields, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"overnight": "OvernightIn", "last24": "Last24HoursIn", "last7": "Last7DaysIn", "storm": "StormTotalIn"}
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”|″|in(?:ches)?\.?)?")


def value(typed):
    """A Firestore value as plain Python, the way the page's scripts read it; a type they do not read fails."""
    if not isinstance(typed, dict) or len(typed) != 1:
        raise ValueError(f"a value of the document is not one typed value: {typed!r}")
    (kind, held), = typed.items()
    if kind in ("stringValue", "booleanValue", "doubleValue"):
        return held
    if kind == "integerValue":
        return int(held)
    if kind == "nullValue":
        return None
    if kind == "arrayValue":
        return [value(item) for item in held.get("values", [])]
    if kind == "mapValue":
        return {name: value(item) for name, item in held.get("fields", {}).items()}
    raise ValueError(f"a value of the document has a type the reader does not know: {kind}")


def document(page: str, name: str) -> dict:
    """The fields of one Firestore document, which has to be the one named."""
    try:
        data = json.loads(page)
    except ValueError as error:
        raise ValueError(f"the {name} document is not JSON: {error}") from error
    if not isinstance(data, dict) or not str(data.get("name", "")).endswith(f"/documents/{name}/current"):
        raise ValueError(f"the {name} document was not found")
    return {field: value(typed) for field, typed in data.get("fields", {}).items()}


def named(row, what: str, flags: tuple) -> str:
    """The name of a lift or trail whose row has its name and its yes-or-no fields."""
    if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
        raise ValueError(f"a {what} of the trail status has no name")
    for flag in flags:
        if not isinstance(row.get(flag), bool):
            raise ValueError(f"{row['name'].strip()} does not say whether it is {flag}")
    return " ".join(row["name"].split())


def status_row(name: str, is_open: bool, difficulty: str | None) -> dict:
    said = "Open" if is_open else "Closed"
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def counted(fields: dict, field: str, read: int, what: str) -> None:
    """The document's own count of something has to be what was read."""
    if fields.get(field) != read:
        raise ValueError(f"the trail status counts {fields.get(field)} {what} but {read} were read")


def mountain_areas(fields: dict) -> list:
    """The lifts as an area named for the resort, then each part of the mountain with its trails."""
    listed, parts = fields.get("lifts"), fields.get("areas")
    if not isinstance(listed, list) or not listed or not isinstance(parts, list) or not parts:
        raise ValueError("the trail status lists no lifts or no trails")
    lifts = [status_row(named(lift, "lift", ("open",)), lift["open"], None) for lift in listed]
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the trail status lists a lift twice")
    areas, groomed = [{"Name": NAME, "Lifts": lifts, "Trails": []}], 0
    for part in parts:
        if not isinstance(part, dict) or not isinstance(part.get("name"), str) or not part["name"].strip():
            raise ValueError("a part of the mountain has no name")
        if not isinstance(part.get("runs"), list):
            raise ValueError(f"{part['name']} has no list of trails")
        trails = []
        for run in part["runs"]:
            name = named(run, "trail", ("open", "groomed"))
            if run.get("level") not in LEVELS:
                raise ValueError(f"{name} has a difficulty the reader does not know: {run.get('level')!r}")
            trail = status_row(name, run["open"], LEVELS[run["level"]])
            trail["Grooming"] = "Yes" if run["groomed"] else "No"
            groomed += run["groomed"]
            trails.append(trail)
        areas.append({"Name": " ".join(part["name"].split()), "Lifts": [], "Trails": trails})
    trails = [trail for area in areas for trail in area["Trails"]]
    counted(fields, "liftsTotal", len(lifts), "lifts")
    counted(fields, "liftsOpen", sum(lift["StatusEnglish"] == "open" for lift in lifts), "lifts open")
    counted(fields, "total", len(trails), "trails")
    counted(fields, "openCount", sum(trail["StatusEnglish"] == "open" for trail in trails), "trails open")
    counted(fields, "groomedCount", groomed, "trails groomed")
    return areas


def inches(fields: dict, field: str):
    """One of the snow report's figures, which the staff type as text; one left empty is None."""
    said = fields.get(field)
    text = "" if said is None else str(said).strip()
    if not text:
        return None
    figure = INCHES.fullmatch(text)
    if not figure:
        raise ValueError(f"the snow report's {field} reads {text!r}, not inches")
    number = float(figure.group(1))
    return int(number) if number.is_integer() else number


def snow_report(fields: dict) -> dict:
    """The snow report document in the shape of the Ikon feed's SnowReport: the base's figures, the summit's depth."""
    if "base" not in fields or "last24" not in fields:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    at = fields.get("at")
    if isinstance(at, bool) or not isinstance(at, int) or at <= 0:
        raise ValueError("the snow report does not say when it was written")
    written = datetime.fromtimestamp(at / 1000, tz=timezone.utc)
    base = {"Name": "Base", "BaseIn": inches(fields, "base")}
    base.update({ours: inches(fields, theirs) for theirs, ours in SNOWFALL.items()})
    surface = [str(fields[field]).strip() for field in ("primary", "secondary") if str(fields.get(field) or "").strip()]
    return {"LastUpdate": written.strftime(STAMP), "Resortwide": True, "BaseConditions": ", ".join(surface) or None,
            "SeasonTotalIn": inches(fields, "ytd"), "BaseArea": base,
            "SummitArea": {"Name": "Summit", "BaseIn": inches(fields, "summit")}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": mountain_areas(document(pages["trails"], "trailstatus"))}
    try:
        feed["SnowReport"] = snow_report(document(pages["snow"], "snowreport"))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
