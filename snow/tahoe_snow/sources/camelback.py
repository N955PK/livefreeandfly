"""Camelback's lifts and trails, and its snow report, from the report its snow report page shows
(conditions.camelbackresort.com/conditions/snow-report/, framed by camelbackresort.com/snow-report-conditions).

The report is the same kind Waterville Valley's is, built on the server by the same software, so Waterville's
reader reads it: the lifts in one section and the trails under their difficulty (Easiest, More Difficult, Most
Difficult, Expert Only), each with its status in words, with the new snow, the base depth, the season's total, the
surface and the time it was posted, which is Eastern time at both mountains. Only the mountain's name differs.

The page also counts its open lifts ("3 Lifts"). Out of season it has been seen counting none while four lifts were
still marked open from the spring, with every trail closed: a page that counts no lifts open and marks some open is
refused instead of showing lifts turning on a closed mountain. Standard library only.
"""
import re
from datetime import datetime

from tahoe_snow.sources import waterville

URL = "https://conditions.camelbackresort.com/conditions/snow-report/"
NAME = "Camelback"
OPEN_LIFTS = re.compile(r"<dt>\s*Open Lifts\s*</dt>\s*<dd>\s*(\d+)\s+Lifts?\s*</dd>")


def parse(page: str, now: datetime) -> dict:
    feed = waterville.parse(page, now)
    if feed["MountainAreas"][0]["Name"] != waterville.NAME:
        raise ValueError("the report's first area is not the whole mountain")
    counted = OPEN_LIFTS.search(page)
    if not counted:
        raise ValueError("the page's count of open lifts was not found")
    marked = sum(lift["StatusEnglish"] == "open" for lift in feed["MountainAreas"][0]["Lifts"])
    if marked and not int(counted.group(1)):
        raise ValueError(f"the page counts no lifts open but marks {marked} open")
    feed["Name"] = feed["MountainAreas"][0]["Name"] = NAME
    return feed
