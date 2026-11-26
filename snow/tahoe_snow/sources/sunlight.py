"""Sunlight's lifts and trails, and its snow report, from its mountain status page
(sunlightmtn.com/explore/mountain-status).

The page is built on the server. Under "LIFTS" is a list of the lifts, each a name and its status in words, carried
as the page says it. Under "Trail Status" is a group of trails for each difficulty, each trail a name, whether it
is groomed and its status in words. A group's difficulty is the name the page gives the group (green circle, blue
square, black diamond, double black diamond, terrain parks, which have none), and a name the reader does not know
fails. The group of uphill routes is not of the lift-served mountain and is left out. Each group's own count of
its trails, and the page's counts of its lifts and of its trails in all, are checked against what is read, so a
change in the page's shape fails instead of showing wrong numbers. The mountain is one mountain area holding all
of them.

The snow report gives the snow since 4pm and over the last 24 and 48 hours, the base depth and the season's
total, in inches, and the surface as the page's own code, carried as words. The page does not say when it was
written, so the report is undated. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://sunlightmtn.com/explore/mountain-status/"
NAME = "Sunlight"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The names of the groups of trails, in the words the app's difficulty symbols are keyed on; parks have none.
LEVELS = {"GREEN_CIRCLE": "Green", "BLUE_SQUARE": "Blue", "BLACK_DIAMOND": "Black",
          "DOUBLE_BLACK_DIAMOND": "Double black", "TERRAIN_PARKS": ""}
# The groups that are not of the lift-served mountain, by their headings.
LEFT_OUT = frozenset({"UPHILL ROUTES"})
# A trail's grooming, in the words the app reads; the page's "UNDEF" says nothing either way.
GROOMED = {"GROOMED": "Yes", "NOT_GROOMED": "No", "UNDEF": None}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Since 4PM": "SinceLiftsClosedIn", "Last 24 Hours": "Last24HoursIn", "Last 48 Hours": "Last48HoursIn",
            "Base Depth": "BaseIn"}
STATUS = re.compile(r"<h4 class=\"elementor-heading-title[^\"]*\">SNOWFALL</h4>(.*?)"
                    r"<h4 class=\"elementor-heading-title[^\"]*\">LIFTS</h4>(.*?)</ul>", re.S)
BOX = re.compile(r"<span class=\"elementor-icon-box-title\">(.*?)</span>\s*</span>\s*"
                 r"<p class=\"elementor-icon-box-description\">(.*?)</p>", re.S)
LIFT = re.compile(r"<li>\s*<span class=\"[^\"]*\">(.*?)</span>\s*<span class=\"[^\"]*\">(.*?)</span>\s*</li>", re.S)
TRAILS = re.compile(r"<div class=\"trl_stuts\">(.*)", re.S)
GROUP = re.compile(r"<div class=\"stuts_rw\" data-level=\"([A-Z_]*)\">\s*<div class=\"stuts_itm\">\s*"
                   r"<span class=\"lvl\">(.*?)</span>\s*<span class=\"opn_stus\">\s*(\d+)\s*/\s*(\d+) Open\s*</span>", re.S)
TRAIL = re.compile(r"<li>\s*<div class=\"trl_nm\">(.*?)<span>\(([A-Z_]*)\)</span>\s*</div>\s*"
                   r"<div class=\"trl_opn[^\"]*\">(.*?)</div>\s*</li>", re.S)
ROWS = "<div class=\"trl_nm\">"
COUNT = re.compile(r"(\d+)\s*/\s*(\d+)")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    if not name or not said or not said.replace(" ", "").isalpha():
        raise ValueError(f"{name or 'a row'} has the status {said!r}, not a word")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_rows(page: str) -> tuple:
    """The trails of the lift-served mountain in the page's order, and how many rows the page has in all."""
    found = TRAILS.search(page)
    if not found:
        raise ValueError("the trail status was not found")
    body = found.group(1)
    groups = list(GROUP.finditer(body))
    trails, read = [], 0
    for at, group in enumerate(groups):
        level, heading, listed = group.group(1), words(group.group(2)), int(group.group(4))
        end = groups[at + 1].start() if at + 1 < len(groups) else len(body)
        rows = TRAIL.findall(body[group.end():end])
        read += len(rows)
        if len(rows) != listed:
            raise ValueError(f"the page counts {listed} trails under {heading} but {len(rows)} were read")
        if heading in LEFT_OUT:
            continue
        if level not in LEVELS:
            raise ValueError(f"the trails under {heading} have a difficulty the reader does not know: {level}")
        for name, groomed, said in rows:
            if groomed not in GROOMED:
                raise ValueError(f"{words(name)}'s grooming reads {groomed!r}, which the reader does not know")
            trail = status_row(words(name), words(said), LEVELS[level])
            if GROOMED[groomed]:
                trail["Grooming"] = GROOMED[groomed]
            trails.append(trail)
    if not trails or read != body.count(ROWS):
        raise ValueError(f"the page has {body.count(ROWS)} trail rows but {read} were read")
    return trails, read


def counted(figures: dict, label: str) -> int:
    """The page's own count of its lifts or its trails in all."""
    found = COUNT.fullmatch(figures.get(label, ""))
    if not found:
        raise ValueError(f"the page's count of {label.lower()} was not found")
    return int(found.group(2))


def snow_report(figures: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    area = {"Name": "Mountain"}
    for label, field in SNOWFALL.items():
        said = INCHES.fullmatch(figures.get(label, ""))
        if not said:
            raise ValueError(f"the snow report's {label} reads {figures.get(label)!r}, not inches")
        value = float(said.group(1))
        area[field] = int(value) if value.is_integer() else value
    season = INCHES.fullmatch(figures.get("Season Total", ""))
    surface = figures.get("Primary Surface", "")
    return {"LastUpdate": None, "Resortwide": True,
            "BaseConditions": surface.replace("_", " ").capitalize() if surface not in ("", "UNDEF") else None,
            "SeasonTotalIn": float(season.group(1)) if season else None, "BaseArea": area, "Report": None,
            "Alert": None}


def parse(page: str, now: datetime) -> dict:
    status = STATUS.search(page)
    if not status:
        raise ValueError("the current status and its list of lifts were not found")
    figures = {words(label): words(said) for label, said in BOX.findall(status.group(1))}
    lifts = [status_row(words(name), words(said), None) for name, said in LIFT.findall(status.group(2))]
    trails, rows = trail_rows(page)
    if not lifts or len(lifts) != status.group(2).count("<li>") or len(lifts) != counted(figures, "Open Lifts"):
        raise ValueError(f"the page counts {figures.get('Open Lifts')} lifts but {len(lifts)} were read")
    if rows != counted(figures, "Open Trails"):
        raise ValueError(f"the page counts {figures.get('Open Trails')} trails but {rows} were read")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
    try:
        feed["SnowReport"] = snow_report(figures)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
