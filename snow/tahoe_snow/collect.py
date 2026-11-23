"""A running record of everything live the snow page reads and shows, kept so the page's own predictions (lift
holds, late openings, surface, road trouble) can be checked against what happened and re-fitted later.

Each pass reads every live source once and appends what changed to a folder for the day (UTC):

    2026-11-22/ikon61.lifts.jsonl      one line each time that part's content changes: {"utc": ..., "data": ...}
    2026-11-22/runs.jsonl              one line per pass: which parts were read, which changed, which sources failed
    forecast/2026-11-22T17-52-11Z.json.gz   the published forecast each time a new one appears, cut down
    state.json                         the last content seen for each part (a hash), so a restart writes no repeats

A part that reads the same as last time writes nothing, so the record of a quiet night is small; the runs file
says the part was read and unchanged, which is how a later script knows the state held between two lines.

Sources, and the parts each gives:
    the Ikon feed (Palisades and Alpine, Mammoth, June): lifts, trails with grooming, the resort's weather
        stations, its snow report (figures and words)
    the resort status files the lifts job writes (Heavenly, Northstar, Kirkwood, Homewood, Boreal): lifts, trails
    Sierra-at-Tahoe's feed: lifts, trails, weather;  Mt. Rose's and Sugar Bowl's status pages: lifts (and trails)
    Caltrans chain controls (districts 3, 10, 9) and full closures (district 9);  the Nevada roads file
    the avalanche centers' zones and danger, and each zone's forecast
    the published forecast

Standard library only. The resort status and Nevada files are written by their own modules first and passed in.
python -m tahoe_snow.collect HISTORY_DIR [--lifts DIR] [--nevada FILE]
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone

from tahoe_snow import config

AGENT = {"User-Agent": "sierra-snow"}
IKON = {61: "ikon61", 60: "ikon60", 59: "ikon59"}  # Palisades and Alpine, Mammoth, June
IKON_FEED = "https://mtnpowder.com/feed?resortId={id}"
SIERRA = "https://sierraattahoe.com/wp-json/sierra/v1/{name}"
MT_ROSE = "https://skirose.com/wp-json/wp/v2/pages?slug=snow-report&_fields=content"
SUGAR_BOWL = "https://www.sugarbowl.com/conditions"
CHAINS = "https://cwwp2.dot.ca.gov/data/d{d}/cc/ccStatusD{d:02d}.json"
CLOSURES = "https://cwwp2.dot.ca.gov/data/d{d}/lcs/lcsStatusD{d:02d}.json"
CHAIN_DISTRICTS, CLOSURE_DISTRICTS = (3, 10, 9), (9,)
AVALANCHE = "https://api.avalanche.org/v2/public"
CENTERS = config.avalanche_centers()
FORECAST = "https://raw.githubusercontent.com/N955PK/livefreeandfly/snow-data/forecast.json"
# What is kept of a weather station and of a snow stake in the Ikon feed.
STATION = ("TemperatureF", "WindDirection", "WindStrengthMph", "WindGustsMph", "Humidity", "Skies")
STAKE = ("BaseIn", "Last24HoursIn", "Last48HoursIn", "Last72HoursIn", "Last7DaysIn", "SinceLiftsClosedIn")
STAKES = ("BaseArea", "MidMountainArea", "SummitArea", "Station4", "Station5", "Station6")
REPORT = ("LastUpdate", "BaseConditions", "SeasonTotalIn", "StormTotalIn", "TotalOpenLifts", "TotalLifts",
          "TotalOpenTrails", "TotalTrails", "GroomedTrails", "OpenTerrainAcres", "TotalTerrainAcres")
# Of the forecast's hourly figures, the hours from this long before a pass to this long after it are kept.
HOURS_BEFORE, HOURS_AFTER = 12, 72


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=30) as response:
        return response.read()


def get(url: str):
    return json.loads(fetch(url))


def plain(html: str | None) -> str:
    """Rich text as plain words."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    for mark, char in (("&nbsp;", " "), ("&amp;", "&"), ("&#8217;", "'"), ("&#8211;", "-"), ("&#038;", "&")):
        text = text.replace(mark, char)
    return re.sub(r"\s+", " ", text).strip()


