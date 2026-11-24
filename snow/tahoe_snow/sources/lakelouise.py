"""Lake Louise's lifts and runs, and its snow report, from the report its own lift, runs and parks status page
reads (skilouise.com/explore-winter/winter-ski-ride/lift-runs-parks-status).

The status page is a frame drawn in the browser from one XML report (ski-louise-status-page.vercel.app/api/ski-data),
which is read here. The report lists the mountain by area (Front Side, Back Bowls, Larch, Richardson's Ridge, West
Bowl), each with its lifts and its runs; an area with neither (the on-mountain dining) is left out, and so are the
terrain and tube parks, which the report keeps apart from the runs and does not count among them. A lift or a run
is open or closed in the report's ``status``, and a word the reader does not know fails. (Each also carries a
``realtime`` word that says closed for every one, open lifts included; the resort's page does not read it and
neither does this.) A run's difficulty and whether it is groomed are the report's own words. The report's own
count of open lifts and of open runs is checked against what is read, so a change in its shape fails instead of
showing wrong numbers.

The snow report is in the same file: a base depth and the snowfall overnight and of the last 24 and 48 hours and
7 days at the lower, the middle and the upper mountain, of which only the places with a base are kept (the middle
has been empty). The resort's snow conditions page shows the same two sets of figures, calling the lower one "Mid
Mountain". The season's snowfall is the highest place's. The report says when the snow report was updated, with
its distance from UTC. **The report is in centimetres; they are converted to inches here (divided by 2.54, to one
decimal).** A report in another unit fails. A snow report that cannot be read costs only the snow report, not the
lifts. Standard library only.
"""
from datetime import datetime, timezone
from xml.etree import ElementTree

URL = "https://ski-louise-status-page.vercel.app/api/ski-data"
NAME = "Lake Louise"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
STATUSES = {"open": "Open", "closed": "Closed"}
# The report's difficulty words, in the words the app's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black"}
GROOMED = {"yes": "Yes", "no": "No"}
# The report's places, lowest first, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Lower Mountain": "BaseArea", "Mid-Mountain": "MidMountainArea", "Upper Mountain": "SummitArea"}
# A place's snowfall, by the names the Ikon feed gives it.
SNOWFALL = {"snowOverNight": "OvernightIn", "snow24Hours": "Last24HoursIn", "snow48Hours": "Last48HoursIn",
            "snow7Days": "Last7DaysIn"}


def status_row(row, difficulty: str | None) -> dict:
    """One lift or run: open or closed, in the report's own word."""
    name, said = (row.get("name") or "").strip(), (row.get("status") or "").strip()
    if not name or said.lower() not in STATUSES:
        raise ValueError(f"{name or 'a lift or a run'} has a status the reader does not know: {said!r}")
    status = STATUSES[said.lower()]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(trail) -> dict:
    level, groomed = trail.get("difficulty"), trail.get("groomed")
    if level not in LEVELS:
        raise ValueError(f"{trail.get('name')} has a difficulty the reader does not know: {level!r}")
    if groomed not in GROOMED:
        raise ValueError(f"{trail.get('name')} has a grooming the reader does not know: {groomed!r}")
    row = status_row(trail, LEVELS[level])
    row["Grooming"] = GROOMED[groomed]
    return row


def mountain_areas(report) -> list:
    """The report's areas that have a lift or a run. A lift listed under two areas is kept under the first."""
    areas, seen = [], set()
    for area in report.findall("./facilities/areas/area"):
        lifts = []
        for lift in area.findall("./lifts/lift"):
            if lift.get("id") not in seen:
                seen.add(lift.get("id"))
                lifts.append(status_row(lift, None))
        trails = [trail_row(trail) for trail in area.findall("./trails/trail")]
        if lifts or trails:
            areas.append({"Name": (area.get("name") or "").strip() or NAME, "Lifts": lifts, "Trails": trails})
    return areas


def checked(areas: list, report) -> list:
    """The areas, once the report's own count of open lifts and open runs agrees with what was read."""
    counted = report.find("./currentConditions/liftsAndRuns")
    if counted is None:
        raise ValueError("the report's count of open lifts and runs was not found")
    for kind, attribute, what in (("Lifts", "lifts", "lifts"), ("Trails", "runs", "runs")):
        rows = [row for area in areas for row in area[kind]]
        opened = sum(row["StatusEnglish"] == "open" for row in rows)
        if not rows or str(opened) != (counted.get(attribute) or "").strip():
            raise ValueError(f"the report counts {counted.get(attribute)} open {what} but {opened} of {len(rows)} "
                             "were read")
    return areas


def inches(said: str | None) -> float | None:
    """A figure of the report's centimetres in inches, to one decimal, or None where the report gives none."""
    said = (said or "").strip()
    if not said:
        return None
    try:
        return round(float(said) / CM_PER_INCH, 1)
    except ValueError as error:
        raise ValueError(f"the snow report has a figure that is not a number: {said!r}") from error


def snow_report(report) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport: a set for each place with a base."""
    if report.get("units") != "metric":
        raise ValueError(f"the report is in {report.get('units')!r} units, not metric")
    stakes, season, surface = {}, None, None
    for place in report.findall("./currentConditions/resortLocations/location"):
        name = (place.get("name") or "").strip()
        if name not in STAKES:
            raise ValueError(f"the snow report has a place the reader does not know: {name!r}")
        base = inches(place.get("base"))
        if base is None:
            continue
        fallen = {field: inches(place.get(attribute)) for attribute, field in SNOWFALL.items()}
        stakes[STAKES[name]] = {"Name": name, "BaseIn": base,
                                **{field: value for field, value in fallen.items() if value is not None}}
        # The places run from the lowest up, so the last with a figure is the highest.
        season = inches(place.get("snowYearToDate")) if place.get("snowYearToDate") else season
        surface = (place.get("primarySurface") or "").strip() or surface
    if not stakes or not any("Last24HoursIn" in stake for stake in stakes.values()):
        raise ValueError("the snow report has no base or no 24 hour snowfall")
    resortwide = report.find("./currentConditions/resortwide")
    posted = resortwide.get("lastSnowfallUpdate") if resortwide is not None else None
    try:
        at = datetime.fromisoformat(posted or "")
    except ValueError as error:
        raise ValueError(f"the snow report does not say when it was updated: {posted!r}") from error
    if at.tzinfo is None:
        raise ValueError(f"the snow report's time gives no distance from UTC: {posted!r}")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": False,
            "BaseConditions": surface, "SeasonTotalIn": season, **stakes, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    try:
        report = ElementTree.fromstring(page.encode("utf-8"))
    except ElementTree.ParseError as error:
        raise ValueError(f"the report does not read as XML: {error}") from error
    if report.tag != "report":
        raise ValueError(f"the report is a {report.tag}, not the mountain's report")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": checked(mountain_areas(report), report)}
    try:
        feed["SnowReport"] = snow_report(report)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
