"""Marmot Basin's lifts and trails, and its snow report, from its lifts, trails and grooming page and its weather
and conditions page (skimarmot.com/mountain/trail-map-lift-status and /mountain/weather-conditions).

Both pages are built on the server. The status page is a group for the lifts and a group for the trails of each
part of the mountain (Lower Mountain, Upper Mountain, Eagle Ridge Area, Knob Area), which are the mountain areas
here; the lifts name no part and are an area of their own. A lift or a trail is open or closed in the word beside
its status symbol, and a word the reader does not know fails; a trail that has been groomed says so in a second
word. A trail's difficulty is the symbol before its name, read from the symbol's name (a terrain park's is orange
and is carried with no difficulty), and one the reader does not know fails. A lift's hours are left out. Each
group's rows are counted against its headings, so a change in the page's shape fails instead of showing wrong
numbers; the page gives no count of its own.

The snow report is one set of figures for the mountain: the snow base, the snowfall of the last 24 hours and 7
days and the season's total, under a line saying when it was updated, in the resort's own time. A snowfall the
page calls a trace is carried as none. **The page reports whole centimetres; they are converted to inches here
(divided by 2.54, to one decimal).** The page gives no word for the surface. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SITE = "https://www.skimarmot.com/mountain"
URLS = {"lifts": f"{SITE}/trail-map-lift-status/", "snow": f"{SITE}/weather-conditions/"}
NAME = "Marmot Basin"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Edmonton")
CM_PER_INCH = 2.54
STATUSES = {"open": "Open", "closed": "Closed"}
# The difficulty symbols' names, in the words the app's difficulty symbols are keyed on; a terrain park has none.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "doubleblack": "Double black", "orange": ""}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Last 24 Hours": "Last24HoursIn", "Last 7 Days": "Last7DaysIn", "Snow Base": "BaseIn",
            "Season Total": "SeasonTotalIn"}
# The months as the page writes them, by their first three letters.
MONTHS = {name: number for number, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
GROUP = re.compile(r"<div class=\"lf-status-group\">\s*<h2>(.*?)</h2>", re.S)
ROW = re.compile(r"<h3 class=\"lf-status-heading\">(.*?)</h3>(.*?)(?=<h3 class=\"lf-status-heading\">|$)", re.S)
ROW_MARK = "<h3 class=\"lf-status-heading\">"
LEVEL = re.compile(r"<div class=\"lf-status-level\">.*?xlink:href=\"#icon-([a-z]+)\".*?</div>", re.S)
SAID = re.compile(r"<div class=\"lf-status-status\">\s*<div class=\"lf-status-icon[^\"]*\">.*?</div>([^<]*)</div>",
                  re.S)
TRAILS = re.compile(r"(.+) Trail Status")
TAG = re.compile(r"<[^>]+>")
SNOW_REPORT = re.compile(r"<h3 class=\"weather-heading[^\"]*\">\s*Snow Report\s*</h3>\s*<p[^>]*>(.*?)</p>(.*?)"
                         r"(?=<div class=\"weather-group\">|$)", re.S)
ITEM = re.compile(r"<div class=\"weather-key\">(.*?)</div>\s*<div class=\"weather-value\">(.*?)</div>", re.S)
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*cm")
UPDATED = re.compile(r"Updated ([A-Z][a-z]+)\.? (\d{1,2}), (\d{4}), (?:(\d{1,2})(?::(\d{2}))? ([ap])\.m\.|(noon|midnight))")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(title: str, body: str, trail: bool) -> dict:
    """One lift or trail: the word beside its status symbol, and for a trail its difficulty and its grooming."""
    levels = LEVEL.findall(title)
    name, said = words(LEVEL.sub("", title)), [words(word) for word in SAID.findall(body)]
    if not name or not said or said[0].lower() not in STATUSES:
        raise ValueError(f"{name or 'a row'} has a status the reader does not know: {said}")
    status = STATUSES[said[0].lower()]
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}
    if not trail:
        if levels or len(said) != 1:
            raise ValueError(f"{name} is a lift with a difficulty or a second status: {levels} {said}")
        return row
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name} has difficulty symbols {levels}, not one the reader knows")
    if said[1:] not in ([], ["Groomed"]) or (said[1:] and status != "Open"):
        raise ValueError(f"{name} has a status the reader does not know: {said}")
    row["Difficulty"], row["Grooming"] = LEVELS[levels[0]], "Yes" if said[1:] else "No"
    return row


def mountain_areas(page: str) -> list:
    heads = list(GROUP.finditer(page))
    areas = []
    for head, after in zip(heads, [*heads[1:], None]):
        title, piece = words(head.group(1)), page[head.end():after.start() if after else len(page)]
        trails = TRAILS.fullmatch(title)
        if title != "Lift Status" and not trails:
            raise ValueError(f"the page has a group the reader does not know: {title}")
        rows = [status_row(name, body, bool(trails)) for name, body in ROW.findall(piece)]
        if not rows or len(rows) != piece.count(ROW_MARK):
            raise ValueError(f"{title} lists {piece.count(ROW_MARK)} rows but {len(rows)} were read")
        if trails:
            areas.append({"Name": trails.group(1), "Lifts": [], "Trails": rows})
        else:
            areas.append({"Name": NAME, "Lifts": rows, "Trails": []})
    if [bool(area["Lifts"]) for area in areas].count(True) != 1 or len(areas) < 2:
        raise ValueError("the page does not list its lifts once and its trails")
    return areas


def updated(said: str) -> str:
    """When the snow report was updated, in UTC, from the resort's own time ("Nov. 24, 2026, 12:55 p.m.")."""
    found = UPDATED.search(said)
    if not found or found.group(1)[:3].lower() not in MONTHS:
        raise ValueError(f"the snow report does not say when it was updated: {said!r}")
    month, day, year, hour, minute, half, named = found.groups()
    if named:
        hour = 12 if named == "noon" else 0
    else:
        hour = int(hour) % 12 + (12 if half == "p" else 0)
    try:
        at = datetime(int(year), MONTHS[month[:3].lower()], int(day), hour, int(minute or 0), tzinfo=RESORT_TIME)
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return at.astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    found = SNOW_REPORT.search(page)
    if not found:
        raise ValueError("the snow report was not found")
    figures = {}
    for heading, said in ITEM.findall(found.group(2)):
        heading, said = words(heading), words(said)
        if heading not in SNOWFALL:
            continue
        centimetres = CENTIMETRES.fullmatch(said)
        if (not centimetres and said.lower() != "trace") or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report's {heading} reads {said!r}, not centimetres given once")
        figures[SNOWFALL[heading]] = round(float(centimetres.group(1)) / CM_PER_INCH, 1) if centimetres else 0.0
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no snow base or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": updated(words(found.group(1))), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": {"Name": NAME, **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": mountain_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
