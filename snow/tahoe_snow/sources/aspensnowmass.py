"""Aspen Mountain's, Aspen Highlands', Buttermilk's and Snowmass's lifts and trails, and their snow reports, from the
reports their own pages on aspensnowmass.com read (aspensnowmass.com/four-mountains/<mountain>/lift-status and
/four-mountains/<mountain>/snow-and-grooming-report).

The four are one company's, on one site, and each is a mountain of its own here, under its own key. The pages are
drawn in the browser from three reports on the same site (/AspenSnowmass/LiftStatus/Feed, /GroomingReport/Feed and
/SnowReport/Feed), each asked for one mountain by the name the page itself gives (AspenMountain, AspenHighlands,
Buttermilk, Snowmass). The lift report names each lift's part of the mountain and the grooming report lists the
trails by part of the mountain; a part is a mountain area here, holding its lifts and its trails. A lift's status is
carried in the report's words (Open, Closed, Hold or On Hold, which are the ones the page has a picture for) and one
the reader does not know fails. A trail is open when the report says it is open today, which is what the page shows,
and its grooming is the report's. The uphill routes are left out: the status is of the lift-served mountain. The
snow report's own count of lifts is checked against what is read, so a change in the reports' shape fails instead
of showing wrong numbers.

The snow report gives one base depth for the mountain, the snowfall of the last 24, 48 and 72 hours and 7 days, the
resort's own words, and when it was posted, in Mountain time. It gives no surface and no season total. A snow report
that cannot be read costs only the snow report, not the lifts.

``parse`` takes all twelve reports and gives the four mountains by key; one mountain whose reports cannot be read
is left out without costing the others, and it fails only when none can be read. ``mountain`` reads one. Standard
library only.
"""
import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FEEDS = "https://www.aspensnowmass.com/AspenSnowmass"
# Mountain: (its name, the name its pages ask the reports for).
MOUNTAINS = {"aspen": ("Aspen Mountain", "AspenMountain"), "highlands": ("Aspen Highlands", "AspenHighlands"),
             "buttermilk": ("Buttermilk", "Buttermilk"), "snowmass": ("Snowmass", "Snowmass")}
KINDS = {"lifts": "LiftStatus/Feed?mountain={code}&areas=&isSummer=False", "trails": "GroomingReport/Feed?mountain={code}",
         "snow": "SnowReport/Feed?mountain={code}"}
URLS = {f"{key}_{kind}": f"{FEEDS}/{path.format(code=code)}"
        for key, (_, code) in MOUNTAINS.items() for kind, path in KINDS.items()}
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The lift report's statuses, as the app writes them.
STATUSES = {"open": "Open", "closed": "Closed", "hold": "Hold", "on hold": "On hold"}
# The grooming report's difficulty words, in the words the app's difficulty symbols are keyed on; terrain parks have
# none.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black",
          "extreme": "Double black", "terrain-park": ""}
NOT_LIFT_SERVED = {"uphill routes"}
# The snow report's snowfall figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"snowBase": "BaseIn", "snow24Hours": "Last24HoursIn", "snow48Hours": "Last48HoursIn",
            "snow72Hours": "Last72HoursIn", "snow7Days": "Last7DaysIn"}
TAG = re.compile(r"<[^>]+>")


def report(page: str, what: str) -> dict:
    try:
        found = json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the {what} report does not read as JSON: {error}") from error
    if not isinstance(found, dict):
        raise ValueError(f"the {what} report is not in the shape expected")
    return found


def named(row: dict, field: str, what: str) -> str:
    name = row.get(field)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"the report lists {what} with no name")
    return name.strip()


def lift_row(lift: dict) -> dict:
    name, said = named(lift, "liftName", "a lift"), lift.get("status")
    if not isinstance(said, str) or said.strip().lower() not in STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {said!r}")
    status = STATUSES[said.strip().lower()]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(trail: dict) -> dict:
    name = named(trail, "name", "a trail")
    if trail.get("difficulty") not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {trail.get('difficulty')!r}")
    if not isinstance(trail.get("isDayOpen"), bool) or not isinstance(trail.get("isGroomed"), bool):
        raise ValueError(f"{name} does not say whether it is open and groomed")
    status = "Open" if trail["isDayOpen"] else "Closed"
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": LEVELS[trail["difficulty"]],
            "Grooming": "Yes" if trail["isGroomed"] else "No"}


def inches(figure) -> float | int:
    """A figure the report gives as {"inches": "12", "centimeters": "30"}."""
    try:
        value = float(figure["inches"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"a snow figure reads {figure!r}, not inches") from error
    if value < 0:
        raise ValueError(f"a snow figure reads {figure!r}, not inches")
    return int(value) if value.is_integer() else value


def snow_report(snow: dict) -> dict:
    """The snow report in the shape of the Ikon feed's SnowReport: one set of figures for the whole mountain."""
    try:
        posted = datetime.strptime(snow.get("lastUpdated") or "", "%I:%M %p %b %d, %Y")
    except ValueError as error:
        raise ValueError(f"the snow report does not say when it was posted: {error}") from error
    area = {"Name": "Mountain", **{ikon: inches(snow.get(field)) for field, ikon in SNOWFALL.items()}}
    words = " ".join(html.unescape(TAG.sub(" ", snow.get("today") or "")).split())
    return {"LastUpdate": posted.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": None, "BaseArea": area,
            "Report": words or None, "Alert": None}


def mountain(key: str, pages: dict, now: datetime) -> dict:
    """One mountain in the app's shape, from its three reports in ``pages`` (named as in URLS)."""
    name = MOUNTAINS[key][0]
    lifts = report(pages[f"{key}_lifts"], "lift").get("liftStatuses")
    listed = report(pages[f"{key}_trails"], "grooming").get("areas")
    if not isinstance(lifts, list) or not isinstance(listed, list):
        raise ValueError("the reports are not in the shape expected")
    areas = {}
    try:
        for lift in lifts:
            part = named(lift, "area", "a lift's part of the mountain")
            areas.setdefault(part, {"Name": part, "Lifts": [], "Trails": []})["Lifts"].append(lift_row(lift))
        for each in listed:
            part = named(each, "name", "a part of the mountain")
            if part.lower() in NOT_LIFT_SERVED:
                continue
            area = areas.setdefault(part, {"Name": part, "Lifts": [], "Trails": []})
            area["Trails"].extend(trail_row(trail) for trail in each["trails"])
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the reports are not in the shape expected: {error!r}") from error
    if not lifts:
        raise ValueError("the report lists no lifts")
    if not any(area["Trails"] for area in areas.values()):
        raise ValueError("the report lists no trails")
    feed = {"Name": name, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        snow = report(pages[f"{key}_snow"], "snow")
        counted = (snow.get("lifts") or {}).get("totalCount") if isinstance(snow.get("lifts"), dict) else None
    except ValueError as error:
        print(f"{name}: snow report: {error}")
        return feed
    if isinstance(counted, int) and counted != len(lifts):
        raise ValueError(f"the snow report counts {counted} lifts but {len(lifts)} were read")
    try:
        feed["SnowReport"] = snow_report(snow)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return feed


def parse(pages: dict, now: datetime) -> dict:
    """The four mountains by key. One whose reports cannot be read is left out; none readable fails."""
    feeds, errors = {}, []
    for key, (name, _) in MOUNTAINS.items():
        try:
            feeds[key] = mountain(key, pages, now)
        except (KeyError, ValueError) as error:
            print(f"{name}: {error}")
            errors.append(f"{name}: {error}")
    if not feeds:
        raise ValueError("; ".join(errors))
    return feeds
