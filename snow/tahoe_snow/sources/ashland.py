"""Mt. Ashland's lifts and trails, and its snow report, from its mountain report page (mtashland.com/mountain-report).

The page is built on the server and typed by hand: a table of lifts, and a table of trails for each group of lifts
(the Sonnet and Lithia, Comer and Windsor, and Ariel "terrain pods"), each under its name. A lift's status is the
word in its row: "Closed", or "Open" followed by its hours ("Open 9am - 9pm"), given here as open; any other words
(a hold, say) are carried as the page has them. The table's last row is uphill access, which is not a lift and is
left out. A trail's status is "Open", "Closed" or "Groomed", which is open and groomed; its difficulty is the
picture in its row, read from the picture's name, and one the reader does not know fails.

The snow report gives the 24 hour and 7 day snowfall, the season's total, and the depth at the lower mountain,
mid-mountain and summit in inches, under a line saying when it was updated, in Pacific time. The surface is the
page's own words, left empty while they only say the ski area is closed. Before the season the page keeps last
season's total beside depths of zero. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.mtashland.com/mountain-report/"
NAME = "Mt. Ashland"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
# The difficulty pictures, by a part of their file names, in the words the app's difficulty symbols are keyed on.
# The double diamond is looked for before the single one its name also holds.
LEVELS = (("double_black_diamond", "Double black"), ("black_diamond", "Black"), ("blue_square", "Blue"),
          ("green_circle", "Green"))
# The snow report's labels: the part of the report each belongs to and the name the Ikon feed gives the figure.
FIGURES = {"24-Hour Snowfall": ("BaseArea", "Last24Hours"), "7-Day Snowfall": ("BaseArea", "Last7Days"),
           "Season Snowfall": (None, "SeasonTotal"), "Lower Mountain": ("BaseArea", "Base"),
           "Mid-Mountain": ("MidMountainArea", "Base"), "Summit": ("SummitArea", "Base")}
LIFT_TABLE = re.compile(r"<h1[^>]*>\s*Chairlift Status\s*</h1>(?:(?!<h1).)*?<table[^>]*>(.*?)</table>", re.S)
TRAILS_HEADING = re.compile(r"<h1[^>]*>\s*Ski Trail Status Report\s*</h1>")
NEXT_HEADING = re.compile(r"<h1[\s>]")
POD = re.compile(r"<p[^>]*>\s*<strong>([^<]+)</strong>\s*</p>\s*<table[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PICTURE = re.compile(r"\s(?:data-src|src)=\"(?!data:)[^\"]*/([^\"/]+)\"")
TAG = re.compile(r"<[^>]+>")
NOTE = re.compile(r"\s*\([^)]*\)\s*$")
SAID = re.compile(r"(open|closed)\b.*", re.I)
SNOW_REPORT = re.compile(r"<h1[^>]*>\s*Snow Report\s*</h1>(.*?)<h1[^>]*>\s*Chairlift Status\s*</h1>", re.S)
FIGURE = re.compile(r"vcex-heading-inner[^\"]*\">([^<]*)</span>\s*</div>\s*<div class=\"wpb_text_column[^>]*>\s*"
                    r"<div class=\"wpb_wrapper\">\s*<p[^>]*>(.*?)</p>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–]\s*(\d+(?:\.\d+)?))?\s*[\"”″]?")
UPDATED = re.compile(r"Updated ([A-Z][a-z]+) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2}) ([AP]M)")
SURFACE = re.compile(r"<h1[^>]*>\s*Ski Surface\s*</h1>.*?<div class=\"wpb_wrapper\">(.*?)</div>", re.S)
SHUT = re.compile(r"(ski area )?closed\b.*", re.I)


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def rows_of(table: str) -> list:
    """The cells of each row of a table."""
    return [CELL.findall(row) for row in ROW.findall(table)]


def lift_rows(page: str) -> list:
    table = LIFT_TABLE.search(page)
    if not table:
        raise ValueError("the table of lifts was not found")
    rows = rows_of(table.group(1))
    if not rows or [words(cell) for cell in rows[0]] != ["Chair Lift", "Status"]:
        raise ValueError("the table of lifts does not start with its Chair Lift and Status headings")
    lifts = []
    for cells in rows[1:]:
        if len(cells) != 2:
            raise ValueError("a row of the lift table is not a name and a status")
        name, said = NOTE.sub("", words(cells[0])), words(cells[1])
        if not name or not said:
            raise ValueError(f"{name or 'a lift'} has no name or no status")
        # The last row is uphill access: skiers climbing under their own power, not a lift.
        if name.lower().startswith("uphill"):
            continue
        known = SAID.fullmatch(said)
        status = known.group(1).capitalize() if known else said[0].upper() + said[1:]
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    if not lifts:
        raise ValueError("the table of lifts names no lifts")
    return lifts


def difficulty(cell: str, name: str) -> str:
    pictures = {picture.lower() for picture in PICTURE.findall(cell)}
    if len(pictures) == 1:
        for part, level in LEVELS:
            if part in next(iter(pictures)):
                return level
    raise ValueError(f"{name} has difficulty pictures {sorted(pictures)}, not one the reader knows")


def trail_row(cells: list) -> dict:
    if len(cells) != 3:
        raise ValueError("a row of a trail table is not a name, a difficulty and a status")
    name, said = words(cells[0]), words(cells[2])
    if not name or not said:
        raise ValueError(f"{name or 'a trail'} has no name or no status")
    groomed = said.lower() == "groomed"
    status = "Open" if groomed else said[0].upper() + said[1:].lower()
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty(cells[1], name),
            "Grooming": "Yes" if groomed else "No"}


def trail_areas(page: str) -> list:
    """The trails of each group of lifts, in the page's order."""
    heading = TRAILS_HEADING.search(page)
    if not heading:
        raise ValueError("the trail report was not found")
    after = NEXT_HEADING.search(page, heading.end())
    part = page[heading.end():after.start() if after else len(page)]
    areas = []
    for name, table in POD.findall(part):
        rows = rows_of(table)
        if (len(rows) < 3 or words(" ".join(rows[0])) != "Trail Designation"
                or [words(cell) for cell in rows[2]] != ["Run", "Difficulty", "Status"]):
            raise ValueError(f"the trail table under {words(name)} does not start with its key and headings")
        areas.append({"Name": words(name), "Lifts": [], "Trails": [trail_row(cells) for cells in rows[3:]]})
    if len(areas) != part.count("<table") or not any(area["Trails"] for area in areas):
        raise ValueError("the trail report has no trails, or a table of trails with no name over it")
    return areas


