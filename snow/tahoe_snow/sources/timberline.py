"""Timberline's lifts and its snow report, from its conditions page (timberlinelodge.com/conditions).

The page is built on the server. Under "Operations Status" it has a table of lifts: each row is a lift's name, its
status, its type and its hours. The status is in the resort's own words ("Waiting for Snow") beside a dot the page
colours green, red or yellow: a green one is given as open and a red one as closed, with the page's words kept as
the status shown, and a yellow one is carried in the page's words alone. A colour the reader does not know fails. A
second table in the same shape lists the parking lots, which are not lifts and are not read. The page lists no
trails, so none are given.

The snow report is the page's "Snow" figures: the depth at the lodge at 6,000 feet, the snowfall of the last 24 and
72 hours and the season's total in inches, with the resort's "Latest Updates" as its words. The page says when its
weather was updated without the year ("Updated November 26, 6:05am"), in Pacific time; the year is the one that
puts the date nearest before the time of reading. It gives no surface. A snow report that cannot be read costs only
the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://timberlinelodge.com/conditions"
NAME = "Timberline"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
# The colours of the dot beside a status, and what a lift with that dot is given as; a yellow one keeps its words.
COLOURS = {"green": "open", "red": "closed", "yellow": None}
# The labels under the page's snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hours": "Last24HoursIn", "72 Hours": "Last72HoursIn", "Base Depth at 6,000'": "BaseIn",
            "Season Total": "SeasonTotalIn"}
TABLE = re.compile(r"<table[^>]*>\s*<thead>(.*?)</thead>\s*<tbody>(.*?)</tbody>\s*</table>", re.S)
HEADING = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
FIRST = re.compile(r"<div[^>]*>(.*?)</div>", re.S)
COLOUR = re.compile(r"class=\"?status__color--([a-z]+)")
TAG = re.compile(r"<[^>]+>")
ITEM = re.compile(r"<div class=\"?conditions__item-data\"?>(.*?)</div>\s*"
                  r"<div class=\"?conditions__item-label\"?>(.*?)</div>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?) ?(?:”|\")")
UPDATED = re.compile(r"<h2 class=\"?conditions__heading\"?>\s*Weather\s*</h2>\s*<p>\s*Updated ([A-Z][a-z]+) (\d{1,2}), "
                     r"(\d{1,2}):(\d{2}) ?([ap]m)\s*</p>")
UPDATES = re.compile(r"Latest Updates\s*</h2>\s*<div class=\"?latest-updates-text-block__text\"?>(.*?)</div>", re.S)


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_row(cells: list) -> dict:
    if len(cells) != 4:
        raise ValueError("a row of the lift table is not a name, a status, a type and its hours")
    # A lift's name is the first line of its cell: "Heidi's" has "at Summit Pass" under it.
    first = FIRST.search(cells[0])
    name = words(first.group(1)) if first else ""
    if not name:
        raise ValueError("a row of the lift table has no name")
    said, colour = words(cells[1]), COLOUR.search(cells[1])
    if not said:
        raise ValueError(f"{name} has no status")
    if not colour or colour.group(1) not in COLOURS:
        raise ValueError(f"{name} has a status of a colour the reader does not know: {cells[1].strip()!r}")
    status = said[0].upper() + said[1:].lower()
    return {"Name": name, "Status": status, "StatusEnglish": COLOURS[colour.group(1)] or status.lower(),
            "Difficulty": None}


def lifts_of(page: str) -> list:
    """The lifts of the page's lift table, in the page's order."""
    headings = ["Lifts", "Status", "Type", "Operating Hours"]
    tables = [body for head, body in TABLE.findall(page) if [words(each) for each in HEADING.findall(head)] == headings]
    if len(tables) != 1:
        raise ValueError(f"the page has {len(tables)} lift tables, not one")
    lifts = [lift_row(CELL.findall(row)) for row in ROW.findall(tables[0])]
    if not lifts:
        raise ValueError("the lift table lists no lifts")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the lift table lists a lift twice")
    return lifts


def updated(page: str, now: datetime) -> datetime:
    """When the page says its weather was updated. It gives no year: the year is the one that puts the date nearest
    before the time of reading, with a day's grace for a clock that is ahead."""
    said = UPDATED.search(page)
    if not said:
        raise ValueError("the page does not say when its weather was updated")
    month, day, hour, minute, half = said.groups()
    for year in (now.year + 1, now.year, now.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
        except ValueError:
            # February 29 in a year that has none.
            continue
        at = at.replace(tzinfo=PACIFIC_TIME)
        if at <= now + timedelta(days=1):
            return at
    raise ValueError(f"the date the weather was updated could not be read: {said.group(0)!r}")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, measured at the lodge."""
    at = updated(page, now)
    figures = {}
    for said, label in ITEM.findall(page):
        label = words(label)
        if label not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(words(said))
        if not inches or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label} reads {words(said)!r}, not inches given once")
        value = float(inches.group(1))
        figures[SNOWFALL[label]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    updates = UPDATES.search(page)
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Lodge (6,000 ft)", **figures},
            "Report": (words(updates.group(1)) or None) if updates else None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts_of(page), "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(page, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
