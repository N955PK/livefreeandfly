"""Keep score: this app's snow forecast, OpenSnow's and Snow-Forecast's, each against what the snow sensors measured.

Nothing else says whether one forecast is better than another: on any one day they simply disagree. So once a day
this saves what all three forecast for every resort whose forecast is corrected to a snow sensor (a snapshot), and
when the days forecast have passed it sets each against the snow the sensor measured.

    python -m tahoe_snow.compare FOLDER        (from the snow folder)

FOLDER is kept on a branch of its own (snow-compare) by the workflow that runs this:
    forecasts/YYYY-MM-DD.json   the day's snapshot, written once
    observed.json               the snow each sensor measured, day by day
    score.json, score.md        the score so far

What is compared, and its limits:
  * Snowfall in inches by local calendar day. A sensor weighs water; its snowfall is that water on a day cold enough
    to snow times a snow ratio for the day's temperature (season.daily_snowfall_in), the app's own reckoning
    everywhere. It is an estimate, and it is ours: where the truth is in doubt it leans our way.
  * Snow-Forecast publishes six days in three parts a day, at the top, middle and bottom of a mountain; the level
    nearest the sensor is read. OpenSnow publishes five-day totals at one elevation of its own choosing. Neither
    publishes more than that to a visitor with no account, and only what a visitor is shown is read.
  * One page of each site per mountain per day, a second apart. A site that refuses is left out for the day; a
    refusal is never worked around.
This app's own figures come from the forecast it has published, at the level nearest the sensor. No weather service
is asked for anything.
"""
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tahoe_snow import season
from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, ALL_STATIONS

SITES = json.loads((Path(__file__).parent / "compare_sites.json").read_text())
PUBLISHED = "https://raw.githubusercontent.com/N955PK/livefreeandfly"
SF_PAGE = "https://www.snow-forecast.com/resorts/{slug}/6day/{level}"
OS_PAGE = "https://opensnow.com/location/{slug}/snow-summary"
AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
PAUSE_S, TIMEOUT_S = 1.0, 30
CM_PER_IN = 2.54
# Snow-Forecast gives each whole day in three parts; a day with fewer is the rest of today.
SF_PARTS = 3
# How far back the sensors are read, and so how old a snapshot can be and still be scored.
OBSERVED_DAYS = 30
# A day ahead is tomorrow. Five days is as far as Snow-Forecast's whole days reach.
LEADS = range(1, 13)
OS_SPANS = {"d1_5": (0, 5), "d6_10": (5, 10)}


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as reply:
        return reply.read().decode("utf-8", "replace")


def branch_of(region: str) -> str:
    collector = ALL_REGIONS[region].collector
    return "snow-data" if collector == "main" else f"snow-data-{collector}"


def level_near(resort, station) -> str:
    """The level of the mountain's forecast nearest the sensor's height."""
    levels = resort.elevations()
    return min(levels, key=lambda label: abs(levels[label] - station.elev_m))


# ---------- the three forecasts ----------
def ours(forecast: dict, key: str, level: str) -> dict | None:
    """This app's snowfall by day from today on, from a region's published forecast."""
    resort = next((r for r in forecast.get("resorts", []) if r["key"] == key), None)
    if resort is None:
        return None
    days = {day["date"]: day["snow_in"] for day in resort["elevations"][level]["days"]
            if day["lead_day"] >= 0 and day["snow_in"] is not None}
    return {"published_utc": forecast.get("published_utc"), "days": days} if days else None


