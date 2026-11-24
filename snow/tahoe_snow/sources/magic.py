"""Magic Mountain's (Vermont) lifts and trails, and its snowfall, from its snow report page
(magicmtn.com/snow-report).

The page is built on the server from the site's own collections (Lift Status, a Trail Status for each difficulty,
and Snow Report), and carries the records it drew its tables from as JSON in its own script element
(wix-warmup-data), so those are read and not the markup. A table shows twelve rows at a time, so the longer trail
lists take a second read of the page, at its tables' second pages; the two are put together and each collection's
own count of its records is checked against what was read, so a change in the page fails instead of dropping runs.
A lift or trail is open where its Open column holds a check mark and closed where it is empty; any other word
there is carried as the page gives it. A trail is groomed where its Grooming column holds a check mark. The page
lists the trails by difficulty, not by part of the mountain, so each difficulty is a mountain area. A lift's name
ends with its length in feet, which is left off. The snow report gives snowfall only (24 and 48 hours, the week
and the season) with the resort's own words and the time it was posted; the site gives no base depth, so there is
none, not a zero. Standard library only.
"""
import json
import re
from datetime import datetime, timezone

PAGE = "https://www.magicmtn.com/snow-report"
# The second page of each of the three trail tables that run past twelve rows, by the names the page gives them.
URLS = {"status": PAGE, "more": PAGE + "?comp-m2w9xtjt_page=2&comp-m2w9zaod_page=2&comp-m2wa2hzs_page=2"}
WARMUP = re.compile(r'<script type="application/json" id="wix-warmup-data">(.*?)</script>', re.S)
LIFTS = "Lift Status"
# The site's trail collections in the page's order: the page's heading for each, and its difficulty in the words
# the page's difficulty symbols are keyed on.
TRAILS = {"Green Trail Status": ("Easiest", "Green"), "Blue Trail Status": ("More Difficult", "Blue"),
          "Black Trail Status": ("Most Difficult", "Black"), "Double Black Trail Status": ("Experts Only", "Double black")}
SNOW = "Snow Report"
# The snow report's figures, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"24HrTotal": "Last24HoursIn", "48HrTotal": "Last48HoursIn", "week": "Last7DaysIn"}
CHECKS = ("✓", "✔")
LENGTH = re.compile(r"\s+[\d,]+\s*'$")
FIGURE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:"|”|in\.?|inches)?')


def collections(page: str) -> tuple:
    """One read of the page: its records by the collection's name, in the page's order, and each collection's own
    count of its records."""
    data = WARMUP.search(page)
    if not data:
        raise ValueError("the page's records were not found")
    binding = json.loads(data.group(1)).get("appsWarmupData", {}).get("dataBinding")
    if not binding:
        raise ValueError("the page's records were not found")
    named = {key: schema.get("displayName") for key, schema in binding["schemas"].items()}
    stored = binding["dataStore"]["recordsByCollectionId"]
    records, totals = {}, {}
    for shown in binding["dataStore"]["recordInfosByDatasetId"].values():
        key = next((key for key, rows in stored.items() if shown["itemIds"] and shown["itemIds"][0] in rows), None)
        if key is None:
            continue
        name = named.get(key)
        records.setdefault(name, {}).update({item: stored[key][item] for item in shown["itemIds"]})
        totals[name] = shown["datasetSize"]["total"]
    return records, totals


def status_row(name: str, mark: str | None, difficulty: str | None) -> dict:
    mark = (mark or "").strip()
    status = "Open" if any(check in mark for check in CHECKS) else mark.capitalize() or "Closed"
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(record: dict, difficulty: str) -> dict:
    row = status_row(" ".join(record["title"].split()), record.get("open"), difficulty)
    row["Grooming"] = "Yes" if any(check in (record.get("grooming") or "") for check in CHECKS) else "No"
    return row


def inches(said) -> float | int | None:
    """A snowfall the report gives as 3 or 3"; None where it gives nothing."""
    said = str(said or "").strip()
    if not said:
        return None
    figure = FIGURE.fullmatch(said)
    if not figure:
        raise ValueError(f"a snow figure does not read as a number: {said}")
    value = float(figure.group(1))
    return int(value) if value.is_integer() else value


def snow_report(record: dict) -> dict:
    """The snow report's figures in the shape of the Ikon feed's SnowReport: snowfall only, for the whole mountain.
    The report's words open with a standing explanation that ends at a ruled line; the day's report is what
    follows it."""
    stamp = record["_updatedDate"]
    posted = datetime.fromisoformat((stamp["$date"] if isinstance(stamp, dict) else stamp).replace("Z", "+00:00"))
    words = re.split(r"_{20,}", record.get("snowReport") or "")[-1].strip()
    return {"LastUpdate": posted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "SeasonTotalIn": inches(record.get("seasonTotal")),
            "BaseArea": {"Name": "Mountain", **{ikon: inches(record.get(field)) for field, ikon in SNOWFALL.items()}},
            "Report": words or None}


def parse(pages: dict, now: datetime) -> dict:
    """The two reads of the page put together: the lifts as one mountain area, then the trails of each difficulty."""
    records, totals = {}, {}
    for which in URLS:
        read, counted = collections(pages[which])
        for name, rows in read.items():
            records.setdefault(name, {}).update(rows)
        totals.update(counted)
    for name in (LIFTS, *TRAILS):
        if not records.get(name):
            raise ValueError(f"the page has no {name} records")
        # Each collection's own count is of all its records, so a table that pages differently fails.
        if len(records[name]) != totals[name]:
            raise ValueError(f"{name} counts {totals[name]} records but {len(records[name])} were read")
    lifts = [status_row(LENGTH.sub("", " ".join(lift["liftStatus"].split())), lift.get("open"), None)
             for lift in records[LIFTS].values()]
    areas = [{"Name": heading, "Lifts": [], "Trails": [trail_row(trail, level) for trail in records[name].values()]}
             for name, (heading, level) in TRAILS.items()]
    feed = {"Name": "Magic Mountain", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Magic Mountain", "Lifts": lifts, "Trails": []}, *areas]}
    try:
        report = next(iter(records.get(SNOW, {}).values()), None)
        snow = snow_report(report) if report else None
    except (ValueError, KeyError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Magic Mountain: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
