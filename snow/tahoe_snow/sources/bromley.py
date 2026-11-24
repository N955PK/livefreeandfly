"""Bromley's lifts and trails, and its snow report, from its snow report page (bromley.com/snow-report).

The page is built on the server and carries the whole report as JSON in its own script element (__NEXT_DATA__),
which is what the page itself draws from, so that is read and not the markup. The report lists the lifts, the
trails and the terrain parks for the whole mountain, not by area: the lifts and trails are one mountain area and
the parks another. Uphill routes are left out: the status is of the lift-served mountain. A status is one of the
page's four (open, scheduled, onHold, closed) and a trail's rating one of its four; one the reader does not know
fails instead of showing wrong numbers, as does a page without the report or without lifts. The snow report (base
depth, new snow, the season's total, surface, the resort's own words and the time it was posted) is carried in the
shape of the Ikon feed's snow report. The site gives the base depth and the new snow as a least and a most, in
inches: both are carried, and the single figure only where the site gives one figure or the two agree. A figure
the resort leaves empty stays empty. Standard library only.
"""
import json
import re
from datetime import datetime, timezone

URL = "https://bromley.com/snow-report"
REPORT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
# The report's ratings, in the words the page's difficulty symbols are keyed on.
LEVELS = {"easiestGreen": "Green", "moreDifficultBlue": "Blue", "mostDifficultBlack": "Black",
          "extremeDoubleBlack": "Double black"}
# The report's statuses, in the words its own page gives them.
STATUSES = {"open": "Open", "scheduled": "Scheduled", "onHold": "On hold", "closed": "Closed"}
# How long the new snow fell over, by the names the Ikon feed gives the figures (the page reads those).
SNOWFALL = {"24-hr": "Last24Hours", "48-hr": "Last48Hours", "72-hr": "Last72Hours", "7-day": "Last7Days"}


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"{name} has a status the reader does not know: {status}")
    words = STATUSES[status]
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict, park: bool = False) -> dict:
    if not park and trail["rating"] not in LEVELS:
        raise ValueError(f"{trail['name']} has a rating the reader does not know: {trail['rating']}")
    row = status_row(trail["name"], trail["status"], "" if park else LEVELS[trail["rating"]])
    row["Grooming"] = "Yes" if trail.get("groomed") else "No"
    return row


def figures(name: str, ends: dict) -> dict:
    """A least and a most under the Ikon feed's name. The site fills the least alone for one figure, so the single
    figure is the least where there is no most or the two agree."""
    low, high = ends.get("min"), ends.get("max")
    if low is None:
        return {f"{name}In": None, f"{name}MinIn": None, f"{name}MaxIn": None}
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float, type(None))):
        raise ValueError(f"a snow figure is not a number: {ends}")
    return {f"{name}In": low if high in (None, low) else None, f"{name}MinIn": low,
            f"{name}MaxIn": low if high is None else high}


def snow_report(report: dict) -> dict:
    """The report's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain."""
    area = {"Name": "Mountain", **figures("Base", (report.get("baseDepth") or [{}])[0])}
    recent = (report.get("recentSnowfall") or [{}])[0]
    if recent:
        if recent.get("duration") not in SNOWFALL:
            raise ValueError(f"the new snow is over a time the reader does not know: {recent.get('duration')}")
        area.update(figures(SNOWFALL[recent["duration"]], recent))
    said = (report.get("snowSurface") or [{}])[0]
    surface = ", ".join(dict.fromkeys(word.strip() for word in (said.get("primary"), said.get("secondary"))
                                      if isinstance(word, str) and word.strip()))
    posted = datetime.fromisoformat(report["dateUpdated"]).astimezone(timezone.utc)
    return {"LastUpdate": posted.strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": report.get("seasonSnowfallTotal"), "BaseArea": area,
            "Report": (report.get("reportComments") or {}).get("plainText") or None}


def parse(page: str, now: datetime) -> dict:
    data = REPORT.search(page)
    if not data:
        raise ValueError("the page's report was not found")
    report = json.loads(data.group(1)).get("props", {}).get("pageProps", {}).get("report")
    if not isinstance(report, dict) or not report.get("lifts"):
        raise ValueError("the report lists no lifts")
    lifts = [status_row(lift["name"], lift["status"], None) for lift in report["lifts"]]
    trails = [trail_row(trail) for trail in report.get("trails") or []]
    parks = [trail_row(park, park=True) for park in report.get("parks") or []]
    areas = [{"Name": "Bromley", "Lifts": lifts, "Trails": trails}]
    if parks:
        areas.append({"Name": "Terrain Parks", "Lifts": [], "Trails": parks})
    feed = {"Name": "Bromley", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas}
    try:
        feed["SnowReport"] = snow_report(report)
    except (ValueError, KeyError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Bromley: snow report: {error}")
    return feed
