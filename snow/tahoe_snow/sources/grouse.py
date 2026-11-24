"""Grouse Mountain's lifts and runs, and its snow report, from its current conditions page
(grousemountain.com/current_conditions).

The page is built on the server. Under its snow report it has a set of tabs, and in winter two of them are a list
of lifts and a list of runs: each row a name, a note and a status, the status being the row's word (Open, Closed)
carried as the page says it. A run's difficulty is the symbol before its name (green, blue, diamond, double
diamond), and a symbol the reader does not know fails. Before the season the page has its tabs but none for lifts
or runs: the mountain is then given with no lifts, which the runner reads as nothing posted. A page without the
tabs at all fails. The terrain parks and the snowshoe park have tabs of their own and are left out.

The snow report gives the depth at the Peak and on the Plateau (where the lifts start), and the snowfall
overnight, over 24 and 48 hours and seven days and the season's total. Grouse reports in centimetres (with its own
whole inches beside them): every figure here is the page's centimetres divided by 2.54 and rounded to one decimal,
to give the inches the Ikon feed's fields hold. The snowfall is the mountain's, and is carried with the Plateau's
depth. The page gives the report's time of day ("3:00 PM Report") but no date, so the report is undated here:
LastUpdate is None and the time is carried as the page writes it. A snow report that cannot be read costs only the
snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.grousemountain.com/current_conditions"
NAME = "Grouse Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The run symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"runs-green": "Green", "runs-blue": "Blue", "runs-diamond": "Black", "runs-double-diamond": "Double black"}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those); None is left out.
SNOWFALL = {"12hrs": None, "Overnight": "OvernightIn", "24hrs": "Last24HoursIn", "48hrs": "Last48HoursIn",
            "Seven Days": "Last7DaysIn", "Total This Season": "SeasonTotalIn", "Depth Peak": "Peak",
            "Depth Plateau": "Plateau"}
TABS = re.compile(r"<div class='conditions_tabs' id='conditions'>")
TAB = re.compile(r"<div class='tab' id='([a-z_]+)'[^>]*>(.*?)(?=<div class='tab' id='|\Z)", re.S)
LIST = re.compile(r"<ul class='data-table'>(.*?)</ul>", re.S)
ROW = re.compile(r"<li>(.*?)</li>", re.S)
# A row: the name's cell, the note's cell, and the status' cell, whose class is the status.
CELLS = re.compile(r"\s*<span>(.*?)</span>\s*<span>\s*<div class='note'>.*?</div>\s*</span>\s*"
                   r"<span class='([a-z_-]+)'>(.*?)</span>\s*", re.S)
SYMBOL = re.compile(r"<span class='(runs-[a-z-]+)'></span>")
DETAILS = re.compile(r"<div class='details'>.*?</div>", re.S)
TAG = re.compile(r"<[^>]+>")
SNOW_REPORT = re.compile(r"<div class='conditions-snow-report__content'>(.*?)<div class='conditions", re.S)
FIGURE = re.compile(r"<li>\s*<p>\s*([^<]*?)\s*</p>\s*<h3 class='metric'>\s*([^<]*?)\s*</h3>")
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*cm")
REPORT_TIME = re.compile(r"<p>\s*(\d{1,2}:\d{2} [AP]M)\s*<span class='time report-label'>\s*Report\s*</span>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def rows_of(tab: str, runs: bool) -> list:
    """The lifts or the runs of a tab, in the page's order."""
    listed = LIST.search(tab)
    if not listed:
        raise ValueError("a tab has no list")
    rows = []
    for item in ROW.findall(listed.group(1)):
        cells = CELLS.fullmatch(item)
        if not cells:
            raise ValueError("a row is not a name, a note and a status")
        symbols = SYMBOL.findall(cells.group(1))
        name, status = words(DETAILS.sub(" ", cells.group(1))), words(cells.group(3)).capitalize()
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a row'} has the status {status!r}, not a word")
        if runs and (len(symbols) != 1 or symbols[0] not in LEVELS):
            raise ValueError(f"{name} has difficulty symbols {symbols}, not one the reader knows")
        rows.append({"Name": name, "Status": status, "StatusEnglish": status.lower(),
                     "Difficulty": LEVELS[symbols[0]] if runs else None})
    return rows


def inches(said: str, heading: str) -> float:
    centimetres = CENTIMETRES.fullmatch(html.unescape(said))
    if not centimetres:
        raise ValueError(f"the snow report's {heading} reads {said!r}, not centimetres")
    return round(float(centimetres.group(1)) / CM_PER_INCH, 1)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the Plateau's depth at the base and the
    Peak's at the summit, with the mountain's snowfall beside the Plateau's."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    figures = {}
    for heading, said in FIGURE.findall(block.group(1)):
        if heading not in SNOWFALL or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report has a figure the reader does not know, or has it twice: {heading}")
        if SNOWFALL[heading]:
            figures[SNOWFALL[heading]] = inches(said, heading)
    if "Plateau" not in figures or "Peak" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no depth at the Peak or on the Plateau, or no 24 hour snowfall")
    peak, plateau, season = figures.pop("Peak"), figures.pop("Plateau"), figures.pop("SeasonTotalIn", None)
    time = REPORT_TIME.search(page)
    return {"LastUpdate": None, "ReportTime": time.group(1) if time else None, "Resortwide": False,
            "BaseConditions": None, "SeasonTotalIn": season, "BaseArea": {"Name": "Plateau", "BaseIn": plateau, **figures},
            "SummitArea": {"Name": "Peak", "BaseIn": peak}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    start = TABS.search(page)
    if not start:
        raise ValueError("the page's tabs were not found")
    tabs = dict(TAB.findall(page, start.end()))
    if not tabs:
        raise ValueError("the page's tabs are empty")
    if ("lifts" in tabs) != ("runs" in tabs):
        raise ValueError("the page has a tab for lifts or for runs but not both")
    # Before the season there is no tab for lifts or runs: nothing is posted, and nothing is made up.
    lifts = rows_of(tabs["lifts"], False) if "lifts" in tabs else []
    runs = rows_of(tabs["runs"], True) if "runs" in tabs else []
    if "lifts" in tabs and (not lifts or not runs):
        raise ValueError("the page's tab of lifts or of runs lists nothing")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": runs}]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
