"""Mt Seymour's lifts and runs, and its snow report, from its conditions page
(mtseymour.ca/the-mountain/todays-conditions-hours).

The page is built on the server. Its table of lifts has a row for each lift, and under each the runs it serves;
each lift is a mountain area here, holding itself and its runs. A lift's status is either a word (Closed, Stand
By), carried as the page says it, or the hours it runs today ("8:30 AM - 9:30 PM"): within those hours, in
Pacific time, the lift reads as open, before them as scheduled and after them as closed, and the hours are carried
beside the status. A run has a symbol for its difficulty and one each for its status by day and by night, read
from the symbols' names, and one the reader does not know fails; the status is the day's, and the night's is
carried beside it. The page's own counts of runs open by day and by night are checked against what is read, so a
change in its shape fails instead of showing wrong numbers. The terrain parks, the snow play areas and the
snowshoe trails have tables of their own and are left out.

The snow report gives the depth at the summit and at the base, the snowfall over 24 and 48 hours and 7 days and
the season's total, and where the page has one a word for the surface, under a line saying when it was last
updated in Pacific time, with a weekday but no year; the year is this one or the last, whichever has that date on that
weekday and not after the time of reading. Mt Seymour reports in centimetres: every figure here is the page's
centimetres divided by 2.54 and rounded to one decimal, to give the inches the Ikon feed's fields hold. The
snowfall is the mountain's, and is carried with the base's depth. A snow report that cannot be read costs only the
snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://mtseymour.ca/the-mountain/todays-conditions-hours"
NAME = "Mt Seymour"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# The page's status symbols.
STATUSES = {"status-open": "Open", "status-closed": "Closed"}
# The page's difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"level-beginner": "Green", "level-intermediate": "Blue", "level-advanced": "Black",
          "level-expert": "Double black"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24hr Snowfall": "Last24HoursIn", "48hr Snowfall": "Last48HoursIn", "7 Day Snowfall": "Last7DaysIn",
            "At The Summit": "Summit", "At The Base": "Base", "This Season": "SeasonTotalIn"}
LIFT_TABLE = re.compile(r"<table[^>]*>\s*<caption[^>]*>\s*Lifts\s*</caption>(.*?)</table>", re.S)
# A lift's row, and the row of runs under it.
LIFT = re.compile(r"<tr class=\"accordion-heading\">\s*<th>\s*([^<]*?)\s*(?:<button.*?</button>\s*)?</th>\s*"
                  r"<td[^>]*>(.*?)</td>\s*</tr>(.*?)(?=<tr class=\"accordion-heading\">|\Z)", re.S)
RUN = re.compile(r"<article[^>]*>(.*?)</article>", re.S)
SYMBOL = re.compile(r"class=\"f-icon icon (level|status) ([a-z-]+)\"")
HIDDEN = re.compile(r"<span class=\"visually-hidden\">.*?</span>", re.S)
TAG = re.compile(r"<[^>]+>")
HOURS = re.compile(r"(\d{1,2}:\d{2} [AP]M) - (\d{1,2}:\d{2} [AP]M)")
# One of the page's figures in a circle: the figure, its unit where it has one, and its label.
FIGURE = re.compile(r"<div class=\"f-size-30 f-w-xbold value\">\s*([^<]*?)\s*</div>\s*"
                    r"(?:<div class=\"[^\"]*\bunit\">\s*([^<]*?)\s*</div>\s*)?</div>\s*</div>\s*"
                    r"<div class=\"[^\"]*\blabel\">\s*([^<]*?)\s*</div>")
SNOW_DATA = re.compile(r"<ul class=\"[^\"]*\bsnow-data\">(.*?)</ul>", re.S)
UPDATED = re.compile(r"Last Updated:\s*([A-Z][a-z]{2}) ([A-Z][a-z]{2})\s+(\d{1,2}) @ (\d{1,2}):(\d{2})([ap]m)")
SURFACE = re.compile(r"<th>\s*Conditions\s*</th>\s*<td>\s*([^<]*?)\s*</td>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_row(name: str, cell: str, now: datetime) -> dict:
    """One lift: a word for its status, or today's hours, read against the time in Pacific time."""
    said = words(cell)
    hours = HOURS.fullmatch(said)
    if not name or not said or not (hours or said.replace(" ", "").isalpha()):
        raise ValueError(f"{name or 'a lift'} has the status {said!r}, not a word or its hours")
    row = {"Name": name, "Status": said.capitalize(), "StatusEnglish": said.lower(), "Difficulty": None}
    if hours:
        here = now.astimezone(PACIFIC_TIME)
        first, last = (datetime.strptime(hour, "%I:%M %p").time() for hour in hours.groups())
        if last <= first:
            raise ValueError(f"{name} has the hours {said!r}, which end before they start")
        status = "Scheduled" if here.time() < first else "Open" if here.time() < last else "Closed"
        row.update({"Status": status, "StatusEnglish": status.lower(), "Hours": said})
    return row


