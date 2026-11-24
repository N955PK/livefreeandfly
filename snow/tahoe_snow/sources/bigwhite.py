"""Big White's lifts and runs, and its snow report, from its lift status, grooming report and daily snow report
pages (bigwhite.com/mountain-conditions/lift-status-hours, /grooming-report and /daily-snow-report).

The three pages are built on the server, each with one block that holds the figures. The lift status block is a
row for each lift: its name, its hours, and its status in the page's own word ("Closed"), which is carried as the
page says it. The grooming report is a panel for each lift over the runs it serves; each lift is a mountain area
here, holding itself and its runs. A run's difficulty and status are the pictures in its row, read from the
pictures' names (closed, open, or groomed, which is an open run that has been groomed), and one the reader does
not know fails. The grooming report also lists what is not a ski run but opens and closes with the mountain (the
Nordic trails, the skating rink), as the page's own count of runs does. Each page's own count of what is closed is
checked against what is read, so a change in its shape fails instead of showing wrong numbers.

The snow report gives the alpine snow base, the new snow of the last 24 hours and 7 days and the season's
cumulative snowfall, under a line saying when it was updated with the zone it is told in ("MST": British Columbia
keeps one time all year). **The page reports whole centimetres; they are converted to inches here (divided by
2.54, to one decimal).** The page's own imperial figures are rounded to whole inches and are not used. Its word
for the surface is carried when it gives one. A snow report that cannot be read costs only the snow report, not
the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone

SITE = "https://www.bigwhite.com/mountain-conditions"
URLS = {"lifts": f"{SITE}/lift-status-hours", "trails": f"{SITE}/grooming-report", "snow": f"{SITE}/daily-snow-report"}
NAME = "Big White"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The zones the page may name its time in, as hours from UTC.
ZONES = {"MST": -7, "PDT": -7, "PST": -8}
# The run pictures' names, as a status and whether the run is groomed.
RUN_STATUSES = {"closed": ("Closed", "No"), "open": ("Open", "No"), "groomed": ("Open", "Yes")}
# The difficulty pictures' names, in the words the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double_black": "Double black"}
# The snow report's headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"New Snow (24hrs)": "Last24HoursIn", "New Snow (7 Days)": "Last7DaysIn", "Alpine snow Base": "BaseIn",
            "Cumulative snowfall": "SeasonTotalIn"}
BLOCK = r"<section id=\"block-{name}\"[^>]*>(.*?)</section>"
LIFT = re.compile(r"<div class=\"small-12 columns [a-z_]+\">\s*<strong[^>]*>(.*?)</strong>(?:(?!<strong).)*?<i>(.*?)</i>",
                  re.S)
PANEL = re.compile(r"<div class=\"panel\">\s*<strong[^>]*>(.*?)</strong>", re.S)
RUN = re.compile(r"<div class=\"small-1 columns text-center icon\">(.*?)</div>\s*"
                 r"<div class=\"small-10 columns run-name\">\s*([^<]*?)\s*<div>.*?</div>\s*</div>\s*"
                 r"<div class=\"small-1 left columns text-center icon\">(.*?)</div>", re.S)
RUN_LINE = "<div class=\"row run-line\">"
PICTURE = re.compile(r"<img[^>]*\salt=\"([^\"]*)\"")
CLOSED = re.compile(r"alt=\"closed\"\s*/>\s*Closed\s*\((\d+)\)", re.I)
TAG = re.compile(r"<[^>]+>")
UPDATED = re.compile(r"Last Updated:\s*<strong>\s*([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th),? (\d{4}) (\d{1,2}):(\d{2}) "
                     r"([AP]M) ([A-Z]{2,4})\s*</strong>")
METRIC = re.compile(r"<div id=\"metric\"[^>]*>(.*?)<div id=\"imperial\"", re.S)
FIGURE = re.compile(r"([A-Za-z][A-Za-z0-9 ()]*?)\s*<br />\s*<span class=\"bigger-font\">\s*([^<]*?)\s*</span>")
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*cm")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def block(page: str, name: str) -> str:
    found = re.search(BLOCK.format(name=name), page, re.S)
    if not found:
        raise ValueError(f"the page's {name} was not found")
    return found.group(1)


def closed_counted(part: str, what: str) -> int:
    """The page's own count of its closed lifts or runs."""
    found = CLOSED.search(part)
    if not found:
        raise ValueError(f"the page's count of closed {what} was not found")
    return int(found.group(1))


