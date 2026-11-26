"""Pajarito's lifts and trails, and its snow figures, from its conditions page
(www.pajarito.ski/weather-conditions-webcams/lifts-and-trails/).

Pajarito is a Mountain Capital Partners resort; the reading is ``mcp``'s, which says what is read and what is not.
The page groups its trails by the lift that serves them, and lists a trail again under each lift that reaches it; it
is kept under the first. The snow report is undated, so no time zone is needed. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.pajarito.ski/weather-conditions-webcams/lifts-and-trails/"
NAME = "Pajarito"


def parse(page: str, now: datetime) -> dict:
    return mcp.feed(page, now, NAME)
