"""Loveland's lifts and trails, and its snow report, from its trail and lift report and its snow report pages
(skiloveland.com/trail-lift-report and skiloveland.com/snow-report).

Both pages are built on the server. The trail and lift report is a heading for each lift, "Chet's Dream - OPEN",
over a table of the trails it serves; each lift is a mountain area here, holding itself and its trails. A lift's
status is the word after the dash in its heading, carried as the page says it. A trail's status and difficulty are
the pictures in its row, read from the pictures' names, and one the reader does not know fails; a grooming picture
is carried as its grooming. A trail the page lists again under a second lift is kept only under the first, so no
trail is counted twice. The page's table of lift elevations names its chairlifts: every one of them has to be among
the lifts read, and the snow report's own count of lifts has to match, so a change in the page's shape fails
instead of showing wrong numbers. The page says of itself that it is not updated for the day's holds and closures.

The snow report gives the depth at mid-mountain, the 24, 48 and 72 hour snowfall and the season's total in inches,
under a heading saying when it was written, in Mountain time. It gives no word for the surface. A snow report that
cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://skiloveland.com/trail-lift-report/", "snow": "https://skiloveland.com/snow-report/"}
NAME = "Loveland"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The pictures' names, in the words of the page's own key.
STATUSES = {"icon_open": "Open", "icon_closed": "Closed"}
# The difficulty pictures, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"icon_beginner": "Green", "icon_more_difficult": "Blue", "icon_most_difficult": "Black",
          "icon_expert": "Double black", "icon_terrainpark": ""}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 HOUR": "Last24HoursIn", "48 HOUR": "Last48HoursIn", "72 HOUR": "Last72HoursIn",
            "TOTAL": "SeasonTotalIn", "MID-MTN": "BaseIn"}
LIFT = re.compile(r"<h2 id=\"tablepress-(\d+)-name\" class=\"tablepress-table-name[^\"]*\">(.*?)</h2>\s*"
                  r"<table id=\"tablepress-\1\"[^>]*>(.*?)</table>", re.S)
HEADING = re.compile(r"(.*\S)\s*-\s*([A-Za-z][A-Za-z ]*)")
ELEVATIONS = re.compile(r"<table id=\"tablepress-\d+\"[^>]*>\s*<thead>(?:(?!</thead>).)*BOTTOM.*?</thead>(.*?)</table>",
                        re.S)
BODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PICTURE = re.compile(r"<img[^>]*\ssrc=\"[^\"]*/([^\"/]+)\.png\"")
TAG = re.compile(r"<[^>]+>")
FIGURE = re.compile(r"<h1>\s*<span[^>]*>\s*([^<]*?)\s*</span>\s*</h1>\s*<h5>\s*<strong>\s*([^<]*?)\s*</strong>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")")
WRITTEN = re.compile(r"<h2>\s*(\d{1,2}):(\d{2}) ([AP]M) REPORT\s*(?:&#8211;|–|-)\s*([A-Z][a-z]+) (\d{1,2}), (\d{4})\s*</h2>")
LIFTS_COUNTED = re.compile(r"of (\d+) LIFTS")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def rows_of(table: str) -> list:
    """The cells of each row of a table's body."""
    body = BODY.search(table)
    if not body:
        raise ValueError("a table has no body")
    return [CELL.findall(row) for row in ROW.findall(body.group(1))]


def one_picture(cell: str, known: dict, what: str, name: str) -> str:
    pictures = PICTURE.findall(cell)
    if len(pictures) != 1 or pictures[0] not in known:
        raise ValueError(f"{name} has {what} pictures {pictures}, not one the reader knows")
    return known[pictures[0]]


def trail_row(cells: list) -> dict | None:
    """One trail, or None for one of the page's empty rows."""
    if len(cells) != 5:
        raise ValueError("a row of a trail table is not a difficulty, a status, a name, a grooming and a location")
    name = words(cells[2])
    if not name:
        if any(words(cell) or PICTURE.search(cell) for cell in cells):
            raise ValueError("a row of a trail table has no name")
        return None
    status = one_picture(cells[1], STATUSES, "status", name)
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(),
           "Difficulty": one_picture(cells[0], LEVELS, "difficulty", name)}
    row["Grooming"] = "Yes" if "grooming" in PICTURE.findall(cells[3]) else "No"
    return row


def chairlifts(page: str) -> list:
    """The lifts the page's table of elevations names, as it writes them."""
    table = ELEVATIONS.search(page)
    if not table:
        raise ValueError("the table of lift elevations was not found")
    names = [words(cells[0]) for cells in rows_of(table.group(1)) if cells and words(cells[0])]
    if not names:
        raise ValueError("the table of lift elevations names no lifts")
    return names


def lift_areas(page: str) -> list:
    """Each lift with the trails under it, in the page's order."""
    written = {name.lower(): name for name in chairlifts(page)}
    areas, seen = [], set()
    for _, heading, table in LIFT.findall(page):
        said = HEADING.fullmatch(words(heading))
        if not said:
            raise ValueError(f"a lift's heading reads {words(heading)!r}, not a name, a dash and a status")
        name, status = written.get(said.group(1).lower(), said.group(1)), " ".join(said.group(2).split()).capitalize()
        trails = []
        for cells in rows_of(table):
            trail = trail_row(cells)
            # A trail served by two lifts is listed under both: it is kept under the first.
            if trail and (trail["Name"], words(cells[4])) not in seen:
                seen.add((trail["Name"], words(cells[4])))
                trails.append(trail)
        areas.append({"Name": name, "Lifts": [{"Name": name, "Status": status, "StatusEnglish": status.lower(),
                                               "Difficulty": None}], "Trails": trails})
    if not areas or not seen:
        raise ValueError("the page lists no lifts or no trails")
    read = {area["Name"].lower() for area in areas}
    if len(read) != len(areas):
        raise ValueError("the page lists a lift twice")
    missing = [name for name in written.values() if name.lower() not in read]
    if missing:
        raise ValueError(f"the table of lift elevations names lifts that were not read: {missing}")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, measured at mid-mountain."""
    written = WRITTEN.search(page)
    if not written:
        raise ValueError("the snow report does not say when it was written")
    hour, minute, half, month, day, year = written.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    figures = {}
    for said, heading in FIGURE.findall(page):
        if heading not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(html.unescape(said))
        if not inches or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report's {heading} reads {said!r}, not inches given once")
        value = float(inches.group(1))
        figures[SNOWFALL[heading]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no mid-mountain depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mid-mountain", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    areas = lift_areas(pages["lifts"])
    counted = LIFTS_COUNTED.search(words(pages["snow"]))
    if counted and int(counted.group(1)) != len(areas):
        raise ValueError(f"the snow report counts {counted.group(1)} lifts but {len(areas)} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
