"""Horseshoe Valley's lifts and runs, and its snow report, from its ski report page
(horseshoeresort.com/ski-report-trails).

The page is built on the server. Its Alpine part is a table of runs for each difficulty (Easy, Difficult, More
Difficult, by their symbols the green circle, the blue square and the black diamond) and one for the terrain park,
which has no difficulty; its Chair Lifts part is one table of lifts. The lifts are one mountain area and each
table of runs another. The page's cross-country trails are in tables of their own further down and are not read.

Every row has two statuses, one for the day's skiing and one for the night's, under the hours of each ("9:00am -
4:30pm", "3:30pm - 9:00pm"). A row is read in the day's column until the day's hours end and in the night's from
then on, by the resort's own clock. A status is the mark on its cell (open, closed, or not available, which is a
run that is not skied at night and reads closed), which has to agree with the cell's words; a mark the reader
does not know fails. The page does not say what is groomed. Every row of the page's tables is one read, so a
change in its shape fails instead of showing wrong numbers.

The page gives the day it was updated, without a time; the report is dated the start of that day. The resort
leaves its last report of the season up all summer and autumn, so a page more than OLD_DAYS old that has anything
open is refused: its statuses are last season's. The snow report is the snowfall of the last 24 hours and the base
depth, one depth or a low and a high, in centimetres, turned into inches here (divided by 2.54, to one decimal),
and the surface in words; the depth and the surface are left empty out of season. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://horseshoeresort.com/ski-report-trails/"
NAME = "Horseshoe Valley"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
CM_PER_INCH = 2.54
# A page older than this with a lift or a run open is last season's, left up after the mountain closed.
OLD_DAYS = 14
# The symbols over the tables of runs, in the words the app's difficulty symbols are keyed on; the park has none.
LEVELS = {"green circle": "Green", "blue square": "Blue", "black diamond": "Black",
          "double black diamond": "Double black", "orange pill": ""}
# The marks on a status cell, as the status carried.
STATUSES = {"open": "Open", "closed": "Closed", "not-available": "Closed"}
SECTION = re.compile(r"<section[^>]*\sclass=\"report report-(alpine|lifts)\"[^>]*>(.*?)</section>", re.S)
TABLE = re.compile(r"<table class=\"report-table\">(.*?)</table>", re.S)
HEADING = re.compile(r"<th class=\"run-level\">(.*?)</th>", re.S)
PERIOD = re.compile(r"<th class=\"time-period\">(.*?)</th>", re.S)
HOURS = re.compile(r"(\d{1,2}):(\d{2})\s*([ap]m)\s*-\s*(\d{1,2}):(\d{2})\s*([ap]m)")
ALT = re.compile(r"<img [^>]*\balt=\"([^\"]*)\"")
BODY = re.compile(r"<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELLS = re.compile(r"\s*<td>(.*?)</td>\s*<td class=\"([a-z-]+)\">(.*?)</td>\s*<td class=\"([a-z-]+)\">(.*?)</td>\s*",
                   re.S)
UPDATED = re.compile(r"<div class=\"updated\">\s*Updated:\s*([A-Z][a-z]+day, [A-Z][a-z]+ \d{1,2}, \d{4})\s*</div>")
SNOWFALL = re.compile(r"<div class=\"weather-entry snowfall\">\s*<h3>Snowfall \(Past 24<span class=\"unit\">hrs</span>"
                      r"\)</h3>.*?<span class=\"data\">([^<]*)</span><span class=\"unit\">cm</span>", re.S)
LINE = re.compile(r"<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
DEPTH = re.compile(r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*(?:cm)?", re.I)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
NOSCRIPT = re.compile(r"<noscript>.*?</noscript>", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def clock(hour: str, minute: str, half: str) -> time:
    return time(int(hour) % 12 + (12 if half == "pm" else 0), int(minute))


def column(table: str, now: datetime) -> int:
    """Which of a table's two status columns holds at ``now``: the day's until its hours end, then the night's."""
    periods = [HOURS.fullmatch(words(period)) for period in PERIOD.findall(table)]
    if len(periods) != 2 or not all(periods):
        raise ValueError("a table is not headed by the hours of the day's and the night's skiing")
    day_ends, night_starts = clock(*periods[0].groups()[3:]), clock(*periods[1].groups()[:3])
    if night_starts > day_ends:
        raise ValueError("the night's skiing does not start by the end of the day's")
    return 1 if now.astimezone(EASTERN_TIME).time() >= day_ends else 0


