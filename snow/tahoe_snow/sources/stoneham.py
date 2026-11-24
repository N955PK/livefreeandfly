"""Stoneham's lifts and trails, and its snowfall, from the frame its conditions page loads
(ski-stoneham.com/refresh/refresh.php?lang=en, behind ski-stoneham.com/en/skiing-riding/snow-report/snow-conditions).

Resorts of the Canadian Rockies runs Stoneham and Mont-Sainte-Anne on one page design, and the reading is done by
``rcr_feed`` in Mont-Sainte-Anne's module, which says how: the day's lifts by their tick or dash, the trails by a
status picture whose title is French even on the English page (OUVERT is Open, FERMÉ is Closed; a mark in the
DAMÉES column is groomed), and the page's own counts checked against what is read. Stoneham lists its trails as one
list, a single mountain area here.

The site gives no depth of snow. Its snowfall is in centimetres and is turned into inches (divided by 2.54, to one
decimal). Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources.montsainteanne import rcr_feed

URL = "https://ski-stoneham.com/refresh/refresh.php?lang=en"
NAME = "Stoneham"
# The element holding the day's trails, and the name its trails are shown under.
TRAIL_AREAS = {"trails-day-element": "Trails"}


def parse(page: str, now: datetime) -> dict:
    return rcr_feed(page, now, NAME, TRAIL_AREAS)