def snow_forecast(page: str) -> dict:
    """Snow-Forecast's snowfall by day (inches), and which of those days are whole. Raises on a page it does not know."""
    days = re.search(r'data-row="days".*?</tr>', page, flags=re.S)
    snow = re.search(r'data-row="snow".*?</tr>', page, flags=re.S)
    if not days or not snow:
        raise ValueError("no forecast table")
    spans = [(int(parts), date) for parts, date in
             re.findall(r'<td[^>]*colspan="(\d+)"[^>]*data-date="(\d{4}-\d\d-\d\d)"', days.group(0))]
    unit = re.search(r'class="snowu">([^<]*)', snow.group(0))
    cells = [re.sub(r"<[^>]+>", "", cell).strip() for cell in
             re.findall(r'<td class="forecast-table__cell[^"]*"[^>]*>(.*?)</td>', snow.group(0), flags=re.S)]
    if not spans or unit is None or unit.group(1) not in ("cm", "in") or len(cells) != sum(n for n, _ in spans):
        raise ValueError("forecast table not as expected")
    per_inch = CM_PER_IN if unit.group(1) == "cm" else 1.0
    values = [0.0 if cell in ("—", "-", "") else float(cell) for cell in cells]
    out, at = {"days": {}, "whole": []}, 0
    for parts, date in spans:
        out["days"][date] = round(sum(values[at:at + parts]) / per_inch, 1)
        if parts == SF_PARTS:
            out["whole"].append(date)
        at += parts
    return out


def open_snow(page: str, tz: str) -> dict:
    """OpenSnow's five-day totals (inches), the day the first of them starts on, and the elevation they are for.
    The page carries its figures as one flat list whose entries point at each other by position."""
    found = re.search(r'id="__NUXT_DATA__">(.*?)</script>', page, flags=re.S)
    if not found:
        raise ValueError("no page data")
    flat = json.loads(found.group(1))
    place = next((entry for entry in flat if isinstance(entry, dict) and "forecast_snow_summary" in entry
                  and "elevation" in entry), None)
    if place is None:
        raise ValueError("no snow summary")
    spans = [flat[at] for at in flat[place["forecast_snow_summary"]]]
    if len(spans) < 2:
        raise ValueError("snow summary not as expected")
    totals = []
    for span in spans[:3]:
        label, amount, count = flat[span["display_at_local_label"]], flat[span["precip_snow"]], flat[span["period_count"]]
        if count != 5 or not str(label).startswith("Next "):
            raise ValueError("snow summary is not five-day totals")
        totals.append(None if amount is None else float(amount))
    start = pd.Timestamp(flat[spans[0]["display_at"]]).tz_convert(tz).strftime("%Y-%m-%d")
    out = {"from": start, "elevation_ft": flat[place["elevation"]], "d1_5": totals[0], "d6_10": totals[1]}
    if len(totals) > 2:
        out["d11_15"] = totals[2]
    return out


