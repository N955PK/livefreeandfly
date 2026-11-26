"""Lutsen Mountains' lifts and trails, and its snow report, from its mountain report page and its snow and weather
page (lutsen.com/mountain-info/mountain-report and lutsen.com/mountain-info/snow-weather).

Both pages are built on the server. The mountain report has a section for each of the resort's four mountains and
its Nordic centre, each listing its lifts, its primary runs and its sidecountry runs; each section is a mountain
area here. A status is an icon, read from the word the page gives with it and checked against the icon's own name:
Open, Closed and On Hold are carried as the page says them, and Projected, the page's word for a lift or run it
expects to open, is said as Expected. A run's difficulty is its icon (beginner, intermediate, advanced, expert,
terrain park), and one the reader does not know fails. A run with the page's groomed icon is groomed. Every lift and
run row in the page is one read, and the page's own counts of lifts, primary runs and sidecountry runs ("1/9",
"0/58", "0/29") have to match what is read, so a change in the page's shape fails instead of showing wrong numbers.

The snow and weather page gives the depth, the snowfall of the last 24 and 48 hours and 7 days and the season's
total in inches, and the day and time they were updated, in Central time and without a year: the year is taken
from the time of reading. It gives no word for the surface. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.lutsen.com/mountain-info/mountain-report",
        "snow": "https://www.lutsen.com/mountain-info/snow-weather"}
NAME = "Lutsen Mountains"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CENTRAL_TIME = ZoneInfo("America/Chicago")
# The status icons, in the words the app reads; the page's "Projected" is a lift or run expected to open.
STATUSES = {"open": "Open", "closed": "Closed", "projected": "Expected", "on-hold": "On hold"}
# The difficulty icons, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black",
          "terrain-park": ""}
# The page's counts, by the heading each kind of row is listed under.
COUNTED = {"Lifts": "Lifts", "Primary Runs": "Primary Trails", "Sidecountry Runs": "Sidecountry Trails"}
# The snowfall figures' headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn", "7 Days": "Last7DaysIn", "Base": "BaseIn",
            "Season Total": "SeasonTotalIn"}
SECTION = "<details>"
SECTION_NAME = re.compile(r"<summary[^>]*>(.*?)</summary>", re.S)
HEADING = re.compile(r"<h2 class=\"h4 ?\">(.*?)</h2>", re.S)
NODE = re.compile(r"<div [^>]*\bclass=\"node node--type-(lift|trail) node--view-mode-row\"[^>]*>(.*?)"
                  r"(?=<div [^>]*\bclass=\"node node--type-|<h2 class=\"h4 ?\">|</details>)", re.S)
TITLE = re.compile(r"<div class=\"cell title\">(.*?)</div>\s*<div class=\"cell icon-cell", re.S)
LEVEL = re.compile(r"<div class=\"cell f-icon level icon-([a-z-]+)\"[^>]*>.*?</div>", re.S)
HOURS = re.compile(r"<span class=\"t-micetype\">.*?</span>", re.S)
STATUS = re.compile(r"<div class=\"cell icon-cell status\">\s*<div class=\"f-icon icon-([a-z-]+)\"\s*"
                    r"title=\"([^\"]*)\">")
GROOMED = "icon-groomed"
STATS = re.compile(r"<div class=\"snow-weather page mountain-stats\">(.*?)<h2\b", re.S)
COUNT = re.compile(r"<h3 class=\"h4\">(.*?)</h3>\s*<div class=\"data h3\">\s*<span class=\"value[^\"]*\">\s*(\d+)\s*"
                   r"</span>\s*<span class=\"unit\">\s*/\s*(\d+)\s*</span>", re.S)
SNOW = re.compile(r"<p class=\"[^\"]*\bupdated\">\s*Updated:\s*([A-Z][a-z]{2})[a-z]* (\d{1,2})(?:st|nd|rd|th) - "
                  r"(\d{1,2}):(\d{2})\s*([ap]m)\s*</p>\s*<div class=\"[^\"]*\bcondition-block snow\b[^\"]*\">(.*?)"
                  r"(?=<h2\b|<footer\b|\Z)", re.S)
FIGURE = re.compile(r"<h3 class=\"h4\">(.*?)</h3>\s*<div class=\"data h3\">\s*<span class=\"imperial-value\">\s*"
                    r"<span class=\"value[^\"]*\">(.*?)</span>\s*<span class=\"unit\">(.*?)</span>", re.S)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def row_of(kind: str, body: str) -> dict:
    """One lift or run."""
    title, status = TITLE.search(body), STATUS.search(body)
    if not title or not status:
        raise ValueError(f"a {kind} row has no name or no status")
    level = LEVEL.search(title.group(1))
    name = words(HOURS.sub(" ", LEVEL.sub(" ", title.group(1))))
    if not name:
        raise ValueError(f"a {kind} row has no name")
    icon, said = status.groups()
    if icon not in STATUSES or icon != "-".join(said.lower().split()):
        raise ValueError(f"{name}'s status icon is {icon} and reads {said!r}, not one the reader knows")
    row = {"Name": name, "Status": STATUSES[icon], "StatusEnglish": STATUSES[icon].lower(), "Difficulty": None}
    if kind == "trail":
        if not level or level.group(1) not in LEVELS:
            raise ValueError(f"{name} has a difficulty the reader does not know: {level.group(1) if level else None}")
        row["Difficulty"] = LEVELS[level.group(1)]
        row["Grooming"] = "Yes" if GROOMED in body else "No"
    return row


def lift_areas(page: str) -> list:
    """Each mountain with its lifts and runs, in the page's order."""
    stats = STATS.search(page)
    if not stats:
        raise ValueError("the page's counts of lifts and trails were not found")
    counted = {words(label): int(total) for label, _, total in COUNT.findall(stats.group(1))}
    areas, read = [], dict.fromkeys(COUNTED, 0)
    for section in page.split(SECTION)[1:]:
        name = SECTION_NAME.search(section)
        if not name or not words(name.group(1)):
            raise ValueError("a section of the report has no name")
        area = {"Name": words(name.group(1)), "Lifts": [], "Trails": []}
        # The section is cut at each of its headings: what follows a heading is the rows listed under it.
        pieces = HEADING.split(section)
        for heading, body in zip(pieces[1::2], pieces[2::2]):
            heading = words(heading)
            if heading not in COUNTED:
                raise ValueError(f"{area['Name']} has a list the reader does not know: {heading}")
            for kind, row in NODE.findall(body + "</details>"):
                if (kind == "lift") != (heading == "Lifts"):
                    raise ValueError(f"{area['Name']} lists a {kind} under {heading}")
                area["Lifts" if kind == "lift" else "Trails"].append(row_of(kind, row))
                read[heading] += 1
        areas.append(area)
    listed = len(re.findall(r"class=\"node node--type-(?:lift|trail) node--view-mode-row\"", page))
    if not read["Lifts"] or sum(read.values()) != listed:
        raise ValueError(f"the page has {listed} lift and run rows but {sum(read.values())} were read")
    for heading, label in COUNTED.items():
        if counted.get(label) != read[heading]:
            raise ValueError(f"the page counts {counted.get(label)} {label.lower()} but {read[heading]} were read")
    return areas


