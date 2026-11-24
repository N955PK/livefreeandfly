"""Le Massif de Charlevoix's lifts and trails, and its snowfall, from its lifts and trails page and its snow and
weather page (lemassif.com/en/the-mountain/winter/lifts-trails-grooming and .../snow-weather-webcams, the English
pages).

Both pages are built on the server. The first lists the lifts, then the trails under a heading for each part of
the mountain (the beginner area, Camp-Boule, Grande-Pointe, Maillard, the snowpark, the off-piste area and alpine
touring), each a mountain area here. A lift's or trail's status is the title of its status symbol. The English page
writes Open, Closed, Scheduled and Progressive, but a row that has not been translated keeps its French word, so
those are read too: ouvert is Open, fermé is Closed, programmé is Scheduled and progressif is Progressive. Any
other title fails. A trail's difficulty is the number of its level symbol, which the site's stylesheet draws as the
green circle (16), the blue square (17), the black diamond (18) and the double black (19); a Groomed mark in its
conditions is carried as its grooming. The page's own count of lifts has to match what is read, and its count of
trails, which leaves some of the listed ones out, must not be more than what is read, so a change in the page's
shape fails instead of showing wrong numbers.

The site gives no depth of snow and no word for the surface. The snow page gives the snowfall of the last 24 hours,
48 hours and 7 days and the season's total, each in centimetres and in inches: the centimetres are read and turned
into inches here (divided by 2.54, to one decimal). Its "since 6am" figure has no place in the feed and is left
out. The report's time is the latest of the snowfall's "Updated" lines, which give no year, in Eastern time; the
year is the latest one that does not put the report after the time of reading. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.lemassif.com/en/the-mountain/winter/lifts-trails-grooming",
        "snow": "https://www.lemassif.com/en/the-mountain/winter/snow-weather-webcams"}
NAME = "Le Massif de Charlevoix"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The titles of the status symbols, English and (on a row left untranslated) French.
STATUSES = {"open": "Open", "ouvert": "Open", "ouverte": "Open", "closed": "Closed", "fermé": "Closed",
            "fermée": "Closed", "scheduled": "Scheduled", "programmé": "Scheduled", "programmée": "Scheduled",
            "progressive": "Progressive", "progressif": "Progressive"}
# The level symbols' numbers, in the words the app's difficulty symbols are keyed on.
LEVELS = {"16": "Green", "17": "Blue", "18": "Black", "19": "Double black"}
GROOMED = "tid-22"
# The snowfall's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn", "7 Days": "Last7DaysIn",
            "Season Total": "SeasonTotalIn"}
LIFTS_START, TRAILS_START = "<h2>Lift Status</h2>", "<h2>Trail Status</h2>"
# In the trails part of the page: a heading over a part of the mountain, or a trail.
HEADING_OR_TRAIL = re.compile(r"<summary[^>]*>(.*?)</summary>|<article[^>]*\bnode--type-trail\b[^>]*>(.*?)</article>",
                              re.S)
LIFT = re.compile(r"<article[^>]*\bnode--type-lift\b[^>]*>(.*?)</article>", re.S)
ROW_NAME = re.compile(r"<div class=\"m-t-0\">(.*?)</div>", re.S)
ROW_STATUS = re.compile(r"<div class=\"cell [^\"]*\bstatus\b[^\"]*\">\s*<div class=\"icon\" title=\"([^\"]*)\"")
ROW_LEVEL = re.compile(r"\blevel level-(\d+)\"")
ROW_CONDITION = re.compile(r"<div class=\"cell [^\"]*\bcondition\b[^\"]*\">(.*?)</div>", re.S)
TAG = re.compile(r"<[^>]+>")
COUNTED = (r"<div class=\"h3[^\"]*\">\s*Open {kind}\s*</div>\s*<div class=\"value\">\s*\d+\s*"
           r"<span class=\"unit\">\s*/\s*(\d+)")
SNOW = re.compile(r"<h2[^>]*>\s*Snowfall\s*</h2>(.*?)<h2", re.S)
FIGURE = re.compile(r"<div class=\"t-large f-w-bold\">\s*([^<]*?)\s*</div>\s*<div class=\"[^\"]*\bvalue\b[^\"]*\">\s*"
                    r"<span class=\"metric-value\">\s*([^<]*?)\s*<span class=\"unit\">\s*([^<]*?)\s*</span>")
UPDATED = re.compile(r"Updated:\s*([A-Z][a-z]{2}) (\d{1,2}) - (\d{1,2}):(\d{2})\s*([ap]m)")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float:
    return round(centimetres / 2.54, 1)


def status_row(markup: str) -> dict:
    """One lift or trail: its name, and its status from the title of its status symbol."""
    named = ROW_NAME.search(markup)
    name = words(named.group(1)) if named else ""
    if not name:
        raise ValueError("a lift or trail has no name")
    titles = [html.unescape(title).strip().lower() for title in ROW_STATUS.findall(markup)]
    if len(titles) != 1 or titles[0] not in STATUSES:
        raise ValueError(f"{name} has status titles {titles}, not one the reader knows")
    status = STATUSES[titles[0]]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(markup: str) -> dict:
    row = status_row(markup)
    levels = ROW_LEVEL.findall(markup)
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{row['Name']} has level symbols {levels}, not one the reader knows")
    row["Difficulty"] = LEVELS[levels[0]]
    row["Grooming"] = "Yes" if any(GROOMED in cell for cell in ROW_CONDITION.findall(markup)) else "No"
    return row


def trail_areas(page: str) -> list:
    """The trails of each part of the mountain, in the page's order."""
    start = page.find(TRAILS_START)
    if start < 0:
        raise ValueError("the trails part of the page was not found")
    areas = []
    for found in HEADING_OR_TRAIL.finditer(page, start):
        if found.group(2) is None:
            areas.append({"Name": words(found.group(1)), "Lifts": [], "Trails": []})
        elif not areas or not areas[-1]["Name"]:
            raise ValueError("a trail has no heading over it")
        else:
            areas[-1]["Trails"].append(trail_row(found.group(2)))
    return [area for area in areas if area["Trails"]]


