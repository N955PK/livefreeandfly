"""Powder King's lifts and runs, and its snow report, from its ski report page (powderking.com/mountain/ski-report).

The page is built on the server from text the resort edits by hand. Under "LIFT REPORT:" is a line for each lift,
"CHAIR LIFT - Closed": the status is the words after the last dash, carried as the page says them, and the lifts
are given with a capital on each word ("T - BAR" as "T-Bar"). Under "OPEN RUN REPORT:" are two tables with a row
for each run: a dot whose colour is the difficulty (green for easiest, blue for more difficult, and uncoloured
for most difficult, as the page's own key has it), the run's number and name, and its status. Two runs give a
status for their upper and their lower half, and each half is a run here ("No Where Man (Upper)"). The runs'
numbers are left off their names. The lifts and the runs are one mountain area. The page says nothing of grooming
run by run, so none is given. A line or a row the reader does not know fails instead of showing wrong numbers.

Under "SNOW BASE" the page says when it was last updated (Pacific time) over a table of the snow of the last 24,
48 and 72 hours and the base depth at the Day Lodge, the Top Chair and the Top T-Bar. **The table is in
centimetres; they are converted to inches here (divided by 2.54, to one decimal).** The page gives no word for the
surface and no season total. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.powderking.com/mountain/ski-report"
NAME = "Powder King"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# The classes that colour a run's dot, in the words the app's difficulty symbols are keyed on; a dot with no
# colour is the page's "Most Difficult/Advanced".
LEVELS = {"green": "Green", "green2": "Green", "blue": "Blue", "blue2": "Blue"}
DOT = "⬤"
# The places of the snow table, by the names the Ikon feed gives its stakes (the app reads those).
STAKES = {"Day Lodge": "BaseArea", "Top Chair": "MidMountainArea", "Top T-Bar": "SummitArea"}
# The snow table's columns after the place, by the names the Ikon feed gives them; the temperature is not kept.
COLUMNS = ("24 Hour", "48 Hour", "72 Hour", "Base cm")
FIELDS = ("Last24HoursIn", "Last48HoursIn", "Last72HoursIn", "BaseIn")
LIFTS = re.compile(r"LIFT REPORT:(.*?)<h2[^>]*>\s*Grooming Report", re.S)
RUNS = re.compile(r"<h2[^>]*>\s*OPEN RUN REPORT:(.*?)<footer", re.S)
SNOW = re.compile(r"SNOW BASE(.*?)<table[^>]*>(.*?)</table>", re.S)
BLOCK = re.compile(r"</(?:p|h\d|div|li)>|<br\s*/?>")
TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
SPAN_CLASS = re.compile(r"<span[^>]*\sclass=\"([^\"]*)\"")
TAG = re.compile(r"<[^>]+>")
LIFT_LINE = re.compile(r"(.*\S)\s+-\s*([A-Za-z][A-Za-z ]*)")
RUN_NAME = re.compile(r"\d+\s+(\S.*)")
STATUS = re.compile(r"[A-Za-z][A-Za-z ]*")
HALVES = re.compile(r"Upper:\s*([A-Za-z][A-Za-z ]*?)\s*Lower:\s*([A-Za-z][A-Za-z ]*)")
UPDATED = re.compile(r"LAST UPDATED:\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])\s+[A-Za-z]+,?\s+([A-Za-z]+)\s+(\d{1,2})"
                     r"(?:st|nd|rd|th)?,?\s+(\d{4})")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, unseen characters out, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).replace("​", "").split())


def said(status: str) -> dict:
    status = " ".join(status.split()).capitalize()
    return {"Status": status, "StatusEnglish": status.lower()}


def lifts_of(page: str) -> list:
    """The lifts under "LIFT REPORT:", in the page's order."""
    section = LIFTS.search(page)
    if not section:
        raise ValueError("the lift report was not found")
    lifts = []
    for line in filter(None, map(words, BLOCK.split(section.group(1)))):
        read = LIFT_LINE.fullmatch(line)
        if not read:
            raise ValueError(f"a line of the lift report reads {line!r}, not a name, a dash and a status")
        # "T - BAR" is one name with a dash in it; a word in capitals is given a capital on its first letter only.
        name = re.sub(r"\s*-\s*", "-", read.group(1))
        name = re.sub(r"[A-Z]{2,}", lambda word: word.group().capitalize(), name)
        lifts.append({"Name": name, **said(read.group(2)), "Difficulty": None})
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the lift report names a lift twice")
    return lifts


