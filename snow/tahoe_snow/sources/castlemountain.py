"""Castle Mountain's lifts and trails, and its snow report, from its snow report page (skicastle.ca/snowreport).

The page is built on the server. Its lift table is a row for each lift: its name, a status symbol and a message.
Its trails are a table for each zone of the mountain (the Chutes, and the trails of each chair), each a mountain
area here; the lifts name no zone and are an area of their own. A lift's or trail's status is its symbol's name, in
the words of the page's own key (Open, Expected, On Hold, Delayed, Closed), and a status the reader does not know
fails. A trail's first symbol is its difficulty (a green circle, a blue square, a black diamond, a double black
diamond; a terrain park has none), and its last cell says whether it is groomed. The page's own counts of lifts and
of trails, open and in all, are checked against what is read, so a change in its shape fails instead of showing
wrong numbers.

The snow table gives, at mid-mountain, the fresh snow of the last 12, 24, 48 and 72 hours and 7 days, the
season's snowfall and the snow base, under a line saying when it was updated in Mountain time. **The page reports
centimetres; they are converted to inches here (divided by 2.54, to one decimal).** The page gives no word for the
surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.skicastle.ca/snowreport/"
NAME = "Castle Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Edmonton")
CM_PER_INCH = 2.54
# The status symbols' names, in the words of the page's key ("Stopped" is the name of the On Hold symbol's file).
STATUSES = {"open": "Open", "expected": "Expected", "on hold": "On hold", "stopped": "On hold", "delayed": "Delayed",
            "closed": "Closed"}
# The difficulty symbols' names, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"green circle": "Green", "blue square": "Blue", "black diamond": "Black",
          "double black diamond": "Double black", "terrain parks": ""}
# The snow table's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Fresh Snow (12 hrs)": "Last12HoursIn", "Fresh Snow (24 hrs)": "Last24HoursIn",
            "Fresh Snow (48 hrs)": "Last48HoursIn", "Fresh Snow (72 hrs)": "Last72HoursIn",
            "Last 7 days": "Last7DaysIn", "Total Snowfall this season": "SeasonTotalIn", "Snow Base": "BaseIn"}
LIFT_TABLE = re.compile(r"<table class=\"cml-table cml-lifts\">(.*?)</table>", re.S)
ZONE = re.compile(r"<div class=\"cml-zone-list\" id=\"([^\"]+)\"[^>]*>\s*<table class=\"cml-table cml-trails\">(.*?)"
                  r"</table>", re.S)
ZONE_NAME = re.compile(r"<option value=\"([^\"]+)\">([^<]*)</option>")
BODY = re.compile(r"<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
SYMBOL = re.compile(r"<img [^>]*\balt=\"([^\"]*)\"(?: title=\"([^\"]*)\")?")
COUNT = r"<p class=\"cml-count\"><strong>(\d+)</strong> of (\d+) {kind} open</p>"
SNOW_TABLE = re.compile(r"<table class=\"cml-table cml-snow\">(.*?)</table>\s*"
                        r"<p class=\"cml-updated\">Last updated: (\d{4}-\d{2}-\d{2}) - (\d{2}:\d{2}) MT</p>", re.S)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def table_rows(table: str, width: int) -> list:
    """The cells of each row of a table's body, which all have to be ``width`` cells wide."""
    body = BODY.search(table)
    rows = [CELL.findall(row) for row in ROW.findall(body.group(1))] if body else []
    if not rows or any(len(cells) != width for cells in rows):
        raise ValueError(f"a table is not rows of {width} cells")
    return rows


def status_row(name: str, cell: str, difficulty: str | None) -> dict:
    """A lift or a trail with the status its symbol names."""
    symbol = SYMBOL.search(cell)
    said = html.unescape(symbol.group(1)).strip() if symbol else ""
    if not name or said.lower() not in STATUSES:
        raise ValueError(f"{name or 'a row'} has the status {said!r}, not one the reader knows")
    status = STATUSES[said.lower()]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(cells: list) -> dict:
    level, name, status, grooming = cells
    name, symbol, groomed = words(name), SYMBOL.search(level), words(grooming).lower()
    said = html.unescape(symbol.group(1)).strip().lower() if symbol else None
    if said not in LEVELS:
        raise ValueError(f"{name} has a difficulty symbol the reader does not know: {said!r}")
    if groomed and "groomed" not in groomed:
        raise ValueError(f"{name}'s grooming reads {groomed!r}, which the reader does not know")
    return {**status_row(name, status, LEVELS[said]),
            "Grooming": "Yes" if groomed and not groomed.startswith("not") else "No"}


def checked(rows: list, page: str, kind: str) -> None:
    """The page's own count of lifts or trails, open and in all, has to match what was read."""
    counted = re.search(COUNT.format(kind=kind), page)
    if not counted:
        raise ValueError(f"the page's count of {kind} was not found")
    is_open, total = (int(figure) for figure in counted.groups())
    read = sum(row["StatusEnglish"] == "open" for row in rows)
    if total != len(rows) or is_open != read:
        raise ValueError(f"the page counts {is_open} of {total} {kind} open but {read} of {len(rows)} were read")


def inches(centimetres: float) -> float:
    return round(centimetres / CM_PER_INCH, 1)


def snow_report(page: str) -> dict:
    """The page's snow table in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    found = SNOW_TABLE.search(page)
    if not found or "Snow Fall (cm)" not in found.group(1):
        raise ValueError("the snow table in centimetres, or the time it was updated, was not found")
    figures = {}
    for label, said in table_rows(found.group(1), 2):
        label, said = words(label), words(said)
        if label not in SNOWFALL or SNOWFALL[label] in figures or not NUMBER.fullmatch(said):
            raise ValueError(f"the snow table's {label!r} reads {said!r}, not centimetres the reader knows, once")
        figures[SNOWFALL[label]] = inches(float(said))
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow table has no snow base or no 24 hour snowfall")
    try:
        at = datetime.strptime(f"{found.group(2)} {found.group(3)}", "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise ValueError(f"the snow table's time could not be read: {error}") from error
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "MidMountainArea": {"Name": "Mid Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lift_table = LIFT_TABLE.search(page)
    if not lift_table:
        raise ValueError("the lift table was not found")
    lifts = [status_row(words(name), status, None) for _, name, status, _ in table_rows(lift_table.group(1), 4)]
    names = {mark: words(name) for mark, name in ZONE_NAME.findall(page)}
    areas = []
    for mark, table in ZONE.findall(page):
        if not names.get(mark) or any(area["Name"] == names[mark] for area in areas):
            raise ValueError(f"a zone of trails has no name or is listed twice: {mark}")
        areas.append({"Name": names[mark], "Lifts": [], "Trails": [trail_row(cells) for cells in table_rows(table, 4)]})
    if page.count("cml-trails") != len(areas) or not areas:
        raise ValueError(f"the page has {page.count('cml-trails')} trail tables but {len(areas)} were read")
    checked(lifts, page, "lifts")
    checked([trail for area in areas for trail in area["Trails"]], page, "trails")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
