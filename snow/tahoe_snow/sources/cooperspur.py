"""Cooper Spur's two lifts and its snow report, from its conditions report page (cooperspur.com/conditions-report/).

The page is built on the server and written by hand: one list of a name over what the resort says of it. Two of the
names are the lifts, the Homestead Lift (the chair) and the Rope Tow, each with its status in the resort's own words
(Open, Closed), carried as the page says them. The page gives no status for a run, so there are lifts and no
trails. Both lifts have to be in the list, and a name in it the reader does not know fails, so a change in the
page's shape fails instead of showing wrong numbers.

The same list gives the new snow and the snow depth in inches. The page does not say over how long its new snow
fell: it is carried as the last 24 hours. The temperature, the weather ("General Conditions") and the parking are not
read. The page dates itself by the day only ("Last Updated: October 31st, 2026"), so the report is stamped at noon
Pacific (``PACIFIC``). A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://cooperspur.com/conditions-report/"
NAME = "Cooper Spur"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC = ZoneInfo("America/Los_Angeles")
LIFTS = ("Homestead Lift", "Rope Tow")
# The list's snow figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"new snow": "Last24HoursIn", "snow depth": "BaseIn"}
# What else the list tells, which is not read.
OTHERS = {"temperature", "general conditions", "parking"}
ITEM = re.compile(r"<p class=\"eael-feature-list-title\">([^<]*)</p>\s*"
                  r"<p class=\"eael-feature-list-content\">([^<]*)</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\"|in\.?|inches)?")
UPDATED = re.compile(r"Last Updated:\s*([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def listed(page: str) -> dict:
    """The page's list: each name with what the resort says of it."""
    said = {}
    for name, content in ITEM.findall(page):
        name = words(name)
        if name.lower() not in SNOWFALL and name.lower() not in OTHERS and name not in LIFTS:
            raise ValueError(f"the list has a name the reader does not know: {name!r}")
        if name in said:
            raise ValueError(f"the list names {name} twice")
        said[name] = words(content)
    return said


def lift_rows(said: dict) -> list:
    rows = []
    for name in LIFTS:
        if not said.get(name):
            raise ValueError(f"the list has no status for the {name}")
        status = said[name].capitalize()
        rows.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    return rows


def snow_report(said: dict, page: str) -> dict:
    """The list's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated = UPDATED.search(words(page))
    if not updated:
        raise ValueError("the page does not say when it was last updated")
    try:
        day = datetime.strptime(" ".join(updated.groups()), "%B %d %Y").replace(hour=12, tzinfo=PACIFIC)
    except ValueError as error:
        raise ValueError(f"the day the page was last updated could not be read: {error}") from error
    figures = {}
    for name, text in said.items():
        if name.lower() in SNOWFALL:
            inches = INCHES.fullmatch(text)
            if not inches:
                raise ValueError(f"the list's {name} reads {text!r}, not inches")
            value = float(inches.group(1))
            figures[SNOWFALL[name.lower()]] = int(value) if value.is_integer() else value
    if len(figures) != len(SNOWFALL):
        raise ValueError("the list has no new snow or no snow depth")
    return {"LastUpdate": day.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": None, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    said = listed(page)
    if not said:
        raise ValueError("the list of conditions was not found")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lift_rows(said), "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(said, page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
