"""Lift and trail status from the resorts' own status pages (Heavenly, Northstar, Kirkwood).

Each resort's lift and terrain status page carries its feed as a JSON literal in the page source. The sites
reject plain HTTP clients, so the page is read with curl_cffi, which presents a browser TLS fingerprint.
Writes one small file the page reads, each mountain in the shape of the Ikon feed the rest of the page uses.
python -m tahoe_snow.sources.resort_status out.json
"""
import json
import re
import sys
from datetime import datetime, timezone

from curl_cffi import requests

RESORTS = {
    "heavenly": ("Heavenly", "www.skiheavenly.com"),
    "northstar": ("Northstar", "www.northstarcalifornia.com"),
    "kirkwood": ("Kirkwood", "www.kirkwood.com"),
}
URL = "https://{host}/the-mountain/mountain-conditions/terrain-and-lift-status.aspx"
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


def fetch(host: str) -> dict:
    response = requests.get(URL.format(host=host), impersonate="chrome", timeout=30)
    response.raise_for_status()
    return feed_of(response.text)


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    resorts = {}
    for key, (name, host) in RESORTS.items():
        try:
            resorts[key] = recast(name, fetch(host), now)
        except Exception as error:
            print(f"{name}: {error}")
    if not resorts:
        return 1
    with open(out_path, "w") as handle:
        json.dump({"updated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "resorts": resorts}, handle, separators=(",", ":"))
    for key, feed in resorts.items():
        lifts = sum(len(area["Lifts"]) for area in feed["MountainAreas"])
        print(f"{feed['Name']}: {lifts} lifts")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
