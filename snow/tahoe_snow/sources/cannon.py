"""Cannon Mountain's lifts and trails, and its snow report, from its mountain report page (cannonmt.com/mountain-report).

The page is built on the server and carries the data it is drawn from as one JSON document inside it (the
``__NEXT_DATA__`` script): the lifts, the trails of each part of the mountain and the morning's report. That document
is what is read, not the drawn tables, so the reading does not depend on the page's styling. The browser cannot read
the page from another site; a scheduled job reads it and writes one small file the page reads, in the shape of the
Ikon feed the rest of the page uses.

A lift's status is one word (open, closed, onHold). A trail's is a list of marks (open, pendingInspection, groomed,
snowmaking): with no mark the trail is closed, as the page draws it. The resort can also shut a whole part of the
mountain, or all of it, with one switch that overrules the marks, and the page's own rule is followed. The trail
lists are named by the part of the mountain they belong to; one the reader does not know fails instead of being
dropped.

The snow report gives the base depth and the new snow as a least and a most. Both are carried, with the middle of
the two as the one figure; a figure the resort leaves empty stays empty. The page does not say over how long its
"new snow" fell: it is carried as the last 24 hours, beside the page's own 48 hour figure. Standard library only.
"""
import json
import re
from datetime import datetime, timezone

URL = "https://www.cannonmt.com/mountain-report"
NAME = "Cannon Mountain"
DATA = re.compile(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", re.S)
TRAIL_LISTS = "TrailsFieldEntries"
# Each trail list of the page's data: the name the page prints over it and the switch that shuts all of it.
AREAS = {
    "upper": ("Upper Mountain", "toggleAllOverrideUpper"),
    "tuckerbrook": ("Tuckerbrook Family Area", "toggleAllOverrideTuckerbrook"),
    "midMountain": ("Mid-Mountain", "toggleAllOverrideMidMt"),
    "front": ("Front5", "toggleAllOverrideFront5"),
    "mittersill": ("Mittersill", "toggleAllOverrideMittersill"),
    "glades": ("Glades", "toggleAllOverrideGlades"),
}
# The switch that shuts every lift and trail.
ALL_SHUT = "toggleAllOverride"
# The page's difficulty marks, in the words the page's difficulty symbols are keyed on.
LEVELS = {"greenCircle": "Green", "blueSquare": "Blue", "blackDiamond": "Black", "doubleBlackDiamond": "Double black"}
HELD = {"onHold": "On hold", "pendingInspection": "Pending inspection"}


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def status_of(marks: list, shut: bool) -> str:
    """The page's own rule: a shut part of the mountain is closed whatever its marks say, a hold comes before open,
    and anything not marked open is closed."""
    if shut:
        return "Closed"
    held = next((HELD[mark] for mark in marks if mark in HELD), None)
    return held or ("Open" if "open" in marks else "Closed")


def trail_row(trail: dict, shut: bool) -> dict:
    marks = trail["trailStatus"]
    if not isinstance(marks, list):
        raise ValueError(f"the trail {trail['title']} has no list of marks")
    row = status_row(trail["title"].strip(), status_of(marks, shut), LEVELS.get(trail.get("difficulty") or "", ""))
    row["Grooming"] = "Yes" if "groomed" in marks and not shut else "No"
    return row


def figure(value) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"a snow figure reads {value!r}, not a number")
    return int(value) if float(value).is_integer() else value


def span(pairs, name: str) -> dict:
    """A figure the page gives as [{"min": 34, "max": 68}], under the Ikon feed's name for it with its least and
    most beside it; the one figure is the middle of the two. Empty where the page gives neither."""
    pair = pairs[0] if isinstance(pairs, list) and pairs else {}
    low, high = figure(pair.get("min")), figure(pair.get("max"))
    low, high = (high if low is None else low), (low if high is None else high)
    if low is not None and low > high:
        raise ValueError(f"the page's {name} runs from {low} down to {high}")
    middle = None if low is None else figure((low + high) / 2)
    return {f"{name}In": middle, f"{name}MinIn": low, f"{name}MaxIn": high}


def snow_report(report: dict) -> dict:
    """The morning report in the shape of the Ikon feed's SnowReport: one set of figures for the whole mountain."""
    posted = datetime.fromisoformat(report["dateUpdated"]).astimezone(timezone.utc)
    said = (report.get("snowConditions") or [{}])[0]
    surface = ", ".join(dict.fromkeys(word.strip() for word in (said.get("primary"), said.get("secondary"))
                                      if isinstance(word, str) and word.strip()))
    area = {"Name": "Mountain", **span(report.get("baseDepth"), "Base"), **span(report.get("newSnow"), "Last24Hours"),
            "Last48HoursIn": figure(report.get("snowLast48Hours"))}
    return {"LastUpdate": posted.strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": figure(report.get("seasonTotal")), "BaseArea": area, "Report": report.get("copy") or None,
            "Alert": None}


def parse(page: str, now: datetime) -> dict:
    found = DATA.search(page)
    if not found:
        raise ValueError("the page's data was not found")
    try:
        data = json.loads(found.group(1))["props"]["pageProps"]["data"]
        status, report = data["trailsLiftsEntries"][0], data["mountainReportEntries"][0]
        all_shut = bool(status[ALL_SHUT])
        lifts = [status_row(lift["title"].strip(), status_of([lift["liftStatus"]], all_shut), None)
                 for lift in status["lifts"]]
        areas = []
        for key, trails in data.items():
            if not key.endswith(TRAIL_LISTS):
                continue
            part = key[:-len(TRAIL_LISTS)]
            if part not in AREAS:
                raise ValueError(f"the page has a trail list this reader does not know: {key}")
            name, switch = AREAS[part]
            shut = all_shut or bool(status[switch])
            areas.append({"Name": name, "Lifts": [], "Trails": [trail_row(trail, shut) for trail in trails]})
        snow = snow_report(report)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError(f"the page's data is not in the shape expected: {error!r}") from error
    areas = [area for area in areas if area["Trails"]]
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    if not all(row["Name"] for area in areas for row in area["Trails"]) or not all(lift["Name"] for lift in lifts):
        raise ValueError("the page lists a lift or a trail with no name")
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas], "SnowReport": snow}
