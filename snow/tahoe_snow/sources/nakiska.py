"""Nakiska's lifts and open runs, and its snow report, from the figures its snow report page is filled with and
its open runs report (skinakiska.com/conditions/snow-report and /conditions/open-runs-report).

Nakiska is one of the Resorts of the Canadian Rockies, whose pages come from the server empty and are filled in
the browser by a hidden frame (skinakiska.com/refresh/refresh.php): a script that sets each figure on the page by
the name of its place. That frame is read here. A lift is a place whose figure is the lift's name, a colon and
its status in the page's own word, open or closed ("GOLD CHAIR: CLOSED", with when it next opens after it, which
is left out); the names come in capitals and are carried in title case. A status the reader does not know fails,
and the frame's own count of lifts operating is checked against what is read.

The site keeps no list of all its runs with their status: the open runs report lists only the runs that are open,
under the part of the mountain each is in (Nakiska, Monster Glades), which is its mountain area; the lifts name
no part and are carried with Nakiska's. So every run read is open, the closed ones are not listed, and nothing says here whether a
run is groomed. A run's difficulty is the mark on its row, read from the mark's name, and one the reader does not
know fails; a run marked between two difficulties is carried as the harder.

The snow report is one set of figures for the mountain: the snow pack (the base), the new snow overnight and of
the last 24 and 48 hours and 7 days, and the year's snowfall, with the surface of the upper and of the lower
mountain and when the report was saved, in the resort's own time. **The frame gives whole centimetres; they are
converted to inches here (divided by 2.54, to one decimal).** A snow report that cannot be read costs only the
snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SITE = "https://skinakiska.com"
URLS = {"status": f"{SITE}/refresh/refresh.php", "runs": f"{SITE}/conditions/open-runs-report/"}
NAME = "Nakiska"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Edmonton")
CM_PER_INCH = 2.54
STATUSES = {"OPEN": "Open", "CLOSED": "Closed"}
# The run marks' names, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green-circle": "Green", "green-circle-blue-square": "Blue", "blue-square": "Blue",
          "blue-square-black-diamond": "Black", "black-diamond": "Black", "double-black-diamond": "Double black"}
# The places of the snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"snowReportNewSnowFallPack": "BaseIn", "snowReportNewSnowFallOvernight": "OvernightIn",
            "snowReportNewSnowFall24": "Last24HoursIn", "snowReportNewSnowFall48": "Last48HoursIn",
            "snowReportNewSnowFall7days": "Last7DaysIn", "snowReportNewSnowFallYTD": "SeasonTotalIn"}
SURFACES = {"snowReportUpperMtnConditions": "upper", "snowReportLowerMtnConditions": "lower"}
SAVED = "snowReportTH_SnowreportRecentSnowSaveDate"
LIFTS_OPEN = "snowReportLiftsOpen"
PLACE = re.compile(r"getElementById\('(\w+)'\)\.innerHTML\s*=\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")\s*;")
LIFT = re.compile(r"([A-Z][A-Z0-9 '.&-]*?):\s*<span[^>]*>([^<]*)</span>")
LIFT_PLACE = re.compile(r"snowReport\w*Status\w*")
TABLE = re.compile(r"<table[^>]*class='table-groom table-bowl'[^>]*>(.*?)</table>", re.S)
PART = re.compile(r"<div class='bowl-title'>(.*?)</div>", re.S)
RUN = re.compile(r"<span class='run-name'>(.*?)</span>\s*<div class='ski-difficulty'>\s*<span class='([a-z-]*)'>",
                 re.S)
RUN_MARK = "<span class='run-name'>"
SUBTITLE = re.compile(r"<span class='rcr-element-box-conditions-subtitle'>.*?</span>", re.S)
STAMPED = re.compile(r"([A-Z]+) (\d{1,2}), (\d{4}) \| (\d{1,2}):(\d{2})\s*([ap]m)", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def places(frame: str) -> dict:
    """What the frame sets each place of the page to, by the place's name."""
    found = {name: one if one else two for name, one, two in PLACE.findall(frame)}
    if not found:
        raise ValueError("the frame sets no figures")
    return found


