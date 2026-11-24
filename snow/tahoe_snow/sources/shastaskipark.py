"""Mt. Shasta Ski Park's lifts and its snow report, from the sheet its conditions page reads
(skipark.com/winter/conditions).

The page's "Daily Conditions Report" is drawn in the browser from a spreadsheet the ski park publishes as CSV: one
row for each report it files, of which the page shows the last. This reads the same file. The four chairlifts are
the row's "Douglas - Open?", "Marmot - Open?", "Coyote - Open?" and "Gray Butte - Open?" columns: "Open" or "Yes"
is open, "Closed" or "No" is closed, and any other words (a hold, say) are carried as written; a lift left empty
fails. The sheet gives the two carpets only as a count, so they are not listed, and the page marks trails only as
groomed or closed, never as open, so no trails are given.

Out of season the sheet holds its headings and no report (the page then says "No report available yet today"),
and the mountain is given with no lifts and no snow report rather than with statuses nobody posted. A file without
the sheet's headings fails.

The snow report is the same row: the depth at the top of Douglas, the 24, 48 and 72 hour snowfall and the season's
total in inches, the surface in the ski park's words, and the row's local time, read as Pacific time. A snow
report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import csv
import io
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = ("https://docs.google.com/spreadsheets/d/e/2PACX-1vQrKLijbjvUVqE7ir1kH7lIaZFsbSffLLbhx2CIuaUvWGUPMSvQGlYpWtdhl3d9"
       "csujmxSZ8HuGQzcz/pub?gid=2049094853&single=true&output=csv")
NAME = "Mt. Shasta Ski Park"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
PACIFIC_TIME = ZoneInfo("America/Los_Angeles")
LIFTS = ("Douglas", "Marmot", "Coyote", "Gray Butte")
STATUSES = {"open": "Open", "yes": "Open", "closed": "Closed", "no": "Closed"}
# The sheet's snowfall columns, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hours (in)": "Last24HoursIn", "48 Hours (in)": "Last48HoursIn", "72 Hours (in)": "Last72HoursIn"}
DEPTH, SEASON, SURFACE, WRITTEN = "Douglas Top Snow Depth", "Season to Date (in)", "Surface Conditions", "Local Timestamp"
INCHES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\"|”|″|in\.?|inches)?", re.I)
# The ways a sheet writes a date and time.
TIMES = ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S")


def latest(page: str) -> dict | None:
    """The last report in the sheet, by its headings; None when the sheet holds no report."""
    rows = [row for row in csv.reader(io.StringIO(page)) if any(cell.strip() for cell in row)]
    headings = [cell.strip() for cell in rows[0]] if rows else []
    missing = [name for name in ["Timestamp", *(f"{lift} - Open?" for lift in LIFTS)] if name not in headings]
    if not headings or headings[0] != "Timestamp" or missing:
        raise ValueError(f"the sheet does not have the conditions report's headings (missing {missing})")
    if len(rows) == 1:
        return None
    # A heading the sheet has twice is read where it first stands, as the page reads it.
    row = [cell.strip() for cell in rows[-1]]
    return {name: row[at] if at < len(row) else "" for at, name in reversed(list(enumerate(headings)))}


def lifts_of(report: dict) -> list:
    lifts = []
    for name in LIFTS:
        said = " ".join(report[f"{name} - Open?"].split())
        if not said:
            raise ValueError(f"the report does not say whether {name} is open")
        status = STATUSES.get(said.lower(), said[0].upper() + said[1:])
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    return lifts


def inches(report: dict, column: str) -> float | int | None:
    """A figure of the report in inches; None where the sheet has no such column or leaves it empty."""
    said = report.get(column, "")
    if not said:
        return None
    found = INCHES.fullmatch(said)
    if not found:
        raise ValueError(f"the report's {column} reads {said!r}, not inches")
    value = float(found.group(1))
    return int(value) if value.is_integer() else value


def written(report: dict) -> str | None:
    """When the report was filed, in UTC; None where the sheet does not say in a way the reader knows."""
    for form in TIMES:
        try:
            at = datetime.strptime(report.get(WRITTEN, ""), form)
        except ValueError:
            continue
        return at.replace(tzinfo=PACIFIC_TIME).astimezone(timezone.utc).strftime(STAMP)
    return None


def snow_report(report: dict) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport: one set, measured at the top of Douglas."""
    area = {"Name": "Top of Douglas", "BaseIn": inches(report, DEPTH),
            **{field: inches(report, column) for column, field in SNOWFALL.items()}}
    if area["BaseIn"] is None and area["Last24HoursIn"] is None:
        raise ValueError("the report has no snow depth and no 24 hour snowfall")
    return {"LastUpdate": written(report), "Resortwide": True, "BaseConditions": report.get(SURFACE) or None,
            "SeasonTotalIn": inches(report, SEASON), "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    report = latest(page)
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts_of(report) if report else [], "Trails": []}]}
    if not report:
        return feed
    try:
        feed["SnowReport"] = snow_report(report)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
