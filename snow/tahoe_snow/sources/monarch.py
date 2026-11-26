"""Monarch Mountain's lifts and trails, and its snow report, from its conditions page (skimonarch.com/conditions).

The page is built on the server. Its lift table gives each lift's name and its status in words, carried as the page
says them. Its terrain is a tab for each part of the mountain (Frontside Terrain, Panorama Ridge, Mirkwood Basin and
so on), each naming the lifts that serve it over a table of its trails; each tab is a mountain area here, holding
those lifts and its trails. A trail's difficulty is a drawing, read by its colour (the hike-to basin's is a picture
labelled "Expert Only"), and one the reader does not know fails; its grooming column is empty unless it is groomed.
The tubing park's lift is counted by the page but is not a ski lift, and is left out. The page's own counts of lifts
and trails, and of how many of each are open, are checked against what is read, so a change in the page's shape
fails instead of showing wrong numbers.

The snow report is a row of figures over a row of their labels: the snow overnight and of the last 24 and 48 hours
and 7 days, the base depth and the season's total, in inches, over a line saying when it was last updated, in
Mountain time. It gives no word for the surface. A snow report that cannot be read costs only the snow report, not
the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://skimonarch.com/conditions/"
NAME = "Monarch Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The difficulty drawings' colours, in the words the app's difficulty symbols are keyed on; the orange oval is a
# terrain park, which has none.
LEVELS = {"#4CAF50": "Green", "#2196F3": "Blue", "#000000": "Black", "#FF9800": ""}
# The difficulty pictures' labels.
PICTURED = {"Expert Only": "Double black"}
NOT_SKIED = "tubing"
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Overnight": "OvernightIn", "24 hours": "Last24HoursIn", "48 hours": "Last48HoursIn",
            "7 days": "Last7DaysIn", "Base": "BaseIn", "Season total": "SeasonTotalIn"}
LIFT_TABLE = re.compile(r"<table class=\"lifts-table\">(.*?)</table>", re.S)
LIFT = re.compile(r"<td data-label=\"Lift Name\">(.*?)</td>\s*<td[^>]*data-label=\"Status\">(.*?)</td>", re.S)
PANEL = re.compile(r"<div class=\"vc_tta-panel\" id=")
TITLE = re.compile(r"<span class=\"vc_tta-title-text\">(.*?)</span>", re.S)
SERVED_BY = re.compile(r"<li>(.*?)</li>", re.S)
TRAIL_TABLE = re.compile(r"<table class=\"trails-table\">(.*?)</table>", re.S)
TRAIL = re.compile(r"<td data-label=\"Trail\">(.*?)</td>\s*<td[^>]*data-label=\"Difficulty\">(.*?)</td>\s*"
                   r"<td[^>]*data-label=\"Groomed\">(.*?)</td>\s*<td[^>]*data-label=\"Status\">(.*?)</td>", re.S)
COLOUR = re.compile(r"<svg[^>]*>\s*<[a-z]+[^>]*\sfill=\"(#[0-9A-Fa-f]{6})\"")
LABEL = re.compile(r"<img[^>]*\salt=\"([^\"]*)\"")
COUNTED = re.compile(r"(Lifts|Trails) Open:\s*(\d+) of\s*(\d+)")
ACCUMULATION = re.compile(r"<table class=\"accumulation__table\">\s*<thead>(.*?)</thead>\s*<tbody>(.*?)</tbody>", re.S)
HEAD, CELL = re.compile(r"<th[^>]*>(.*?)</th>", re.S), re.compile(r"<td[^>]*>(.*?)</td>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|″|”)")
UPDATED = re.compile(r"Last Updated:\s*([A-Z][a-z]+ \d{1,2}, \d{4}) - (\d{1,2}:\d{2} [AP]M)")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    if not name:
        raise ValueError("the page lists a lift or a trail with no name")
    if not said:
        raise ValueError(f"{name} has no status")
    status = said.capitalize()
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def difficulty(cell: str, name: str) -> str:
    colour, label = COLOUR.search(cell), LABEL.search(cell)
    if colour and colour.group(1).upper() in LEVELS:
        return LEVELS[colour.group(1).upper()]
    if label and label.group(1) in PICTURED:
        return PICTURED[label.group(1)]
    raise ValueError(f"{name} has a difficulty the reader does not know")


def trail_row(name: str, level: str, groomed: str, said: str) -> dict:
    row = status_row(words(name), words(said), difficulty(level, words(name)))
    # The grooming column holds nothing for a trail that is not groomed.
    row["Grooming"] = "Yes" if words(groomed) or "<" in groomed else "No"
    return row


def counted(page: str, what: str, rows: list) -> None:
    """Fails unless the page's own count of its lifts or trails, and of those open, is what was read."""
    counts = {kind: (int(turning), int(total)) for kind, turning, total in COUNTED.findall(words(page))}
    if what not in counts:
        raise ValueError(f"the page's count of {what.lower()} was not found")
    read = (sum(row["StatusEnglish"] == "open" for row in rows), len(rows))
    if counts[what] != read:
        raise ValueError(f"the page counts {counts[what][0]} of {counts[what][1]} {what.lower()} open "
                         f"but {read[0]} of {read[1]} were read")


