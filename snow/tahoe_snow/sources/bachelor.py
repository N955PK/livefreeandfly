"""Mt. Bachelor's lifts and trails, and its snow report, from the reports its own mountain report page reads
(mtbachelor.com/the-mountain/mountain-report).

Mt. Bachelor is run by the company that runs Copper Mountain and Snowbird, and its page is drawn in the browser from
the same three reports on the resort's own API (api.mtbachelor.com/api/v1/dor/drupal): the lifts, the trails and the
snow reports. So the reading of a lift, a trail and the newest snow report is Copper's and Snowbird's. Each lift and
trail names its part of the mountain in capitals (FRONTSIDE, EASTSIDE, WESTSIDE, SUMMIT), which is its mountain area
here, written as a name. The reports also list the summer lifts and the biking and hiking trails, the cross-country,
snowshoe and uphill routes, and the trails Mt. Bachelor marks as not for the status page (its terrain parks among
them); only the winter lifts and the ski trails it shows are kept.

The snow report is written by the resort each morning: one base depth, the new snow overnight, the snowfall of the
last 24, 48 and 72 hours and 7 days, the season's total, the resort's own words, and when it was posted. Snowbird's
reading takes that time as Mountain time; Mt. Bachelor writes it in Pacific time, so it is read again here. It gives
no surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tahoe_snow.sources.copper import SEASONS, SKIED, trail_row
from tahoe_snow.sources.snowbird import listed, snow_report, status_row

API = "https://api.mtbachelor.com/api/v1/dor/drupal"
URLS = {"lifts": f"{API}/lifts", "trails": f"{API}/trails", "snow": f"{API}/snow-reports"}
NAME = "Mt. Bachelor"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")


def area_name(sector: dict) -> str:
    """A part of the mountain as a name: the report writes "FRONTSIDE", and one of them with a space after it."""
    name = sector["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("the report names a part of the mountain with no name")
    return " ".join(name.split()).title()


def pacific_snow_report(reports: list) -> dict | None:
    """The newest snow report, with the time it was posted read as Pacific time. None when there is no report."""
    snow = snow_report(reports)
    if snow is None:
        return None
    try:
        posted = datetime.strptime(max(report["date"] for report in reports), "%Y-%m-%d %H:%M:%S")
    except (KeyError, TypeError) as error:
        raise ValueError(f"the snow report is not in the shape expected: {error!r}") from error
    snow["LastUpdate"] = posted.replace(tzinfo=PACIFIC_TIME).astimezone(timezone.utc).strftime(STAMP)
    return snow


def parse(pages: dict, now: datetime) -> dict:
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
        snow = pacific_snow_report(listed(pages["snow"], "snow"))
    except ValueError as error:
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
