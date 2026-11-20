"""Boreal's lifts and trails from the report its lift and trail status page reads (api.rideboreal.com).

Boreal's API answers a plain request but turns away a browser on another site, so a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The report also lists
the summer hiking, biking, and park trails and the trails Boreal marks as not for the status page; only the winter
trails it shows are kept. Standard library only. python -m tahoe_snow.sources.boreal out.json
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone

URL = "https://api.rideboreal.com/api/v1/dor/lift-trail-report?alphabetical=true"
SEASONS = {"winter", "all"}
# Boreal's difficulty words, in the words the page's difficulty symbols are keyed on; parks and the like have none.
LEVELS = {"easiest": "Green", "more_difficult": "Blue", "most_difficult": "Black"}


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = status.replace("_", " ").strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def parse(report: dict, now: datetime) -> dict:
    lifts = [status_row(lift["name"], lift["status"], None) for lift in report["lift"] if lift["season"] in SEASONS]
    by_sector = {}
    for trail in report["trail"]:
        if trail["include"] and trail["season"] in SEASONS:
            by_sector.setdefault(trail["sector"]["name"], []).append(
                status_row(trail["name"], trail["status"], LEVELS.get(trail["difficulty"], "")))
    if not lifts:
        raise ValueError("the report lists no winter lifts")
    return {"Name": "Boreal", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Boreal", "Lifts": lifts, "Trails": []},
                              *({"Name": name, "Lifts": [], "Trails": trails} for name, trails in by_sector.items())]}


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    request = urllib.request.Request(URL, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        feed = parse(json.load(response), now)
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": {"boreal": feed}}, handle,
                  separators=(",", ":"))
    print(f"Boreal: {sum(len(a['Lifts']) for a in feed['MountainAreas'])} lifts, "
          f"{sum(len(a['Trails']) for a in feed['MountainAreas'])} trails")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
