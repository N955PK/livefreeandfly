"""Alyeska's lifts and its snow report, from its mountain report page (alyeskaresort.com/mountain-report, which sends
the reader on to the season's own page; only the winter one is read).

The page is built on the server and written by hand. Under the heading "Lift Status Report and Hours" there is a box
for each lift: its name, then a dot and its status in the resort's own word, then its hours. The status is carried
as the page says it. The box headed "Terrain Parks" lists parks, not a lift, and is left out; any other box that is
not a name over a dot and a status fails, so a change in the page's shape fails instead of showing wrong numbers.
The page lists no trails by name, so there are none here: it gives only a count of trails open, which it leaves
standing from the season before until the mountain opens, and that count is not read.

The snow report is under the heading "Snow Totals": the snow depth and the snow of the last 12 hours at the base,
the middle and the top, and the snow of the last 24 hours and the season's total at the top of the Glacier Bowl
Express, which are given with the top's. The page draws the three stakes twice, once for wide screens and once for
narrow ones, and the two have to agree. The report is dated by the day in the heading over it and the time its
words start with, in Alaska time; a report with no time is taken as written at the start of its day. The depths are
of natural snow only, the page says. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.alyeskaresort.com/mountain-report/"
NAME = "Alyeska"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
ALASKA_TIME = ZoneInfo("America/Anchorage")
LIFTS_HEADING = "Lift Status Report and Hours"
SNOW_HEADING = "Snow Totals"
# Boxes among the lifts that are not lifts.
NOT_LIFTS = {"terrain parks"}
# The three stakes, by the names the Ikon feed gives them (the app reads those).
STAKES = ("BaseArea", "MidMountainArea", "SummitArea")
HEADING = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)
BOX = re.compile(r"<h3 class=\"elementor-icon-box-title\">(.*?)</h3>\s*"
                 r"<p class=\"elementor-icon-box-description\">(.*?)</p>", re.S)
TAG = re.compile(r"<[^>]+>")
STATUS = re.compile(r"●\s*([A-Za-z][A-Za-z ]*?)\s*(?:\d{1,2}(?::\d{2})?\s*[ap]m\b.*)?")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:”|\")")
TIME = re.compile(r">\s*(\d{1,2}):(\d{2})\s*([ap]m)\s*<", re.I)
STAKE_HEADINGS = ("base", "middle", "top")
TWELVE_HOURS = ("past 12 hours", "last 12 hours")
DEPTH = "*snow depth"


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def section(page: str, heading: str) -> tuple:
    """Where the section under an h2 heading starts and ends: from after the heading to the next h2."""
    for found in HEADING.finditer(page):
        if words(found.group(1)) == heading:
            following = HEADING.search(page, found.end())
            return found.end(), following.start() if following else len(page)
    raise ValueError(f"the heading {heading!r} was not found")


def lifts_of(page: str) -> list:
    start, end = section(page, LIFTS_HEADING)
    lifts = []
    for title, description in BOX.findall(page[start:end]):
        name = words(title)
        if name.lower() in NOT_LIFTS:
            continue
        said = STATUS.fullmatch(words(description))
        if not name or not said:
            raise ValueError(f"the box for {name!r} reads {words(description)!r}, not a dot, a status and hours")
        status = " ".join(said.group(1).split()).capitalize()
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    if not lifts:
        raise ValueError("the page lists no lifts")
    if len({lift["Name"].lower() for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return lifts


def inches(said: str, what: str) -> int | float:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {what} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def stakes_of(heads: list) -> dict:
    """The depth and the 12 hour snow at the base, the middle and the top, from each place the page draws them."""
    lowered, drawn = [head.lower() for head in heads], []
    for at in range(len(heads) - 10):
        if tuple(lowered[at:at + 3]) == STAKE_HEADINGS and lowered[at + 3] in TWELVE_HOURS and lowered[at + 7] == DEPTH:
            drawn.append(([inches(said, "12 hour snow") for said in heads[at + 4:at + 7]],
                          [inches(said, "snow depth") for said in heads[at + 8:at + 11]]))
    if not drawn or any(each != drawn[0] for each in drawn):
        raise ValueError("the snow report's three stakes were not found, or its two drawings of them differ")
    new, depth = drawn[0]
    return {stake: {"Name": name.capitalize(), "BaseIn": depth[at], "Last12HoursIn": new[at]}
            for at, (stake, name) in enumerate(zip(STAKES, STAKE_HEADINGS))}


def written(page: str, start: int, end: int) -> datetime:
    """When the report was written: the day in the heading over "Mountain Report", and the time its words start with."""
    heads = [words(head) for head in HEADING.findall(page[:start])]
    if len(heads) < 3 or heads[-2] != "Mountain Report":
        raise ValueError("the snow report is not under the heading \"Mountain Report\"")
    try:
        day = datetime.strptime(heads[-3], "%B %d, %Y")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    time = TIME.search(page[start:end])
    if time:
        hour, minute, half = int(time.group(1)), int(time.group(2)), time.group(3).lower()
        if not 1 <= hour <= 12 or minute > 59:
            raise ValueError(f"the snow report's time reads {time.group(0)!r}")
        day = day.replace(hour=hour % 12 + (12 if half == "pm" else 0), minute=minute)
    return day.replace(tzinfo=ALASKA_TIME)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: a set for each of the three stakes."""
    start, _ = section(page, SNOW_HEADING)
    end = section(page, LIFTS_HEADING)[0]
    if end < start:
        raise ValueError("the snow report is not above the lifts")
    heads = [words(head) for head in HEADING.findall(page[start:end])]
    lowered = [head.lower() for head in heads]
    if lowered[:2] != ["past 24 hours", "season total"] or len(heads) < 6:
        raise ValueError("the snow report does not start with the last 24 hours and the season's total")
    stakes = stakes_of(heads)
    # Both are measured at the top of the Glacier Bowl Express, so the 24 hour snow goes with the top's figures.
    stakes["SummitArea"]["Last24HoursIn"] = inches(heads[2], "24 hour snow")
    return {"LastUpdate": written(page, start, end).astimezone(timezone.utc).strftime(STAMP), "Resortwide": False,
            "BaseConditions": None, "SeasonTotalIn": inches(heads[4], "season total"), **stakes, "Report": None,
            "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts_of(page), "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
