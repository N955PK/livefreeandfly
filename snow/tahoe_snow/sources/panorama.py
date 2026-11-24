"""Panorama's lifts and trails, and its snow report, from its daily snow report page
(panoramaresort.com/panorama-today/daily-snow-report).

The page is built on the server. Its trail table is a row for each trail under a row naming its zone (Champagne,
Discovery Zone, Extreme Dream Zone, Founder's Ridge, Mile One, Summit, Sun Bowl, Sunbird, Taynton Bowl, the
terrain park, Toby), which is its mountain area; the lifts name no zone and are an area of their own. A status is
the word in its row, in the words of the page's own legend: open, closed, on-hold, delayed and race in progress.
A trail's difficulty is the symbols in its row (a circle, a square, one diamond or two), and it is groomed when
its row carries the groomer's mark. A word or a symbol the reader does not know fails. The page's own count of
its trails, and of those open, is checked against what is read, so a change in its shape fails instead of showing
wrong numbers; its count of lifts leaves one of the listed lifts out and is not checked.

The snow report gives the snow depth at the village and at the summit, the new snow overnight and of the last 24
and 48 hours and 7 days, the season's snowfall, and the resort's own words. The page does not say where the
snowfall is measured: it is carried with the first depth it gives. **The page reports whole centimetres; they
are converted to inches here (divided by 2.54, to one decimal).** The page does not date its snow report (the time
over its tables is that of the lifts and trails), so it is undated here, and it gives no word for the surface.
Before the season the figures are empty and there is no snow report. A snow report that cannot be read costs only
the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://www.panoramaresort.com/panorama-today/daily-snow-report"
NAME = "Panorama"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The page's status words, from its own legend, as a status and how the app counts it.
STATUSES = {"open": "Open", "closed": "Closed", "on-hold": "On hold", "on hold": "On hold", "delayed": "Delayed",
            "race in progress": "Race in progress"}
# The difficulty symbols of a row, in the words the app's difficulty symbols are keyed on.
LEVELS = {("circular-shape-silhouette",): "Green", ("square",): "Blue", ("diamond",): "Black",
          ("diamond", "diamond"): "Double black"}
# The snow report's labels: the places with a depth, and the snowfall by the names the Ikon feed gives it.
STAKES = {"Village": "BaseArea", "Summit": "SummitArea"}
SNOWFALL = {"Overnight": "OvernightIn", "24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn",
            "7 Days": "Last7DaysIn", "Season": "SeasonTotalIn"}
TABLE = r"<div class=\"tabs-panel[^\"]*\" id=\"{name}-info\">.*?<tbody>(.*?)</tbody>"
ROW = re.compile(r"<tr class=\"strong\">\s*<td colspan=\"5\">(.*?)</td>\s*</tr>|"
                 r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>\s*<span class=\"label[^\"]*\">(.*?)</span>\s*</td>\s*"
                 r"<td>(.*?)</td>\s*<td>.*?</td>\s*</tr>", re.S)
LIFT = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>\s*<span class=\"label[^\"]*\">(.*?)</span>\s*</td>\s*<td>.*?</td>\s*"
                  r"</tr>", re.S)
SYMBOL = re.compile(r"<i class=\"fi flaticon-([a-z-]+)[ \"]")
GROOMED = "groomed-icon"
COUNTED = re.compile(r"<h4 class=\"margin-bottom-0\">\s*(\d+)<sup class=\"light-text\">/(\d+)</sup></h4>\s*"
                     r"<p[^>]*>\s*Trails Open\s*</p>")
SNOW_REPORT = re.compile(r"<div class=\"reports reports--block reports--snow[^\"]*\">(.*?)"
                         r"<div class=\"reports reports--block reports--weather", re.S)
FIGURE = re.compile(r"<h4 class=\"margin-bottom-0\">\s*([^<]*?)\s*<sup class=\"light-text\">\s*([^<]*?)\s*</sup></h4>"
                    r"\s*<p[^>]*>\s*([^<]*?)\s*</p>")
CELL = "summary-facilities__stat"
SAID = re.compile(r"Snow Information</h5>\s*<p[^>]*>(.*?)</p>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def table(page: str, name: str) -> str:
    found = re.search(TABLE.format(name=name), page, re.S)
    if not found:
        raise ValueError(f"the page's table of {name} was not found")
    return found.group(1)


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    name, said = words(name), words(said).lower()
    if not name or said not in STATUSES:
        raise ValueError(f"{name or 'a row'} has a status the reader does not know: {said!r}")
    status = STATUSES[said]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(name: str, level: str, said: str, groomed: str) -> dict:
    symbols = tuple(SYMBOL.findall(level))
    if symbols not in LEVELS:
        raise ValueError(f"{words(name) or 'a trail'} has difficulty symbols {list(symbols)}, not ones the reader knows")
    if groomed.strip() and GROOMED not in groomed:
        raise ValueError(f"{words(name)} has a grooming mark the reader does not know")
    row = status_row(name, said, LEVELS[symbols])
    row["Grooming"] = "Yes" if GROOMED in groomed else "No"
    return row


def zones(page: str) -> list:
    """The trails under each zone of the trail table, as a mountain area each, in the page's order."""
    body, areas = table(page, "trails"), []
    for zone, name, level, said, groomed in ROW.findall(body):
        if zone:
            areas.append({"Name": words(zone), "Lifts": [], "Trails": []})
        elif not areas:
            raise ValueError(f"{words(name)} is under no zone")
        else:
            areas[-1]["Trails"].append(trail_row(name, level, said, groomed))
    trails = [trail for area in areas for trail in area["Trails"]]
    if not trails or len(areas) + len(trails) != body.count("<tr"):
        raise ValueError(f"the trail table has {body.count('<tr')} rows but {len(areas) + len(trails)} were read")
    counted = COUNTED.search(page)
    if not counted:
        raise ValueError("the page's count of trails was not found")
    is_open = sum(trail["StatusEnglish"] == "open" for trail in trails)
    if (is_open, len(trails)) != (int(counted.group(1)), int(counted.group(2))):
        raise ValueError(f"the page counts {counted.group(1)} of {counted.group(2)} trails open but {is_open} of "
                         f"{len(trails)} were read")
    return [area for area in areas if area["Trails"]]


