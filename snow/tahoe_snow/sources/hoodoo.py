"""Hoodoo's lifts and trails, and its snow report, from its mountain and lift status page
(hoodoo.com/the-mountain/mountain-lift-status).

The page is built on the server and written by one of the resort's groomers on the mornings it runs. It has the
day's conditions report, a table of trails under "Grooming Information for Saturday, March 14, 2026", and a table
headed "LIFTS SCHEDULED" with a row for each lift: its name and the hours it is scheduled to run that day ("9 AM to
9 PM") or "CLOSED". The page gives no other word on a lift, and says of its schedule that it is what the resort
plans to open and may change with weather, mechanical or staffing trouble. So a lift is given as open during the
hours the page schedules it on the day of its report, and as closed outside them; a lift's hours that do not read as
hours fail.

The report stays up on the days the mountain is shut and all through the summer, so its date matters: when the
report is not for the day of the reading, in Pacific time, every lift and every trail is given as closed, whatever
the old report says of them. The morning's report can come out late, and until it does the mountain reads as closed.

A trail's row is its name, its difficulty in words, "OPEN" or "CLOSED", a picture of a tick or a cross for whether
it was groomed, and another for whether it is lit at night, which is not read. A difficulty, a status or a grooming
picture the reader does not know fails. All the lifts and trails are one mountain area.

The snow report is the two lines the conditions report ends its words with: "Base (as of 2 AM): 16 inches" and "New
Snow:" followed by a sentence. The new snow is given only when the sentence says there was none or starts with a
figure in inches, as the snowfall of the last 24 hours. It is dated the day of the report at the hour the base was
read. It gives no surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
import html
import re
import string
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

URL = "https://hoodoo.com/the-mountain/mountain-lift-status/"
NAME = "Hoodoo"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
# The page's difficulty words, in the words the app's difficulty symbols are keyed on. "DIFFICULT" is written beside
# the same black diamond as "MOST DIFFICULT".
LEVELS = {"EASIER": "Green", "MORE DIFFICULT": "Blue", "DIFFICULT": "Black", "MOST DIFFICULT": "Black"}
STATUSES = {"OPEN": "Open", "CLOSED": "Closed"}
# The pictures of the groomed column, by the start of their names; an empty cell is a no.
PICTURES = {"black-check": "Yes", "red-x": "No"}
REPORT_DAY = re.compile(r"Grooming Information for\s+[A-Z][a-z]+day,\s+([A-Z][a-z]+) (\d{1,2}), (\d{4})")
TABLE = re.compile(r"<table id=\"tablepress-\d+\"[^>]*>\s*<thead>(.*?)</thead>\s*<tbody[^>]*>(.*?)</tbody>\s*</table>",
                   re.S)
HEADING = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PICTURE = re.compile(r"<img[^>]*\ssrc=\"[^\"]*/([^\"/]+)\.png\"")
TAG = re.compile(r"<[^>]+>")
HOURS = re.compile(r"(\d{1,2})(?::(\d{2}))? ?([AP]M) to (\d{1,2})(?::(\d{2}))? ?([AP]M)")
BASE = re.compile(r"Base \(as of (\d{1,2})(?::(\d{2}))? ?([AP]M)\):\s*(\d+(?:\.\d+)?) inch(?:es)?\b")
NEW_SNOW = re.compile(r"New Snow:\s*(?:(\d+(?:\.\d+)?) inch(?:es)?\b|We have received (no) new snow\b)")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def table(page: str, headings: list, what: str) -> list:
    """The cells of each row of the one table with these headings."""
    found = [body for head, body in TABLE.findall(page) if [words(each) for each in HEADING.findall(head)] == headings]
    if len(found) != 1:
        raise ValueError(f"the page has {len(found)} {what} tables, not one")
    return [CELL.findall(row) for row in ROW.findall(found[0])]


def report_day(page: str) -> datetime:
    """The day the page's report is for, as the heading over its trail table says it."""
    said = REPORT_DAY.search(words(page))
    if not said:
        raise ValueError("the page does not say what day its grooming information is for")
    try:
        return datetime.strptime(" ".join(said.groups()), "%B %d %Y")
    except ValueError as error:
        raise ValueError(f"the day of the grooming information could not be read: {error}") from error


