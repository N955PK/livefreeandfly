"""Ski Big Bear's lifts and trails, and its snow report, from its conditions and trail map page
(ski-bigbear.com/conditions-trail-map).

The page is built on the server from the mountain's own data, and carries that data with it as JSON
(``window.__remixContext``): the page's "status" holds the lifts, each a name and a status, the trails, each a name,
a difficulty (beginner, intermediate, advanced, expert) and a status, a list of conditions, the mountain's message
and when the report was updated. A status is carried in the page's own words (Open, Closed). The page lists the
trails under a heading for each difficulty, so the lifts are one mountain area and each difficulty's trails
another. A difficulty the reader does not know, a lift or trail with no name or no status, or a name given twice
fails, so a change in the page's shape fails instead of showing wrong numbers.

The conditions give a base depth and a snow surface, each "N/A" out of season. The page was only ever seen closed,
so the base depth is read as inches given once or as a least and a most, and anything else costs the snow report.
Its "Recent Snowfall" does not say over how long, so it is not carried as a 24 hour figure. A snow report that
cannot be read costs only the snow report, not the lifts. The time the report was updated is given in UTC.
Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone

URL = "https://www.ski-bigbear.com/conditions-trail-map"
NAME = "Ski Big Bear"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
ROUTE = "routes/_page.conditions-trail-map"
# The page's difficulty words, by the heading it lists them under and the words the app's symbols are keyed on.
LEVELS = {"beginner": ("Beginner Trails", "Green"), "intermediate": ("Intermediate Trails", "Blue"),
          "advanced": ("Advanced Trails", "Black"), "expert": ("Expert Trails", "Double black")}
CONTEXT = re.compile(r"window\.__remixContext\s*=\s*")
NONE = re.compile(r"(?:n/?a|none|[–—-]*)", re.I)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\"|in\.?|inch(?:es)?)?", re.I)
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\"|in\.?|inch(?:es)?)?\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*"
                   r"(?:″|”|\"|in\.?|inch(?:es)?)?", re.I)


def status_of(page: str) -> dict:
    """The mountain's status from the data the page carries."""
    found = CONTEXT.search(page)
    if not found:
        raise ValueError("the page's data was not found")
    try:
        context, _ = json.JSONDecoder().raw_decode(page, found.end())
        status = context["state"]["loaderData"][ROUTE]["status"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError(f"the page's data could not be read: {error!r}") from error
    if not isinstance(status, dict) or not isinstance(status.get("lifts"), list) \
            or not isinstance(status.get("trails"), list):
        raise ValueError("the page's status has no list of lifts or of trails")
    return status


def status_row(row, difficulty: str | None) -> dict:
    name, said = (row.get("name"), row.get("status")) if isinstance(row, dict) else (None, None)
    if not isinstance(name, str) or not name.strip() or not isinstance(said, str) or not said.strip():
        raise ValueError(f"a lift or trail reads {row!r}, not a name and a status")
    said = " ".join(said.split())
    return {"Name": " ".join(name.split()), "Status": said.capitalize(), "StatusEnglish": said.lower(),
            "Difficulty": difficulty}


def trail_areas(trails: list) -> list:
    """The trails of each difficulty as an area, in the page's order."""
    areas = {}
    for trail in trails:
        level = trail.get("difficulty") if isinstance(trail, dict) else None
        if level not in LEVELS:
            raise ValueError(f"a trail has a difficulty the reader does not know: {trail!r}")
        heading, difficulty = LEVELS[level]
        areas.setdefault(heading, []).append(status_row(trail, difficulty))
    return [{"Name": heading, "Lifts": [], "Trails": rows} for heading, rows in areas.items()]


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def depth(said: str) -> dict:
    """The base depth as one figure, or as its least and its most where the mountain gives the two; no figure
    where it gives none."""
    if NONE.fullmatch(said):
        return {"BaseIn": None}
    spread, single = RANGE.fullmatch(said), INCHES.fullmatch(said)
    if spread and number(spread.group(1)) <= number(spread.group(2)):
        return {"BaseMinIn": number(spread.group(1)), "BaseMaxIn": number(spread.group(2))}
    if not single:
        raise ValueError(f"the base depth reads {said!r}, not inches")
    return {"BaseIn": number(single.group(1))}


def snow_report(status: dict) -> dict:
    """The page's conditions in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    try:
        at = datetime.strptime(status.get("date_updated") or "", "%Y-%m-%dT%H:%M:%S.%f%z")
    except (TypeError, ValueError) as error:
        raise ValueError(f"the time the report was updated could not be read: {error}") from error
    conditions = status.get("conditions")
    if not isinstance(conditions, list) or not all(isinstance(entry, dict) for entry in conditions):
        raise ValueError("the page's status has no list of conditions")
    said = {str(entry.get("key")).strip().lower(): str(entry.get("value") or "").strip() for entry in conditions}
    if "base depth" not in said:
        raise ValueError("the conditions give no base depth")
    surface, message = said.get("snow surface", ""), str(status.get("message") or "").strip()
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None if NONE.fullmatch(surface) else surface, "SeasonTotalIn": None,
            "BaseArea": {"Name": "Mountain", **depth(said["base depth"])},
            "Report": html.escape(message) or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    status = status_of(page)
    lifts, areas = [status_row(lift, None) for lift in status["lifts"]], trail_areas(status["trails"])
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    for rows in (lifts, [trail for area in areas for trail in area["Trails"]]):
        names = [row["Name"].lower() for row in rows]
        if len(set(names)) != len(names):
            raise ValueError("the page names a lift or a trail twice")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(status)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
