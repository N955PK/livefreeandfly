"""Mont Orford's lifts and trails, and its snowfall, from its ski conditions page
(montorford.com/en-ca/winter/conditions-ski, the English page).

The page is built on the server. Its lifts and its trails are each listed by part of the mountain (Mont-Orford,
Mont Giroux Nord, Mont Giroux Est, Mont Alfred-DesRochers), each a mountain area here holding its lifts and its
trails. A lift's or trail's status is the tooltip of its status symbol, in the words of the page's own key: "Open
not groomed" and "Open Groomed" are Open (the second carried as the trail's grooming), "Closed" is Closed, and
"Event" and "Progressive opening" are carried as the page says them; a tooltip the reader does not know fails. A
trail's difficulty is the tooltip of its level symbol (Quebec's Easy, Difficult, Very difficult and Extreme are the
green circle, the blue square, the black diamond and the double black). The page's own counts (chairlifts and magic
carpets; trails, snowparks and glades) are checked against what is read, so a change in its shape fails instead of
showing wrong numbers.

The site gives no depth of snow. It gives the snowfall of the last 24 hours, 48 hours and 7 days and the season's
total in centimetres, which are turned into inches here (divided by 2.54, to one decimal; the page's own inches are
rounded to the whole inch and are not used), a word for the surface, and the time of its update in Eastern time. A
snow report that cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://montorford.com/en-ca/winter/conditions-ski/"
NAME = "Mont Orford"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The status tooltips, in the words of the page's key: the status carried, and whether the trail is groomed.
STATUSES = {"open not groomed": ("Open", "No"), "open groomed": ("Open", "Yes"), "closed": ("Closed", "No"),
            "event": ("Event", "No"), "progressive opening": ("Progressive opening", "No")}
# The level tooltips, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easy": "Green", "difficult": "Blue", "very difficult": "Black", "extreme": "Double black"}
# The snowfall's keys, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"today": "Last24HoursIn", "twoDays": "Last48HoursIn", "sevenDays": "Last7DaysIn",
            "season": "SeasonTotalIn"}
LIFTS_START = "<section class=\"section conditions-tracks -chairlifts\">"
TRAILS_START = "<section class=\"section conditions-tracks -ski\">"
DOMAIN = "<li class=\"item domain\">"
TRACK = "<li class=\"item track\">"
DOMAIN_NAME = re.compile(r"<span class=\"text\">(.*?)</span>", re.S)
TRACK_NAME = re.compile(r"<span class=\"name\">(.*?)</span>", re.S)
TOOLTIP = re.compile(r"data-tippy=\"([^\"]*)\"\s+data-target=\"pages--conditions--tooltip\.(status|level|type)\"")
TAG = re.compile(r"<[^>]+>")
STATS = re.compile(r"<ul class=\"stats list\">(.*?)</ul>", re.S)
STAT = re.compile(r"<span class=\"total\">\s*/\s*(\d+)\s*</span>\s*</span>\s*"
                  r"<span class=\"label\">\s*([^<]*?)\s*</span>")
LIFT_KINDS, TRAIL_KINDS = ("Chairlifts", "Magic Carpets"), ("Trails", "Snowparks", "Glades")
SNOW = re.compile(r"<section class=\"section conditions-snow\"[^>]*>(.*?)</section>", re.S)
FIGURE = re.compile(r"<li class=\"item\" data-key=\"(\w+)\">\s*<ul class=\"values list\">\s*"
                    r"<li class=\"entry\" data-format=\"cm\">\s*<span class=\"value\">\s*([^<]*?)\s*</span>")
SURFACE = re.compile(r"data-key=\"surface\">\s*<div class=\"condition-title\">[^<]*</div>\s*"
                     r"<div class=\"condition-type\">(.*?)</div>", re.S)
UPDATED = re.compile(r"Update the (\d{4}-\d{2}-\d{2}) at (\d{2}:\d{2}:\d{2})")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float:
    return round(centimetres / 2.54, 1)


def part(page: str, start: str, end: str) -> str:
    """The page from one marker to the next."""
    at = page.find(start)
    if at < 0:
        raise ValueError(f"the page has no {start}")
    stop = page.find(end, at + len(start))
    if stop < 0:
        raise ValueError(f"the page has no {end} after {start}")
    return page[at:stop]


def track(markup: str, is_trail: bool) -> dict:
    """One lift or trail: its name, and the tooltips of its status and (a trail's) level symbols."""
    named = TRACK_NAME.search(markup)
    name = words(named.group(1)) if named else ""
    if not name:
        raise ValueError("a lift or trail has no name")
    tips = {}
    for said, kind in TOOLTIP.findall(markup):
        if kind in tips:
            raise ValueError(f"{name} has two {kind} symbols")
        tips[kind] = html.unescape(said).strip().lower()
    if tips.get("status") not in STATUSES:
        raise ValueError(f"{name} has the status {tips.get('status')!r}, not one the reader knows")
    status, groomed = STATUSES[tips["status"]]
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}
    if is_trail:
        if tips.get("level") not in LEVELS:
            raise ValueError(f"{name} has the level {tips.get('level')!r}, not one the reader knows")
        row["Difficulty"], row["Grooming"] = LEVELS[tips["level"]], groomed
    return row


