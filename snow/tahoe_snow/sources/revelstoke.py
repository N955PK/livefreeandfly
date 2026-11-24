"""Revelstoke's lifts and groomed runs, and its snow report, from its lifts and grooming page and its snow report
page (revelstokemountainresort.com/mountain/conditions/lifts-grooming/ and /snow-report/).

Both pages are built on the server. The lifts and grooming page is a panel for each lift over the runs under it;
each panel is a mountain area here, holding its lift and its runs. The panels are named as the page names them:
the three chairs by name, the gondola's upper mountain as "Stoke Base to Revelation Lodge", and the runs below the
lodge as "Revelation Lodge to Village Base", a panel with no lift and no lift status. **The page lists the runs
the resort grooms, not every run on the mountain**, and a run that passes under more than one lift is listed
under each, sometimes at a different difficulty: each listing is kept where the page has it, so a run can be read
more than once. A status is the mark on its row, in the page's own set: open, closed, groomed and ungroomed (open
runs, groomed or not) and standby, which is carried in the page's own word. A mark or a difficulty the reader does
not know fails, and each panel's rows are counted against what is read.

The snow report gives one base depth, the snowfall of the last 24 and 48 hours and 7 days, and the season's total.
Its "new snow" and "last hour" are left out: the page does not say what the first is counted from. **The page
reports whole centimetres; they are converted to inches here (divided by 2.54, to one decimal).** The page does
not say when the report was made or where it is measured, so it is undated here, and it gives no word for the
surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime

SITE = "https://www.revelstokemountainresort.com/mountain/conditions"
URLS = {"lifts": f"{SITE}/lifts-grooming/", "snow": f"{SITE}/snow-report/"}
NAME = "Revelstoke"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The page's status marks, as a status and whether the run is groomed; None is carried in the page's own word.
STATUSES = {"open": ("Open", "No"), "closed": ("Closed", "No"), "groomed": ("Open", "Yes"),
            "ungroomed": ("Open", "No"), "standby": (None, "No")}
# The page's difficulty marks, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black"}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 hours": "Last24HoursIn", "48 hours": "Last48HoursIn", "7 days": "Last7DaysIn",
            "Base Depth": "BaseIn", "Season Total": "SeasonTotalIn"}
LEFT_OUT = {"New Snow", "Last Hour"}
PANEL = re.compile(r"<div class=\"lifts-runs__lift[^\"]*\">\s*<div class=\"lifts-runs__header\">\s*<h2>(.*?)</h2>"
                   r"(.*?)</div>\s*<table class=\"lifts-runs__table\"[^>]*>(.*?)</table>", re.S)
MARK = r"<span class=\"{kind}-status {kind}-status--([a-z-]+)\">.*?<span class=\"status-text\">(.*?)</span>"
LIFT_MARK, RUN_MARK = re.compile(MARK.format(kind="lift"), re.S), MARK.format(kind="run")
RUN = re.compile(r"<td class=\"run-difficulty ([a-z-]+)\">.*?</td>\s*<td class=\"run-name\">(.*?)</td>\s*"
                 r"<td class=\"run-info\">\s*" + RUN_MARK, re.S)
RUN_NAME, TABLE = "<td class=\"run-name\">", "<table class=\"lifts-runs__table\""
SNOW_REPORT = re.compile(r"<section class=\"snow-report__section\">(.*?)</section>", re.S)
FIGURE = re.compile(r"<h2 class=\"snow-report__title\">(.*?)</h2>\s*<span class=\"snow-report__data\">\s*"
                    r"<span class=\"value\">(.*?)</span>\s*<span class=\"unit\">(.*?)</span>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, mark: str, said: str, difficulty: str | None) -> dict:
    """One lift or run: its status is the mark on its row."""
    name = words(name)
    if not name or mark not in STATUSES:
        raise ValueError(f"{name or 'a row'} has a status the reader does not know: {mark}")
    status, groomed = STATUSES[mark]
    status = status or words(said).capitalize()
    if not status:
        raise ValueError(f"{name} has no status")
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
    if difficulty is not None:
        row["Grooming"] = groomed
    return row


def run_row(level: str, name: str, mark: str, said: str) -> dict:
    if level not in LEVELS:
        raise ValueError(f"{words(name) or 'a run'} has a difficulty the reader does not know: {level}")
    return status_row(name, mark, said, LEVELS[level])


def panels(page: str) -> list:
    """Each lift's panel as a mountain area: its lift, when the panel has one, over its runs."""
    areas = []
    for heading, head, table in PANEL.findall(page):
        name, marks = words(heading), LIFT_MARK.findall(head)
        if not name or len(marks) > 1 or ("lift-status" in head and not marks):
            raise ValueError(f"{name or 'a panel'} does not read as a lift and its status")
        runs = [run_row(*found) for found in RUN.findall(table)]
        if len(runs) != table.count(RUN_NAME):
            raise ValueError(f"{name} lists {table.count(RUN_NAME)} runs but {len(runs)} were read")
        areas.append({"Name": name, "Lifts": [status_row(name, *marks[0], None)] if marks else [], "Trails": runs})
    if len(areas) != page.count(TABLE):
        raise ValueError(f"the page has {page.count(TABLE)} panels but {len(areas)} were read")
    if not any(area["Lifts"] for area in areas) or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no runs")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, undated."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    figures = {}
    for heading, said, unit in FIGURE.findall(block.group(1)):
        heading = words(heading)
        if heading in LEFT_OUT:
            continue
        if heading not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {heading}")
        if not said.strip().isdigit() or unit.strip() != "cm" or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report's {heading} reads {said!r} {unit!r}, not centimetres given once")
        figures[SNOWFALL[heading]] = round(int(said) / CM_PER_INCH, 1)
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": panels(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