def difficulty(cell: str, name: str) -> str:
    """A run's difficulty from the colour of its dot."""
    if words(cell) != DOT:
        raise ValueError(f"{name} has {words(cell)!r} where its difficulty's dot should be")
    colours = SPAN_CLASS.findall(cell)
    if not colours:
        return "Black"
    if len(set(colours)) != 1 or colours[0] not in LEVELS:
        raise ValueError(f"{name} has a dot coloured {colours}, not a colour the reader knows")
    return LEVELS[colours[0]]


def runs_of(page: str) -> list:
    """The runs of the tables under "OPEN RUN REPORT:", in the page's order."""
    section = RUNS.search(page)
    if not section:
        raise ValueError("the run report was not found")
    runs = []
    for table in TABLE.findall(section.group(1)):
        for row in ROW.findall(table):
            cells = CELL.findall(row)
            if len(cells) != 3:
                raise ValueError("a row of the run report is not a dot, a name and a status")
            numbered = RUN_NAME.fullmatch(words(cells[1]))
            if not numbered:
                raise ValueError(f"a run is written {words(cells[1])!r}, not a number and a name")
            name, status, level = numbered.group(1), words(cells[2]), difficulty(cells[0], numbered.group(1))
            halves = HALVES.fullmatch(status)
            if halves:
                runs += [{"Name": f"{name} ({half})", **said(given), "Difficulty": level}
                         for half, given in zip(("Upper", "Lower"), halves.groups())]
            elif STATUS.fullmatch(status):
                runs.append({"Name": name, **said(status), "Difficulty": level})
            else:
                raise ValueError(f"{name} has the status {status!r}, not a word")
    if len({run["Name"] for run in runs}) != len(runs):
        raise ValueError("the run report names a run twice")
    return runs


def inches(given: str, what: str) -> float | None:
    """A figure of the table's centimetres in inches, to one decimal, or None where the table gives none."""
    given = given.lower().removesuffix("cm").strip()
    if not given:
        return None
    try:
        return round(float(given) / CM_PER_INCH, 1)
    except ValueError as error:
        raise ValueError(f"the snow table's {what} reads {given!r}, not a number") from error


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: a set for each place with a base."""
    section = SNOW.search(page)
    if not section:
        raise ValueError("the snow table was not found")
    updated = UPDATED.search(words(section.group(1)))
    if not updated:
        raise ValueError("the snow table does not say when it was last updated")
    hour, minute, half, month, day, year = updated.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute or '00'} {half.upper()}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow table's date could not be read: {error}") from error
    rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(section.group(2))]
    if not rows or tuple(rows[0][1:5]) != COLUMNS:
        raise ValueError("the snow table's columns are not the 24, 48 and 72 hour snow and the base in centimetres")
    stakes = {}
    for place, *figures in rows[1:]:
        if place not in STAKES or len(figures) < len(FIELDS) or STAKES[place] in stakes:
            raise ValueError(f"the snow table has a row the reader does not know: {place!r}")
        read = {field: inches(figure, f"{place} {column}") for field, column, figure in zip(FIELDS, COLUMNS, figures)}
        if read["BaseIn"] is not None:
            stakes[STAKES[place]] = {"Name": place, **{field: value for field, value in read.items()
                                                       if value is not None}}
    if not stakes or not any("Last24HoursIn" in stake for stake in stakes.values()):
        raise ValueError("the snow table has no base or no 24 hour snowfall")
    return {"LastUpdate": at.replace(tzinfo=LOCAL_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": False, "BaseConditions": None, "SeasonTotalIn": None, **stakes, "Report": None,
            "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, runs = lifts_of(page), runs_of(page)
    if not lifts or not runs:
        raise ValueError("the page lists no lifts or no runs")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": runs}]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
