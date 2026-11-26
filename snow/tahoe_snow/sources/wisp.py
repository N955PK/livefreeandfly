"""Wisp's lifts and trails, and its snow report, from its mountain report page (wispresort.com/mountain-report-cams).

Wisp and Wintergreen are Pacific Group Resorts mountains whose sites share one layout, so the reading is here
(``feed``) and Wintergreen's module calls it. The page is built on the server: a table of the lifts, and a table of
runs under a heading for each part of the mountain. A lift's status is the word in its row, carried as the page
says it. A run's status is a picture, so it is read from the name the page gives the picture's cell (closed,
open), carried the same way. A run's difficulty is the symbol before its name (green, blue, black, double black,
park), and a symbol the reader does not know fails; a terrain park has none. The lifts are one mountain area and
each part of the mountain another. The tables under headings that are not of the lift-served mountain (Wisp's
Mountain Park, which is its coaster and its tubing) are left out. The page's count of runs is not checked: Wisp
counts 33 over 34 rows.

The snow report gives the snow overnight and over the last 24 and 48 hours, the base depth, as one depth or a low
and a high, and the season's total, in inches. Before the mountain opens the figures are blank, which reads as no
snow report. The page does not say when it was written, so the report is undated, and it gives no word for the
surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.wispresort.com/mountain-report-cams/"
NAME = "Wisp"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The headings over tables that are not of the lift-served mountain.
LEFT_OUT = frozenset({"Mountain Park"})
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on; a park has none.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "doubleblack": "Double black", "park": ""}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Overnight": "OvernightIn", "Last 24 hrs.": "Last24HoursIn", "Last 48 hrs.": "Last48HoursIn"}
SECTION = r"<section class=\"lift-section {kind}\"[^>]*>(.*?)</section>"
HEADING_OR_TABLE = re.compile(r"<h5[^>]*>(.*?)</h5>|<table class=\"table\">(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td data-title=\"([^\"]*)\"(?:\s+class=\"([^\"]*)\")?\s*>(.*?)</td>", re.S)
SYMBOL = re.compile(r"/themes/pgri/images/([a-z]+)\.svg")
FIGURE = re.compile(r"<h6>([^<]*)</h6>\s*<h3>([^<]*)</h3>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")?\s*(?:-|–)\s*(\d+(?:\.\d+)?)\s*(?:”|\")?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def section(page: str, kind: str, what: str) -> str:
    found = re.search(SECTION.format(kind=kind), page, re.S)
    if not found:
        raise ValueError(f"the page's {what} were not found")
    return found.group(1)


def rows_of(table: str, named: str) -> list:
    """The rows of a table: each a name, the status its row gives, and the symbols before the name (the page
    writes a symbol twice where it loads its pictures late)."""
    rows = []
    for row in ROW.findall(table):
        cells = {title: (kind or "", markup) for title, kind, markup in CELL.findall(row)}
        if not cells:
            continue
        if named not in cells or "Status" not in cells:
            raise ValueError(f"a row is not a {named.lower()} and a status")
        name = words(cells[named][1])
        # A lift's status is written out; a run's is a picture, and the cell is named for it.
        status = (words(cells["Status"][1]) or cells["Status"][0]).capitalize()
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a row'} has the status {status!r}, not a word")
        rows.append(({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None},
                     sorted(set(SYMBOL.findall(cells.get("", ("", ""))[1])))))
    return rows


def lift_rows(page: str) -> list:
    tables = [table for _, table in HEADING_OR_TABLE.findall(section(page, "lift-section-main", "lifts")) if table]
    if len(tables) != 1:
        raise ValueError(f"the page has {len(tables)} tables of lifts, not one")
    return [lift for lift, _ in rows_of(tables[0], "Lift Name")]


def trail_areas(page: str, left_out: frozenset) -> list:
    """The runs of each lift-served part of the mountain, in the page's order."""
    areas, heading = [], None
    for said, table in HEADING_OR_TABLE.findall(section(page, "lift-section-main slopes-section", "runs")):
        if not table:
            heading = words(said)
            continue
        if not heading:
            raise ValueError("a table of runs is under no heading")
        if heading in left_out:
            continue
        trails = []
        for trail, symbols in rows_of(table, "Run Name"):
            if len(symbols) != 1 or symbols[0] not in LEVELS:
                raise ValueError(f"{trail['Name']} has difficulty symbols {symbols}, not one the reader knows")
            trails.append({**trail, "Difficulty": LEVELS[symbols[0]]})
        areas.append({"Name": heading, "Lifts": [], "Trails": trails})
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page has two tables of runs under one heading")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    figures = {words(label): words(said) for label, said in FIGURE.findall(section(page, "snow-conditions",
                                                                                   "snow figures"))}
    depth = figures.get("Current Base", "")
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
    for label, field in SNOWFALL.items():
        said = INCHES.fullmatch(figures.get(label, ""))
        area[field] = number(said.group(1)) if said else None
    season = INCHES.fullmatch(figures.get("Season Total", ""))
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": number(season.group(1)) if season else None, "BaseArea": area, "Report": None,
            "Alert": None}


def feed(page: str, now: datetime, name: str, left_out: frozenset = frozenset()) -> dict:
    """One Pacific Group Resorts mountain's page, in the shape of the Ikon feed."""
    lifts, areas = lift_rows(page), trail_areas(page, left_out)
    if not lifts or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no runs")
    found = {"Name": name, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
             "MountainAreas": [{"Name": name, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        found["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return found


def parse(page: str, now: datetime) -> dict:
    return feed(page, now, NAME, LEFT_OUT)
