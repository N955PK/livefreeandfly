"""Mt. Spokane's lifts and trails, and its snow report, from its trail report and conditions pages
(mtspokane.com/trail-maps and mtspokane.com/conditions).

Both pages are built on the server, out of the site builder's tables. The trail report's "Grooming & Lift Report"
is first a table of each lift or area with its status in words, carried as the page says it; its terrain parks
and its uphill route are rows of that table and are not lifts, so they are left out. Under it is a heading for
each chair, or for two chairs that share their trails ("Illuminator, Chair 2/Parkway Express, Chair 3"), over a
table of trails: a name, a status and whether it is groomed, where anything but "No" (the page writes "AM" or "PM"
for when) is groomed. Each heading is a mountain area here, holding its chairs and its trails; the lifts with no
heading (the conveyor and the handle tow) are an area of their own. A trail the page lists again under a second
chair is kept only under the first, so no trail is counted twice. The page gives no difficulty for a trail. Every
chair a heading names has to be in the table of lifts, and every table of trails has to have a heading, so a
change in the page's shape fails instead of showing wrong numbers.

The conditions page has a table of the depth at the base and at the summit and the snowfall of the last 24 and 48
hours, in inches, and the surface in words, under a line saying the day it was updated, without the year or the
time: the year is taken from the day the page is read, and the weekday has to agree. Before the mountain opens
the table reads "N/A" throughout, which is no snow report. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.mtspokane.com/trail-maps", "snow": "https://www.mtspokane.com/conditions"}
NAME = "Mt. Spokane"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Los_Angeles")
# The page posts its report at five in the morning, and gives only the day: the report is dated to that hour.
POSTED_HOUR = 5
# Rows of the table of lifts and areas that are not lifts.
NOT_LIFTS = {"terrain parks", "uphill route"}
OTHER_LIFTS = "Other lifts"
# The conditions table's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Base Depth": ("BaseArea", "BaseIn"), "Summit Depth": ("SummitArea", "BaseIn"),
            "New Snow in Last 24 Hours": ("BaseArea", "Last24HoursIn"),
            "New Snow in Last 48 Hours": ("BaseArea", "Last48HoursIn")}
PART = re.compile(r"<h4[^>]*>(.*?)</h4>|<table class=\"table\">(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
UPDATED = re.compile(r"Updated ([A-Z][a-z]+), ([A-Z][a-z]{2})[a-z]*\.? (\d{1,2})\b")
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\"|in\.?|inch(?:es)?)?", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def tables(page: str) -> list:
    """Each table of the page as (the heading before it, its rows of cells), in the page's order."""
    out, heading = [], None
    for said, table in PART.findall(page):
        if said:
            heading = words(said)
        else:
            rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(table)]
            # The site builder leaves empty rows at the foot of a table.
            out.append((heading, [row for row in rows if any(row)]))
            heading = None
    return out


def status_row(name: str, said: str) -> dict:
    if not name or not said:
        raise ValueError("a lift or a trail has no name or no status")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}


def lift_areas(page: str) -> list:
    """Each heading's chairs with the trails under it, then the lifts no heading names, in the page's order."""
    found = tables(page)
    listed = [rows for _, rows in found if rows and rows[0] == ["Lift/Area Name", "Status"]]
    if len(listed) != 1:
        raise ValueError("the table of lifts and their statuses was not found once")
    if any(len(row) != 2 for row in listed[0]):
        raise ValueError("a row of the table of lifts is not a name and a status")
    lifts = {name: status_row(name, said) for name, said in listed[0][1:] if name.lower() not in NOT_LIFTS}
    if not lifts or len(lifts) != sum(name.lower() not in NOT_LIFTS for name, _ in listed[0][1:]):
        raise ValueError("the table of lifts is empty or lists a lift twice")
    areas, seen, placed = [], set(), set()
    for heading, rows in found:
        if not rows or [cell.lower() for cell in rows[0][1:]] != ["status", "groomed"]:
            continue
        chairs = [chair.strip() for chair in (heading or "").split("/")]
        if any(chair not in lifts or chair in placed for chair in chairs):
            raise ValueError(f"a table of trails is under the heading {heading!r}, not chairs of the table of lifts")
        placed.update(chairs)
        trails = []
        for row in rows[1:]:
            if len(row) != 3:
                raise ValueError("a row of a trail table is not a name, a status and a grooming")
            # A trail served by two chairs is listed under both: it is kept under the first.
            if row[0] not in seen:
                seen.add(row[0])
                trails.append({**status_row(row[0], row[1]), "Grooming": "No" if row[2].lower() == "no" else "Yes"})
        areas.append({"Name": heading, "Lifts": [lifts[chair] for chair in chairs], "Trails": trails})
    if not seen:
        raise ValueError("the page lists no trails")
    others = [lift for name, lift in lifts.items() if name not in placed]
    if others:
        areas.append({"Name": OTHER_LIFTS, "Lifts": others, "Trails": []})
    return areas


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the conditions' {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def updated(page: str, now: datetime) -> datetime:
    """The day the report was updated: the page gives a weekday, a month and a day, and the year is the latest
    that does not put it after the day the page is read."""
    said = UPDATED.search(words(page))
    if not said:
        raise ValueError("the conditions do not say when they were updated")
    weekday, month, day = said.groups()
    today = now.astimezone(LOCAL_TIME)
    for year in (today.year, today.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day}", "%Y %b %d").replace(hour=POSTED_HOUR, tzinfo=LOCAL_TIME)
        except ValueError as error:
            raise ValueError(f"the conditions' date could not be read: {error}") from error
        if at <= today + timedelta(days=1):
            break
    if at.strftime("%A") != weekday:
        raise ValueError(f"the conditions were updated {weekday}, {month} {day}, which is not a {weekday} this year")
    return at


def snow_report(page: str, now: datetime) -> dict:
    """The conditions table in the shape of the Ikon feed's SnowReport: the base and the summit."""
    found = [rows for _, rows in tables(page) if rows and rows[0] and rows[0][0] == "Base Depth"]
    if len(found) != 1 or any(len(row) != 2 for row in found[0]):
        raise ValueError("the table of conditions was not found once, as labels and figures")
    said = dict(found[0])
    if any(label not in said for label in SNOWFALL):
        raise ValueError("the table of conditions has no depth or no new snow")
    if said["Base Depth"] in ("N/A", ""):
        raise ValueError("the table of conditions has no figures yet")
    out = {"BaseArea": {"Name": "Base"}, "SummitArea": {"Name": "Summit"}}
    for label, (area, field) in SNOWFALL.items():
        out[area][field] = None if said[label] in ("N/A", "") else inches(said[label], label)
    surface = said.get("Surface Conditions")
    return {"LastUpdate": updated(page, now).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None if surface in (None, "", "N/A") else surface, "SeasonTotalIn": None, **out,
            "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
