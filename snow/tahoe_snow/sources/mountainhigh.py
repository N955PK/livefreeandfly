"""Mountain High's lifts and trails, and its snow report, from its lift and trail report and its snow conditions
pages (mthigh.com/site/trails-and-conditions/conditions/alpine-grooming and .../snow-and-weather-report).

Both pages are built on the server. The lift and trail report has, for each of the resort's two mountains ("West
Resort" and "East Resort"), a table of its lifts and a table of its trails; each mountain is a mountain area here.
A status is an icon with its word, and the two have to agree: open and closed are carried as they are, the page's
"expected to open" as Expected and its "hold" as On hold. A trail the page marks groomed is open and groomed, and
grooming is carried only on a day the page marks some trail so; a trail given over to a race is carried as Race. A
trail's difficulty is its icon (beginner, intermediate, advanced, expert), and one the reader does not know fails.
Every row of the four tables is one read, bar the notes the page puts under a row, so a change in the page's shape
fails instead of showing wrong numbers. The page's own count of open lifts is not used: before the lifts turn it
already counts the ones the tables give as expected.

The snow conditions page gives the depth at the base and at the top, the snowfall of the last 24 and 48 hours and
7 days and the season's total at the base (the top's is not carried), in inches, the surface in the resort's
words, and the day and time the report was updated, in Pacific time. A snow report that cannot be read costs only
the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.mthigh.com/site/trails-and-conditions/conditions/alpine-grooming",
        "snow": "https://www.mthigh.com/site/trails-and-conditions/conditions/snow-and-weather-report"}
NAME = "Mountain High"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
# The status icons, in the words the app reads. A groomed trail is an open one.
STATUSES = {"open": "Open", "closed": "Closed", "expected": "Expected", "hold": "On hold", "groomed": "Open",
            "race": "Race"}
# The difficulty icons, in the words the app's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black"}
# The snow figures' labels, as (the stake, the name the Ikon feed gives the figure); None is the season's total.
FIGURES = {"Base Snow Depth": ("BaseArea", "BaseIn"), "Top Snow Depth": ("SummitArea", "BaseIn"),
           "24 Hour Snowfall": ("BaseArea", "Last24HoursIn"), "48 Hour Snowfall": ("BaseArea", "Last48HoursIn"),
           "7 Day Snowfall": ("BaseArea", "Last7DaysIn"), "Base Season Snowfall": (None, "SeasonTotalIn")}
MOUNTAIN = re.compile(r"<h2>(.*?)</h2>", re.S)
TABLE = re.compile(r"<table class=\"StatusReport StatusReport--(lifts|trails)\"[^>]*>.*?<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr class=\"([^\"]*)\">(.*?)</tr>", re.S)
NOTE = "StatusReport-rowNote"
ICON = re.compile(r"<td class=\"StatusReport-type\">\s*<span class=\"ir i-(lift|skill)-([a-z-]+)\">")
TITLE = re.compile(r"<th scope=\"row\" class=\"StatusReport-title\">(.*?)(?:<span\b|</th>)", re.S)
STATUS = re.compile(r"<td class=\"StatusReport-status\">\s*<span class=\"ir i-status-([a-z-]+)\">(.*?)</span>", re.S)
UPDATED = re.compile(r"<p class=\"u-textRight\">\s*Updated: [A-Z][a-z]+, ([A-Z][a-z]+) (\d{1,2}), (\d{4}) "
                     r"(\d{1,2}):(\d{2}) ([AP]M)\s*</p>")
BOX = "<div class=\"LabelBox\">"
BOX_TITLE = re.compile(r"<h3 class=\"LabelBox-title\">(.*?)</h3>", re.S)
DIGITS = re.compile(r"<div class=\"t-digit-lg\">\s*(\d+(?:\.\d+)?)\s*<span[^>]*>(.*?)</div>", re.S)
SURFACE = re.compile(r"<div class=\"LabelBox-content\">\s*<div>\s*<p>(.*?)</p>", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def row_of(kind: str, body: str) -> dict:
    """One lift or trail."""
    icon, title, status = ICON.search(body), TITLE.search(body), STATUS.search(body)
    if not icon or not title or not words(title.group(1)) or not status:
        raise ValueError(f"a row of a table of {kind} is not a kind, a name and a status")
    name, marked, said = words(title.group(1)), status.group(1), words(status.group(2))
    if marked not in STATUSES or marked != said.lower():
        raise ValueError(f"{name}'s status icon is {marked} and reads {said!r}, not one the reader knows")
    row = {"Name": name, "Status": STATUSES[marked], "StatusEnglish": STATUSES[marked].lower(), "Difficulty": None}
    if kind == "trails":
        if icon.group(1) != "skill" or icon.group(2) not in LEVELS:
            raise ValueError(f"{name} has a difficulty the reader does not know: {icon.group(2)}")
        row["Difficulty"] = LEVELS[icon.group(2)]
        if marked == "groomed":
            row["Grooming"] = "Yes"
    elif icon.group(1) != "lift":
        raise ValueError(f"{name} is in a table of lifts but is not marked as one")
    return row


def lift_areas(page: str) -> list:
    """Each of the two mountains with its lifts and trails, in the page's order."""
    page = COMMENT.sub("", page)
    pieces = MOUNTAIN.split(page)
    areas, read = [], 0
    for name, body in zip(pieces[1::2], pieces[2::2]):
        tables = TABLE.findall(body)
        if not tables:
            continue
        area = {"Name": words(name), "Lifts": [], "Trails": []}
        for kind, rows in tables:
            found = [row_of(kind, row) for marks, row in ROW.findall(rows) if NOTE not in marks]
            area["Lifts" if kind == "lifts" else "Trails"] += found
            read += len(found)
        areas.append(area)
    listed = page.count("<th scope=\"row\" class=\"StatusReport-title\">")
    if not read or read != listed:
        raise ValueError(f"the page has {listed} lift and trail rows but {read} were read")
    lifts = [lift["Name"] for area in areas for lift in area["Lifts"]]
    trails = [trail for area in areas for trail in area["Trails"]]
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    if len(set(lifts)) != len(lifts):
        raise ValueError("the page lists a lift twice")
    # The page says which trails are groomed only by marking them so: on a day it does, the others are not.
    if any("Grooming" in trail for trail in trails):
        for trail in trails:
            trail.setdefault("Grooming", "No")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the base and the top."""
    updated = UPDATED.search(page)
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute, half = updated.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    out = {"BaseArea": {"Name": "Base"}, "SummitArea": {"Name": "Top"}}
    season = surface = None
    seen = set()
    for box in page.split(BOX)[1:]:
        title = BOX_TITLE.search(box)
        label = words(title.group(1)) if title else ""
        if label == "Primary":
            said = SURFACE.search(box)
            surface = words(said.group(1)) if said and words(said.group(1)) else None
        if label not in FIGURES:
            continue
        figure = DIGITS.search(box[:title.start()])
        if not figure or words(figure.group(2)) != "″" or label in seen:
            raise ValueError(f"the snow report's {label} is not a number of inches given once")
        seen.add(label)
        value = float(figure.group(1))
        value = int(value) if value.is_integer() else value
        area, field = FIGURES[label]
        if area is None:
            season = value
        else:
            out[area][field] = value
    if "BaseIn" not in out["BaseArea"] or "Last24HoursIn" not in out["BaseArea"]:
        raise ValueError("the snow report has no depth at the base or no 24 hour snowfall")
    return {"LastUpdate": at.replace(tzinfo=PACIFIC_TIME).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": surface, "SeasonTotalIn": season, **out, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
