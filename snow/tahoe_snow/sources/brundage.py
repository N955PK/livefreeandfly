"""Brundage's lifts and trails, and its snow report, from its grooming report page
(brundage.com/grooming-report).

The page is built on the server. Its "Lift & Zone Status" is the lifts by part of the mountain (a "zone"), each
with its name and its status in words, carried as the page says it; the status is also in the row's class, and the
two have to agree. Its "Trail Status" is one table of trails for each zone, each row a name, a difficulty and a
status in words. A zone is a mountain area here, holding its lifts and its trails. A trail said to be groomed is
open and groomed, and grooming is carried only on a day the page says it of some trail. A difficulty the reader
does not know fails; a terrain park ("Freestyle") has none. Every lift and trail row in the page is one read, and
the page's own count of trails ("0 of 70") has to match, so a change in the page's shape fails instead of showing
wrong numbers. Its count of lifts is not used: it leaves the conveyor out.

The snow report is the page's weather box: the depth at the base, at Lakeview (mid-mountain) and at the summit,
the snowfall of the last 24, 48 and 72 hours and the week at the base and at Lakeview, and the season's total at
each, in inches, with the day and time the report was last updated, in Boise's time. A figure the resort leaves
as a dash stays empty. It gives no word for the surface. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://brundage.com/grooming-report/"
NAME = "Brundage"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Boise")
# The trail tables' difficulties, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double black": "Double black", "freestyle": ""}
# The weather box's stakes, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Base": "BaseArea", "Lakeview": "MidMountainArea", "Summit": "SummitArea"}
SNOWFALL = {"24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn", "72 Hours": "Last72HoursIn",
            "1 Week": "Last7DaysIn"}
LIFT_REPORT = re.compile(r"<section class=\"weather-conditions lift-zone-report\">(.*?)</section>", re.S)
TRAIL_REPORT = re.compile(r"<section class=\"weather-conditions trail-report\">(.*?)</section>", re.S)
ZONE = re.compile(r"<div class=\"lift-zone-report__zone\b[^\"]*\">\s*<h3>(.*?)</h3>(.*?)</ul>", re.S)
LIFT = re.compile(r"<h4>(.*?)</h4>\s*<p class=\"lift-status ([a-z-]+)\">(.*?)</p>", re.S)
TRAILS = re.compile(r"<span class=\"wp-block-accordion-heading__toggle-title\">(.*?)</span>.*?"
                    r"<table[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TRAILS_COUNTED = re.compile(r"<div class=\"weather-box-title\">Trails Open</div>.*?<div>\s*<div>(\d+)</div>\s*"
                            r"<div>(\d+)</div>", re.S)
UPDATED = re.compile(r"Last Updated (\d{1,2})/(\d{1,2})/(\d{2}) (\d{1,2}):(\d{2})\s*([AP]M)")
DEPTHS = re.compile(r"<div class=\"weather-box-title\">Snow Depths</div>\s*<ul>(.*?)</ul>", re.S)
LOCATIONS = re.compile(r"<div class=\"weather-box-winter-locations\">(.*?)<div class=\"weather-box-title\">", re.S)
LOCATION = re.compile(r"<div>\s*([A-Z][A-Za-z ]*?)\s*\([\d,]+(?:&#0?39;|['’])\)\s*</div>\s*<ul>(.*?)</ul>", re.S)
ITEM = re.compile(r"<li>(.*?)</li>", re.S)
FIGURE = re.compile(r"(.*\S)\s*:\s*(\S+)")
SEASON = re.compile(r"Total Season Snowfall \(\s*(\w+)\s*\)")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")")
EMPTY = {"—", "-", "–"}
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    said = status.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def lift_zones(page: str) -> dict:
    """The lifts of each zone, in the page's order."""
    report = LIFT_REPORT.search(page)
    if not report:
        raise ValueError("the lift and zone status was not found")
    zones = {}
    for zone, body in ZONE.findall(report.group(1)):
        rows = []
        for name, marked, said in LIFT.findall(body):
            name, said = words(name), words(said)
            if not name or not said:
                raise ValueError("a lift has no name or no status")
            if marked != "-".join(said.lower().split()):
                raise ValueError(f"{name} is marked {marked} but reads {said!r}")
            rows.append(status_row(name, said, None))
        if words(zone) in zones:
            raise ValueError(f"the page lists {words(zone)} twice")
        zones[words(zone)] = rows
    lifts = [lift["Name"] for rows in zones.values() for lift in rows]
    listed = report.group(1).count("class=\"lift-status")
    if not lifts or len(lifts) != listed:
        raise ValueError(f"the page has {listed} lift rows but {len(lifts)} were read")
    if len(set(lifts)) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return zones


