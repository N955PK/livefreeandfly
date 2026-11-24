"""Mt. Norquay's lifts and runs, and its snow report, from its conditions page (banffnorquay.com/conditions).

The page is built on the server. Its lift and run status is a panel for each lift (the chairs and the carpets):
the lift's name with its status in the page's own word, open or closed, over the runs it serves; each lift is a
mountain area here, holding itself and its runs. The tube park, which the page lists after the lifts, is not
one and is left out. A run's difficulty, its status and whether it is groomed are
marks on its row, read from the marks' names, and a word or a mark the reader does not know fails. The page's own
count of open runs is checked against what is read, so a change in its shape fails instead of showing wrong
numbers. (Its count of all runs has been one more than it lists, so that is not checked.)

The snow report gives the new snow overnight and of the last 24 hours and 7 days, and the snow base and the
year's snowfall at the lower and the upper mountain. The page does not say where the new snow is measured: it is
carried with the lower mountain's base. The season's snowfall is the upper mountain's. The page gives no time for
the report, only the day in the heading of the day's update ("Conditions update for Tuesday, November 24.");
that day's start, in the resort's own time, is carried, with the latest year that does not put it after the time
of reading, and a page without the heading has an undated report. **The page reports whole centimetres; they are
converted to inches here (divided by 2.54, to one decimal).** The page gives no word for the surface. A snow
report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://banffnorquay.com/conditions/"
NAME = "Mt. Norquay"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Edmonton")
CM_PER_INCH = 2.54
STATUSES = {"open": "Open", "closed": "Closed"}
# The run marks' names, in the words the app's difficulty symbols are keyed on, and whether the run is groomed.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black"}
GROOMED = {"groomed": "Yes", "ungroomed": "No"}
# The snow report's figures, by the heading over them and the words under them, as where they are carried.
FIGURES = {("New Snow", "Overnight"): ("BaseArea", "OvernightIn"),
           ("New Snow", "Last 24 Hours"): ("BaseArea", "Last24HoursIn"),
           ("New Snow", "Last 7 Days"): ("BaseArea", "Last7DaysIn"),
           ("Snow Base - Lower Mountain", "Lower Mountain"): ("BaseArea", "BaseIn"),
           ("Snow Base - Lower Mountain", "Year to Date Snowfall"): ("BaseArea", "SeasonTotalIn"),
           ("Snow Base - Upper Mountain", "Upper Mountain"): ("SummitArea", "BaseIn"),
           ("Snow Base - Upper Mountain", "Year to Date Snowfall"): ("SummitArea", "SeasonTotalIn")}
NAMES = {"BaseArea": "Lower Mountain", "SummitArea": "Upper Mountain"}
STATUS_BLOCK = re.compile(r"id=\"liftstatus\"(.*)", re.S)
PANEL = re.compile(r"<div class=\"jet-toggle__label-text\">(.*?)<span class=\"lift-status is-([a-z-]+)\">(.*?)</span>"
                   r"\s*</div>", re.S)
RUN = re.compile(r"<span class=\"run-difficulty difficulty-([a-z-]+)\"></span>.*?"
                 r"<div class=\"jet-listing-dynamic-field__content\"\s*>([^<]*)</div>.*?"
                 r"<span class=\"run-status status-([a-z-]+)\"></span>.*?"
                 r"<span class=\"run-groomed groomed-([a-z-]+)\"></span>", re.S)
RUN_MARK = "<span class=\"run-status "
LIFT_MARK = "<div class=\"jet-toggle__label-text\">"
RUNS_OPEN = re.compile(r">\s*Runs Open:\s*</p>.*?>\s*(\d+) of\s*</p>", re.S)
SNOW_BLOCK = re.compile(r">\s*Current Snowfall\s*</h3>(.*?)>\s*Today(?:&#8217;|&#039;|'|’)s Forecast\s*<", re.S)
HEADING = re.compile(r"<(?:h\d|p) class=\"elementor-heading-title[^\"]*\">(.*?)</(?:h\d|p)>", re.S)
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*cm")
UPDATE = re.compile(r"Conditions update for [A-Z][a-z]+day, ([A-Z][a-z]+) (\d{1,2})(?:st|nd|rd|th)?\b")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_row(name: str, mark: str, said: str) -> dict:
    name, said = words(name), words(said)
    if not name or said.lower() not in STATUSES or mark != said.lower():
        raise ValueError(f"{name or 'a lift'} has a status the reader does not know: {said!r} ({mark})")
    status = STATUSES[said.lower()]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def run_row(level: str, name: str, status: str, groomed: str) -> dict:
    name = html.unescape(name).strip()
    if not name or level not in LEVELS:
        raise ValueError(f"{name or 'a run'} has a difficulty the reader does not know: {level}")
    if status not in STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {status}")
    if groomed not in GROOMED:
        raise ValueError(f"{name} has a grooming the reader does not know: {groomed}")
    return {"Name": name, "Status": STATUSES[status], "StatusEnglish": status, "Difficulty": LEVELS[level],
            "Grooming": GROOMED[groomed]}


def mountain_areas(page: str) -> list:
    """Each lift of the lift and run status with the runs under it, in the page's order."""
    found = STATUS_BLOCK.search(page)
    if not found:
        raise ValueError("the page's lift and run status was not found")
    block = found.group(1)
    heads = list(PANEL.finditer(block))
    areas = []
    for head, after in zip(heads, [*heads[1:], None]):
        lift = lift_row(*head.groups())
        piece = block[head.end():after.start() if after else len(block)]
        runs = [run_row(*run) for run in RUN.findall(piece)]
        if len(runs) != piece.count(RUN_MARK):
            raise ValueError(f"{lift['Name']} lists {piece.count(RUN_MARK)} runs but {len(runs)} were read")
        areas.append({"Name": lift["Name"], "Lifts": [lift], "Trails": runs})
    if not areas or len(areas) != block.count(LIFT_MARK):
        raise ValueError(f"the page lists {block.count(LIFT_MARK)} lifts but {len(areas)} were read")
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists a lift twice")
    counted = RUNS_OPEN.search(block)
    if not counted:
        raise ValueError("the page's count of open runs was not found")
    opened = sum(run["StatusEnglish"] == "open" for area in areas for run in area["Trails"])
    if opened != int(counted.group(1)):
        raise ValueError(f"the page counts {counted.group(1)} open runs but {opened} were read")
    return areas


