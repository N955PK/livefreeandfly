"""Copper Mountain's lifts and trails, and its snow report, from the reports its own snow report page reads
(coppercolorado.com/the-mountain/conditions-weather/snow-report).

The page is drawn in the browser from three reports on the resort's own API (api.coppercolorado.com/api/v1/dor/drupal),
the same kind Snowbird's page reads, so the reading of a row, a figure and the newest snow report is Snowbird's: the
lifts, the trails and the snow reports. Each lift and trail names its part of the mountain (Center, East, West, Union
Peak, Copper Bowl and so on), which is its mountain area here. The trail report also lists the summer biking and
hiking trails, the uphill and cross-country routes and the trails Copper marks as not for the status page; only the
winter ski trails and terrain parks it shows are kept. A trail's difficulty the reader does not know fails.

The snow report is written by the resort each morning: one base depth, the new snow overnight, the snowfall of the
last 24, 48 and 72 hours and 7 days, the season's total, the resort's own words, and when it was posted, in Mountain
time. It gives no surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
from datetime import datetime

from tahoe_snow.sources.snowbird import listed, snow_report, status_row

API = "https://api.coppercolorado.com/api/v1/dor/drupal"
URLS = {"lifts": f"{API}/lifts", "trails": f"{API}/trails", "snow": f"{API}/snow-reports"}
NAME = "Copper Mountain"
SEASONS = {"winter", "all"}
SKIED = {"alpine_trail", "terrain_park_trail"}
# The report's difficulty words, in the words the page's difficulty symbols are keyed on. One trail has none.
LEVELS = {"easiest": "Green", "more_difficult": "Blue", "most_difficult": "Black", "extreme": "Double black",
          "extreme_terrain": "Double black", "N/A": ""}
GROOMED = {"groomed": "Yes", "not_groomed": "No"}


def trail_row(trail: dict) -> dict:
    if trail["difficulty"] not in LEVELS:
        raise ValueError(f"{trail['name']} has a difficulty the reader does not know: {trail['difficulty']}")
    if trail["groom_status"] not in GROOMED:
        raise ValueError(f"{trail['name']} has a grooming the reader does not know: {trail['groom_status']}")
    row = status_row(trail["name"], trail["status"], LEVELS[trail["difficulty"]])
    row["Grooming"] = GROOMED[trail["groom_status"]]
    return row


def parse(pages: dict, now: datetime) -> dict:
    lifts, trails = listed(pages["lifts"], "lift"), listed(pages["trails"], "trail")
    areas = {}
    try:
        for lift in lifts:
            if lift["season"] in SEASONS:
                area = areas.setdefault(lift["sector"]["name"], {"Name": lift["sector"]["name"], "Lifts": [], "Trails": []})
                area["Lifts"].append(status_row(lift["name"], lift["status"], None))
        for trail in trails:
            if trail["season"] in SEASONS and trail["type"] in SKIED and trail["include"] is True:
                area = areas.setdefault(trail["sector"]["name"], {"Name": trail["sector"]["name"], "Lifts": [], "Trails": []})
                area["Trails"].append(trail_row(trail))
    except (KeyError, TypeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Lifts"] for area in areas.values()):
        raise ValueError("the report lists no lifts")
    if not any(area["Trails"] for area in areas.values()):
        raise ValueError("the report lists no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": list(areas.values())}
    try:
        snow = snow_report(listed(pages["snow"], "snow"))
    except ValueError as error:
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