def trail_row(cells: list) -> dict:
    if len(cells) != 3 or not words(cells[0]) or not words(cells[2]):
        raise ValueError("a row of a trail table is not a name, a difficulty and a status")
    name, level, said = words(cells[0]), words(cells[1]).lower(), words(cells[2])
    if level not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {words(cells[1])}")
    if said.lower() == "groomed":
        return {**status_row(name, "Open", LEVELS[level]), "Grooming": "Yes"}
    return status_row(name, said, LEVELS[level])


def trail_zones(page: str) -> dict:
    """The trails of each zone, in the page's order."""
    report = TRAIL_REPORT.search(page)
    if not report:
        raise ValueError("the trail status was not found")
    zones = {}
    for zone, table in TRAILS.findall(report.group(1)):
        if words(zone) in zones:
            raise ValueError(f"the page lists {words(zone)}'s trails twice")
        zones[words(zone)] = [trail_row(CELL.findall(row)) for row in ROW.findall(table)]
    trails = [trail for rows in zones.values() for trail in rows]
    listed = report.group(1).count("<tr")
    if not trails or len(trails) != listed:
        raise ValueError(f"the page has {listed} trail rows but {len(trails)} were read")
    # The page says which trails are groomed only by calling them groomed: on a day it does, the others are not.
    if any("Grooming" in trail for trail in trails):
        for trail in trails:
            trail.setdefault("Grooming", "No")
    counted = TRAILS_COUNTED.search(page)
    if not counted:
        raise ValueError("the page's count of trails was not found")
    turning = sum(trail["StatusEnglish"].startswith("open") for trail in trails)
    if (turning, len(trails)) != (int(counted.group(1)), int(counted.group(2))):
        raise ValueError(f"the page counts {counted.group(1)} of {counted.group(2)} trails open but {turning} of "
                         f"{len(trails)} were read")
    return zones


def inches(said: str, label: str) -> float | int | None:
    """A figure in inches, or None where the resort has left a dash."""
    if said in EMPTY:
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def figures(markup: str) -> dict:
    """The lines of one list of the weather box, each label with what the page says after its colon."""
    out = {}
    for item in ITEM.findall(markup):
        said = FIGURE.fullmatch(words(item))
        if not said or said.group(1) in out:
            raise ValueError(f"a line of the snow report reads {words(item)!r}, not a label and a figure given once")
        out[said.group(1)] = said.group(2)
    return out


def snow_report(page: str) -> dict:
    """The weather box's figures in the shape of the Ikon feed's SnowReport: the base, Lakeview and the summit."""
    updated, depths, locations = UPDATED.search(page), DEPTHS.search(page), LOCATIONS.search(page)
    if not updated or not depths or not locations:
        raise ValueError("the snow report has no time of update, no depths or no snowfall")
    month, day, year, hour, minute, half = updated.groups()
    try:
        at = datetime.strptime(f"20{year} {month} {day} {hour}:{minute} {half}", "%Y %m %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    out = {area: {"Name": name} for name, area in STAKES.items()}
    seasons = {}
    for label, said in figures(depths.group(1)).items():
        season = SEASON.fullmatch(label)
        if season and season.group(1) in STAKES:
            seasons[season.group(1)] = inches(said, label)
        elif label in STAKES:
            out[STAKES[label]]["BaseIn"] = inches(said, label)
        else:
            raise ValueError(f"the snow depths have a line the reader does not know: {label}")
    if "BaseIn" not in out["BaseArea"]:
        raise ValueError("the snow depths have no depth at the base")
    read = set()
    for name, body in LOCATION.findall(locations.group(1)):
        if name not in STAKES or name in read:
            raise ValueError(f"the snowfall is given for a place the reader does not know, or twice: {name}")
        read.add(name)
        for label, said in figures(body).items():
            if label not in SNOWFALL:
                raise ValueError(f"the snowfall at {name} has a line the reader does not know: {label}")
            out[STAKES[name]][SNOWFALL[label]] = inches(said, label)
    if "Last24HoursIn" not in out["BaseArea"]:
        raise ValueError("the snowfall has no 24 hour figure at the base")
    return {"LastUpdate": at.replace(tzinfo=LOCAL_TIME).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": seasons.get("Base"), **out, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, trails = lift_zones(page), trail_zones(page)
    areas = [{"Name": zone, "Lifts": lifts.get(zone, []), "Trails": trails.get(zone, [])}
             for zone in list(lifts) + [zone for zone in trails if zone not in lifts]]
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
