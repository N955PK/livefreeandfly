"""Crystal Mountain's lifts and trails, and its snow report, from its mountain report page
(crystalmountain.com/ski/cams-conditions/mountain-report). This is Michigan's Crystal Mountain, not Washington's.

The page is built on the server: a tab of trails, folded under a heading for each lift's part of the mountain
(Buck, Crystal Clipper, Loki, North Face, Backyard, Ridge and the Mountain Adventure Zone), and a tab of lifts. A
lift's or trail's status is the word on its row (open, closed, on hold), carried as the page says it. A trail's
difficulty is the symbol before its name (beginner, intermediate, advanced, park), and one the reader does not
know fails; a terrain park has none. A trail marked groomed is carried as groomed. The lifts are one mountain area
and each part of the mountain another. The page's own counts of trails and of lifts, open and in all, are checked
against what is read, so a change in the page's shape fails instead of showing wrong numbers.

The snow report gives the snow of the last 24 hours and the base depth, as one depth or a low and a high, in
inches, under the day it was written, which is read as noon of that day in Eastern time. The page gives no word
for the surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.crystalmountain.com/ski/cams-conditions/mountain-report"
NAME = "Crystal Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Detroit")
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on; a park has none.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "park": ""}
# In the tabs: a heading over a part of the mountain, or the start of a lift's or a trail's row.
HEADING_OR_ROW = re.compile(r"<summary[^>]*>(.*?)</summary>|<div class=\"(lift|trail) d-flex[^\"]*\">", re.S)
STATUS = re.compile(r"<div class=\"cell status\">\s*<div class=\"[a-z-]+ status-block\">([^<]*)</div>\s*</div>")
TITLE = re.compile(r"<div class=\"pos-relative cell title\">\s*<div class=\"cell f-icon type "
                   r"(?:level_category|lift_type) ([a-z-]+)\"[^>]*>[^<]*</div>([^<]*)</div>")
GROOMED = re.compile(r"class=\"[^\"]*\bgroomed\b")
COUNTED = r"<h3 class=\"h5\">\s*{kind} Open\s*</h3>\s*<div[^>]*>\s*<span class=\"value\">\s*(\d+)\s*</span>\s*" \
          r"<span class=\"[^\"]*\btotal\">\s*/\s*(\d+)\s*</span>"
FIGURE = r"<h3 class=\"h5\">\s*{label}\s*</h3>\s*<div[^>]*>\s*<span class=\"value\">\s*([^<]*?)\s*</span>"
WRITTEN = re.compile(r"component-snow-report\">\s*<div[^>]*>\s*<h2>\s*([A-Z][a-z]+ \d{1,2}, \d{4})\s*</h2>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\"")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\"?\s*-\s*(\d+(?:\.\d+)?)\"")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def rows_of(page: str) -> tuple:
    """The lifts, and the trails of each part of the mountain, in the page's order."""
    lifts, areas, heading = [], {}, None
    marks = list(HEADING_OR_ROW.finditer(page))
    for mark, following in zip(marks, marks[1:] + [None]):
        if mark.group(2) is None:
            heading = words(mark.group(1))
            continue
        kind, row = mark.group(2), page[mark.end():following.start() if following else len(page)]
        status, title = STATUS.search(row), TITLE.search(row)
        if not status or not title or not words(title.group(2)):
            raise ValueError(f"a {kind}'s row is not a status, a symbol and a name")
        name, said = words(title.group(2)), words(status.group(1)).capitalize()
        if not said or not said.replace(" ", "").isalpha():
            raise ValueError(f"{name} has the status {said!r}, not a word")
        found = {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}
        if kind == "lift":
            lifts.append(found)
            continue
        if title.group(1) not in LEVELS:
            raise ValueError(f"{name} has a difficulty symbol the reader does not know: {title.group(1)}")
        if not heading:
            raise ValueError(f"{name} is under no part of the mountain")
        found.update({"Difficulty": LEVELS[title.group(1)], "Grooming": "Yes" if GROOMED.search(row) else "No"})
        areas.setdefault(heading, []).append(found)
    return lifts, [{"Name": heading, "Lifts": [], "Trails": trails} for heading, trails in areas.items()]


def counted(page: str, kind: str) -> tuple:
    """The page's own count of its trails or its lifts: how many are open, and how many there are."""
    found = re.search(COUNTED.format(kind=kind), page)
    if not found:
        raise ValueError(f"the page's count of {kind.lower()} was not found")
    return int(found.group(1)), int(found.group(2))


def checked(rows: list, page: str, kind: str) -> None:
    read = sum(row["StatusEnglish"] == "open" for row in rows), len(rows)
    if counted(page, kind) != read:
        turning, listed = counted(page, kind)
        raise ValueError(f"the page counts {turning} of {listed} {kind.lower()} open but {read[0]} of {read[1]} "
                         "were read")


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    written = WRITTEN.search(page)
    if not written:
        raise ValueError("the snow report does not say when it was written")
    try:
        at = datetime.strptime(written.group(1), "%B %d, %Y").replace(hour=12, tzinfo=LOCAL_TIME)
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    new, depth = (re.search(FIGURE.format(label=label), page) for label in ("24h Snowfall", "Base Depth"))
    new, depth = (html.unescape(found.group(1)) if found else "" for found in (new, depth))
    if not INCHES.fullmatch(new):
        raise ValueError(f"the 24 hour snowfall reads {new!r}, not inches")
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
    area["Last24HoursIn"] = number(INCHES.fullmatch(new).group(1))
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": None, "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = rows_of(page)
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    checked(lifts, page, "Lifts")
    checked([trail for area in areas for trail in area["Trails"]], page, "Trails")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