def inches(said: str, label: str) -> dict:
    """A figure of the snow report, as the Ikon feed names it: the one number, or the two ends of a range."""
    found = INCHES.fullmatch(html.unescape(said).strip())
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    low, high = (None if end is None else int(float(end)) if float(end).is_integer() else float(end)
                 for end in found.groups())
    return {"In": low} if high is None else {"In": None, "MinIn": low, "MaxIn": high}


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the lower mountain as its base area."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    out = {"BaseArea": {"Name": "Lower Mountain"}, "MidMountainArea": {"Name": "Mid-Mountain"},
           "SummitArea": {"Name": "Summit"}}
    season, seen = None, set()
    for said, label in FIGURE.findall(block.group(1)):
        label = words(label)
        if label not in FIGURES or label in seen:
            raise ValueError(f"the snow report has a figure the reader does not know, or has it twice: {label}")
        seen.add(label)
        area, field = FIGURES[label]
        figure = inches(said, label)
        if area is None:
            season = figure["In"]
        else:
            out[area].update({field + end: value for end, value in figure.items()})
    if seen != set(FIGURES):
        raise ValueError(f"the snow report is missing {sorted(set(FIGURES) - seen)}")
    updated = UPDATED.search(words(block.group(1)))
    posted = None
    if updated:
        month, day, year, hour, minute, half = updated.groups()
        try:
            at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
        except ValueError as error:
            raise ValueError(f"the snow report's date could not be read: {error}") from error
        posted = at.replace(tzinfo=PACIFIC_TIME).astimezone(timezone.utc).strftime(STAMP)
    surface = SURFACE.search(block.group(1))
    surface = words(surface.group(1)) if surface else ""
    return {"LastUpdate": posted, "Resortwide": True,
            "BaseConditions": surface if surface and not SHUT.fullmatch(surface) else None, "SeasonTotalIn": season,
            **out, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lift_rows(page), "Trails": []}, *trail_areas(page)]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