def domains(section: str, is_trail: bool) -> dict:
    """The lifts or trails of each part of the mountain, by the part's name, in the page's order."""
    found = {}
    for block in section.split(DOMAIN)[1:]:
        named = DOMAIN_NAME.search(block)
        name = words(named.group(1)) if named else ""
        if not name or name in found:
            raise ValueError(f"a part of the mountain has no name or is listed twice: {name!r}")
        found[name] = [track(markup, is_trail) for markup in block.split(TRACK)[1:]]
    return found


def totals(page: str) -> dict:
    """The page's own counts of what it has, by its labels."""
    stats = STATS.search(page)
    if not stats:
        raise ValueError("the page's counts were not found")
    found = {label: int(total) for total, label in STAT.findall(stats.group(1))}
    if any(kind not in found for kind in LIFT_KINDS + TRAIL_KINDS):
        raise ValueError(f"the page's counts are {sorted(found)}, not the ones the reader knows")
    return found


def snow_report(page: str) -> dict:
    """The page's snowfall in the shape of the Ikon feed's SnowReport, centimetres turned into inches. There is no
    depth of snow to give."""
    block = SNOW.search(page)
    if not block:
        raise ValueError("the snowfall was not found")
    figures = {}
    for key, said in FIGURE.findall(block.group(1)):
        if key not in SNOWFALL or SNOWFALL[key] in figures or not re.fullmatch(r"\d+(?:\.\d+)?", said):
            raise ValueError(f"the snowfall's {key} reads {said!r}, not centimetres the reader knows, given once")
        figures[SNOWFALL[key]] = inches(float(said))
    if "Last24HoursIn" not in figures:
        raise ValueError("the snowfall has no 24 hour figure")
    updated = UPDATED.search(page)
    if not updated:
        raise ValueError("the page does not say when it was updated")
    try:
        at = datetime.strptime(" ".join(updated.groups()), "%Y-%m-%d %H:%M:%S")
    except ValueError as error:
        raise ValueError(f"the page's date could not be read: {error}") from error
    season = figures.pop("SeasonTotalIn", None)
    surface = SURFACE.search(block.group(1))
    return {"LastUpdate": at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc).strftime(STAMP),
            "Resortwide": True, "BaseConditions": (words(surface.group(1)) or None) if surface else None,
            "SeasonTotalIn": season, "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    # The page breaks its tags over lines: every run of spaces and line ends is read as one space.
    page = " ".join(page.split())
    trails = domains(part(page, TRAILS_START, LIFTS_START), True)
    lifts = domains(part(page, LIFTS_START, "</section>"), False)
    read_lifts, read_trails = sum(map(len, lifts.values())), sum(map(len, trails.values()))
    if not read_lifts or not read_trails:
        raise ValueError("the page lists no lifts or no trails")
    counted = totals(page)
    counted_lifts, counted_trails = (sum(counted[kind] for kind in kinds) for kinds in (LIFT_KINDS, TRAIL_KINDS))
    if counted_lifts != read_lifts:
        raise ValueError(f"the page counts {counted_lifts} lifts but {read_lifts} were read")
    if counted_trails != read_trails:
        raise ValueError(f"the page counts {counted_trails} trails but {read_trails} were read")
    names = list(lifts) + [name for name in trails if name not in lifts]
    feed = {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": name, "Lifts": lifts.get(name, []), "Trails": trails.get(name, [])}
                              for name in names]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
