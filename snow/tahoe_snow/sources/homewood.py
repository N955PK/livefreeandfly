"""Homewood's lifts, trails, and weather readings from its snow report page (skihomewood.com/snowreport).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page lists each
lift with its trails beneath it and a table of readings at the summit and the base (the base reading is NOAA's).
Its counts of lifts and runs are checked against what is parsed, so a redesign fails instead of showing wrong
numbers. Standard library only. python -m tahoe_snow.sources.homewood out.json
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://skihomewood.com/snowreport/"
# The page's own words for trail levels, in the words the page's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black"}
ZONES = {"summit": "Summit", "base": "Base"}
# A trail's row: name, level, grooming, status.
TRAIL_ROW = re.compile(r"<tr>\s*<td class=\"zone\" data-label=\"Trail Name\">(.*?)</td>\s*<td[^>]*>(.*?)</td>"
                       r"\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>", re.S)


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def words_of(fragment: str) -> str:
    """The words in a cell, without the symbols the page puts in front of them."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text_of(fragment))).strip()


def readings(page: str) -> dict:
    """Temperature, wind, and wind direction by zone from the Current Conditions table."""
    start = page.index("Current Conditions")
    table = page[start:page.index("</table>", start)]
    out = {}
    for row in re.findall(r"<tr>\s*<td class=\"zone\"[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>"
                          r"\s*<td[^>]*>(.*?)</td>", table, re.S):
        zone = ZONES.get(text_of(row[0]).split(" (")[0].lower())
        temp, wind = re.search(r"-?\d+(\.\d+)?", text_of(row[1])), re.search(r"\d+(\.\d+)?", text_of(row[2]))
        if zone and temp and wind:
            direction = text_of(row[3])
            out[zone] = {"TemperatureF": float(temp.group()), "WindStrengthMph": float(wind.group()),
                         "WindDirection": direction if re.fullmatch(r"[NESW]+", direction) else ""}
    return out


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def sectors(page: str) -> list[dict]:
    """The lifts with their status in one area, then one area per section of the page holding its trails.

    The surface lifts are listed as consecutive headings that share one status block, so a heading with nothing
    under it takes the status of the next one that has it. A section named for a zone is a grouping of trails, not
    a lift, and has no lift of its own.
    """
    lifts, areas, waiting = [], [], []
    for chunk in re.split(r"<h3 class=\"sector-name\">", page)[1:]:
        name = text_of(chunk[:chunk.index("</h3>")])
        body = chunk[chunk.index("</h3>") + 5:]
        status = re.search(r"<strong>Status:</strong>(.*?)(?:<br|</div>)", body, re.S)
        if not status:
            waiting.append(name)
            continue
        trails = [status_row(text_of(cells[0]), words_of(cells[3]), LEVELS.get(words_of(cells[1]).lower(), ""))
                  for cells in TRAIL_ROW.findall(body)]
        state = words_of(status.group(1))
        if not name.endswith("Zone"):
            lifts += [status_row(lift, state, None) for lift in [*waiting, name]]
        areas.append({"Name": name, "Lifts": [], "Trails": trails})
        waiting = []
    if waiting:
        raise ValueError(f"no status for {', '.join(waiting)}")
    return [{"Name": "Homewood", "Lifts": lifts, "Trails": []}, *areas]


def totals(page: str) -> tuple[int, int]:
    """The lifts and runs the page says it has, from its summary at the top of the status section."""
    lifts = re.search(r"Open Lifts</strong>\s*<div class=\"number\">\s*\d+/(\d+)", page)
    runs = re.search(r"Open Runs</strong>\s*<div class=\"number\">\s*\d+/(\d+)", page)
    if not lifts or not runs:
        raise ValueError("the page's lift and run totals were not found")
    return int(lifts.group(1)), int(runs.group(1))


def parse(page: str, now: datetime) -> dict:
    areas, (n_lifts, n_runs) = sectors(page), totals(page)
    found = (sum(len(area["Lifts"]) for area in areas), sum(len(area["Trails"]) for area in areas))
    if found != (n_lifts, n_runs):
        raise ValueError(f"the page lists {n_lifts} lifts and {n_runs} runs but {found[0]} and {found[1]} were read")
    return {"Name": "Homewood", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas,
            "CurrentConditions": readings(page)}


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    request = urllib.request.Request(URL, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        feed = parse(response.read().decode("utf-8"), now)
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": {"homewood": feed}}, handle,
                  separators=(",", ":"))
    print(f"Homewood: {sum(len(a['Lifts']) for a in feed['MountainAreas'])} lifts, "
          f"{sum(len(a['Trails']) for a in feed['MountainAreas'])} runs, "
          f"readings at {', '.join(feed['CurrentConditions']) or 'no zone'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