def posted(said: tuple, now: datetime) -> str:
    """When the snowfall was updated. The page gives no year: it is the one that puts the day just behind now."""
    month, day, hour, minute, half = said
    here = now.astimezone(CENTRAL_TIME)
    for year in (here.year, here.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
        except ValueError as error:
            raise ValueError(f"the snowfall's date could not be read: {error}") from error
        at = at.replace(tzinfo=CENTRAL_TIME)
        if at - here <= timedelta(days=1):
            break
    return at.astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str, now: datetime) -> dict:
    """The page's snowfall in the shape of the Ikon feed's SnowReport: one set for the whole resort."""
    block = SNOW.search(page)
    if not block:
        raise ValueError("the snowfall and the time it was updated were not found")
    figures = {}
    for label, said, unit in FIGURE.findall(block.group(6)):
        label = words(label)
        if label not in SNOWFALL or SNOWFALL[label] in figures:
            raise ValueError(f"the snowfall has a figure the reader does not know, or has it twice: {label}")
        if not NUMBER.fullmatch(said.strip()) or words(unit) != "in":
            raise ValueError(f"the snowfall's {label} reads {words(said)!r} {words(unit)!r}, not a number of inches")
        value = float(said)
        figures[SNOWFALL[label]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snowfall has no base depth or no 24 hour figure")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": posted(block.groups()[:5], now), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