def lift_rows(set_to: dict) -> list:
    lifts = []
    for place, value in set_to.items():
        said = LIFT.match(value)
        if not LIFT_PLACE.fullmatch(place) or not said:
            continue
        name, status = " ".join(said.group(1).split()).title(), said.group(2).strip().upper()
        if status not in STATUSES:
            raise ValueError(f"{name} has a status the reader does not know: {said.group(2)!r}")
        lifts.append({"Name": name, "Status": STATUSES[status], "StatusEnglish": STATUSES[status].lower(),
                      "Difficulty": None})
    if not lifts or len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the frame lists no lifts, or lists one twice")
    opened = sum(lift["StatusEnglish"] == "open" for lift in lifts)
    if set_to.get(LIFTS_OPEN, "").strip() != str(opened):
        raise ValueError(f"the frame counts {set_to.get(LIFTS_OPEN)!r} lifts operating but {opened} of {len(lifts)} "
                         "were read open")
    return lifts


def open_runs(page: str) -> list:
    """The open runs report's runs under each part of the mountain, as mountain areas. Every run listed is open."""
    tables = TABLE.findall(page)
    if not tables:
        raise ValueError("the open runs report was not found")
    areas = []
    for table in tables:
        part = PART.search(table)
        if not part or not words(part.group(1)):
            raise ValueError("the open runs report has a table under no part of the mountain")
        runs = []
        for name, level in RUN.findall(table):
            name = words(name)
            if not name or level not in LEVELS:
                raise ValueError(f"{name or 'a run'} has a difficulty the reader does not know: {level!r}")
            runs.append({"Name": name, "Status": "Open", "StatusEnglish": "open", "Difficulty": LEVELS[level]})
        if len(runs) != table.count(RUN_MARK):
            raise ValueError(f"{words(part.group(1))} lists {table.count(RUN_MARK)} runs but {len(runs)} were read")
        if runs:
            areas.append({"Name": words(part.group(1)), "Lifts": [], "Trails": runs})
    return areas


def saved(said: str) -> str:
    """When the snow report was saved, in UTC, from the resort's own time ("NOVEMBER 24, 2026 | 10:47am")."""
    found = STAMPED.search(said)
    if not found:
        raise ValueError(f"the snow report does not say when it was saved: {said!r}")
    month, day, year, hour, minute, half = found.groups()
    try:
        at = datetime.strptime(f"{year} {month.title()} {day} {hour}:{minute} {half.upper()}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc).strftime(STAMP)


def snow_report(set_to: dict) -> dict:
    """The frame's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    figures = {}
    for place, field in SNOWFALL.items():
        said = words(set_to.get(place, ""))
        if not said:
            continue
        try:
            figures[field] = round(float(said) / CM_PER_INCH, 1)
        except ValueError as error:
            raise ValueError(f"the snow report's {place} reads {said!r}, not a number") from error
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no snow pack or no 24 hour snowfall")
    surfaces = {where: words(SUBTITLE.sub("", set_to.get(place, ""))) for place, where in SURFACES.items()}
    told = [f"{surface} ({where})" for where, surface in surfaces.items() if surface]
    if len(set(surfaces.values())) == 1:
        told = [surface for surface in set(surfaces.values()) if surface]
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": saved(set_to.get(SAVED, "")), "Resortwide": True, "BaseConditions": ", ".join(told) or None,
            "SeasonTotalIn": season, "BaseArea": {"Name": NAME, **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    set_to = places(pages["status"])
    areas = {NAME: {"Name": NAME, "Lifts": lift_rows(set_to), "Trails": []}}
    for area in open_runs(pages["runs"]):
        areas.setdefault(area["Name"], area)["Trails"] = area["Trails"]
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        feed["SnowReport"] = snow_report(set_to)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
