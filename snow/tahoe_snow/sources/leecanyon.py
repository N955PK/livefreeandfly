"""Lee Canyon's lifts and trails, and its snow figures, from its lifts and trails page
(www.leecanyonlv.com/lifts-and-trails/).

Lee Canyon is a Mountain Capital Partners resort; the reading of a lift, a trail and a figure is ``mcp``'s, which
says what is read and what is not.
The page groups its trails by the lift that serves them (Rabbit Peak, Bluebird, Sherwood and so on) and counts its
lifts and its trails, which are both checked. After the lifts' groups it lists its uphill travel routes, below and
above the lift-served terrain, as two more groups whose rows carry no difficulty: they are not ski trails and are
not in the page's own count, so their rows are taken out before the page is read and their groups left out after.
A lift that is not built or not yet open keeps the words the page gives it in its name ("West Bowl Coming in
December").

The row of snow figures has the snowfall of the last 24 and 48 hours and the season's total but no base depth, so
the depth stays empty. The snow report is undated, so no time zone is needed. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
from datetime import datetime

from tahoe_snow.sources import mcp

URL = "https://www.leecanyonlv.com/lifts-and-trails/"
NAME = "Lee Canyon"
# The start of the name of a group of routes that no lift serves.
UPHILL = "Uphill Travel"


def without_uphill(page: str) -> str:
    """The page with the rows of its uphill travel groups taken out, the groups themselves left empty."""
    start = mcp.TRAIL_LIST.search(page)
    if not start:
        raise ValueError("the list of trails was not found")
    head, *groups = page[start.end():].split(mcp.GROUP)
    kept = []
    for group in groups:
        name = mcp.LIFT_NAME.search(group)
        if name and mcp.words(name.group(1)).startswith(UPHILL):
            group = mcp.TRAIL.sub("", group)
        kept.append(group)
    return page[:start.end()] + mcp.GROUP.join([head] + kept)


def snow_report(page: str) -> dict:
    """The page's snow figures, with the base depth the page does not give left empty."""
    said = mcp.figures(page)
    said.setdefault("base depth", "")
    return mcp.snow_report(said)


def parse(page: str, now: datetime) -> dict:
    lifts = mcp.lift_rows(page)
    if not lifts:
        raise ValueError("the page lists no lifts")
    groups = [area for area in mcp.trail_areas(without_uphill(page)) if not area["Name"].startswith(UPHILL)]
    trails = sum(len(area["Trails"]) for area in groups)
    try:
        said = mcp.figures(page)
    except ValueError:
        said = {}
    for what, read in (("lifts", len(lifts)), ("trails", trails)):
        counted = mcp.COUNT.fullmatch(said.get(f"{what} open", ""))
        if counted and int(counted.group(2)) != read:
            raise ValueError(f"the page counts {counted.group(2)} {what} but {read} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(mcp.STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}] + groups}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
