"""Grand Targhee's lifts and trails, and its snow report, from its own pages
(grandtarghee.com/the-mountain/cams-conditions/lifts-trails-report and .../mountain-report).

Both pages are built on the server and cannot be read by a page on another site, so the collector reads them. The
lifts-and-trails page lists each lift with the trails it serves beneath it, so each lift is a mountain area with
its trails. The page's own count of lifts is checked against what is read, so a redesign fails instead of showing
wrong numbers; its count of trails is of named runs and is lower than the list it gives, so the list is only
required to hold at least that many. The snow report is the mountain-report page's one set of figures for the whole
mountain (base depth, the last 24 hours, the season so far) and the time of its snapshot, in the shape of the Ikon
feed's snow report. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URLS = {"lifts": "https://www.grandtarghee.com/the-mountain/cams-conditions/lifts-trails-report",
        "report": "https://www.grandtarghee.com/the-mountain/cams-conditions/mountain-report"}
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The page's trail levels, in the words the page's difficulty symbols are keyed on; terrain parks have none.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "expert": "Double black",
          "terrain-park": ""}
ROW = re.compile(r'<article\s+data-history-node-id="\d+" class="node node--type-(lift|trail) ')
STATUS = re.compile(r'class="cell f-icon status [\w-]+" title="([^"]+)"')
# The overview's "Lifts 2 /6" and "Trails 14 /95".
COUNT = r"{}\s*</[^>]+>\s*(?:<[^>]+>\s*)*\d+\s*(?:<[^>]+>\s*)*/\s*(?:<[^>]+>\s*)*(\d+)"
# The mountain report's figures: a label, then inches.
STAT = r"<dt>\s*{}\s*</dt>\s*<dd>\s*(\d+(?:\.\d+)?)\s*(?:\"|&quot;)"


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, row: str, difficulty: str | None) -> dict:
    status = STATUS.search(row)
    if not name or not status:
        raise ValueError(f"a lift or trail has no name or no status: {name!r}")
    words = html.unescape(status.group(1)).strip().capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def trail_row(row: str) -> dict:
    cell = re.search(r'<div class="cell title">(.*?)</div>\s*</div>', row, re.S)
    level = re.search(r'class="f-icon level ([\w-]+)"[^>]*>.*?</div>(.*)', cell.group(1), re.S) if cell else None
    if level:
        if level.group(1) not in LEVELS:
            raise ValueError(f"a trail has a level the reader does not know: {level.group(1)}")
        name, difficulty = text_of(level.group(2)), LEVELS[level.group(1)]
    else:
        # A trail the page gives no level.
        name, difficulty = text_of(cell.group(1)) if cell else "", ""
    out = status_row(name, row, difficulty)
    detail = re.search(r'<div class="cell t-micetype detail">(.*?)</div>', row, re.S)
    out["Grooming"] = "Yes" if detail and "groomed" in text_of(detail.group(1)).lower() else "No"
    return out


def areas(page: str) -> list[dict]:
    """One area per lift, holding the lift and the trails listed beneath it."""
    out = []
    pieces = ROW.split(page)
    for kind, row in zip(pieces[1::2], pieces[2::2]):
        if kind == "lift":
            name = re.search(r"<button[^>]*>(.*?)</button>", row, re.S)
            lift = status_row(text_of(name.group(1)) if name else "", row, None)
            out.append({"Name": lift["Name"], "Lifts": [lift], "Trails": []})
        elif out:
            trail = trail_row(row)
            # The uphill route is not a run; the other mountains' lists leave theirs out too.
            if trail["Name"] != "Uphill Access":
                out[-1]["Trails"].append(trail)
        else:
            raise ValueError("a trail is listed before any lift")
    return out


def counted(page: str, what: str) -> int:
    found = re.search(COUNT.format(what), page)
    if not found:
        raise ValueError(f"the page's count of {what.lower()} was not found")
    return int(found.group(1))


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def snow_report(page: str) -> dict | None:
    """The mountain report's figures in the shape of the Ikon feed's SnowReport, for the whole mountain. None
    when the page has no snapshot time."""
    posted = re.search(r'Current snapshot:\s*</span>\s*<time datetime="([^"]+)"', page)
    if not posted:
        return None

    def stat(label: str):
        found = re.search(STAT.format(label), page)
        return number(found.group(1)) if found else None

    season = re.search(r"(\d+(?:\.\d+)?)\s*(?:\"|&quot;)\s*season total", page)
    sky = re.search(r'<p class="mountain-report-hero__sky">(.*?)</p>', page, re.S)
    update = re.search(r'<h2 id="mountain-report-conditions-heading">.*?</h2>(.*?)</section>', page, re.S)
    return {"LastUpdate": datetime.fromisoformat(posted.group(1)).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": None, "Weather": text_of(sky.group(1)) if sky else None,
            "SeasonTotalIn": number(season.group(1)) if season else None,
            "BaseArea": {"Name": "Mountain", "BaseIn": stat("Base depth"), "Last24HoursIn": stat("24hr snow"),
                         "OvernightIn": stat("Overnight")},
            "Report": update.group(1).strip() if update else None}


def parse(pages: dict, now: datetime) -> dict:
    found = areas(pages["lifts"])
    lifts = sum(len(area["Lifts"]) for area in found)
    trails = sum(len(area["Trails"]) for area in found)
    if not lifts or lifts != counted(pages["lifts"], "Lifts"):
        raise ValueError(f"the page counts {counted(pages['lifts'], 'Lifts')} lifts but {lifts} were read")
    if trails < counted(pages["lifts"], "Trails"):
        raise ValueError(f"the page counts {counted(pages['lifts'], 'Trails')} trails but only {trails} were read")
    feed = {"Name": "Grand Targhee", "LastUpdate": now.strftime(STAMP), "MountainAreas": found}
    try:
        snow = snow_report(pages["report"])
    except (ValueError, KeyError) as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Grand Targhee: snow report: {error}")
        snow = None
    if snow:
        feed["SnowReport"] = snow
    return feed
