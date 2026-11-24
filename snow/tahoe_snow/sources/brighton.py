"""Brighton's lifts and trails, and its snow report, from the report its own conditions page reads
(brightonresort.com/conditions).

Brighton is one of Boyne's mountains and its site is built like the others': the conditions page reads one report
from its own site (/api/reportpal?resortName=br, "br" being the code the page itself names). The report has the
same shape as Sugarloaf's or Loon's, so it is read by the same reader (``boyne.parse``): one mountain area per lift
with the trails it serves, the report's own count of lifts checked against what is read, and the snow report (base
depth, new snow, surface and the time it was posted) in the shape of the Ikon feed's. A report that is not
Brighton's, or not in that shape, fails instead of giving wrong numbers. Standard library only.
"""
import json
from datetime import datetime

from tahoe_snow.sources import boyne

URL = "https://www.brightonresort.com/api/reportpal?resortName=br&useReportPal=true"
NAME = "Brighton"


def parse(page: str, now: datetime) -> dict:
    try:
        report = json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the report does not read as JSON: {error}") from error
    if not isinstance(report, dict) or report.get("name") != NAME:
        raise ValueError("the report is not Brighton's")
    if report.get("units") != "USC":
        raise ValueError(f"the report's units are {report.get('units')}, not inches")
    try:
        return boyne.parse(NAME, report, now)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
