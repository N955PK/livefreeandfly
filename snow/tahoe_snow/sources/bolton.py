"""Bolton Valley's lifts and trails, and its snow report, from the report its own snow-report page reads
(boltonvalley.com/winter/trail-maps-snow-reports/snow-reports/).

The page reads one report from its own site (/wp-admin/admin-ajax.php?action=get_prop_conditions). The report is
JSON with stray commas where the site's template leaves a gap in a list, and the page itself takes them out before
reading it, so the same two repairs are made here and nothing more. The report lists the lifts and the trails for
the whole mountain, not by area, so they are one mountain area. A lift's or trail's statuses are a list: one says
whether it is open (Open, Closed, a hold or a delay) and the others are what it has (Groomed). The report's own
counts of lifts and trails are checked against what is read, and a lift or trail without exactly one open-or-closed
status fails, so a change in its shape fails instead of showing wrong numbers. The snow report (base depth, new
snow, surface and the time it was posted) is carried in the shape of the Ikon feed's snow report. The report gives
the base depth and the 24-hour snowfall as a range ("12-24"): the two ends are carried as the least and the most,
and the single figure only where the two ends agree. A figure the resort leaves empty stays empty. Standard
library only.
"""
import json
import re
from datetime import datetime, timezone

URL = "https://www.boltonvalley.com/wp-admin/admin-ajax.php?action=get_prop_conditions"
# The report's difficulty words, in the words the page's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"easiest": "Green", "more-difficult": "Blue", "most-difficult": "Black", "expert-only": "Double black",
          "terrain": ""}
# The report's snowfall figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"snow24Hours": "Last24Hours", "snow48Hours": "Last48Hours", "snow72Hours": "Last72Hours",
            "snow7days": "Last7Days"}
SPAN = re.compile(r"(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?")


def repaired(page: str) -> dict:
    """The report as the site's own page reads it: a comma after an opening bracket and a doubled comma are taken
    out, then it is read as JSON."""
    return json.loads(re.sub(r",\s*,", ",", re.sub(r"\[\s*,", "[", page)))


def status_row(name: str, statuses: list, difficulty: str | None) -> dict:
    """One lift or trail. Exactly one of its statuses says whether it is open; the rest are what it has."""
    states = [word.strip() for word in statuses
              if word.strip().lower() in ("open", "closed") or "hold" in word.lower() or "delay" in word.lower()]
    if len(states) != 1:
        raise ValueError(f"{name} has statuses {statuses}, not one that says open or closed")
    words = states[0].capitalize()
    return {"Name": name.strip(), "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    if trail["difficulty"] not in LEVELS:
        raise ValueError(f"{trail['name']} has a difficulty the reader does not know: {trail['difficulty']}")
    row = status_row(trail["name"], trail["statuses"], LEVELS[trail["difficulty"]])
    row["Grooming"] = "Yes" if any(word.strip().lower() == "groomed" for word in trail["statuses"]) else "No"
    return row


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def span(said) -> tuple | None:
    """A figure the report gives as "12" or as a range "12-24", as its two ends; None where it gives nothing."""
    said = str(said or "").strip()
    if not said:
        return None
    figure = SPAN.fullmatch(said)
    if not figure:
        raise ValueError(f"a snow figure does not read as a number or a range: {said}")
    return number(figure.group(1)), number(figure.group(2) or figure.group(1))


def figures(name: str, said) -> dict:
    """A figure under the Ikon feed's name: the single figure where the report gives one or a range whose ends
    agree, and the two ends as the least and the most where it gives a range."""
    ends = span(said)
    single = {f"{name}In": ends[0] if ends and ends[0] == ends[1] else None}
    if ends and "-" in str(said):
        single.update({f"{name}MinIn": ends[0], f"{name}MaxIn": ends[1]})
    return single


def snow_report(report: dict) -> dict | None:
    """The report's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain (the report
    gives one location). None when the report has no location."""
    place = (report["currentConditions"].get("resortLocations") or {}).get("location")
    if not place:
        return None
    if report.get("units") != "imperial":
        raise ValueError(f"the report's units are {report.get('units')}, not inches")
    area = {"Name": "Mountain", **figures("Base", place.get("baseRange"))}
    for field, ikon in SNOWFALL.items():
        area.update(figures(ikon, place.get(field)))
    surface = ", ".join(dict.fromkeys(word.strip() for word in (place.get("primarySurface"), place.get("secondarySurface"))
                                      if isinstance(word, str) and word.strip()))
    posted = datetime.fromisoformat(report["updated"]).astimezone(timezone.utc)
    return {"LastUpdate": posted.strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": figures("SeasonTotal", place.get("seasonTotal"))["SeasonTotalIn"], "BaseArea": area,
            "Report": (report.get("comment") or {}).get("comments") or None}


def parse(page: str, now: datetime) -> dict:
    report = repaired(page).get("report")
    if not isinstance(report, dict) or "facilities" not in report:
        raise ValueError("the report has no facilities")
    plant = report["facilities"]
    lifts = [status_row(lift["name"], lift["statuses"], None) for lift in plant.get("lifts") or []]
    trails = [trail_row(trail) for trail in plant.get("trails") or [] if not trail.get("excluded")]
    if not lifts:
        raise ValueError("the report lists no lifts")
    # The report's own counts are of all its lifts and trails, so a change in its shape fails instead of dropping some.
    for kind, rows, counted in (("lifts", lifts, plant.get("maxOpenDownHillLifts")),
                                ("trails", trails, plant.get("maxOpenDownHillTrails"))):
        if str(counted).strip() != str(len(rows)):
            raise ValueError(f"the report counts {counted} {kind} but {len(rows)} were read")
    feed = {"Name": "Bolton Valley", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Bolton Valley", "Lifts": lifts, "Trails": trails}]}
    try:
        snow = snow_report(report)
    except (ValueError, KeyError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Bolton Valley: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