def lift_rows(page: str) -> list:
    body = table(page, "lifts")
    lifts = [status_row(name, said, None) for name, said in LIFT.findall(body)]
    if not lifts or len(lifts) != body.count("<tr"):
        raise ValueError(f"the lift table has {body.count('<tr')} rows but {len(lifts)} were read")
    return lifts


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: a depth at the village and the summit."""
    block = SNOW_REPORT.search(page)
    if not block:
        raise ValueError("the snow report was not found")
    depths, fallen, figures = {}, {}, FIGURE.findall(block.group(1))
    if len(figures) != block.group(1).count(CELL):
        raise ValueError(f"the snow report has {block.group(1).count(CELL)} figures but {len(figures)} were read")
    for said, unit, label in figures:
        label = html.unescape(label)
        if label not in STAKES and label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        if not said.isdigit() or unit != "cm" or label in depths or SNOWFALL.get(label) in fallen:
            raise ValueError(f"the snow report's {label} reads {said!r} {unit!r}, not centimetres given once")
        inches = round(int(said) / CM_PER_INCH, 1)
        if label in STAKES:
            depths[label] = inches
        else:
            fallen[SNOWFALL[label]] = inches
    if not depths or "Last24HoursIn" not in fallen:
        raise ValueError("the snow report has no snow depth or no 24 hour snowfall")
    season, said = fallen.pop("SeasonTotalIn", None), SAID.search(block.group(1))
    areas = {STAKES[label]: {"Name": label, "BaseIn": inches} for label, inches in depths.items()}
    # The page does not say where the snowfall is measured: it goes with the first depth the page gives.
    next(iter(areas.values())).update(fallen)
    return {"LastUpdate": None, "Resortwide": len(areas) == 1, "BaseConditions": None, "SeasonTotalIn": season,
            **areas, "Report": (words(said.group(1)) if said else "") or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lift_rows(page), "Trails": []}, *zones(page)]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