def snapshot(now: datetime, fetch=get, pause_s: float = PAUSE_S) -> dict:
    """What all three forecast right now, for every mountain in the list."""
    forecasts, mountains = {}, {}
    for key, site in SITES.items():
        resort = ALL_RESORTS[key]
        station = ALL_STATIONS[resort.station]
        tz = ALL_REGIONS[resort.region or "tahoe"].tz
        level = level_near(resort, station)
        entry = {"level": level, "today": pd.Timestamp(now).tz_convert(tz).strftime("%Y-%m-%d"), "ours": None,
                 "snow_forecast": None, "open_snow": None}
        region = resort.region or "tahoe"
        if region not in forecasts:
            try:
                forecasts[region] = json.loads(fetch(f"{PUBLISHED}/{branch_of(region)}/forecast/{region}.json"))
            except (OSError, ValueError) as error:
                print(f"{region}: our forecast FAILED {str(error)[:120]}", flush=True)
                forecasts[region] = {}
        entry["ours"] = ours(forecasts[region], key, level)
        for name, url, read in (
                ("snow_forecast", site.get("sf") and SF_PAGE.format(slug=site["sf"], level=site["sf_level"]), snow_forecast),
                ("open_snow", site.get("os") and OS_PAGE.format(slug=site["os"]), lambda page: open_snow(page, tz))):
            if not url:
                continue
            try:
                entry[name] = read(fetch(url))
            except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
                print(f"{key}: {name} FAILED {str(error)[:120]}", flush=True)
            time.sleep(pause_s)
        mountains[key] = entry
    return {"read_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "mountains": mountains}


# ---------- what the sensors measured ----------
def observed(now: datetime, history=season.history) -> dict:
    """Snowfall by day at each mountain's sensor over the last weeks, in inches. A sensor that cannot be read, or
    one with no daily record, is left out."""
    day = pd.Timestamp(now).tz_convert("UTC").tz_localize(None).normalize()
    start = (day - pd.Timedelta(days=OBSERVED_DAYS)).strftime("%Y-%m-%d")
    out = {}
    for key in SITES:
        station = ALL_STATIONS[ALL_RESORTS[key].station]
        if station.source in season.NO_RECORD:
            continue
        try:
            snow = season.daily_snowfall_in(history(station, day, start)).dropna()
        except (RuntimeError, OSError, ValueError, KeyError, IndexError) as error:
            print(f"{key}: sensor FAILED {str(error)[:120]}", flush=True)
            continue
        out[key] = {date.strftime("%Y-%m-%d"): round(float(value), 1) for date, value in snow.items()}
    return out


# ---------- the score ----------
def _stats(errors: list) -> dict | None:
    if not errors:
        return None
    errors = np.asarray(errors, dtype=float)
    return {"n": int(len(errors)), "mean_error_in": round(float(np.abs(errors).mean()), 2),
            "bias_in": round(float(errors.mean()), 2)}


def score(snapshots: list, measured: dict) -> dict:
    """Each source's miss against the sensors: day by day for the two that publish days, and over five-day spans
    for all three. ``same_days`` counts only mountain-days both daily sources forecast, so neither is scored on an
    easier set than the other."""
    daily = {"ours": {}, "snow_forecast": {}}
    paired = {"ours": {}, "snow_forecast": {}}
    spans = {name: {"ours": [], "open_snow": [], "snow_forecast": []} for name in OS_SPANS}
    for snap in snapshots:
        for key, entry in snap["mountains"].items():
            seen = measured.get(key, {})
            today = pd.Timestamp(entry["today"])
            date_at = lambda lead: (today + pd.Timedelta(days=lead)).strftime("%Y-%m-%d")
            mine = (entry.get("ours") or {}).get("days", {})
            theirs = entry.get("snow_forecast") or {"days": {}, "whole": []}
            for lead in LEADS:
                date = date_at(lead)
                if date not in seen:
                    continue
                a = mine.get(date)
                b = theirs["days"].get(date) if date in theirs["whole"] else None
                if a is not None:
                    daily["ours"].setdefault(lead, []).append(a - seen[date])
                if b is not None:
                    daily["snow_forecast"].setdefault(lead, []).append(b - seen[date])
                if a is not None and b is not None:
                    paired["ours"].setdefault(lead, []).append(a - seen[date])
                    paired["snow_forecast"].setdefault(lead, []).append(b - seen[date])
            other = entry.get("open_snow")
            if not other or not other.get("from"):
                continue
            # OpenSnow's five days start on the day its page says, which turns over in the evening, hours before
            # the mountain's own midnight; all three are totalled over those same days.
            base = pd.Timestamp(other["from"])
            for name, (first, last) in OS_SPANS.items():
                dates = [(base + pd.Timedelta(days=lead)).strftime("%Y-%m-%d") for lead in range(first, last)]
                if other.get(name) is None or any(d not in seen for d in dates) or any(d not in mine for d in dates):
                    continue
                fell = sum(seen[d] for d in dates)
                spans[name]["ours"].append(sum(mine[d] for d in dates) - fell)
                spans[name]["open_snow"].append(other[name] - fell)
                # Snow-Forecast's first day is only the rest of today, so its five days are a little short.
                if all(d in theirs["days"] for d in dates):
                    spans[name]["snow_forecast"].append(sum(theirs["days"][d] for d in dates) - fell)
    by_lead = lambda table: {source: {str(lead): _stats(errors) for lead, errors in sorted(rows.items())}
                             for source, rows in table.items()}
    return {"snapshots": len(snapshots), "first": snapshots[0]["read_utc"] if snapshots else None,
            "last": snapshots[-1]["read_utc"] if snapshots else None,
            "by_day": by_lead(daily), "same_days": by_lead(paired),
            "five_days": {name: {source: _stats(errors) for source, errors in rows.items()} for name, rows in spans.items()}}


NAMES = {"ours": "Turbo Snow", "open_snow": "OpenSnow", "snow_forecast": "Snow-Forecast"}


def report(card: dict) -> str:
    """The score as a page to read."""
    cell = lambda s: "–" if not s else f"{s['mean_error_in']:.1f} ({s['bias_in']:+.1f}, {s['n']})"
    lines = ["# Snow forecasts against the sensors", "",
             f"{card['snapshots']} daily snapshots, {card['first'] or '–'} to {card['last'] or '–'}. Each cell is the "
             "average miss in inches, then (the average error with its sign, the number of mountain-days). "
             "A positive sign is too much snow forecast.", "",
             "## Day by day, on the mountain-days both forecast", "", "| Days ahead | Turbo Snow | Snow-Forecast |", "|---|---|---|"]
    both = card["same_days"]
    for lead in sorted({*both["ours"], *both["snow_forecast"]}, key=int):
        lines.append(f"| {lead} | {cell(both['ours'].get(lead))} | {cell(both['snow_forecast'].get(lead))} |")
    lines += ["", "## Turbo Snow day by day, as far ahead as it forecasts", "", "| Days ahead | Turbo Snow |", "|---|---|"]
    lines += [f"| {lead} | {cell(stats)} |" for lead, stats in sorted(card["by_day"]["ours"].items(), key=lambda kv: int(kv[0]))]
    lines += ["", "## Five-day totals", "", "| Span | Turbo Snow | OpenSnow | Snow-Forecast |", "|---|---|---|---|"]
    for name, label in (("d1_5", "OpenSnow's first five days"), ("d6_10", "The five days after those")):
        row = card["five_days"][name]
        lines.append(f"| {label} | {cell(row['ours'])} | {cell(row['open_snow'])} | {cell(row['snow_forecast'])} |")
    lines += ["", "The sensors' snowfall is water weighed, turned to snow by this app's own snow ratio, so where the "
              "truth is in doubt it leans this app's way. Snow-Forecast's five days start partway through today. "
              "OpenSnow's figure is for an elevation of its choosing, which is not always the sensor's.", ""]
    return "\n".join(lines)


def run(folder: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    root = Path(folder)
    (root / "forecasts").mkdir(parents=True, exist_ok=True)
    today = root / "forecasts" / f"{now:%Y-%m-%d}.json"
    if not today.exists():
        today.write_text(json.dumps(snapshot(now), separators=(",", ":")))
    seen_path = root / "observed.json"
    measured = json.loads(seen_path.read_text()) if seen_path.exists() else {}
    for key, days in observed(now).items():
        # A later reading of a day replaces an earlier one: sensors' records are revised.
        measured.setdefault(key, {}).update(days)
    seen_path.write_text(json.dumps(measured, separators=(",", ":"), sort_keys=True))
    snapshots = [json.loads(path.read_text()) for path in sorted((root / "forecasts").glob("*.json"))]
    card = score(snapshots, measured)
    (root / "score.json").write_text(json.dumps(card, indent=1))
    (root / "score.md").write_text(report(card))
    return card


if __name__ == "__main__":
    result = run(sys.argv[1])
    print(f"{result['snapshots']} snapshots; scored days ahead: {sorted(result['by_day']['ours'], key=int)}")
