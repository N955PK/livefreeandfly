"""Whitecap Mountains' lifts and trails, and its snow report, from its snow report page
(whitecapresort.com/winter/snow-report).

The page is built on the server from the form the resort fills in each morning: a table of the day's conditions,
a table of the lifts, and a table of trails for each difficulty (Easier, More Difficult, Most Difficult, Expert
Only). A lift's or a trail's status is the word in its row (OPEN, CLOSED), carried as the page says it. A trail's
note says whether it is groomed; any other note, or none, reads as not groomed. The trails are written in capitals
and are given here with a capital on each word. The lifts are one mountain area and each difficulty's trails
another. The page's own counts of lifts and of trails open have to match what is read, so a change in the page's
shape fails instead of showing wrong numbers.

The conditions give the day and time the report was written (Central time), the base depth as a low and a high
("0-34+") or as one depth, the natural snow of the last 24 hours and 7 days and of the season, in inches, and the
surface in words. The resort leaves its last report of the season up all summer and autumn with its lifts still
reading open, so a report more than OLD_DAYS old that has anything open is refused: its statuses are last
season's. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.whitecapresort.com/winter/snow-report"
NAME = "Whitecap"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Chicago")
# A report older than this with a lift or a trail open is last season's, left up after the mountain closed.
OLD_DAYS = 14
# The headings of the trail tables, in the words the app's difficulty symbols are keyed on.
LEVELS = {"Easier": "Green", "More Difficult": "Blue", "Most Difficult": "Black", "Expert Only": "Double black"}
# The conditions' lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Depth of Natural Snow Last 24 Hours": "Last24HoursIn", "Depth of Natural Snow Last 7 Days": "Last7DaysIn"}
TABLE = re.compile(r"<table class=\"(snowreport|lifts|trails)\b[^\"]*\"[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t([hd])[^>]*>(.*?)</t[hd]>", re.S)
WRITTEN = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}) - (\d{1,2}):(\d{2}) ([AP]M)")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”|in(?:ches)?\.?)?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”)?\s*(?:-|–)\s*(\d+(?:\.\d+)?)\s*(?:\"|”)?\+?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def named(said: str) -> str:
    """A name the page writes in capitals, with a capital on each word instead."""
    return " ".join(word.capitalize() for word in said.split()) if said.isupper() else said


def tables(page: str) -> tuple:
    """The page's tables as rows of cells: the conditions, the lifts, and the trails of each difficulty."""
    conditions, lifts, trails = None, None, {}
    for kind, body in TABLE.findall(page):
        rows = [[(cell, words(text)) for cell, text in CELL.findall(row)] for row in ROW.findall(body)]
        if not rows or len(rows[0]) != 3 or any(cell != "h" for cell, _ in rows[0]):
            raise ValueError(f"a {kind} table does not begin with a heading of three cells")
        heading, rest = rows[0][0][1], [[text for _, text in row] for row in rows[1:]]
        if kind == "snowreport" and conditions is None:
            conditions = {row[0]: row[1] for row in rest if len(row) >= 2 and row[0]}
        elif kind == "lifts" and lifts is None and heading == "Lifts":
            lifts = rest
        elif kind == "trails" and heading in LEVELS and heading not in trails:
            trails[heading] = rest
        else:
            raise ValueError(f"the page has a {kind} table the reader does not know, or has it twice: {heading}")
    if conditions is None or lifts is None or not trails:
        raise ValueError("the conditions, the lifts or the trails were not found")
    return conditions, lifts, trails


def status_rows(rows: list, difficulty: str | None) -> list:
    """The lifts or trails of a table; a row with no name and no status is the table's padding."""
    found = []
    for row in rows:
        if len(row) != 3:
            raise ValueError("a row is not a name, a status and a note")
        name, status, note = named(row[0]), row[1].capitalize(), row[2]
        if not name and not status:
            continue
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a row'} has the status {status!r}, not a word")
        entry = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
        if difficulty is not None:
            entry["Grooming"] = "Yes" if note.lower() == "groomed" else "No"
        found.append(entry)
    return found


def written(conditions: dict) -> datetime:
    """When the report was written."""
    said = WRITTEN.fullmatch(conditions.get("Date / Time", ""))
    if not said:
        raise ValueError(f"the report's date reads {conditions.get('Date / Time')!r}, not a day and a time")
    try:
        at = datetime.strptime(" ".join(said.groups()), "%b %d %Y %I %M %p")
    except ValueError as error:
        raise ValueError(f"the report's date could not be read: {error}") from error
    return at.replace(tzinfo=LOCAL_TIME)


def checked(rows: list, conditions: dict, label: str) -> None:
    turning = sum(row["StatusEnglish"] == "open" for row in rows)
    if conditions.get(label) != str(turning):
        raise ValueError(f"the page's {label.lower()} is {conditions.get(label)!r} but {turning} were read")


def snow_report(conditions: dict, at: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    depth, area = conditions.get("Base Depth Range", ""), {"Name": "Mountain"}
    if RANGE.fullmatch(depth):
        low, high = (number(end) for end in RANGE.fullmatch(depth).groups())
        if low > high:
            raise ValueError(f"the base depth runs from {low} down to {high}")
        area.update({"BaseMinIn": low, "BaseMaxIn": high})
    elif INCHES.fullmatch(depth):
        area["BaseIn"] = number(INCHES.fullmatch(depth).group(1))
    else:
        raise ValueError(f"the base depth reads {depth!r}, not inches")
    for label, field in SNOWFALL.items():
        said = INCHES.fullmatch(conditions.get(label, ""))
        area[field] = number(said.group(1)) if said else None
    if area["Last24HoursIn"] is None:
        raise ValueError(f"the 24 hour snowfall reads {conditions.get(next(iter(SNOWFALL)))!r}, not inches")
    season = INCHES.fullmatch(conditions.get("Depth of Natural Snow All Season", ""))
    surface = conditions.get("Surface Conditions", "")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": surface.capitalize() or None, "SeasonTotalIn": number(season.group(1)) if season else None,
            "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    conditions, lift_table, trail_tables = tables(page)
    lifts = status_rows(lift_table, None)
    areas = [{"Name": heading, "Lifts": [], "Trails": status_rows(rows, LEVELS[heading])}
             for heading, rows in trail_tables.items()]
    trails = [trail for area in areas for trail in area["Trails"]]
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    checked(lifts, conditions, "Total Lifts Open")
    checked(trails, conditions, "Total Trails Open")
    at = written(conditions)
    if now - at > timedelta(days=OLD_DAYS) and any(row["StatusEnglish"] == "open" for row in lifts + trails):
        raise ValueError(f"the report was written {at:%Y-%m-%d} and has lifts or trails open: it is last season's")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(conditions, at)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
