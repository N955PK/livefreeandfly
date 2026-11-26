"""Granite Peak's lifts and trails, and its snow report, from its mountain report page and its snow and weather
page (skigranitepeak.com/mountain-info/mountain-report and skigranitepeak.com/mountain-info/snow-weather).

Granite Peak is a Midwest Family Ski Resorts mountain, as Lutsen is, and its pages are made of Lutsen's pieces, so
a run's row, the page's counts and the snow report are read by Lutsen's reader. What differs is the mountain
report's shape: it has a section for each lift, whose heading is the lift's name with its status as an icon, over
the runs that lift serves. Each lift is a mountain area here, holding itself and its runs. A run that several
lifts serve is listed under each of them on the page and once here, under the first, and its statuses there have
to agree. A lift's status icon is named for the status (open, closed, projected, on-hold), said as Lutsen's are:
Projected, the page's word for a lift it expects to open, is Expected. The page sometimes gives a lift a bare
number where the name should be (its own record number for a status, with no word): that lift is carried as
Unknown instead of guessing. Every lift and run in the page is one read, and the page's own counts of lifts and of
primary and sidecountry runs together ("0/7", "0/62" and "0/9") have to match what is read, so a change in the
page's shape fails instead of showing wrong numbers.

The snow and weather page gives the depth and the snowfall in inches under a day and time in Central time, read
as Lutsen's is. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import re
from datetime import datetime

from tahoe_snow.sources import lutsen

URLS = {"lifts": "https://www.skigranitepeak.com/mountain-info/mountain-report",
        "snow": "https://www.skigranitepeak.com/mountain-info/snow-weather"}
NAME = "Granite Peak"
# What a lift is said to be where the page gives a number in place of its status.
UNWORDED = "Unknown"
SECTION = "<details>"
LIFT = re.compile(r"<summary[^>]*>\s*<div class=\"component-row lift-title\">\s*<div class=\"cell icon-cell status\">"
                  r"\s*<div class=\"f-icon icon-([a-z0-9-]+)\"\s*title=\"([^\"]*)\">\s*</div>\s*</div>(.*?)</div>\s*"
                  r"</summary>(.*?)</details>", re.S)
HEADINGS = ("Trails",)
TRAIL_ROW = "class=\"node node--type-trail node--view-mode-row\""


def lift_row(icon: str, said: str, name: str) -> dict:
    """A lift with the status its icon is named for."""
    if not name:
        raise ValueError("a lift has no name")
    if icon != "-".join(said.lower().split()):
        raise ValueError(f"{name}'s status icon is {icon} and reads {said!r}")
    if icon.isdigit():
        status = UNWORDED
    elif icon in lutsen.STATUSES:
        status = lutsen.STATUSES[icon]
    else:
        raise ValueError(f"{name}'s status icon is {icon}, not one the reader knows")
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def lift_areas(page: str) -> list:
    """Each lift with the runs it serves, in the page's order."""
    stats = lutsen.STATS.search(page)
    if not stats:
        raise ValueError("the page's counts of lifts and trails were not found")
    counted = {lutsen.words(label): int(total) for label, _, total in lutsen.COUNT.findall(stats.group(1))}
    areas, seen, rows = [], {}, 0
    for section in page.split(SECTION)[1:]:
        lift = LIFT.match(section)
        if not lift:
            raise ValueError("a section of the report is not a lift, its status and its runs")
        icon, said, name, body = lift.groups()
        area = {"Name": lutsen.words(name), "Lifts": [lift_row(icon, said, lutsen.words(name))], "Trails": []}
        headings = tuple(lutsen.words(heading) for heading in lutsen.HEADING.findall(body))
        if headings != HEADINGS:
            raise ValueError(f"{area['Name']} has lists the reader does not know: {list(headings)}")
        for kind, row in lutsen.NODE.findall(body + "</details>"):
            if kind != "trail":
                raise ValueError(f"{area['Name']} lists a {kind} among its runs")
            trail = lutsen.row_of(kind, row)
            rows += 1
            if trail["Name"] not in seen:
                seen[trail["Name"]] = trail
                area["Trails"].append(trail)
            elif seen[trail["Name"]] != trail:
                raise ValueError(f"{trail['Name']} is listed under two lifts with different statuses")
        areas.append(area)
    if not areas or len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists no lifts, or one twice")
    if counted.get("Lifts") != len(areas):
        raise ValueError(f"the page counts {counted.get('Lifts')} lifts but {len(areas)} were read")
    listed = counted.get("Primary Trails", 0) + counted.get("Sidecountry Trails", 0)
    if not rows or rows != page.count(TRAIL_ROW) or rows != listed:
        raise ValueError(f"the page counts {listed} trails and has {page.count(TRAIL_ROW)} rows but {rows} were read")
    return areas


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(lutsen.STAMP), "MountainAreas": lift_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = lutsen.snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
