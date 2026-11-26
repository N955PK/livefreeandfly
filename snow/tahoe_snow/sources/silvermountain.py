"""Silver Mountain's lifts and trails, and its snow report, from its trail status and snow report pages
(silvermt.com/snow-report/trail-status and silvermt.com/snow-report).

Both pages are built on the server. The trail status is a folding block for each chairlift, the lift's name with
its status in words beside it, over a list of the trails it serves; each lift is a mountain area here, holding
itself and its trails. A trail's row is its name, a sign of its difficulty (easy, more difficult, difficult,
expert, or a terrain park, which has none) and its status in words. A status is also in its badge's own mark, and
the two have to agree; a sign the reader does not know fails. The gondola from the town is not in the list, so the
snow report's count of lifts is one more than are read and is not checked. Every block and every trail row in the
page is one read, so a change in the page's shape fails instead of showing wrong numbers.

The snow report is a set of tiles, a figure over its label: the summit's snowfall of the last 24 and 48 hours and
its snow depth, the season's snowfall at the summit, in inches, and the surface in words. It gives the depth at
the summit only, and does not say when it was written, so it is carried undated. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime

URLS = {"lifts": "https://silvermt.com/snow-report/trail-status/", "snow": "https://silvermt.com/snow-report/"}
NAME = "Silver Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The difficulty signs, in the words the app's difficulty symbols are keyed on; a terrain park has none.
LEVELS = {"easy": "Green", "more": "Blue", "difficult": "Black", "expert": "Double black", "park": ""}
# The summit's tiles, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Last 24 Hours": "Last24HoursIn", "Last 48 Hours": "Last48HoursIn", "Summit Snow Depth": "BaseIn"}
BLOCK = re.compile(r"<details class=\"[^\"]*\bstatus-list__item\"[^>]*>(.*?)</details>", re.S)
BADGE = r"<span class=\"[^\"]*\bstatus-badge\" data-status=\"([a-z-]+)\">(.*?)</span>"
HEAD = re.compile(r"<h2 class=\"[^\"]*\bstatus-list__name\">(.*?)</h2>\s*" + BADGE, re.S)
ROW = re.compile(r"<li class=\"[^\"]*\bstatus-list__row\"[^>]*>(.*?)</li>", re.S)
TRAIL = re.compile(r"<span class=\"[^\"]*\bstatus-list__row-name\">(.*?)</span>\s*<span class=\"[^\"]*\btrail-sign\" "
                   r"data-sign=\"([a-z-]+)\"[^>]*>\s*</span>\s*" + BADGE, re.S)
TILE = re.compile(r"<p class=\"[^\"]*\bstat-tile__value\">(.*?)</p>(?:(?!stat-tile__value\").)*?"
                  r"<p class=\"[^\"]*\bstat-tile__label\">(.*?)</p>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*in\.?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, marked: str, said: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in the page's words, which have to agree with its badge's mark."""
    if not name or not said:
        raise ValueError("a lift or a trail has no name or no status")
    if marked != "-".join(said.lower().split()):
        raise ValueError(f"{name} is marked {marked} but reads {said!r}")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(row: str) -> dict:
    cells = TRAIL.search(row)
    if not cells:
        raise ValueError("a row of a lift's trails is not a name, a difficulty sign and a status")
    name = words(cells.group(1))
    if cells.group(2) not in LEVELS:
        raise ValueError(f"{name} has a difficulty sign the reader does not know: {cells.group(2)}")
    return status_row(name, cells.group(3), words(cells.group(4)), LEVELS[cells.group(2)])


def lift_areas(page: str) -> list:
    """Each lift with the trails under it, in the page's order."""
    areas = []
    for block in BLOCK.findall(page):
        head = HEAD.search(block)
        if not head:
            raise ValueError("a lift's block does not begin with its name and its status")
        name = words(head.group(1))
        areas.append({"Name": name, "Lifts": [status_row(name, head.group(2), words(head.group(3)), None)],
                      "Trails": [trail_row(row) for row in ROW.findall(block)]})
    blocks, rows = len(re.findall(r"\bstatus-list__item\"", page)), len(re.findall(r"\bstatus-list__row\"", page))
    read = sum(len(area["Trails"]) for area in areas)
    if not areas or len(areas) != blocks or read != rows or not read:
        raise ValueError(f"the page has {blocks} lifts and {rows} trail rows but {len(areas)} and {read} were read")
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists a lift twice")
    return areas


def tiles(page: str) -> dict:
    """The snow report's tiles, each label with the figure the page gives over it."""
    return {words(label): words(said) for said, label in TILE.findall(page)}


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the summit only, and undated."""
    said = tiles(page)
    missing = [label for label in SNOWFALL if label not in said]
    if missing:
        raise ValueError(f"the snow report has no tile for {missing}")
    summit = {"Name": "Summit", **{field: inches(said[label], label) for label, field in SNOWFALL.items()}}
    season = said.get("Summit Snowfall YTD")
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": said.get("Surface Conditions") or None,
            "SeasonTotalIn": inches(season, "season's snowfall") if season else None, "SummitArea": summit,
            "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
