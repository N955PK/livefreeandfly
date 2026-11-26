"""Nub's Nob's lifts and trails, and its snow report, from its conditions page (nubsnob.com/conditions-tables,
which nubsnob.com/conditions-new leads to).

The page is built on the server: a block of the day's figures, a block of the lifts, and a block of trails for each
part of the mountain (Nub's North, Nub's Nob South, Pintail Peak). Each row is a name and a few symbols. The first
symbol is the status, a tick or a cross, read from its name (open, closed), and one the reader does not know fails.
A trail's second symbol is its difficulty (beginner, intermediate, expert, and expert with two diamonds), and one
the reader does not know fails. The lifts are one mountain area and each part of the mountain another. The day's
figures count the lifts open: where that is a number it has to match what is read, so a change in the page's shape
fails instead of showing wrong numbers.

The day's figures give the base depth, as one depth or a low and a high, the new snow since yesterday and over 3
and 7 days, the season's total, the surface in the resort's word and its comments. They are dated in words: a date
with a month and a day is read, in Eastern time ("Thanksgiving Day" is not, and leaves the report undated). A
snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.nubsnob.com/conditions-tables/"
NAME = "Nub's Nob"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Detroit")
LIFTS = "ski-lift-information"
# The status symbols' names, in the words of the page's own key.
STATUSES = {"open-icon": "Open", "closed-icon": "Closed"}
# The difficulty symbols, in the words the app's difficulty symbols are keyed on, the two-diamond one first.
LEVELS = (("double-diamond", "Double black"), ("expert-icon", "Black"), ("intermediate-icon", "Blue"),
          ("beginner-icon", "Green"))
# The longer snowfalls, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"3 days": "Last72HoursIn", "7 days": "Last7DaysIn", "YTD": "SeasonTotalIn"}
BLOCK = re.compile(r"<div class='glm-ski-conditions' data-region='([a-z0-9-]+)'>\s*<h6>(.*?)</h6>(.*?)"
                   r"(?=<div class='glm-ski-conditions'|<footer|\Z)", re.S)
TODAY = re.compile(r"<div class=\"glm-ski-conditions-data\" data-region=\"current\">(.*?)"
                   r"(?=<div id=\"glm-ski-conditions-legend-container\"|<div class='glm-ski-conditions'|\Z)", re.S)
RECORD = re.compile(r"<div class=\"glm-conditions-record flex\">(.*?)(?=<div class=\"glm-conditions-record flex\">|\Z)",
                    re.S)
CELL = re.compile(r"<div class='conditions-cell cell-(\d)'>(.*?)(?=<div class='conditions-cell cell-\d'>|\Z)", re.S)
SYMBOL = re.compile(r"\b[a-z]+-(?:icon|diamond)\b")
TAG = re.compile(r"<[^>]+>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”|inches|in\.?)?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”)?\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:\"|”|inches|in\.?)?")
DATED = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December) "
                   r"(\d{1,2})(?:st|nd|rd|th)?\b(?:,? (\d{4}))?")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def rows_of(body: str, lifts: bool) -> list:
    """The rows of one block: each a name, its status from its first symbol, and a trail's difficulty."""
    rows = []
    for record in RECORD.findall(body):
        cells = dict(CELL.findall(record))
        name = words(cells.get("0", ""))
        if not name:
            raise ValueError("a row has no name")
        status = [STATUSES.get(symbol) for symbol in SYMBOL.findall(cells.get("1", ""))]
        if len(status) != 1 or not status[0]:
            raise ValueError(f"{name} has the status symbols {SYMBOL.findall(cells.get('1', ''))}, "
                             "not one the reader knows")
        difficulty = None
        if not lifts:
            symbols = set(SYMBOL.findall(cells.get("2", "")))
            difficulty = next((level for symbol, level in LEVELS if symbol in symbols), None)
            if difficulty is None:
                raise ValueError(f"{name} has the difficulty symbols {sorted(symbols)}, not one the reader knows")
        rows.append({"Name": name, "Status": status[0], "StatusEnglish": status[0].lower(), "Difficulty": difficulty})
    return rows


def figures_of(page: str) -> dict:
    """The day's figures: each label with the cells beside it."""
    found = TODAY.search(page)
    if not found:
        raise ValueError("the day's figures were not found")
    figures = {}
    for record in RECORD.findall(found.group(1)):
        cells = [words(cell) for _, cell in CELL.findall(record)]
        if cells and cells[0]:
            figures[cells[0].rstrip(": ")] = cells[1:]
    return figures


def written(said: str, now: datetime) -> str | None:
    """When the figures are dated, as noon of that day in Eastern time; None where the page gives no month and day."""
    found = DATED.search(said)
    if not found:
        return None
    month, day, year = found.groups()
    try:
        at = datetime.strptime(f"{year or now.astimezone(LOCAL_TIME).year} {month} {day} 12", "%Y %B %d %H")
        at = at.replace(tzinfo=LOCAL_TIME)
        if not year and at - now > timedelta(days=2):
            # A date with no year that would be ahead of today is last year's.
            at = at.replace(year=at.year - 1)
    except ValueError:
        return None
    return at.astimezone(timezone.utc).strftime(STAMP)


def snow_report(figures: dict, now: datetime) -> dict:
    """The day's figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    depth, new = (figures.get("Base Depth") or [""])[0], figures.get("New Snow since yesterday") or [""]
    area = {"Name": "Mountain"}
    if RANGE.fullmatch(depth):
        low, high = (number(end) for end in RANGE.fullmatch(depth).groups())
        if low > high:
            raise ValueError(f"the base depth runs from {low} down to {high}")
        area.update({"BaseMinIn": low, "BaseMaxIn": high})
    elif INCHES.fullmatch(depth):
        area["BaseIn"] = number(INCHES.fullmatch(depth).group(1))
    else:
        raise ValueError(f"the base depth reads {depth!r}, not inches")
    if not INCHES.fullmatch(new[0]):
        raise ValueError(f"the new snow since yesterday reads {new[0]!r}, not inches")
    area["Last24HoursIn"] = number(INCHES.fullmatch(new[0]).group(1))
    season = None
    for said in new[1:]:
        label, _, amount = said.partition(":")
        if label.strip() in SNOWFALL and INCHES.fullmatch(amount.strip()):
            value = number(INCHES.fullmatch(amount.strip()).group(1))
            if SNOWFALL[label.strip()] == "SeasonTotalIn":
                season = value
            else:
                area[SNOWFALL[label.strip()]] = value
    surface = (figures.get("Snow Surface") or [""])[0]
    return {"LastUpdate": written((figures.get("Date") or [""])[0], now), "Resortwide": True,
            "BaseConditions": None if surface in ("", "N/A") else surface, "SeasonTotalIn": season, "BaseArea": area,
            "Report": (figures.get("Comments") or [""])[0] or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    areas = []
    for region, heading, body in BLOCK.findall(page):
        rows = rows_of(body, region == LIFTS)
        areas.append({"Name": NAME, "Lifts": rows, "Trails": []} if region == LIFTS else
                     {"Name": words(heading), "Lifts": [], "Trails": rows})
    if sum(bool(area["Lifts"]) for area in areas) != 1 or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    figures = figures_of(page)
    counted = (figures.get("Lifts Open") or [""])[0]
    read = sum(lift["StatusEnglish"] == "open" for area in areas for lift in area["Lifts"])
    if counted.isdigit() and int(counted) != read:
        raise ValueError(f"the page counts {counted} lifts open but {read} were read")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(figures, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