def clock(hour: str, minute: str | None, half: str) -> time:
    try:
        return datetime.strptime(f"{hour}:{minute or '00'} {half}", "%I:%M %p").time()
    except ValueError as error:
        raise ValueError(f"an hour on the page could not be read: {error}") from error


def picture(cell: str, name: str) -> str:
    pictures = PICTURE.findall(cell)
    if not pictures and not words(cell):
        return "No"
    known = [said for start, said in PICTURES.items() if len(pictures) == 1 and pictures[0].startswith(start)]
    if not known:
        raise ValueError(f"{name} has a grooming the reader does not know: {cell.strip()!r}")
    return known[0]


def trail_row(cells: list, today: bool) -> dict:
    if len(cells) != 5:
        raise ValueError("a row of the trail table is not a name, a difficulty, a status, a grooming and a night")
    name = words(cells[0])
    if not name:
        raise ValueError("a row of the trail table has no name")
    level, status = words(cells[1]), words(cells[2])
    if level not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {level!r}")
    if status not in STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {status!r}")
    groomed = picture(cells[3], name)
    said = STATUSES[status] if today else "Closed"
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": LEVELS[level],
            "Grooming": groomed if today else "No"}


def lift_row(cells: list, today: bool, at: time) -> dict:
    if len(cells) != 2:
        raise ValueError("a row of the lift table is not a name and its hours")
    # The page writes its lifts in capitals: "HAROLD'S MAGIC CARPET".
    name, said = string.capwords(words(cells[0])), words(cells[1])
    if not name:
        raise ValueError("a row of the lift table has no name")
    hours = HOURS.fullmatch(said)
    if hours:
        start, end = clock(*hours.groups()[:3]), clock(*hours.groups()[3:])
        if start >= end:
            raise ValueError(f"{name} has hours that do not run forwards: {said!r}")
        status = "Open" if today and start <= at < end else "Closed"
    elif said == "CLOSED":
        status = "Closed"
    else:
        raise ValueError(f"{name} has hours the reader does not know: {said!r}")
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def snow_report(page: str, day: datetime) -> dict:
    """The conditions report's base depth and new snow in the shape of the Ikon feed's SnowReport."""
    text = words(page)
    bases = BASE.findall(text)
    if len(bases) != 1:
        raise ValueError(f"the conditions report gives its base depth {len(bases)} times, not once")
    hour, minute, half, inches = bases[0]
    posted = datetime.combine(day.date(), clock(hour, minute, half), tzinfo=PACIFIC_TIME)
    area = {"Name": "Base", "BaseIn": int(float(inches)) if float(inches).is_integer() else float(inches)}
    new = NEW_SNOW.search(text)
    if new:
        fell = float(new.group(1)) if new.group(1) else 0.0
        area["Last24HoursIn"] = int(fell) if fell.is_integer() else fell
    return {"LastUpdate": posted.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": None, "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    day, here = report_day(page), now.astimezone(PACIFIC_TIME)
    today = day.date() == here.date()
    lifts = [lift_row(cells, today, here.time()) for cells in table(page, ["LIFT", "HOURS"], "lift")]
    trails = [trail_row(cells, today)
              for cells in table(page, ["Trail", "Difficulty/Color", "Status", "Groomed", "Night Ski"], "trail")]
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    if len({lift["Name"] for lift in lifts}) != len(lifts) or len({trail["Name"] for trail in trails}) != len(trails):
        raise ValueError("the page lists a lift or a trail twice")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
    try:
        feed["SnowReport"] = snow_report(page, day)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