def updated(page: str, now: datetime) -> str | None:
    """The start of the day the page's update is headed with, in UTC, or None where it names no day. The heading
    gives no year: it is the latest that does not put the day more than a day after the time of reading."""
    found = UPDATE.search(page)
    if not found:
        return None
    month, day = found.groups()
    for year in (now.year, now.year - 1):
        try:
            at = datetime.strptime(f"{year} {month} {day}", "%Y %B %d")
        except ValueError:
            return None
        at = at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc)
        if at <= now + timedelta(days=1):
            return at.strftime(STAMP)
    return None


def snow_report(page: str, now: datetime) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: the lower and the upper mountain."""
    found = SNOW_BLOCK.search(page)
    if not found:
        raise ValueError("the snow report was not found")
    stakes, group, figure = {key: {"Name": name} for key, name in NAMES.items()}, None, None
    # The figures come as a heading (the group), then pairs of a figure and the words under it.
    for said in (words(heading) for heading in HEADING.findall(found.group(1))):
        centimetres = CENTIMETRES.fullmatch(said)
        if centimetres:
            figure = float(centimetres.group(1))
        elif figure is None:
            group = said
        else:
            if (group, said) not in FIGURES or FIGURES[group, said][1] in stakes[FIGURES[group, said][0]]:
                raise ValueError(f"the snow report has a figure the reader does not know, or has it twice: "
                                 f"{group}, {said}")
            key, field = FIGURES[group, said]
            stakes[key][field], figure = round(figure / CM_PER_INCH, 1), None
    if figure is not None:
        raise ValueError("the snow report ends on a figure with no words under it")
    if any("BaseIn" not in stake for stake in stakes.values()) or "Last24HoursIn" not in stakes["BaseArea"]:
        raise ValueError("the snow report has no lower or upper base or no 24 hour snowfall")
    season = stakes["SummitArea"].pop("SeasonTotalIn", None)
    stakes["BaseArea"].pop("SeasonTotalIn", None)
    return {"LastUpdate": updated(page, now), "Resortwide": False, "BaseConditions": None, "SeasonTotalIn": season,
            **stakes, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": mountain_areas(page)}
    try:
        feed["SnowReport"] = snow_report(page, now)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
