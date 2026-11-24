"""Snowbasin's lifts and trails, and its snow report, from its mountain report page
(snowbasin.com/the-mountain/mountain-report).

The page is built on the server: one table of lifts, and a table of trails for each part of the mountain (its
access gates, John Paul, Needles, Porcupine, Strawberry and the terrain parks), each under a heading. A lift's or
trail's status is the symbol in its row (open, closed, hold, scheduled, delayed, expected), read from the symbol's
name, and a symbol the reader does not know fails. A trail's first symbol is its difficulty and a groomed mark is
carried as its grooming. The page's own count of lifts is checked against what is read, so a change in its shape
fails instead of showing wrong numbers; its count of trails leaves out the gates and parks, so the list is only
required to hold at least that many.

The snow report gives the base depth, the overnight, 24 hour and 7 day snowfall and the season's total as whole
inches, under a line saying when it was posted in Mountain time without a year; the year is the latest one that
does not put the report after the time of reading. The page gives no word for the surface. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.snowbasin.com/the-mountain/mountain-report/"
NAME = "Snowbasin"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The page's status symbols, in the words of its own key.
STATUSES = {"open": "Open", "closed": "Closed", "hold": "On hold", "scheduled": "Scheduled", "delayed": "Delayed",
            "expected": "Expected"}
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"easy": "Green", "moderate": "Blue", "difficult": "Black", "most-difficult": "Double black",
          "terrain-park": ""}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Overnight": "OvernightIn", "Base": "BaseIn", "24 hours": "Last24HoursIn", "7 days": "Last7DaysIn",
            "Season": "SeasonTotalIn"}
LIFT_TABLE = re.compile(r"<table class=\"mc__table mc-lifts__table\">(.*?)</table>", re.S)
# In the trails part of the page: a heading over a part of the mountain, or a table of trails.
HEADING_OR_TABLE = re.compile(r"class=\"accordion__toggle js-accordion__toggle[^\"]*\">\s*([^<]*?)\s*<"
                              r"|<table class=\"mc__table mc-trails__table[^\"]*\">(.*?)</table>", re.S)
BODY = re.compile(r"<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
SYMBOL = re.compile(r"class=\"mc__icon mc__icon-([a-z-]+)\"")
TAG = re.compile(r"<[^>]+>")
COUNTED = r"<span class=\"mc-lifts__graph-value\">\s*(\d+)\s*/\s*(\d+)\s*</span>\s*{kind} Open"
SNOW_REPORT = re.compile(r"<h2 class=\"mc__heading mc__h2\">Snow Report</h2>(.*?)<h2", re.S)
FIGURE = re.compile(r"<h3 class=\"mc__heading mc__h3\">\s*([^<]*?)\s*</h3>\s*<p class=\"mc__num mc__num-lg\">\s*"
                    r"([^<]*?)\s*</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")")
POSTED = re.compile(r"class=\"mc__timestamp mc__timestamp-light\">\s*Last Updated:?\s*([A-Z][a-z]{2}) (\d{1,2}),?\s*"
                    r"(\d{1,2}):(\d{2}) ([AP]M) MT\s*<")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, cell: str, difficulty: str | None) -> dict:
    """One lift or trail: its status is the one symbol in its status cell."""
    symbols = SYMBOL.findall(cell)
    if not name or len(symbols) != 1 or symbols[0] not in STATUSES:
        raise ValueError(f"{name or 'a row'} has status symbols {symbols}, not one the reader knows")
    status = STATUSES[symbols[0]]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def rows_of(table: str) -> list:
    """The cells of each row of a table's body."""
    body = BODY.search(table)
    if not body:
        raise ValueError("a table has no body")
    return [CELL.findall(row) for row in ROW.findall(body.group(1))]


def lift_rows(page: str) -> list:
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the table of lifts was not found")
    rows = rows_of(table.group(1))
    if any(len(cells) != 4 for cells in rows):
        raise ValueError("a row of the lift table is not a name, a type, a status and hours")
    return [status_row(words(cells[0]), cells[2], None) for cells in rows]


def trail_row(cells: list) -> dict:
    if len(cells) < 2:
        raise ValueError("a row of a trail table has no status")
    name, levels = words(cells[0]), SYMBOL.findall(cells[0])
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name or 'a trail'} has difficulty symbols {levels}, not one the reader knows")
    row = status_row(name, cells[1], LEVELS[levels[0]])
    row["Grooming"] = "Yes" if any("mc__icon-groomed" in cell for cell in cells[2:]) else "No"
    return row


def trail_areas(page: str) -> list:
    """The trails of each part of the mountain, in the page's order."""
    start = page.find("<div class=\"mc-trails\">")
    if start < 0:
        raise ValueError("the trails part of the page was not found")
    areas, heading = [], None
    for found in HEADING_OR_TABLE.finditer(page, start):
        if found.group(2) is None:
            heading = html.unescape(found.group(1))
            continue
        if not heading:
            raise ValueError("a table of trails has no heading")
        areas.append({"Name": heading, "Lifts": [], "Trails": [trail_row(cells) for cells in rows_of(found.group(2))]})
        heading = None
    return [area for area in areas if area["Trails"]]


def counted(page: str, kind: str) -> int:
    """The page's own count of all its lifts or trails."""
    found = re.search(COUNTED.format(kind=kind), page)
    if not found:
        raise ValueError(f"the page's count of {kind.lower()} was not found")
    return int(found.group(2))


def posted(block: str, now: datetime) -> str:
    """When the snow report was posted, in UTC. The page gives no year: it is the latest that does not put the
    report more than a day after the time of reading."""
    found = POSTED.findall(block)
    if not found:
        raise ValueError("the snow report does not say when it was posted")
    month, day, hour, minute, half = found[-1]
    for year in (now.year, now.year - 1):
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
        at = at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc)
        if at <= now + timedelta(days=1):
            return at.strftime(STAMP)
    raise ValueError(f"the snow report's date {month} {day} could not be placed")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    figures = {}
    for heading, said in FIGURE.findall(block.group(1)):
        if heading not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {heading}")
        inches = INCHES.fullmatch(html.unescape(said))
        if not inches:
            raise ValueError(f"the snow report's {heading} reads {said!r}, not inches")
        value = float(inches.group(1))
        figures[SNOWFALL[heading]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": posted(page[:block.start()], now), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = lift_rows(page), trail_areas(page)
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    if counted(page, "Lifts") != len(lifts):
        raise ValueError(f"the page counts {counted(page, 'Lifts')} lifts but {len(lifts)} were read")
    trails = sum(len(area["Trails"]) for area in areas)
    if trails < counted(page, "Trails"):
        raise ValueError(f"the page counts {counted(page, 'Trails')} trails but only {trails} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
