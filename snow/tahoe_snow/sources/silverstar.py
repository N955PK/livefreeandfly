"""SilverStar's lifts and trails, and its snow report, from the reports its own weather and conditions page reads
(skisilverstar.com/the-mountain/weather-conditions).

The page is drawn in the browser from three reports on the resort's own API (api.skisilverstar.com/api/v1/dor/drupal),
the same kind Snowbird's and Copper's pages read, so the reading of a row and a figure is Snowbird's: the lifts, the
trails and the snow reports. Each lift and trail names its part of the mountain (Comet, Putnam Creek, Attridge,
Silver Woods, the Silver Queen beginner area and so on), which is its mountain area here. The lift report includes
the carpets of the beginner areas and of Tube Town. The trail report also lists the cross-country, snowshoe and fat
bike trails, the summer's biking and hiking trails and the trails SilverStar marks as not for the status page; only
the alpine trails it shows are kept (its terrain parks are among them). A trail's difficulty or grooming the reader
does not know fails.

The snow report is written by the resort: one base depth, the new snow overnight, the snowfall of the last 24, 48
and 72 hours and 7 days, the season's total, the resort's own words, and when it was posted, in the resort's own
time. **The report gives centimetres; they are converted to inches here (divided by 2.54, to one decimal).** A
report in a unit other than centimetres or inches fails. It gives no surface. A snow report that cannot be read
costs only the snow report, not the lifts. Standard library only.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tahoe_snow.sources.snowbird import figure, listed, status_row

API = "https://api.skisilverstar.com/api/v1/dor/drupal"
URLS = {"lifts": f"{API}/lifts", "trails": f"{API}/trails", "snow": f"{API}/snow-reports"}
NAME = "SilverStar"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
RESORT_TIME = ZoneInfo("America/Vancouver")
SEASONS = {"winter", "all"}
SKIED = {"alpine_trail"}
# The report's difficulty words, in the words the page's difficulty symbols are keyed on. A terrain park has none.
LEVELS = {"easiest": "Green", "more_difficult": "Blue", "most_difficult": "Black", "extreme": "Double black",
          "N/A": ""}
GROOMED = {"groomed": "Yes", "not_groomed": "No"}
# The snow report's computed snowfall, by the names the Ikon feed gives them.
SNOWFALL = {"24_hour": "Last24HoursIn", "48_hour": "Last48HoursIn", "72_hour": "Last72HoursIn", "7_day": "Last7DaysIn"}
# How many of the report's unit make an inch.
PER_INCH = {"cm": 2.54, "in": 1}


def trail_row(trail: dict) -> dict:
    if trail["difficulty"] not in LEVELS:
        raise ValueError(f"{trail['name']} has a difficulty the reader does not know: {trail['difficulty']}")
    if trail["groom_status"] not in GROOMED:
        raise ValueError(f"{trail['name']} has a grooming the reader does not know: {trail['groom_status']}")
    row = status_row(trail["name"], trail["status"], LEVELS[trail["difficulty"]])
    row["Grooming"] = GROOMED[trail["groom_status"]]
    return row


def inches(value, per_inch: float) -> float | int | None:
    """A snow figure in inches, to one decimal, or None where the report gives none."""
    value = figure(value)
    if value is None or per_inch == 1:
        return value
    return round(value / per_inch, 1)


def snow_report(reports: list) -> dict | None:
    """The newest snow report in the shape of the Ikon feed's SnowReport: one set of figures for the whole mountain.
    None when there is no report."""
    if not reports:
        return None
    try:
        report = max(reports, key=lambda each: each["date"])
        if report["unit_of_measurement"] not in PER_INCH:
            raise ValueError(f"the snow report's units are {report['unit_of_measurement']}, not centimetres or inches")
        per_inch = PER_INCH[report["unit_of_measurement"]]
        posted = datetime.strptime(report["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=RESORT_TIME)
        computed = report["computed"]
        area = {"Name": "Mountain", "BaseIn": inches(report["base_depth"], per_inch),
                **{ikon: inches(computed[field], per_inch) for field, ikon in SNOWFALL.items()},
                "OvernightIn": inches(report["overnight_amount"], per_inch)}
        return {"LastUpdate": posted.astimezone(timezone.utc).strftime(STAMP), "Resortwide": True,
                "BaseConditions": None, "SeasonTotalIn": inches(computed["total"], per_inch), "BaseArea": area,
                "Report": report.get("report") or None}
    except (KeyError, TypeError) as error:
        raise ValueError(f"the snow report is not in the shape expected: {error!r}") from error


def parse(pages: dict, now: datetime) -> dict:
    lifts, trails = listed(pages["lifts"], "lift"), listed(pages["trails"], "trail")
    areas = {}
    try:
        for lift in lifts:
            if lift["season"] in SEASONS:
                area = areas.setdefault(lift["sector"]["name"], {"Name": lift["sector"]["name"], "Lifts": [], "Trails": []})
                area["Lifts"].append(status_row(lift["name"], lift["status"], None))
        for trail in trails:
            if trail["season"] in SEASONS and trail["type"] in SKIED and trail["include"] is True:
                area = areas.setdefault(trail["sector"]["name"], {"Name": trail["sector"]["name"], "Lifts": [], "Trails": []})
                area["Trails"].append(trail_row(trail))
    except (KeyError, TypeError) as error:
        raise ValueError(f"the report is not in the shape expected: {error!r}") from error
    if not any(area["Lifts"] for area in areas.values()):
        raise ValueError("the report lists no lifts")
    if not any(area["Trails"] for area in areas.values()):
        raise ValueError("the report lists no trails")
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
    try:
        snow = snow_report(listed(pages["snow"], "snow"))
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
