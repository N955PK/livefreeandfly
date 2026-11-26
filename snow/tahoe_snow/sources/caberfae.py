"""Caberfae Peaks' lifts and trails, and its snow report, from its snow report page (caberfaepeaks.com/snow-report).

The page is built on the server. Under "LIFT STATUS" and "TRAIL STATUS" it lists each lift and each trail by name
beside an icon, and the icon is the status: the site's icon font's check mark for open and its cross for closed.
The page says no more than that of a lift or a trail, so a status is Open or Closed, and an icon that is neither
fails. The trails stand in three lists, which the site's stylesheet colours green, blue and black; the page
itself does not say which is which, so a trail is given no difficulty. The names are carried as the page writes
them, in capitals. The lifts and the trails are one mountain area. The page's own counts of lifts and of slopes,
open and in all ("LIFTS OPEN – 0/5", "SLOPES OPEN – 0/27"), have to match what is read, so a change in the page's
shape or in what its icons mean fails instead of showing wrong numbers.

The snow report is a small table: the base depth, the snowfall of the last 24, 48 and 72 hours and of the season,
in inches, and the surface in words, under the day it was written ("Today's Date: NOVEMBER 25, 2026"), which is
read as noon of that day in Eastern time. A snow report that cannot be read costs only the snow report, not the
lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://caberfaepeaks.com/snow-report/"
NAME = "Caberfae Peaks"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Detroit")
# The icons beside a lift or a trail, by their place in the site's icon font ("check" and "cancel").
ICONS = {"": "Open", "": "Closed"}
# The snow table's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 HOUR SNOWFALL": "Last24HoursIn", "48 HOUR SNOWFALL": "Last48HoursIn",
            "72 HOUR SNOWFALL": "Last72HoursIn"}
HEADING = r"<h2 class='av-special-heading-tag'[^>]*>\s*{said}\s*</h2>"
ITEM = re.compile(r"<li>\s*<div class='iconlist_icon [^']*'>\s*<span class='iconlist-char'[^>]*\sdata-av_icon='([^']*)'"
                  r"\s+data-av_iconfont='([^']*)'>\s*</span>\s*</div>.*?<h4 class='av_iconlist_title[^']*'[^>]*>"
                  r"(.*?)</h4>", re.S)
LISTED = "class='iconlist_icon "
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
LINE = re.compile(r"([A-Z0-9 ]+?)\s*(?:–|-|:)\s*(.*)")
COUNT = re.compile(r"(\d+)\s*/\s*(\d+)")
WRITTEN = re.compile(r"Today(?:’|')s Date:\s*([A-Za-z]+ \d{1,2}, \d{4})")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?\s*(?:-|–)\s*(\d+(?:\.\d+)?)\s*(?:″|”|\")")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def rows_of(page: str) -> tuple:
    """The lifts and the trails: the items listed under each of the page's two headings."""
    lifts_at, trails_at = (re.search(HEADING.format(said=said), page) for said in ("LIFT STATUS", "TRAIL STATUS"))
    if not lifts_at or not trails_at or trails_at.start() < lifts_at.end():
        raise ValueError("the lift status and the trail status were not found")
    found = []
    for body, difficulty in ((page[lifts_at.end():trails_at.start()], None), (page[trails_at.end():], "")):
        rows = []
        for icon, font, name in ITEM.findall(body):
            icon, name = html.unescape(icon), words(name)
            if not name:
                raise ValueError("a lift or a trail has no name")
            if font != "entypo-fontello" or icon not in ICONS:
                raise ValueError(f"{name}'s icon is {icon!r} of {font}, not one the reader knows")
            rows.append({"Name": name, "Status": ICONS[icon], "StatusEnglish": ICONS[icon].lower(),
                         "Difficulty": difficulty})
        if not rows or len(rows) != body.count(LISTED):
            raise ValueError(f"the page lists {body.count(LISTED)} lifts or trails under a heading but {len(rows)} "
                             "were read")
        found.append(rows)
    return tuple(found)


def lines(page: str) -> dict:
    """The snow table's cells, each a label and what it says ("SNOW BASE – 0″")."""
    found = {}
    for cell in CELL.findall(page):
        line = LINE.fullmatch(words(cell))
        if line:
            found.setdefault(line.group(1), line.group(2))
    return found


def checked(rows: list, said: dict, label: str) -> None:
    count = COUNT.fullmatch(said.get(label, ""))
    read = sum(row["StatusEnglish"] == "open" for row in rows), len(rows)
    if not count or (int(count.group(1)), int(count.group(2))) != read:
        raise ValueError(f"the page's {label.lower()} reads {said.get(label)!r} but {read[0]} of {read[1]} were read")


def snow_report(page: str, said: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    written = WRITTEN.search(html.unescape(page))
    if not written:
        raise ValueError("the snow report does not say when it was written")
    try:
        at = datetime.strptime(written.group(1).title(), "%B %d, %Y").replace(hour=12, tzinfo=LOCAL_TIME)
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    depth, area = said.get("SNOW BASE", ""), {"Name": "Mountain"}
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
    if area["Last24HoursIn"] is None:
        raise ValueError(f"the 24 hour snowfall reads {said.get('24 HOUR SNOWFALL')!r}, not inches")
    season = INCHES.fullmatch(said.get("YTD SNOWFALL", ""))
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": said.get("SURFACE") or None, "SeasonTotalIn": number(season.group(1)) if season else None,
            "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, trails = rows_of(page)
    said = lines(page)
    checked(lifts, said, "LIFTS OPEN")
    checked(trails, said, "SLOPES OPEN")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
    try:
        feed["SnowReport"] = snow_report(page, said)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
