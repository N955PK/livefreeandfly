"""Sunrise Park's lifts and trails, and its snow report, from its snow report page (sunrise.ski/winter/snow-report).

The page is built on the server. Its lift table is a row for each lift: a mark with the lift's status in a word
under it ("Closed"), then the lift's name over a line describing it. Its trails are a table for each of the
resort's three peaks (Sunrise, Apache, Cyclone), each a mountain area here; the lifts name no peak and are an area
of their own. A trail's row is four cells: a difficulty symbol (a green circle, a blue square, a black diamond or
a double black diamond), its name, a grooming mark and a status mark.

**A trail's status and grooming are pictures with no words.** The only ones seen are the closed cross
(``closed_x.png``) and the ungroomed mark (``no_snow_groomer.png``), the page being read before the season. A
trail whose mark is not the closed cross is taken to be open, and one whose mark is not the ungroomed mark to be
groomed, and only as long as the page's own counts ("12/67 trails open", "9/67 groomed") agree with what that
gives: a hold mark, or any other third picture, makes the counts disagree and the page is refused. The lifts'
count is checked the same way, so a change in the page's shape fails instead of showing wrong numbers.

The snow levels give the snow of the last 24 hours, 72 hours and 7 days, the base depth and the season's total,
in inches, under a line saying when the report was updated in the resort's own time (Arizona's, which has no
daylight time). The page keeps last season's report up until it opens. The page gives no word for the surface. A
snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://sunrise.ski/winter/snow-report/"
NAME = "Sunrise Park"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Phoenix")
# The difficulty symbols' file names, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green_trail": "Green", "blue_trail": "Blue", "black_diamond": "Black",
          "double_black_diamond": "Double black"}
CLOSED_MARK, UNGROOMED_MARK = "closed_x", "no_snow_groomer"
# The snow levels' lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Last 24 Hours": "Last24HoursIn", "Last 72 Hours": "Last72HoursIn", "Last 7 Days": "Last7DaysIn",
            "Base Depth": "BaseIn", "Season Total": "SeasonTotalIn"}
LIFT_TABLE = re.compile(r"<table class=\"liftstable\">(.*?)</table>", re.S)
LIFT = re.compile(r"<td[^>]*>\s*<img [^>]*>\s*<p>([^<]*)</p>\s*</td>\s*<td[^>]*>\s*<h4>(.*?)</h4>", re.S)
# A peak's tab, then its trail table: the tab's heading is the peak's name.
PEAK = re.compile(r"id=\"mobile-fusion-tab-(\w+)\"[^>]*>\s*<h4[^>]*>(.*?)</h4>.*?id=\"tab-\1\"[^>]*>\s*<div[^>]*>\s*"
                  r"<table class=\"trailstable\">(.*?)</table>", re.S)
ROW = re.compile(r"<tr class='(?:lifts|trails)row'>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
MARK = re.compile(r"<img src='[^']*/([\w-]+)\.png'")
# The page counts its lifts and trails in more than one place, as "<big>12</big>/67 trails open".
COUNT = r">\s*(\d+)\s*</span>\s*(?:<span[^>]*>)?\s*/(\d+)\s*<br\s*/?>\s*{kind}\b"
LEVEL_LINE = re.compile(r"<p[^>]*>([^<]*)</p>\s*</div>\s*<div[^>]*>\s*<p[^>]*>(" + "|".join(SNOWFALL) + r")</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:“|”|″|\")?")
UPDATED = re.compile(r"<span[^>]*>Updated:\s*([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th),? (\d{4}) (\d{1,2}:\d{2}\s*[ap]m)"
                     r"</span>")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def counted(page: str, kind: str) -> tuple:
    """The page's own count of ``kind`` ("lifts open", "trails open", "groomed"), which it gives more than once."""
    found = {(int(some), int(total)) for some, total in re.findall(COUNT.format(kind=kind), page)}
    if len(found) != 1:
        raise ValueError(f"the page's count of {kind} was not found, or it gives two that differ")
    return found.pop()


