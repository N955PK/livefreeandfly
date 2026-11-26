"""Dodge Ridge's lifts and trails from the two pieces its lift status page asks its own site for, and its
snowfall from its snow report page (dodgeridge.com/lift-status and dodgeridge.com/snow-report).

The lift status page is empty until its script asks the site's ``admin-ajax.php`` for the lifts
(``action=fetch_lift_data``) and the trails (``action=fetch_trail_data``); each answer is a piece of a page, and
the site gives the same answer to a plain GET, which is what is asked here. A lift is its name, its status in a
word ("open", "closed") and its type. A trail is a difficulty symbol (a green circle, a blue square, a black
diamond or a double black diamond; a symbol the reader does not know fails), its name, its status and the part of
the mountain it is on (Upper Mountain, Lower Mountain, Backside), each part a mountain area here; the lifts name no
part and are an area of their own. A status other than open or closed is carried in the site's own words. Every
lift and trail in an answer has to be read, so a change in its shape fails instead of showing wrong numbers. The
site says nothing of grooming.

The snow report page gives the snowfall of the last 24 and 72 hours and the season's total, in inches, and no
base depth. **It is dated by hand, as a day with no year or time ("November 25 update:")**: the year is taken to be
the one that puts the day nearest before the time of reading, and the time to be the start of that day in Pacific
time. A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URLS = {"lifts": "https://dodgeridge.com/wp-admin/admin-ajax.php?action=fetch_lift_data",
        "trails": "https://dodgeridge.com/wp-admin/admin-ajax.php?action=fetch_trail_data",
        "snow": "https://dodgeridge.com/snow-report/"}
NAME = "Dodge Ridge"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
# The difficulty symbols' file names, in the words the app's difficulty symbols are keyed on; parks have none.
LEVELS = {"green_circle": "Green", "blue_square": "Blue", "black_diamond": "Black",
          "double_black_diamond": "Double black", "terrain_park": ""}
# The snow report's figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 hrs": "Last24HoursIn", "72 hrs": "Last72HoursIn", "Season Total": "SeasonTotalIn"}
LIFT = re.compile(r"<div class=\"lift\">\s*<span[^>]*>\s*<img[^>]*>\s*<div class=\"lift-details\">\s*"
                  r"<p class=\"lift-name\">(.*?)</p>\s*<p class=\"lift-status\">(.*?)</p>", re.S)
TRAIL = re.compile(r"<div class=\"trail\">\s*<span[^>]*>\s*<img src=\"[^\"]*/difficulty_icons/([\w-]+)\.png\"[^>]*>\s*"
                   r"<div class=\"trail-details\">\s*<p class=\"trail-name\">(.*?)</p>\s*"
                   r"<p class=\"trail-status\">(.*?)</p>\s*<p class=\"trail-area\">Area:(.*?)</p>", re.S)
FIGURE = re.compile(r"<div[^>]*>(" + "|".join(SNOWFALL) + r")</div>\s*<div[^>]*>([^<]*)</div>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")")
DATED = re.compile(r">\s*([A-Z][a-z]+)\.? (\d{1,2})(?:st|nd|rd|th)? update:?\s*<", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in the site's words."""
    if not name or not said:
        raise ValueError("a lift or a trail has no name or no status")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def lift_rows(piece: str) -> list:
    if "class=\"ski-resort-lifts\"" not in piece:
        raise ValueError("the site's answer for the lifts is not its list of lifts")
    lifts = [status_row(words(name), words(said), None) for name, said in LIFT.findall(piece)]
    listed = piece.count("class=\"lift\"")
    if not lifts or len(lifts) != listed or len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError(f"the site lists {listed} lifts but {len(lifts)} were read, or one twice")
    return lifts


def trail_areas(piece: str) -> list:
    """Each part of the mountain with its trails, the parts in the order they first come."""
    if "class=\"ski-resort-trails\"" not in piece:
        raise ValueError("the site's answer for the trails is not its list of trails")
    areas, read = {}, 0
    for symbol, name, said, part in TRAIL.findall(piece):
        name, part = words(name), words(part)
        if symbol not in LEVELS:
            raise ValueError(f"{name} has a difficulty symbol the reader does not know: {symbol}")
        if not part:
            raise ValueError(f"{name} is on no part of the mountain")
        areas.setdefault(part, []).append(status_row(name, words(said), LEVELS[symbol]))
        read += 1
    listed = piece.count("class=\"trail\"")
    if not read or read != listed:
        raise ValueError(f"the site lists {listed} trails but {read} were read")
    return [{"Name": part, "Lifts": [], "Trails": trails} for part, trails in areas.items()]


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def dated(page: str, now: datetime) -> datetime:
    """The start of the day the report names, in the year that puts it nearest before ``now``."""
    found = DATED.search(page)
    if not found:
        raise ValueError("the day the snow report was updated was not found")
    month, day = found.group(1)[:3].title(), int(found.group(2))
    today = now.astimezone(PACIFIC_TIME)
    for year in (today.year, today.year - 1):
        try:
            at = datetime.strptime(f"{month} {day} {year}", "%b %d %Y").replace(tzinfo=PACIFIC_TIME)
        except ValueError:
            continue
        # A day of grace covers a report dated for the morning ahead.
        if at <= today + timedelta(days=1):
            return at
    raise ValueError(f"the snow report's day could not be read: {found.group(1)} {found.group(2)}")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snowfall in the shape of the Ikon feed's SnowReport; the page gives no base depth."""
    figures = {}
    for label, said in FIGURE.findall(page):
        if SNOWFALL[label] in figures:
            raise ValueError(f"the snow report gives its {label} twice")
        figures[SNOWFALL[label]] = inches(words(said), label)
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": dated(page, now).astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", "BaseIn": None, **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": lift_rows(pages["lifts"]), "Trails": []},
                              *trail_areas(pages["trails"])]}
    try:
        feed["SnowReport"] = snow_report(pages["snow"], now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
