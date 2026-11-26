"""Purgatory's lifts and trails, and its snow report, from its weather, conditions and webcams page
(purgatory.ski/mountain/weather-conditions-webcams).

The page is built on the server, in tabs. The lifts tab lists each lift with its status in words (Open, Closed, On
Hold, Open as needed), carried as the page says them. The trails tab is a heading for each part of the mountain
(Frontside, Columbine Beginner Area, Backside), saying which lifts reach it and how many of its trails are open, over
its trails; each part is a mountain area here, holding those lifts and its trails. A trail's status is its own words,
and its difficulty and grooming are the classes the page's own filter reads; a difficulty the reader does not know
fails. Each part's own count of its open trails is checked against what is read, so a change in the page's shape
fails instead of showing wrong numbers. (Its count of all its trails is not checked: the page lists one more trail on
the Backside than it counts.) A lift no part names is given an area of the mountain's own name. The terrain parks
tab is not read: the parks are features on trails already listed.

The snow report gives one base depth, the snowfall of the last 24 and 48 hours and 7 days, the season's total, and
the resort's own words. When it was updated is not in the page: the page's script fills it in from a small file on
the same site (wp-content/uploads/sites/2/m-json/weather.json), which says when the snowfall totals were updated, in
Mountain time. A report whose time cannot be read is given undated. It gives no word for the surface. A snow report
that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URLS = {"report": "https://www.purgatory.ski/mountain/weather-conditions-webcams/",
        "updated": "https://www.purgatory.ski/wp-content/uploads/sites/2/m-json/weather.json"}
NAME = "Purgatory"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The trail filter's difficulty classes, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "double-blue": "Blue", "black": "Black", "double-black": "Double black",
          "double-black-extreme-terrain": "Double black"}
GROOMED = {"groomed": "Yes", "not-groomed": "No"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hr": "Last24HoursIn", "48 Hr": "Last48HoursIn", "7 Day": "Last7DaysIn", "Base Depth": "BaseIn",
            "Season Total": "SeasonTotalIn"}
TAB = "id=\"m-tab-{name}\""
LIFT = re.compile(r"<li class=\"m-lift-status-[a-z-]+\">.*?<h3 class=\"[^\"]*m-lift-header\">(.*?)</h3>.*?"
                  r"<div class=\"[^\"]*m-status-[a-z-]+\">(.*?)</div>\s*</div>\s*</li>", re.S)
PART = re.compile(r"<li class=\"m-accordion\">")
PART_HEAD = re.compile(r"<h3 class=\"[^\"]*m-lift-header\"[^>]*>(.*?)</h3>(.*?)</div>.*?"
                       r"<div>\s*(\d+)\s*/\s*\d+ Trails Open", re.S)
TRAIL = re.compile(r"<li class=\"m-filter-target m-filter-value-[a-z-]+ m-filter-value-((?:not-)?groomed) "
                   r"m-filter-status m-filter-value-([a-z-]+)\">.*?<h4[^>]*>(.*?)</h4>.*?"
                   r"<div class=\"m-status m-status-[a-z-]+\">(.*?)</div>", re.S)
TOTALS = re.compile(r"<div class=\"m-snow-totals-table m-snow-totals-table-header[^\"]*\">(.*?)"
                    r"<div class=\"m-js-conditions-table-updated", re.S)
FIGURE = re.compile(r"<div class=\"m-snow-totals-top[^\"]*\">(.*?)</div>\s*"
                    r"<div class=\"m-snow-totals-label[^\"]*\">(.*?)</div>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|″|”)")
REPORT = re.compile(r"<div class=\"m-js-todays-report-updated[^\"]*\">.*?</div>\s*<div class=\"[^\"]*\">(.*?)</div>",
                    re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def tab(page: str, name: str, until: str) -> str:
    """The part of the page from one tab's start to the next tab's."""
    start, end = page.find(TAB.format(name=name)), page.find(TAB.format(name=until))
    if start < 0 or end < start:
        raise ValueError(f"the {name} tab was not found")
    return page[start:end]


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    if not name:
        raise ValueError("the page lists a lift or a trail with no name")
    if not said:
        raise ValueError(f"{name} has no status")
    status = said.capitalize()
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def lift_rows(page: str) -> list:
    listed = tab(page, "lifts", "trails")
    lifts = [status_row(words(name), words(said), None) for name, said in LIFT.findall(listed)]
    if not lifts:
        raise ValueError("the page lists no lifts")
    if len(lifts) != listed.count("<li class=\"m-lift-status-") or len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("a lift of the lifts tab is not in the shape expected, or is listed twice")
    return lifts


def trail_row(groomed: str, level: str, name: str, said: str) -> dict:
    if level not in LEVELS:
        raise ValueError(f"{words(name)} has a difficulty the reader does not know: {level}")
    row = status_row(words(name), words(said), LEVELS[level])
    row["Grooming"] = GROOMED[groomed]
    return row


def parts(page: str) -> list:
    """Each part of the mountain as (its name, the lifts that reach it, its trails), in the page's order."""
    listed = tab(page, "trails", "terrain")
    starts = [found.start() for found in PART.finditer(listed)]
    found = []
    for at, start in enumerate(starts):
        part = listed[start:starts[at + 1] if at + 1 < len(starts) else len(listed)]
        head = PART_HEAD.search(part)
        if not head:
            raise ValueError("a part of the mountain has no name or no count of its trails")
        name, reached = words(head.group(1)), words(head.group(2))
        trails = [trail_row(*cells) for cells in TRAIL.findall(part)]
        if len(trails) != part.count("<li class=\"m-filter-target"):
            raise ValueError(f"a trail of {name} is not in the shape expected")
        turning = sum(trail["StatusEnglish"] == "open" for trail in trails)
        if turning != int(head.group(3)):
            raise ValueError(f"the page counts {head.group(3)} trails open on {name} but {turning} were read")
        via = reached.removeprefix("Access via").strip() if reached.startswith("Access via") else ""
        found.append((name, [lift.strip() for lift in via.split(",") if lift.strip()], trails))
    if not any(trails for _, _, trails in found):
        raise ValueError("the page lists no trails")
    return found


def updated(page: str) -> str | None:
    """When the snowfall totals were updated, from the file the page's script reads; None when it does not say."""
    try:
        said = json.loads(page)["conditions_table_updated"]
        at = datetime.strptime(" ".join(said.replace(",", " ").split()), "%B %d %Y %I:%M %p")
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
    return at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str, posted: str | None) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    totals = TOTALS.search(page)
    if not totals:
        raise ValueError("the snow totals were not found")
    figures = {}
    for said, label in FIGURE.findall(totals.group(1)):
        if words(label) not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(words(said))
        if not inches or SNOWFALL[words(label)] in figures:
            raise ValueError(f"the snow report's {words(label)} reads {words(said)!r}, not inches given once")
        value = float(inches.group(1))
        figures[SNOWFALL[words(label)]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season, report = figures.pop("SeasonTotalIn", None), REPORT.search(page)
    return {"LastUpdate": posted, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": words(report.group(1)) or None if report else None,
            "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    lifts, areas, placed = lift_rows(pages["report"]), [], set()
    for name, reached, trails in parts(pages["report"]):
        mine = [lift for lift in lifts if lift["Name"] in reached and lift["Name"] not in placed]
        placed.update(lift["Name"] for lift in mine)
        areas.append({"Name": name, "Lifts": mine, "Trails": trails})
    stray = [lift for lift in lifts if lift["Name"] not in placed]
    if stray:
        areas.append({"Name": NAME, "Lifts": stray, "Trails": []})
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(pages["report"], updated(pages.get("updated") or ""))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
