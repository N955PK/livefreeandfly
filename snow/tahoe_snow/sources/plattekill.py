"""Plattekill's lifts and trails, and its snow report, from its conditions page (plattekill.com/on-the-trail).

The page is built on the server. Its trail report is one table the mountain fills in by hand, in parts under
headings: the trails under their difficulty (Easiest, More Difficult, Most Difficult, Experts Only), each a name,
a status and a surface condition; then the lifts, each a name and a status; then the snow. A status is a word in
capitals ("OPEN", "CLOSED") and is carried with one capital. The surface is the page's own letters ("MG" for
machine groomed, "PP" for packed powder, dashes for nothing), and a trail whose letters include "MG" is carried as
groomed. The terrain park is a row among the hardest trails, named in capitals, and is set apart as an area of its
own, with no difficulty. The page does not divide the mountain into parts, so the lifts and trails are one area.
Every row under those headings has to read, and a heading the reader does not know fails, so a change in the
page's shape fails instead of showing wrong numbers.

The snow part of the table gives the natural snow of the last 24 hours and the least and the most base depth,
each "N/A" when the mountain gives none; the page's heading gives the season's snow, and the last 24 hours again,
which is used where the table has none. The report is for a day, written at the top of the page, and is read as
noon of that day in Eastern time. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://plattekill.com/on-the-trail/"
NAME = "Plattekill"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/New_York")
# The table's headings over its trails, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easiest": "Green", "more difficult": "Blue", "most difficult": "Black", "experts only": "Double black"}
LIFTS, SNOW, END = "lifts", "snow", "trail report"
PARK = "terrain park"
GROOMED = "MG"
TABLE = re.compile(r"<table\b[^>]*>\s*<thead>(.*?)</thead>(.*?)</table>", re.S)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S)
HEADING = re.compile(r"<h3\b[^>]*>(.*?)</h3>", re.S)
REPORTED = re.compile(r"Report for:\s*(\d{1,2}/\d{1,2}/\d{4})")
STAT = re.compile(r"<span class=\"alt snowStat\">(.*?)</span>\s*<p class=\"statLabel alt\">(.*?)</p>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\"|in\.?|inches)?", re.I)
NONE = re.compile(r"(?:n/a|-*)", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def parts_of(page: str) -> dict:
    """The trail report's rows, as lists of cells, under each of its headings (in small letters)."""
    for head, body in TABLE.findall(page):
        if "Surface Condition" in words(head):
            break
    else:
        raise ValueError("the trail report's table was not found")
    parts, heading = {}, None
    for row in ROW.findall(body):
        found = HEADING.search(row)
        if found:
            heading = words(found.group(1)).lower()
            if heading in parts:
                raise ValueError(f"the trail report has two parts headed {heading!r}")
            parts[heading] = []
            continue
        if heading is None:
            raise ValueError("the trail report has a row under no heading")
        parts[heading].append([words(cell) for cell in CELL.findall(row)])
    return parts


def status_row(cells: list, difficulty: str | None) -> dict:
    if len(cells) < 2 or not cells[0] or not cells[1]:
        raise ValueError(f"a row of the trail report is not a name and a status: {cells}")
    said = cells[1].capitalize()
    return {"Name": cells[0], "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(cells: list, difficulty: str) -> dict:
    if len(cells) != 3:
        raise ValueError(f"a trail's row is not a name, a status and a surface: {cells}")
    letters = re.findall(r"[A-Za-z]+", cells[2])
    return {**status_row(cells, difficulty), "Grooming": "Yes" if GROOMED in letters else "No"}


def inches(said: str, label: str) -> float | int | None:
    """A depth in inches, or None where the mountain gives none ("N/A", dashes, nothing)."""
    if NONE.fullmatch(said):
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str, rows: list | None) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    reported = REPORTED.search(page)
    if not reported:
        raise ValueError("the page does not say which day its report is for")
    try:
        at = datetime.strptime(reported.group(1), "%m/%d/%Y").replace(hour=12, tzinfo=LOCAL_TIME)
    except ValueError as error:
        raise ValueError(f"the report's day could not be read: {error}") from error
    said = {row[0].lower().rstrip(":"): row[1] for row in rows or [] if len(row) == 2}
    labels = ("new natural snow last 24 hours", "base depth, minimum", "base depth, maximum")
    missing = [label for label in labels if label not in said]
    if missing:
        raise ValueError(f"the snow report has no line for {missing}")
    new, low, high = (inches(said[label], label) for label in labels)
    stats = {words(label).lower(): words(figure) for figure, label in STAT.findall(page)}
    if new is None and "last 24 hours" in stats:
        new = inches(stats["last 24 hours"], "last 24 hours")
    if low is not None and high is not None and low > high:
        raise ValueError(f"the base depth runs from {low} down to {high}")
    area = {"Name": "Mountain", "BaseIn": low if low == high else None, "BaseMinIn": low, "BaseMaxIn": high,
            "Last24HoursIn": new}
    if (low is None) != (high is None):
        # Only one end of the depth is given: it is the depth.
        area.update({"BaseIn": low if high is None else high, "BaseMinIn": None, "BaseMaxIn": None})
    season = inches(stats["season snow"], "season snow") if "season snow" in stats else None
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    parts = parts_of(page)
    unknown = [heading for heading in parts if heading not in (*LEVELS, LIFTS, SNOW, END)]
    if unknown:
        raise ValueError(f"the trail report has parts the reader does not know: {unknown}")
    lifts, trails, parks = [status_row(cells, None) for cells in parts.get(LIFTS, [])], [], []
    for heading, difficulty in LEVELS.items():
        for cells in parts.get(heading, []):
            if cells and cells[0].lower().startswith(PARK):
                parks.append({**trail_row(cells, ""), "Name": cells[0].title() if cells[0].isupper() else cells[0]})
            else:
                trails.append(trail_row(cells, difficulty))
    if not lifts or not trails:
        raise ValueError("the trail report lists no lifts or no trails")
    areas = [{"Name": NAME, "Lifts": lifts, "Trails": trails}]
    if parks:
        areas.append({"Name": "Terrain Parks", "Lifts": [], "Trails": parks})
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page, parts.get(SNOW))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
