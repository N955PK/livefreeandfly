"""Saddleback's lifts and trails, and its snow report, from the report its own mountain-report page reads.

Saddleback's mountain-report page (saddlebackmaine.com/mountain-report/) fills its lift and trail tables in the
browser from one report of the resort's own (saddlebackapi.netlify.app/.netlify/functions/getAll), and carries the
day's report in the resort's own words in the page itself, so two things are read: the report ("status") and the
page ("snow"). A scheduled job reads them and writes one small file the page reads, in the shape of the Ikon feed
the rest of the page uses. The report sorts the trails by difficulty, with the terrain parks and the uphill routes
in lists of their own; the uphill routes are left out (the status is of the lift-served mountain), and so are the
two entries that are not trails but carry the day's surface (PRIMARY SURFACE, SECONDARY SURFACE). A status is read
as the resort's page reads it: OPEN is open, FORECAST is expected to open, STOPPED is on hold, and anything else
(CLOSED, or OUT_OF_PERIOD outside the season) is closed. The report's own count of lifts is checked against what is
read, and a list of trails the page does not know fails, so a change in its shape fails instead of showing wrong
numbers.

The snow report is in the shape of the Ikon feed's snow report: the base depth, the snowfall over 24, 48 and 72
hours and 7 days, the season's total and the surface from the report, and the day's words from the page, stamped
with the day and time the page gives them (Eastern). The report keeps last season's snow figures all summer, and
the resort's page hides them then, so figures last changed more than a week ago are left empty; they are in inches,
and a figure in any other unit fails. With no words and no fresh figures there is no snow report. Standard library
only.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"status": "https://saddlebackapi.netlify.app/.netlify/functions/getAll",
        "snow": "https://www.saddlebackmaine.com/mountain-report/"}
EASTERN = ZoneInfo("America/New_York")
# The report's lists of trails, by the headings the resort's page gives them.
GROUPS = {"greenCircle": "Easier", "blueSquare": "More Difficult", "blackDiamond": "Most Difficult",
          "doubleBlackDiamond": "Experts Only", "terrainParks": "Terrain Parks"}
NOT_SKIED = {"uphill"}
# The report's trail levels, in the words the page's difficulty symbols are keyed on.
LEVELS = {"GREEN_CIRCLE": "Green", "BLUE_SQUARE": "Blue", "BLACK_DIAMOND": "Black", "DOUBLE_BLACK_DIAMOND": "Double black"}
STATUSES = {"OPEN": "Open", "FORECAST": "Expected", "STOPPED": "On hold"}
# Entries among the trails that are not trails: their snow quality is the day's surface.
SURFACE_ROWS = ("PRIMARY SURFACE", "SECONDARY SURFACE")
# The report's surfaces, in the words the resort's page gives them.
SURFACES = {"SNOW_GROOMED": "Machine Groomed", "POWDER": "Powder", "PACKED_POWDER": "Packed Powder", "FRESH": "Fresh",
            "HARD_PACKED": "Hard Packed", "EARLY_SEASON": "Early Season Conditions", "CRUSTED": "Crusty",
            "DRIFTED": "Windblown", "SPRING": "Spring Conditions", "WET_SNOW": "Wet Snow", "GRADIENT": "Loose Granular",
            "FROZEN": "Icy", "ARTIFICIAL": "Snowmaking", "LOW_SNOWFALL": "No Snow", "VARIABLE": "Variable Conditions"}
# The report's snowfall figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"freshSnowFallDepth24H": "Last24HoursIn", "freshSnowFallDepth48H": "Last48HoursIn",
            "freshSnowFallDepth72H": "Last72HoursIn", "freshSnowFallDepth7D": "Last7DaysIn"}
FRESH = timedelta(days=7)
WORDS = re.compile(r"<div class=\"daily-report__body\">(.*?)</div>", re.S)
WORDS_DAY = re.compile(r"<h3>\s*(?:[A-Z][a-z]+day,\s*)?([A-Z][a-z]+ \d{1,2}, \d{4})\s*</h3>")
WORDS_TIME = re.compile(r"<p>\s*<strong>\s*(\d{1,2}):(\d{2})\s*([ap])m\s*</strong>\s*</p>", re.I)


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = STATUSES.get(status, "Closed")
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    row = status_row(trail["name"], trail["openingStatus"], LEVELS.get(trail.get("trailLevel") or "", ""))
    row["Grooming"] = "Yes" if trail.get("groomingStatus") == "GROOMED" else "No"
    return row


def inches(figure, value: str = "value", unit: str = "unit") -> float | int | None:
    """A depth the report gives as {"value": 30, "unit": "INCH"}; None where it gives nothing."""
    said = figure.get(value) if isinstance(figure, dict) else None
    if said is None:
        return None
    if figure.get(unit) != "INCH":
        raise ValueError(f"a snow figure is in {figure.get(unit)}, not inches")
    said = float(said)
    return int(said) if said.is_integer() else said


def words_of(page: str | None) -> tuple:
    """The day's report from the resort's page: when it was posted, and its paragraphs as the page has them. The
    page heads them with the day and, in a line of its own, the time; a day with no time is stamped at noon."""
    body = WORDS.search(page or "")
    day = WORDS_DAY.search(body.group(1)) if body else None
    if not day:
        return None, None
    posted = datetime.strptime(day.group(1), "%B %d, %Y").replace(hour=12, tzinfo=EASTERN)
    said = body.group(1)[day.end():]
    clock = WORDS_TIME.match(said.lstrip())
    if clock:
        hour = int(clock.group(1)) % 12 + (12 if clock.group(3).lower() == "p" else 0)
        posted, said = posted.replace(hour=hour, minute=int(clock.group(2))), said.lstrip()[clock.end():]
    return posted, said.strip() or None


def snow_report(report: dict, page: str | None, now: datetime) -> dict | None:
    """The report's snow figures and the page's words in the shape of the Ikon feed's SnowReport, for the whole
    mountain. Figures last changed more than a week before ``now`` are last season's and are left empty."""
    snow = report.get("snow") or {}
    changed = datetime.fromisoformat(snow["lastModified"]) if snow.get("lastModified") else None
    fresh = changed is not None and now - changed <= FRESH
    posted, words = words_of(page)
    if not fresh and not posted:
        return None
    area = {"Name": "Mountain", "BaseIn": inches(snow.get("snowTotalDepth")) if fresh else None}
    area.update({ikon: inches(snow.get(field)) if fresh else None for field, ikon in SNOWFALL.items()})
    marks = {trail["name"]: trail.get("snowQuality") for trails in (report.get("trailsSorted") or {}).values()
             for trail in trails if trail["name"] in SURFACE_ROWS}
    surface = ", ".join(dict.fromkeys(SURFACES[marks[name]] for name in SURFACE_ROWS if marks.get(name) in SURFACES))
    return {"LastUpdate": (posted or changed).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Resortwide": True, "BaseConditions": (surface or None) if fresh else None,
            "SeasonTotalIn": inches(snow.get("snowFallDepthCompleteSeason"), "countryValue", "countryUnit") if fresh else None,
            "BaseArea": area, "Report": words, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    """``pages`` holds the report's text under "status" and the resort's page under "snow"; without the page the
    snow report has no words."""
    report = json.loads(pages["status"]).get("data")
    if not isinstance(report, dict) or not isinstance(report.get("lifts"), dict):
        raise ValueError("the report's lifts were not found")
    lifts = [status_row(lift["name"], lift["openingStatus"], None) for lift in report["lifts"].values()]
    if not lifts:
        raise ValueError("the report lists no lifts")
    listed = report["liftStatus"]["totalLifts"]
    if len(lifts) != listed:
        raise ValueError(f"the report counts {listed} lifts but {len(lifts)} were read")
    unknown = set(report["trailsSorted"]) - set(GROUPS) - NOT_SKIED
    if unknown:
        raise ValueError(f"the report has trails the page does not list: {', '.join(sorted(unknown))}")
    areas = [{"Name": name, "Lifts": [],
              "Trails": [trail_row(trail) for trail in report["trailsSorted"].get(group) or []
                         if trail["name"] not in SURFACE_ROWS]} for group, name in GROUPS.items()]
    areas = [area for area in areas if area["Trails"]]
    if not areas:
        raise ValueError("the report lists no trails")
    feed = {"Name": "Saddleback", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Saddleback", "Lifts": lifts, "Trails": []}, *areas]}
    snow = snow_report(report, pages.get("snow"), now)
    if snow:
        feed["SnowReport"] = snow
    return feed
