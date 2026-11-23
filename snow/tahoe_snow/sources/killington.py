"""Killington's and Pico's lifts and trails, from their lifts-and-trails status pages.

The two share one site design: the page is built on the server, one section per area of the mountain, each lift and
trail a card that carries its status (and a trail its difficulty and type) as data attributes. The site does not let
a browser on another site read it, so a scheduled job reads it and writes one small file the page reads, in the
shape of the Ikon feed the rest of the page uses. Uphill routes are left out. Each area's own count of lifts and
trails is checked against what is read, so a redesign fails instead of showing wrong numbers. One resort that fails
is left out of the file without costing the other. Standard library only.
python -m tahoe_snow.sources.killington out.json
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone

RESORTS = {
    "killington": ("Killington", "https://killington.com/lifts-and-trails-status"),
    "pico": ("Pico", "https://picomountain.com/lifts-and-trails-status"),
}
TIMEOUT = 20
# The site's difficulty words, in the words the page's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double_black": "Double black"}
NOT_SKIED = {"uphill_trail"}
AREA = re.compile(r'<div class="area-section">')
AREA_NAME = re.compile(r'<span class="area-toggle-text">(.*?)</span>', re.S)
AREA_COUNT = re.compile(r'<span class="meta-pill">(Lifts|Trails) \d+/(\d+)</span>')
LIFT = re.compile(r'<div class="item lift-card lift-row"[^>]*\sdata-lift-status="([^"]*)"[^>]*>.*?'
                  r'<div class="lift-name">(?:<span class="lift-type">.*?</span>)?(.*?)</div>', re.S)
TRAIL = re.compile(r'<div class="item trail-card trail-row"([^>]*)>.*?<span class="trail-name">(.*?)</span>', re.S)


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = (status or "closed").replace("-", " ").replace("_", " ").strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(attributes: str, name: str) -> dict:
    said = dict(re.findall(r'\sdata-([a-z-]+)="([^"]*)"', attributes))
    row = status_row(text_of(name), said.get("trail-status", ""), LEVELS.get(said.get("difficulty", ""), ""))
    row["Grooming"] = "Yes" if "trail-feature::groomed" in said.get("filter-values", "").split("|") else "No"
    return row, said.get("type", "")


def parse(name: str, page: str, now: datetime) -> dict:
    """One mountain area per area of the page, the lifts and trails as its cards list them. The list of all lifts
    at the top of the page repeats them and is not an area."""
    areas = []
    for section in AREA.split(page)[1:]:
        title = AREA_NAME.search(section)
        if not title:
            continue
        lifts = [status_row(text_of(lift), status, None) for status, lift in LIFT.findall(section)]
        trails = [trail_row(attributes, trail) for attributes, trail in TRAIL.findall(section)]
        counted = {kind: int(total) for kind, total in AREA_COUNT.findall(section)}
        if (len(lifts), len(trails)) != (counted.get("Lifts", 0), counted.get("Trails", 0)):
            raise ValueError(f"{text_of(title.group(1))} counts {counted} but {len(lifts)} lifts and "
                             f"{len(trails)} trails were read")
        trails = [row for row, kind in trails if kind not in NOT_SKIED]
        if lifts or trails:
            areas.append({"Name": text_of(title.group(1)), "Lifts": lifts, "Trails": trails})
    if not any(area["Lifts"] for area in areas):
        raise ValueError("the page lists no lifts")
    return {"Name": name, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8")


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    resorts = {}
    for key, (name, url) in RESORTS.items():
        try:
            resorts[key] = parse(name, fetch(url), now)
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
              f"{len(trails)} trails ({sum(t['StatusEnglish'] == 'open' for t in trails)} open)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
