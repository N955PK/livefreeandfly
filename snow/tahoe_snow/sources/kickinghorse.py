"""Kicking Horse's lifts and its snow report, from the page its conditions pages are filled from
(kickinghorseresort.com/conditions/snow-report/, filled from kickinghorseresort.com/refresh/refresh.php).

Kicking Horse is a Resorts of the Canadian Rockies mountain; the reading is ``rcr``'s, which says what is read and
what is not (the page gives no status for a run, so there are lifts and no trails). The snow is measured at the
resort's alpine snow plot, at 2,060 m, and the report is dated in Golden's time, which is Alberta's. **The page
reports centimetres; they are converted to inches in ``rcr``.** Standard library only.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from tahoe_snow.sources import rcr

URL = "https://kickinghorseresort.com/refresh/refresh.php"
NAME = "Kicking Horse"
RESORT_TIME = ZoneInfo("America/Edmonton")
# Where the resort measures its snow, in the page's own words.
PLOT = "Alpine Snow Plot"


def parse(page: str, now: datetime) -> dict:
    return rcr.feed(page, now, NAME, RESORT_TIME, PLOT)
