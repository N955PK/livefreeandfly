"""Powderhorn's lifts and trails, and its snow report, from its mountain report page (powderhorn.com/conditions).

Powderhorn is a Pacific Group Resorts mountain on the group's newer layout, the one Mount Washington Alpine's
page has, so its list of lifts is read with that reader's patterns. The page is built on the server. The list of
lifts has a heading for each part of the mountain (West End, Beginner, Flat Top Flyer) and under it the lifts,
each a name and its status in words, carried as the page says it. The grooming report has the runs under the
same headings, each a name, its difficulty as a symbol before the name (a green circle, a blue square, a black
diamond, two black diamonds for a double black; a symbol the reader does not know fails) and its status in
words. Each part of the mountain is a mountain area here, holding its lifts and its runs. A run the page gives
as groomed is open and groomed, and grooming is carried only on a day the page gives some run so; a run the page
has not yet set a status for is carried in the page's words ("Not yet set"). The page's own count of its runs,
open and in all, is checked against what is read, so a change in its shape fails instead of showing wrong
numbers.

The snow report gives the snow of the last 24 and 48 hours and 7 days, the base depth and the season's total, in
inches. Before the mountain opens the figures are dashes, which reads as no snow report. The page does not say
when the report was written, so it is undated, and it gives no word for the surface. (The figures beside the
day's forecast on the same page are a forecaster's, not the resort's, and are not read.) A snow report that
cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import re
from datetime import datetime, timezone

from tahoe_snow.sources.mtwashington import CELLS, HEADING_OR_ROW, words

URL = "https://www.powderhorn.com/conditions/"
NAME = "Powderhorn"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The difficulty symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {"●": "Green", "■": "Blue", "◆": "Black", "◆◆": "Double black"}
# The snow report's labels, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hours": "Last24HoursIn", "48 Hours": "Last48HoursIn", "7 Days": "Last7DaysIn",
            "Base Depth": "BaseIn", "Season Total": "SeasonTotalIn"}
LIFTS = re.compile(r"<div [^>]*class=\"pgri-clist pgri-clist--lifts[^\"]*\">(.*?</div>)\s*</div>", re.S)
REPORT = re.compile(r"<div class=\"pgri-groom [^\"]*\">(.*?)(?:</main>|<footer\b|$)", re.S)
COUNTED = re.compile(r"<div class=\"pgri-groom__meta\">\s*<span>\s*<strong>(\d+)</strong> of <strong>(\d+)</strong> "
                     r"runs open\s*</span>")
AREA = re.compile(r"<h3 class=\"pgri-groom__area-name\">(.*?)</h3>", re.S)
RUN = re.compile(r"<div class=\"pgri-groom__run\">\s*<span class=\"pgri-groom__name\">\s*"
                 r"<span class=\"pgri-groom__dg\"[^>]*>([^<]*)</span>(.*?)</span>\s*"
                 r"<span class=\"pgri-groom__status pgri-groom__status--[a-z-]+\">\s*"
                 r"<span class=\"pgri-groom__sg\"[^>]*>[^<]*</span>\s*<span class=\"pgri-groom__lbl\">([^<]*)</span>",
                 re.S)
RUNS = "<div class=\"pgri-groom__run\">"
FEATURES = re.compile(r"<span class=\"pgri-groom__feats\">.*", re.S)
FIGURE = re.compile(r"<p class=\"pgri-stat-n [^\"]*\">([^<]*)</p>\s*<p class=\"pgri-stat-l [^\"]*\">([^<]*)</p>")
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:″|”|\")?")


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    said = said.capitalize()
    if not name or not said or not said.replace(" ", "").isalpha():
        raise ValueError(f"{name or 'a row'} has the status {said!r}, not a word")
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def lift_rows(page: str) -> dict:
    """The lifts of each part of the mountain, in the page's order."""
    found = LIFTS.search(page)
    if not found:
        raise ValueError("the list of lifts was not found")
    areas, heading = {}, None
    for area, row in HEADING_OR_ROW.findall(found.group(1)):
        if area:
            heading = words(area)
            continue
        cells = CELLS.fullmatch(row)
        if not cells or not heading:
            raise ValueError("a row of the list of lifts is not a name and a status under a part of the mountain")
        areas.setdefault(heading, []).append(status_row(words(cells.group(1)), words(cells.group(2)), None))
    read = sum(len(lifts) for lifts in areas.values())
    if not read or read != found.group(1).count("<div class=\"pgri-clist__row\">"):
        raise ValueError(f"the list of lifts has rows the reader could not read: {read} were read")
    return areas


def run_rows(page: str) -> dict:
    """The runs of each part of the mountain, in the page's order."""
    report, counted = REPORT.search(page), COUNTED.search(page)
    if not report or not counted:
        raise ValueError("the grooming report or its count of runs was not found")
    pieces = AREA.split(report.group(1))
    areas, trails = {}, []
    for heading, body in zip(pieces[1::2], pieces[2::2]):
        for symbol, name, said in RUN.findall(body):
            name = words(FEATURES.sub(" ", name))
            if symbol.strip() not in LEVELS:
                raise ValueError(f"{name} has a difficulty symbol the reader does not know: {symbol.strip()!r}")
            trail = status_row(name, words(said), LEVELS[symbol.strip()])
            if trail["StatusEnglish"] == "groomed":
                trail.update({"Status": "Open", "StatusEnglish": "open", "Grooming": "Yes"})
            areas.setdefault(words(heading), []).append(trail)
            trails.append(trail)
    turning = sum(trail["StatusEnglish"] == "open" for trail in trails)
    if not trails or len(trails) != report.group(1).count(RUNS) or len(trails) != int(counted.group(2)):
        raise ValueError(f"the page counts {counted.group(2)} runs but {len(trails)} were read")
    if turning != int(counted.group(1)):
        raise ValueError(f"the page counts {counted.group(1)} runs open but {turning} were read")
    # The page says which runs are groomed only by giving them so: on a day it does, the others are not.
    if any("Grooming" in trail for trail in trails):
        for trail in trails:
            trail.setdefault("Grooming", "No")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    figures = {}
    for said, label in FIGURE.findall(page):
        found = INCHES.fullmatch(words(said))
        if words(label) in SNOWFALL and found:
            value = float(found.group(1))
            figures[SNOWFALL[words(label)]] = int(value) if value.is_integer() else value
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no base depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    lifts, runs = lift_rows(page), run_rows(page)
    names = [lift["Name"] for part in lifts.values() for lift in part]
    if len(set(names)) != len(names):
        raise ValueError("the page lists a lift twice")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": heading, "Lifts": lifts.get(heading, []), "Trails": runs.get(heading, [])}
                              for heading in dict.fromkeys([*lifts, *runs])]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
