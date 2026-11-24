"""Smugglers' Notch's lifts and trails, and its snow report, from its winter report page
(smuggs.com/conditions/winter-report/).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page gives each
of the three mountains (Morse, Sterling, Madonna) a table of trails and a table of lifts, each row carrying its
status and a trail its difficulty as words. The uphill-access table is left out: the status is of the lift-served
mountain. The page's own counts of lifts and of trails (which leave out the terrain parks) are checked against what
is read, so a change in its shape fails instead of showing wrong numbers. The snow report (new snow, the season's
total, the depth of man-made and of natural snow, the surfaces, the resort's daily message and the time it was
posted, in Eastern time) is carried in the shape of the Ikon feed's snow report. The page says "new snowfall"
without a period; it is carried as the last 24 hours'. The base depth is the man-made snow's, the depth on the
trails that have snowmaking, and the natural snow's depth is carried beside it. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.smuggs.com/conditions/winter-report/"
NAME = "Smugglers' Notch"
# The page's difficulty words, in the words the page's difficulty symbols are keyed on; a terrain park has none.
LEVELS = {"easy": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black",
          "extreme-expert": "Double black", "terrain-park": ""}
TABLE = re.compile(r'<table class="facility-table">\s*<caption>(.*?)</caption>(.*?)</table>', re.S)
ROW = re.compile(r'<tr class="facility-report_item"[^>]*>(.*?)</tr>', re.S)
ROW_NAME = re.compile(r'<span class="facility-report_title">(.*?)</span>', re.S)
ROW_STATUS = re.compile(r'<span class="facility-report_icon --status --[a-z-]+" title="([^"]+)"')
ROW_LEVEL = re.compile(r"facility-report_icon --difficulty --([a-z-]+)")
ROW_CONDITION = re.compile(r'<td class="facility-report_condition">(.*?)</td>', re.S)
TOTAL = re.compile(r'<span class="report-totals_total">(\d+)</span>.*?</div>\s*<p[^>]*>([^<]+)</p>', re.S)
AMOUNT = re.compile(r'<span class="report-snow-data_amount">([^<]*)<.*?</div>\s*<p[^>]*>([^<]+)</p>', re.S)
LINE = re.compile(r"<p[^>]*>\s*(Natural Snow Depth|Man-Made Snow Depth|Primary|Secondary):([^<]*)</p>")
POSTED = re.compile(r"Report Last Updated:\s*</strong>\s*</p>\s*<p[^>]*>([^<]*)</p>")
MESSAGE = re.compile(r"Daily Message:\s*</strong>\s*</p>\s*<p[^>]*>(.*?)</p>", re.S)
EASTERN = ZoneInfo("America/New_York")


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = status.strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def table_row(row: str, trail: bool) -> dict:
    name, status, level = ROW_NAME.search(row), ROW_STATUS.search(row), ROW_LEVEL.search(row)
    if not name or not text_of(name.group(1)) or not status:
        raise ValueError("a lift or trail on the page has no name or no status")
    if not trail:
        return status_row(text_of(name.group(1)), html.unescape(status.group(1)), None)
    if not level or level.group(1) not in LEVELS:
        raise ValueError(f"the trail {text_of(name.group(1))} has no difficulty the page's legend names")
    found = status_row(text_of(name.group(1)), html.unescape(status.group(1)), LEVELS[level.group(1)])
    condition = ROW_CONDITION.search(row)
    if condition and "groomed" in condition.group(1).lower():
        found["Grooming"] = "Yes"
    return found


def inches(said: str) -> float | int:
    """A depth as the page writes it (0 with a double prime); anything that is not a number of inches is refused."""
    figure = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:″|"|in|inches)?', html.unescape(said).strip())
    if not figure:
        raise ValueError(f"a depth on the page does not read as inches: {said.strip()}")
    value = float(figure.group(1))
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain."""
    amounts = {text_of(label): inches(amount) for amount, label in AMOUNT.findall(page)}
    lines = {label: html.unescape(said).strip() for label, said in LINE.findall(page)}
    posted = POSTED.search(page)
    if "New Snowfall" not in amounts or "Man-Made Snow Depth" not in lines or "Natural Snow Depth" not in lines:
        raise ValueError("the snow report's new snowfall or its depths were not found")
    if not posted:
        raise ValueError("the snow report has no date")
    when = datetime.strptime(posted.group(1).strip(), "%m/%d/%Y %I:%M %p").replace(tzinfo=EASTERN)
    surface = ", ".join(dict.fromkeys(word for word in (lines.get("Primary"), lines.get("Secondary")) if word))
    message = MESSAGE.search(page)
    area = {"Name": "Mountain", "BaseIn": inches(lines["Man-Made Snow Depth"]),
            "NaturalIn": inches(lines["Natural Snow Depth"]), "Last24HoursIn": amounts["New Snowfall"]}
    return {"LastUpdate": when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "BaseConditions": surface or None, "SeasonTotalIn": amounts.get("Season Total"), "BaseArea": area,
            "Report": (text_of(message.group(1)) if message else "") or None}


def parse(page: str, now: datetime) -> dict:
    areas = {}
    for caption, body in TABLE.findall(page):
        mountain, _, kind = text_of(caption).rpartition(" ")
        if kind not in ("Lifts", "Trails") or not mountain:
            continue
        area = areas.setdefault(mountain, {"Name": mountain, "Lifts": [], "Trails": []})
        area[kind] += [table_row(row, kind == "Trails") for row in ROW.findall(body)]
    lifts = sum(len(area["Lifts"]) for area in areas.values())
    runs = sum(trail["Difficulty"] != "" for area in areas.values() for trail in area["Trails"])
    if not lifts:
        raise ValueError("the page's lift tables were not found")
    totals = {text_of(label): int(total) for total, label in TOTAL.findall(page)}
    if "Lifts Open" not in totals or "Trails Open" not in totals:
        raise ValueError("the page's counts of lifts and trails were not found")
    if totals["Lifts Open"] != lifts or totals["Trails Open"] != runs:
        raise ValueError(f"the page counts {totals['Lifts Open']} lifts and {totals['Trails Open']} trails but "
                         f"{lifts} and {runs} were read")
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "MountainAreas": list(areas.values()),
            "SnowReport": snow_report(page)}
