"""Bromont's lifts and trails, and its snow report, from its detailed conditions page
(bromontmontagne.com/en/detailed-conditions), read in English.

The page is built on the server. Its lifts, its trails and its glades are each a list under a heading for each
side of the mountain (Versant du Village, Versant du Lac, Mont Soleil and the rest); each side is a mountain area
here, holding its lifts, then its trails, then its glades. A lift's row gives a word for the day, a word for the
evening and a word "in real time": the real-time word is its status, and the day's word is used only where a row
has none. A trail's row gives a word for the day and a word for the evening, or a dash where it is not skied then:
its status is the day's word, or the evening's where the day has only a dash. The words the reader knows are
Open, Closed and On hold, and their French (ouvert/ouverte -> Open, fermé/fermée -> Closed, en attente -> On hold)
in case the page falls back to it; any other word fails. A trail's difficulty is the symbol in its row (facile ->
Green, intermed -> Blue, difficile -> Black, tdifficile -> Double black, as the page's own key orders them), and
one the reader does not know fails. The page's own counts of lifts, trails and glades are checked against what is
read, so a change in its shape fails instead of showing wrong numbers. Snow parks, alpine touring and snowshoe
trails further down the page are not read.

The snow report gives the snow of the last 24 hours, 48 hours and 7 days and the season's total, with the time it
was updated in Eastern time, and words for the surface, the base and the coverage. **The page reports
centimetres; they are converted to inches here (divided by 2.54, rounded to one decimal).** The page gives no base
depth, so ``BaseIn`` is None. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.bromontmontagne.com/en/detailed-conditions/"
NAME = "Bromont"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The page's status words, English and French, in the words the app shows.
STATUSES = {"open": "Open", "ouvert": "Open", "ouverte": "Open", "closed": "Closed", "fermé": "Closed",
            "fermée": "Closed", "on hold": "On hold", "standby": "On hold", "en attente": "On hold"}
# The difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"ico-facile": "Green", "ico-intermed": "Blue", "ico-difficile": "Black", "ico-tdifficile": "Double black"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"last 24 hrs": "Last24HoursIn", "48 hrs": "Last48HoursIn", "7 days": "Last7DaysIn",
            "total": "SeasonTotalIn"}
SECTION = r"<div[^>]*\sid=\"{name}\"[^>]*>(.*?)(?=<div[^>]*\sid=\"recap-|\Z)"
SIDE = re.compile(r"<div class=\"bloc_versant[^\"]*\">\s*<div class=\"bloc_header[^\"]*\">\s*"
                  r"<span class=\"titre\">(.*?)</span>(.*?)(?=<div class=\"bloc_versant|\Z)", re.S)
ROW = re.compile(r"<div class=\"liste[^\"]*\">(.*?)</div><!-- liste -->", re.S)
NAMED = re.compile(r"<span class=\"nom\">(.*?)</span>", re.S)
BY_DAY = re.compile(r"<span class=\"jour[^\"]*\">(.*?)</span>", re.S)
BY_EVENING = re.compile(r"<span class=\"soir[^\"]*\">(.*?)</span>", re.S)
REAL_TIME = re.compile(r"<div class=\"statut[^\"]*\">\s*(?:<span class=\"statut_titre_mobile\">.*?</span>)?(.*?)</div>",
                       re.S)
LEGEND = re.compile(r"<span class=\"legende\">(.*?)</span>", re.S)
SYMBOL = re.compile(r"<i class=\"(ico-[a-z]+)\">")
COUNTED = re.compile(r"<div class=\"etat\s*\">\s*<i class=\"ico-jour\"></i>\s*<span class=\"txt-data\">\s*\d+\s*</span>"
                     r"\s*<span class=\"total\">\s*/\s*(\d+)\s*</span>")
TAG = re.compile(r"<[^>]+>")
ACCUMULATIONS = re.compile(r"<div[^>]*\sid=\"dash-acc\"[^>]*>(.*?)<div[^>]*\sid=\"dash-conditions\"", re.S)
FIGURE = re.compile(r"<div class=\"data_metric[^\"]*\">(.*?)</div>\s*<div class=\"data_imp[^\"]*\">.*?</div>\s*"
                    r"<span class=\"txt-data-label\">(.*?)</span>", re.S)
CENTIMETRES = re.compile(r"(\d+(?:[.,]\d+)?)(?:\s*cm)?")
CONDITIONS = re.compile(r"<div[^>]*\sid=\"dash-conditions\"[^>]*>(.*?)</div>", re.S)
WORD = re.compile(r"<span class=\"txt-data-label\">(.*?)</span>\s*<p>(.*?)</p>", re.S)
UPDATED = re.compile(r"<div class=\"maj-time\">\s*Updated on\s+(\d{2})-(\d{2})-(\d{4})\s+(\d{2}):(\d{2}):(\d{2})\s*</div>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float | int:
    value = round(centimetres / 2.54, 1)
    return int(value) if value.is_integer() else value


def section(page: str, name: str) -> str:
    found = re.search(SECTION.format(name=name), page, re.S)
    if not found:
        raise ValueError(f"the page's {name} part was not found")
    return found.group(1)


def status_of(said: str, name: str) -> str:
    if said.lower() not in STATUSES:
        raise ValueError(f"{name} has the status {said!r}, not one the reader knows")
    return STATUSES[said.lower()]


def one(pattern: re.Pattern, row: str) -> str | None:
    found = pattern.search(row)
    return words(found.group(1)) if found else None


def lift_row(row: str) -> dict:
    name = one(NAMED, row)
    if not name:
        raise ValueError("a row of the lifts has no name")
    said = one(REAL_TIME, row) or one(BY_DAY, row)
    if not said:
        raise ValueError(f"{name} has no status")
    status = status_of(said, name)
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(row: str) -> dict:
    name = one(NAMED, row)
    if not name:
        raise ValueError("a row of the trails has no name")
    said = [word for word in (one(BY_DAY, row), one(BY_EVENING, row)) if word and word != "-"]
    if not said:
        raise ValueError(f"{name} has no status")
    status = status_of(said[0], name)
    legend = LEGEND.search(row)
    levels = [symbol for symbol in SYMBOL.findall(legend.group(1) if legend else "") if symbol != "ico-sousbois"]
    if len(levels) != 1 or levels[0] not in LEVELS:
        raise ValueError(f"{name} has difficulty symbols {levels}, not one the reader knows")
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": LEVELS[levels[0]]}


def sides(page: str, name: str, what: str, read) -> list:
    """The rows of one part of the page, by the side of the mountain they are under, checked against its count."""
    part = section(page, name)
    counted = COUNTED.search(part)
    if not counted:
        raise ValueError(f"the page's count of {what} was not found")
    found = [(words(side), [read(row) for row in ROW.findall(rows)]) for side, rows in SIDE.findall(part)]
    if any(not side for side, _ in found):
        raise ValueError(f"a list of {what} has no heading")
    total = sum(len(rows) for _, rows in found)
    if total != int(counted.group(1)):
        raise ValueError(f"the page counts {counted.group(1)} {what} but {total} were read")
    return found


def mountain_areas(page: str) -> list:
    """Each side of the mountain with its lifts and its trails, the glades after the trails, in the page's order."""
    areas = {}
    for name, what, kind, read in (("recap-remontes", "lifts", "Lifts", lift_row),
                                   ("recap-pistes", "trails", "Trails", trail_row),
                                   ("recap-pistes-ssbois", "glades", "Trails", trail_row)):
        for side, rows in sides(page, name, what, read):
            area = areas.setdefault(side.lower(), {"Name": side, "Lifts": [], "Trails": []})
            area[kind].extend(rows)
    return list(areas.values())


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    updated = UPDATED.search(page)
    if not updated:
        raise ValueError("the snow report does not say when it was updated")
    day, month, year, hour, minute, second = (int(part) for part in updated.groups())
    try:
        at = datetime(year, month, day, hour, minute, second, tzinfo=EASTERN_TIME)
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    block = ACCUMULATIONS.search(page)
    if not block:
        raise ValueError("the snow report's accumulations were not found")
    figures = {}
    for said, label in FIGURE.findall(block.group(1)):
        label = words(label).lower()
        if label not in SNOWFALL:
            raise ValueError(f"the snow report has a figure the reader does not know: {label}")
        centimetres = CENTIMETRES.fullmatch(words(said))
        if not centimetres or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label} reads {words(said)!r}, not centimetres given once")
        figures[SNOWFALL[label]] = inches(float(centimetres.group(1).replace(",", ".")))
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    conditions = CONDITIONS.search(page)
    said = {words(label).lower(): words(word) for label, word in WORD.findall(conditions.group(1) if conditions else "")}
    surface = said.get("surface")
    return {"LastUpdate": at.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
            "BaseConditions": surface if surface and surface.strip("-") else None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", "BaseIn": None, **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    areas = mountain_areas(page)
    if not any(area["Lifts"] for area in areas) or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
