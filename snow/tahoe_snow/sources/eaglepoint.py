"""Eagle Point's lifts and trails, and its snow report, from its mountain conditions page
(eaglepointresort.com/mountain-conditions).

The page is built on the server. Under "Lifts & Runs" is a table for each lift: its first row is the lift's name
and its status in a word (the status is also in the row's class, and the two have to agree), and each row after
is a run the lift serves, with its status and its condition in words. Each lift is a mountain area here, holding
itself and its runs. The table the page heads "Terrain Parks" is not a lift and is an area with no lift. A run's
difficulty is the symbol before its name (green, blue, black, double black), and a symbol the reader does not
know fails. A run's condition says whether it is groomed ("Groomed", "Ungroomed"); any other condition says
nothing of the grooming. Above the tables the page lists the lifts again by whether they are open, and that
list has to name the same lifts as the tables. Every table and every run is one read, so a change in the page's
shape fails instead of showing wrong numbers.

The snow report gives the snow of the last 24 and 48 hours, the base depth and the season's total, in inches,
each written under its label. Before the mountain opens the page leaves all but the season's total blank, which
reads as no snow report. The page does not say when it was written, so the report is undated, and it gives no
word for the surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.eaglepointresort.com/mountain-conditions/"
NAME = "Eagle Point"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The tables that are headed by something other than a lift.
NOT_LIFTS = frozenset({"Terrain Parks"})
# The difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double-black": "Double black"}
GROOMED = {"groomed": "Yes", "ungroomed": "No"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24hr Snowfall": "Last24HoursIn", "48hr Snowfall": "Last48HoursIn", "Base": "BaseIn",
            "Season Total": "SeasonTotalIn"}
TABLE = re.compile(r"<table class=\"runs-table\"[^>]*>(.*?)</table>", re.S)
HEAD = re.compile(r"<tr class=\"label-status-row\">\s*<td[^>]*class=\"label\">(.*?)</td>\s*"
                  r"<td class=\"main-status status-([a-z-]+)\">(.*?)</td>\s*</tr>", re.S)
RUN = re.compile(r"<tr>\s*<td>\s*<span class=\"difficulty-[a-z]+ difficulty-([a-z-]+)\">\s*</span>(.*?)</td>\s*"
                 r"<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
RUNS = "<span class=\"difficulty-"
LISTED = re.compile(r"<div class=\"lift-item\">(.*?)</div>", re.S)
SNOW = re.compile(r"id=\"snowfall\"(.*?)id=\"mountain-cams\"", re.S)
LABEL = re.compile(r"<p class=\"elementor-heading-title[^\"]*\">(.*?)</p>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    if not name or not said or not said.replace(" ", "").isalpha():
        raise ValueError(f"{name or 'a row'} has the status {said!r}, not a word")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def run_row(level: str, name: str, said: str, condition: str) -> dict:
    if level not in LEVELS:
        raise ValueError(f"{words(name)} has a difficulty symbol the reader does not know: {level}")
    run = status_row(words(name), words(said), LEVELS[level])
    if words(condition).lower() in GROOMED:
        run["Grooming"] = GROOMED[words(condition).lower()]
    return run


def lift_areas(page: str) -> list:
    """Each lift with the runs in its table, in the page's order."""
    areas, read = [], 0
    for table in TABLE.findall(page):
        head = HEAD.search(table)
        if not head or not words(head.group(1)):
            raise ValueError("a table of runs is not headed by a lift and its status")
        name, marked, said = words(head.group(1)), head.group(2), words(head.group(3))
        if marked != "-".join(said.lower().split()):
            raise ValueError(f"{name} is marked {marked} but reads {said!r}")
        trails = [run_row(*run) for run in RUN.findall(table)]
        read += len(trails)
        lift = status_row(name, said, None)
        areas.append({"Name": name, "Lifts": [] if name in NOT_LIFTS else [lift], "Trails": trails})
    tables, runs = page.count("<table class=\"runs-table\""), page.count(RUNS)
    if not areas or len(areas) != tables or read != runs or not read:
        raise ValueError(f"the page has {tables} tables and {runs} runs but {len(areas)} and {read} were read")
    names = [area["Name"] for area in areas]
    if len(set(names)) != len(names) or not any(area["Lifts"] for area in areas):
        raise ValueError("the page lists no lifts, or one twice")
    if sorted(names) != sorted(words(item) for item in LISTED.findall(page)):
        raise ValueError("the page's list of lifts does not name the lifts of its tables")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    report = SNOW.search(page)
    if not report:
        raise ValueError("the snow report was not found")
    pieces = LABEL.split(report.group(1))
    figures = {}
    for label, body in zip(pieces[1::2], pieces[2::2]):
        if words(label) not in SNOWFALL or not words(body):
            continue
        said = INCHES.fullmatch(words(body))
        if not said:
            raise ValueError(f"the snow report's {words(label)} reads {words(body)!r}, not inches")
        value = float(said.group(1))
        figures[SNOWFALL[words(label)]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": lift_areas(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
