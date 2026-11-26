"""Taos Ski Valley's lifts and trails, and its snow report, from its lifts and trails page (skitaos.com/lifts).

The page is built on the server and carries what it draws as data in its own scripts: the pieces of one long text,
each handed to ``self.__next_f.push``. In that text the trail map's part has "liftData" and, straight after it,
"slopeData", each with a summer list and a winter list; the winter lists are read. The summer lists hold the bike
trails and the restaurants and shops the resort posts hours for, and are left alone. Neither a lift nor a trail names
a part of the mountain, so there is one mountain area. A lift's status is carried in the page's word. A trail is open
or closed and nothing else, and its difficulty is one of the page's five words; one the reader does not know fails.
Only the rows the resort counts as trails are kept, which leaves out the skating rink it lists among them. The page's
own counts of lifts and of slopes have to match what was read, so a change in the page's shape fails instead of
showing wrong numbers.

The snow figures are the ones the page shows under "Weather Conditions": one base depth, the snowfall of the last 24,
48 and 72 hours and 7 days, the snow overnight where it is given, and the season's total, in inches. The page does
not say when they were measured, so the report is undated, and the runner leaves an undated report out while no lift
is turning. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import json
import re
from datetime import datetime

URL = "https://www.skitaos.com/lifts"
NAME = "Taos Ski Valley"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The page's difficulty words, in the words the app's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"easy": "Green", "intermediate": "Blue", "expert": "Black", "extreme-terrain": "Double black",
          "terrain-park": ""}
# The page's snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"base": "BaseIn", "last24Hours": "Last24HoursIn", "last48Hours": "Last48HoursIn",
            "last72Hours": "Last72HoursIn", "last7Days": "Last7DaysIn", "overnight": "OvernightIn"}
PIECE = re.compile(r"self\.__next_f\.push\(\[1,(\"(?:[^\"\\]|\\.)*\")\]\)")
DECODER = json.JSONDecoder()
# Where the page's own counts of lifts and slopes start.
COUNTS = "{\"liftsOpen\":"


def carried(page: str) -> str:
    """The text the page's scripts carry, put back together."""
    try:
        text = "".join(json.loads(piece) for piece in PIECE.findall(page))
    except json.JSONDecodeError as error:
        raise ValueError(f"the page's data does not read as JSON: {error}") from error
    if not text:
        raise ValueError("the page carries no data in its scripts")
    return text


def value_at(text: str, start: int, what: str):
    try:
        return DECODER.raw_decode(text, start)
    except json.JSONDecodeError as error:
        raise ValueError(f"the page's {what} does not read as JSON: {error}") from error


def value_after(text: str, label: str, what: str):
    """The value the text gives after the first ``label``."""
    at = text.find(label)
    if at < 0:
        raise ValueError(f"the page's {what} was not found")
    return value_at(text, at + len(label), what)[0]


def winter(listing, what: str) -> list:
    """The rows of a listing's winter list, which has to be whole: as many rows as it says it has."""
    try:
        rows, total = listing["winter"]["data"], listing["winter"]["total"]
    except (KeyError, TypeError) as error:
        raise ValueError(f"the {what} are not in the shape expected: {error!r}") from error
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows) or total != len(rows):
        raise ValueError(f"the page says it has {total} {what} but does not list that many")
    return rows


def name_of(row: dict) -> str:
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the page lists a lift or a trail with no name")
    return name.strip()


def lift_row(lift: dict) -> dict:
    name, status = name_of(lift), lift.get("status")
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"{name} has no status")
    words = status.replace("-", " ").replace("_", " ").strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": None}


def trail_row(trail: dict) -> dict:
    name = name_of(trail)
    if not isinstance(trail.get("open"), bool):
        raise ValueError(f"{name} is not said to be open or closed")
    if trail.get("difficulty") not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {trail.get('difficulty')}")
    status = "Open" if trail["open"] else "Closed"
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(),
            "Difficulty": LEVELS[trail["difficulty"]],
            "Grooming": "Yes" if "groom" in str(trail.get("conditions") or "").lower() else "No"}


def mountain_area(text: str) -> dict:
    """The winter lifts and trails, as one mountain area."""
    at = text.find("\"liftData\":")
    if at < 0:
        raise ValueError("the page's lifts were not found")
    lifts, end = value_at(text, at + len("\"liftData\":"), "lifts")
    if not text.startswith(",\"slopeData\":", end):
        raise ValueError("the page's trails were not found after its lifts")
    slopes = value_at(text, end + len(",\"slopeData\":"), "trails")[0]
    lifts, slopes = winter(lifts, "lifts"), winter(slopes, "slopes")
    counts = value_at(text, text.find(COUNTS), "counts")[0] if COUNTS in text else {}
    if not isinstance(counts, dict):
        raise ValueError("the page's counts are not in the shape expected")
    if counts.get("liftsTotal") != len(lifts) or counts.get("slopesTotal") != len(slopes):
        raise ValueError(f"the page counts {counts.get('liftsTotal')} lifts and {counts.get('slopesTotal')} slopes "
                         f"but {len(lifts)} and {len(slopes)} were read")
    area = {"Name": NAME, "Lifts": [lift_row(lift) for lift in lifts],
            "Trails": [trail_row(trail) for trail in slopes if trail.get("includeInTrailCount") is True]}
    if not area["Lifts"] or not area["Trails"]:
        raise ValueError("the page lists no lifts or no trails")
    return area


def figure(value, what: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"the snow report's {what} reads {value!r}, not inches")
    return value


def snow_report(text: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain, undated."""
    said = value_after(text, "\"snowData\":", "snow report")
    if not isinstance(said, dict):
        raise ValueError("the snow report is not in the shape expected")
    figures = {ikon: figure(said.get(field), field) for field, ikon in SNOWFALL.items()}
    if figures["BaseIn"] is None or figures["Last24HoursIn"] is None:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    area = {"Name": "Base", **{ikon: value for ikon, value in figures.items() if value is not None}}
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": figure(said.get("seasonTotal"), "seasonTotal"), "BaseArea": area, "Report": None,
            "Alert": None}


def parse(page: str, now: datetime) -> dict:
    text = carried(page)
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": [mountain_area(text)]}
    try:
        feed["SnowReport"] = snow_report(text)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