def said(value) -> bool:
    return value not in (None, "", "--", "N/A")


# ---------- the sources: each returns {part name: content}, content holding nothing that changes on its own ----------
def areas_parts(name: str, areas: list) -> dict:
    """Lifts and trails by mountain area, each as {name: status}; a trail the resort marks groomed ends in " *"."""
    lifts = {area.get("Name"): {lift.get("Name"): lift.get("Status") for lift in area.get("Lifts") or []} for area in areas}
    trails = {area.get("Name"): {trail.get("Name"): (trail.get("Status") or "") + (" *" if str(trail.get("Grooming") or "").lower().startswith("y") else "")
                                 for trail in area.get("Trails") or []} for area in areas}
    return {f"{name}.lifts": {area: found for area, found in lifts.items() if found},
            f"{name}.trails": {area: found for area, found in trails.items() if found}}


def ikon(feed_id: int) -> dict:
    feed, name = get(IKON_FEED.format(id=feed_id)), IKON[feed_id]
    report = feed.get("SnowReport") or {}
    weather = {place: {field: station.get(field) for field in STATION if said(station.get(field))}
               for place, station in (feed.get("CurrentConditions") or {}).items() if isinstance(station, dict)}
    words = {"status": feed.get("OperatingStatus"), **{field: report.get(field) for field in REPORT if said(report.get(field))},
             "stakes": {stake: {field: report[stake].get(field) for field in STAKE if said(report[stake].get(field))}
                        for stake in STAKES if isinstance(report.get(stake), dict)},
             "report": plain(report.get("Report")), "alert": plain(report.get("Alert")) if said(report.get("Alert")) else ""}
    return {**areas_parts(name, feed.get("MountainAreas") or []), f"{name}.weather": {k: v for k, v in weather.items() if v},
            f"{name}.report": words}


def published(path: str) -> dict:
    """A file the lifts job wrote: {"updated": ..., "resorts": {key: feed in the Ikon shape}}."""
    with open(path) as handle:
        status = json.load(handle)
    out = {}
    for key, feed in (status.get("resorts") or {}).items():
        out.update(areas_parts(key, feed.get("MountainAreas") or []))
    return out


def sierra() -> dict:
    lifts, trails, weather = (get(SIERRA.format(name=name)) for name in ("lifts", "trails", "weather"))
    row = lambda item: (plain((item.get("title") or {}).get("rendered")), item.get("status"))
    now = dict(weather.get("current") or {})
    now.pop("last_updated", None)
    return {"sierra.lifts": dict(map(row, lifts)), "sierra.trails": dict(map(row, trails)), "sierra.weather": now}


def mt_rose() -> dict:
    page = get(MT_ROSE)[0]["content"]["rendered"]
    table = page[page.index('id="lift-status"'):]
    lifts = {}
    for row in re.split(r'class="[^"]*\brow data\b', table)[1:]:
        name, status = re.search(r'class="rose-name">(.*?)</div>', row, re.S), re.search(r'class="[^"]*column-status[^"]*">(.*?)</div>\s*</div>', row, re.S)
        if name and status:
            lifts[plain(name.group(1))] = plain(status.group(1))
    if not lifts:
        raise ValueError("Mt. Rose's lift table was not found")
    return {"mtrose.lifts": lifts}


def sugar_bowl() -> dict:
    page = fetch(SUGAR_BOWL).decode("utf-8", "replace")
    lifts = {plain(name): (re.sub(r"<[^>]+>", "", (re.search(rf'data-update-id="{lift}_status_text"[^>]*>(.*?)<', page, re.S) or [0, ""])[1]).strip() or icon)
             for icon, lift, name in re.findall(r'icon_lift_(\w+)\.svg"[^>]*data-update-id="(lift_\w+?)_status_icon".*?class="txt_0001_conditions">(.*?)</div>', page, re.S)}
    trails = {plain(name): plain(status) for name, status in
              re.findall(r'class="run_status_\w+ run_info_row".*?class="run_name[^"]*">(.*?)</div>\s*<div class="run_status"[^>]*>\s*<span[^>]*>(.*?)</span>', page, re.S)}
    if not lifts:
        raise ValueError("Sugar Bowl's lift list was not found")
    return {"sugarbowl.lifts": lifts, "sugarbowl.trails": trails}


