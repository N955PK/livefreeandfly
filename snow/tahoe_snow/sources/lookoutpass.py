"""Lookout Pass's lifts and trails, and its snow report, from its snow report page (skilookout.com/snow-report).

The page is built on the server, by a "powderwatch" block. Its "Lift & Slope Status" is a heading for each lift
with the lift's status in words beside it, over a table of the trails it serves; each lift is a mountain area here,
holding itself and its trails. A status is also in its badge's class, and the two have to agree. A trail's row is
its name, its status, whether it is groomed ("Yes", "No", or "Glade" for a glade, which is never groomed) and its
difficulty as symbols: one green circle, blue square or black diamond, two black diamonds for a double black, or
the park symbol, which has no difficulty. A trail between two difficulties carries both symbols and is given the
harder. A symbol the reader does not know fails. Every lift and trail row in the
page is one read, so a change in the page's shape fails instead of showing wrong numbers.

The snow report gives, at the summit and at the base, the snowfall of the last 24, 48 and 72 hours, the season's
total and the depth, in inches, and the surface in words. The block carries the time it was last updated as a
count of seconds, which is what is read, so no time zone is needed. A snow report that cannot be read costs only
the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://skilookout.com/snow-report/"
NAME = "Lookout Pass"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The difficulty symbols, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {("green-circle",): "Green", ("blue-square",): "Blue", ("black-diamond",): "Black",
          ("black-diamond", "black-diamond"): "Double black", ("park",): "",
          # A trail between two difficulties carries both symbols: it is given the harder.
          ("green-circle", "blue-square"): "Blue", ("blue-square", "black-diamond"): "Black"}
GROOMED = {"yes": "Yes", "no": "No", "glade": "No"}
# The snow report's places and lines, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Base": "BaseArea", "Summit": "SummitArea"}
SNOWFALL = {"24h Snow": "Last24HoursIn", "48h Snow": "Last48HoursIn", "72h Snow": "Last72HoursIn",
            "Depth": "BaseIn", "Season Total": "SeasonTotalIn"}
BLOCK = re.compile(r"<div class=\"powderwatch-conditions\"[^>]*\sdata-timestamp=\"(\d+)\"")
LIFTS = re.compile(r"<div class=\"powderwatch-lifts\">(.*?)(?:<div class=\"powderwatch-notes\">|</main>|$)", re.S)
LIFT = re.compile(r"<div class=\"lift-header\"[^>]*>\s*<h4>(.*?)</h4>\s*<div class=\"lift-status-container\">\s*"
                  r"<div class=\"lift-status ([a-z-]+)\">(.*?)</div>", re.S)
ROW = re.compile(r"<tr class=\"slope-row\">(.*?)</tr>", re.S)
TRAIL = re.compile(r"<td class=\"trail-name\">(.*?)</td>\s*<td class=\"status-cell\">\s*"
                   r"<span class=\"status-badge ([a-z-]+)\">(.*?)</span>.*?</td>\s*<td class=\"groomed-cell\">\s*"
                   r"<span class=\"groomed-badge [a-z-]+\">(.*?)</span>\s*</td>\s*"
                   r"<td class=\"difficulty-cell\">(.*?)</td>", re.S)
SYMBOL = re.compile(r"<span class=\"difficulty-symbol ([a-z-]+)\">")
SNOW = re.compile(r"<div class=\"powderwatch-snow-report\">(.*?)<div class=\"powderwatch-weather\">", re.S)
SECTION = re.compile(r"<div class=\"snow-report-section\">\s*<h4>(.*?)</h4>(.*?)(?=<div class=\"snow-report-section\">"
                     r"|$)", re.S)
LINE = re.compile(r"<span class=\"label\">(.*?):</span>\s*<span class=\"value\">(.*?)</span>", re.S)
SURFACE = re.compile(r"<div class=\"surface-data\">(.*?)</div>\s*</div>\s*</div>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\")")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, marked: str, said: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in the page's words, which have to agree with its badge."""
    if not name or not said:
        raise ValueError("a lift or a trail has no name or no status")
    if marked != "-".join(said.lower().split()):
        raise ValueError(f"{name} is marked {marked} but reads {said!r}")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(row: str) -> dict:
    cells = TRAIL.search(row)
    if not cells:
        raise ValueError("a row of a trail table is not a name, a status, a grooming and a difficulty")
    name, symbols, groomed = words(cells.group(1)), tuple(SYMBOL.findall(cells.group(5))), words(cells.group(4))
    if symbols not in LEVELS:
        raise ValueError(f"{name} has difficulty symbols the reader does not know: {list(symbols)}")
    if groomed.lower() not in GROOMED:
        raise ValueError(f"{name}'s grooming reads {groomed!r}, which the reader does not know")
    return {**status_row(name, cells.group(2), words(cells.group(3)), LEVELS[symbols]),
            "Grooming": GROOMED[groomed.lower()]}


def lift_areas(page: str) -> list:
    """Each lift with the trails under it, in the page's order."""
    report = LIFTS.search(page)
    if not report:
        raise ValueError("the lift and slope status was not found")
    body = report.group(1)
    found = list(LIFT.finditer(body))
    areas = []
    for at, lift in enumerate(found):
        name = words(lift.group(1))
        end = found[at + 1].start() if at + 1 < len(found) else len(body)
        trails = [trail_row(row) for row in ROW.findall(body[lift.end():end])]
        areas.append({"Name": name, "Lifts": [status_row(name, lift.group(2), words(lift.group(3)), None)],
                      "Trails": trails})
    lifts, rows = body.count("class=\"lift-header\""), body.count("class=\"slope-row\"")
    read = sum(len(area["Trails"]) for area in areas)
    if not areas or len(areas) != lifts or read != rows or not read:
        raise ValueError(f"the page has {lifts} lifts and {rows} trail rows but {len(areas)} and {read} were read")
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists a lift twice")
    return areas


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the base and the summit."""
    block, report = BLOCK.search(page), SNOW.search(page)
    if not block or not report:
        raise ValueError("the snow report or the time it was updated was not found")
    out, seasons = {}, {}
    for place, body in SECTION.findall(report.group(1)):
        place = words(place)
        if place not in STAKES or STAKES[place] in out:
            raise ValueError(f"the snow report is given for a place the reader does not know, or twice: {place}")
        figures = {SNOWFALL[words(label)]: inches(words(said), words(label)) for label, said in LINE.findall(body)
                   if words(label) in SNOWFALL}
        seasons[place] = figures.pop("SeasonTotalIn", None)
        out[STAKES[place]] = {"Name": place, **figures}
    if "BaseIn" not in out.get("BaseArea", {}) or "Last24HoursIn" not in out["BaseArea"]:
        raise ValueError("the snow report has no depth or no 24 hour snowfall at the base")
    surface = SURFACE.search(page)
    said = dict((words(label), words(value)) for label, value in LINE.findall(surface.group(1))) if surface else {}
    at = datetime.fromtimestamp(int(block.group(1)), timezone.utc)
    return {"LastUpdate": at.strftime(STAMP), "Resortwide": True, "BaseConditions": said.get("Primary") or None,
            "SeasonTotalIn": seasons.get("Base"), **out, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
