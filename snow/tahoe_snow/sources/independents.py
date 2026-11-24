"""Lifts, trails and snow reports of the mountains that each run their own website: New England's independents,
Jackson Hole and Grand Targhee in the Tetons, and six of the Wasatch's resorts.

Each mountain has a module of its own that knows its page (``URL``, or ``URLS`` where it takes more than one request)
and reads it (``parse``). This runs them all and writes one file the page reads, in the shape of the Ikon feed the
rest of the page uses. A mountain whose page cannot be read is left out without costing the others.

Two things are settled here so every mountain's report reads the same way. A depth or snowfall a mountain gives
only as a range is also given as the middle of it, which is what the map takes. And a mountain with no lift turning
whose report is undated, or older than ``STALE_DAYS``, has its snow report left out: several of these pages keep
last season's figures up until the mountain opens. Standard library only.
python -m tahoe_snow.sources.independents out.json
"""
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from tahoe_snow.sources import (alta, blackmountain, bolton, brettonwoods, brighton, bromley, burke, cannon,
                                cranmore, jacksonhole, jaypeak, madriverglen, magic, powdermountain, saddleback,
                                smugglers, snowbasin, snowbird, sundance, targhee, waterville)

TIMEOUT = 20
STALE_DAYS = 14
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MODULES = {"jaypeak": jaypeak, "burke": burke, "smugglers": smugglers, "bolton": bolton,
           "madriverglen": madriverglen, "bromley": bromley, "magic": magic, "cannon": cannon,
           "brettonwoods": brettonwoods, "waterville": waterville, "cranmore": cranmore,
           "blackmountain": blackmountain, "saddleback": saddleback,
           "jacksonhole": jacksonhole, "targhee": targhee,
           "alta": alta, "snowbird": snowbird, "brighton": brighton, "snowbasin": snowbasin,
           "powdermountain": powdermountain, "sundance": sundance}
# The figures a mountain may give as a low and a high: "BaseIn" beside "BaseMinIn" and "BaseMaxIn", and so on.
RANGED = ("Base", "Last24Hours")


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8")


def middles(snow: dict) -> dict:
    """The report with the middle of each range filled in where the mountain gave only its two ends."""
    for at in snow.values():
        if not isinstance(at, dict):
            continue
        for field in RANGED:
            low, high = at.get(f"{field}MinIn"), at.get(f"{field}MaxIn")
            if at.get(f"{field}In") is None and low is not None and high is not None:
                at[f"{field}In"] = round((float(low) + float(high)) / 2, 1)
    return snow


def turning(feed: dict) -> bool:
    return any(lift["StatusEnglish"] == "open" for area in feed["MountainAreas"] for lift in area["Lifts"])


def stale(snow: dict, now: datetime) -> bool:
    """Whether a snow report is undated or older than STALE_DAYS."""
    posted = snow.get("LastUpdate")
    if not posted:
        return True
    try:
        at = datetime.strptime(posted, STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - at > timedelta(days=STALE_DAYS)


def settled(feed: dict, now: datetime) -> dict:
    """A mountain's feed as the page gets it: ranges given a middle, and a closed mountain's old report left out."""
    snow = feed.get("SnowReport")
    if snow and not turning(feed) and stale(snow, now):
        del feed["SnowReport"]
    elif snow:
        middles(snow)
    return feed


def read(module, now: datetime) -> dict:
    if hasattr(module, "URLS"):
        return module.parse({name: fetch(url) for name, url in module.URLS.items()}, now)
    return module.parse(fetch(module.URL), now)


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    resorts = {}
    for key, module in MODULES.items():
        try:
            resorts[key] = settled(read(module, now), now)
        except Exception as error:
            print(f"{key}: {error}")
    if not resorts:
        return 1
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime(STAMP), "resorts": resorts}, handle, separators=(",", ":"))
    for key, feed in resorts.items():
        lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
        trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
        base = (feed.get("SnowReport") or {}).get("BaseArea") or {}
        print(f"{feed['Name']}: {len(lifts)} lifts ({sum(l['StatusEnglish'] == 'open' for l in lifts)} open), "
              f"{len(trails)} trails ({sum(t['StatusEnglish'] == 'open' for t in trails)} open)"
              + (f"; base {base.get('BaseIn')} in" if "SnowReport" in feed else "; no snow report"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