def chains(district: int) -> dict:
    """The chain controls in force (anything but R-0), by control point."""
    found = {}
    for item in get(CHAINS.format(d=district)).get("data") or []:
        control = item["cc"]
        status, place = control.get("statusData") or {}, control.get("location") or {}
        if control.get("inService") == "true" and status.get("status") not in (None, "", "R-0"):
            stamp = status.get("statusTimestamp") or {}
            found[control["index"]] = {"route": place.get("route"), "name": place.get("locationName"), "direction": place.get("direction"),
                                       "status": status["status"], "words": status.get("statusDescription"),
                                       "since": f"{stamp.get('statusDate')}T{stamp.get('statusTime')}"}
    return {f"caltrans{district}.chains": found}


def closures(district: int) -> dict:
    """Full closures of a highway that are in force, as the page picks them out."""
    found = []
    for item in get(CLOSURES.format(d=district)).get("data") or []:
        closure, place = item["lcs"]["closure"], item["lcs"]["location"]
        if (closure.get("typeOfClosure") != "Full" or not re.search("hwy|highway|freeway|expressway", closure.get("facility") or "", re.I)
                or closure["code1097"]["isCode1097"] != "true" or closure["code1098"]["isCode1098"] == "true"):
            continue
        found.append({"route": place["begin"].get("beginRoute"), "from": (place["begin"].get("beginLocationName") or "").strip(),
                      "to": (place["end"].get("endLocationName") or "").strip(), "work": closure.get("typeOfWork"),
                      "since": closure["closureTimestamp"].get("closureStartEpoch")})
    return {f"caltrans{district}.closures": sorted(found, key=lambda c: (c["route"] or "", c["from"]))}


def nevada(path: str) -> dict:
    with open(path) as handle:
        status = json.load(handle)
    status.pop("updated", None)
    return {"nevada.roads": status}


def avalanche(center: str) -> dict:
    zones, out = {}, {}
    for feature in get(f"{AVALANCHE}/products/map-layer/{center}").get("features") or []:
        p = feature["properties"]
        zones[p.get("name")] = {"level": p.get("danger_level"), "advice": p.get("travel_advice"), "off_season": p.get("off_season"),
                                "warning": (p.get("warning") or {}).get("product"), "from": p.get("start_date"), "to": p.get("end_date")}
        try:
            product = get(f"{AVALANCHE}/product?type=forecast&center_id={center}&zone_id={feature['id']}")
        except Exception:  # the zones are still worth keeping when one forecast cannot be read
            continue
        out[f"avalanche.{center}.{feature['id']}"] = {
            "zone": p.get("name"), "published": product.get("published_time"), "expires": product.get("expires_time"),
            "danger": product.get("danger"), "bottom_line": plain(product.get("bottom_line")),
            "problems": [{"name": problem.get("name"), "likelihood": problem.get("likelihood"), "size": problem.get("size"),
                          "location": problem.get("location")} for problem in product.get("forecast_avalanche_problems") or []]}
    return {f"avalanche.{center}.zones": zones, **out}


def trimmed(forecast: dict, now: datetime) -> dict:
    """The forecast without the season curves and with its hourly figures cut to the hours around now."""
    first, last = ((now + timedelta(hours=h)).strftime("%Y-%m-%dT%H:00:00Z") for h in (-HOURS_BEFORE, HOURS_AFTER))
    out = {key: value for key, value in forecast.items() if key not in ("season_curves", "resorts")}
    out["resorts"] = []
    for resort in forecast.get("resorts") or []:
        hours = resort.get("hours_utc") or []
        keep = [n for n, stamp in enumerate(hours) if first <= stamp <= last]
        cut = lambda series: [series[n] for n in keep] if isinstance(series, list) and len(series) == len(hours) else series
        kept = {key: value for key, value in resort.items() if key not in ("elevations", "hours_utc")}
        kept["hours_utc"] = [hours[n] for n in keep]
        kept["elevations"] = {level: {**part, "hourly": {name: cut(series) for name, series in (part.get("hourly") or {}).items()}}
                              for level, part in (resort.get("elevations") or {}).items()}
        out["resorts"].append(kept)
    return out


