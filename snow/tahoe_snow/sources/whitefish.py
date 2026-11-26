"""Whitefish's lifts and trails, and its snow report, from its snow report page
(skiwhitefish.com/snowreport).

The page is built on the server. Under "Open/Closed/Groomed" it has a section for each lift, "Chair 1 - Big
Mountain Express", holding the lift's status and the trails it serves; each is a mountain area here, holding itself
and its trails. The section "Terrain Parks" is not a lift and is an area with trails only. A status is a picture,
read from the word the page gives with it (Open, Closed, Groomed), and the picture's own name has to say the same;
a lift's is carried as that word. A trail said to be groomed is open and groomed, and grooming is carried only on a
day the page says it of some trail. A trail's difficulty is a small drawing, told by its shape (a circle, a square,
one diamond or two), and a drawing the reader does not know fails. Every trail row in the page is one read, and
every section has to have a status, so a change in the page's shape fails instead of showing wrong numbers. The
page's two counts, "Open" and "Groomed", are not used: it does not say what they count.

The snow report is "The Stats": at the summit the snow overnight, in the last 24 hours and 7 days, the settled
depth and the season's total, and at the base area the snow of the last 24 hours and 7 days (natural snow only, so
no depth is given there), in inches. The report's day is the one its story opens with, and the page says the
figures are measured around 6 a.m., in Mountain time; a story with no day leaves the report undated. It gives no
word for the surface. A snow report that cannot be read costs only the snow report, not the lifts. Standard library
only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://skiwhitefish.com/snowreport/"
NAME = "Whitefish"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MOUNTAIN_TIME = ZoneInfo("America/Denver")
# The hour the page says its figures are measured at.
MEASURED_AT = 6
# The section of the page that lists trails under no lift.
PARKS = "Terrain Parks"
# The stats' labels at each stake, by the names the Ikon feed gives them (the app reads those).
STAKES = {"Summit": "SummitArea", "Base Area": "BaseArea"}
SNOWFALL = {"Overnight Fresh": "OvernightIn", "Past 24 Hours": "Last24HoursIn", "Past 7 Days": "Last7DaysIn",
            "Settled Base": "BaseIn", "Season to Date": "SeasonTotalIn"}
SECTION = "<div class=\"wmr-lift-section\">"
SECTION_NAME = re.compile(r"<div class=\"wmr-accordion-header\">\s*<span>(.*?)</span>", re.S)
STATUS_BAR = re.compile(r"<div class=\"wmr-lift-status-bar\">(.*?)<div class=\"wmr-run-container\">", re.S)
RUN = re.compile(r"<div class=\"wmr-run-row\">\s*<div class=\"wmr-col\"[^>]*>(.*?)</div>\s*"
                 r"<div class=\"wmr-col wmr-col-name\">(.*?)</div>\s*<div class=\"wmr-col wmr-col-status\">(.*?)</div>",
                 re.S)
PICTURE = re.compile(r"<img\b[^>]*\salt=\"([^\"]*)\"[^>]*\ssrc=\"[^\"]*/is_([a-z_]+)\.svg\"")
SHAPE = re.compile(r"<(circle|rect|path)\b")
# The drawings' shapes, in the words the app's difficulty symbols are keyed on. A row with no drawing has none.
LEVELS = {("circle",): "Green", ("rect",): "Blue", ("path",): "Black", ("path", "path"): "Double black", (): ""}
GROUP = re.compile(r"<div class=\"wmr_snow_stat_group_header\">(.*?)<em\b.*?</div>(.*?)</div>\s*"
                   r"(?=<div class=\"wmr_snow_(?:stat_group|disclaimer)\"|</div>)", re.S)
STAT = re.compile(r"<span class=\"wmr_snow_stat_label\">(.*?)</span>\s*"
                  r"<span class=\"wmr_snow_stat_value\">(.*?)</span>", re.S)
STORY_DAY = re.compile(r"<div class=\"wmr_snow_story_text\">\s*<p>\s*<strong>\s*[A-Z][a-z]+, ([A-Z][a-z]{2})[a-z]*\.? "
                       r"(\d{1,2}), (\d{4})")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def said_by(markup: str, name: str) -> str:
    """The word of the one status picture in a piece of the page."""
    pictures = PICTURE.findall(markup)
    if len(pictures) != 1 or not pictures[0][0].strip():
        raise ValueError(f"{name} has {len(pictures)} status pictures with a word, not one")
    said, drawn = pictures[0]
    if "_".join(said.lower().split()) != drawn:
        raise ValueError(f"{name}'s status picture is {drawn} but reads {said!r}")
    return " ".join(said.split()).capitalize()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(drawing: str, name: str, status: str) -> dict:
    name = words(name)
    if not name:
        raise ValueError("a trail row has no name")
    shape = tuple(SHAPE.findall(drawing))
    if shape not in LEVELS:
        raise ValueError(f"{name} has a difficulty drawing the reader does not know: {' and '.join(shape)}")
    said = said_by(status, name)
    if said == "Groomed":
        return {**status_row(name, "Open", LEVELS[shape]), "Grooming": "Yes"}
    return status_row(name, said, LEVELS[shape])


def lift_areas(page: str) -> list:
    """Each lift with the trails under it, and the terrain parks, in the page's order."""
    areas, read = [], 0
    for section in page.split(SECTION)[1:]:
        name, bar = SECTION_NAME.search(section), STATUS_BAR.search(section)
        if not name or not words(name.group(1)) or not bar:
            raise ValueError("a section of the lift list has no name or no status")
        name = words(name.group(1))
        status = said_by(bar.group(1), name)
        trails = [trail_row(*row) for row in RUN.findall(section)]
        read += len(trails)
        lifts = [] if name == PARKS else [status_row(name, status, None)]
        areas.append({"Name": name, "Lifts": lifts, "Trails": trails})
    listed = page.count("<div class=\"wmr-run-row\">")
    if not areas or not read or read != listed:
        raise ValueError(f"the page has {listed} trail rows but {read} were read")
    if not any(area["Lifts"] for area in areas):
        raise ValueError("the page lists no lifts")
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists a lift twice")
    # The page says which trails are groomed only by calling them groomed: on a day it does, the others are not.
    trails = [trail for area in areas for trail in area["Trails"]]
    if any("Grooming" in trail for trail in trails):
        for trail in trails:
            trail.setdefault("Grooming", "No")
    return areas


