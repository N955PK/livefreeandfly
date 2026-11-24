"""Lift and trail status from Vail's resorts' own status pages: Heavenly, Northstar, Kirkwood, in New England
Stowe, Okemo, Mount Snow, Wildcat, Attitash, Mount Sunapee and Crotched, Stevens Pass near Seattle, and Park City in Utah.

Each resort's lift and terrain status page carries its feed as a JSON literal in the page source. The sites
reject plain HTTP clients, so the page is read with curl_cffi, which presents a browser TLS fingerprint.
Writes one small file the page reads, each mountain in the shape of the Ikon feed the rest of the page uses.
The pages are read a few at a time, so a pass over all of them takes seconds, and one resort that fails or
has posted nothing yet is left out of the file without costing the others.
python -m tahoe_snow.sources.resort_status out.json
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from curl_cffi import requests

# The resorts name the page two ways; each is given the name its own site links to.
TERRAIN_AND_LIFT, LIFT_AND_TERRAIN = "terrain-and-lift-status.aspx", "lift-and-terrain-status.aspx"
RESORTS = {
    "heavenly": ("Heavenly", "www.skiheavenly.com", TERRAIN_AND_LIFT),
    "northstar": ("Northstar", "www.northstarcalifornia.com", TERRAIN_AND_LIFT),
    "kirkwood": ("Kirkwood", "www.kirkwood.com", TERRAIN_AND_LIFT),
    "stowe": ("Stowe", "www.stowe.com", TERRAIN_AND_LIFT),
    "okemo": ("Okemo", "www.okemo.com", LIFT_AND_TERRAIN),
    "mountsnow": ("Mount Snow", "www.mountsnow.com", LIFT_AND_TERRAIN),
    "wildcat": ("Wildcat", "www.skiwildcat.com", LIFT_AND_TERRAIN),
    "attitash": ("Attitash", "www.attitash.com", LIFT_AND_TERRAIN),
    "sunapee": ("Mount Sunapee", "www.mountsunapee.com", LIFT_AND_TERRAIN),
    "crotched": ("Crotched", "www.crotchedmtn.com", LIFT_AND_TERRAIN),
    "stevens": ("Stevens Pass", "www.stevenspass.com", LIFT_AND_TERRAIN),
    "parkcity": ("Park City", "www.parkcitymountain.com", TERRAIN_AND_LIFT),
}
URL = "https://{host}/the-mountain/mountain-conditions/{page}"
# Pages read at once, and how long one may take: the collector passes every five minutes, so a pass over all of
# them, even with every site slow, stays well under a minute.
WORKERS, TIMEOUT = 5, 20
FEED = "FR.TerrainStatusFeed"
LIFT_STATUS = {0: "Closed", 1: "Open", 2: "Hold", 3: "Scheduled"}
DIFFICULTY = {1: "Green", 2: "Blue", 3: "Black", 4: "Double black"}


def feed_of(html: str) -> dict:
    """The JSON literal assigned to FR.TerrainStatusFeed in the page source."""
    match = re.search(re.escape(FEED) + r"\s*=\s*", html)
    if not match:
        raise ValueError(f"{FEED} not found in page")
    feed, _ = json.JSONDecoder().raw_decode(html[match.end():])
    if not feed.get("IsSuccessful"):
        raise ValueError(f"feed reported an error: {feed.get('ErrorDetails')}")
    if not feed.get("Lifts") and not any(area.get("Trails") for area in feed.get("GroomingAreas", [])):
        # A resort before its season publishes its areas with nothing in them; that is no status yet, not a closed mountain.
        raise ValueError("feed has no lifts or trails")
    return feed


def lift_row(lift: dict) -> dict:
    status = LIFT_STATUS.get(lift["Status"], "Closed")
    return {"Name": lift["Name"], "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def trail_row(trail: dict) -> dict:
    """A trail in the page's shape. Grooming is given (as the Ikon feed gives it, "Yes" or "No") only when the resort
    says one way or the other; before the season and on some days the feed leaves it unsaid."""
    status = "Open" if trail["IsOpen"] else "Closed"
    row = {"Name": trail["Name"], "Status": status, "StatusEnglish": status.lower(),
           "Difficulty": DIFFICULTY.get(trail["Difficulty"], "")}
    if isinstance(trail.get("IsGroomed"), bool):
        row["Grooming"] = "Yes" if trail["IsGroomed"] else "No"
    return row


def recast(name: str, feed: dict, now: datetime) -> dict:
    """The feed in the page's shape: one mountain area per grooming area, lifts placed by the area they serve."""
    lifts = feed["Lifts"]
    areas = []
    for area in feed["GroomingAreas"]:
        mine = [lift_row(lift) for lift in lifts if lift["Mountain"] == area["Name"]]
        trails = [trail_row(trail) for trail in area["Trails"]]
        if mine or trails:
            areas.append({"Name": area["Name"], "Lifts": mine, "Trails": trails})
    placed = {lift["Name"] for area in areas for lift in area["Lifts"]}
    stray = [lift_row(lift) for lift in lifts if lift["Name"] not in placed]
    if stray:
        areas.append({"Name": name, "Lifts": stray, "Trails": []})
    return {"Name": name, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": areas}


def counts(feed: dict) -> str:
    """A line for the log: the mountain's lifts and trails, and how many of each are open."""
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    open_ = lambda rows: sum(row["StatusEnglish"].startswith("open") for row in rows)
    return f"{feed['Name']}: {len(lifts)} lifts ({open_(lifts)} open), {len(trails)} trails ({open_(trails)} open)"


def fetch(host: str, page: str) -> dict:
    response = requests.get(URL.format(host=host, page=page), impersonate="chrome", timeout=TIMEOUT)
    response.raise_for_status()
    return feed_of(response.text)


def read(key: str, now: datetime) -> dict | None:
    """One resort in the page's shape, or None when its page could not be read or it has posted nothing."""
    name, host, page = RESORTS[key]
    try:
        return recast(name, fetch(host, page), now)
    except Exception as error:
        print(f"{name}: {error}")
        return None


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    with ThreadPoolExecutor(WORKERS) as pool:
        found = dict(zip(RESORTS, pool.map(lambda key: read(key, now), RESORTS)))
    resorts = {key: feed for key, feed in found.items() if feed}
    if not resorts:
        return 1
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": resorts}, handle, separators=(",", ":"))
    for feed in resorts.values():
        print(counts(feed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