# ---------- the record ----------
def digest(content) -> str:
    return hashlib.sha1(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def collect(history: str, lifts_dir: str | None, nevada_file: str | None, now: datetime) -> dict:
    """One pass. Returns the line written to the day's runs file."""
    readers = {**{IKON[feed_id]: (lambda feed_id=feed_id: ikon(feed_id)) for feed_id in IKON},
               "sierra": sierra, "mtrose": mt_rose, "sugarbowl": sugar_bowl,
               **{f"caltrans{d}.chains": (lambda d=d: chains(d)) for d in CHAIN_DISTRICTS},
               **{f"caltrans{d}.closures": (lambda d=d: closures(d)) for d in CLOSURE_DISTRICTS},
               **{f"avalanche.{center}": (lambda center=center: avalanche(center)) for center in CENTERS}}
    for name in ("resort_status", "homewood", "boreal", "boyne", "killington", "missionridge"):
        path = os.path.join(lifts_dir or "", f"{name}.json")
        if lifts_dir and os.path.exists(path):
            readers[name] = lambda path=path: published(path)
    if nevada_file and os.path.exists(nevada_file):
        readers["nevada"] = lambda: nevada(nevada_file)

    state_path = os.path.join(history, "state.json")
    try:
        with open(state_path) as handle:
            state = json.load(handle)
    except (FileNotFoundError, ValueError):
        state = {}
    stamp, day = now.strftime("%Y-%m-%dT%H:%M:%SZ"), os.path.join(history, now.strftime("%Y-%m-%d"))
    os.makedirs(day, exist_ok=True)
    run = {"utc": stamp, "read": [], "changed": [], "failed": {}}
    for source, reader in readers.items():
        try:
            parts = reader()
        except Exception as error:  # one source down must not cost the rest of the pass
            run["failed"][source] = f"{type(error).__name__}: {error}"[:200]
            continue
        for part, content in parts.items():
            run["read"].append(part)
            mark = digest(content)
            if state.get(part) == mark:
                continue
            state[part] = mark
            run["changed"].append(part)
            with open(os.path.join(day, f"{part}.jsonl"), "a") as handle:
                handle.write(json.dumps({"utc": stamp, "data": content}, separators=(",", ":")) + "\n")

    try:
        forecast = get(FORECAST)
        published_at = forecast.get("published_utc") or forecast.get("generated_utc")
        run["forecast"] = published_at
        if published_at and state.get("forecast") != published_at:
            os.makedirs(os.path.join(history, "forecast"), exist_ok=True)
            with gzip.open(os.path.join(history, "forecast", published_at.replace(":", "-") + ".json.gz"), "wt") as handle:
                json.dump(trimmed(forecast, now), handle, separators=(",", ":"))
            state["forecast"] = published_at
            run["changed"].append("forecast")
    except Exception as error:
        run["failed"]["forecast"] = f"{type(error).__name__}: {error}"[:200]

    with open(state_path, "w") as handle:
        json.dump(state, handle, indent=0, sort_keys=True)
    with open(os.path.join(day, "runs.jsonl"), "a") as handle:
        handle.write(json.dumps(run, separators=(",", ":")) + "\n")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("history")
    parser.add_argument("--lifts")
    parser.add_argument("--nevada")
    args = parser.parse_args()
    run = collect(args.history, args.lifts, args.nevada, datetime.now(timezone.utc))
    print(f"{len(run['read'])} parts read, {len(run['changed'])} changed" + (f"; failed: {', '.join(run['failed'])}" if run["failed"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
