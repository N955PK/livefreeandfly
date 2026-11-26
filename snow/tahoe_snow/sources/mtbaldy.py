"""Mt. Baldy's chairs and runs, and its snow report, from the feed its mountain report page reads
(mtbaldyresort.com/mountain-report, which shows a dash for every chair until its script has asked
tickets.mtbaldyresort.com/api/status; a plain GET with no key and no cookie answers).

The feed lists the four chairs, the report the mountain last wrote (a status for each chair, new snow, base depth,
the surface and a few written paragraphs), every run with the chair it is skied from, and the days and hours the
lifts run. Each chair is a mountain area here, holding itself and its runs.

A chair's status is one of the page's own words: "open", "scenic" (running, for rides to the Notch only), "hold",
"closed" and "snow" (closed for want of snow, which the page writes "Pray for snow"). A chair the report leaves out
reads "snow", as the page has it. The page shows an open chair as open only inside the day's hours (and from the
chair's own opening time where the report gives one), so the reader does the same: the report is written the evening
before and its "open" stays up all night. Any other status fails.

A run's status is the grooming report's word: "groomed", "powder", "ungroomed" and "moguls" are open, "closed" is
closed, and a run the grooming report has not covered has no word and reads "Not reported" here. A run's level is
one of four words; the freestyle terrain has none. In its summer season the mountain runs Chair 1 for sightseeing
and the feed is refused.

The report's base depth and new snow are in inches, and a figure the mountain has not filled in is null. The page
shows a base depth only above zero, so a zero is taken as not filled in. The page calls the new snow just "new";
it is carried as the last 24 hours. A snow report that cannot be read costs only the snow report, not the lifts.
Standard library only.
"""
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://tickets.mtbaldyresort.com/api/status"
NAME = "Mt. Baldy"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Los_Angeles")
# A chair's status in the feed, as (the words shown, the plain status). Open and scenic also depend on the hours.
CHAIRS = {"open": ("Open", "open"), "scenic": ("Scenic rides only", "open"), "hold": ("On hold", "on hold"),
          "closed": ("Closed", "closed"), "snow": ("Pray for snow", "closed")}
# A run's status in the feed, as (the words shown, the plain status, whether it is groomed).
RUNS = {"groomed": ("Groomed", "open", "Yes"), "powder": ("Powder", "open", "No"),
        "ungroomed": ("Ungroomed", "open", "No"), "moguls": ("Moguls", "open", "No"),
        "closed": ("Closed", "closed", "No"), "": ("Not reported", "not reported", None)}
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black", "": ""}


def minutes(said, label: str) -> int:
    """A time of day ("09:00") as minutes after midnight."""
    try:
        hour, minute = (int(part) for part in str(said).split(":"))
    except ValueError as error:
        raise ValueError(f"{label} reads {said!r}, not a time of day") from error
    if not (0 <= hour <= 24 and 0 <= minute < 60):
        raise ValueError(f"{label} reads {said!r}, not a time of day")
    return hour * 60 + minute


def clock(at: int) -> str:
    """Minutes after midnight as the page writes a time ("9 AM", "12:30 PM")."""
    hour, minute = divmod(at, 60)
    return f"{hour % 12 or 12}{f':{minute:02d}' if minute else ''} {'AM' if hour % 24 < 12 else 'PM'}"


def today(feed: dict, now: datetime) -> dict:
    """The feed's hours for the resort's own day: whether the lifts run and from when to when."""
    hours = feed.get("openHours")
    if not isinstance(hours, dict) or not isinstance(hours.get("days"), list) or not hours["days"]:
        raise ValueError("the feed does not give the days the lifts run")
    date = now.astimezone(RESORT_TIME).strftime("%Y-%m-%d")
    day = next((day for day in hours["days"] if isinstance(day, dict) and day.get("date") == date), None)
    if day is None:
        raise ValueError(f"the feed's hours do not cover {date}")
    if not isinstance(day.get("open"), bool):
        raise ValueError(f"the feed does not say whether the lifts run on {date}")
    return day


def chair_status(posted: dict, day: dict, now: datetime, name: str) -> tuple:
    """A chair's status as the page shows it: the report's word, and for a running chair the day's hours."""
    said = posted.get("status") or "closed"
    if said not in CHAIRS:
        raise ValueError(f"{name} has the status {said!r}, which the reader does not know")
    words, plain = CHAIRS[said]
    if plain != "open":
        return words, plain
    if not day["open"]:
        return "Closed", "closed"
    local = now.astimezone(RESORT_TIME)
    at = local.hour * 60 + local.minute
    start, end = minutes(day.get("from"), "the day's opening"), minutes(day.get("to"), "the day's closing")
    if posted.get("opens"):
        start = max(start, minutes(posted["opens"], f"{name}'s opening"))
    if at >= end:
        return "Closed", "closed"
    if at < start:
        return f"Opens {clock(start)}", "closed"
    return words, plain


