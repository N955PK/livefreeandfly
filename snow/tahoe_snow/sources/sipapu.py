"""Sipapu's lifts and trails, and its snow figures, from its conditions page
(www.sipapu.ski/snow-report/).

Sipapu is a Mountain Capital Partners resort; the reading is ``mcp``'s, which says what is read and what is not.
The page lists its trails as one group, "Trails". The snow report is undated, so no time zone is needed. Standard
library only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.sipapu.ski/snow-report/"
NAME = "Sipapu"


def parse(page: str, now: datetime) -> dict:
    return mcp.feed(page, now, NAME)
