"""Canaan Valley's lifts, and its snow report, from its trail report page (canaanresort.com/trail-report).

The page is built on the server. Its "Lifts Open" list is each lift's name and its status in words (Closed, Open),
carried as the page says it, and the page's own count of lifts, open and in all ("0/6"), has to match what is
read, so a change in the page's shape fails instead of showing wrong numbers. The two lifts of the tube park are
counted with the rest and then left out: the status is of the lift-served ski area. The lifts are one mountain
area. The page's tables of trails were empty when this was written ("Trails are Closed for the Season", "Trails
Open: 0/0"), so the shape of a trail's row is not known and no trails are read; the mountain is given lifts only.

The page says when it was last updated, in Eastern time. The resort leaves its last report up through the summer
and autumn, so a page more than OLD_DAYS old that still has a lift open is refused: its statuses are last
season's. The conditions give the base depth, as one depth or a low and a high, the snowfall of the last 24 hours,
of the storm and of the season, in inches, and the surface in words; out of season they are dashes, which reads
as no snow report. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.canaanresort.com/trail-report"
NAME = "Canaan Valley"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/New_York")
# A page older than this with a lift open is last season's, left up after the mountain closed.
OLD_DAYS = 14
# The lifts that are not of the lift-served ski area.
LEFT_OUT = frozenset({"Tubing Lift"})
# The conditions' lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Snowfall (Last 24 hrs)": "Last24HoursIn", "Snowfall (Storm Total)": "StormTotalIn"}
UPDATED = re.compile(r"<div class=\"last-updated\">\s*Last Updated:\s*([A-Z][a-z]+ \d{1,2}, \d{4}), "
                     r"(\d{1,2}:\d{2}\s*[ap]m)\s*</div>")
LIFTS = re.compile(r"<div class=\"lifts\">\s*<h3>\s*Lifts Open:\s*(\d+)\s*/\s*(\d+)\s*</h3>\s*<ul>(.*?)</ul>", re.S)
# A drawing stands between a lift's name and its status.
LIFT = re.compile(r"<li>\s*<span class=\"name\">(.*?)</span>\s*(?:<svg\b.*?</svg>\s*)?<span class=\"status\">(.*?)"
                  r"</span>\s*</li>", re.S)
CONDITIONS = re.compile(r"<section id=\"conditions\"[^>]*>(.*?)</section>", re.S)
LINE = re.compile(r"<li>\s*<span>(.*?)</span>(.*?)</li>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\"|in(?:ches)?\.?)?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?\s*(?:-|–)\s*(\d+(?:\.\d+)?)\s*(?:″|”|\"|in(?:ches)?\.?)?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def updated(page: str) -> datetime:
    """When the page says it was last updated."""
    said = UPDATED.search(page)
    if not said:
        raise ValueError("the page does not say when it was last updated")
    try:
        at = datetime.strptime(f"{said.group(1)} {''.join(said.group(2).split())}", "%B %d, %Y %I:%M%p")
    except ValueError as error:
        raise ValueError(f"the page's date could not be read: {error}") from error
    return at.replace(tzinfo=LOCAL_TIME)


def lift_rows(page: str) -> list:
    """The ski area's lifts, checked with the tube park's against the page's own count."""
    listed = LIFTS.search(page)
    if not listed:
        raise ValueError("the page's lifts were not found")
    rows = []
    for name, said in LIFT.findall(listed.group(3)):
        name, status = words(name), words(said).capitalize()
        if not name or not status or not status.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a lift'} has the status {status!r}, not a word")
        rows.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    read = sum(row["StatusEnglish"] == "open" for row in rows), len(rows)
    if not rows or read != (int(listed.group(1)), int(listed.group(2))) or len(rows) != listed.group(3).count("<li"):
        raise ValueError(f"the page counts {listed.group(1)} of {listed.group(2)} lifts open but {read[0]} of "
                         f"{read[1]} were read")
    return [row for row in rows if row["Name"] not in LEFT_OUT]


def snow_report(page: str, at: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    conditions = CONDITIONS.search(page)
    if not conditions:
        raise ValueError("the conditions were not found")
    said = {words(label): words(value) for value, label in LINE.findall(conditions.group(1))}
    depth, area = said.get("Base Depth", ""), {"Name": "Mountain"}
    if RANGE.fullmatch(depth):
        low, high = (number(end) for end in RANGE.fullmatch(depth).groups())
        if low > high:
            raise ValueError(f"the base depth runs from {low} down to {high}")
        area.update({"BaseMinIn": low, "BaseMaxIn": high})
    elif INCHES.fullmatch(depth):
        area["BaseIn"] = number(INCHES.fullmatch(depth).group(1))
    else:
        raise ValueError(f"the base depth reads {depth!r}, not inches")
    for label, field in SNOWFALL.items():
        inches = INCHES.fullmatch(said.get(label, ""))
        area[field] = number(inches.group(1)) if inches else None
    storm = area.pop("StormTotalIn")
    season = INCHES.fullmatch(said.get("Snowfall (Season Total)", ""))
    surface = said.get("Primary Surface", "")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": surface if any(letter.isalpha() for letter in surface) else None,
            "SeasonTotalIn": number(season.group(1)) if season else None, "StormTotalIn": storm, "BaseArea": area,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, at = lift_rows(page), updated(page)
    if not lifts:
        raise ValueError("the page lists no lifts of the ski area")
    if now - at > timedelta(days=OLD_DAYS) and any(lift["StatusEnglish"] == "open" for lift in lifts):
        raise ValueError(f"the page was last updated {at:%Y-%m-%d} and has lifts open: it is last season's")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(page, at)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
