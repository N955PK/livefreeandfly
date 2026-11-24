"""Banff Sunshine's lifts and trails, and its snow report, from its lifts and trails report and its current
conditions pages (skibanff.com/the-mountain/mountain-report/lifts-trails-report and /current-conditions).

Both pages are built on the server. The lifts and trails report is a row for each lift and each trail. A row's
status is the word beside its status symbol, in the words of the page's own key: open, closed or standby (a lift
or a trail waiting to turn, carried as on hold), and a word the reader does not know fails. A trail's row also
says its difficulty (a terrain park's row gives none) and says so when it has been groomed. The trails are listed
under the three mountains (Goat's Eye Mountain, Lookout Mountain, Mount Standish), which are the mountain areas
here; the lifts name no mountain and are an area of their own. The page's own count of lifts and of trails, open
and in all, is checked against what is read, so a change in its shape fails instead of showing wrong numbers.

The snow report gives two sets of figures, at the upper mountain and at mid mountain: the snow overnight and of
the last 24 hours and 7 days, the base, and the season's cumulative snowfall (carried from the upper mountain),
under a line saying when the conditions were updated, in the resort's own time. **The page's centimetres are
read and converted to inches here (divided by 2.54, to one decimal).** The page's own imperial figures are
rounded and are not used. The page gives no word for the surface. A snow report that cannot be read costs only
the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SITE = "https://www.skibanff.com/the-mountain/mountain-report"
URLS = {"lifts": f"{SITE}/lifts-trails-report", "snow": f"{SITE}/current-conditions"}
NAME = "Banff Sunshine"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Edmonton")
CM_PER_INCH = 2.54
# The page's status words, as the status carried and the word the app sorts it by.
STATUSES = {"Open": ("Open", "open"), "Closed": ("Closed", "closed"), "Standby": ("Standby", "on hold")}
# The page's difficulty words, in the words the app's difficulty symbols are keyed on.
LEVELS = {"Easiest": "Green", "More Difficult": "Blue", "Most Difficult": "Black", "Experts Only": "Double black"}
# The snow report's two places, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Mid Mountain Snow Report": ("MidMountainArea", "Mid Mountain"),
          "Upper Mountain Snow Report": ("SummitArea", "Upper Mountain")}
# The figures of a place, by the names the Ikon feed gives them; the two places head them differently.
FIGURES = {"Overnight": "OvernightIn", "24hr": "Last24HoursIn", "24 Hours": "Last24HoursIn", "7 Day": "Last7DaysIn",
           "7 Days": "Last7DaysIn", "Base": "BaseIn", "Settled Base": "BaseIn", "Cumulative": "SeasonTotalIn"}
BLOCK = re.compile(r"<div id=\"block-lifts-trails\"(.*?)</main>", re.S)
ROW = re.compile(r"class=\"node node--type-(lift|trail) node--view-mode-row\"")
MOUNTAIN = re.compile(r"<summary[^>]*>(.*?)</summary>", re.S)
TITLE = re.compile(r"<div class=\"h4 m-0 title\">(.*?)(?:<div class=\"t-micetype|</div>\s*<div class=\"[^\"]*f-icon)",
                   re.S)
SAID = re.compile(r"<div class=\"[^\"]*\bicon-(level|condition|status)\b[^\"]*\">\s*<span class=\"visually-hidden\">"
                  r"(.*?)</span>\s*</div>", re.S)
COUNTED = r"<div class=\"[^\"]*\bvalue\">\s*(\d+)\s*</div>\s*<div class=\"[^\"]*\btotal\">\s*of (\d+)\s*</div>\s*" \
          r"</div>\s*<figcaption[^>]*>\s*{kind} Open\s*</figcaption>"
TAG = re.compile(r"<[^>]+>")
SNOW_REPORT = re.compile(r"<div id=\"block-weather-feed\"(.*?)</section>", re.S)
UPDATED = re.compile(r"Updated:\s*[A-Z][a-z]+day, ([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th)?, (\d{4}) "
                     r"(\d{1,2}):(\d{2}) ([AP]M)")
GROUP = re.compile(r"<h3 class=\"snow-group-title\">(.*?)</h3>", re.S)
FIGURE = re.compile(r"<h4>(.*?)</h4>\s*<div class=\"[^\"]*snow-stats\">\s*<div>\s*<div class=\"[^\"]*weather-data\">\s*"
                    r"<span class=\"value\">\s*([^<]*?)\s*</span>\s*<span class=\"[^\"]*unit\">\s*([^<]*?)\s*</span>",
                    re.S)


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(kind: str, body: str) -> dict:
    """One lift or trail: its name, and the words beside its difficulty, grooming and status symbols."""
    title = TITLE.search(body)
    said = {}
    for symbol, word in SAID.findall(body):
        if symbol in said:
            raise ValueError(f"{words(title.group(1)) if title else 'a row'} has two {symbol} symbols")
        said[symbol] = words(word)
    # A trail's difficulty sits inside its title; a lift's hours follow its name and are left out.
    name = words(SAID.sub("", title.group(1))) if title else ""
    if not name or said.get("status") not in STATUSES:
        raise ValueError(f"{name or 'a row'} has a status the reader does not know: {said.get('status')!r}")
    status, english = STATUSES[said["status"]]
    row = {"Name": name, "Status": status, "StatusEnglish": english, "Difficulty": None}
    if kind == "trail":
        if "level" in said and said["level"] not in LEVELS:
            raise ValueError(f"{name} has a difficulty the reader does not know: {said['level']!r}")
        if said.get("condition", "Groomed") != "Groomed":
            raise ValueError(f"{name} has a condition the reader does not know: {said['condition']!r}")
        row["Difficulty"] = LEVELS[said["level"]] if "level" in said else ""
        row["Grooming"] = "Yes" if "condition" in said else "No"
    return row


def checked(rows: list, block: str, kind: str) -> list:
    """The rows, once the page's own count of them, open and in all, agrees with what was read."""
    counted = re.search(COUNTED.format(kind=kind), block)
    if not counted:
        raise ValueError(f"the page's count of {kind} was not found")
    opened = sum(row["StatusEnglish"] == "open" for row in rows)
    if (opened, len(rows)) != (int(counted.group(1)), int(counted.group(2))):
        raise ValueError(f"the page counts {counted.group(1)} of {counted.group(2)} {kind} open but {opened} of "
                         f"{len(rows)} were read")
    return rows


