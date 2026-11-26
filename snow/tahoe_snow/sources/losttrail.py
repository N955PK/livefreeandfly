"""Lost Trail's lifts and its snow report from its snow report page (losttrail.com/snow-report).

The page is built on the server, as a run of lines, each a label with what the page says beside it. Under its
"Lift Report" heading the lines are the five chairs, each with its status in words, carried as the page says it.
The page does not list its trails: it only counts them ("12/69"), and its lifts ("3/5"), in its terrain report.
The lifts are one mountain area with no trails, the count of trails is carried in the snow report, and the count
of lifts has to match the lifts read, so a change in the page's shape fails instead of showing wrong numbers.

The snow report gives the snow since the lifts closed and of the last 24 and 48 hours, the season's snowfall, the
depth at the bottom and at the top, in inches, and the surface in words, with the day and time it was written, in
Mountain time. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://losttrail.com/snow-report/"
NAME = "Lost Trail"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LOCAL_TIME = ZoneInfo("America/Denver")
# The snow report's lines, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"New Snow (since lifts closed)": "SinceLiftsClosedIn", "New Snow, 24 hours": "Last24HoursIn",
            "New Snow, 48 hours": "Last48HoursIn", "Snow Depth - Bottom": "BaseIn"}
# A line: a label in a block of its own, then what the page says of it in the next piece of text.
LINE = re.compile(r"<div class=\"elementor-heading-title[^\"]*\">([^<]*)</div>(?:(?!elementor-heading-title).)*?"
                  r"<span class=\"elementor-heading-title[^\"]*\">(.*?)</span>", re.S)
HEADING = re.compile(r"<h[1-6] class=\"elementor-heading-title[^\"]*\">(.*?)</h[1-6]>", re.S)
WRITTEN = re.compile(r"Snow Report for ([A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [ap]m)")
COUNTED = re.compile(r"(\d+)\s*/\s*(\d+)")
INCHES = re.compile(r"(\d+(?:\.\d+)?|\.\d+)\s*(?:″|”|\")")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lines(markup: str) -> dict:
    """The lines of a piece of the page, each label with what the page says beside it."""
    return {words(label): words(said) for label, said in LINE.findall(markup)}


def lift_report(page: str) -> str:
    """The piece of the page under its "Lift Report" heading, up to the next heading."""
    headings = list(HEADING.finditer(page))
    for heading, following in zip(headings, headings[1:] + [None]):
        if words(heading.group(1)) == "Lift Report":
            return page[heading.end():following.start() if following else len(page)]
    raise ValueError("the lift report was not found")


def lifts_of(page: str) -> list:
    lifts = []
    for name, said in lines(lift_report(page)).items():
        if not name or not said:
            raise ValueError(f"the lift {name!r} has no name or no status: {said!r}")
        said = said.capitalize()
        lifts.append({"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None})
    return lifts


def counted(said: dict, label: str) -> tuple:
    """One of the terrain report's counts: how many are open, and how many there are."""
    found = COUNTED.fullmatch(said.get(label, ""))
    if not found:
        raise ValueError(f"the page's count under {label!r} was not found")
    return int(found.group(1)), int(found.group(2))


def inches(said: str, label: str) -> float | int:
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the snow report's {label} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str, said: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the bottom and the top."""
    written = WRITTEN.search(words(page))
    if not written:
        raise ValueError("the snow report does not say when it was written")
    try:
        at = datetime.strptime(written.group(1), "%B %d, %Y %I:%M %p").replace(tzinfo=LOCAL_TIME)
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    missing = [label for label in (*SNOWFALL, "Snow Depth - Top") if label not in said]
    if missing:
        raise ValueError(f"the snow report has no line for {missing}")
    base = {"Name": "Bottom", **{field: inches(said[label], label) for label, field in SNOWFALL.items()}}
    season, (turning, trails) = said.get("Season Snowfall"), counted(said, "Trails Open")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": said.get("Surface Conditions (Primary)") or None,
            "SeasonTotalIn": inches(season, "season's snowfall") if season else None, "BaseArea": base,
            "SummitArea": {"Name": "Top", "BaseIn": inches(said["Snow Depth - Top"], "Snow Depth - Top")},
            "TotalOpenTrails": turning, "TotalTrails": trails, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, said = lifts_of(page), lines(page)
    if not lifts:
        raise ValueError("the lift report lists no lifts")
    turning, listed = counted(said, "Number of Lifts Open")
    read = sum(lift["StatusEnglish"] == "open" for lift in lifts), len(lifts)
    if listed != read[1] or turning > listed:
        raise ValueError(f"the page counts {turning} of {listed} lifts open but {read[0]} of {read[1]} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(page, said)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
