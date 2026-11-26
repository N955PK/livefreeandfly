"""Telluride's lifts and trails, and its snow report, from its snow report page (tellurideskiresort.com/snow-report).

The page is built on the server. Its lift table gives each lift a status picture (open, on hold or closed), its name,
its part of the mountain and its hours. Its trail list is a heading for each lift over the trails it serves, and a
heading of its own for a lift's hike-to terrain; each heading is a mountain area here, holding the lift of that name
and its trails, and a lift with no trails under it is an area of its own. A trail says in its own attributes whether
it is closed, on hold and groomed, and how hard it is, and a value the reader does not know fails. The page's own
count of lifts, and of lifts open, is checked against what is read, so a change in the page's shape fails instead
of showing wrong numbers. (Its count of trails is of fewer trails than it lists, so that is not checked.)

The snow report gives one snow depth, the snow overnight and of the last 24 and 48 hours and 7 days, the season's
total and a word for the surface, under a line saying when it was last updated, in Mountain time. A snow report that
cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://tellurideskiresort.com/snow-report/"
NAME = "Telluride"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The status pictures, in the words of the page's own key.
STATUSES = {"open": "Open", "hold": "On hold", "closed": "Closed"}
# The page's six difficulties, in the words the app's difficulty symbols are keyed on.
LEVELS = {"novice": "Green", "advanced_novice": "Green", "intermediate": "Blue", "advanced_intermediate": "Blue",
          "expert": "Black", "extreme": "Double black"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Snow depth": "BaseIn", "Season total": "SeasonTotalIn", "Snow overnight": "OvernightIn",
            "Last 24 hours": "Last24HoursIn", "Last 48 hours": "Last48HoursIn", "Last 7 days": "Last7DaysIn"}
LIFT_TABLE = re.compile(r"<table id=\"tsr-report-app-lift-table\">.*?<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PICTURE = re.compile(r"class=\"tsr-report-app-icon-(open|hold|closed)\"")
LIFTS_COUNTED = re.compile(r"<span>\s*(\d+)\s*<span>\s*/\s*(\d+)\s*</span>\s*<p>\s*lifts open\s*</p>")
TRAIL_LIST = re.compile(r"<div class=\"tsr-report-app-trail-list\">(.*?)<div class=\"tsr-report-app-weather", re.S)
HEADING = re.compile(r"<div class=\"tsr-report-app-trail-list-lift\">\s*<h4>(.*?)</h4>", re.S)
TRAIL = re.compile(r"<p\s+class=\"tsr-report-app-trail-list-trail\"([^>]*)>\s*<span[^>]*></span>\s*<span>(.*?)</span>",
                   re.S)
ATTRIBUTE = re.compile(r"data-([a-z]+)=\"([^\"]*)\"")
TAG = re.compile(r"<[^>]+>")
FIGURE = re.compile(r"<span>\s*([A-Za-z0-9 ]+?)\s*</span>\s*<span>\s*<strong>\s*([^<]*?)\s*</strong>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|″|”)")
SURFACE = re.compile(r"Current snow condition\s*</strong>\s*</span>\s*<br\s*/?>\s*<span>\s*([^<]*?)\s*</span>")
UPDATED = re.compile(r"Last Updated:\s*([A-Z][a-z]+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2}\s*[ap]m)")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_rows(page: str) -> list:
    """The lifts of the page's lift table, in its order."""
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the lift table was not found")
    lifts = []
    for row in ROW.findall(table.group(1)):
        cells = CELL.findall(row)
        if len(cells) != 4:
            raise ValueError("a row of the lift table is not a status, a name, an area and its hours")
        name, pictures = words(cells[1]), PICTURE.findall(cells[0])
        if not name or len(pictures) != 1:
            raise ValueError(f"the lift {name!r} has status pictures {pictures}, not one the reader knows")
        status = STATUSES[pictures[0]]
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    if not lifts:
        raise ValueError("the page lists no lifts")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    counted = LIFTS_COUNTED.search(page)
    if not counted:
        raise ValueError("the page's count of lifts was not found")
    turning = sum(lift["StatusEnglish"] == "open" for lift in lifts)
    if (int(counted.group(1)), int(counted.group(2))) != (turning, len(lifts)):
        raise ValueError(f"the page counts {counted.group(1)} of {counted.group(2)} lifts open "
                         f"but {turning} of {len(lifts)} were read")
    return lifts


def trail_row(attributes: str, name: str) -> dict:
    said = dict(ATTRIBUTE.findall(attributes))
    if not name:
        raise ValueError("the page lists a trail with no name")
    if said.get("level") not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {said.get('level')}")
    if any(said.get(field) not in ("0", "1") for field in ("closed", "hold", "groomed")):
        raise ValueError(f"{name} does not say whether it is closed, on hold and groomed")
    status = "Closed" if said["closed"] == "1" else "On hold" if said["hold"] == "1" else "Open"
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": LEVELS[said["level"]],
            "Grooming": "Yes" if said["groomed"] == "1" else "No"}


def trail_areas(page: str) -> list:
    """Each heading of the trail list with the trails under it, in the page's order."""
    listed = TRAIL_LIST.search(page)
    if not listed:
        raise ValueError("the trail list was not found")
    headings = list(HEADING.finditer(listed.group(1)))
    areas = []
    for at, heading in enumerate(headings):
        end = headings[at + 1].start() if at + 1 < len(headings) else len(listed.group(1))
        trails = [trail_row(attributes, words(name))
                  for attributes, name in TRAIL.findall(listed.group(1)[heading.end():end])]
        areas.append({"Name": words(heading.group(1)), "Lifts": [], "Trails": trails})
    if not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no trails")
    if listed.group(1).count("tsr-report-app-trail-list-trail\"") != sum(len(area["Trails"]) for area in areas):
        raise ValueError("a trail of the trail list is not in the shape expected")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated = UPDATED.search(words(page))
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    try:
        at = datetime.strptime(f"{updated.group(1)} {updated.group(2).replace(' ', '')}", "%B %d, %Y %I:%M%p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    figures = {}
    for label, said in FIGURE.findall(page):
        if label not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(html.unescape(said))
        if not inches or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label} reads {said!r}, not inches given once")
        value = float(inches.group(1))
        figures[SNOWFALL[label]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no snow depth or no 24 hour snowfall")
    season, surface = figures.pop("SeasonTotalIn", None), SURFACE.search(page)
    return {"LastUpdate": at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": html.unescape(surface.group(1)) or None if surface else None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = lift_rows(page), trail_areas(page)
    by_name = {area["Name"]: area for area in areas}
    for lift in lifts:
        # A lift with no trails listed under it (the gondola from town, a carpet) is an area of its own.
        if lift["Name"] not in by_name:
            areas.append({"Name": lift["Name"], "Lifts": [], "Trails": []})
            by_name[lift["Name"]] = areas[-1]
        by_name[lift["Name"]]["Lifts"].append(lift)
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
