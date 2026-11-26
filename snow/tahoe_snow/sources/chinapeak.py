"""China Peak's lifts and trails, and its snow totals, from its conditions page (skichinapeak.com/conditions).

The page is built on the server. Under "Lift Status & Rank" each lift has a bar with its name and its status in
words (the status is also the class of the words, and the two have to agree), and under the bar the runs the lift
serves; each lift is a mountain area here, holding itself and its runs. A run's status is a letter, which the
page's own key reads as O for open, C for closed and S for scheduled (the letter is also its class, and the two
have to agree). A run's difficulty is a picture (moderate, difficult, double diamond), and a picture the reader
does not know fails. The bar the page names "*" holds the runs no lift serves and is an area with no lift, and
the tubing hill's bar is not a lift and is left out. Every bar and every run on the page is one read, so a change
in the page's shape fails instead of showing wrong numbers.

The snow totals give the snow of the last 24 hours and the last 7 days and the season's total, in inches, each
as one figure or as a low and a high. The page gives no base depth, does not say when the totals were written,
so the report is undated, and gives no word for the surface. Snow totals that cannot be read cost only the snow
report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.skichinapeak.com/conditions"
NAME = "China Peak"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The bar over the runs no lift serves, and the name its area is given here.
NO_LIFT, NO_LIFT_NAME = "*", "Other terrain"
# Bars that are not of the lift-served mountain, by how their names begin.
LEFT_OUT = ("Tubing",)
# The pictures of difficulty, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easy": "Green", "mod": "Blue", "diff": "Black", "dd": "Double black"}
# The run's letter, by the page's own key.
LETTERS = {"O": "Open", "C": "Closed", "S": "Scheduled"}
# The snow totals' labels, by the stem of the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"Last 24 Hours": "Last24Hours", "Last 7 Days": "Last7Days", "Season Total": "SeasonTotal"}
BAR = re.compile(r"<div class=\"row chair-bar\">\s*(.*?):\s*<span class=\"([A-Za-z -]+)\">(.*?)</span>\s*</div>", re.S)
RUN = re.compile(r"<div class=\"run-status[^\"]*\">\s*<table>\s*<tr>\s*<td[^>]*>\s*<img src=\"/Content/images/"
                 r"level_([a-z]+)\.jpg\"[^>]*>\s*</td>\s*<td>(.*?)<span class=\"([A-Z]+)\">(.*?)</span>\s*</td>", re.S)
BARS, RUNS = "<div class=\"row chair-bar\">", "<div class=\"run-status"
TOTALS = re.compile(r"<div class=\"underline\"[^>]*>\s*Snow Totals:\s*</div>\s*<div class=\"data\">(.*?)</div>", re.S)
TOTAL = re.compile(r"([A-Za-z0-9 ]+?):\s*<span[^>]*>(.*?)</span>", re.S)
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*\"?")
RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*\"?\s*(?:-|–)\s*(\d+(?:\.\d+)?)\s*\"?")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def number(said: str):
    value = float(said)
    return int(value) if value.is_integer() else value


def run_row(found) -> dict:
    level, name, marked, letter = found.group(1), words(found.group(2)), found.group(3), words(found.group(4))
    if not name or letter not in LETTERS or marked != letter:
        raise ValueError(f"{name or 'a run'} has the status {letter!r} (marked {marked}), not one of the page's key")
    if level not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {level}")
    return {"Name": name, "Status": LETTERS[letter], "StatusEnglish": LETTERS[letter].lower(),
            "Difficulty": LEVELS[level]}


def lift_areas(page: str) -> list:
    """Each lift with the runs under its bar, in the page's order."""
    bars = list(BAR.finditer(page))
    areas, read = [], 0
    for at, bar in enumerate(bars):
        name, marked, said = words(bar.group(1)), bar.group(2), words(bar.group(3))
        end = bars[at + 1].start() if at + 1 < len(bars) else len(page)
        trails = [run_row(run) for run in RUN.finditer(page, bar.end(), end)]
        read += len(trails)
        if not name or not said or marked != said or not said.replace(" ", "").isalpha():
            raise ValueError(f"{name or 'a lift'} has the status {said!r} (marked {marked}), not a word")
        if name.startswith(LEFT_OUT):
            if trails:
                raise ValueError(f"{name} is left out but has runs under it")
            continue
        if name == NO_LIFT:
            areas.append({"Name": NO_LIFT_NAME, "Lifts": [], "Trails": trails})
            continue
        said = said.capitalize()
        areas.append({"Name": name, "Trails": trails,
                      "Lifts": [{"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}]})
    listed, runs = page.count(BARS), page.count(RUNS)
    if not bars or len(bars) != listed or read != runs or not read:
        raise ValueError(f"the page has {listed} lift bars and {runs} runs but {len(bars)} and {read} were read")
    if not any(area["Lifts"] for area in areas) or len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page lists no lifts, or one twice")
    return areas


def snow_report(page: str) -> dict:
    """The page's snow totals in the shape of the Ikon feed's SnowReport: one set for the whole mountain."""
    totals = TOTALS.search(page)
    if not totals:
        raise ValueError("the snow totals were not found")
    figures = {}
    for label, said in TOTAL.findall(totals.group(1)):
        label, said = words(label), words(said)
        if label not in SNOWFALL:
            continue
        if RANGE.fullmatch(said):
            low, high = (number(end) for end in RANGE.fullmatch(said).groups())
            if low > high:
                raise ValueError(f"the snow totals' {label} runs from {low} down to {high}")
            figures.update({f"{SNOWFALL[label]}MinIn": low, f"{SNOWFALL[label]}MaxIn": high})
        elif INCHES.fullmatch(said):
            figures[f"{SNOWFALL[label]}In"] = number(INCHES.fullmatch(said).group(1))
        else:
            raise ValueError(f"the snow totals' {label} reads {said!r}, not inches")
    if "Last24HoursIn" not in figures and "Last24HoursMinIn" not in figures:
        raise ValueError("the snow totals have no 24 hour snowfall")
    season = {name: figures.pop(name) for name in list(figures) if name.startswith("SeasonTotal")}
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": None, **season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": lift_areas(page)}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # Snow totals that cannot be read cost only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
