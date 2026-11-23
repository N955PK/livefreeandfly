"""Sugarloaf's, Sunday River's and Loon's lifts and trails, and their snow report, from the report their own
mountain-report pages read.

The three are Boyne's, and each site's mountain-report page reads one report from its own site
(/api/reportpal?resortName=<code>), the code being the one the page itself names (sl, sr, lm). The report answers a
plain request but does not let a browser on another site read it, so a scheduled job reads it and writes one small
file the page reads, in the shape of the Ikon feed the rest of the page uses. Nordic and uphill routes are left
out: the status is of the lift-served mountain. The report's own count of lifts is checked against what is read,
so a change in its shape fails instead of showing wrong numbers. One resort that fails is left out of the file
without costing the others. The snow report (base depth, new snow, surface, the resort's own words and the time
it was posted) is carried in the shape of the Ikon feed's snow report; a figure the resort leaves empty stays empty.
Standard library only. python -m tahoe_snow.sources.boyne out.json
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

RESORTS = {
    "sugarloaf": ("Sugarloaf", "www.sugarloaf.com", "sl"),
    "sundayriver": ("Sunday River", "www.sundayriver.com", "sr"),
    "loon": ("Loon", "www.loonmtn.com", "lm"),
}
URL = "https://{host}/api/reportpal?resortName={code}&useReportPal=true"
TIMEOUT = 20
# The report's difficulty icons, in the words the page's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black"}
NOT_ALPINE = {"cross country"}
# The report's snowfall figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"snow24Hours": "Last24HoursIn", "snow48Hours": "Last48HoursIn", "snow72Hours": "Last72HoursIn",
            "snow7Days": "Last7DaysIn"}


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = (status or "Closed").strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(trail: dict) -> dict:
    row = status_row(trail["name"], trail["status"], LEVELS.get(trail.get("difficultyIcon") or "", ""))
    if isinstance(trail.get("groomed"), bool):
        row["Grooming"] = "Yes" if trail["groomed"] else "No"
    return row


def inches(figure) -> float | int | None:
    """A depth the report gives as {"inches": "12", "centimeters": "30"}; None where it gives nothing."""
    said = figure.get("inches") if isinstance(figure, dict) else None
    if said is None or str(said).strip() in ("", "--"):
        return None
    value = float(str(said).strip())
    return int(value) if value.is_integer() else value


def snow_report(report: dict) -> dict | None:
    """The report's snow figures in the shape of the Ikon feed's SnowReport. Boyne gives one depth for the whole
    lift-served mountain (with its least and most), not one per stake, so it is the only area and is marked as the
    whole mountain's. The Nordic centre's figures are left out. None when the report has no location at all."""
    places = [place for place in report["currentConditions"].get("resortLocations", {}).get("location") or []
              if "nordic" not in (place.get("name") or "").lower()]
    if not places:
        return None
    place = places[0]
    area = {"Name": "Mountain", "BaseIn": inches(place.get("base")), "BaseMinIn": inches(place.get("baseMin")),
            "BaseMaxIn": inches(place.get("baseMax"))}
    area.update({ikon: inches(place.get(field)) for field, ikon in SNOWFALL.items()})
    surface = ", ".join(word.strip() for word in (place.get("primarySurface"), place.get("secondarySurface"))
                        if isinstance(word, str) and word.strip())
    said = {comment["name"]: comment.get("text") or "" for comment in (report.get("comments") or {}).get("comment") or []}
    return {"LastUpdate": report["updated"], "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": inches(place.get("snowSeasonTotal")), "BaseArea": area,
            "Report": said.get("Comment") or None, "Alert": said.get("commentAlert") or None}


def parse(name: str, report: dict, now: datetime) -> dict:
    """The report in the page's shape: one mountain area per area of the report that has lifts or ski trails."""
    areas = []
    for area in report["facilities"]["areas"]["area"]:
        if "uphill" in area["name"].lower():
            continue
        lifts = [status_row(lift["name"], lift["status"], None) for lift in (area.get("lifts") or {}).get("lift") or []]
        trails = [trail_row(trail) for trail in (area.get("trails") or {}).get("trail") or []
                  if (trail.get("type") or "").lower() not in NOT_ALPINE]
        if lifts or trails:
            areas.append({"Name": area["name"].title() if area["name"].isupper() else area["name"], "Lifts": lifts,
                          "Trails": trails})
    listed = report["currentConditions"]["resortwide"]["numLiftsTotal"]
    found = sum(len(area["Lifts"]) for area in areas)
    if not found:
        raise ValueError("the report lists no lifts")
    if found != listed:
        raise ValueError(f"the report counts {listed} lifts but {found} were read")
    feed = {"Name": name, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas}
    snow = snow_report(report)
    if snow:
        feed["SnowReport"] = snow
    return feed


def fetch(host: str, code: str) -> dict:
    request = urllib.request.Request(URL.format(host=host, code=code), headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def snow_line(snow: dict | None) -> str:
    """The snow report's part of the log line: base depth and new snow, and when the resort posted it."""
    if not snow:
        return "; no snow report"
    area = snow["BaseArea"]
    return (f"; base {area['BaseIn']} in, 24 h {area['Last24HoursIn']} in, posted {snow['LastUpdate']}")


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    resorts = {}
    for key, (name, host, code) in RESORTS.items():
        try:
            resorts[key] = parse(name, fetch(host, code), now)
        except Exception as error:
            print(f"{name}: {error}")
    if not resorts:
        return 1
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": resorts}, handle, separators=(",", ":"))
    for feed in resorts.values():
        lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
        trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
        print(f"{feed['Name']}: {len(lifts)} lifts ({sum(l['StatusEnglish'] == 'open' for l in lifts)} open), "
              f"{len(trails)} trails ({sum(t['StatusEnglish'] == 'open' for t in trails)} open)"
              + snow_line(feed.get("SnowReport")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
