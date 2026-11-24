"""Powder Mountain's lifts and trails, and its snow report, from the report its own conditions page reads
(powdermountain.com/conditions).

The page reads one file of JSON from its own site (/api/conditions). Its status lists the lifts and trails by part
of the mountain (a "sector"), and each is a mountain area here; a sector with neither is left out. A status is one
of the report's codes, said in the words the resort's page gives it (OPEN "Open", STOPPED "On-hold", FORECAST
"Expected"); a lift or trail out of its season ("out of period") is said as closed, and a code the page has no
words for is carried as it stands. A trail's level the reader does not know fails. Grooming is carried only where
the report says one way or the other. The report's counts of lifts and trails leave some of the list out (surface
lifts, gates), so the list is only required to hold at least that many.

The snow report is the resort's one plot, in inches: the depth, the overnight, 24, 48 and 72 hour and 7 day
snowfall, the season's total and when it was last changed. A figure not given in inches fails. The surface is
given only when the resort names one. Standard library only.
"""
import json
from datetime import datetime, timezone

URL = "https://powdermountain.com/api/conditions"
NAME = "Powder Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The report's status codes, in the words the resort's own page gives them. A lift or trail out of its season is
# closed.
STATUSES = {"CLOSED": "Closed", "CLOSED_CONTEST": "Closed Contest", "DELAYED": "Delayed",
            "DELAYED_SECURING": "Delayed Securing", "DELAYED_TECHNICAL_ISSUE": "Delayed Technical Issue",
            "DELAYED_WEATHER": "Delayed Weather", "DELAYED_WIND": "Delayed Wind", "FORECAST": "Expected",
            "FORECAST_AURORA_SKI": "Expected Aurora Ski", "FORECAST_NIGHT_SKI": "Expected Night Ski", "OPEN": "Open",
            "OPEN_DOWNHILL_ONLY": "Open Downhill Only", "OPEN_PEDESTRIAN_ONLY": "Open Pedestrian Only",
            "OUT_OF_PERIOD": "Closed", "OUT_OF_PERIOD_SEASON_BEGINNING": "Closed",
            "OUT_OF_PERIOD_SEASON_ENDING": "Closed", "STOPPED": "On-hold", "STOPPED_SECURING": "On-hold Securing",
            "STOPPED_TECHNICAL_ISSUE": "On-hold Technical Issue", "STOPPED_WEATHER": "On-hold Weather",
            "STOPPED_WIND": "On-hold Wind", "PARTIAL": "Partial"}
# The report's trail levels, in the words the app's difficulty symbols are keyed on. Terrain parks and some gates
# have none.
LEVELS = {"GREEN_CIRCLE": "Green", "BLUE_SQUARE": "Blue", "DOUBLE_BLUE_SQUARE": "Blue", "BLACK_DIAMOND": "Black",
          "BLACK": "Black", "DOUBLE_BLACK_DIAMOND": "Double black", "TERRAIN_PARKS": "", "UNDEF": ""}
GROOMED = {"GROOMED": "Yes", "MORNING_GROOMED": "Yes", "EVENING_GROOMED": "Yes", "NOT_GROOMED": "No"}
# The plot's snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"snowTotalDepth": "BaseIn", "overnight": "OvernightIn", "freshSnowFallDepth24H": "Last24HoursIn",
            "freshSnowFallDepth48H": "Last48HoursIn", "freshSnowFallDepth72H": "Last72HoursIn",
            "freshSnowFallDepth7D": "Last7DaysIn"}
DAILY_REPORT = "Daily Report"


def status_row(item: dict, difficulty: str | None) -> dict:
    code, name = item.get("openingStatus"), (item.get("name") or "").strip()
    if not code or not name:
        raise ValueError(f"a lift or trail has no name or no status: {item}")
    status = STATUSES.get(code, code)
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail.get("trailLevel") not in LEVELS:
        raise ValueError(f"{trail.get('name')} has a level the reader does not know: {trail.get('trailLevel')}")
    row = status_row(trail, LEVELS[trail["trailLevel"]])
    if trail.get("groomingStatus") in GROOMED:
        row["Grooming"] = GROOMED[trail["groomingStatus"]]
    return row


def inches(figure) -> float | int | None:
    """A snow figure in inches, or None where the report gives none."""
    if not isinstance(figure, dict) or figure.get("countryValue") is None:
        return None
    value = figure["countryValue"]
    if figure.get("countryUnit") != "INCH" or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"a snow figure reads {value!r} {figure.get('countryUnit')}, not a number of inches")
    return int(value) if float(value).is_integer() else value


def daily_report(conditions: dict) -> str | None:
    """The words of the resort's daily report, as the page prints them."""
    for note in conditions.get("resortData") or []:
        if note.get("title") == DAILY_REPORT:
            return next((said.get("data") for said in note.get("data") or [] if said.get("data")), None)
    return None


def snow_report(conditions: dict) -> dict | None:
    """The plot's figures in the shape of the Ikon feed's SnowReport, for the whole mountain. None when the report
    has no plot."""
    plot = conditions.get("currentSnow")
    if not plot:
        return None
    area = {"Name": "Mountain", **{ikon: inches(plot.get(field)) for field, ikon in SNOWFALL.items()}}
    if area["BaseIn"] is None:
        raise ValueError("the plot gives no depth")
    posted = datetime.fromisoformat(plot["lastModified"]).astimezone(timezone.utc)
    quality = plot.get("snowQuality")
    surface = quality.replace("_", " ").capitalize() if quality and quality != "UNDEF" else None
    return {"LastUpdate": posted.strftime(STAMP), "Resortwide": True, "BaseConditions": surface,
            "SeasonTotalIn": inches(plot.get("snowFallDepthCompleteSeason")), "BaseArea": area,
            "Report": daily_report(conditions), "Alert": None}


def parse(page: str, now: datetime) -> dict:
    report = json.loads(page)
    status = report.get("status") if isinstance(report, dict) else None
    if not isinstance(status, dict) or not isinstance(status.get("sectorsData"), list):
        raise ValueError("the report has no status by part of the mountain")
    try:
        areas = [{"Name": sector["name"].strip(), "Lifts": [status_row(lift, None) for lift in sector.get("lifts") or []],
                  "Trails": [trail_row(trail) for trail in sector.get("trails") or []]}
                 for sector in status["sectorsData"]]
        lifts_counted = status["liftsOverall"]["lifts"]
        trails_counted = status["trailsOverall"]["trailsInPeriode"]
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the report's status is not in the shape expected: {error!r}") from error
    areas = [area for area in areas if area["Lifts"] or area["Trails"]]
    lifts, trails = (sum(len(area[kind]) for area in areas) for kind in ("Lifts", "Trails"))
    # The report's own counts leave some of its list out, so they are a floor: a list shorter than its count has
    # changed shape.
    if not lifts or lifts < lifts_counted:
        raise ValueError(f"the report counts {lifts_counted} lifts but {lifts} were read")
    if trails < trails_counted:
        raise ValueError(f"the report counts {trails_counted} trails but only {trails} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        snow = snow_report(report.get("conditions") or {})
    except (ValueError, KeyError, TypeError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
