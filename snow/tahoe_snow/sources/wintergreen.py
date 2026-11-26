"""Wintergreen's lifts and trails, and its snow report, from its mountain report page
(wintergreenresort.com/mountain-report-cams).

Wintergreen is a Pacific Group Resorts mountain and its site shares Wisp's layout, so the reading is Wisp's
(``wisp.feed``): a table of the lifts, a table of runs under a heading for each lift (Potato Patch, Blue Ridge
Express, Big Acorn, Highlands, Loggers Alley), and the snow figures, blank before the mountain opens. The table
under "Tubing" is left out: the status is of the lift-served mountain. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import wisp

URL = "https://www.wintergreenresort.com/mountain-report-cams/"
NAME = "Wintergreen"
# The headings over tables that are not of the lift-served mountain.
LEFT_OUT = frozenset({"Tubing"})


def parse(page: str, now: datetime) -> dict:
    return wisp.feed(page, now, NAME, LEFT_OUT)
