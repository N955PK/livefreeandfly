"""Boyne Mountain's lifts and trails, and its snow report, from the report its own mountain-report page reads
(www.boynemountain.com/mountain-report).

Boyne Mountain is Boyne's, and its page reads one report from its own site (/api/reportpal?resortName=bm), the code
being the one the page itself names, so the reading of an area, a lift, a trail and the snow report is the one the
other Boyne mountains use (``boyne``): the report has one area, the whole mountain, the report's own count of lifts
is checked against what is read, and there is one depth for the whole mountain with the snowfall of the last 24, 48
and 72 hours and 7 days, the season's total, the surface, the resort's own words and when it was posted. The time
it was posted is written in UTC, so the reader needs no time zone. A rating the Boyne reader does not know
fails. Standard library only.
"""
import json
from datetime import datetime

from tahoe_snow.sources import boyne

URL = "https://www.boynemountain.com/api/reportpal?resortName=bm&useReportPal=true"
NAME = "Boyne Mountain"
# The name the report gives itself.
REPORT_NAME = "Boyne Mountain"


def known(report: dict) -> dict:
    """The report, once every trail in it has one of the four ratings the Boyne reader knows."""
    for area in report["facilities"]["areas"]["area"]:
        for trail in (area.get("trails") or {}).get("trail") or []:
            rating = trail.get("difficultyIcon")
            if rating not in boyne.LEVELS:
                raise ValueError(f"{trail['name']} has a rating the reader does not know: {rating}")
    return report


def parse(page: str, now: datetime) -> dict:
    try:
        report = json.loads(page)
    except ValueError as error:
        raise ValueError(f"the report does not read as JSON: {error}") from error
    if not isinstance(report, dict) or report.get("name") != REPORT_NAME:
        raise ValueError(f"the report is not {NAME}'s")
    try:
        feed = boyne.parse(NAME, known(report), now)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Trails"] for area in feed["MountainAreas"]):
        raise ValueError("the report lists no trails")
    return feed
