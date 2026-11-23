"""Mission Ridge's lifts and trails from its mountain report page (missionridge.com/mountain-report/).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page lists the
lifts in one table, then the trails in one table under each chair, and the off-piste areas and terrain parks.
A trail's status is a letter: O open, X closed, and AM or PM for a run groomed this morning or last night, which is
open. A page whose tables are not found, or whose trail statuses do not all read, fails instead of showing wrong
numbers. Standard library only.
python -m tahoe_snow.sources.missionridge out.json
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://www.missionridge.com/mountain-report/"
TIMEOUT = 20
# The page's trail symbols, in the words the page's difficulty symbols are keyed on; blue-black is read as black.
LEVELS = {"green": "Green", "blue": "Blue", "blue-black": "Black", "black": "Black", "double-black": "Double black"}
LIFTS = re.compile(r"<th class=\"Lift\">Lift</th>(.*?)</tbody>", re.S)
LIFT_ROW = re.compile(r"<td class=\"title\">(.*?)</td>\s*<td class=\"summit\">(.*?)</td>", re.S)
SECTION = re.compile(r"<h4>(.*?)</h4>\s*<table class=\"status trail\">(.*?)</tbody>", re.S)
# The off-piste areas and terrain parks have no difficulty column.
TRAIL_ROW = re.compile(r"(?:<td class=\"difficulty\">(.*?)</td>\s*)?<td class=\"trail\">(.*?)</td>\s*"
                       r"<td class=\"status\">(.*?)</td>", re.S)
GROOMED = {"AM", "PM"}


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(icon: str, name: str, mark: str) -> dict:
    level = re.search(r"mark-([a-z-]+)\.svg", icon or "")
    mark = text_of(mark).upper()
    status = "Open" if mark == "O" or mark in GROOMED else "Closed" if mark == "X" else mark.capitalize() or "Closed"
    row = status_row(text_of(name), status, LEVELS.get(level.group(1), "") if level else "")
    if mark in GROOMED:
        row["Grooming"] = "Yes"
    return row


def parse(page: str, now: datetime) -> dict:
    lifts = LIFTS.search(page)
    if not lifts:
        raise ValueError("the page's lift table was not found")
    rows = [status_row(text_of(name), text_of(state).capitalize() or "Closed", None)
            for name, state in LIFT_ROW.findall(lifts.group(1))]
    areas = [{"Name": text_of(name), "Lifts": [], "Trails": [trail_row(*cells) for cells in TRAIL_ROW.findall(body)]}
             for name, body in SECTION.findall(page)]
    areas = [area for area in areas if area["Trails"]]
    if not rows or not areas:
        raise ValueError("the page lists no lifts or no trails")
    # Every trail status on the page is one read, so a change in its shape fails instead of dropping runs.
    listed, found = page.count("<td class=\"status\">"), sum(len(area["Trails"]) for area in areas)
    if found != listed:
        raise ValueError(f"the page lists {listed} trail statuses but {found} trails were read")
    return {"Name": "Mission Ridge", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Mission Ridge", "Lifts": rows, "Trails": []}, *areas]}


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    request = urllib.request.Request(URL, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        feed = parse(response.read().decode("utf-8"), now)
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": {"missionridge": feed}}, handle,
                  separators=(",", ":"))
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    print(f"Mission Ridge: {len(lifts)} lifts ({sum(l['StatusEnglish'] == 'open' for l in lifts)} open), "
          f"{len(trails)} trails ({sum(t['StatusEnglish'] == 'open' for t in trails)} open)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