def snow_report(page: str) -> dict:
    """The page's stats in the shape of the Ikon feed's SnowReport: the summit, and the base area's snowfall."""
    out = {"BaseArea": {"Name": "Base Area"}, "SummitArea": {"Name": "Summit"}}
    seen = set()
    for stake, body in GROUP.findall(page):
        stake = words(stake)
        if stake not in STAKES or stake in seen:
            raise ValueError(f"the stats are given for a place the reader does not know, or twice: {stake}")
        seen.add(stake)
        for label, said in STAT.findall(body):
            label, inches = words(label), INCHES.fullmatch(words(said))
            if label not in SNOWFALL or SNOWFALL[label] in out[STAKES[stake]]:
                raise ValueError(f"the stats at the {stake} have a figure the reader does not know, or twice: {label}")
            if not inches:
                raise ValueError(f"the stats' {label} at the {stake} reads {words(said)!r}, not inches")
            value = float(inches.group(1))
            out[STAKES[stake]][SNOWFALL[label]] = int(value) if value.is_integer() else value
    summit = out["SummitArea"]
    if "BaseIn" not in summit or "Last24HoursIn" not in summit:
        raise ValueError("the stats have no settled base or no 24 hour snowfall at the summit")
    posted, day = None, STORY_DAY.search(page)
    if day:
        try:
            at = datetime.strptime(" ".join(day.groups()), "%b %d %Y").replace(hour=MEASURED_AT, tzinfo=MOUNTAIN_TIME)
        except ValueError as error:
            raise ValueError(f"the story's day could not be read: {error}") from error
        posted = at.astimezone(timezone.utc).strftime(STAMP)
    season = summit.pop("SeasonTotalIn", None)
    out["BaseArea"].pop("SeasonTotalIn", None)
    # The base area's figures are of natural snow only, and the page gives no depth there.
    out["BaseArea"].setdefault("BaseIn", None)
    return {"LastUpdate": posted, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season, **out,
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": lift_areas(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
