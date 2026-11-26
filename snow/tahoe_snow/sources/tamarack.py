"""Tamarack's lifts and trails, and its snow report, from its snow report page
(tamarackidaho.com/the-mountain/snow-report).

The page is built on the server. Its "Chair Lifts Status" is a table of the lifts, each with its status in words,
carried as the page says it. Its "Trails Status" is two tables, the downhill trails and the terrain parks, each row
a name, a difficulty and a status in words. The lifts are a mountain area here, named for the resort, and each of
the two tables of trails is an area after it. A difficulty the reader does not know fails; a terrain park has none.
The page's table of uphill routes is not lifts and is not read. Every row of the three tables is one read, so a
change in the page's shape fails instead of showing wrong numbers. The page's own counts of open lifts and runs are
not used: they are written at another time than the tables. The page says nothing of grooming.

The snow report is the row of figures at the top of the page: at the summit and at mid-mountain, the depth, the
snowfall of the last 24 and 48 hours and the last storm's total, and the season's snow at 7,700 feet, in inches,
with the day and time they were last updated, in Boise's time. It gives no word for the surface. A snow report that
cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://tamarackidaho.com/the-mountain/snow-report"
NAME = "Tamarack"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Boise")
# The trail tables' difficulties, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black",
          "terrain park": ""}
# The two tables of trails, by the name of the tab each is under.
PANELS = {"downhill": "Downhill Trails", "parks": "Terrain Parks"}
# The figures at the top of the page, as (the stake, the name the Ikon feed gives the figure).
FIGURES = {"24 HRS Summit": ("SummitArea", "Last24HoursIn"), "48 HRS Summit": ("SummitArea", "Last48HoursIn"),
           "Last Storm Total Summit": ("SummitArea", "StormTotalIn"), "Summit Base Depth": ("SummitArea", "BaseIn"),
           "24 HRS Mid": ("MidMountainArea", "Last24HoursIn"), "48 HRS Mid": ("MidMountainArea", "Last48HoursIn"),
           "Last Storm Total Mid": ("MidMountainArea", "StormTotalIn"), "Mid Base Depth": ("MidMountainArea", "BaseIn")}
LIFT_TABLE = re.compile(r"<table class=\"sr-table sr-table--lifts[^\"]*\">\s*<thead>\s*<tr>\s*"
                        r"<th scope=\"col\">Lifts</th>.*?<tbody>(.*?)</tbody>", re.S)
PANEL = re.compile(r"<div class=\"sr-tab-panel\"[^>]*\bid=\"sr-panel-([a-z-]+)\"[^>]*>\s*"
                   r"<table class=\"sr-table sr-table--trails[^\"]*\">.*?<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
LIFT_NAME = re.compile(r"<th scope=\"row\">(.*?)</th>", re.S)
TRAIL_NAME = re.compile(r"<span class=\"sr-trail__name\">(.*?)</span>", re.S)
CELL = re.compile(r"<td data-label=\"([^\"]*)\">(.*?)</td>", re.S)
SNOW_STATS = re.compile(r"<ul class=\"sr-stats sr-stats--snow\">(.*?)</ul>", re.S)
STAT = re.compile(r"<span class=\"sr-stat__value\">(.*?)</span>\s*<span class=\"sr-stat__label\">(.*?)</span>", re.S)
TOTAL = re.compile(r"<span class=\"sr-summary__total-value\">(.*?)</span>\s*"
                   r"<span class=\"sr-summary__total-label\">\s*Total Snow\b", re.S)
UPDATED = re.compile(r"<p class=\"sr-summary__updated\">\s*Last update: (\d{1,2}) ([A-Z][a-z]{2}) (\d{4}) at "
                     r"(\d{1,2}):(\d{2}) ([AP]M)\s*</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    said = status.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def cells_of(row: str) -> dict:
    """A row's cells by their labels, in words."""
    return {label: words(body) for label, body in CELL.findall(row)}


def lift_rows(page: str) -> list:
    """The lifts of the table of lifts, in the page's order."""
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the table of lifts was not found")
    rows = []
    for row in ROW.findall(table.group(1)):
        name, cells = LIFT_NAME.search(row), cells_of(row)
        if not name or not words(name.group(1)) or not cells.get("Status"):
            raise ValueError("a row of the table of lifts has no name or no status")
        rows.append(status_row(words(name.group(1)), cells["Status"], None))
    if not rows:
        raise ValueError("the table of lifts lists no lifts")
    if len({row["Name"] for row in rows}) != len(rows):
        raise ValueError("the page lists a lift twice")
    return rows


def trail_areas(page: str) -> list:
    """Each table of trails with its trails, in the page's order."""
    areas, read = [], 0
    for panel, body in PANEL.findall(page):
        if panel not in PANELS:
            raise ValueError(f"the page has a table of trails the reader does not know: {panel}")
        trails = []
        for row in ROW.findall(body):
            name, cells = TRAIL_NAME.search(row), cells_of(row)
            if not name or not words(name.group(1)) or not cells.get("Status") or "Difficulty" not in cells:
                raise ValueError("a row of a table of trails is not a name, a difficulty and a status")
            if cells["Difficulty"].lower() not in LEVELS:
                raise ValueError(f"{words(name.group(1))} has a difficulty the reader does not know: "
                                 f"{cells['Difficulty']}")
            trails.append(status_row(words(name.group(1)), cells["Status"], LEVELS[cells["Difficulty"].lower()]))
        read += len(trails)
        areas.append({"Name": PANELS[panel], "Lifts": [], "Trails": trails})
    listed = page.count("<span class=\"sr-trail__name\">")
    if not read or read != listed:
        raise ValueError(f"the page has {listed} trail rows but {read} were read")
    return areas


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(html.unescape(said).strip())
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The figures at the top of the page in the shape of the Ikon feed's SnowReport: mid-mountain and the summit."""
    stats, updated = SNOW_STATS.search(page), UPDATED.search(page)
    if not stats or not updated:
        raise ValueError("the snow figures or the time they were updated were not found")
    day, month, year, hour, minute, half = updated.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    out = {"MidMountainArea": {"Name": "Mid-Mountain"}, "SummitArea": {"Name": "Summit"}}
    seen = set()
    for said, label in STAT.findall(stats.group(1)):
        label = words(label)
        if label not in FIGURES or label in seen:
            raise ValueError(f"the snow report has a figure the reader does not know, or has it twice: {label}")
        seen.add(label)
        area, field = FIGURES[label]
        out[area][field] = inches(said, label)
    if seen != set(FIGURES):
        raise ValueError(f"the snow report is missing {sorted(set(FIGURES) - seen)}")
    total = TOTAL.search(page)
    return {"LastUpdate": at.replace(tzinfo=LOCAL_TIME).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": inches(total.group(1), "season total") if total else None,
            **out, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    areas = [{"Name": NAME, "Lifts": lift_rows(page), "Trails": []}] + trail_areas(page)
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