def run_row(markup: str) -> dict:
    """One run: its difficulty, and its status by day and by night."""
    name = words(HIDDEN.sub(" ", markup))
    levels = [symbol for kind, symbol in SYMBOL.findall(markup) if kind == "level"]
    statuses = [symbol for kind, symbol in SYMBOL.findall(markup) if kind == "status"]
    if not name or len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name or 'a run'} has difficulty symbols {levels}, not one the reader knows")
    if len(statuses) != 2 or any(status not in STATUSES for status in statuses):
        raise ValueError(f"{name} has status symbols {statuses}, not one for the day and one for the night")
    day, night = (STATUSES[status] for status in statuses)
    return {"Name": name, "Status": day, "StatusEnglish": day.lower(), "Difficulty": LEVELS[levels[0]],
            "NightStatus": night}


def lift_areas(page: str, now: datetime) -> list:
    """Each lift with the runs under it, in the page's order."""
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the table of lifts was not found")
    areas = []
    for name, cell, under in LIFT.findall(table.group(1)):
        name = html.unescape(name)
        areas.append({"Name": name, "Lifts": [lift_row(name, cell, now)],
                      "Trails": [run_row(run) for run in RUN.findall(under)]})
    if not areas or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no runs")
    if len(RUN.findall(table.group(1))) != sum(len(area["Trails"]) for area in areas):
        raise ValueError("the table of lifts has runs that are under no lift")
    return areas


def figures_of(markup: str) -> dict:
    """The page's circled figures by their labels: each the figure and its unit as written."""
    return {html.unescape(label): (said, unit) for said, unit, label in FIGURE.findall(markup)}


def counted(page: str, label: str) -> int:
    """The page's own count of the runs open by day or by night."""
    said = figures_of(page).get(label, ("", ""))[0]
    if not said.isdigit():
        raise ValueError(f"the page's count of {label.lower()} was not found")
    return int(said)


def updated(page: str, now: datetime) -> str:
    """When the page was last updated, in UTC. The page gives a weekday and no year: it is this year or the last,
    whichever has the date on that weekday not more than a day after the time of reading."""
    found = UPDATED.search(words(page))
    if not found:
        raise ValueError("the page does not say when it was last updated")
    weekday, month, day, hour, minute, half = found.groups()
    for year in (now.year, now.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %b %d %I:%M %p")
        except ValueError:
            continue
        if at.strftime("%a") == weekday and at.replace(tzinfo=PACIFIC_TIME) <= now + timedelta(days=1):
            return at.replace(tzinfo=PACIFIC_TIME).astimezone(timezone.utc).strftime(STAMP)
    raise ValueError(f"the page's date {weekday} {month} {day} could not be placed")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the depth at the base and at the summit,
    with the mountain's snowfall beside the base's."""
    block = SNOW_DATA.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    figures = {}
    for label, (said, unit) in figures_of(block.group(1)).items():
        if label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        if unit != "cm" or not re.fullmatch(r"\d+(?:\.\d+)?", said):
            raise ValueError(f"the snow report's {label} reads {said!r} {unit!r}, not centimetres")
        figures[SNOWFALL[label]] = round(float(said) / CM_PER_INCH, 1)
    if "Base" not in figures or "Summit" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no depth at the base or the summit, or no 24 hour snowfall")
    summit, base, season = figures.pop("Summit"), figures.pop("Base"), figures.pop("SeasonTotalIn", None)
    surface = SURFACE.search(page)
    return {"LastUpdate": updated(page, now), "Resortwide": False,
            "BaseConditions": html.unescape(surface.group(1)) or None if surface else None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Base", "BaseIn": base, **figures}, "SummitArea": {"Name": "Summit", "BaseIn": summit},
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    areas = lift_areas(page, now)
    runs = [run for area in areas for run in area["Trails"]]
    for label, field in (("Day Runs Open", "Status"), ("Night Runs Open", "NightStatus")):
        read = sum(run[field] == "Open" for run in runs)
        if counted(page, label) != read:
            raise ValueError(f"the page counts {counted(page, label)} {label.lower()} but {read} were read")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
