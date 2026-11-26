"""Red River's lifts and trails, and its snow report, from its snow report page
(redriverskiarea.com/winter/winter-mountain/snow-report/).

The page is built on the server, by the same report maker as Waterville Valley's, so the reading of a lift, a trail
and a depth is ``waterville``'s. The report lists the lifts, then the trails under their difficulty (Easier, More
Difficult, Most Difficult), then the glades and the terrain parks; it does not divide the mountain into parts, so the
trails are one area, and the glades and the parks an area each. Each lift and trail carries its status in words
(Open, Closed, Closed for Event), and a trail may carry a groomed mark after it. Every lift and trail on the page is
one read, a heading the reader does not know fails, and the page's own counts of its lifts and of its trails (which
leave out the glades and the parks) have to match, so a change in its shape fails instead of dropping runs.

The snow report gives the base depth as a least and a most ("10 - 16"): both are carried, with the middle of the two
as the one figure. It gives the snowfall of the last 24 and 72 hours and the season's total, the primary surface,
and the time it was updated, in Mountain time (``MOUNTAIN_TIME``). A snow report that cannot be read costs only the
snow report, not the lifts. Standard library only.
"""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tahoe_snow.sources.waterville import MEASURE, SECTION, rows_of, span, text_of

URL = "https://www.redriverskiarea.com/winter/winter-mountain/snow-report/"
NAME = "Red River"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The headings the trails are listed under, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easier": "Green", "more difficult": "Blue", "most difficult": "Black"}
# The headings that are an area of their own, with no difficulty, and are not in the page's count of trails.
APART = {"glades": "Glades", "terrain parks": "Terrain Parks"}
COMMENT = re.compile(r"<!--.*?-->", re.S)
UPDATED = re.compile(r"<dt>\s*Updated\s*</dt>\s*<dd>(.*?)</dd>", re.S)
SURFACE = re.compile(r"<dl class=\"SnowReport-measure\" id=\"PrimarySurface\">\s*<dt>.*?</dt>\s*<dd>(.*?)</dd>", re.S)
COUNTED = r"<h2 class=\"h5\">{} Open</h2>\s*<dl[^>]*>\s*<dd>\s*<span[^>]*>\d+</span>\s*of\s*<span[^>]*>(\d+)</span>"


def counted(page: str, what: str) -> int | None:
    """The page's own count of its lifts or its trails ("2 of 7"), where it gives one."""
    read = re.search(COUNTED.format(what), page)
    return int(read.group(1)) if read else None


def posted(page: str) -> str:
    """When the report was updated ("07:49 AM, November 25, 2026", in Mountain time)."""
    read = UPDATED.search(page)
    if not read:
        raise ValueError("the time the report was updated was not found")
    try:
        when = datetime.strptime(text_of(read.group(1)), "%I:%M %p, %B %d, %Y").replace(tzinfo=MOUNTAIN_TIME)
    except ValueError as error:
        raise ValueError(f"the time the report was updated does not read: {text_of(read.group(1))!r}") from error
    return when.astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    measures = {text_of(label).lower(): text_of(value) for label, value in MEASURE.findall(page)}
    if "base depth" not in measures or "last 24 hours" not in measures:
        raise ValueError("the report's snowfall and base depth were not found")
    area = {"Name": "Mountain", **span(measures["base depth"], "Base"),
            "Last24HoursIn": span(measures["last 24 hours"], "Last24Hours")["Last24HoursIn"],
            "Last72HoursIn": span(measures.get("last 72 hours"), "Last72Hours")["Last72HoursIn"]}
    surface = SURFACE.search(page)
    return {"LastUpdate": posted(page), "Resortwide": True,
            "BaseConditions": text_of(surface.group(1)) or None if surface else None,
            "SeasonTotalIn": span(measures.get("season total"), "SeasonTotal")["SeasonTotalIn"], "BaseArea": area,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    listed = len(re.findall(r"<article class=\"SnowReport-(?:Trail|Lift)\b", page))
    page = COMMENT.sub("", page)
    lifts, trails, apart = [], [], {}
    for kind, title, body in SECTION.findall(page):
        title = text_of(title).lower()
        if kind == "lifts":
            lifts += rows_of(body, None, False)
        elif title in LEVELS:
            trails += rows_of(body, LEVELS[title], True)
        elif title in APART:
            apart.setdefault(APART[title], []).extend(rows_of(body, "", True))
        else:
            raise ValueError(f"the report lists trails under a heading the reader does not know: {title!r}")
    if not lifts or not trails:
        raise ValueError("the report lists no lifts or no trails")
    # Every lift and trail in the report is one read, so a change in its shape fails instead of dropping runs.
    found = len(lifts) + len(trails) + sum(len(rows) for rows in apart.values())
    if found != listed:
        raise ValueError(f"the report lists {listed} lifts and trails but {found} were read")
    for what, rows in (("Lifts", lifts), ("Trails", trails)):
        count = counted(page, what)
        if count is not None and count != len(rows):
            raise ValueError(f"the report counts {count} {what.lower()} but {len(rows)} were read")
    areas = [{"Name": NAME, "Lifts": lifts, "Trails": trails}]
    areas += [{"Name": name, "Lifts": [], "Trails": rows} for name, rows in apart.items()]
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
