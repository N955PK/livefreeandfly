"""49 Degrees North's lifts and trails, and its snow report, from its trail status and conditions report pages
(ski49n.com/mountain-info/trail-status and ski49n.com/mountain-info/expanded-conditions).

Both pages are built on the server. The trail status is one list under a row of headings: "Lifts", then each part
of the mountain ("Sunrise Basin", "Central Basin Glades" and so on). Every line under a heading is a name, a dash
and a status in words, carried as the page says it. The lifts are one mountain area here and each part of the
mountain another, holding its trails. The page gives no difficulty for a trail; its key has "Groomed" as a third
state beside open and closed, and a trail said to be groomed is open and groomed. Every line in the list is one
read, and the list has to begin with its lifts, so a change in the page's shape fails instead of
showing wrong numbers.

The conditions report gives, at the base and at the summit, the snowfall of the last 12, 24, 48 and 72 hours and
the depth, in inches, the season's snowfall at the summit and the surface in words, with the day and time it was
last updated, in Pacific time. A figure the resort leaves empty stays empty. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.ski49n.com/mountain-info/trail-status",
        "snow": "https://www.ski49n.com/mountain-info/expanded-conditions"}
NAME = "49 Degrees North"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Los_Angeles")
# The heading the lifts are listed under; every other heading is a part of the mountain.
LIFTS = "Lifts"
# The conditions report's places and lines, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Base": "BaseArea", "Summit": "SummitArea"}
SNOWFALL = {"12 Hours": "Last12HoursIn", "24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn",
            "72 Hours": "Last72HoursIn", "Snow Depth": "BaseIn"}
STATUS_LIST = re.compile(r"<h3[^>]*>\s*Lifts\s*</h3>.*?(?=</section>|$)", re.S)
ENTRY = re.compile(r"<h3[^>]*>(.*?)</h3>|<h4[^>]*>(.*?)</h4>", re.S)
LINE = re.compile(r"(.*\S)\s+-\s+(\S.*)")
UPDATED = re.compile(r"Last updated:\s*(\d{1,2})/(\d{1,2})/(\d{2}) at (\d{1,2}):(\d{2})\s*([ap]m)")
NEW_SNOW = re.compile(r"<h3>\s*New Snow\s*</h3>(.*?)<div class=\"heading\">", re.S)
BOX = re.compile(r"<div class=\"box\">\s*<h4>(.*?)</h4>\s*<h3>(.*?)</h3>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\")?")
EMPTY = {"", "\"", "″", "”"}
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_areas(page: str) -> list:
    """The lifts, then each part of the mountain with its trails, in the page's order."""
    listed = STATUS_LIST.search(page)
    if not listed:
        raise ValueError("the list of lifts and trails was not found")
    areas = []
    for heading, line in ENTRY.findall(listed.group(0)):
        if heading or not areas:
            areas.append({"Name": words(heading), "Lifts": [], "Trails": []})
            continue
        said = LINE.fullmatch(words(line))
        if not said:
            raise ValueError(f"a line of the list reads {words(line)!r}, not a name, a dash and a status")
        status, lift = said.group(2).capitalize(), areas[-1]["Name"] == LIFTS
        # The page's key has three states for a trail: open, closed and groomed. A groomed trail is open.
        groomed = status == "Groomed" and not lift
        status = "Open" if groomed else status
        row = {"Name": said.group(1), "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}
        if groomed:
            row["Grooming"] = "Yes"
        areas[-1]["Lifts" if lift else "Trails"].append(row)
    names = [area["Name"] for area in areas]
    if not names or names[0] != LIFTS or len(set(names)) != len(names):
        raise ValueError(f"the list's headings read {names}, not the lifts and then each part of the mountain once")
    if not areas[0]["Lifts"] or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    lifts = [lift["Name"] for lift in areas[0]["Lifts"]]
    if len(set(lifts)) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return areas


def inches(said: str, label: str) -> float | int | None:
    """A figure in inches, or None where the resort has left it empty."""
    if said in EMPTY:
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the conditions report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the base and the summit."""
    updated, snow = UPDATED.search(page), NEW_SNOW.search(page)
    if not updated or not snow:
        raise ValueError("the conditions report has no time of update or no new snow")
    month, day, year, hour, minute, half = updated.groups()
    try:
        at = datetime.strptime(f"20{year} {month} {day} {hour}:{minute} {half}", "%Y %m %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the conditions report's date could not be read: {error}") from error
    out, place = {}, None
    for label, said in BOX.findall(snow.group(1)):
        label, said = words(label), words(said)
        if not label:
            # A row begins with a box that has no label and names the place.
            if said not in STAKES or STAKES[said] in out:
                raise ValueError(f"the new snow is given for a place the reader does not know, or twice: {said}")
            place = STAKES[said]
            out[place] = {"Name": said}
        elif place is None or label not in SNOWFALL:
            raise ValueError(f"the new snow has a box the reader does not know: {label}")
        else:
            out[place][SNOWFALL[label]] = inches(said, label)
    if out.get("BaseArea", {}).get("Last24HoursIn") is None:
        raise ValueError("the new snow has no 24 hour figure at the base")
    others = {words(label): words(said) for label, said in BOX.findall(page[snow.end():])}
    season = others.get("Snowfall YTD (summit)", "")
    return {"LastUpdate": at.replace(tzinfo=LOCAL_TIME).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": others.get("Surface Condition") or None,
            "SeasonTotalIn": inches(season, "season's snowfall"), **out, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": status_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
