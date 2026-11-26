"""Discovery's lifts and trails, and its snow report, from its trail report and snow report pages
(skidiscovery.com/trail-report and skidiscovery.com/snow-report).

Both pages are built on the server. The trail report is a heading for each lift, "JUBLIEE TRIPLE CHAIR - CLOSED",
over a table of the trails it serves; a heading can name two lifts that share a table, and a lift with no trails
of its own has a heading and no table. Each heading is a mountain area here, holding its lifts and its trails. A
lift's status is the word after the dash, carried as the page says it. A trail's row is a picture of its
difficulty (read from the picture's name), its name, its status in words, its condition and a comment; a
condition of "Groomed" is carried as its grooming, and a difficulty the reader does not know fails. The headings
are in capitals, and a lift's name is given a capital for each word instead. Every heading and every trail row in
the report is one read, and the snow report's own count of lifts has to match, so a change in the page's shape
fails instead of showing wrong numbers.

The snow report gives the snow since the lifts closed and of the last 24, 48 and 72 hours, the season's total,
the depth at the bottom and at the top, in inches, and the surface in words, with the day and time it was
updated, in Mountain time. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
import html
import re
import string
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://www.skidiscovery.com/trail-report/", "snow": "https://www.skidiscovery.com/snow-report/"}
NAME = "Discovery"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Denver")
# The difficulty pictures' names, in the words the app's difficulty symbols are keyed on. The pictures' words are
# not used: the double black diamond's reads "Black".
LEVELS = {"green-circle": "Green", "blue-square": "Blue", "black-diamond": "Black",
          "double-black-diamond": "Double black"}
# The snow report's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"New Snow (since lifts closed)": "SinceLiftsClosedIn", "New Snow, 24 hours": "Last24HoursIn",
            "New Snow, 48 hours": "Last48HoursIn", "New Snow, 72 hours": "Last72HoursIn",
            "Snow Depth - Bottom": "BaseIn"}
REPORT = re.compile(r"<div class=\"include-table\">(.*?)</section>", re.S)
PART = re.compile(r"<h4[^>]*>(.*?)</h4>|<table id=\"trail\"[^>]*>(.*?)</table>", re.S)
LIFT = re.compile(r"(\S.*?)\s+-\s+([A-Z][A-Z ]*?)(?=\s{2,}|$)")
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
PICTURE = re.compile(r"<img[^>]*\ssrc=\"[^\"]*/([^\"/]+)\.png\"")
WRITTEN = re.compile(r"Updated:\s*([A-Z][a-z]+) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2})\s*([ap]m)")
LINE = re.compile(r"<div class=\"row\">\s*<p>(.*?)</p>\s*<p class=\"little-text[^\"]*\">(.*?)</p>", re.S)
LIFTS_COUNTED = re.compile(r"\d+\s*/\s*(\d+)")
NUMBER = re.compile(r"\d+(?:\.\d+)?|\.\d+")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lifts_of(heading: str) -> list:
    """The lifts one heading names, each with its status; lifts that share a heading are set apart by spaces."""
    said = " ".join(html.unescape(TAG.sub(" ", heading)).replace("\xa0", "  ").replace("\n", " ").strip().split(" "))
    lifts, at = [], 0
    for found in LIFT.finditer(said):
        if said[at:found.start()].strip():
            break
        status = " ".join(found.group(2).split()).capitalize()
        lifts.append({"Name": string.capwords(found.group(1)), "Status": status, "StatusEnglish": status.lower(),
                      "Difficulty": None})
        at = found.end()
    if not lifts or said[at:].strip():
        raise ValueError(f"a lift's heading reads {words(heading)!r}, not a name, a dash and a status")
    return lifts


def trail_row(cells: list) -> dict | None:
    """One trail, or None for the row of the table's headings."""
    if len(cells) != 5:
        raise ValueError("a row of a trail table is not a difficulty, a name, a status, a condition and a comment")
    if "<h5" in cells[1]:
        return None
    name, status, pictures = words(cells[1]), words(cells[2]).capitalize(), PICTURE.findall(cells[0])
    if not name or not status:
        raise ValueError("a row of a trail table has no name or no status")
    if len(pictures) != 1 or pictures[0] not in LEVELS:
        raise ValueError(f"{name} has difficulty pictures {pictures}, not one the reader knows")
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(),
            "Difficulty": LEVELS[pictures[0]], "Grooming": "Yes" if words(cells[3]) == "Groomed" else "No"}


def lift_areas(page: str) -> list:
    """Each heading's lifts with the trails under it, in the page's order."""
    report = REPORT.search(page)
    if not report:
        raise ValueError("the trail report was not found")
    areas = []
    for heading, table in PART.findall(report.group(1)):
        if heading:
            if words(heading).upper().startswith("UPDATED"):
                continue
            lifts = lifts_of(heading)
            areas.append({"Name": " & ".join(lift["Name"] for lift in lifts), "Lifts": lifts, "Trails": None})
        elif not areas or areas[-1]["Trails"] is not None:
            raise ValueError("a table of trails has no lift's heading of its own")
        else:
            areas[-1]["Trails"] = [trail for row in ROW.findall(table) if (trail := trail_row(CELL.findall(row)))]
    for area in areas:
        area["Trails"] = area["Trails"] or []
    lifts = [lift["Name"] for area in areas for lift in area["Lifts"]]
    if not lifts or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    if len(set(lifts)) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return areas


def number(said: str, label: str) -> float | int:
    if not NUMBER.fullmatch(said):
        raise ValueError(f"the snow report's {label} reads {said!r}, not a number")
    value = float(said)
    return int(value) if value.is_integer() else value


def lines(page: str) -> dict:
    """The snow report's lines, each label with what the page says beside it."""
    return {words(label): words(said) for label, said in LINE.findall(page)}


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the bottom and the top."""
    written, said = WRITTEN.search(words(page)), lines(page)
    if not written:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute, half = written.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    missing = [label for label in (*SNOWFALL, "Snow Depth - Top") if label not in said]
    if missing:
        raise ValueError(f"the snow report has no line for {missing}")
    base = {"Name": "Bottom", **{field: number(said[label], label) for label, field in SNOWFALL.items()}}
    season = said.get("Snowfall, YTD")
    return {"LastUpdate": at.replace(tzinfo=LOCAL_TIME).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": said.get("Surface Conditions (Primary)") or None,
            "SeasonTotalIn": number(season, "season's total") if season else None, "BaseArea": base,
            "SummitArea": {"Name": "Top", "BaseIn": number(said["Snow Depth - Top"], "Snow Depth - Top")},
            "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    areas = lift_areas(pages["lifts"])
    read = sum(len(area["Lifts"]) for area in areas)
    counted = LIFTS_COUNTED.fullmatch(lines(pages["snow"]).get("Lifts Open", ""))
    if counted and int(counted.group(1)) != read:
        raise ValueError(f"the snow report counts {counted.group(1)} lifts but {read} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
