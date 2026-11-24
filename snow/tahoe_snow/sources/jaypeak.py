"""Jay Peak's lifts and trails, and its snow report, from the report its snow-report page shows
(digital.jaypeakresort.com/conditions/snow-report/snow-report/, framed by jaypeakresort.com's snow report page).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page lists the
lifts in one section, then the trails in one section per kind (beginner, intermediate, advanced, terrain park and
the two kinds of glade), each lift and trail a card whose status is an icon with its word beside it. The page's own
count of lifts is checked against what is read, and every card must give a name and a status the page's legend
names, so a change in its shape fails instead of showing wrong numbers. The page's count of trails is not checked:
it counts fewer trails than it lists. The snow report (new snow, the season's total, base depth, surface and the
time it was posted, in Eastern time and without a year) is carried in the shape of the Ikon feed's snow report; a
figure the resort leaves empty stays empty. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://digital.jaypeakresort.com/conditions/snow-report/snow-report/"
NAME = "Jay Peak"
# The page's status icons, in the words its legend gives them.
STATUSES = {"open": "Open", "closed": "Closed", "hold": "On hold", "open-partial": "Partially open"}
# The page's kinds of trail, in the words the page's difficulty symbols are keyed on; a terrain park has none.
LEVELS = {"easiest": "Green", "more-difficult": "Blue", "most-difficult": "Black", "glades--more-difficult": "Blue",
          "glades--most-difficult": "Black", "terrain": ""}
SECTION = re.compile(r'<section class="SnowReport-section SnowReport-section--(lifts|trails)">(.*?)</section>', re.S)
SECTION_TITLE = re.compile(r'<h2 class="SnowReport-section-title">(.*?)(?:<span class="SnowReport-item-type">\s*'
                           r'<i class="pti pti-([a-z-]+)".*?)?</h2>', re.S)
CARD = re.compile(r'<article class="SnowReport-(?:Lift|Trail) SnowReport-feature">(.*?)</article>', re.S)
CARD_NAME = re.compile(r'<h3 class="SnowReport-feature-title">(.*?)</h3>', re.S)
CARD_STATUS = re.compile(r'SnowReport-item-status">\s*<i class="pti pti-([a-z-]+)"')
MEASURE = re.compile(r'<dl class="SnowReport-measure">\s*<dt>(.*?)</dt>\s*<dd>(.*?)</dd>\s*</dl>', re.S)
POSTED = re.compile(r'<dl class="update-info">\s*<dd>(.*?)</dd>', re.S)
# The report's snowfall labels, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"Last 24 Hours": "Last24HoursIn", "Last 48 Hours": "Last48HoursIn", "Last 7 Days": "Last7DaysIn"}
EASTERN = ZoneInfo("America/New_York")


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def card_row(card: str, difficulty: str | None) -> dict:
    name, mark = CARD_NAME.search(card), CARD_STATUS.search(card)
    if not name or not text_of(name.group(1)) or not mark:
        raise ValueError("a lift or trail on the page has no name or no status")
    if mark.group(1) not in STATUSES:
        raise ValueError(f"the page gives a status its legend does not name: {mark.group(1)}")
    row = status_row(text_of(name.group(1)), STATUSES[mark.group(1)], difficulty)
    if "pti-groomed" in card:
        row["Grooming"] = "Yes"
    return row


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def depth(said: str) -> tuple:
    """A depth in inches as the page writes it ('8 "', '12 - 24 "', or only the inch mark where the resort gives
    none), as the figure, its least and its most; a range has no single figure. Anything else is refused."""
    said = said.replace('"', "").replace("″", "").strip()
    if not said:
        return None, None, None
    spread = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", said)
    if spread:
        low, high = number(spread.group(1)), number(spread.group(2))
        return (low if low == high else None), low, high
    if not re.fullmatch(r"\d+(?:\.\d+)?", said):
        raise ValueError(f"a depth on the page does not read as inches: {said}")
    return number(said), None, None


def posted_at(said: str, now: datetime) -> str:
    """The time the report was posted ('Monday November 16 at 8:36 AM', Eastern, no year) in UTC. The year is this
    one, or last year when that date has not come yet; the weekday must agree, so a stale page is refused instead
    of being given the wrong year."""
    for year in (now.year, now.year - 1):
        try:
            posted = datetime.strptime(f"{year} {said}", "%Y %A %B %d at %I:%M %p").replace(tzinfo=EASTERN)
        except ValueError:
            raise ValueError(f"the snow report's date does not read: {said}") from None
        if posted <= now + timedelta(days=1) and posted.strftime("%A") == said.split()[0]:
            return posted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise ValueError(f"the snow report's date is not a day of this year or last: {said}")


def snow_report(measures: dict, posted: str | None) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport: one depth for the whole mountain."""
    if "Last 24 Hours" not in measures or "Base Depth" not in measures:
        raise ValueError("the snow report has no 24-hour figure or no base depth")
    base, least, most = depth(measures["Base Depth"])
    area = {"Name": "Mountain", "BaseIn": base, "BaseMinIn": least, "BaseMaxIn": most}
    area.update({ikon: depth(measures[label])[0] if label in measures else None for label, ikon in SNOWFALL.items()})
    return {"LastUpdate": posted, "Resortwide": True, "BaseConditions": measures.get("Primary Surface") or None,
            "SeasonTotalIn": depth(measures.get("Season Total", ""))[0], "BaseArea": area}


def parse(page: str, now: datetime) -> dict:
    lifts, areas = [], []
    for kind, body in SECTION.findall(page):
        if kind == "lifts":
            lifts += [card_row(card, None) for card in CARD.findall(body)]
            continue
        title = SECTION_TITLE.search(body)
        if not title or title.group(2) not in LEVELS:
            raise ValueError("a trail section on the page has no kind the page's legend names")
        areas.append({"Name": text_of(title.group(1)), "Lifts": [],
                      "Trails": [card_row(card, LEVELS[title.group(2)]) for card in CARD.findall(body)]})
    areas = [area for area in areas if area["Trails"]]
    if not lifts:
        raise ValueError("the page's lifts were not found")
    # Every card on the page is one read, so a change in its shape fails instead of dropping lifts or runs.
    listed, found = page.count('class="SnowReport-Trail '), sum(len(area["Trails"]) for area in areas)
    if found != listed or len(lifts) != page.count('class="SnowReport-Lift '):
        raise ValueError(f"the page lists {listed} trails but {found} were read, or its lifts were not all read")
    measures = {text_of(label): text_of(value) for label, value in MEASURE.findall(page)}
    counted = re.fullmatch(r"\d+ / (\d+)", measures.get("Open Lifts", ""))
    if not counted:
        raise ValueError("the page's count of lifts was not found")
    if int(counted.group(1)) != len(lifts):
        raise ValueError(f"the page counts {counted.group(1)} lifts but {len(lifts)} were read")
    posted = POSTED.search(page)
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas],
            "SnowReport": snow_report(measures, posted_at(text_of(posted.group(1)), now) if posted else None)}