def mountain_areas(page: str) -> list:
    found = BLOCK.search(page)
    if not found:
        raise ValueError("the page's lifts and trails were not found")
    block = found.group(1)
    # Each row runs to the next row or the next mountain's heading, whichever comes first.
    marks = sorted([(row.start(), row.group(1), None) for row in ROW.finditer(block)]
                   + [(head.start(), "mountain", words(head.group(1))) for head in MOUNTAIN.finditer(block)])
    lifts, areas = [], []
    for (start, kind, name), after in zip(marks, [*marks[1:], (len(block), None, None)]):
        if kind == "mountain":
            areas.append({"Name": name, "Lifts": [], "Trails": []})
        elif kind == "lift":
            lifts.append(status_row(kind, block[start:after[0]]))
        elif not areas:
            raise ValueError("the page lists a trail under no mountain")
        else:
            areas[-1]["Trails"].append(status_row(kind, block[start:after[0]]))
    checked(lifts, block, "lifts")
    checked([trail for area in areas for trail in area["Trails"]], block, "trails")
    return [{"Name": NAME, "Lifts": lifts, "Trails": []}, *(area for area in areas if area["Trails"])]


def updated(block: str) -> str:
    """When the conditions were updated, in UTC, from the resort's own time."""
    found = UPDATED.search(block)
    if not found:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute, half = found.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc).strftime(STAMP)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: a set at mid mountain and at the top."""
    found = SNOW_REPORT.search(page)
    if not found:
        raise ValueError("the snow report was not found")
    block = found.group(1)
    heads = list(GROUP.finditer(block))
    stakes, season = {}, {}
    for head, after in zip(heads, [*heads[1:], None]):
        title = words(head.group(1))
        if title not in STAKES or STAKES[title][0] in stakes:
            raise ValueError(f"the snow report has a place the reader does not know, or has it twice: {title}")
        key, name = STAKES[title]
        figures = {}
        for heading, value, unit in FIGURE.findall(block[head.end():after.start() if after else len(block)]):
            heading = words(heading)
            if heading not in FIGURES or FIGURES[heading] in figures or unit != "cm":
                raise ValueError(f"the snow report's {heading} at {name} is not a figure the reader knows, in "
                                 "centimetres, given once")
            try:
                figures[FIGURES[heading]] = round(float(value) / CM_PER_INCH, 1)
            except ValueError as error:
                raise ValueError(f"the snow report's {heading} at {name} reads {value!r}, not a number") from error
        if "BaseIn" not in figures or "Last24HoursIn" not in figures:
            raise ValueError(f"the snow report has no base or no 24 hour snowfall at {name}")
        season[key] = figures.pop("SeasonTotalIn", None)
        stakes[key] = {"Name": name, **figures}
    if set(stakes) != {key for key, _ in STAKES.values()}:
        raise ValueError("the snow report has no upper mountain or no mid mountain figures")
    return {"LastUpdate": updated(block), "Resortwide": False, "BaseConditions": None,
            "SeasonTotalIn": season["SummitArea"], "MidMountainArea": stakes["MidMountainArea"],
            "SummitArea": stakes["SummitArea"], "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": mountain_areas(pages["lifts"])}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
