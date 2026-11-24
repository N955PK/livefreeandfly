"""Sun Peaks' lifts and trails, and its snow report, from its lifts and trail status page and its weather and snow
report page (sunpeaksresort.com/ski-ride/weather-conditions-cams/lifts-trail-status and /weather-snow-report).

Both pages are built on the server. The status page is a row for each lift and each alpine trail. A row's status
is the symbol in its status cell, in the words of the page's own key: open, closed, groomed, or groomed with fresh
(the last two are open trails that have been groomed), and a symbol the reader does not know fails. A trail's first
symbol is its difficulty (a terrain park or a glade has none here) and its row names its zone (Tod Mountain,
Sundance, Mt. Morrisey, Orient Ridge, West Bowl), which is its mountain area; the zones' names are the page's own,
from its zone filter. The lifts name no zone and are an area of their own. The page's own count of lifts is checked
against what is read, so a change in its shape fails instead of showing wrong numbers; its count of trails leaves
some of the listed rows out, so the list is only required to hold at least that many.

The snow report gives the snow base at mid-mountain and in the alpine, and the snowfall of the last 24 and 48 hours
and 7 days, under a line saying when it was updated, in the resort's own time without a year; the year is the
latest one that does not put the report after the time of reading. The page does not say where the snowfall is
measured: it is carried with the mid-mountain base. Its "new snow" is counted from 3:45pm each day and is left out.
**The page reports whole centimetres; they are converted to inches here (divided by 2.54, to one decimal).** The
page gives no word for the surface. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SITE = "https://www.sunpeaksresort.com/ski-ride/weather-conditions-cams"
URLS = {"lifts": f"{SITE}/lifts-trail-status", "snow": f"{SITE}/weather-snow-report"}
NAME = "Sun Peaks"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# The page's status symbols, as a status and whether the trail is groomed, in the words of its own key.
STATUSES = {"icon-open": ("Open", "No"), "icon-close": ("Closed", "No"), "icon-tick groomed": ("Open", "Yes"),
            "icon-tick groomed-with-fresh": ("Open", "Yes")}
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on; parks and glades have none.
LEVELS = {"1-easiest": "Green", "2-more-difficult": "Blue", "3-most-difficult": "Black",
          "4-experts-only": "Double black", "5-park": "", "5-black-diamond-park": "", "6-glades": ""}
# The snow report's headings: the snowfall by the names the Ikon feed gives it, and the two places with a base.
SNOWFALL = {"24 Hr": "Last24HoursIn", "48 Hr": "Last48HoursIn", "7 Days": "Last7DaysIn"}
STAKES = {"Mid Mountain": "MidMountainArea", "Alpine": "SummitArea"}
LEFT_OUT = {"New Snow *"}
ROW = re.compile(r"<article [^>]*class=\"([^\"]*\bnode-type-(lift|trail)\b[^\"]*)\"[^>]*>(.*?)</article>", re.S)
TITLE = re.compile(r"<span class=\"field field--name-title[^\"]*\">(.*?)</span>", re.S)
STATUS_CELL = re.compile(r"<div class=\"row-cell status\">(.*?)</div>", re.S)
SYMBOL = re.compile(r"<span class=\"(icon-[^\"]*)\"")
LEVEL = re.compile(r"<span class=\"icon-trail_([a-z0-9-]+)\s")
ZONES = re.compile(r"<select id=\"zone\"[^>]*>(.*?)</select>", re.S)
ZONE = re.compile(r"<option value=\"\.(cat-[a-z0-9-]+)\">([^<]*)</option>")
COUNTED = r"<div class=\"weather-unit {kind}-total\">\s*/\s*(\d+)\s*</div>"
TAG = re.compile(r"<[^>]+>")
COMMENT = re.compile(r"<!--.*?-->", re.S)
SNOW_REPORT = re.compile(r"<div id=\"snow-conditions\"[^>]*>(.*?)<div id=\"newsletter-signup\"", re.S)
ITEM = re.compile(r"<li>(.*?)</li>", re.S)
HEADING = re.compile(r"<h4>\s*([^<]*?)\s*</h4>")
CENTIMETRES = re.compile(r"<span class=\"value_switch value_cm[^\"]*\">\s*(\d+(?:\.\d+)?)\s*</span>.*?"
                         r"<span class=\"unit_switch unit_cm\">cm</span>", re.S)
UPDATED = re.compile(r"Updated ([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th)? at (\d{1,2}):(\d{2})\s*([ap]m)")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(body: str, difficulty: str | None) -> dict:
    """One lift or trail: its status is the one symbol in its status cell."""
    title, cell = TITLE.search(body), STATUS_CELL.search(body)
    name = words(title.group(1)) if title else ""
    symbols = [" ".join(symbol.split()) for symbol in SYMBOL.findall(cell.group(1))] if cell else []
    if not name or len(symbols) != 1 or symbols[0] not in STATUSES:
        raise ValueError(f"{name or 'a row'} has status symbols {symbols}, not one the reader knows")
    status, groomed = STATUSES[symbols[0]]
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
    if difficulty is not None:
        row["Grooming"] = groomed
    return row


def zones(page: str) -> dict:
    """The page's zones, by the mark a trail's row carries for each."""
    select = ZONES.search(page)
    named = dict(ZONE.findall(select.group(1))) if select else {}
    if not named:
        raise ValueError("the page's zones were not found")
    return {mark: html.unescape(name).strip() for mark, name in named.items()}


def trail_row(marks: str, body: str, named: dict) -> tuple:
    """One trail and the zone it is in."""
    levels = LEVEL.findall(body)
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{words(body) or 'a trail'} has difficulty symbols {levels}, not one the reader knows")
    row = status_row(body, LEVELS[levels[0]])
    within = [named[mark] for mark in marks.split() if mark in named]
    if len(within) != 1:
        raise ValueError(f"{row['Name']} is in zones {within}, not one")
    return within[0], row


def counted(page: str, kind: str) -> int:
    """The page's own count of all its lifts or trails."""
    found = re.search(COUNTED.format(kind=kind), page)
    if not found:
        raise ValueError(f"the page's count of {kind} was not found")
    return int(found.group(1))


