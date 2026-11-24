"""Alta's lifts and runs, and its snow report, from its lift and terrain status page (alta.com/lift-terrain-status).

The page is built on the server and carries the data it is drawn from as one JSON document inside it
(``window.Alta = {...}``): the lifts, the runs each lift serves, and the day's conditions. That document is what is
read, not the drawn tables. Each lift is a mountain area with its runs. A run two lifts serve is listed under both
in the page's data; here it is kept under the first, so each run is counted once, and the page's own counts of lifts
and runs are checked against what is read, so a change in its shape fails instead of showing wrong numbers.

A lift is open or not (the page gives nothing between). A run is open or not, and groomed or not. The page's
hike-to terrain areas (Ballroom, Backside and the rest) and its access gates are not runs and are left out.

The conditions give one base depth, the snow of the last 12 and 24 hours, the storm's total and the season's, and
when they were measured, in Mountain time. They give no surface. Standard library only.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.alta.com/lift-terrain-status"
NAME = "Alta"
MARK = "window.Alta ="
MOUNTAIN = ZoneInfo("America/Denver")
# The page's difficulty words, in the words the page's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black"}
# The conditions' figures, by the names the Ikon feed gives them.
SNOWFALL = {"last12": "Last12HoursIn", "last24": "Last24HoursIn", "storm_total": "StormTotalIn"}


def status_row(name, is_open, difficulty: str | None) -> dict:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the page lists a lift or a run with no name")
    if not isinstance(is_open, bool):
        raise ValueError(f"{name} is neither open nor closed: {is_open!r}")
    status = "Open" if is_open else "Closed"
    return {"Name": name.strip(), "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def run_row(run: dict) -> dict:
    if run["difficulty"] not in LEVELS:
        raise ValueError(f"{run['name']} has a difficulty the reader does not know: {run['difficulty']}")
    if not isinstance(run["groomed"], bool):
        raise ValueError(f"{run['name']} is neither groomed nor not: {run['groomed']!r}")
    row = status_row(run["name"], run["open"], LEVELS[run["difficulty"]])
    row["Grooming"] = "Yes" if run["groomed"] and run["open"] else "No"
    return row


def figure(said) -> float | int | None:
    """A figure the page gives as "39.0"; None where it gives nothing."""
    if said is None or str(said).strip() == "":
        return None
    try:
        value = float(str(said).strip())
    except ValueError:
        raise ValueError(f"a snow figure reads {said!r}, not a number") from None
    if value < 0:
        raise ValueError(f"a snow figure is below nothing: {said!r}")
    return int(value) if value.is_integer() else value


def snow_report(conditions: dict) -> dict:
    """The conditions in the shape of the Ikon feed's SnowReport: one set of figures for the whole mountain."""
    measured = datetime.strptime(conditions["dated_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MOUNTAIN)
    area = {"Name": "Mountain", "BaseIn": figure(conditions["base_depth"])}
    area.update({ikon: figure(conditions[field]) for field, ikon in SNOWFALL.items()})
    return {"LastUpdate": measured.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": figure(conditions["year_to_date"]), "BaseArea": area}


def parse(page: str, now: datetime) -> dict:
    at = page.find(MARK)
    if at < 0:
        raise ValueError("the page's data was not found")
    try:
        data, _ = json.JSONDecoder().raw_decode(page[at + len(MARK):].lstrip())
    except json.JSONDecodeError as error:
        raise ValueError(f"the page's data does not read as JSON: {error}") from error
    try:
        areas, seen = [], set()
        for lift in data["liftStatus"]["lifts"]:
            runs = [run for run in lift["runs"] if run["id"] not in seen]
            seen.update(run["id"] for run in runs)
            areas.append({"Name": lift["name"].strip(), "Lifts": [status_row(lift["name"], lift["open"], None)],
                          "Trails": [run_row(run) for run in runs]})
        counted = data["operations"]["lifts"]["total"], data["operations"]["runs"]["total"]
        snow = snow_report(data["conditions"])
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError(f"the page's data is not in the shape expected: {error!r}") from error
    if not areas:
        raise ValueError("the page lists no lifts")
    if (len(areas), len(seen)) != counted:
        raise ValueError(f"the page counts {counted[0]} lifts and {counted[1]} runs but {len(areas)} and "
                         f"{len(seen)} were read")
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas, "SnowReport": snow}
