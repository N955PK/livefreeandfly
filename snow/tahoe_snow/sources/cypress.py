"""Cypress Mountain's lifts and trails, and its snow report, from the report its own mountain-report page reads
(cypressmountain.com/mountain-report, which asks its own site for /api/reportpal?resortName=cy).

Cypress is Boyne's, and the report is the one Boyne's other mountains give (see boyne.py): an area for each lift,
holding the lift and the trails it serves, and after them the Nordic area's trails, which are left out: the status
is of the lift-served mountain. A lift's or trail's status is the report's own word. The report's own count of
lifts is checked against what is read, so a change in its shape fails instead of showing wrong numbers.

The snow report has a stake at the base (Cypress Base) and one at mid-mountain (Mid Mountain), each with its depth,
the least and most of it, and the snowfall overnight and over 24, 48 and 72 hours and 7 days, and the time the
report was posted. Cypress reports in centimetres: every figure here is the report's centimetres divided by 2.54
and rounded to one decimal, to give the inches the Ikon feed's fields hold. A figure the report leaves empty stays
empty. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone

URL = "https://www.cypressmountain.com/api/reportpal?resortName=cy&useReportPal=true"
NAME = "Cypress Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The report's difficulty icons, in the words the app's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black"}
NOT_ALPINE = {"nordic", "cross country", "snowshoe"}
# The report's snowfall figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"snowOverNight": "OvernightIn", "snow24Hours": "Last24HoursIn", "snow48Hours": "Last48HoursIn",
            "snow72Hours": "Last72HoursIn", "snow7Days": "Last7DaysIn"}
# The report's stakes, by the Ikon feed's names for where they stand.
STAKES = {"Cypress Base": "BaseArea", "Mid Mountain": "MidMountainArea"}
TAG = re.compile(r"<[^>]+>")


def status_row(row: dict, difficulty: str | None) -> dict:
    name, status = row["name"], row["status"]
    if not isinstance(name, str) or not name.strip() or not isinstance(status, str) or not status.strip():
        raise ValueError(f"{name or 'a row'} has no name or no status")
    words = " ".join(status.split()).capitalize()
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    level = trail.get("difficultyIcon") or ""
    if level and level not in LEVELS:
        raise ValueError(f"{trail['name']} has a difficulty the reader does not know: {level}")
    row = status_row(trail, LEVELS.get(level, ""))
    if isinstance(trail.get("groomed"), bool):
        row["Grooming"] = "Yes" if trail["groomed"] else "No"
    return row


def inches(figure) -> float | None:
    """A depth the report gives as {"inches": "12", "centimeters": "30"}, from its centimetres; None where it
    gives nothing."""
    said = figure.get("centimeters") if isinstance(figure, dict) else None
    if said is None or str(said).strip() in ("", "--"):
        return None
    value = float(str(said).strip())
    if value < 0:
        raise ValueError(f"a depth of {said} cm")
    return round(value / CM_PER_INCH, 1)


def stake(place: dict) -> dict:
    area = {"Name": place["name"], "BaseIn": inches(place.get("base")), "BaseMinIn": inches(place.get("baseMin")),
            "BaseMaxIn": inches(place.get("baseMax"))}
    area.update({ikon: inches(place.get(field)) for field, ikon in SNOWFALL.items()})
    return area


def words(markup: str) -> str:
    """The text of a piece of the report's words: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def snow_report(report: dict) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport: the base and mid-mountain stakes."""
    if report.get("units") != "Metric":
        raise ValueError(f"the report's units are {report.get('units')!r}, not metric")
    posted = datetime.strptime(report["updated"], STAMP).strftime(STAMP)
    places = {place.get("name"): place for place in report["currentConditions"]["resortLocations"]["location"]}
    stakes = {ikon: stake(places[name]) for name, ikon in STAKES.items() if name in places}
    if "BaseArea" not in stakes:
        raise ValueError("the report has no stake at the base")
    base = places["Cypress Base"]
    surface = ", ".join(dict.fromkeys(word.strip() for word in (base.get("primarySurface"), base.get("secondarySurface"))
                                      if isinstance(word, str) and word.strip()))
    said = [words(comment.get("text") or "") for comment in (report.get("comments") or {}).get("comment") or []
            if comment.get("name") == "Comment"]
    return {"LastUpdate": posted, "Resortwide": False, "BaseConditions": surface or None,
            "SeasonTotalIn": inches(base.get("snowSeasonTotal")), **stakes,
            "Report": next((text for text in said if text), None), "Alert": None}


def areas_of(report: dict) -> list:
    """One mountain area for each of the report's areas that has a lift or a ski trail."""
    areas = []
    for area in report["facilities"]["areas"]["area"]:
        if "nordic" in area["name"].lower() or "uphill" in area["name"].lower():
            continue
        lifts = [status_row(lift, None) for lift in (area.get("lifts") or {}).get("lift") or []]
        trails = [trail_row(trail) for trail in (area.get("trails") or {}).get("trail") or []
                  if (trail.get("type") or "").lower() not in NOT_ALPINE]
        if lifts or trails:
            areas.append({"Name": area["name"], "Lifts": lifts, "Trails": trails})
    listed = report["currentConditions"]["resortwide"]["numLiftsTotal"]
    found = sum(len(area["Lifts"]) for area in areas)
    if not found:
        raise ValueError("the report lists no lifts")
    if found != listed:
        raise ValueError(f"the report counts {listed} lifts but {found} were read")
    return areas


def parse(page: str, now: datetime) -> dict:
    report = json.loads(page)
    try:
        areas = areas_of(report)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the report is not in the shape the reader knows: {error!r}") from error
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(report)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error!r}")
    return feed
