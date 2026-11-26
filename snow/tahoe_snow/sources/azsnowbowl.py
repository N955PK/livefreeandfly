"""Arizona Snowbowl's lifts and trails, and its snow figures, from its conditions page
(www.snowbowl.ski/the-mountain/weather-conditions-webcams/).

Arizona Snowbowl is a Mountain Capital Partners resort; the reading is ``mcp``'s, which says what is read and what
is not. The page groups its trails by the lift that serves them (Arizona Gondola, Grand Canyon Express and so on)
and counts its lifts, which is checked. The snow report is undated, so no time zone is needed. Standard library
only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.snowbowl.ski/the-mountain/weather-conditions-webcams/"
NAME = "Arizona Snowbowl"


def parse(page: str, now: datetime) -> dict:
    return mcp.feed(page, now, NAME)
