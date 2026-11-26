"""Sasquatch Mountain's lifts and runs, and its snow report, from the two feeds its snow report page reads
(sasquatchmountain.ca/snow-report, which asks its own site for /wp-json/custom/v1/lifts and /wp-json/custom/v1/snow).

The lifts feed is a list of lifts, each with its status and the runs it serves; each lift is a mountain area here,
holding itself and its runs. A lift's status is a word, sometimes followed by a colon and the same word with a
coloured dot ("closed: 🔴 Closed"): the word before the colon is the status. The page's key knows Open, Closed and
Marginal; any other word is carried as the feed says it. A run's status is a word the same way, and the feed says
whether it is groomed. A run's difficulty is the symbol its name starts with (a green circle, a blue square, a
black diamond, two for a double black); a run with no symbol (the terrain parks) has none, and a symbol the reader
does not know fails. The feed says when the statuses were last changed, in the resort's own time. The resort
leaves its last statuses of the season up all summer and autumn with lifts still reading open, so statuses more
than OLD_DAYS old with anything open are refused: they are last season's.

The snow feed gives the depth at the alpine weather plot and the snow of the last 12, 24 and 48 hours and of the
season, in centimetres, turned into inches here (divided by 2.54, to one decimal), with the day and time it was
written (day/month/year, the resort's own time). A figure the resort has not filled in is a dash and is left out.
A snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SITE = "https://sasquatchmountain.ca/wp-json/custom/v1"
URLS = {"lifts": f"{SITE}/lifts", "snow": f"{SITE}/snow"}
NAME = "Sasquatch Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Vancouver")
CM_PER_INCH = 2.54
# Statuses older than this with a lift or a run open are last season's, left up after the mountain closed.
OLD_DAYS = 14
# The symbols a run's name starts with, in the words the app's difficulty symbols are keyed on.
LEVELS = {"🟢": "Green", "🟦": "Blue", "◆": "Black", "◆◆": "Double black"}
# The snow feed's figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"alpine_base": "BaseIn", "past12": "Last12HoursIn", "past24": "Last24HoursIn", "past48": "Last48HoursIn",
            "season_total": "SeasonTotalIn"}
STATUS = re.compile(r"[a-z][a-z ]*")
SYMBOLS = re.compile(r"^([^\w\s\"'(]+)\s*(.*)$", re.S)
NUMBER = re.compile(r"\d+(?:\.\d+)?")
EMPTY = {"", "-", "–", "—"}


def status(said, name: str) -> str:
    """A lift's or a run's status: the word before any colon, with a capital."""
    word = " ".join(str(said or "").split(":")[0].lower().split())
    if not STATUS.fullmatch(word):
        raise ValueError(f"{name} has the status {said!r}, which is not a word")
    return word.capitalize()


def run_row(run: dict) -> dict:
    """One run: its difficulty is the symbol its name starts with, and the feed says whether it is groomed."""
    said = " ".join(str(run.get("run_name") or "").split())
    marked = SYMBOLS.match(said)
    symbol, name = ("".join(marked.group(1).split()), marked.group(2).strip()) if marked else ("", said)
    # Some symbols come with an invisible mark after them that only chooses how they are drawn.
    symbol = symbol.replace("️", "")
    if not name:
        raise ValueError("a run has no name")
    if symbol and symbol not in LEVELS:
        raise ValueError(f"{name} starts with a symbol the reader does not know: {symbol!r}")
    if not isinstance(run.get("groomed"), bool):
        raise ValueError(f"{name} does not say whether it is groomed")
    said = status(run.get("run_status"), name)
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": LEVELS.get(symbol, ""),
            "Grooming": "Yes" if run["groomed"] else "No"}


def lift_areas(feed: dict) -> list:
    """Each lift with the runs under it, in the feed's order."""
    lifts = feed.get("lifts") if isinstance(feed, dict) else None
    if not isinstance(lifts, list) or not lifts:
        raise ValueError("the lifts feed lists no lifts")
    areas = []
    for lift in lifts:
        name = " ".join(str(lift.get("lift_name") or "").split())
        if not name or not isinstance(lift.get("runs"), list):
            raise ValueError("a lift has no name or no list of runs")
        said = status(lift.get("lift_status"), name)
        areas.append({"Name": name, "Trails": [run_row(run) for run in lift["runs"]],
                      "Lifts": [{"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}]})
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the feed lists a lift twice")
    if not any(area["Trails"] for area in areas):
        raise ValueError("the lifts feed lists no runs")
    return areas


def changed(feed: dict) -> datetime:
    """When the statuses were last changed ("March 6, 2026 8:08 am", the resort's own time)."""
    said = " ".join(str(feed.get("status_updated") or "").split())
    try:
        at = datetime.strptime(said, "%B %d, %Y %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the lifts feed's time reads {said!r}, not a day and a time") from error
    return at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc)


def inches(said, label: str) -> float | None:
    """A figure in centimetres as inches; a dash or nothing is no figure."""
    said = str(said if said is not None else "").strip()
    if said in EMPTY:
        return None
    if not NUMBER.fullmatch(said):
        raise ValueError(f"the snow feed's {label} reads {said!r}, not centimetres")
    return round(float(said) / CM_PER_INCH, 1)


def snow_report(feed: dict) -> dict:
    """The snow feed in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    if not isinstance(feed, dict) or any(key not in feed for key in SNOWFALL):
        raise ValueError("the snow feed does not have the figures the reader knows")
    figures = {field: inches(feed[key], key) for key, field in SNOWFALL.items()}
    figures = {field: value for field, value in figures.items() if value is not None}
    if "BaseIn" not in figures and "Last24HoursIn" not in figures:
        raise ValueError("the snow feed has no depth and no 24 hour snowfall")
    said = " ".join(str(feed.get("date_updated") or "").split())
    try:
        at = datetime.strptime(said, "%d/%m/%Y %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow feed's time reads {said!r}, not a day and a time") from error
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": at.replace(tzinfo=RESORT_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Alpine", **figures}, "Report": None, "Alert": None}


def parse(pages: dict, now: datetime) -> dict:
    lifts = json.loads(pages["lifts"])
    areas = lift_areas(lifts)
    at = changed(lifts)
    rows = [row for area in areas for row in area["Lifts"] + area["Trails"]]
    if now - at > timedelta(days=OLD_DAYS) and any(row["StatusEnglish"] == "open" for row in rows):
        raise ValueError(f"the statuses were last changed {at:%Y-%m-%d} and have lifts or runs open: "
                         "they are last season's")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(json.loads(pages["snow"]))
    except (ValueError, KeyError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