def updated(block: str, now: datetime) -> str:
    """When the snow report was updated, in UTC. The page gives no year: it is the latest that does not put the
    report more than a day after the time of reading."""
    found = UPDATED.search(block)
    if not found:
        raise ValueError("the snow report does not say when it was updated")
    month, day, hour, minute, half = found.groups()
    for year in (now.year, now.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
        except ValueError as error:
            raise ValueError(f"the snow report's date could not be read: {error}") from error
        at = at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc)
        if at <= now + timedelta(days=1):
            return at.strftime(STAMP)
    raise ValueError(f"the snow report's date {month} {day} could not be placed")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: a base at mid-mountain and in the alpine."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    shown = COMMENT.sub("", block.group(1))
    snowfall, bases = {}, {}
    for item in ITEM.findall(shown):
        heading = HEADING.search(item)
        if not heading or heading.group(1) in LEFT_OUT:
            continue
        heading = html.unescape(heading.group(1))
        if heading not in SNOWFALL and heading not in STAKES:
            raise ValueError(f"the snow report has a figure the reader does not know: {heading}")
        centimetres = CENTIMETRES.search(item)
        if not centimetres or heading in snowfall or heading in bases:
            raise ValueError(f"the snow report's {heading} is not centimetres given once")
        (snowfall if heading in SNOWFALL else bases)[heading] = round(float(centimetres.group(1)) / CM_PER_INCH, 1)
    if set(bases) != set(STAKES) or "24 Hr" not in snowfall:
        raise ValueError("the snow report has no mid-mountain or alpine base or no 24 hour snowfall")
    fallen = {SNOWFALL[heading]: inches for heading, inches in snowfall.items()}
    return {"LastUpdate": updated(shown, now), "Resortwide": False, "BaseConditions": None, "SeasonTotalIn": None,
            "MidMountainArea": {"Name": "Mid Mountain", "BaseIn": bases["Mid Mountain"], **fallen},
            "SummitArea": {"Name": "Alpine", "BaseIn": bases["Alpine"]}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    page = pages["lifts"]
    named = zones(page)
    lifts, areas = [], {name: {"Name": name, "Lifts": [], "Trails": []} for name in named.values()}
    for marks, kind, body in ROW.findall(page):
        if kind == "lift":
            lifts.append(status_row(body, None))
        else:
            zone, row = trail_row(marks, body, named)
            areas[zone]["Trails"].append(row)
    trails = sum(len(area["Trails"]) for area in areas.values())
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    if counted(page, "lifts") != len(lifts):
        raise ValueError(f"the page counts {counted(page, 'lifts')} lifts but {len(lifts)} were read")
    if trails < counted(page, "trails"):
        raise ValueError(f"the page counts {counted(page, 'trails')} trails but only {trails} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []},
                              *(area for area in areas.values() if area["Trails"])]}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
