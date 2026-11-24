"""The lifts and the snow report of a Resorts of the Canadian Rockies mountain (Kicking Horse, Fernie, Kimberley),
from the page its own website fills its conditions pages from (``/refresh/refresh.php`` on each resort's site).

The three resorts' websites are one design. Their conditions pages are drawn empty and filled in the browser by a
second page, loaded out of sight, that is a list of assignments: the name of a place on the conditions page and
the text to put there. That list is what is read. The lifts are the assignments between the one that dates the
lift status and the one that dates the bowl status; each reads "NAME: STATUS", and one that does not, or a status
the reader does not know, fails. A lift's name is written in capitals and is given here in title case.

**The list gives no status for a run.** Its grooming report names the groomed runs with their difficulty but not
whether a run is open, and its bowl status is of zones of terrain, not runs, so a mountain read here has lifts and
no trails.

The snow report gives one base depth, the new snow overnight and of the last 24 and 48 hours and 7 days, the
season's snowfall, the resort's own words, and when it was saved, in the resort's own time. **The list reports
whole centimetres; they are converted to inches here (divided by 2.54, to one decimal).** Its word for the surface
of the upper mountain is carried when it gives one. A snow report that cannot be read costs only the snow report,
not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The words a lift's status is given in.
STATUSES = {"open": "Open", "closed": "Closed", "on hold": "On hold", "standby": "On hold"}
# The places on the conditions page that date the lift status and the bowl status: the lifts are between them.
LIFTS_FROM, LIFTS_TO = "snowReportTH_SnowreportLiftsSaveDate", "snowReportTH_SnowreportBowlsSaveDate"
# The snow report's places, by the names the Ikon feed gives the figures (the app reads those).
SNOWFALL = {"snowReportNewSnowFallPack": "BaseIn", "snowReportNewSnowFall24": "Last24HoursIn",
            "snowReportNewSnowFall48": "Last48HoursIn", "snowReportNewSnowFall7days": "Last7DaysIn",
            "snowReportNewSnowFallOvernight": "OvernightIn"}
SEASON, SAVED = "snowReportNewSnowFallYTD", "snowReportTH_SnowreportRecentSnowSaveDate"
SURFACES, WORDS = ("snowReportUpperMtnConditions", "snowReportLowerMtnConditions"), "SnowreportComments"
ASSIGNED = re.compile(r"getElementById\('([A-Za-z0-9_-]+)'\)\.innerHTML\s*=\s*"
                      r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*;", re.S)
ESCAPED = re.compile(r"\\(.)", re.S)
LIFT = re.compile(r"\s*([^<:]+?)\s*:\s*<span[^>]*>\s*([^<]*?)\s*</span>\s*")
SUBTITLE = re.compile(r"<span class='rcr-element-box-conditions-subtitle'>.*?</span>", re.S)
SAVED_AT = re.compile(r"([A-Za-z]+) (\d{1,2}), (\d{4}) \| (\d{1,2}):(\d{2})\s*([ap]m)", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def assignments(page: str) -> list:
    """Each place the page fills and the text it puts there, in the page's order."""
    return [(place, ESCAPED.sub(r"\1", text[1:-1])) for place, text in ASSIGNED.findall(page)]


def lift_rows(assigned: list) -> list:
    places = [place for place, _ in assigned]
    if LIFTS_FROM not in places or LIFTS_TO not in places or places.index(LIFTS_TO) < places.index(LIFTS_FROM):
        raise ValueError("the page's lift status was not found")
    lifts = []
    for place, text in assigned[places.index(LIFTS_FROM) + 1:places.index(LIFTS_TO)]:
        found = LIFT.fullmatch(text)
        if not found:
            raise ValueError(f"the lift status at {place} does not read as a lift and its status: {text!r}")
        name, said = words(found.group(1)), words(found.group(2)).lower()
        if said not in STATUSES:
            raise ValueError(f"{name} has a status the reader does not know: {said!r}")
        lifts.append({"Name": name.title() if name.isupper() else name, "Status": STATUSES[said],
                      "StatusEnglish": STATUSES[said].lower(), "Difficulty": None})
    if not lifts:
        raise ValueError("the page lists no lifts")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return lifts


def saved(text: str, zone: ZoneInfo) -> str:
    """When the snow report was saved, in UTC, from the resort's own time."""
    found = SAVED_AT.search(text)
    if not found:
        raise ValueError(f"the snow report does not say when it was saved: {text!r}")
    month, day, year, hour, minute, half = found.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %B %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the snow report's date could not be read: {error}") from error
    return at.replace(tzinfo=zone).astimezone(timezone.utc).strftime(STAMP)


def inches(said: dict, place: str) -> float:
    if place not in said or not said[place].strip().isdigit():
        raise ValueError(f"the snow report's {place} reads {said.get(place)!r}, not whole centimetres")
    return round(int(said[place]) / CM_PER_INCH, 1)


def snow_report(assigned: list, zone: ZoneInfo, plot: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one set, measured at the resort's plot."""
    said = dict(assigned)
    if SAVED not in said:
        raise ValueError("the snow report does not say when it was saved")
    figures = {ikon: inches(said, place) for place, ikon in SNOWFALL.items()}
    surfaces = [words(SUBTITLE.sub(" ", said.get(place, ""))) for place in SURFACES]
    return {"LastUpdate": saved(said[SAVED], zone), "Resortwide": True,
            "BaseConditions": next((surface for surface in surfaces if surface), None),
            "SeasonTotalIn": inches(said, SEASON), "BaseArea": {"Name": plot, **figures},
            "Report": words(said.get(WORDS, "")) or None, "Alert": None}


def feed(page: str, now: datetime, name: str, zone: ZoneInfo, plot: str) -> dict:
    """One resort's feed: ``name`` as the app shows it, ``zone`` the resort's own time, ``plot`` where it measures."""
    assigned = assignments(page)
    read = {"Name": name, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": name, "Lifts": lift_rows(assigned), "Trails": []}]}
    try:
        read["SnowReport"] = snow_report(assigned, zone, plot)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return read
