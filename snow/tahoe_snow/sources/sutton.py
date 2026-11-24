"""Mont Sutton's lifts and trails, and its snow report, from its conditions page (montsutton.com/en/conditions),
read in English.

The page is built on the server: a table of chairlifts, a table of trails, and a conditions block with the page's
own counts, the snow of the last days and the state of the magic carpets. The chairlifts are named only by their
numbers (I, II, IV Ouest), so each is given here as "Chairlift I"; the magic carpets, which the page gives one
status for, follow them as one lift under the page's own name. A lift's or trail's status is the word in its row.
The words the reader knows are Open, Closed and On hold, and their French (ouvert/ouverte -> Open, fermé/fermée ->
Closed, en attente -> On hold) in case the page falls back to it; any other word fails. A trail's difficulty is
the picture beside its name, read from the picture's name (facile -> Green, moyenne -> Blue, difficile -> Black,
extreme -> Double black); a trail with two is given the harder, and one the reader does not know fails. A trail's
surface word is carried as its grooming (groomed, or damé in French, is "Yes"). The page shows its lists twice
(once in a drawer), and splits some trails into a top and a bottom: a row repeated word for word is read once.
The page's own count of chairlifts has to match what is read, and its count of trails, which takes a split trail
as one, must not be more than the rows read, so a change in the page's shape fails instead of showing wrong
numbers.

The snow report gives the snow of the last 24 hours, 48 hours and 7 days and the season's total, under the time
it was written in Eastern time. **The page reports centimetres; they are converted to inches here (divided by
2.54, rounded to one decimal).** The page gives no base depth, so ``BaseIn`` is None, and no word for the surface
of the whole mountain. A snow report that cannot be read costs only the snow report, not the lifts. Standard
library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://montsutton.com/en/conditions/"
NAME = "Mont Sutton"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The page's status words, English and French, in the words the app shows.
STATUSES = {"open": "Open", "ouvert": "Open", "ouverte": "Open", "closed": "Closed", "fermé": "Closed",
            "fermée": "Closed", "on hold": "On hold", "standby": "On hold", "en attente": "On hold"}
# The difficulty pictures from the easiest to the hardest, in the words the app's difficulty symbols are keyed on.
LEVELS = {"type_piste_facile": "Green", "type_piste_moyenne": "Blue", "type_piste_difficile": "Black",
          "type_piste_extreme": "Double black"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 h": "Last24HoursIn", "48 h": "Last48HoursIn", "7 days": "Last7DaysIn", "cumulative": "SeasonTotalIn"}
CARPETS = "tapis magiques"
LIFTS = re.compile(r"<section class=\"flexible_statuts -telesieges[^\"]*\">(.*?)</section>", re.S)
LIFT = re.compile(r"<div class=\"flexible_statuts_list_row js-pistes-row\"[^>]*>(.*?)"
                  r"(?=<div class=\"flexible_statuts_list_row|\Z)", re.S)
LIFT_CELL = re.compile(r"<div class=\"flexible_statuts_list_cell[^\"]*\">(.*?)</div>", re.S)
TRAIL = re.compile(r"<div class=\"flexible_liste_des_pistes_list_row js-pistes-row\"[^>]*>(.*?)"
                   r"(?=<div class=\"flexible_liste_des_pistes_list_row|</section>|\Z)", re.S)
TRAIL_CELL = re.compile(r"<div class=\"flexible_liste_des_pistes_list_cell[^\"]*\">(.*?)</div>", re.S)
LEVEL_PICTURES = re.compile(r"<span class=\"flexible_liste_des_pistes_list_levels[^\"]*\"[^>]*>(.*?)</span>", re.S)
PICTURE = re.compile(r"<img[^>]*\sdata-src=\"[^\"]*/([^\"/]+)\.svg\"")
NOSCRIPT = re.compile(r"<noscript>.*?</noscript>", re.S)
TAG = re.compile(r"<[^>]+>")
COUNTED = re.compile(r"<span class=\"flexible_conditions_list_stats_item_label\">\s*{label}\s*</span>\s*"
                     r"<span class=\"flexible_conditions_list_stats_item_value\">\s*\d+\s*/\s*(\d+)\s*</span>")
STATED = re.compile(r"<span class=\"flexible_conditions_list_status_item_label\">(.*?)</span>\s*"
                    r"<span class=\"flexible_conditions_list_status_item_tag[^\"]*\">(.*?)</span>", re.S)
FIGURE = re.compile(r"<span class=\"flexible_conditions_list_snow_item_label\">(.*?)</span>\s*"
                    r"<span class=\"flexible_conditions_list_snow_item_value\">(.*?)</span>\s*</span>", re.S)
CENTIMETRES = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm")
WRITTEN = re.compile(r"<span class=\"flexible_conditions_header_date\">\s*(\d{1,2}) ([A-Za-z]+) (\d{4})\s*"
                     r"(?:&#8211;|&ndash;|–|-)\s*(\d{1,2})\s*H\s*(\d{1,2})\s*MIN\s*</span>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float | int:
    value = round(centimetres / 2.54, 1)
    return int(value) if value.is_integer() else value


def status_of(said: str, name: str) -> str:
    if said.lower() not in STATUSES:
        raise ValueError(f"{name} has the status {said!r}, not one the reader knows")
    return STATUSES[said.lower()]


def counted(page: str, label: str) -> int:
    """The page's own count of all its chairlifts or trails."""
    found = re.search(COUNTED.pattern.format(label=label), page)
    if not found:
        raise ValueError(f"the page's count of {label.lower()} was not found")
    return int(found.group(1))


