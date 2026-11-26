"""Lifts, trails and snow reports of the mountains that each run their own website: New England's independents,
Jackson Hole and Grand Targhee in the Tetons, six of the Wasatch's resorts, Copper and Loveland in Colorado, the Mt. Shasta Ski Park and Mt. Ashland,
Big White, SilverStar and Sun Peaks in the Okanagan, and Cypress, Grouse, Mt. Seymour and Mount Washington on
British Columbia's coast, nine of Quebec's, five in the Canadian Rockies,
seven along the Powder Highway and in the East Kootenays, thirteen in Montana, Sun Valley, Oregon, New Mexico
and Alaska, and seven in Southwest Colorado (Aspen Snowmass's four from one site).

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

from tahoe_snow.sources import (alta, alyeska, arcticvalley, ashland, aspensnowmass, azsnowbowl, bachelor, bigsky,
                                bigwhite, blackmountain, bogusbasin, bolton, boynehighlands, boynemountain,
                                brettonwoods, brianhead, brighton, bristol, bromley, bromont, brundage, burke, caberfae,
                                camelback, canaanvalley, cannon, cooperspur, copper, cranmore, crystalmi, cypress,
                                discovery, dollar, eaglecrest, eldora, elkmountain, fernie, fortyninenorth, granitepeak,
                                grouse, holidayvalley, hoodmeadows, hoodoo, jacksonhole, jaypeak, kickinghorse,
                                kimberley, lakelouise, leecanyon, lemassif, lookoutpass, losttrail, loveland, lutsen,
                                madriverglen, magic, marmot, massanutten, monarch, montblanc, montsainteanne,
                                mountainhigh, mtspokane, mtwashington, nakiska, norquay, nubsnob, orford, owlshead,
                                pajarito, panorama, powderking, plattekill, powdermountain, purgatory, redmountain, redriver,
                                revelstoke, saddleback, saintsauveur, seymour, shastaskipark, showdown, silvermountain,
                                silverstar, sipapu, skibowl, skisantafe, smugglers, snowbasin, snowbird, snowriver,
                                stoneham, sundance, sunpeaks, sunshine, sunvalley, sutton, tamarack, taos, targhee,
                                telluride, terrypeak, timberline, timberlinewv, waterville, westmountain, whitecap,
                                whitefish, whitewater, willamettepass, windham, wintergreen, wisp)

TIMEOUT = 20
STALE_DAYS = 14
STAMP = "%Y-%m-%dT%H:%M:%SZ"
MODULES = {"jaypeak": jaypeak, "burke": burke, "smugglers": smugglers, "bolton": bolton,
           "madriverglen": madriverglen, "bromley": bromley, "magic": magic, "cannon": cannon,
           "brettonwoods": brettonwoods, "waterville": waterville, "cranmore": cranmore,
           "blackmountain": blackmountain, "saddleback": saddleback,
           "jacksonhole": jacksonhole, "targhee": targhee,
           "alta": alta, "snowbird": snowbird, "brighton": brighton, "snowbasin": snowbasin,
           "powdermountain": powdermountain, "sundance": sundance,
           "copper": copper, "loveland": loveland,
           "shastaskipark": shastaskipark, "ashland": ashland,
           "bigwhite": bigwhite, "silverstar": silverstar, "sunpeaks": sunpeaks,
           "cypress": cypress, "grouse": grouse, "seymour": seymour, "mtwashington": mtwashington,
           "montblanc": montblanc, "saintsauveur": saintsauveur, "bromont": bromont, "sutton": sutton, "orford": orford,
           "owlshead": owlshead, "stoneham": stoneham, "montsainteanne": montsainteanne, "lemassif": lemassif,
           "lakelouise": lakelouise, "sunshine": sunshine, "norquay": norquay, "nakiska": nakiska, "marmot": marmot,
           "revelstoke": revelstoke, "redmountain": redmountain, "whitewater": whitewater, "kickinghorse": kickinghorse,
           "panorama": panorama, "kimberley": kimberley, "fernie": fernie,
           # The third collector's regions. Sun Valley's page holds Dollar Mountain too, and is read once for each.
           "bigsky": bigsky, "sunvalley": sunvalley, "dollar": dollar,
           "hoodmeadows": hoodmeadows, "cooperspur": cooperspur, "willamettepass": willamettepass,
           "taos": taos, "redriver": redriver, "sipapu": sipapu, "skisantafe": skisantafe, "pajarito": pajarito,
           "alyeska": alyeska, "arcticvalley": arcticvalley,
           "telluride": telluride, "monarch": monarch, "purgatory": purgatory,
           # Hoodoo's page gives each lift's hours for the day, not a live status: a lift reads open inside them.
           "timberline": timberline, "skibowl": skibowl, "hoodoo": hoodoo, "bachelor": bachelor,
           # The later regions' first readers.
           "boynemountain": boynemountain, "boynehighlands": boynehighlands, "eldora": eldora,
           "brianhead": brianhead, "azsnowbowl": azsnowbowl, "leecanyon": leecanyon,
           "whitefish": whitefish, "bogusbasin": bogusbasin, "brundage": brundage, "tamarack": tamarack,
           "lutsen": lutsen, "mountainhigh": mountainhigh, "showdown": showdown,
           "lookoutpass": lookoutpass, "fortyninenorth": fortyninenorth, "mtspokane": mtspokane,
           "discovery": discovery,
           # Massanutten's statuses answer only a POST (see ``read``).
           "wisp": wisp, "wintergreen": wintergreen, "massanutten": massanutten, "holidayvalley": holidayvalley,
           "bristol": bristol, "nubsnob": nubsnob, "crystalmi": crystalmi,
           # Snowriver and Granite Peak are Lutsen's owner's and reuse its reader.
           "snowriver": snowriver, "granitepeak": granitepeak, "whitecap": whitecap, "caberfae": caberfae,
           "timberlinewv": timberlinewv, "canaanvalley": canaanvalley,
           # Camelback is refused while its page counts no lifts open but marks some open.
           "silvermountain": silvermountain, "losttrail": losttrail, "camelback": camelback, "windham": windham,
           "eaglecrest": eaglecrest, "terrypeak": terrypeak, "plattekill": plattekill, "westmountain": westmountain,
           "elkmountain": elkmountain, "powderking": powderking}
# Sites that report several mountains at once: ``parse`` gives {mountain key: feed}, leaving out any it cannot read.
GROUPS = {"aspensnowmass": aspensnowmass}
# The figures a mountain may give as a low and a high: "BaseIn" beside "BaseMinIn" and "BaseMaxIn", and so on.
RANGED = ("Base", "Last24Hours")


def fetch(url: str, method: str = "GET") -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"}, method=method)
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


def posted(feed: dict) -> bool:
    return any(area["Lifts"] for area in feed["MountainAreas"])


def read(module, now: datetime) -> dict:
    if hasattr(module, "URLS"):
        # A module's ``POST`` names the requests its site answers only as a POST with no body.
        post = getattr(module, "POST", ())
        return module.parse({name: fetch(url, "POST" if name in post else "GET")
                             for name, url in module.URLS.items()}, now)
    return module.parse(fetch(module.URL), now)


def main(out_path: str) -> int:
    now = datetime.now(timezone.utc)
    resorts = {}
    for key, module in MODULES.items():
        try:
            feed = settled(read(module, now), now)
        except Exception as error:
            print(f"{key}: {error}")
            continue
        # A mountain that has posted no lifts yet (the Ski Park's sheet is empty until it opens) is left out, which
        # the page reads as nothing posted, not as a mountain with no lifts.
        if not posted(feed):
            print(f"{key}: no lifts posted yet")
            continue
        resorts[key] = feed
    for name, module in GROUPS.items():
        try:
            feeds = read(module, now)
        except Exception as error:
            print(f"{name}: {error}")
            continue
        for key, feed in feeds.items():
            try:
                feed = settled(feed, now)
            except Exception as error:
                print(f"{key}: {error}")
                continue
            if not posted(feed):
                print(f"{key}: no lifts posted yet")
                continue
            resorts[key] = feed
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
