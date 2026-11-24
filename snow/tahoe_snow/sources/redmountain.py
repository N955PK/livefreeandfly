"""RED Mountain's lifts and runs, and its snow report, from the two reports its own report page reads
(redresort.com/report/).

The page is drawn in the browser from the resort's own API (api.redresort.com): a query for the lifts with the
runs each serves, which the API also answers as a plain request with the query in its address, and the day's
mountain report. Each lift is a mountain area with its runs, in the page's order. A run two lifts serve is listed
under both; here it is kept under the first, so each run is counted once. A lift is open, closed or on hold. A
run is open, closed or open in marginal conditions, which the page marks and which is carried in its own words,
and is groomed or not (a run that is never groomed is not). A status, a grooming or a difficulty the reader does
not know fails.

The mountain report is written by the resort: the snow depth at its alpine weather plot, the new snow overnight
and of the last 24 and 48 hours, 3 days and 7 days, the snowfall since October 1, the resort's own words, and when
it was posted, with its hours from UTC. **The report gives centimetres; they are converted to inches here
(divided by 2.54, to one decimal).** It gives no surface. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote

API = "https://api.redresort.com"
QUERY = "{lifts{name status runs{sortOrder run{name difficulty status grooming}}}}"
URLS = {"lifts": f"{API}/graphql/query?query={quote(QUERY)}", "snow": f"{API}/report/full"}
NAME = "RED Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The reports' status words for a lift, and for a run with whether it counts as open.
LIFT_STATUSES = {"OPEN": "Open", "CLOSED": "Closed", "ON_HOLD": "On hold"}
RUN_STATUSES = {"OPEN": ("Open", "open"), "CLOSED": ("Closed", "closed"),
                "MARGINAL_CONDITIONS": ("Marginal conditions", "open")}
# The reports' difficulty words, in the words the app's difficulty symbols are keyed on. A terrain park has none.
LEVELS = {"GREEN": "Green", "BLUE": "Blue", "BLACK_DIAMOND": "Black", "DOUBLE_BLACK": "Double black", "PARK": ""}
GROOMED = {"GROOMED": "Yes", "NOT_GROOMED": "No", "DISABLED": "No"}
# The mountain report's snowfall, by the names the Ikon feed gives it (the app reads those).
SNOWFALL = {"MetricAlpineSnowDepth": "BaseIn", "Metric24hours": "Last24HoursIn", "Metric48hours": "Last48HoursIn",
            "Metric3days": "Last72HoursIn", "Metric7days": "Last7DaysIn", "MetricOvernight": "OvernightIn"}
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the report: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def loaded(page: str, what: str) -> dict:
    try:
        report = json.loads(page)
    except json.JSONDecodeError as error:
        raise ValueError(f"the {what} report does not read as JSON: {error}") from error
    if not isinstance(report, dict):
        raise ValueError(f"the {what} report is not in the shape expected")
    return report


def named(row: dict) -> str:
    if not isinstance(row["name"], str) or not row["name"].strip():
        raise ValueError("the report lists a lift or a run with no name")
    return row["name"].strip()


def lift_row(lift: dict) -> dict:
    name = named(lift)
    if lift["status"] not in LIFT_STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {lift['status']!r}")
    status = LIFT_STATUSES[lift["status"]]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def run_row(run: dict) -> dict:
    name = named(run)
    if run["status"] not in RUN_STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {run['status']!r}")
    if run["difficulty"] not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {run['difficulty']!r}")
    if run["grooming"] not in GROOMED:
        raise ValueError(f"{name} has a grooming the reader does not know: {run['grooming']!r}")
    status, english = RUN_STATUSES[run["status"]]
    return {"Name": name, "Status": status, "StatusEnglish": english, "Difficulty": LEVELS[run["difficulty"]],
            "Grooming": GROOMED[run["grooming"]]}


def areas(report: dict) -> list:
    """Each lift as a mountain area with the runs it serves; a run two lifts serve is kept under the first."""
    read, seen = [], set()
    try:
        for lift in report["data"]["lifts"]:
            runs = []
            for listed in sorted(lift["runs"], key=lambda each: each["sortOrder"]):
                run = run_row(listed["run"])
                if run["Name"] not in seen:
                    seen.add(run["Name"])
                    runs.append(run)
            read.append({"Name": named(lift), "Lifts": [lift_row(lift)], "Trails": runs})
    except (KeyError, TypeError) as error:
        raise ValueError(f"the lift report is not in the shape expected: {error!r}") from error
    if not read or not seen:
        raise ValueError("the lift report lists no lifts or no runs")
    return read


def inches(value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"the mountain report gives {value!r}, not centimetres")
    return round(value / CM_PER_INCH, 1)


def snow_report(report: dict) -> dict:
    """The mountain report in the shape of the Ikon feed's SnowReport: one set, measured at the alpine plot."""
    try:
        mountain = report["MountainReport"]
        posted = datetime.fromisoformat(mountain["DateTime"])
        if posted.tzinfo is None:
            raise ValueError(f"the mountain report's time has no hours from UTC: {mountain['DateTime']}")
        figures = {ikon: inches(mountain[field]) for field, ikon in SNOWFALL.items()}
        return {"LastUpdate": posted.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
                "BaseConditions": None, "SeasonTotalIn": inches(mountain["TotalSnowDepth"]),
                "BaseArea": {"Name": "Alpine weather plot", **figures},
                "Report": words(mountain.get("Notes") or "") or None, "Alert": None}
    except (KeyError, TypeError) as error:
        raise ValueError(f"the mountain report is not in the shape expected: {error!r}") from error


def parse(pages: dict, now: datetime) -> dict:
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas(loaded(pages["lifts"], "lift"))}
    try:
        feed["SnowReport"] = snow_report(loaded(pages["snow"], "mountain"))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
