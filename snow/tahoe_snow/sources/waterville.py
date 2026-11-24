"""Waterville Valley's lifts and trails, and its snow report, from the report its snow report page shows
(features.waterville.com/propsnow/, shown inside waterville.com/snow-report-maps).

The report is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The report lists the
trails under their difficulty (Easiest, More Difficult, Most Difficult, Expert Only), then the terrain parks, then
the lifts; it does not divide the mountain into parts, so the trails are one area and the parks another. Each trail
and lift carries its status in words (Open, Closed, On Hold, Wind Delay), and a trail may carry more marks after it:
groomed or partly groomed (both read as groomed), moguls, snowmaking, racing. Every lift and trail on the page is
one read, so a change in its shape fails instead of dropping runs. Parts of the report the resort has switched off
are left in the page as comments, and are not read.

The snow report gives the new snow and the base depth as one figure or as a least and a most ("20 - 30 in."): both
are carried, with the middle of the two as the one figure. A figure the resort leaves empty stays empty, and one
that does not read as inches fails. The time the report was posted is in the mountain's own time. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://features.waterville.com/propsnow/"
NAME = "Waterville Valley"
LOCAL = ZoneInfo("America/New_York")
COMMENT = re.compile(r"<!--.*?-->", re.S)
UPDATED = re.compile(r"<dd>\s*Updated:\s*</dd>\s*<dd>(.*?)</dd>", re.S)
MEASURE = re.compile(r"<dl class=\"SnowReport-measure\">\s*<dt>(.*?)</dt>\s*<dd>(.*?)</dd>", re.S)
WRITTEN = re.compile(r"<section class=\"SnowReport-section SnowReport-section--written\">\s*<article>(.*?)</article>\s*"
                     r"</section>", re.S)
SECTION = re.compile(r"<section class=\"SnowReport-section SnowReport-section--(trails|lifts)\">\s*"
                     r"<h2 class=\"SnowReport-section-title\">(.*?)</h2>(.*?)</section>", re.S)
FEATURE = re.compile(r"<article class=\"SnowReport-(?:Trail|Lift) SnowReport-feature\">(.*?)</article>", re.S)
TITLE = re.compile(r"<h3 class=\"SnowReport-feature-title\">(.*?)</h3>", re.S)
# A status mark: its symbol and its words. The words of the marks after the first sit inside the symbol.
MARK = re.compile(r"SnowReport-item-status\">\s*<i class=\"pti pti-([a-z-]+)\"[^>]*>(?:\s*</i>)?\s*"
                  r"<span class=\"SnowReport-sr-label\">(.*?)</span>", re.S)
# The report's headings, in the words the page's difficulty symbols are keyed on.
LEVELS = {"easiest": "Green", "more difficult": "Blue", "most difficult": "Black", "expert only": "Double black"}
PARKS = "terrain park"
GROOMED = {"groomed", "groomed-partial"}
INCHES = re.compile(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*(?:\"|in\.?)?", re.I)
EMPTY = re.compile(r"[\s-]*(?:in\.?)?", re.I)


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = status.strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def span(said: str | None, name: str) -> dict:
    """A depth the report gives as '173 in.' or '20 - 30 in.', under the Ikon feed's name for it with its least and
    most beside it; the one figure is the middle of the two. Empty where the report gives nothing (' - in.', ' in.'),
    and words that are not a depth fail."""
    if said is None or EMPTY.fullmatch(said):
        return {f"{name}In": None, f"{name}MinIn": None, f"{name}MaxIn": None}
    read = INCHES.fullmatch(said.strip())
    if not read:
        raise ValueError(f"the report's {name} reads {said!r}, not a depth in inches")
    low = number(read.group(1))
    high = number(read.group(2)) if read.group(2) else low
    if low > high:
        raise ValueError(f"the report's {name} runs from {low} down to {high}")
    return {f"{name}In": number(str((low + high) / 2)), f"{name}MinIn": low, f"{name}MaxIn": high}


def posted(page: str) -> str:
    """When the report was posted ('11:12am, November 23, 2026', in the mountain's own time)."""
    read = UPDATED.search(page)
    if not read:
        raise ValueError("the time the report was posted was not found")
    try:
        when = datetime.strptime(text_of(read.group(1)), "%I:%M%p, %B %d, %Y").replace(tzinfo=LOCAL)
    except ValueError as error:
        raise ValueError(f"the time the report was posted does not read: {text_of(read.group(1))!r}") from error
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snow_report(page: str) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    measures = {text_of(label).lower(): text_of(value) for label, value in MEASURE.findall(page)}
    if "base depth" not in measures or "past 24 hours" not in measures:
        raise ValueError("the report's snowfall and base depth were not found")
    area = {"Name": "Mountain", **span(measures["base depth"], "Base"), **span(measures["past 24 hours"], "Last24Hours"),
            "Last48HoursIn": span(measures.get("past 48 hours"), "Last48Hours")["Last48HoursIn"]}
    words = WRITTEN.search(page)
    return {"LastUpdate": posted(page), "Resortwide": True, "BaseConditions": measures.get("primary surface") or None,
            "SeasonTotalIn": span(measures.get("season total"), "SeasonTotal")["SeasonTotalIn"], "BaseArea": area,
            "Report": words.group(1).strip() if words else None, "Alert": None}


def rows_of(body: str, difficulty: str | None, trails: bool) -> list:
    rows = []
    for feature in FEATURE.findall(body):
        title, marks = TITLE.search(feature), MARK.findall(feature)
        if not title or not text_of(title.group(1)) or not marks or not text_of(marks[0][1]):
            raise ValueError("a lift or trail in the report has no name or no status")
        row = status_row(text_of(title.group(1)), text_of(marks[0][1]), difficulty)
        if trails:
            row["Grooming"] = "Yes" if GROOMED & {symbol for symbol, _ in marks[1:]} else "No"
        rows.append(row)
    return rows


def parse(page: str, now: datetime) -> dict:
    listed = len(re.findall(r"<article class=\"SnowReport-(?:Trail|Lift)\b", page))
    page = COMMENT.sub("", page)
    lifts, trails, parks = [], [], []
    for kind, title, body in SECTION.findall(page):
        title = text_of(title)
        if kind == "lifts":
            lifts += rows_of(body, None, False)
        elif title.lower().startswith(PARKS):
            parks += rows_of(body, "", True)
        else:
            trails += rows_of(body, LEVELS.get(title.lower(), ""), True)
    if not lifts or not trails:
        raise ValueError("the report lists no lifts or no trails")
    # Every lift and trail in the report is one read, so a change in its shape fails instead of dropping runs.
    found = len(lifts) + len(trails) + len(parks)
    if found != listed:
        raise ValueError(f"the report lists {listed} lifts and trails but {found} were read")
    areas = [{"Name": NAME, "Lifts": lifts, "Trails": trails}]
    if parks:
        areas.append({"Name": "Terrain Parks", "Lifts": [], "Trails": parks})
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas,
            "SnowReport": snow_report(page)}
