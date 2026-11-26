"""The reading shared by the Mountain Capital Partners resorts whose sites are built from one theme: Willamette
Pass, Sipapu and Pajarito (their "Weather, Conditions & Webcams" pages).

The page is built on the server. Its Lifts tab is a list of the lifts, each with its name and its status in words
(Open, Closed, On Hold, Open as needed), carried as the page says it; the status is also in the row's class, and the
two have to agree. Its Trails tab is one group of trails for each part of the mountain or each lift ("Frontside",
"Spruce", or only "Trails"), which is a mountain area here; the lifts are an area of their own, named for the
resort, ahead of them. A trail's status, grooming and difficulty are read from its row's classes, and one the reader
does not know fails. A trail the page lists again under a second lift is kept only under the first, so no trail is
counted twice. Every lift and trail row in the page is one read, and where the page counts its lifts ("0/6") the
count has to match, so a change in the page's shape fails instead of showing wrong numbers. The count of trails each
group gives of itself is not used: Sipapu's does not match its own list.

The snow report is the row of figures at the top of the page: the snowfall of the last 24, 48 and 72 hours and 7
days, the season's total and the base depth, in inches. A figure the resort leaves empty stays empty. The page does
not say when the figures were written, so the report is undated, and it gives no word for the surface. A snow report
that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime

STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The trail rows' difficulty classes, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double-black": "Double black"}
GROOMED = {"groomed": "Yes", "not-groomed": "No"}
# The snow figures' labels, by the names the Ikon feed gives them (the app reads those); a 5 day figure has none.
SNOWFALL = {"24 hr": "Last24HoursIn", "48 hr": "Last48HoursIn", "72 hr": "Last72HoursIn", "7 day": "Last7DaysIn",
            "5 day": None, "season total": "SeasonTotalIn", "base depth": "BaseIn"}
LIFT_LIST = re.compile(r"<ul class=\"m-lifts-list[^\"]*\">(.*?)</ul>", re.S)
LIFT = re.compile(r"<li class=\"m-lift-status-([a-z-]+)\">(.*?)</li>", re.S)
LIFT_NAME = re.compile(r"<h3 class=\"[^\"]*\bm-lift-header\b[^\"]*\"[^>]*>(.*?)</h3>", re.S)
LIFT_STATUS = re.compile(r"<div class=\"[^\"]*\bm-status m-margin-bottom m-status-([a-z-]+)\">(.*?)</div>", re.S)
TRAIL_LIST = re.compile(r"<ul class=\"[^\"]*\bm-lifts-and-trails\">")
GROUP = "<li class=\"m-accordion\">"
TRAIL = re.compile(r"<li class=\"m-filter-target([^\"]*)\">(.*?)</li>", re.S)
TRAIL_NAME = re.compile(r"<h4 class=\"[^\"]*\bm-status-([a-z-]+)\">(.*?)</h4>", re.S)
TRAIL_STATUS = re.compile(r"<div class=\"m-status m-status-([a-z-]+)\">(.*?)</div>", re.S)
VALUE = re.compile(r"m-filter-value-([a-z-]+)")
TOTALS = re.compile(r"<div class=\"m-snow-totals-table m-snow-totals-table-header[^\"]*\">(.*?)"
                    r"<div class=\"m-js-conditions-table-updated", re.S)
FIGURE = re.compile(r"<div class=\"m-snow-totals-top[^\"]*\">(.*?)</div>\s*"
                    r"<div class=\"m-snow-totals-label[^\"]*\">(.*?)</div>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?")
COUNT = re.compile(r"(\d+)\s*/\s*(\d+)")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def slug(said: str) -> str:
    """A status as the page's classes write it: "Open as needed" is "open-as-needed"."""
    return "-".join(said.lower().split())


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    said = status.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def lift_rows(page: str) -> list:
    """The lifts of the Lifts tab, in the page's order."""
    listed = LIFT_LIST.search(page)
    if not listed:
        raise ValueError("the list of lifts was not found")
    rows = []
    for marked, body in LIFT.findall(listed.group(1)):
        name, status = LIFT_NAME.search(body), LIFT_STATUS.search(body)
        if not name or not words(name.group(1)) or not status or not words(status.group(2)):
            raise ValueError("a lift in the list has no name or no status")
        said = words(status.group(2))
        if not marked == status.group(1) == slug(said):
            raise ValueError(f"{words(name.group(1))} is marked {marked} but reads {said!r}")
        rows.append(status_row(words(name.group(1)), said, None))
    listed_rows = page.count("<li class=\"m-lift-status-")
    if len(rows) != listed_rows:
        raise ValueError(f"the page has {listed_rows} lift rows but {len(rows)} were read")
    if len({row["Name"] for row in rows}) != len(rows):
        raise ValueError("the page lists a lift twice")
    return rows


