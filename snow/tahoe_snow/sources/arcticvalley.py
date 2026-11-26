"""Arctic Valley's lifts and its snow report, from its conditions page (arcticvalley.org/conditions/).

The page is built on the server and written by hand, as sections that fold open. The "Lift Status" section is one
line for each lift, its name in bold and then the ski club's own words for it: "N/A" out of season, and otherwise
whatever the club writes. The words are carried as the page has them; a lift reads as open or closed where its
words begin with that word ("Open until 4pm"), and as the words themselves otherwise. The page gives no status for a
run, so there are lifts and no trails. Every bold name in the section is one lift read, so a change in the page's
shape fails instead of dropping lifts.

The "Snow Report" section gives the new snow of the last 24 hours and since last week, and the total snow depth, in
inches, under the day it was updated, written as a weekday, a month and a day with no year ("Friday November
20th"). The year is the latest that puts the day not after today, the weekday has to agree with it, and the report
is stamped at noon in Alaska (``ALASKA``): a day whose weekday does not agree is a slip of the hand or a year old,
and costs the snow report. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://arcticvalley.org/conditions/"
NAME = "Arctic Valley"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
ALASKA = ZoneInfo("America/Anchorage")
# The snow report's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"new snow last 24 hours": "Last24HoursIn", "new snow since last week": "Last7DaysIn",
            "total snow depth": "BaseIn"}
SECTION = re.compile(r"<details[^>]*>\s*<summary>(.*?)</summary>(.*?)</details>", re.S)
LIFT = re.compile(r"<strong>([^<]*?):\s*</strong>([^<]*)")
BREAK = re.compile(r"<br\s*/?>|</p>")
UPDATED = re.compile(r"Updated\s+([A-Z][a-z]+)day,?\s+([A-Z][a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b")
LINE = re.compile(r"([^:]+):\s*(\d+(?:\.\d+)?)\s*(?:″|”|\"|in\.?|inches)?")
SETTLED = re.compile(r"(open|closed)\b", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def section(page: str, title: str) -> str:
    """The inside of the folding section with this title."""
    for summary, body in SECTION.findall(page):
        if words(summary).lstrip("• ").lower() == title:
            return body
    raise ValueError(f"the page has no {title} section")


def lift_rows(page: str) -> list:
    """The lifts of the Lift Status section, in the page's order."""
    body = section(page, "lift status")
    rows = []
    for name, said in LIFT.findall(body):
        name, said = words(name), words(said)
        if not name or not said:
            raise ValueError("a lift in the Lift Status section has no name or no status")
        settled = SETTLED.match(said)
        rows.append({"Name": name, "Status": said, "StatusEnglish": (settled.group(1) if settled else said).lower(),
                     "Difficulty": None})
    if not rows:
        raise ValueError("the Lift Status section lists no lifts")
    if len(rows) != body.count("<strong>"):
        raise ValueError(f"the Lift Status section has {body.count('<strong>')} names but {len(rows)} lifts were read")
    return rows


def updated(body: str, now: datetime) -> str:
    """The day the snow report says it was updated, at noon in Alaska, in UTC."""
    said = UPDATED.search(words(body))
    if not said:
        raise ValueError("the snow report does not say when it was updated")
    today = now.astimezone(ALASKA)
    for year in (today.year, today.year - 1):
        try:
            day = datetime.strptime(f"{year} {said.group(2)} {said.group(3)}", "%Y %B %d")
        except ValueError:
            continue
        day = day.replace(hour=12, tzinfo=ALASKA)
        if day <= today + timedelta(days=1):
            if day.strftime("%A") != said.group(1) + "day":
                break
            return day.astimezone(timezone.utc).strftime(STAMP)
    raise ValueError(f"the snow report's day does not read as a day of the last year: {said.group(0)!r}")


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    body = section(page, "snow report")
    figures = {}
    for line in BREAK.split(body):
        read = LINE.fullmatch(words(line))
        if read and read.group(1).lower() in SNOWFALL:
            value = float(read.group(2))
            figures[SNOWFALL[read.group(1).lower()]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no total snow depth or no 24 hour snowfall")
    return {"LastUpdate": updated(body, now), "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": None,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lift_rows(page), "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(page, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
