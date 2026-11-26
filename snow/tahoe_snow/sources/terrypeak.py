"""Terry Peak's lifts and trails, and its snow report, from its trails and lifts page and its snow report page
(terrypeak.com/trails-lifts and terrypeak.com/snow-report).

Both pages are built on the server. The trails and lifts page is a list of the lifts and then the trails in three
columns, beginner, intermediate and advanced; each lift and trail is its status in words, in a badge, then its
name. A status is also in its badge's class, and the two have to agree. The lifts are one mountain area and each
column of trails another. A trail may carry marks after its name; one that says it is groomed is carried as
groomed, and where no trail on the page carries it the page says nothing of grooming. The page says when it was
updated, as a time, a weekday and a day with no year, in Mountain time: the year is this one or the last, and the
weekday has to agree. The snow report's own counts of lifts and of trails have to match what is read, so a change
in the page's shape fails instead of showing wrong numbers.

The snow report gives the new snow of the last 24, 48 and 72 hours and the base depth, in inches. It carries no
time of its own, and is given the time the trails and lifts page was updated, both being the day's one report. A
snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://terrypeak.com/trails-lifts", "snow": "https://terrypeak.com/snow-report"}
NAME = "Terry Peak"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Denver")
# The columns of trails, in the words the app's difficulty symbols are keyed on.
LEVELS = {"beginner": ("Beginner", "Green"), "intermediate": ("Intermediate", "Blue"),
          "advanced": ("Advanced", "Black")}
# The snow report's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"New Snow (24H)": "Last24HoursIn", "Last 48hr": "Last48HoursIn", "Last 72hr": "Last72HoursIn",
            "Base Depth": "BaseIn"}
# In the page: the heading of a column of trails, or one lift or trail.
PART = re.compile(r"<div class=\"dor-status-display__column-heading dor-status-display__column-heading--([a-z-]+)\">"
                  r"|<div class=\"dor-status-display__item\">\s*<span class=\"dor-status-display__badge "
                  r"dor-status-display__badge--([a-z-]+)\">(.*?)</span>\s*"
                  r"<span class=\"dor-status-display__name\">(.*?)</span>", re.S)
HEADING = re.compile(r"<h3 class=\"dor-status-display__heading\">(.*?)</h3>", re.S)
GROOMED = re.compile(r"title=\"Groom", re.I)
UPDATED = re.compile(r"<div class=\"dor-status-display__timestamp\">\s*Updated:\s*(\d{1,2}:\d{2} [AP]M) ([A-Z][a-z]+), "
                     r"([A-Z][a-z]+ \d{1,2})\s*</div>")
LINE = re.compile(r"<div class=\"label\">(.*?)</div>\s*<div class=\"value\">(.*?)</div>", re.S)
COUNTED = re.compile(r"(\d+)\s*/\s*(\d+)")
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


def rows_of(page: str) -> tuple:
    """The lifts, and the trails of each column, in the page's order."""
    sections = [(found.start(), words(found.group(1))) for found in HEADING.finditer(page)]
    if [title for _, title in sections] != ["Lift Status", "Trail Status"]:
        raise ValueError("the page is not a lift status and then a trail status")
    lifts, areas, column, groomed = [], {}, None, False
    marks = [mark for mark in PART.finditer(page) if mark.start() > sections[0][0]]
    for mark, following in zip(marks, marks[1:] + [None]):
        if mark.group(1):
            column = mark.group(1)
            if column not in LEVELS:
                raise ValueError(f"a column of trails has a difficulty the reader does not know: {column}")
            continue
        name = words(mark.group(4))
        if mark.start() < sections[1][0]:
            lifts.append(status_row(name, mark.group(2), words(mark.group(3)), None))
            continue
        if not column:
            raise ValueError(f"{name} is under no column of trails")
        trail = status_row(name, mark.group(2), words(mark.group(3)), LEVELS[column][1])
        # A trail's marks run to the next trail, or a little way after the last one.
        after = page[mark.end():following.start() if following else mark.end() + 600]
        trail["Grooming"] = "Yes" if GROOMED.search(after) else "No"
        groomed = groomed or trail["Grooming"] == "Yes"
        areas.setdefault(LEVELS[column][0], []).append(trail)
    if not groomed:
        # No trail carries the mark, so the page says nothing of grooming (the mark has not been seen).
        for trails in areas.values():
            for trail in trails:
                del trail["Grooming"]
    listed, read = page.count("class=\"dor-status-display__item\""), len(lifts) + sum(map(len, areas.values()))
    if read != listed:
        raise ValueError(f"the page lists {listed} lifts and trails but {read} were read")
    return lifts, [{"Name": name, "Lifts": [], "Trails": trails} for name, trails in areas.items()]


def updated(page: str, now: datetime) -> str:
    """When the page was updated ('10:04 AM Wednesday, Nov 25', Mountain time, no year) in UTC. The year is this
    one, or last year when that date has not come yet; the weekday must agree, so a stale page is refused instead
    of being given the wrong year."""
    found = UPDATED.search(page)
    if not found:
        raise ValueError("the page does not say when it was updated")
    clock, weekday, day = found.groups()
    for year in (now.year, now.year - 1):
        try:
            at = datetime.strptime(f"{year} {day} {clock}", "%Y %b %d %I:%M %p").replace(tzinfo=LOCAL_TIME)
        except ValueError as error:
            raise ValueError(f"the time the page was updated could not be read: {error}") from error
        if at <= now + timedelta(days=1) and at.strftime("%A") == weekday:
            return at.astimezone(timezone.utc).strftime(STAMP)
    raise ValueError(f"the page was updated on {weekday}, {day}, which is not a day of this year or last")


def lines(page: str) -> dict:
    """The snow report's lines, each label with what the page says under it."""
    return {words(label): words(said) for label, said in LINE.findall(page)}


def checked(rows: list, said: dict, label: str) -> None:
    """Refuse the page when the snow report's count of lifts or trails is not what was read."""
    found = COUNTED.fullmatch(said.get(label, ""))
    if not found:
        raise ValueError(f"the snow report's count under {label!r} was not found")
    if int(found.group(2)) != len(rows):
        raise ValueError(f"the snow report counts {found.group(2)} under {label!r} but {len(rows)} were read")


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(said: dict, lifts_page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    missing = [label for label in SNOWFALL if label not in said]
    if missing:
        raise ValueError(f"the snow report has no line for {missing}")
    area = {"Name": "Mountain", **{field: inches(said[label], label) for label, field in SNOWFALL.items()}}
    return {"LastUpdate": updated(lifts_page, now), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": None, "BaseArea": area, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    lifts, areas = rows_of(pages["lifts"])
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    said = lines(pages["snow"])
    checked(lifts, said, "Lifts Open")
    checked([trail for area in areas for trail in area["Trails"]], said, "Trails Open")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(said, pages["lifts"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