def counted(page: str, kind: str) -> int:
    """The page's own count of all its lifts or trails."""
    found = re.search(COUNTED.format(kind=kind), page)
    if not found:
        raise ValueError(f"the page's count of {kind.lower()} was not found")
    return int(found.group(1))


def updated(block: str, now: datetime) -> str:
    """The latest of the snowfall's "Updated" lines, in UTC. They give no year: it is the latest that does not put
    the line more than a day after the time of reading."""
    times = []
    for month, day, hour, minute, half in UPDATED.findall(block):
        for year in (now.year, now.year - 1):
            try:
                at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
            except ValueError as error:
                raise ValueError(f"the snowfall's date could not be read: {error}") from error
            at = at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc)
            if at <= now + timedelta(days=1):
                times.append(at)
                break
        else:
            raise ValueError(f"the snowfall's date {month} {day} could not be placed")
    if not times:
        raise ValueError("the snowfall does not say when it was updated")
    return max(times).strftime(STAMP)


def snow_report(page: str, now: datetime) -> dict:
    """The page's snowfall in the shape of the Ikon feed's SnowReport, centimetres turned into inches. There is no
    depth of snow to give."""
    block = SNOW.search(page)
    if not block:
        raise ValueError("the snowfall was not found")
    figures = {}
    for heading, said, unit in FIGURE.findall(block.group(1)):
        if heading not in SNOWFALL:
            continue
        if unit != "cm" or not re.fullmatch(r"\d+(?:\.\d+)?", said) or SNOWFALL[heading] in figures:
            raise ValueError(f"the snowfall's {heading} reads {said!r} {unit!r}, not centimetres given once")
        figures[SNOWFALL[heading]] = inches(float(said))
    if "Last24HoursIn" not in figures:
        raise ValueError("the snowfall has no 24 hour figure")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": updated(block.group(1), now), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    page = pages["lifts"]
    start, end = page.find(LIFTS_START), page.find(TRAILS_START)
    if start < 0 or end < start:
        raise ValueError("the lifts part of the page was not found")
    lifts = [status_row(markup) for markup in LIFT.findall(page[start:end])]
    areas = trail_areas(page)
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    if counted(page, "Lifts") != len(lifts):
        raise ValueError(f"the page counts {counted(page, 'Lifts')} lifts but {len(lifts)} were read")
    trails = sum(len(area["Trails"]) for area in areas)
    if trails < counted(page, "Trails"):
        raise ValueError(f"the page counts {counted(page, 'Trails')} trails but only {trails} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
