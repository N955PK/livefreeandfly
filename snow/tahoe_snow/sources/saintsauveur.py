"""Sommet Saint-Sauveur's lifts and trails, and its snow report, from Les Sommets' trail conditions page
(sommets.com/en/what-to-do/skiing-snowboarding/trail-conditions), read in English.

The page covers all six of Les Sommets' mountains. Each has a block the page's own script draws its tables from:
the lifts, the trails and the page's counts are JSON in the block's attributes. Two blocks are read, Sommet
Saint-Sauveur and its Versant Avila, which share a ticket and are joined on the snow; each is a mountain area
here. The other four mountains are left out. The page shows each block twice (once for narrow screens): the two
have to agree.

A lift or trail carries no status word, only whether it is open by day and whether it is open by night; the page
shows one or the other, and says in the block which it opens on (the night once the day is over). The reader
follows the page: open by the half of the day the page is showing is Open, anything else Closed. A trail's
difficulty is the page's word (Easy -> Green, Difficult -> Blue, Very difficult -> Black, Extreme -> Double
black, Terrain Park -> none), and one the reader does not know fails; "Groomed" among its types is carried as
its grooming. The page's own counts of lifts and trails are checked against what is read, so a change in its
shape fails instead of showing wrong numbers.

The snow report is Sommet Saint-Sauveur's own block of the page: the snow of the last 24 and 48 hours and the
season's total, words for the base, the surface and the cover, and the time it was updated in Eastern time.
**The page reports centimetres; they are converted to inches here (divided by 2.54, rounded to one decimal).**
The page gives no base depth, so ``BaseIn`` is None. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.sommets.com/en/what-to-do/skiing-snowboarding/trail-conditions/"
NAME = "Sommet Saint-Sauveur"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The page's names for the two sides of the mountain, in its order.
AREAS = ("Sommet Saint-Sauveur", "Versant Avila")
# The page's difficulty words, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"easy": "Green", "difficult": "Blue", "very difficult": "Black", "extreme": "Double black",
          "terrain park": ""}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"last 24 hours": "Last24HoursIn", "last 48 hours": "Last48HoursIn", "season total": "SeasonTotalIn"}
BLOCK = re.compile(r"<div data-component=\"sommets-app-conditions-winter-list\"([^>]*)>")
ATTRIBUTE = re.compile(r"\s(data-[a-z-]+)=\"([^\"]*)\"")
OF = re.compile(r"\d+\s*/\s*(\d+)")
WEATHER = re.compile(r"<h2>\s*Weather\s*</h2>\s*<h2>\s*<span[^>]*>\s*{name}\s*</span>\s*</h2>(.*?)"
                     r"(?=<h2>\s*Weather\s*</h2>|\Z)", re.S)
UPDATED = re.compile(r"Information updated ([A-Z][a-z]+) (\d{1,2}),? (\d{4}) at (\d{1,2})\s*h\s*(\d{2})")
FIGURE = re.compile(r"<div class=\"text-2xl[^\"]*\">\s*([^<]*?)\s*</div>\s*<div class=\"text-xxs[^\"]*\">\s*([^<]*?)\s*</div>")
CENTIMETRES = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm")
WORD = re.compile(r"<div class=\"text-xxs[^\"]*\">\s*([^<]*?)\s*</div>\s*<div class=\"text-xl[^\"]*\">\s*([^<]*?)\s*</div>")


def inches(centimetres: float) -> float | int:
    value = round(centimetres / 2.54, 1)
    return int(value) if value.is_integer() else value


def blocks(page: str) -> dict:
    """Each mountain's block of the page by its name: its counts, its lifts, its trails and the half of the day
    it opens on."""
    found = {}
    for tag in BLOCK.findall(page):
        said = {name: html.unescape(value) for name, value in ATTRIBUTE.findall(tag)}
        try:
            block = {"summary": json.loads(said["data-summary"]), "lifts": json.loads(said["data-lift-items"]),
                     "trails": json.loads(said["data-trail-items"]),
                     "night": {"true": True, "false": False}[said["data-is-night-prop"].lower()]}
            name = block["summary"]["Name"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"a mountain's block could not be read: {error!r}") from error
        if found.setdefault(name, block) != block:
            raise ValueError(f"the page gives {name} twice, differently")
    return found


def row(item: dict, night: bool) -> dict:
    """One lift or trail: open if it is open in the half of the day the page is showing."""
    name, is_open = item.get("Name"), item.get("IsNightOpen" if night else "IsDayOpen")
    if not isinstance(name, str) or not name.strip() or not isinstance(is_open, bool):
        raise ValueError(f"{name or 'a row'} does not say whether it is open")
    status = "Open" if is_open else "Closed"
    return {"Name": " ".join(name.split()), "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(item: dict, night: bool) -> dict:
    trail = row(item, night)
    level = str(item.get("Difficulty", "")).strip().lower()
    if level not in LEVELS:
        raise ValueError(f"{trail['Name']} has the difficulty {item.get('Difficulty')!r}, not one the reader knows")
    trail["Difficulty"] = LEVELS[level]
    types = [said.strip().lower() for said in str(item.get("Type") or "").split(",")]
    trail["Grooming"] = "Yes" if "groomed" in types else "No"
    return trail


def counted(summary: dict, field: str, name: str) -> int:
    """The page's own count of all of a mountain's lifts or trails, from its "open / all"."""
    found = OF.fullmatch(str(summary.get(field, "")).strip())
    if not found:
        raise ValueError(f"{name}'s count {field} was not found")
    return int(found.group(1))


def mountain_area(name: str, block: dict) -> dict:
    lifts = [row(item, block["night"]) for item in block["lifts"]]
    trails = [trail_row(item, block["night"]) for item in block["trails"]]
    for what, read, field in (("lifts", lifts, "LiftDayOpen"), ("trails", trails, "TrailDayOpen")):
        if len(read) != counted(block["summary"], field, name):
            raise ValueError(f"the page counts {counted(block['summary'], field, name)} {what} at {name} "
                             f"but {len(read)} were read")
    return {"Name": name, "Lifts": lifts, "Trails": trails}


def snow_report(page: str) -> dict:
    """The mountain's own snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    block = re.search(WEATHER.pattern.format(name=re.escape(AREAS[0])), page, re.S)
    if not block:
        raise ValueError("the snow report was not found")
    updated = UPDATED.search(block.group(1))
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute = updated.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute}", "%Y %B %d %H:%M")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    figures = {}
    for said, label in FIGURE.findall(block.group(1)):
        label = html.unescape(label).lower()
        if label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        centimetres = CENTIMETRES.fullmatch(html.unescape(said))
        if not centimetres or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label} reads {said!r}, not centimetres given once")
        figures[SNOWFALL[label]] = inches(float(centimetres.group(1).replace(",", ".")))
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    said = {html.unescape(label).lower(): html.unescape(word) for label, word in WORD.findall(block.group(1))}
    return {"LastUpdate": at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": said.get("surface") or None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", "BaseIn": None, **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    found = blocks(page)
    missing = [name for name in AREAS if name not in found]
    if missing:
        raise ValueError(f"the page has no block for {missing}")
    areas = [mountain_area(name, found[name]) for name in AREAS]
    if not any(area["Lifts"] for area in areas) or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
