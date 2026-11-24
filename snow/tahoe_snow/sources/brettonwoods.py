"""Bretton Woods' lifts and trails, and its snow report, from its snow and trail report page
(brettonwoods.com/snow-trail-report/).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page has an
alpine report and a Nordic one; only the alpine one is read: the status is of the lift-served mountain. Under it the
lifts are one list, then the trails and the glades are one list for each part of the mountain, each headed by its
name and its own count ("Mount Rosebrook 0/40"). Every list is checked against the count in its heading, and the
lists together against the page's own totals of lifts, trails and glades, so a change in the page's shape fails
instead of showing wrong numbers. A trail carries its status in words, its difficulty as a symbol and a grooming
mark when the cats have been over it.

The snow report gives one base depth for the whole mountain, usually as a least and a most ("25-50 inches"): both
are carried, with the middle of the two as the one figure. Snowfall is given at the mountain base and on the upper
mountain, as "Recent" and "Season to Date". The page does not say how long "Recent" is, so it is carried under its
own name (RecentIn) and not as the last 24 hours. A figure the resort leaves empty stays empty, and one that does
not read as inches fails. The time the report was posted is given without a year and in the mountain's own time; the
year is the one that puts it nearest before now. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.brettonwoods.com/snow-trail-report/"
NAME = "Bretton Woods"
LOCAL = ZoneInfo("America/New_York")
ALPINE = re.compile(r"<li class=\"tabs-component__tab[^\"]*\" id=\"alpine-report[^\"]*\">(.*?)"
                    r"(?=<li class=\"tabs-component__tab[^\"]*\" id=\"nordic-report|\Z)", re.S)
UPDATED = re.compile(r"trail-reports__updated[^>]*>\s*Updated:\s*(\d{1,2})/(\d{1,2}) at (\d{1,2})(?::(\d{2}))?\s*([ap])m",
                     re.I)
SUMMARY = re.compile(r"summary-item-heading\">(.*?)</div>\s*<div class=\"trail-reports__summary-item-count\">(.*?)</div>",
                     re.S)
INFO = re.compile(r"info-item-heading\">(.*?)</div>\s*<div class=\"trail-reports__info-item-value\">(.*?)</div>", re.S)
SNOWFALL_ROW = re.compile(r"<div class=\"trail-reports__snowfall-(?:header-)?row\">(.*?)</div>\s*</div>", re.S)
SNOWFALL_CELL = re.compile(r"<div class=\"trail-reports__snowfall-cell[^\"]*\">(.*?)(?:</div>|\Z)", re.S)
# A list of lifts or trails: its heading ("Zephyr Area 3/12") and the rows under it.
SECTION = re.compile(r"aria-label=\"([^\"]*?)\s+(\d+)/(\d+)\"(.*?)<ul class=\"trail-reports__table[^\"]*\">(.*?)</ul", re.S)
ROW = re.compile(r"<li class=\"trail-reports__table-item[^\"]*\" data-status=\"[^\"]*\">(.*?)</li>", re.S)
ROW_NAME = re.compile(r"<div class=\"trail-reports__table-item--name\">(.*?)</div>", re.S)
ROW_STATUS = re.compile(r"<div class=\"trail-reports__table-item--status\">\s*<span>(.*?)</span>", re.S)
ROW_LEVEL = re.compile(r"trail-reports__table-item--ability\">\s*<svg class=\"[^\"]*v-icon__svg--trail-([a-z-]+)")
COMMENTS = re.compile(r"aria-label=\"Comments\".*?<div class=\"accordion__content[^\"]*\">(.*?)</div>\s*</div>\s*</li>", re.S)
LIFTS = "lifts operating"
# The page's trail symbols, in the words the page's difficulty symbols are keyed on.
LEVELS = {"circle": "Green", "square": "Blue", "diamond": "Black", "two-diamond": "Double black"}
# The snowfall table's columns, by the Ikon feed's names for the stakes, and its rows by the names carried here.
STAKES = {"mountain base": "BaseArea", "upper mountain": "SummitArea"}
SNOWFALL = {"recent": "Recent", "season to date": "SeasonTotal"}
INCHES = re.compile(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?\s*(?:\"|”|in\.?|inch(?:es)?)?", re.I)


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = (status or "Closed").strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def span(said: str, name: str) -> dict:
    """A depth the page gives as '25-50 inches', '1-3"' or '0"', under the name given with its least and most beside
    it; the one figure is the middle of the two. Empty where the page gives nothing, and words that are not a depth
    fail."""
    said = said.strip()
    if said in ("", "-", "--", "N/A"):
        return {f"{name}In": None, f"{name}MinIn": None, f"{name}MaxIn": None}
    read = INCHES.fullmatch(said)
    if not read:
        raise ValueError(f"the page's {name} reads {said!r}, not a depth in inches")
    low = number(read.group(1))
    high = number(read.group(2)) if read.group(2) else low
    if low > high:
        raise ValueError(f"the page's {name} runs from {low} down to {high}")
    return {f"{name}In": number(str((low + high) / 2)), f"{name}MinIn": low, f"{name}MaxIn": high}


def posted(alpine: str, now: datetime) -> str:
    """When the report was posted. The page gives the month, day and hour in the mountain's own time and no year:
    the year is now's, or the one before where that would put the report in the future (a December report read in
    January)."""
    read = UPDATED.search(alpine)
    if not read:
        raise ValueError("the time the report was posted was not found")
    month, day, hour, minute, half = read.groups()
    hour = int(hour) % 12 + (12 if half.lower() == "p" else 0)
    here = now.astimezone(LOCAL)
    try:
        when = datetime(here.year, int(month), int(day), hour, int(minute or 0), tzinfo=LOCAL)
        if when > here + timedelta(days=1):
            when = when.replace(year=here.year - 1)
    except ValueError as error:
        raise ValueError(f"the time the report was posted does not read: {read.group(0)!r}") from error
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snow_report(alpine: str, now: datetime) -> dict:
    """The alpine report's snow figures in the shape of the Ikon feed's SnowReport. The base depth and the surface
    are the whole mountain's and are carried at the base; snowfall is carried at the base and on the upper mountain
    as the page gives it."""
    info = {text_of(heading).rstrip(":").lower(): text_of(value) for heading, value in INFO.findall(alpine)}
    rows = [[text_of(cell) for cell in SNOWFALL_CELL.findall(row)] for row in SNOWFALL_ROW.findall(alpine)]
    if not rows or rows[0][0].lower() != "snowfall":
        raise ValueError("the page's snowfall table was not found")
    places = [STAKES.get(place.lower()) for place in rows[0][1:]]
    if None in places or not places:
        raise ValueError(f"the snowfall table's columns are not the ones expected: {rows[0][1:]}")
    stakes = {place: {"Name": name} for place, name in zip(places, rows[0][1:])}
    for label, *cells in rows[1:]:
        field = SNOWFALL.get(label.lower())
        if not field or len(cells) != len(places):
            raise ValueError(f"the snowfall table has a row this reader does not know: {label!r}")
        for place, cell in zip(places, cells):
            stakes[place].update(span(cell, field))
    stakes["BaseArea"] = {**stakes.get("BaseArea", {"Name": "Mountain Base"}), **span(info.get("base depth", ""), "Base"),
                          "Last24HoursIn": None}
    words = COMMENTS.search(alpine)
    return {"LastUpdate": posted(alpine, now), "Resortwide": False, "BaseConditions": info.get("snow conditions") or None,
            "SeasonTotalIn": None, **stakes, "Report": words.group(1).strip() if words else None, "Alert": None}


def rows_of(body: str, trails: bool) -> list:
    rows = []
    for item in ROW.findall(body):
        name, status, level = ROW_NAME.search(item), ROW_STATUS.search(item), ROW_LEVEL.search(item)
        if not name or not status or not text_of(name.group(1)) or not text_of(status.group(1)):
            raise ValueError("a lift or trail on the page has no name or no status")
        row = status_row(text_of(name.group(1)), text_of(status.group(1)),
                         LEVELS.get(level.group(1), "") if level else "" if trails else None)
        if trails:
            row["Grooming"] = "Yes" if "trail-reports__table-item--grooming" in item else "No"
        rows.append(row)
    return rows


def parse(page: str, now: datetime) -> dict:
    found = ALPINE.search(page)
    if not found:
        raise ValueError("the page's alpine report was not found")
    alpine = found.group(1)
    lifts, areas = [], []
    for name, _, total, between, body in SECTION.findall(alpine):
        # A heading whose own list was not found must not be given the next heading's rows.
        if "aria-label=" in between:
            raise ValueError(f"the list under {name!r} was not found")
        name, is_lifts = text_of(name), text_of(name).lower() == LIFTS
        rows = rows_of(body, not is_lifts)
        if len(rows) != int(total):
            raise ValueError(f"{name} counts {total} but {len(rows)} were read")
        if is_lifts:
            lifts += rows
        else:
            areas.append({"Name": name, "Lifts": [], "Trails": rows})
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    # The page's own totals ("Trail Count 0/63", "Glades Count 0/40", "Lifts Open 0/8") against what was read.
    totals = {text_of(heading).lower(): text_of(count).rpartition("/")[2] for heading, count in SUMMARY.findall(alpine)}
    try:
        listed_lifts, listed_trails = int(totals["lifts open"]), int(totals["trail count"]) + int(totals["glades count"])
    except (KeyError, ValueError) as error:
        raise ValueError(f"the page's totals of lifts, trails and glades were not found: {error!r}") from error
    read_trails = sum(len(area["Trails"]) for area in areas)
    if listed_lifts != len(lifts) or listed_trails != read_trails:
        raise ValueError(f"the page counts {listed_lifts} lifts and {listed_trails} trails and glades but "
                         f"{len(lifts)} and {read_trails} were read")
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas],
            "SnowReport": snow_report(alpine, now)}
