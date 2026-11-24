"""Owl's Head's lifts and trails, and its snowfall, from its ski conditions page
(owlshead.com/en/ski-conditions, the English page).

The page is built on the server: a block for each lift, "1. Summit" to "6. Magic carpet", headed by the lift's name
and its status and holding the trails it serves, then a block for the snowparks and one for alpine touring. Each
numbered block is a mountain area here, holding the lift (named without its number) and its trails; the snowparks
are an area with no lift, and alpine touring, which lists nothing, is left out. A lift's or trail's status is the
word the page writes, "Open" or "Closed"; any other word is carried as the page says it. A trail's difficulty is
the symbol in its row (Quebec's easy, difficult, very difficult and extreme are the green circle, the blue square,
the black diamond and the double black), and one the reader does not know fails; a groomed symbol is carried as its
grooming. Each block's own count of its trails, and the page's count of its chairlifts, are checked against what is
read, so a change in the page's shape fails instead of showing wrong numbers.

The site gives no depth of snow and no word for the surface. It gives "fresh snow" (taken as the last 24 hours:
the next figure is the last 48), the last 48 hours and 7 days and the season's total in centimetres, which are
turned into inches here (divided by 2.54, to one decimal), and the time of its last modification in Eastern time.
A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://owlshead.com/en/ski-conditions/"
NAME = "Owl's Head"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The level symbols, in the words the app's difficulty symbols are keyed on; the snowpark's has none.
LEVELS = {"icon-easy": "Green", "icon-diff": "Blue", "icon-vdiff": "Black", "icon-ext": "Double black",
          "icon-park": ""}
# The snowfall's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"of fresh snow": "Last24HoursIn", "Last 48 h": "Last48HoursIn", "Last 7 days": "Last7DaysIn",
            "Total season": "SeasonTotalIn"}
BLOCK = "<div class=\"section-piste\""
HEADING = re.compile(r"<span class=\"label-title[^\"]*\">(.*?)</span>\s*<span class=\"section-[a-z-]+\">(.*?)</span>",
                     re.S)
NUMBERED = re.compile(r"\d+\.\s*(.+)")
BLOCK_COUNT = re.compile(r"<p class=\"sum-total[^\"]*\">\s*\d+\s*/\s*(\d+)\s*</p>")
ROW = "<div class=\"table-row\">"
CELL = r"<div class=\"{name}\">(.*?)</div>"
SYMBOL = re.compile(r"<span class=\"(icon-[a-z]+)")
STATE = re.compile(r"<span class=\"slope-[a-z-]+\">(.*?)</span>", re.S)
TAG = re.compile(r"<[^>]+>")
STAT = re.compile(r"<h4>\s*([^<]*?)\s*</h4>\s*<div class=\"text p-large\">\s*([^<]*?)\s*</div>")
MODIFIED = re.compile(r"Last modification:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float:
    return round(centimetres / 2.54, 1)


def carried(said: str, name: str) -> dict:
    """A status in the page's own word."""
    status = " ".join(said.split()).capitalize()
    if not status:
        raise ValueError(f"{name} has no status")
    return {"Status": status, "StatusEnglish": status.lower()}


def cell(row: str, name: str, trail: str) -> str:
    found = re.search(CELL.format(name=name), row, re.S)
    if not found:
        raise ValueError(f"{trail} has no {name}")
    return found.group(1)


def trail_row(row: str) -> dict:
    name = words(cell(row, "name", "a trail"))
    if not name:
        raise ValueError("a trail has no name")
    # A glade's tree is sometimes drawn beside its level; it is not a level.
    levels = [symbol for symbol in SYMBOL.findall(cell(row, "level", name)) if symbol != "icon-wood"]
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name} has level symbols {levels}, not one the reader knows")
    states = STATE.findall(cell(row, "slope-state", name))
    if len(states) != 1:
        raise ValueError(f"{name} has {len(states)} statuses, not one")
    return {"Name": name, **carried(words(states[0]), name), "Difficulty": LEVELS[levels[0]],
            "Grooming": "Yes" if "icon-damee" in cell(row, "state", name) else "No"}


def areas_of(page: str) -> list:
    """Each lift with the trails under it, and the snowparks, in the page's order."""
    areas = []
    for block in page.split(BLOCK)[1:]:
        heading = HEADING.search(block)
        if not heading:
            raise ValueError("a block of trails has no name and status")
        title = words(heading.group(1))
        trails = [trail_row(row) for row in block.split(ROW)[1:]]
        counted = BLOCK_COUNT.search(block)
        if counted and int(counted.group(1)) != len(trails):
            raise ValueError(f"{title} counts {counted.group(1)} trails but {len(trails)} were read")
        if trails and not counted:
            raise ValueError(f"{title} does not count its trails")
        lift = NUMBERED.fullmatch(title)
        lifts = [{"Name": lift.group(1), **carried(words(heading.group(2)), title), "Difficulty": None}] if lift else []
        if lifts or trails:
            areas.append({"Name": lift.group(1) if lift else title, "Lifts": lifts, "Trails": trails})
    return areas


def stats(page: str) -> dict:
    """The figures the page gives under small headings: its snowfall and its counts."""
    return {heading: said for heading, said in STAT.findall(page)}


def snow_report(page: str) -> dict:
    """The page's snowfall in the shape of the Ikon feed's SnowReport, centimetres turned into inches. There is no
    depth of snow to give."""
    given, figures = stats(page), {}
    for heading, field in SNOWFALL.items():
        said = re.fullmatch(r"(\d+(?:\.\d+)?)\s*cm", given.get(heading, ""))
        if not said:
            raise ValueError(f"the snowfall's {heading!r} reads {given.get(heading)!r}, not centimetres")
        figures[field] = inches(float(said.group(1)))
    modified = MODIFIED.search(page)
    if not modified:
        raise ValueError("the page does not say when it was last modified")
    try:
        at = datetime.strptime(modified.group(1), "%Y-%m-%d %H:%M")
    except ValueError as error:
        raise ValueError(f"the page's date could not be read: {error}") from error
    season = figures.pop("SeasonTotalIn")
    return {"LastUpdate": at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    # Every run of spaces and line ends is read as one space, so the page's layout does not matter.
    page = " ".join(page.split())
    areas = areas_of(page)
    lifts = sum(len(area["Lifts"]) for area in areas)
    if not lifts or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    counted = re.fullmatch(r"\d+\s*/\s*(\d+)", stats(page).get("Chairlifts", ""))
    if not counted:
        raise ValueError("the page's count of chairlifts was not found")
    if int(counted.group(1)) != lifts:
        raise ValueError(f"the page counts {counted.group(1)} chairlifts but {lifts} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
