"""Snowriver's lifts and trails, and its snow report, from its mountain report page and its snow and weather page
(snowriver.com/mountain-info/mountain-report and snowriver.com/mountain-info/snow-weather).

Snowriver is a Midwest Family Ski Resorts mountain and its site shares Lutsen's layout, so the reading is Lutsen's
(``lutsen.lift_areas`` and ``lutsen.snow_report``): a section for each part of its two peaks (Black River
Basin's Frontside and Westside, Jackson Creek Summit's Main Face, Bear Creek and The East), each listing its lifts,
its primary runs and its sidecountry runs, with the page's own counts checked against what is read; and the depth
and the snowfall in inches. Snowriver keeps Central time, as Lutsen does, so the snowfall's time is read by
Lutsen's clock. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
from datetime import datetime

from tahoe_snow.sources import lutsen

URLS = {"lifts": "https://www.snowriver.com/mountain-info/mountain-report",
        "snow": "https://www.snowriver.com/mountain-info/snow-weather"}
NAME = "Snowriver"


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(lutsen.STAMP), "MountainAreas": lutsen.lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = lutsen.snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
