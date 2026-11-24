"""Cranmore's lifts and trails, and its snow report, from its snow report page (cranmore.com/snow-report).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page lists the
lifts in one table, with the tubing park and the summer rides under a heading of their own (left out: the status is
of the lift-served mountain), then the trails in one table under a heading for each kind (Beginner, Intermediate,
Expert, Glades, Terrain Parks). A trail's last column says "groomed" or "natural". The page's own count of lifts is
checked against what is read, and every row of both tables is one read, so a redesign fails instead of showing
wrong numbers.

The snow report is the page's figures above the tables, in the shape of the Ikon feed's snow report: the base depth
(one figure, or a range such as 26-40", carried as its least and most with the middle as the depth), the snow that
fell overnight (carried as OvernightIn, and as the 24-hour figure, which is the nearest the page gives), the 7-day
and season totals, and the resort's own words. Before the season the page gives no figures and they stay empty. The
page dates its report by the day only, so it is stamped at noon Eastern. A figure that does not read as a number
stays empty. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://cranmore.com/snow-report"
# The page's difficulty symbols, in the words the page's difficulty symbols are keyed on; a park has none.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "doubleblack": "Double black"}
EASTERN = ZoneInfo("America/New_York")
ROW = "<div id=\"\\d+\" class=\"row\">"
CELL = "\\s*<div class=\"col\">(.*?)</div>"
LIFTS = re.compile(r"<h2>Lifts</h2>\s*<div class=\"datatable\">(.*?)<h2>Trails</h2>", re.S)
TRAILS = re.compile(r"<h2>Trails</h2>\s*<div class=\"datatable\">(.*?)</section>", re.S)
# The tubing park and the rides follow the lifts under a heading of their own.
NOT_LIFTS = re.compile(r"<div class=\"row\">\s*<h3>")
LIFT_ROW = re.compile(ROW + CELL + CELL, re.S)
GROUP = re.compile(ROW + r"\s*<h3>(.*?)</h3>", re.S)
TRAIL_ROW = re.compile(ROW + CELL * 5, re.S)
LEVEL = re.compile(r"class=\"difficulty\" alt=\"([a-z-]+)\"")
FIGURE = re.compile(r"<h3>(.*?)</h3>\s*<span class=\"value\">(.*?)</span>", re.S)
POSTED = re.compile(r"Last Updated:\s*([A-Z][a-z]{2} \d{1,2}, \d{4})")
WORDS = re.compile(r"Report:(.*?)<br />\s*<div class=\"conditions\">", re.S)
DEPTH = re.compile(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*(?:\"|”|in\.?|inches)?")
# The page's snowfall figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"overnight": "OvernightIn", "7 day total": "Last7DaysIn"}


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = (text_of(status) or "Closed").capitalize()
    return {"Name": text_of(name), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(name: str, status: str, night: str, symbol: str, surface: str) -> dict:
    level = LEVEL.search(symbol)
    row = status_row(name, status, LEVELS.get(level.group(1), "") if level else "")
    row["Grooming"] = "Yes" if "groomed" in text_of(surface).lower() else "No"
    return row


def number(value: float) -> float | int:
    return int(value) if value.is_integer() else value


def depth(said: str) -> tuple:
    """A depth as the page writes it (30", or the range 26-40"): the depth, its least and its most. A range's depth
    is its middle; one figure has no least or most. Nothing where it does not read as a number."""
    figure = DEPTH.fullmatch(text_of(said))
    if not figure:
        return None, None, None
    low = float(figure.group(1))
    if figure.group(2) is None:
        return number(low), None, None
    high = float(figure.group(2))
    return number((low + high) / 2), number(low), number(high)


def snow_report(page: str) -> dict | None:
    """The page's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain. None when the
    page does not date its report."""
    posted = POSTED.search(page)
    if not posted:
        return None
    day = datetime.strptime(posted.group(1), "%b %d, %Y").replace(hour=12, tzinfo=EASTERN)
    figures = {text_of(label).lower(): value for label, value in FIGURE.findall(page)}
    base, least, most = depth(figures.get("base depth", ""))
    area = {"Name": "Mountain", "BaseIn": base, "BaseMinIn": least, "BaseMaxIn": most, "Last24HoursIn": None}
    area.update({ikon: depth(figures.get(label, ""))[0] for label, ikon in SNOWFALL.items()})
    area["Last24HoursIn"] = area["OvernightIn"]
    words = WORDS.search(page)
    return {"LastUpdate": day.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": depth(figures.get("season total", ""))[0], "BaseArea": area,
            "Report": (words.group(1).strip() if words else "") or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, trails = LIFTS.search(page), TRAILS.search(page)
    if not lifts or not trails:
        raise ValueError("the page's lift and trail tables were not found")
    chairs = NOT_LIFTS.split(lifts.group(1))[0]
    rows = [status_row(name, state, None) for name, state in LIFT_ROW.findall(chairs)]
    if not rows:
        raise ValueError("the page lists no lifts")
    # Every row of the lift table above the rides is one lift read, and the page's own count agrees.
    listed = len(re.findall(ROW, chairs))
    if len(rows) != listed:
        raise ValueError(f"the page lists {listed} lift rows but {len(rows)} lifts were read")
    count = re.search(r"<h3>Open Lifts</h3>\s*<span class=\"value\">\s*\d+\s*/\s*(\d+)\s*</span>", page)
    if not count:
        raise ValueError("the page's count of lifts was not found")
    if int(count.group(1)) != len(rows):
        raise ValueError(f"the page counts {count.group(1)} lifts but {len(rows)} were read")
    parts = GROUP.split(trails.group(1))
    areas = [{"Name": text_of(name), "Lifts": [], "Trails": [trail_row(*cells) for cells in TRAIL_ROW.findall(body)]}
             for name, body in zip(parts[1::2], parts[2::2])]
    # Every row of the trail table is a heading or one trail read, so a change in its shape fails.
    listed = len(re.findall(ROW, trails.group(1))) - len(areas)
    found = sum(len(area["Trails"]) for area in areas)
    if not found:
        raise ValueError("the page lists no trails")
    if found != listed:
        raise ValueError(f"the page lists {listed} trail rows but {found} trails were read")
    feed = {"Name": "Cranmore", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Cranmore", "Lifts": rows, "Trails": []}, *areas]}
    snow = snow_report(page)
    if snow:
        feed["SnowReport"] = snow
    return feed
