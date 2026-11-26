"""Elk Mountain's lifts and trails, and its snow report, from its conditions page (elkskier.com/conditions).

The page is built on the server. Its trail status is a table of the lifts, each with its status in a badge, and a
table of trails for each difficulty (easy, intermediate, expert) and one for the terrain parks: a trail's row is
its name, its status in a badge, whether snow is being made on it and whether it is groomed ("Yes" or "No"). A
status is the badge's words (Open, Partially open, Closed), and it has to agree with the badge's class. The lifts
are one mountain area and each table of trails another; a terrain park has no difficulty. A table the reader does
not know fails, and the page's own counts of lifts and of trails have to match what is read, so a change in the
page's shape fails instead of showing wrong numbers.

The conditions report gives the base depth, as one depth or a least and a most, and the new snow of the last 24
hours, in inches, each a dash when the mountain gives none, and the surface in words, with the day and time it
was updated, in Eastern time. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.elkskier.com/conditions/"
NAME = "Elk Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/New_York")
LIFTS = "lifts"
# The tables of trails, by the name each area is given and the words the app's difficulty symbols are keyed on.
LEVELS = {"easy": ("Easy", "Green"), "intermediate": ("Intermediate", "Blue"), "expert": ("Expert", "Black"),
          "parks": ("Terrain Parks", "")}
# The badges' classes, with the words each has to carry.
BADGES = {"open": "open", "partial": "partially open", "closed": "closed"}
GROUP = re.compile(r"<div class=\"elk-snow-group elk-snow-group-([a-z-]+)\">\s*<table\b[^>]*>(.*?)</table>", re.S)
BODY = re.compile(r"<tbody>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
NAMED = re.compile(r"<th scope=\"row\">(.*?)(?:<span class=\"elk-snow-meta\".*?)?</th>", re.S)
BADGE = re.compile(r"<span class=\"elk-snow-badge elk-snow-([a-z-]+)\">(.*?)</span>\s*</td>", re.S)
GROOMED = re.compile(r"<td data-label=\"Groomed\">(.*?)</td>", re.S)
UPDATED = re.compile(r"<p class=\"elk-snow-updated\">\s*Updated "
                     r"([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [ap]m)\s*</p>")
TILE = re.compile(r"<span class=\"elk-snow-tile-value\">(.*?)</span>\s*"
                  r"<span class=\"elk-snow-tile-label\">(.*?)</span>", re.S)
DETAIL = re.compile(r"<tr>\s*<th scope=\"row\">([^<]*)</th>\s*<td>(.*?)</td>\s*</tr>", re.S)
COUNTED = re.compile(r"(\d+)\s*/\s*(\d+)")
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\"|in\.?)?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:″|”|\"|in\.?)?")
NONE = re.compile(r"[–—-]*")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(row: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in its badge's words, which have to agree with the badge's class."""
    named, badge = NAMED.search(row), BADGE.search(row)
    if not named or not badge or not words(named.group(1)):
        raise ValueError("a row of the trail status is not a name and a status in a badge")
    name, said = words(named.group(1)), words(badge.group(2))
    if BADGES.get(badge.group(1)) != said.lower():
        raise ValueError(f"{name} is marked {badge.group(1)} but reads {said!r}")
    return {"Name": name, "Status": said.capitalize(), "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(row: str, difficulty: str) -> dict:
    found, groomed = status_row(row, difficulty), GROOMED.search(row)
    if not groomed or words(groomed.group(1)) not in ("Yes", "No"):
        raise ValueError(f"{found['Name']} does not say whether it is groomed")
    return {**found, "Grooming": words(groomed.group(1))}


def rows_of(page: str) -> tuple:
    """The lifts, and the trails of each table, in the page's order."""
    lifts, areas = [], []
    for kind, table in GROUP.findall(page):
        body = BODY.search(table)
        rows = ROW.findall(body.group(1)) if body else []
        if kind == LIFTS:
            lifts += [status_row(row, None) for row in rows]
        elif kind in LEVELS:
            name, difficulty = LEVELS[kind]
            areas.append({"Name": name, "Lifts": [], "Trails": [trail_row(row, difficulty) for row in rows]})
        else:
            raise ValueError(f"the trail status has a table the reader does not know: {kind}")
    if page.count("class=\"elk-snow-group ") != len(areas) + bool(lifts):
        raise ValueError("the tables of the trail status were not all read")
    return lifts, [area for area in areas if area["Trails"]]


def tiles(page: str) -> dict:
    """The conditions report's tiles, each label (in small letters) with the figure the page gives over it."""
    return {words(label).lower(): words(said) for said, label in TILE.findall(page)}


def checked(rows: list, said: dict, label: str) -> None:
    """Refuse the page when its own count of lifts or of trails is not what was read."""
    found = COUNTED.fullmatch(said.get(label, ""))
    if not found:
        raise ValueError(f"the page's count under {label!r} was not found")
    if int(found.group(2)) != len(rows):
        raise ValueError(f"the page counts {found.group(2)} under {label!r} but {len(rows)} were read")


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def inches(said: str, label: str) -> float | int | None:
    """A depth in inches, or None where the mountain gives a dash."""
    if NONE.fullmatch(said):
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the conditions report's {label} reads {said!r}, not inches")
    return number(found.group(1))


def depth(said: str) -> dict:
    """The base depth as one figure, or as its least and its most where the mountain gives the two."""
    spread = RANGE.fullmatch(said)
    if not spread:
        return {"BaseIn": inches(said, "base depth")}
    low, high = number(spread.group(1)), number(spread.group(2))
    if low > high:
        raise ValueError(f"the base depth runs from {low} down to {high}")
    return {"BaseMinIn": low, "BaseMaxIn": high}


def snow_report(page: str, said: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated = UPDATED.search(page)
    if not updated:
        raise ValueError("the conditions report does not say when it was updated")
    try:
        at = datetime.strptime(updated.group(1), "%B %d, %Y %I:%M %p").replace(tzinfo=LOCAL_TIME)
    except ValueError as error:
        raise ValueError(f"the time the report was updated could not be read: {error}") from error
    missing = [label for label in ("base depth", "new snow, 24 hours") if label not in said]
    if missing:
        raise ValueError(f"the conditions report has no tile for {missing}")
    area = {"Name": "Mountain", **depth(said["base depth"]),
            "Last24HoursIn": inches(said["new snow, 24 hours"], "new snow")}
    details = {words(label).lower(): words(value) for label, value in DETAIL.findall(page)}
    surface = details.get("surface conditions", "")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None if NONE.fullmatch(surface) else surface, "SeasonTotalIn": None, "BaseArea": area,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = rows_of(page)
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    said = tiles(page)
    checked(lifts, said, "lifts open")
    checked([trail for area in areas for trail in area["Trails"] if trail["Difficulty"]], said, "trails open")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page, said)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