def status_rows(table: str, now: datetime, difficulty: str | None) -> list:
    """The lifts or runs of one table, each with the status of the part of the day ``now`` is in."""
    at, body = column(table, now), BODY.search(table)
    rows = []
    for row in ROW.findall(body.group(1)) if body else []:
        cells = CELLS.fullmatch(row)
        if not cells:
            raise ValueError("a row is not a name and a status for the day and for the night")
        name, marked, said = words(cells.group(1)), cells.group(2 + 2 * at), words(cells.group(3 + 2 * at))
        if not name or marked not in STATUSES:
            raise ValueError(f"{name or 'a row'} is marked {marked!r}, not a status the reader knows")
        if marked != "-".join(said.lower().split()):
            raise ValueError(f"{name} is marked {marked} but reads {said!r}")
        status = STATUSES[marked]
        rows.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty})
    if not rows:
        raise ValueError("a table has no rows")
    return rows


def run_areas(alpine: str, now: datetime) -> list:
    """Each table of runs as a mountain area named by its heading, its difficulty the heading's symbol."""
    areas = []
    for table in TABLE.findall(alpine):
        heading = HEADING.search(table)
        symbol = ALT.search(heading.group(1)) if heading else None
        name = words(NOSCRIPT.sub(" ", heading.group(1))) if heading else ""
        level = html.unescape(symbol.group(1)).strip().lower() if symbol else None
        if not name or level not in LEVELS or any(area["Name"] == name for area in areas):
            raise ValueError(f"a table of runs is headed {name!r} with the symbol {level!r}, which the reader does "
                             "not know, or twice")
        areas.append({"Name": name, "Lifts": [], "Trails": status_rows(table, now, LEVELS[level])})
    return areas


def updated(page: str) -> datetime:
    """The day the page was updated, as the start of that day by the resort's clock."""
    found = UPDATED.search(page)
    if not found:
        raise ValueError("the page does not say when it was updated")
    try:
        day = datetime.strptime(found.group(1), "%A, %B %d, %Y")
    except ValueError as error:
        raise ValueError(f"the page's date could not be read: {error}") from error
    return day.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc)


def inches(centimetres: str) -> float:
    return round(float(centimetres) / CM_PER_INCH, 1)


def snow_report(page: str, alpine: str, at: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    snowfall = SNOWFALL.search(page)
    if not snowfall or not NUMBER.fullmatch(snowfall.group(1).strip()):
        raise ValueError("the snowfall of the last 24 hours was not found in centimetres")
    area = {"Name": "Base", "Last24HoursIn": inches(snowfall.group(1).strip())}
    lines = {words(label): words(said) for label, said in LINE.findall(alpine)}
    if "Base Depth" not in lines or "Conditions" not in lines:
        raise ValueError("the Alpine report has no base depth line or no conditions line")
    if lines["Base Depth"]:
        depth = DEPTH.fullmatch(lines["Base Depth"])
        if not depth:
            raise ValueError(f"the base depth reads {lines['Base Depth']!r}, not centimetres")
        if depth.group(2):
            area.update({"BaseMinIn": inches(depth.group(1)), "BaseMaxIn": inches(depth.group(2))})
        else:
            area["BaseIn"] = inches(depth.group(1))
    return {"LastUpdate": at.strftime(STAMP), "Resortwide": True, "BaseConditions": lines["Conditions"] or None,
            "SeasonTotalIn": None, "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    # The page keeps an old cross-country part, and a note under the lifts, inside comments: they are not read.
    page = COMMENT.sub("", page)
    sections = dict(SECTION.findall(page))
    if set(sections) != {"alpine", "lifts"}:
        raise ValueError("the Alpine and the Chair Lifts parts of the report were not found")
    lift_tables = TABLE.findall(sections["lifts"])
    if len(lift_tables) != 1:
        raise ValueError(f"the Chair Lifts part has {len(lift_tables)} tables, not one")
    lifts, areas = status_rows(lift_tables[0], now, None), run_areas(sections["alpine"], now)
    rows = lifts + [trail for area in areas for trail in area["Trails"]]
    listed = sum(section.count("<tr>") - section.count("<table") for section in sections.values())
    if not areas or len(rows) != listed:
        raise ValueError(f"the page has {listed} rows of lifts and runs but {len(rows)} were read")
    at = updated(page)
    if now - at > timedelta(days=OLD_DAYS) and any(row["StatusEnglish"] == "open" for row in rows):
        raise ValueError(f"the page was last updated {at:%Y-%m-%d} and has lifts or runs open: it is last season's")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page, sections["alpine"], at)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
