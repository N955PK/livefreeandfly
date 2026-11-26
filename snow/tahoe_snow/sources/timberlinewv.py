"""Timberline Mountain's lifts and trails, and its snow report, from its snow report page
(timberlinemountain.com/snow-report). This is West Virginia's Timberline, not Oregon's Timberline Lodge.

The page is built on the server, by a snow report plug-in: under "Lift Access", "Trail Access" and "Terrain Park
Access" each lift, trail and park is a line of its name, a status icon and the status in words (Closed, Open),
carried as the page says it. The red cross is the icon of a closed line and of no other, and a line where the two
disagree fails. A trail's difficulty is the symbol before its name (beginner, intermediate, expert, expert only),
and one the reader does not know fails; a terrain park is given none. The lifts are one mountain area, the trails
another and the terrain parks a third. Every line in the page is one read, so a change in the page's shape fails
instead of showing wrong numbers.

The snow report gives the snow of the last 24 hours and 7 days and the base depth as a low and a high, in inches.
The page does not say when it was written, so the report is undated (out of season its figures are all noughts),
and it gives no word for the surface. A snow report that cannot be read costs only the snow report, not the
lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://timberlinemountain.com/snow-report/"
NAME = "Timberline Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "expert": "Black", "expert-only": "Double black"}
# The status icon of a closed lift or trail.
CLOSED_ICON = "red-x-32"
# The page's kinds of line, by the mountain area each is listed in.
KINDS = {"slope": NAME, "trail": "Trails", "terrain-park": "Terrain Parks"}
# The snow report's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Snow Last 24 Hours": "Last24HoursIn", "Snow Last 7 Days": "Last7DaysIn", "Base Lo": "BaseMinIn",
            "Base Hi": "BaseMaxIn"}
IMAGE = r"<img [^>]*\bsrc=\"[^\"]*/ski-area-snow-report/public/images/([a-z0-9-]+)\.png\"[^>]*>"
LINE = re.compile(r"<p class=\"([a-z-]+)-access-name\">\s*(?:" + IMAGE + r")?\s*<strong>(.*?)</strong>\s*"
                  r"<img [^>]*\bclass=\"status-icon\"[^>]*\bsrc=\"[^\"]*/([a-z0-9-]+)\.png\"[^>]*>([^<]*)</p>", re.S)
LISTED = "-access-name\">"
FIGURE = re.compile(r"<p class=\"resort-info-title\">(.*?)</p>\s*<p>(.*?)</p>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*in")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def areas_of(page: str) -> list:
    """The lifts, the trails and the terrain parks, each kind a mountain area, in the page's order."""
    areas = {name: {"Name": name, "Lifts": [], "Trails": []} for name in KINDS.values()}
    read = 0
    for kind, level, name, icon, said in LINE.findall(page):
        name, status = words(name).rstrip(":").strip(), words(said).capitalize()
        if kind not in KINDS:
            raise ValueError(f"{name} is a kind of line the reader does not know: {kind}")
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a line'} has the status {status!r}, not a word")
        if (icon == CLOSED_ICON) != (status == "Closed"):
            raise ValueError(f"{name}'s status icon is {icon} but it reads {status!r}")
        row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}
        if kind == "slope":
            if level:
                raise ValueError(f"{name} is a lift with a difficulty symbol")
            areas[KINDS[kind]]["Lifts"].append(row)
        else:
            if level not in LEVELS:
                raise ValueError(f"{name} has a difficulty symbol the reader does not know: {level or None}")
            row["Difficulty"] = LEVELS[level] if kind == "trail" else ""
            areas[KINDS[kind]]["Trails"].append(row)
        read += 1
    if read != page.count(LISTED):
        raise ValueError(f"the page has {page.count(LISTED)} lines of lifts and trails but {read} were read")
    if not areas[NAME]["Lifts"] or not areas["Trails"]["Trails"]:
        raise ValueError("the page lists no lifts or no trails")
    return [area for area in areas.values() if area["Lifts"] or area["Trails"]]


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    area = {"Name": "Mountain"}
    for label, said in FIGURE.findall(page):
        label = words(label)
        if label not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(words(said))
        if not inches or SNOWFALL[label] in area:
            raise ValueError(f"the snow report's {label} reads {words(said)!r}, not inches, or is given twice")
        area[SNOWFALL[label]] = number(inches.group(1))
    if "BaseMinIn" not in area or "BaseMaxIn" not in area or "Last24HoursIn" not in area:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    if area["BaseMinIn"] > area["BaseMaxIn"]:
        raise ValueError(f"the base depth runs from {area['BaseMinIn']} down to {area['BaseMaxIn']}")
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": None, "BaseArea": area,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas_of(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
