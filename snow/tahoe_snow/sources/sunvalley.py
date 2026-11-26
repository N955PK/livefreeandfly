"""Sun Valley's lifts and trails, and its snow report, from its mountain report page
(sunvalley.com/the-mountain/mountain-report).

The page is built on the server and holds two mountains, Bald Mountain and Dollar Mountain, each under a tab of its
own in every part of the report: the weather, the lifts and the trails. Each is a mountain of its own here, as
Alpental is in the Summit at Snoqualmie's report: ``parse`` gives Bald Mountain (the key ``sunvalley``), and the
``dollar`` module reads the same page for Dollar Mountain. Under a mountain's tab the lifts and the trails are
tables, one for each part of the mountain (Bowls, Frenchman's, River Run, Seattle Ridge, Warm Springs and so on),
which is a mountain area here. A lift's or trail's status and a trail's difficulty are the symbols in its row, read
from the symbols' names in the words of the page's own key, and one the reader does not know fails; a terrain park
has no difficulty. A trail's grooming symbol is carried as its grooming. The page's own count of the mountain's
lifts and of its trails has to match what is read (its count of Bald Mountain's trails leaves the terrain parks
out), so a change in the page's shape fails instead of showing wrong numbers.

The snow report gives each mountain its snowfall overnight, in the last 24 hours and 7 days and over the season,
in inches, and Bald Mountain its base depth (Dollar Mountain's tab gives none, so its depth stays empty). It says
when it was last updated without the year, in Mountain time, so the year is the one that puts it nearest before the
time of reading. It gives no word for the surface. A snow report that cannot be read costs only the snow report,
not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.sunvalley.com/the-mountain/mountain-report"
# Mountain: (its name, the name the page's tabs give it).
MOUNTAINS = {"sunvalley": ("Sun Valley", "bald"), "dollar": ("Dollar Mountain", "dollar")}
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# Sun Valley is in Idaho's Mountain time.
MOUNTAIN_TIME = ZoneInfo("America/Boise")
# The symbols' names, in the words of the page's own keys.
LIFT_STATUSES = {"open": "Open", "closed": "Closed", "hold": "On hold", "scheduled": "Scheduled", "delayed": "Delayed"}
TRAIL_STATUSES = {"open": "Open", "closed": "Closed", "expected": "Expected", "delayed": "Delayed"}
# The difficulty symbols, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"easy": "Green", "moderate": "Blue", "difficult": "Black", "most-difficult": "Double black",
          "terrain-park": ""}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Overnight": "OvernightIn", "24 hours": "Last24HoursIn", "7 days": "Last7DaysIn", "Base": "BaseIn",
            "Season": "SeasonTotalIn"}
TAB = re.compile(r"<div class=\"mc__tab js-mc__tab[^\"]*\" data-tab=\"([a-z]+)-([a-z]+)\">")
COUNTED = re.compile(r"<span class=\"mc-lifts__graph-value\">\s*(\d+)\s*/\s*(\d+)\s*</span>")
PART = re.compile(r"<a href=\"#\" class=\"accordion__toggle js-accordion__toggle[^\"]*\">([^<]*)<")
TABLE = re.compile(r"<table class=\"mc__table mc-(?:lifts|trails)__table[^\"]*\">(.*?)</table>", re.S)
BODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
SYMBOL = re.compile(r"<span class=\"mc__icon mc__icon-([a-z-]+)\">")
TAG = re.compile(r"<[^>]+>")
FIGURE = re.compile(r"<h3 class=\"mc__heading mc__h3\">\s*([^<]*?)\s*</h3>\s*"
                    r"<p class=\"mc__num mc__num-lg\">\s*([^<]*?)\s*</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")")
UPDATED = re.compile(r"<p class=\"mc__timestamp mc__timestamp-light\">\s*Last Updated:\s*([A-Z][a-z]{2}) (\d{1,2}), "
                     r"(\d{1,2}):(\d{2}) ([AP]M) MT\s*</p>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def tab(page: str, kind: str, mountain: str) -> tuple:
    """Where a mountain's tab of one part of the report starts, and the tab itself: up to the next tab."""
    tabs = list(TAB.finditer(page))
    found = [index for index, each in enumerate(tabs) if each.groups() == (kind, mountain)]
    if len(found) != 1:
        raise ValueError(f"the page has {len(found)} {kind} tabs for {mountain}, not one")
    end = tabs[found[0] + 1].start() if found[0] + 1 < len(tabs) else len(page)
    return tabs[found[0]].start(), page[tabs[found[0]].end():end]


