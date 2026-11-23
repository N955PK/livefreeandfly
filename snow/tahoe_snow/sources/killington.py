"""Killington's and Pico's lifts and trails, and their snowfall, from their lifts-and-trails status pages.

The two share one site design: the page is built on the server, one section per area of the mountain, each lift and
trail a card that carries its status (and a trail its difficulty and type) as data attributes. The site does not let
a browser on another site read it, so a scheduled job reads it and writes one small file the page reads, in the
shape of the Ikon feed the rest of the page uses. Uphill routes are left out. Each area's own count of lifts and
trails is checked against what is read, so a redesign fails instead of showing wrong numbers. One resort that fails
is left out of the file without costing the other. Every page of the site carries the snow report's figures
(new snow over 24 and 48 hours and 7 days, the season's total, and when they were posted, in Eastern time), so
they are read from the same page, in the shape of the Ikon feed's snow report. The site gives no base depth.
Standard library only.
python -m tahoe_snow.sources.killington out.json
"""
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
SNOW_BLOCK = re.compile(r'<div class="dor-snow-report">(.*?)</div>\s*</div>', re.S)
SNOW_DATE = re.compile(r'<div class="condition-report-date">\s*Updated\s+(.*?)\s*</div>', re.S)
SNOW_CELL = re.compile(r'<div class="dor-snow-label">(.*?)</div>.*?<div class="dor-snow-val">(.*?)</div>', re.S)
# The report's labels, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"24 hour": "Last24HoursIn", "48 hour": "Last48HoursIn", "7 day": "Last7DaysIn", "season": "SeasonTotalIn"}
EASTERN = ZoneInfo("America/New_York")
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


def snow_report(page: str) -> dict | None:
    """The snow report's figures in the shape of the Ikon feed's SnowReport: snowfall only, for the whole mountain
    (the site gives no base depth, so there is none, not a zero). None when the page carries no report."""
    block = SNOW_BLOCK.search(page)
    if not block:
        return None
    stamp = SNOW_DATE.search(block.group(1))
    if not stamp:
        raise ValueError("the snow report has no date")
    posted = datetime.strptime(text_of(stamp.group(1)), "%B %d, %Y %I:%M %p").replace(tzinfo=EASTERN)
    figures = {}
    for label, value in SNOW_CELL.findall(block.group(1)):
        field = SNOWFALL.get(text_of(label).lower())
        number = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:"|&quot;|in)?', text_of(value))
        if field:
            figures[field] = (float(number.group(1)) if "." in number.group(1) else int(number.group(1))) if number else None
    if "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no 24-hour figure")
    area = {"Name": "Mountain", **{key: value for key, value in figures.items() if key != "SeasonTotalIn"}}
    return {"LastUpdate": posted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "SeasonTotalIn": figures.get("SeasonTotalIn"), "BaseArea": area}


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
    feed = {"Name": name, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas}
    try:
        snow = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed


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
              f"{len(trails)} trails ({sum(t['StatusEnglish'] == 'open' for t in trails)} open)"
              + (f"; 24 h {feed['SnowReport']['BaseArea']['Last24HoursIn']} in, posted {feed['SnowReport']['LastUpdate']}"
                 if feed.get("SnowReport") else "; no snow report"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
