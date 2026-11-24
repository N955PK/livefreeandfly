"""Kimberley's lifts and its snow report, from the page its conditions pages are filled from
(skikimberley.com/conditions/snow-report/, filled from skikimberley.com/refresh/refresh.php).

Kimberley is a Resorts of the Canadian Rockies mountain; the reading is ``rcr``'s, which says what is read and
what is not (the page gives no status for a run, so there are lifts and no trails). The page does not say where
the snow is measured. The report is dated in Kimberley's time, which is Alberta's. **The page reports centimetres;
they are converted to inches in ``rcr``.** Standard library only.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from tahoe_snow.sources import rcr

URL = "https://skikimberley.com/refresh/refresh.php"
NAME = "Kimberley"
RESORT_TIME = ZoneInfo("America/Edmonton")
# Where the resort measures its snow, in the page's own words.
PLOT = "Mountain"


def parse(page: str, now: datetime) -> dict:
    return rcr.feed(page, now, NAME, RESORT_TIME, PLOT)
