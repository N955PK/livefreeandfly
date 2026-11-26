"""Eaglecrest's lifts and trails, and its snow report, from its conditions page (skieaglecrest.com/conditions).

The page is built on the server, as tables the ski area fills in by hand, and each is known here by the words
that head its columns. "CHAIRLIFT, STATUS" is the chairlifts, each with its status in words; the table ends with
a line for the hours of operation, which is not a lift. "Trail, Status" is the grooming and trail report, and
"TERRAIN, STATUS" the gates to the terrain beyond the trails; the Nordic trails' table is headed by the day it was
updated and is not read. A line that runs across a table as one cell is a note (a link, the gates' closing time)
and is not read. Statuses are carried as the page says them. The page gives no trail's difficulty. The chairlifts
and trails are one mountain area and the gated terrain another. Every other row of the three tables has to be a
name and a status, so a change in the page's shape fails instead of showing wrong numbers.

The snow report is the table headed "CONDITIONS, BASE, SUMMIT": the new snow of the last 12 hours, the snowpack
and the season's snowfall, at the base and at the summit, in inches. The ski area leaves it empty out of season,
and a table with no snowpack in it gives no snow report. It does not say when it was filled in, so it is carried
undated. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://skieaglecrest.com/conditions/"
NAME = "Eaglecrest"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The tables, by the words that head their columns.
LIFTS, TRAILS, GATES, SNOW = ("chairlift", "status"), ("trail", "status"), ("terrain", "status"), \
    ("conditions", "base", "summit")
# The line that ends the chairlifts' table and is not a lift.
NOT_LIFTS = re.compile(r"hours of operation", re.I)
# The snow table's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"new snow: 12hrs": "Last12HoursIn", "snowpack": "BaseIn", "season snowfall": "SeasonTotalIn"}
STAKES = {"BaseArea": "Base", "SummitArea": "Summit"}
TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
HEAD = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S)
CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\"|in\.?|inches)?", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def tables(page: str) -> dict:
    """The page's tables, each under the words that head its columns, as rows of cells."""
    found = {}
    for body in TABLE.findall(page):
        heads = tuple(words(head).lower() for head in HEAD.findall(body))
        rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(body)]
        if heads in found:
            raise ValueError(f"the page has two tables headed {heads}")
        found[heads] = [row for row in rows if row]
    return found


def status_rows(rows: list, what: str, difficulty: str | None) -> list:
    """The rows of a table of names and statuses, each status in the page's words; a one-cell row is a note."""
    out = []
    for row in rows:
        if len(row) == 1:
            continue
        if len(row) != 2 or not row[0] or not row[1]:
            raise ValueError(f"a row of the {what} is not a name and a status: {row}")
        said = row[1].capitalize()
        out.append({"Name": row[0], "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty})
    if len({row["Name"] for row in out}) != len(out):
        raise ValueError(f"the {what} list a name twice")
    return out


def inches(said: str, label: str) -> float | int | None:
    if not said:
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(rows: list | None) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the base and the summit, undated."""
    if rows is None:
        raise ValueError("the table of conditions at the base and the summit was not found")
    said = {row[0].lower(): row[1:] for row in rows if len(row) == 3}
    missing = [label for label in SNOWFALL if label not in said]
    if missing:
        raise ValueError(f"the snow report has no line for {missing}")
    out = {}
    for at, (area, place) in enumerate(STAKES.items()):
        out[area] = {"Name": place, **{field: inches(said[label][at], f"{label} at the {place.lower()}")
                                       for label, field in SNOWFALL.items()}}
    if out["BaseArea"]["BaseIn"] is None and out["SummitArea"]["BaseIn"] is None:
        raise ValueError("the snow report gives no snowpack")
    season = out["SummitArea"].pop("SeasonTotalIn")
    out["BaseArea"].pop("SeasonTotalIn")
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season, **out,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    found = tables(page)
    missing = [heads for heads in (LIFTS, TRAILS, GATES) if heads not in found]
    if missing:
        raise ValueError(f"the page has no table headed {missing}")
    lifts = status_rows([row for row in found[LIFTS] if not NOT_LIFTS.search(row[0])], "chairlifts", None)
    trails, gates = status_rows(found[TRAILS], "trails", ""), status_rows(found[GATES], "gated terrain", "")
    if not lifts or not trails:
        raise ValueError("the page lists no chairlifts or no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails},
                              {"Name": "Gate Access", "Lifts": [], "Trails": gates}]}
    try:
        feed["SnowReport"] = snow_report(found.get(SNOW))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
