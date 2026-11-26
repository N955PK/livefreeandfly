"""Mt. Hood Meadows' lifts and its snow report, from the two reports its own conditions page reads
(skihood.com/mountain-report).

The page is drawn in the browser from the resort's own site: its points of interest (skihood.com/api/weather/poi),
a list of sectors of which "Lifts" holds the lifts, and its report (skihood.com/api/weather/report), which holds the
snow at the base area and at mid-mountain, the resort's notes and the day's written report. A lift's status is one
of the words the page's script colours green, yellow or red: the green ones are given as open, the red ones as
closed, and the yellow ones (a delay, a stop, a lift expected later) are carried in the report's words; a status
the script does not know fails. The report counts the lifts open, pending and closed, and that count has to match
the lifts read, so a change in its shape fails instead of showing wrong numbers. The page's grooming report marks
trails only as groomed, never as open or closed, so no trails are given.

Before the season the "Lifts" sector holds no lifts and the page shows no lift card; the mountain is then given
with no lifts rather than with statuses nobody posted. A report without the "Lifts" sector fails.

The snow report gives, for each of the two zones, the depth, the overnight snow and the snowfall of the last 24,
48 and 72 hours and 7 days in inches, and when it was last changed; the season's total is the base area's. The
surface is the resort's "Surface Conditions" note and the written report is its "Today's Report". A snow report
that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone

SITE = "https://www.skihood.com/api/weather"
URLS = {"lifts": f"{SITE}/poi?include=Nordic%20Center,Lifts,Parking%20Lots,Access%20Gates,TERRAIN_PARKS",
        "snow": f"{SITE}/report?includeResortInfo=true&includeSnowInfo=true"}
NAME = "Mt. Hood Meadows"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
SECTOR = "Lifts"
# The statuses the page's script draws with a green tick, a red cross and a yellow pause.
OPEN = {"OPEN", "OPEN_DOWNHILL_ONLY", "OPEN_PEDESTRIAN_ONLY"}
CLOSED = {"CLOSED", "CLOSED_CONTEST", "OUT_OF_PERIOD", "OUT_OF_PERIOD_SEASON_BEGINNING", "OUT_OF_PERIOD_SEASON_ENDING"}
PENDING = {"FORECAST", "FORECAST_AURORA_SKI", "FORECAST_NIGHT_SKI", "DELAYED", "DELAYED_SECURING",
           "DELAYED_TECHNICAL_ISSUE", "DELAYED_WEATHER", "DELAYED_WIND", "STOPPED", "STOPPED_SECURING",
           "STOPPED_TECHNICAL_ISSUE", "STOPPED_WEATHER", "STOPPED_WIND"}
# The report's snow zones, by the names the Ikon feed gives its stakes (the app reads those).
ZONES = {"Base Area": "BaseArea", "Mid-Mountain": "MidMountainArea"}
# A zone's figures, by the names the Ikon feed gives them.
FIGURES = {"snowTotalDepth": "BaseIn", "freshSnowFallDepth24H": "Last24HoursIn",
           "freshSnowFallDepth48H": "Last48HoursIn", "freshSnowFallDepth72H": "Last72HoursIn",
           "freshSnowFallDepth7D": "Last7DaysIn", "overnight": "OvernightIn"}
SEASON = "snowFallDepthCompleteSeason"
TAG = re.compile(r"<[^>]+>")


def loaded(page: str, what: str) -> dict:
    try:
        report = json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the {what} report does not read as JSON: {error}") from error
    if not isinstance(report, dict):
        raise ValueError(f"the {what} report is not an object")
    return report


def words(markup: str) -> str:
    """The text of one of the resort's notes: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_row(lift: dict) -> dict:
    name, status = lift["name"], lift["openingStatusCompl"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the report lists a lift with no name")
    if status in OPEN:
        said = "Open"
    elif status in CLOSED:
        said = "Closed"
    elif status in PENDING:
        said = status.replace("_", " ").capitalize()
    else:
        raise ValueError(f"{name.strip()} has a status the reader does not know: {status!r}")
    return {"Name": name.strip(), "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}


def lifts_of(report: dict) -> list:
    """The lifts of the "Lifts" sector; none when the sector holds none, as before the season."""
    try:
        sectors = [sector for sector in report["data"] if sector.get("name") == SECTOR]
        if len(sectors) != 1:
            raise ValueError(f"the report has {len(sectors)} sectors named {SECTOR}, not one")
        lifts = [lift_row(lift) for lift in sectors[0].get("lifts") or []]
        counts = [count for count in report["counters"] if count["name"] == SECTOR]
        counted = sum(count[state] for count in counts for state in ("open", "pending", "closed"))
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the lift report is not in the shape expected: {error!r}") from error
    # Before the season the report has no count of lifts at all, which reads as none.
    if counted != len(lifts):
        raise ValueError(f"the report counts {counted} lifts but {len(lifts)} were read")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the report lists a lift twice")
    return lifts


def inches(zone: dict, field: str) -> float | int:
    figure = zone[field]
    value = figure["countryValue"]
    if figure["countryUnit"] != "INCH" or isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{zone['name']}'s {field} reads {value!r} {figure['countryUnit']}, not inches")
    return int(value) if float(value).is_integer() else value


def note(notes: list, title: str) -> str | None:
    """The resort's note of that title in plain words, or None when it has none."""
    for each in notes:
        if each.get("title") == title and each.get("data"):
            return words(each["data"][0]["data"]) or None
    return None


def snow_report(report: dict) -> dict:
    """The report's snow zones in the shape of the Ikon feed's SnowReport: the base area and mid-mountain."""
    try:
        data = report["data"]
        zones = {zone["name"]: zone for zone in data["snow"]["snowZones"]}
        if "Base Area" not in zones:
            raise ValueError("the snow report has no base area")
        changed = max(datetime.fromisoformat(zone["lastModified"]) for zone in zones.values() if zone["name"] in ZONES)
        if changed.tzinfo is None:
            raise ValueError("the snow report does not say what time zone it was changed in")
        snow = {"LastUpdate": changed.astimezone(timezone.utc).strftime(STAMP), "Resortwide": False,
                "BaseConditions": note(data["resort"]["resortInfos"], "Surface Conditions"),
                "SeasonTotalIn": inches(zones["Base Area"], SEASON)}
        for name, ikon in ZONES.items():
            if name in zones:
                snow[ikon] = {"Name": name, **{figure: inches(zones[name], field) for field, figure in FIGURES.items()}}
        snow["Report"] = note(data["weather"]["weatherSkyInfos"], "Today's Report")
        snow["Alert"] = None
        return snow
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError(f"the snow report is not in the shape expected: {error!r}") from error


def parse(pages: dict, now: datetime) -> dict:
    lifts = lifts_of(loaded(pages["lifts"], "lift"))
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(loaded(pages["snow"], "snow"))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
