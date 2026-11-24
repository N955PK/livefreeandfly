"""Mont-Sainte-Anne's lifts and trails, and its snowfall, from the frame its conditions page loads
(mont-sainte-anne.com/refresh/refresh.php?lang=en, behind mont-sainte-anne.com/en/alpine-skiing-snow-conditions).

Resorts of the Canadian Rockies runs Mont-Sainte-Anne and Stoneham on one page design, so the reading is done by
``rcr_feed`` here and Stoneham's module calls it. The conditions page is empty until a hidden frame fills it: the
frame is a script of lines, each putting a piece of markup into one named element of the page. The reader takes the
pieces by their names.

The day's lifts are the rows of ``lifts-day-element``: a tick is open and a dash is closed, and anything else
fails. The trails are rows of a difficulty picture, a name and a status picture whose title is French even on the
English page: OUVERT is Open and FERMÉ (fermé) is Closed, and any other title fails. A mark in the grooming column
(the column headed DAMÉES, groomed) is carried as the trail's grooming. Mont-Sainte-Anne lists its trails by side of
the mountain (south, north, west), each a mountain area here. The page's own counts of lifts and trails, and of the
lifts it says are open, are checked against what is read, so a change in its shape fails instead of showing wrong
numbers.

The site gives no depth of snow: its "Base" is a word (Firm). It gives the snowfall of the last 24 hours, 48 hours
and 7 days and the season's total in centimetres, which are turned into inches here (divided by 2.54, to one
decimal), and the time it was last updated, in Eastern time. A snow report that cannot be read costs only the snow
report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://mont-sainte-anne.com/refresh/refresh.php?lang=en"
NAME = "Mont-Sainte-Anne"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
EASTERN_TIME = ZoneInfo("America/Toronto")
# The elements holding the day's trails, and the side of the mountain each is shown under.
TRAIL_AREAS = {"trails-day-element-msa": "South Side", "trails-north-day-element-msa": "North Side",
               "trails-west-day-element-msa": "West Side"}
# The titles of the trails' status pictures, which are French on both pages.
STATUSES = {"OUVERT": "Open", "FERMÉ": "Closed"}
# The difficulty pictures' names, in the words the app's difficulty symbols are keyed on. Quebec's "difficult" is
# the blue square.
LEVELS = {"easy": "Green", "green_easy": "Green", "difficult": "Blue", "blue_difficult": "Blue",
          "diamond": "Black", "d_diamond": "Double black"}
# The snowfall boxes' headings, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24h": "Last24HoursIn", "48h": "Last48HoursIn", "7 days": "Last7DaysIn", "Season": "SeasonTotalIn"}
PIECE = re.compile(r"getElementById\('([^']+)'\)\.innerHTML=\s*'((?:[^'\\]|\\.)*)';")
ESCAPED = re.compile(r"\\(.)", re.S)
LIFT = re.compile(r"<div class=\"lift-column-row\">\s*<div class=\"lift-name\">(.*?)</div>\s*"
                  r"<div class=\"lift-open\">(.*?)</div>", re.S)
TRAIL_ROW = re.compile(r"<div class=\"trail-column-row trail-column-row-cursor\">(.*?)"
                       r"(?=<div class=\"trail-column-row|\Z)", re.S)
TRAIL_CELL = r"<div class=\"{name}\">(.*?)</div>"
PICTURE = re.compile(r"<img[^>]*\ssrc=\"[^\"]*/([^\"/]+)\.(?:svg|png)\"")
TITLE = re.compile(r"<img[^>]*\stitle=\"([^\"]*)\"")
TAG = re.compile(r"<[^>]+>")
COUNTED = {"lifts": re.compile(r"Lifts(?: Operating)? (\d+) / (\d+)"),
           "trails": re.compile(r"Trails open (\d+) / (\d+)")}
FIGURE = re.compile(r"<div class=\"snowreport-snowfall-box-title-element\">\s*([^<]*?)\s*</div>\s*"
                    r"<div class=\"snowreport-snowfall-box-value-element\">\s*([^<]*?)\s*"
                    r"<div class=\"snowreport-snowfall-box-units-element\">\s*([^<]*?)\s*</div>")
SURFACE = re.compile(r"<div class=\"snowreport-column-label[^\"]*\">Surface</div>\s*"
                     r"<div class=\"snowreport-column-value[^\"]*\">(.*?)</div>", re.S)
UPDATED = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{1,2})[:h](\d{2}) ([ap]m)")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def inches(centimetres: float) -> float:
    return round(centimetres / 2.54, 1)


def pieces(page: str) -> dict:
    """The markup the frame puts into each named element of the conditions page; the first is kept where the frame
    fills an element twice."""
    found = {}
    for name, markup in PIECE.findall(page):
        found.setdefault(name, ESCAPED.sub(r"\1", markup))
    if not found:
        raise ValueError("the frame fills no element of the conditions page")
    return found


def piece(found: dict, name: str) -> str:
    if name not in found:
        raise ValueError(f"the frame does not fill {name}")
    return found[name]


def lift_rows(markup: str) -> list:
    """The day's lifts: a tick is open, a dash is closed."""
    lifts = []
    for name, mark in LIFT.findall(markup):
        name = words(name)
        if "icon-check" in mark and "largeminus" not in mark:
            status = "Open"
        elif "largeminus" in mark and "icon-check" not in mark:
            status = "Closed"
        else:
            raise ValueError(f"{name or 'a lift'} has a status mark the reader does not know: {mark!r}")
        if not name:
            raise ValueError("a lift has no name")
        lifts.append({"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None})
    return lifts


def cell(row: str, name: str, trail: str) -> str:
    found = re.search(TRAIL_CELL.format(name=name), row, re.S)
    if not found:
        raise ValueError(f"{trail} has no {name}")
    return found.group(1)


def trail_rows(markup: str) -> list:
    """The trails of one element: a difficulty picture, a name, a status picture and a grooming mark each."""
    trails = []
    for row in TRAIL_ROW.findall(markup):
        named = re.search(r"<div class=\"trail-name(?:-list)?\">(.*?)</div>", row, re.S)
        name = words(named.group(1)) if named else ""
        if not name:
            raise ValueError("a trail has no name")
        levels = [level.lower() for level in PICTURE.findall(cell(row, "trail-diff", name))]
        if len(levels) != 1 or levels[0] not in LEVELS:
            raise ValueError(f"{name} has difficulty pictures {levels}, not one the reader knows")
        titles = [html.unescape(title).strip().upper() for title in TITLE.findall(cell(row, "trail-open", name))]
        if len(titles) != 1 or titles[0] not in STATUSES:
            raise ValueError(f"{name} has status titles {titles}, not one the reader knows")
        status = STATUSES[titles[0]]
        trails.append({"Name": name, "Status": status, "StatusEnglish": status.lower(),
                       "Difficulty": LEVELS[levels[0]],
                       "Grooming": "Yes" if "gcircle" in cell(row, "trail-groom", name) else "No"})
    return trails


def counted(summary: str, kind: str) -> tuple:
    """The page's own count of its lifts or trails: how many are open, and how many there are."""
    found = COUNTED[kind].search(summary)
    if not found:
        raise ValueError(f"the page's count of {kind} was not found")
    return int(found.group(1)), int(found.group(2))


def updated(page: str) -> str:
    """When the conditions were last updated, in UTC: "2026-11-11 9:38 am" on one site, "2026-04-07 06h51 am" on
    the other, in Eastern time."""
    found = UPDATED.search(page)
    if not found:
        raise ValueError("the conditions do not say when they were updated")
    year, month, day, hour, minute, half = found.groups()
    try:
        at = datetime.strptime(f"{year} {month} {day} {hour}:{minute} {half}", "%Y %m %d %I:%M %p")
    except ValueError as error:
        raise ValueError(f"the conditions' date could not be read: {error}") from error
    return at.replace(tzinfo=EASTERN_TIME).astimezone(timezone.utc).strftime(STAMP)


def snow_report(found: dict, page: str) -> dict:
    """The frame's snowfall in the shape of the Ikon feed's SnowReport, centimetres turned into inches. There is no
    depth of snow to give."""
    figures = {}
    for heading, said, unit in FIGURE.findall(piece(found, "weatherSnow")):
        if heading not in SNOWFALL:
            continue
        if unit != "cm" or not re.fullmatch(r"\d+(?:\.\d+)?", said) or SNOWFALL[heading] in figures:
            raise ValueError(f"the snowfall's {heading} reads {said!r} {unit!r}, not centimetres given once")
        figures[SNOWFALL[heading]] = inches(float(said))
    if "Last24HoursIn" not in figures:
        raise ValueError("the snowfall has no 24 hour figure")
    season = figures.pop("SeasonTotalIn", None)
    surface = SURFACE.search(piece(found, "conditions-day-element"))
    return {"LastUpdate": updated(page), "Resortwide": True,
            "BaseConditions": (words(surface.group(1)) or None) if surface else None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def rcr_feed(page: str, now: datetime, name: str, trail_areas: dict) -> dict:
    """The feed of one of the two mountains: its lifts, and the trails of each element named in ``trail_areas``
    under the area's name given there."""
    found = pieces(page)
    lifts = lift_rows(piece(found, "lifts-day-element"))
    areas = [{"Name": area, "Lifts": [], "Trails": trail_rows(piece(found, element))}
             for element, area in trail_areas.items()]
    trails = sum(len(area["Trails"]) for area in areas)
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    summary = words(piece(found, "conditions-day-element"))
    turning, listed = counted(summary, "lifts")
    if listed != len(lifts):
        raise ValueError(f"the page counts {listed} lifts but {len(lifts)} were read")
    if turning != sum(lift["StatusEnglish"] == "open" for lift in lifts):
        raise ValueError(f"the page counts {turning} lifts open but the list of lifts does not")
    if counted(summary, "trails")[1] != trails:
        raise ValueError(f"the page counts {counted(summary, 'trails')[1]} trails but {trails} were read")
    feed = {"Name": name, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": name, "Lifts": lifts, "Trails": []},
                              *(area for area in areas if area["Trails"])]}
    try:
        feed["SnowReport"] = snow_report(found, page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{name}: snow report: {error}")
    return feed


def parse(page: str, now: datetime) -> dict:
    return rcr_feed(page, now, NAME, TRAIL_AREAS)
