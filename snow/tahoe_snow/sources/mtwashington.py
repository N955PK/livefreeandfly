"""Mount Washington Alpine Resort's lifts and trails, and its snow report, from its snow report page
(mountwashington.ca/the-mountain/snow-report). This is Vancouver Island's Mount Washington, not New Hampshire's.

The page is built on the server: a list of lifts, and a list of trails under a heading for each part of the
mountain (Eagle, Hawk, Boomerang, Easy Acres, Whiskey Jack, Sunrise). A lift's or trail's status is the word on
its row, carried as the page says it. A trail's difficulty is the symbol before its name (green, blue, black,
double black), and a symbol the reader does not know fails. The Nordic, snowshoe and fat bike trails are listed
among the parts of the mountain and are left out: the status is of the lift-served mountain. The page lists the
Boomerang Quad twice: a lift listed again with the same status is read once, and with another status fails. The
page's own counts of lifts, open and in all, and of runs in all are checked against what is read, so a change in its
shape fails instead of showing wrong numbers.

The snow report gives the base depth and the snow of the last 24 hours as the patrol reported them, the resort's
daily dispatch in its own words, and when it was updated, in Pacific time. Mount Washington reports in
centimetres: every figure here is the page's centimetres divided by 2.54 and rounded to one decimal, to give the
inches the Ikon feed's fields hold. The base depth is written twice on the page, and the two have to agree. The
page gives no word for the surface. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.mountwashington.ca/the-mountain/snow-report/"
NAME = "Mount Washington"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double-black": "Double black"}
# The parts of the mountain no lift serves.
NOT_ALPINE = {"nordic", "snowshoe", "fat bike"}
LIST = r"<div class=\"pgri-clist pgri-clist--{kind}[^\"]*\">(.*?</div>)\s*</div>"
# In a list: a heading over a part of the mountain, or a row.
HEADING_OR_ROW = re.compile(r"<p class=\"pgri-clist__area\">(.*?)</p>|<div class=\"pgri-clist__row\">(.*?)</div>", re.S)
CELLS = re.compile(r"\s*<span class=\"pgri-clist__name\">(.*)</span>\s*"
                   r"<span class=\"pgri-clist__pill pgri-clist__pill--[a-z-]+\">([^<]*)</span>\s*", re.S)
SYMBOL = re.compile(r"<span class=\"pgri-clist__diff pgri-clist__diff--([a-z-]+)\"")
TAGS = re.compile(r"<span class=\"pgri-clist__tags\">.*</span>", re.S)
TAG = re.compile(r"<[^>]+>")
COUNTED = r"<span class=\"pgri-conditions__stat pgri-conditions__{kind}\">\s*<strong>\s*(\d+)\s*/\s*(\d+)\s*</strong>"
BASE = re.compile(r"<span class=\"pgri-conditions__stat pgri-conditions__base\">\s*<strong>\s*(\d+(?:\.\d+)?) cm\s*</strong>")
FIGURE = re.compile(r"<h4 class=\"[^\"]*\bmw-ops-stat__value\">\s*([^<]*?)\s*</h4>\s*"
                    r"<p class=\"[^\"]*\bmw-ops-stat__label\b[^\"]*\">\s*([^<]*?)\s*</p>")
UPDATED = re.compile(r"<p class=\"pgri-conditions__updated\">\s*Updated ([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [ap]m)\s*</p>")
DISPATCH = re.compile(r"<p class=\"pgri-conditions__summary\">(.*?)</p>", re.S)


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def rows_of(page: str, kind: str) -> list:
    """The page's list of lifts or of trails: each row with the part of the mountain it is under (None for a
    lift), in the page's order."""
    found = re.search(LIST.format(kind=kind), page, re.S)
    if not found:
        raise ValueError(f"the list of {kind} was not found")
    rows, heading = [], None
    for area, row in HEADING_OR_ROW.findall(found.group(1)):
        if area:
            heading = words(area)
            continue
        cells = CELLS.fullmatch(row)
        if not cells:
            raise ValueError(f"a row of the list of {kind} is not a name and a status")
        symbols = SYMBOL.findall(cells.group(1))
        name, status = words(TAGS.sub(" ", cells.group(1))), words(cells.group(2)).capitalize()
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a row'} has the status {status!r}, not a word")
        if len(symbols) > 1 or any(symbol not in LEVELS for symbol in symbols):
            raise ValueError(f"{name} has difficulty symbols {symbols}, not one the reader knows")
        difficulty = None if kind == "lifts" else LEVELS[symbols[0]] if symbols else ""
        rows.append((heading, {"Name": name, "Status": status, "StatusEnglish": status.lower(),
                               "Difficulty": difficulty}))
    return rows


def lift_rows(page: str) -> list:
    """The lifts, each once: the page lists one of them twice."""
    lifts = {}
    for _, lift in rows_of(page, "lifts"):
        if lifts.setdefault(lift["Name"], lift) != lift:
            raise ValueError(f"{lift['Name']} is listed twice, with two statuses")
    return list(lifts.values())


def trail_areas(page: str) -> list:
    """The trails of each lift-served part of the mountain, in the page's order."""
    areas = {}
    for heading, trail in rows_of(page, "trails"):
        if not heading:
            raise ValueError(f"{trail['Name']} is under no part of the mountain")
        if heading.lower() not in NOT_ALPINE:
            areas.setdefault(heading, []).append(trail)
    return [{"Name": heading, "Lifts": [], "Trails": trails} for heading, trails in areas.items()]


def counted(page: str, kind: str) -> tuple:
    """The page's own count of its lifts or its runs: how many are open, and how many there are."""
    found = re.search(COUNTED.format(kind=kind), page)
    if not found:
        raise ValueError(f"the page's count of {kind} was not found")
    return int(found.group(1)), int(found.group(2))


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated, base = UPDATED.search(page), BASE.search(page)
    if not updated or not base:
        raise ValueError("the snow report has no base depth or does not say when it was updated")
    at = datetime.strptime(updated.group(1), "%B %d, %Y %I:%M %p").replace(tzinfo=PACIFIC_TIME)
    figures = {html.unescape(label): said for said, label in FIGURE.findall(page)}
    depth, new = figures.get("Base Depth (cm)", ""), figures.get("New Snow · 24h", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", depth) or not re.fullmatch(r"\d+(?:\.\d+)?", new):
        raise ValueError(f"the patrol's base depth reads {depth!r} and its new snow {new!r}, not centimetres")
    if float(depth) != float(base.group(1)):
        raise ValueError(f"the page gives two base depths, {base.group(1)} cm and {depth} cm")
    dispatch = DISPATCH.search(page)
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": None,
            "BaseArea": {"Name": "Mountain", "BaseIn": round(float(depth) / CM_PER_INCH, 1),
                         "Last24HoursIn": round(float(new) / CM_PER_INCH, 1)},
            "Report": words(dispatch.group(1)) or None if dispatch else None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = lift_rows(page), trail_areas(page)
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    turning, listed = counted(page, "lifts")
    read = sum(lift["StatusEnglish"] == "open" for lift in lifts)
    if listed != len(lifts) or turning != read:
        raise ValueError(f"the page counts {turning} of {listed} lifts open but {read} of {len(lifts)} were read")
    trails = sum(len(area["Trails"]) for area in areas)
    if counted(page, "trails")[1] != trails:
        raise ValueError(f"the page counts {counted(page, 'trails')[1]} runs but {trails} were read")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
