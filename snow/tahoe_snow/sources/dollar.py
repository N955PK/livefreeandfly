"""Dollar Mountain's lifts and trails, and its snow report, from Sun Valley's mountain report page
(sunvalley.com/the-mountain/mountain-report).

Dollar Mountain is Sun Valley's second mountain, across the valley from Bald Mountain, and the one page holds both,
each under a tab of its own. The reading is the ``sunvalley`` module's; this gives Dollar Mountain's tabs under its
own key. Its tab of the snow report gives no base depth, so the depth stays empty. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import sunvalley

URL = sunvalley.URL


def parse(page: str, now: datetime) -> dict:
    return sunvalley.parse(page, now, "dollar")
