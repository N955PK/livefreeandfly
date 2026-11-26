"""Willamette Pass's lifts and trails, and its snow figures, from its conditions page
(www.willamettepass.ski/weather-conditions-webcams/).

Willamette Pass is a Mountain Capital Partners resort; the reading is ``mcp``'s, which says what is read and what is
not. The page groups its trails by part of the mountain (Frontside, Backside, Sleepy Hollow Beginner Area) and
counts its lifts, which is checked. The snow report is undated, so no time zone is needed. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.willamettepass.ski/weather-conditions-webcams/"
NAME = "Willamette Pass"


def parse(page: str, now: datetime) -> dict:
    return mcp.feed(page, now, NAME)
