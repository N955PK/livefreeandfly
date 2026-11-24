"""Whitewater's lifts and groomed runs, and its snow report, from its lift and grooming status page, the statuses
that page loads, and its conditions page (whitewatermountainresort.com/lift-grooming-status/, /lifts-json/ and
/conditions/).

The status page is built on the server with every status left to be filled in: it names the lifts, and under each
of its three chairs' headings (Raven, Summit, Glory) the runs with their difficulty. The statuses are a JSON
document the page loads, keyed the way the page's rows are marked, and are joined to the rows here. The lifts are
a mountain area of their own, and each heading is an area holding its runs. **The page lists the runs the resort
grooms, not every run on the mountain.** A status is one of the page's own set, in the words of its key: open,
closed, freshly groomed, previously groomed and ungroomed (open runs; only a freshly groomed one is given as
groomed) and the one its key calls unknown, which is carried in the page's own word. A status or a difficulty the
reader does not know fails, as does a row the statuses do not have. The page's parking lots, its avalanche
closures and its Nordic trails are not lifts or ski runs and are left out.

The snow report gives one base depth, the new snow overnight, the snowfall of the last 24 and 48 hours, 3 days and
7 days, and the season's total, measured at the summit weather plot at 1,950 m, under a line saying when it was
updated, in the resort's own time. **The page reports whole centimetres; they are converted to inches here
(divided by 2.54, to one decimal).** It gives no word for the surface. A snow report that cannot be read costs
only the snow report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SITE = "https://whitewatermountainresort.com"
URLS = {"lifts": f"{SITE}/lift-grooming-status/", "status": f"{SITE}/lifts-json/", "snow": f"{SITE}/conditions/"}
NAME = "Whitewater"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# The statuses' keys, as a status and whether the run is groomed; None is carried in the page's own word.
STATUSES = {"open": ("Open", "No"), "closed": ("Closed", "No"), "fresh": ("Open", "Yes"), "groomed": ("Open", "No"),
            "ungroomed": ("Open", "No"), "standby": (None, "No")}
# The page's difficulty words, in the words the app's difficulty symbols are keyed on.
LEVELS = {"Easiest - Green Circle": "Green", "More Difficult - Blue Square": "Blue",
          "Most Difficult - Black Diamond": "Black"}
# The headings of the status page that are not ski runs, by their marks.
LEFT_OUT = {"nordic_trails"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24hr": "Last24HoursIn", "48hr": "Last48HoursIn", "3 Days": "Last72HoursIn", "7 Days": "Last7DaysIn",
            "Current Base": "BaseIn", "Total Snowfall": "SeasonTotalIn"}
LIFT = re.compile(r"<h3 class=\"status__item__heading\">([^<]*)</h3>\s*<span class=\"status__item__status\"\s+"
                  r"data-update-lift=\"terrain\" data-update-run=\"([a-z0-9_]+)\">", re.S)
PANEL = re.compile(r"<section class=\"lifts-runs__lift ([a-z0-9_]+)\">\s*<h2[^>]*>\s*<span>(.*?)</span>(.*?)</section>",
                   re.S)
RUN = re.compile(r"<span class=\"u-hide-visual\">([^<]*)</span>\s*</td>\s*<td>(.*?)</td>\s*<td>\s*"
                 r"<span class=\"lifts-runs__status\" data-update-lift=\"([a-z0-9_]+)\" "
                 r"data-update-run=\"([a-z0-9_]+)\">", re.S)
RUN_MARK = "data-update-run="
UPDATED = re.compile(r"<div class=\"report-date[^\"]*\">\s*<p>\s*Updated on ([A-Z][a-z]+) (\d{1,2}), (\d{4}) at "
                     r"(\d{1,2}):(\d{2})\s*</p>")
SNOW_REPORT = re.compile(r"<section class=\"daily-snow-report[^\"]*\">(.*?)</section>", re.S)
FIGURE = re.compile(r"<span class=\"condition-field__value\">(.*?)</span><span class=\"condition-field__unit\">(.*?)"
                    r"</span>\s*</div>\s*<div class=\"condition-field__label\">(.*?)</div>", re.S)
OVERNIGHT = re.compile(r"snow-summary__item--overnight\">.*?<span class=\"value\">(\d+)</span><span class=\"unit\">cm"
                       r"</span>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def statuses(page: str) -> dict:
    """The statuses the page loads: each heading's mark, over the marks of its rows."""
    try:
        loaded = json.loads(page)["lifts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError(f"the statuses do not read: {error!r}") from error
    if not isinstance(loaded, dict):
        raise ValueError("the statuses are not in the shape expected")
    return loaded


def status_row(name: str, loaded: dict, heading: str, mark: str, difficulty: str | None) -> dict:
    """One lift or run: its status is the one the statuses have under its heading's mark and its own."""
    name = words(name)
    try:
        said = loaded[heading]["runs"][mark]
        key, label = said["key"], said["label"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"{name or mark} has no status: {error!r}") from error
    if not name or key not in STATUSES:
        raise ValueError(f"{name or mark} has a status the reader does not know: {key!r}")
    status, groomed = STATUSES[key]
    status = status or words(str(label)).capitalize()
    if not status:
        raise ValueError(f"{name} has no status")
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
    if difficulty is not None:
        row["Grooming"] = groomed
    return row


def lift_rows(page: str, loaded: dict) -> list:
    # The page lists its lifts twice, once for a narrow screen.
    named = dict((mark, name) for name, mark in LIFT.findall(page))
    lifts = [status_row(name, loaded, "terrain", mark, None) for mark, name in named.items()]
    if not lifts:
        raise ValueError("the page lists no lifts")
    return lifts


def run_areas(page: str, loaded: dict) -> list:
    """The runs under each heading of the status page, as a mountain area each."""
    areas = []
    for heading, title, body in PANEL.findall(page):
        if heading in LEFT_OUT:
            continue
        runs = []
        for level, name, under, mark in RUN.findall(body):
            level = html.unescape(level).strip()
            if level not in LEVELS or under != heading:
                raise ValueError(f"{words(name) or mark} has a difficulty the reader does not know: {level}")
            runs.append(status_row(name, loaded, heading, mark, LEVELS[level]))
        if len(runs) != body.count(RUN_MARK):
            raise ValueError(f"{words(title)} lists {body.count(RUN_MARK)} runs but {len(runs)} were read")
        areas.append({"Name": words(title), "Lifts": [], "Trails": runs})
    if not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no runs")
    return areas


def updated(page: str) -> str:
    """When the snow report was updated, in UTC, from the resort's own time."""
    found = UPDATED.search(page)
    if not found:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute = found.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute}", "%Y %b %d %H:%M")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, measured at the summit plot."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    figures = {}
    for said, unit, label in FIGURE.findall(block.group(1)):
        label = words(label)
        if label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        if not said.strip().isdigit() or unit.strip().lower() != "cm" or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label} reads {said!r} {unit!r}, not centimetres given once")
        figures[SNOWFALL[label]] = round(int(said) / CM_PER_INCH, 1)
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base or no 24 hour snowfall")
    overnight = OVERNIGHT.search(page)
    if overnight:
        figures["OvernightIn"] = round(int(overnight.group(1)) / CM_PER_INCH, 1)
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": updated(page), "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Summit weather plot", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    loaded = statuses(pages["status"])
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lift_rows(pages["lifts"], loaded), "Trails": []},
                              *run_areas(pages["lifts"], loaded)]}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