def lift_rows(page: str) -> list:
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the lift table was not found")
    lifts = [status_row(words(name), words(said), None) for name, said in LIFT.findall(table.group(1))]
    if not lifts:
        raise ValueError("the page lists no lifts")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    counted(page, "Lifts", lifts)
    return [lift for lift in lifts if NOT_SKIED not in lift["Name"].lower()]


def terrain(page: str) -> list:
    """Each tab of the terrain as (its name, the lifts it names, its trails), in the page's order."""
    starts = [found.start() for found in PANEL.finditer(page)]
    tabs = []
    for at, start in enumerate(starts):
        panel = page[start:starts[at + 1] if at + 1 < len(starts) else len(page)]
        title, table = TITLE.search(panel), TRAIL_TABLE.search(panel)
        if not title or not table:
            raise ValueError("a tab of the terrain has no name or no table of trails")
        trails = [trail_row(*cells) for cells in TRAIL.findall(table.group(1))]
        if len(trails) != table.group(1).count("data-label=\"Trail\""):
            raise ValueError(f"a row of {words(title.group(1))}'s trails is not in the shape expected")
        tabs.append((words(title.group(1)), [words(item) for item in SERVED_BY.findall(panel[:table.start()])], trails))
    if not any(trails for _, _, trails in tabs):
        raise ValueError("the page lists no trails")
    counted(page, "Trails", [trail for _, _, trails in tabs for trail in trails])
    return tabs


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated, table = UPDATED.search(words(page)), ACCUMULATION.search(page)
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    if not table:
        raise ValueError("the snow report's table was not found")
    try:
        at = datetime.strptime(f"{updated.group(1)} {updated.group(2)}", "%B %d, %Y %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    said = [words(cell) for cell in HEAD.findall(table.group(1))]
    labels = [words(cell) for cell in CELL.findall(table.group(2))]
    if len(said) != len(labels) or len(set(labels)) != len(labels):
        raise ValueError("the snow report's figures and their labels do not pair up")
    figures = {}
    for label, figure in zip(labels, said):
        if label not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(figure)
        if not inches:
            raise ValueError(f"the snow report's {label} reads {figure!r}, not inches")
        value = float(inches.group(1))
        figures[SNOWFALL[label]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas, placed = lift_rows(page), [], set()
    for name, served_by, trails in terrain(page):
        # A tab names its lifts as "Garfield Lift"; the lift table has them as "Garfield".
        mine = [lift for lift in lifts if f"{lift['Name']} Lift".lower() in {item.lower() for item in served_by}]
        placed.update(lift["Name"] for lift in mine)
        areas.append({"Name": name, "Lifts": mine, "Trails": trails})
    stray = [lift for lift in lifts if lift["Name"] not in placed]
    if stray:
        areas.append({"Name": NAME, "Lifts": stray, "Trails": []})
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
