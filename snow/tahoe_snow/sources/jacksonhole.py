"""Jackson Hole's lifts and trails, and its snow report, from the report its own mountain-report page reads
(jacksonhole.com/mountain-report).

The page reads one file of JSON from the resort's own service, which does not let a page on another site read it,
so the collector does. It lists every lift and trail for the whole mountain, not by area, so they are one mountain
area. A lift or trail closed for the season is given as "out of period", which is said here as closed; any other
status is carried in the report's own word. The report's count of lifts is checked against what is read, so a
change in its shape fails instead of showing wrong numbers; its count of trails is of named runs and is lower than
the list it gives, so the list is only required to hold at least that many. The snow report is carried in the
shape of the Ikon feed's: the resort measures at mid-mountain and at the top of the tram, and gives nothing for
the base. A figure the resort leaves empty stays empty. Standard library only.
"""
import json
from datetime import datetime, timezone

URL = "https://jacksonhole-prod.zaneray.com/api/all.json"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The report's trail levels, in the words the page's difficulty symbols are keyed on. Its double blue is a harder
# blue, not an expert run; terrain parks have no level.
LEVELS = {"GREEN_CIRCLE": "Green", "BLUE_SQUARE": "Blue", "DOUBLE_BLUE_SQUARE": "Blue", "BLACK_DIAMOND": "Black",
          "DOUBLE_BLACK_DIAMOND": "Double black", "TERRAIN_PARKS": ""}
# The report's snow figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"totalSnowDepth": "BaseIn", "newSnowLast24H": "Last24HoursIn", "newSnowLast48H": "Last48HoursIn",
            "newSnowLast72H": "Last72HoursIn", "newSnowLast7D": "Last7DaysIn", "seasonTotalSnow": "SeasonTotalIn"}
# Where the resort measures, by the Ikon feed's names for a mountain's stakes.
STAKES = {"midMountain": ("MidMountainArea", "Mid-Mountain"), "tramSummit": ("SummitArea", "Tram Summit")}


def status_row(item: dict, difficulty: str | None) -> dict:
    said = item.get("openingStatus")
    if not said or not item.get("name"):
        raise ValueError(f"a lift or trail has no name or no status: {item}")
    words = "Closed" if said == "OUT_OF_PERIOD" else said.replace("_", " ").capitalize()
    return {"Name": item["name"].strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail.get("trailLevel") not in LEVELS:
        raise ValueError(f"{trail.get('name')} has a level the reader does not know: {trail.get('trailLevel')}")
    row = status_row(trail, LEVELS[trail["trailLevel"]])
    row["Grooming"] = "Yes" if (trail.get("groomingStatus") or "").strip() else "No"
    return row


def inches(figure) -> float | int | None:
    """A snow figure in inches, or None where the report gives none."""
    if not isinstance(figure, dict) or str(figure.get("value", "")).strip() == "":
        return None
    if figure.get("unit") != "INCH":
        raise ValueError(f"a snow figure is in {figure.get('unit')}, not inches")
    value = float(str(figure["value"]).replace(",", ""))
    return int(value) if value.is_integer() else value


def snow_report(report: dict) -> dict | None:
    """The report's snow figures in the shape of the Ikon feed's SnowReport. None when it gives none."""
    snow = report.get("snow") or {}
    out = {}
    for place, (stake, name) in STAKES.items():
        at = snow.get(place)
        if at:
            out[stake] = {"Name": name, **{ikon: inches(at.get(field)) for field, ikon in SNOWFALL.items()}}
    if not out:
        return None
    posted = datetime.fromisoformat(report["lastModified"]).astimezone(timezone.utc)
    # The season's total is the mid-mountain plot's, the one the resort quotes as its own.
    return {"LastUpdate": posted.strftime(STAMP), "Resortwide": False,
            "SeasonTotalIn": (out.get("MidMountainArea") or {}).get("SeasonTotalIn"),
            "Report": (snow.get("detail") or "").strip() or None, "Alert": (snow.get("psa") or "").strip() or None,
            **out}


def parse(page: str, now: datetime) -> dict:
    report = json.loads(page)
    lifts = [status_row(lift, None) for lift in (report.get("lifts") or {}).values()]
    trails = [trail_row(trail) for trail in (report.get("trails") or {}).values()]
    counted = (report.get("liftStatus") or {}).get("totalLifts")
    if not lifts or counted != len(lifts):
        raise ValueError(f"the report counts {counted} lifts but {len(lifts)} were read")
    named = (report.get("trailStatus") or {}).get("totalTrails") or 0
    if len(trails) < named:
        raise ValueError(f"the report counts {named} trails but only {len(trails)} were read")
    feed = {"Name": "Jackson Hole", "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": "Jackson Hole", "Lifts": sorted(lifts, key=lambda row: row["Name"]),
                               "Trails": sorted(trails, key=lambda row: row["Name"])}]}
    try:
        snow = snow_report(report)
    except (ValueError, KeyError, TypeError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Jackson Hole: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