def trail_row(marks: str, body: str) -> dict:
    name, status = TRAIL_NAME.search(body), TRAIL_STATUS.search(body)
    if not name or not words(name.group(2)) or not status or not words(status.group(2)):
        raise ValueError("a trail in the list has no name or no status")
    said, values = words(status.group(2)), set(VALUE.findall(marks))
    if slug(said) != status.group(1) or status.group(1) not in values:
        raise ValueError(f"{words(name.group(2))} is marked {sorted(values)} but reads {said!r}")
    if name.group(1) not in LEVELS or name.group(1) not in values:
        raise ValueError(f"{words(name.group(2))} has a difficulty the reader does not know: {name.group(1)}")
    grooming = [GROOMED[value] for value in values if value in GROOMED]
    if len(grooming) != 1:
        raise ValueError(f"{words(name.group(2))} has no grooming the reader knows: {sorted(values)}")
    row = status_row(words(name.group(2)), said, LEVELS[name.group(1)])
    row["Grooming"] = grooming[0]
    return row


def trail_areas(page: str) -> list:
    """Each group of the Trails tab with its trails, in the page's order."""
    start = TRAIL_LIST.search(page)
    if not start:
        raise ValueError("the list of trails was not found")
    areas, seen, read = [], set(), 0
    for group in page[start.end():].split(GROUP)[1:]:
        name = LIFT_NAME.search(group)
        if not name or not words(name.group(1)):
            raise ValueError("a group of trails has no name")
        trails = []
        for marks, body in TRAIL.findall(group):
            trail, read = trail_row(marks, body), read + 1
            # A trail served by two lifts is listed under both: it is kept under the first.
            if trail["Name"] not in seen:
                seen.add(trail["Name"])
                trails.append(trail)
        areas.append({"Name": words(name.group(1)), "Lifts": [], "Trails": trails})
    if not seen:
        raise ValueError("the page lists no trails")
    listed_rows = page.count("<li class=\"m-filter-target")
    if read != listed_rows:
        raise ValueError(f"the page has {listed_rows} trail rows but {read} were read")
    return areas


def figures(page: str) -> dict:
    """The row of figures at the top of the page, each label in lower case with what the page says under it."""
    table = TOTALS.search(page)
    if not table:
        raise ValueError("the row of snow figures was not found")
    return {words(label).lower(): words(said) for said, label in FIGURE.findall(table.group(1))}


def snow_report(said: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    if "base depth" not in said or "24 hr" not in said:
        raise ValueError("the snow figures have no base depth or no 24 hour snowfall")
    read = {}
    for label, text in said.items():
        if label not in SNOWFALL:
            if COUNT.fullmatch(text):
                continue
            raise ValueError(f"the snow figures have one the reader does not know: {label}")
        inches = INCHES.fullmatch(text)
        if text and not inches:
            raise ValueError(f"the snow figures' {label} reads {text!r}, not inches")
        if SNOWFALL[label]:
            value = float(inches.group(1)) if inches else None
            read[SNOWFALL[label]] = int(value) if value is not None and value.is_integer() else value
    season = read.pop("SeasonTotalIn", None)
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **read}, "Report": None, "Alert": None}


def feed(page: str, now: datetime, name: str) -> dict:
    """One resort's feed: ``name`` as the app shows it."""
    lifts = lift_rows(page)
    if not lifts:
        raise ValueError("the page lists no lifts")
    try:
        said = figures(page)
    except ValueError:
        said = None
    counted = COUNT.fullmatch((said or {}).get("lifts open", ""))
    if counted and int(counted.group(2)) != len(lifts):
        raise ValueError(f"the page counts {counted.group(2)} lifts but {len(lifts)} were read")
    areas = [{"Name": name, "Lifts": lifts, "Trails": []}] + trail_areas(page)
    out = {"Name": name, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        out["SnowReport"] = snow_report(figures(page))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return out
