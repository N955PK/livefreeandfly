"""Eldora's lifts and trails, and its snow report, from the reports its own trail and lift status page reads
(www.eldora.com/the-mountain/current-conditions/trail-lift-status/).

Eldora is run by the company that runs Copper Mountain, Snowbird and Mt. Bachelor, and its page is drawn in the
browser from the same three reports on the resort's own API (api.eldora.com/api/v1/dor/drupal): the lifts, the trails
and the snow reports. So the reading of a lift, a trail and the newest snow report is Copper's and Snowbird's. Each
lift and trail names its part of the mountain (Little Hawk, Challenge Mountain, Corona, Indian Peaks), which is its
mountain area here. The trail report also lists the Nordic centre's cross-country trails and the uphill routes, which
Eldora marks as not for the status page; only the ski trails it shows are kept.

The snow report is written by the resort each morning: one base depth, the new snow overnight, the snowfall of the
last 24, 48 and 72 hours and 7 days, the season's total, the resort's own words, and when it was posted. Eldora
writes that time in Mountain time, which is how Snowbird's reading takes it; the reader checks that the two zones
are one. It gives no surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from tahoe_snow.sources import snowbird
from tahoe_snow.sources.copper import SEASONS, SKIED, trail_row
from tahoe_snow.sources.snowbird import listed, snow_report, status_row

API = "https://api.eldora.com/api/v1/dor/drupal"
URLS = {"lifts": f"{API}/lifts", "trails": f"{API}/trails", "snow": f"{API}/snow-reports"}
NAME = "Eldora"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
ZONE = ZoneInfo("America/Denver")


def area_name(sector: dict) -> str:
    """A part of the mountain by its name, which has to be there."""
    name = sector["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the report names a part of the mountain with no name")
    return " ".join(name.split())


def parse(pages: dict, now: datetime) -> dict:
    if snowbird.MOUNTAIN != ZONE:
        raise ValueError("the snow report's time would be read in a zone that is not Eldora's")
    lifts, trails = listed(pages["lifts"], "lift"), listed(pages["trails"], "trail")
    areas = {}
    try:
        for lift in lifts:
            if lift["season"] in SEASONS:
                name = area_name(lift["sector"])
                area = areas.setdefault(name, {"Name": name, "Lifts": [], "Trails": []})
                area["Lifts"].append(status_row(lift["name"], lift["status"], None))
        for trail in trails:
            if trail["season"] in SEASONS and trail["type"] in SKIED and trail["include"] is True:
                name = area_name(trail["sector"])
                area = areas.setdefault(name, {"Name": name, "Lifts": [], "Trails": []})
                area["Trails"].append(trail_row(trail))
    except (KeyError, TypeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Lifts"] for area in areas.values()):
        raise ValueError("the report lists no lifts")
    if not any(area["Trails"] for area in areas.values()):
        raise ValueError("the report lists no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        snow = snow_report(listed(pages["snow"], "snow"))
    except ValueError as error:
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
