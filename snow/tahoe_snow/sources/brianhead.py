"""Brian Head's lifts and trails, and its snow figures, from its conditions page
(www.brianhead.com/weather-conditions-webcams/).

Brian Head is a Mountain Capital Partners resort; the reading is ``mcp``'s, which says what is read and what is not.
The page groups its trails by the chair that serves them ("Giant Steps Express, Chair 2"); a trail listed under a
second chair is kept only under the first. It does not count its lifts. The snow report is undated, so no time zone
is needed. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.brianhead.com/weather-conditions-webcams/"
NAME = "Brian Head"


def parse(page: str, now: datetime) -> dict:
    return mcp.feed(page, now, NAME)
