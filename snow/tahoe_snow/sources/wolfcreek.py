"""Wolf Creek's snow report, from its snow report page (wolfcreekski.com/wcs-snow-report, where wolfcreekski.com/snow
leads).

The page is built on the server and holds the ski patrol's newest report as pairs of a label and a figure: the snow
depth at the summit and at midway, the snowfall of the latest storm, of the last 24, 48 and 72 hours and 7 days and
of the year to date, in inches, the surface in the patrol's words, how much of the mountain is open and how many
lifts are running, under a line saying when it was updated, in Mountain time.

Wolf Creek's site does not list its lifts or its trails by name anywhere, only how many lifts are running, so this
gives no lift or trail statuses: the mountain areas are empty, and the count of lifts running is carried in the snow
report as the Ikon feed carries it (``TotalOpenLifts``). The midway stake is given as the base area and the summit
stake as the summit area; the snowfall is the mountain's, and is written beside the midway depth. A page without
the report, or with a depth or a date that does not read, fails instead of giving wrong numbers. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://wolfcreekski.com/wcs-snow-report/"
NAME = "Wolf Creek"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The report's snowfall labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 hours": "Last24HoursIn", "48 hours": "Last48HoursIn", "72 hours": "Last72HoursIn",
            "7 days": "Last7DaysIn", "Latest Storm": "StormTotalIn"}
REPORT = re.compile(r"class=\"ct-div-block snow-report-parent\"(.*?)class=\"ct-div-block snow-report-footer-div\"", re.S)
UPDATED = re.compile(r"Updated:\s*([A-Z][a-z]{2} \d{1,2}, \d{4}) - (\d{1,2}:\d{2})")
PAIR = re.compile(r"class=\"ct-text-block snow-report-left-text\"[^>]*>((?:(?!</div>).)*)</div>\s*"
                  r"<div[^>]*class=\"ct-text-block snow-report-right-text\"[^>]*>((?:(?!</div>).)*)</div>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|″|”)")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(said: dict, label: str) -> float | int | None:
    """A figure of the report in inches; None where the report does not have the label."""
    if label not in said:
        return None
    figure = INCHES.fullmatch(said[label])
    if not figure:
        raise ValueError(f"the report's {label} reads {said[label]!r}, not inches")
    value = float(figure.group(1))
    return int(value) if value.is_integer() else value


def count(said: dict, label: str) -> int | None:
    figure = re.fullmatch(r"(\d+)\s*%?", said.get(label, ""))
    return int(figure.group(1)) if figure else None


def snow_report(page: str) -> dict:
    """The patrol's report in the shape of the Ikon feed's SnowReport: the midway and the summit stakes."""
    report = REPORT.search(page)
    if not report:
        raise ValueError("the snow report was not found")
    updated = UPDATED.search(words(report.group(1)))
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    try:
        at = datetime.strptime(f"{updated.group(1)} {updated.group(2)}", "%b %d, %Y %H:%M")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    said = {}
    for label, figure in PAIR.findall(report.group(1)):
        if words(label) in said:
            raise ValueError(f"the report gives {words(label)} twice")
        said[words(label)] = words(figure)
    midway, summit = inches(said, "Midway Snow Depth"), inches(said, "Summit Snow Depth")
    if midway is None or summit is None or "24 hours" not in said:
        raise ValueError("the snow report has no midway or summit depth, or no 24 hour snowfall")
    snowfall = {ikon: inches(said, label) for label, ikon in SNOWFALL.items() if label in said}
    storm = snowfall.pop("StormTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=MOUNTAIN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": False, "BaseConditions": said.get("Surface Conditions") or None,
            "SeasonTotalIn": inches(said, "Snowfall YTD"), "StormTotalIn": storm,
            "TotalOpenLifts": count(said, "Number of Lifts"), "OpenTerrainPercent": count(said, "Percentage Open"),
            "BaseArea": {"Name": "Midway", "BaseIn": midway, **snowfall},
            "SummitArea": {"Name": "Summit", "BaseIn": summit}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    return {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": [], "SnowReport": snow_report(page)}