def lift_rows(page: str) -> list:
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the lift table was not found")
    lifts = []
    for row in ROW.findall(table.group(1)):
        found = LIFT.search(row)
        said, name = (words(found.group(1)), words(found.group(2))) if found else ("", "")
        if not name or not said:
            raise ValueError("a row of the lift table is not a status in a word and a name")
        said = said.capitalize()
        lifts.append({"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None})
    if not lifts or len(lifts) != table.group(1).count("<tr") or len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the lift table has no rows, a row that is not a lift, or a lift twice")
    is_open, total = counted(page, "lifts open")
    read = sum(lift["StatusEnglish"] == "open" for lift in lifts)
    if total != len(lifts) or is_open != read:
        raise ValueError(f"the page counts {is_open} of {total} lifts open but {read} of {len(lifts)} were read")
    return lifts


def trail_row(row: str) -> dict:
    cells = CELL.findall(row)
    if len(cells) != 4:
        raise ValueError("a row of a trail table is not a difficulty, a name, a grooming and a status")
    name = words(cells[1])
    level, groomed, status = (MARK.search(cell) for cell in (cells[0], cells[2], cells[3]))
    if not name or not level or level.group(1) not in LEVELS:
        raise ValueError(f"{name or 'a trail'} has a difficulty symbol the reader does not know")
    if not groomed or not status:
        raise ValueError(f"{name} has no grooming mark or no status mark")
    said = "Closed" if status.group(1) == CLOSED_MARK else "Open"
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": LEVELS[level.group(1)],
            "Grooming": "No" if groomed.group(1) == UNGROOMED_MARK else "Yes"}


def trail_areas(page: str) -> list:
    """Each peak with its trails, in the page's order, checked against the page's own counts."""
    areas = []
    for _, name, table in PEAK.findall(page):
        rows = ROW.findall(table)
        if not rows or words(rows[0]) != "Level Trail Groomed Status":
            raise ValueError("a trail table does not begin with the headings Level, Trail, Groomed and Status")
        areas.append({"Name": words(name), "Lifts": [], "Trails": [trail_row(row) for row in rows[1:]]})
    trails = [trail for area in areas for trail in area["Trails"]]
    tables, rows = page.count("class=\"trailstable\""), page.count("class='trailsrow'")
    if not trails or len(areas) != tables or len(trails) != rows - tables:
        raise ValueError(f"the page has {tables} trail tables and {rows} rows but {len(areas)} tables and "
                         f"{len(trails)} trails were read")
    if len({area["Name"] for area in areas}) != len(areas) or not all(area["Name"] for area in areas):
        raise ValueError("a peak has no name or is listed twice")
    for kind, field, value in (("trails open", "StatusEnglish", "open"), ("groomed", "Grooming", "Yes")):
        some, total = counted(page, kind)
        read = sum(trail[field] == value for trail in trails)
        if total != len(trails) or some != read:
            # A third picture (a hold, say) is read as open or groomed, and shows up here.
            raise ValueError(f"the page counts {some} of {total} {kind} but {read} of {len(trails)} were read")
    return areas


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The page's snow levels in the shape of the Ikon feed's SnowReport."""
    figures = {}
    for said, label in LEVEL_LINE.findall(page):
        if SNOWFALL[label] in figures:
            raise ValueError(f"the snow report gives its {label} twice")
        figures[SNOWFALL[label]] = inches(words(said), label)
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    updated = UPDATED.search(page)
    if not updated:
        raise ValueError("the time the snow report was updated was not found")
    month, day, year, clock = updated.groups()
    try:
        at = datetime.strptime(f"{month} {day} {year} {clock.replace(' ', '')}", "%B %d %Y %I:%M%p")
    except ValueError as error:
        raise ValueError(f"the snow report's time could not be read: {error}") from error
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": lift_rows(page), "Trails": []}, *trail_areas(page)]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
