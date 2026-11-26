"""Holiday Valley's lifts and trails, and its snow report, from its snow report page (holidayvalley.com/snow-report).

The page is built on the server: a folding section for the lifts and one for each kind of trail (easiest, more
difficult, most difficult, expert, gladed, terrain park), each under a heading that counts how many of its rows are
open, "0 of 13 OPEN LIFTS". A row is a picture and a name, and the picture's name is its status (open, closed, on
hold); a picture the reader does not know fails. A second picture on a row says it was groomed or has snowmaking,
and the groomed one is carried as the trail's grooming. The lifts' own count, open and in all, is checked against
what is read, so a change in the page's shape fails instead of showing wrong numbers. The trails' counts are not
checked: the page counts 24 easiest trails over 33 rows and 16 most difficult over 21. The lifts are one mountain
area and each kind of trail another, the trails taking their difficulty from the section they are under. The
uphill routes, which the page lists again among the easiest trails, and the cross country and walking trails are
left out: the status is of the lift-served mountain.

The snow report gives the base depth as a low and a high, the snow of the past 24 hours and the season's total, in
inches. The page does not say when it was written, so the report is undated, and it gives no word for the surface.
A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.holidayvalley.com/snow-report/"
NAME = "Holiday Valley"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The status pictures' names, in the words of the page's own key.
STATUSES = {"Open": "Open", "Closed": "Closed", "Hold": "On hold"}
# The other pictures a row may carry.
MARKS = {"Groomed", "icon_snowreport_snowmaking"}
# The sections of trails, with the words the app's difficulty symbols are keyed on; glades and parks have none.
LEVELS = {"Easiest": "Green", "More Difficult": "Blue", "Most Difficult": "Black", "Expert": "Double black",
          "Gladed": "", "Terrain Park": ""}
LIFTS = "Lifts"
# The section that is not of the lift-served mountain, and the names of the other rows that are not.
UPHILL = "Uphill Routes"
NOT_ALPINE = re.compile(r"Cross Country|Walking Trail")
SECTION = re.compile(r"<(?:h3|span) class=\"label-accord\">([^<]*)</(?:h3|span)>\s*<span class=\"[^\"]*\bms-auto\">"
                     r"\s*(\d+)\s+of\s+(\d+) OPEN[A-Z ]*</span>\s*</button>\s*</h2>(.*?)(?=<h2 class=\"accordion-header|\Z)",
                     re.S)
ROW = re.compile(r"<div class=\"grid-item\">(.*?)</div>", re.S)
PICTURE = re.compile(r"<img[^>]*\ssrc=\"[^\"]*/([^\"/]+)\.(?:png|svg)\"[^>]*>")
TAG = re.compile(r"<[^>]+>")
FIGURE = re.compile(r"<h3 class=\"box-label subheading word-wrap-mobile\">(.*?)</h3>\s*"
                    r"<span class=\"big-number\">([^<]*)</span>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\"")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\"\s*-\s*(\d+(?:\.\d+)?)\"")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def rows_of(section: str, body: str, difficulty) -> list:
    """The rows of one section: each a name, its status from its picture, and whether it was groomed."""
    rows = []
    for markup in ROW.findall(body):
        name, pictures = words(markup), PICTURE.findall(markup)
        if not name:
            raise ValueError(f"a row of {section} has no name")
        if not pictures or pictures[0] not in STATUSES or any(mark not in MARKS for mark in pictures[1:]):
            raise ValueError(f"{name} has the pictures {pictures}, not a status the reader knows")
        status = STATUSES[pictures[0]]
        row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
        if difficulty is not None:
            row["Grooming"] = "Yes" if "Groomed" in pictures[1:] else "No"
        rows.append(row)
    return rows


def sections(page: str) -> list:
    """The lifts' area and one for each kind of trail, in the page's order, the lifts checked against their count."""
    found = [(words(heading), int(turning), int(listed), body) for heading, turning, listed, body in
             SECTION.findall(page)]
    unknown = [section for section, *_ in found if section not in LEVELS and section not in (LIFTS, UPHILL)]
    if unknown or len({section for section, *_ in found}) != len(found):
        raise ValueError(f"the page has a section twice, or ones the reader does not know: {unknown}")
    uphill = {row["Name"] for section, _, _, body in found if section == UPHILL for row in rows_of(section, body, "")}
    areas = []
    for section, turning, listed, body in found:
        if section == LIFTS:
            lifts = rows_of(section, body, None)
            read = sum(lift["StatusEnglish"] == "open" for lift in lifts)
            if (turning, listed) != (read, len(lifts)):
                raise ValueError(f"the page counts {turning} of {listed} lifts open but {read} of {len(lifts)} "
                                 "were read")
            areas.append({"Name": NAME, "Lifts": lifts, "Trails": []})
        elif section != UPHILL:
            trails = [trail for trail in rows_of(section, body, LEVELS[section])
                      if trail["Name"] not in uphill and not NOT_ALPINE.search(trail["Name"])]
            areas.append({"Name": section, "Lifts": [], "Trails": trails})
    if not any(area["Lifts"] for area in areas) or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    figures = {words(heading): words(said) for heading, said in FIGURE.findall(page)}
    depth = RANGE.fullmatch(figures.get("BASE DEPTH", ""))
    new, season = INCHES.fullmatch(figures.get("PAST 24HRS", "")), INCHES.fullmatch(figures.get("SEASON TOTAL", ""))
    if not depth or not new:
        raise ValueError(f"the base depth reads {figures.get('BASE DEPTH')!r} and the past 24 hours "
                         f"{figures.get('PAST 24HRS')!r}, not inches")
    low, high = number(depth.group(1)), number(depth.group(2))
    if low > high:
        raise ValueError(f"the base depth runs from {low} down to {high}")
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None,
            "SeasonTotalIn": number(season.group(1)) if season else None,
            "BaseArea": {"Name": "Mountain", "BaseMinIn": low, "BaseMaxIn": high,
                         "Last24HoursIn": number(new.group(1))}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": sections(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
