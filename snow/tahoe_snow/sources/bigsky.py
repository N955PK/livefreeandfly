"""Big Sky's lifts and trails, and its snow report, from the report its own current-conditions page reads
(bigskyresort.com/current-conditions, which bigskyresort.com/lift-status leads to).

Big Sky is Boyne's, and its page reads one report from its own site (/api/reportpal?resortName=bs), the code being
the one the page itself names, so the reading of an area, a lift, a trail and the snow report is the one the other
Boyne mountains use (``boyne``): one mountain area per area of the report, the report's own count of lifts checked
against what is read, and one depth for the whole mountain with the snowfall of the last 24, 48 and 72 hours and
7 days, the resort's own words and when it was posted. Big Sky rates its trails in six steps, two more than the
other Boyne mountains: an advanced intermediate trail (its blue-black) is carried as a blue and a high exposure
trail (its triple black) as a double black, the nearest of the page's four symbols. A rating the reader does not
know fails. Standard library only.
"""
import json
from datetime import datetime

from tahoe_snow.sources import boyne

URL = "https://www.bigskyresort.com/api/reportpal?resortName=bs&useReportPal=true"
NAME = "Big Sky"
# Big Sky's ratings, as the ratings the Boyne reader knows.
RATINGS = {"beginner": "beginner", "intermediate": "intermediate", "advanced-intermediate": "intermediate",
           "advanced": "advanced", "expert": "expert", "high-exposure": "expert"}


def rated(report: dict) -> dict:
    """The report with each trail's rating written as one of the four the Boyne reader knows."""
    for area in report["facilities"]["areas"]["area"]:
        for trail in (area.get("trails") or {}).get("trail") or []:
            rating = trail.get("difficultyIcon")
            if rating not in RATINGS:
                raise ValueError(f"{trail['name']} has a rating the reader does not know: {rating}")
            trail["difficultyIcon"] = RATINGS[rating]
    return report


def parse(page: str, now: datetime) -> dict:
    try:
        report = json.loads(page)
    except ValueError as error:
        raise ValueError(f"the report does not read as JSON: {error}") from error
    if not isinstance(report, dict) or report.get("name") != NAME:
        raise ValueError("the report is not Big Sky's")
    try:
        feed = boyne.parse(NAME, rated(report), now)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Trails"] for area in feed["MountainAreas"]):
        raise ValueError("the report lists no trails")
    return feed