def checked(rows: list, part: str, what: str) -> list:
    closed = sum(row["StatusEnglish"] == "closed" for row in rows)
    if closed != closed_counted(part, what):
        raise ValueError(f"the page counts {closed_counted(part, what)} closed {what} but {closed} were read")
    return rows


def lift_rows(page: str) -> list:
    part = block(page, "liftstatusblock")
    lifts = []
    for name, said in LIFT.findall(part):
        name, status = words(name), words(said).capitalize()
        if not name or not status:
            raise ValueError(f"{name or 'a lift'} has no name or no status")
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    if not lifts or len(lifts) != part.count("<strong style="):
        raise ValueError(f"the lift status lists {part.count('<strong style=')} lifts but {len(lifts)} were read")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the lift status lists a lift twice")
    return checked(lifts, part, "lifts")


def run_row(level: str, name: str, status: str) -> dict:
    name = html.unescape(name).strip()
    levels, statuses = PICTURE.findall(level), {said.lower() for said in PICTURE.findall(status)}
    if not name or len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name or 'a run'} has difficulty pictures {levels}, not one the reader knows")
    if not statuses or statuses - set(RUN_STATUSES) or ("closed" in statuses and len(statuses) > 1):
        raise ValueError(f"{name} has status pictures {sorted(statuses)}, not ones the reader knows")
    said, groomed = RUN_STATUSES["groomed" if "groomed" in statuses else statuses.pop()]
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": LEVELS[levels[0]],
            "Grooming": groomed}


def run_panels(page: str) -> dict:
    """The runs under each lift of the grooming report, by the lift's name, in the page's order."""
    part = block(page, "groomingreportblock")
    heads = list(PANEL.finditer(part))
    panels = {}
    for head, after in zip(heads, [*heads[1:], None]):
        piece = part[head.end():after.start() if after else len(part)]
        runs = [run_row(*found) for found in RUN.findall(piece)]
        if len(runs) != piece.count(RUN_LINE):
            raise ValueError(f"{words(head.group(1))} lists {piece.count(RUN_LINE)} runs but {len(runs)} were read")
        panels.setdefault(words(head.group(1)), []).extend(runs)
    runs = [run for each in panels.values() for run in each]
    if not runs or len(runs) != part.count(RUN_LINE):
        raise ValueError(f"the grooming report lists {part.count(RUN_LINE)} runs but {len(runs)} were read")
    checked(runs, part, "runs")
    return panels


def updated(part: str) -> str:
    """When the snow report was updated, in UTC, from the zone the page names."""
    found = UPDATED.search(part)
    if not found:
        raise ValueError("the snow report does not say when it was updated")
    month, day, year, hour, minute, half, zone = found.groups()
    if zone not in ZONES:
        raise ValueError(f"the snow report's time is in {zone}, a zone the reader does not know")
    # The page writes the afternoon both ways: "1:12 PM" and "18:58 PM".
    hour = int(hour) if int(hour) > 12 else int(hour) % 12 + (12 if half == "PM" else 0)
    try:
        at = datetime.strptime(f"{year} {month} {day}", "%Y %B %d").replace(hour=hour, minute=int(minute))
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return (at.replace(tzinfo=timezone.utc) - timedelta(hours=ZONES[zone])).strftime(STAMP)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, measured in the alpine."""
    part = block(page, "snowreportblock")
    metric = METRIC.search(part)
    if not metric:
        raise ValueError("the snow report's metric figures were not found")
    figures, surface = {}, None
    for heading, said in FIGURE.findall(metric.group(1)):
        if heading == "Conditions":
            surface = html.unescape(said).strip() or None
        if heading not in SNOWFALL:
            continue
        centimetres = CENTIMETRES.fullmatch(html.unescape(said).replace("\xa0", " ").strip())
        if not centimetres or SNOWFALL[heading] in figures:
            raise ValueError(f"the snow report's {heading} reads {said!r}, not centimetres given once")
        figures[SNOWFALL[heading]] = round(float(centimetres.group(1)) / CM_PER_INCH, 1)
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no alpine base or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": updated(part), "Resortwide": True, "BaseConditions": surface, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Alpine", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    lifts, panels = lift_rows(pages["lifts"]), run_panels(pages["trails"])
    areas = [{"Name": lift["Name"], "Lifts": [lift], "Trails": panels.pop(lift["Name"], [])} for lift in lifts]
    # A panel of the grooming report under a name the lift status does not have keeps its runs, with no lift.
    areas += [{"Name": name, "Lifts": [], "Trails": runs} for name, runs in panels.items() if runs]
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(pages["snow"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
