"""Sundance's lifts and trails, and its snow report, from the report its own mountain-report page reads
(sundanceresort.com/mountain-report).

The page reads one file of JSON from its own site (/api/mountain-information/) and fills its tables from it. The
file has a list for the lifts, one for the ski trails (it calls it grooming, and it also holds the summer's hiking
and biking trails, marked not to be shown) and one for the terrain parks. Each list starts with its own count,
and only the entries marked to be shown are read, as the page does. The trails are grouped by the part of the
mountain each names, in the file's order, and the terrain parks are a part of their own. A trail's status is
"Closed", "Open" or "Open - Groomed": the last is an open trail that has been groomed. The file's count of lifts
is checked against what is read, so a change in its shape fails instead of showing wrong numbers.

The snow report gives the base depth, the 24 and 48 hour snowfall and the season's total in inches. The file does
not say when they were posted (the page says only that they are updated daily at 5 AM), so the report carries no
time, and the runner leaves an undated report out while no lift is turning. Standard library only.
"""
import json
from datetime import datetime

URL = "https://www.sundanceresort.com/api/mountain-information/"
NAME = "Sundance"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
COUNT = "open-count"
# The file's difficulty words, in the words the app's difficulty symbols are keyed on. Its double blue is a harder
# blue, not an expert run; a terrain park listed among the trails ("freestyle") has none.
LEVELS = {"green": "Green", "blue": "Blue", "double blue": "Blue", "black": "Black", "double black": "Double black",
          "freestyle": ""}
# The file's snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"base_snow": "BaseIn", "24hr_snow": "Last24HoursIn", "48hr_snow": "Last48HoursIn"}
SEASON, WORDS = "ytd_snow", "day_forecast"
PARKS = "Terrain Parks"


def shown(entries) -> list:
    """A list's entries the page shows: all but its count and those marked not to be shown."""
    if not isinstance(entries, list):
        raise ValueError("a list of the report is missing")
    return [entry for entry in entries if entry.get("id") != COUNT and entry.get("display") == "yes"]


def named(entry: dict, kind: str) -> str:
    """An entry's name: under the list's own heading ("Lifts", "Trails"), or "label" as the file once had it."""
    return str(entry.get(kind) or entry.get("label") or "").strip()


def status_row(entry: dict, kind: str, difficulty: str | None) -> dict:
    """One lift or trail. Its status is open, closed or a hold, with "Groomed" after a dash on a groomed trail."""
    name, said = named(entry, kind), str(entry.get("status_value") or "").strip()
    status = said.split(" - ")[0].strip().capitalize()
    known = status in ("Open", "Closed") or "hold" in status.lower() or "delay" in status.lower()
    if not name or not known:
        raise ValueError(f"{name or 'an entry'} has the status {said!r}, not one the reader knows")
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(entry: dict, difficulty: str | None = None) -> dict:
    if difficulty is None:
        if entry.get("difficulty") not in LEVELS:
            raise ValueError(f"{named(entry, 'Trails')} has a difficulty the reader does not know: "
                             f"{entry.get('difficulty')}")
        difficulty = LEVELS[entry["difficulty"]]
    row = status_row(entry, "Trails", difficulty)
    row["Grooming"] = "Yes" if "groomed" in str(entry["status_value"]).lower() else "No"
    return row


def trail_areas(entries: list) -> list:
    """The trails by the part of the mountain each names, in the file's order."""
    areas = {}
    for entry in entries:
        part = str(entry.get("type") or entry.get("area") or "").strip()
        if not part:
            raise ValueError(f"{named(entry, 'Trails')} names no part of the mountain")
        areas.setdefault(part, []).append(trail_row(entry))
    return [{"Name": part, "Lifts": [], "Trails": trails} for part, trails in areas.items()]


def inches(entries: dict, key: str) -> float | int | None:
    """A snow figure in inches, or None where the file leaves it empty."""
    said = str((entries.get(key) or {}).get("status_value") or "").strip()
    if not said:
        return None
    try:
        value = float(said)
    except ValueError:
        raise ValueError(f"the snow report's {key} reads {said!r}, not a number") from None
    if value < 0:
        raise ValueError(f"the snow report's {key} reads {said!r}")
    return int(value) if value.is_integer() else value


def snow_report(entries) -> dict | None:
    """The file's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain. None when it
    gives no base depth."""
    if not isinstance(entries, list):
        return None
    by_id = {entry.get("id"): entry for entry in entries}
    area = {"Name": "Mountain", **{ikon: inches(by_id, key) for key, ikon in SNOWFALL.items()}}
    if area["BaseIn"] is None:
        return None
    words = str((by_id.get(WORDS) or {}).get("status_value") or "").strip()
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": inches(by_id, SEASON),
            "BaseArea": area, "Report": words or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    report = json.loads(page)
    if not isinstance(report, dict) or "lift-status" not in report or "grooming" not in report:
        raise ValueError("the report has no lifts or no trails")
    try:
        lifts = [status_row(entry, "Lifts", None) for entry in shown(report["lift-status"])]
        areas = trail_areas(shown(report["grooming"]))
        parks = [trail_row(entry, "") for entry in shown(report.get("terrain-parks") or [])]
        counted = next((entry.get("total") for entry in report["lift-status"] if entry.get("id") == COUNT), None)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if parks:
        areas.append({"Name": PARKS, "Lifts": [], "Trails": parks})
    if not lifts or not areas:
        raise ValueError("the report lists no lifts or no trails")
    if counted != len(lifts):
        raise ValueError(f"the report counts {counted} lifts but {len(lifts)} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        snow = snow_report(report.get("snow-weather"))
    except (ValueError, TypeError, AttributeError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