def one_symbol(cell: str, known: dict, what: str, name: str) -> str:
    symbols = SYMBOL.findall(cell)
    if len(symbols) != 1 or symbols[0] not in known:
        raise ValueError(f"{name} has {what} symbols {symbols}, not one the reader knows")
    return known[symbols[0]]


def lift_row(cells: list) -> dict:
    if len(cells) != 4:
        raise ValueError("a row of a lift table is not a name, a type, a status and its hours")
    # A note the resort adds under a lift's name ("Early season: Last up 3:30") is not part of the name.
    name = words(cells[0].split("<")[0])
    if not name:
        raise ValueError("a row of a lift table has no name")
    status = one_symbol(cells[2], LIFT_STATUSES, "status", name)
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(cells: list) -> dict:
    if len(cells) != 4:
        raise ValueError("a row of a trail table is not a name, a status and two marks")
    name = words(cells[0])
    if not name:
        raise ValueError("a row of a trail table has no name")
    status = one_symbol(cells[1], TRAIL_STATUSES, "status", name)
    marks = SYMBOL.findall(cells[2] + cells[3])
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(),
            "Difficulty": one_symbol(cells[0], LEVELS, "difficulty", name),
            "Grooming": "Yes" if "groomed" in marks else "No"}


def listed(page: str, kind: str, mountain: str, read_row) -> list:
    """Each part of the mountain with its lifts or its trails, in the page's order: (the part's name, its rows)."""
    _, section = tab(page, kind, mountain)
    counted = COUNTED.search(section)
    if not counted:
        raise ValueError(f"the page does not count the mountain's {kind}")
    parts = PART.split(section)[1:]
    found = []
    for name, markup in zip(parts[0::2], parts[1::2]):
        tables = TABLE.findall(markup)
        if not words(name) or not tables or not all(BODY.search(table) for table in tables):
            raise ValueError(f"a part of the mountain's {kind} has no name or no table")
        found.append((words(name), [read_row(CELL.findall(each)) for table in tables
                                    for each in ROW.findall(BODY.search(table).group(1))]))
    read = sum(len(rows) for _, rows in found)
    if not read:
        raise ValueError(f"the page lists no {kind}")
    # The page's count of Bald Mountain's trails leaves its terrain parks out, and of Dollar Mountain's takes them in.
    parks = sum(row["Difficulty"] == "" for _, rows in found for row in rows)
    if int(counted.group(2)) not in (read, read - parks):
        raise ValueError(f"the page counts {counted.group(2)} {kind} but {read} were read")
    return found


def updated(page: str, before: int, now: datetime) -> datetime:
    """When the snow report says it was last updated: the page gives the day and the time but not the year."""
    written = UPDATED.findall(page[:before])
    if not written:
        raise ValueError("the snow report does not say when it was updated")
    month, day, hour, minute, half = written[-1]
    year = now.astimezone(MOUNTAIN_TIME).year
    for year in (year, year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
        except ValueError as error:
            raise ValueError(f"the snow report's date could not be read: {error}") from error
        at = at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc)
        # A report read in January and written in December is last year's.
        if at <= now + timedelta(days=1):
            return at
    raise ValueError("the snow report's date is ahead of the time of reading")


def snow_report(page: str, mountain: str, now: datetime) -> dict:
    """The mountain's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    start, section = tab(page, "weather", mountain)
    at = updated(page, start, now)
    figures = {}
    for heading, said in FIGURE.findall(section):
        if heading not in SNOWFALL:
            continue
        inches = INCHES.fullmatch(html.unescape(said))
        if not inches or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report's {heading} reads {said!r}, not inches given once")
        value = float(inches.group(1))
        figures[SNOWFALL[heading]] = int(value) if value.is_integer() else value
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.strftime(STAMP), "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", "BaseIn": None, **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime, key: str = "sunvalley") -> dict:
    """One of the page's two mountains, by its key in MOUNTAINS: Bald Mountain unless told otherwise."""
    name, mountain = MOUNTAINS[key]
    areas = {}
    for part, lifts in listed(page, "lifts", mountain, lift_row):
        areas.setdefault(part, {"Name": part, "Lifts": [], "Trails": []})["Lifts"].extend(lifts)
    for part, trails in listed(page, "trails", mountain, trail_row):
        areas.setdefault(part, {"Name": part, "Lifts": [], "Trails": []})["Trails"].extend(trails)
    feed = {"Name": name, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        feed["SnowReport"] = snow_report(page, mountain, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return feed