def run_row(run: dict) -> dict:
    """One run, with its level and the grooming report's word for it."""
    name = " ".join(str(run.get("name") or "").split())
    if not name:
        raise ValueError("a run has no name")
    said, level = run.get("status"), run.get("level")
    if said not in RUNS:
        raise ValueError(f"{name} has the status {said!r}, which the reader does not know")
    if level not in LEVELS:
        raise ValueError(f"{name} has the level {level!r}, which the reader does not know")
    words, plain, groomed = RUNS[said]
    row = {"Name": name, "Status": words, "StatusEnglish": plain, "Difficulty": LEVELS[level]}
    if groomed:
        row["Grooming"] = groomed
    return row


def areas(feed: dict, now: datetime) -> list:
    """Each chair with the runs skied from it, in the feed's order."""
    chairs, runs, report = feed.get("chairs"), feed.get("runs"), feed.get("report")
    if not isinstance(chairs, list) or not chairs or not isinstance(runs, list) or not runs:
        raise ValueError("the feed lists no chairs or no runs")
    if not isinstance(report, dict) or not isinstance(report.get("chairs"), dict):
        raise ValueError("the feed has no report of the chairs")
    if feed.get("season") != "winter" or report.get("season") != "winter":
        raise ValueError(f"the feed is for the {feed.get('season')} season (its report for the "
                         f"{report.get('season')}), not the winter")
    day, found, numbers = today(feed, now), [], {}
    for chair in chairs:
        number, name = chair.get("n"), " ".join(str(chair.get("name") or "").split())
        if not isinstance(number, int) or not name or number in numbers:
            raise ValueError("a chair has no number or no name, or is listed twice")
        full = f"Chair {number} · {name}"
        posted = report["chairs"].get(str(number))
        if posted is not None and not isinstance(posted, dict):
            raise ValueError(f"{full}'s status is not in the shape the reader knows")
        # A chair the report leaves out reads "snow" in winter, as on the page.
        words, plain = chair_status(posted or {"status": "snow"}, day, now, full)
        numbers[number] = {"Name": full, "Trails": [],
                           "Lifts": [{"Name": full, "Status": words, "StatusEnglish": plain, "Difficulty": None}]}
        found.append(numbers[number])
    for run in runs:
        if run.get("chair") not in numbers:
            raise ValueError(f"the run {run.get('name')!r} is on chair {run.get('chair')!r}, which is not listed")
        numbers[run["chair"]]["Trails"].append(run_row(run))
    names = [trail["Name"] for area in found for trail in area["Trails"]]
    if len(set(names)) != len(names):
        raise ValueError("the feed lists a run twice")
    return found


def figure(said, label: str) -> float | None:
    """A figure in inches; null or nothing is no figure."""
    if said is None or said == "":
        return None
    if isinstance(said, bool):
        raise ValueError(f"the report's {label} reads {said!r}, not inches")
    try:
        value = float(said)
    except (TypeError, ValueError) as error:
        raise ValueError(f"the report's {label} reads {said!r}, not inches") from error
    if not 0 <= value < 1000:
        raise ValueError(f"the report's {label} reads {said!r}, not inches")
    return round(value, 1)


def snow_report(report: dict) -> dict:
    """The mountain's report in the shape of the Ikon feed's SnowReport."""
    base, new = figure(report.get("base"), "base depth"), figure(report.get("newSnow"), "new snow")
    figures = {}
    # The page shows a base depth only above zero: a zero is a figure nobody filled in.
    if base:
        figures["BaseIn"] = base
    if new is not None:
        figures["Last24HoursIn"] = new
    if not base and not new:
        raise ValueError("the report gives no base depth and no new snow")
    try:
        at = datetime.strptime(str(report.get("at")), "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError(f"the report's time reads {report.get('at')!r}, not a day and a time") from error
    surface = " ".join(str(report.get("surface") or "").split())
    return {"LastUpdate": at.strftime(STAMP), "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": None, "BaseArea": {"Name": "Mountain", **figures},
            "Report": str(report.get("text") or "").strip() or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    feed = json.loads(page)
    if not isinstance(feed, dict):
        raise ValueError("the feed is not in the shape the reader knows")
    out = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
           "MountainAreas": areas(feed, now)}
    try:
        out["SnowReport"] = snow_report(feed["report"])
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return out
