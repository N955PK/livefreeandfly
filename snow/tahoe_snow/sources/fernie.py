"""Fernie's lifts and its snow report, from the page its conditions pages are filled from
(skifernie.com/conditions/snow-report/, filled from skifernie.com/refresh/refresh.php).

Fernie is a Resorts of the Canadian Rockies mountain; the reading is ``rcr``'s, which says what is read and what
is not (the page gives no status for a run, so there are lifts and no trails). The snow is measured at the resort's
Bear weather plot, at 1,615 m, and the report is dated in Fernie's time, which is Alberta's. **The page reports
centimetres; they are converted to inches in ``rcr``.** Standard library only.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from tahoe_snow.sources import rcr

URL = "https://skifernie.com/refresh/refresh.php"
NAME = "Fernie"
RESORT_TIME = ZoneInfo("America/Edmonton")
# Where the resort measures its snow, in the page's own words.
PLOT = "Bear Weather Plot"


def parse(page: str, now: datetime) -> dict:
    return rcr.feed(page, now, NAME, RESORT_TIME, PLOT)