def lift_rows(page: str) -> list:
    table = LIFTS.search(page)
    if not table:
        raise ValueError("the table of chairlifts was not found")
    lifts = []
    for row in LIFT.findall(table.group(1)):
        cells = [words(cell) for cell in LIFT_CELL.findall(row)]
        if len(cells) != 3 or not cells[0]:
            raise ValueError("a row of the chairlift table is not a name, a type and a status")
        name = f"Chairlift {cells[0]}"
        status = status_of(cells[2], name)
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    if len(lifts) != counted(page, "Chairlifts"):
        raise ValueError(f"the page counts {counted(page, 'Chairlifts')} chairlifts but {len(lifts)} were read")
    for label, said in STATED.findall(page):
        if words(label).lower() == CARPETS:
            status = status_of(words(said), words(label))
            lifts.append({"Name": words(label), "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
            break
    return lifts


def trail_rows(page: str) -> list:
    """The trails in the page's order, a row repeated word for word read once."""
    trails = []
    for row in TRAIL.findall(NOSCRIPT.sub("", page)):
        cells = TRAIL_CELL.findall(row)
        if len(cells) != 5:
            raise ValueError("a row of the trail table is not a number, a name, a status, a surface and a type")
        pictures = LEVEL_PICTURES.search(cells[1])
        name = words(LEVEL_PICTURES.sub("", cells[1]))
        if not name:
            raise ValueError("a row of the trail table has no name")
        levels = PICTURE.findall(pictures.group(1) if pictures else "")
        if not levels or any(level not in LEVELS for level in levels):
            raise ValueError(f"{name} has difficulty pictures {levels}, not ones the reader knows")
        status = status_of(words(cells[2]), name)
        surface = words(cells[3]).lower()
        trail = {"Name": name, "Status": status, "StatusEnglish": status.lower(),
                 "Difficulty": LEVELS[max(levels, key=list(LEVELS).index)],
                 "Grooming": "Yes" if surface.startswith(("groomed", "damé")) else "No"}
        if trail not in trails:
            trails.append(trail)
    return trails


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    written = WRITTEN.search(page)
    if not written:
        raise ValueError("the snow report does not say when it was written")
    day, month, year, hour, minute = written.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute}", "%Y %B %d %H:%M")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    figures = {}
    for label, said in FIGURE.findall(page):
        label = words(label).lower()
        if label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        centimetres = CENTIMETRES.fullmatch(words(said))
        if not centimetres:
            raise ValueError(f"the snow report's {label} reads {words(said)!r}, not centimetres")
        value = inches(float(centimetres.group(1).replace(",", ".")))
        # The page shows its conditions twice: the two have to agree.
        if figures.setdefault(SNOWFALL[label], value) != value:
            raise ValueError(f"the snow report gives its {label} twice, differently")
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", "BaseIn": None, **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, trails = lift_rows(page), trail_rows(page)
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    if len(trails) < counted(page, "Trails"):
        raise ValueError(f"the page counts {counted(page, 'Trails')} trails but only {len(trails)} were read")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
