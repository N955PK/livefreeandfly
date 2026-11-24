"""Mont Blanc's lifts and trails (the Laurentians' Mont Blanc, skimontblanc.com), from the status table its
mountain info page frames in from GetTrail (app.gettrail.info), which the mountain's staff keep.

The table is built on the server and comes in French unless a browser asks for English, so the reader knows
both. It is a run of sectors, each a heading over its rows: the lifts (REMONTÉES MÉCANIQUES), the three mountains
(MONT BLANC, MONT FAUSTIN, MONT BLANC NORD) and the alpine touring routes. A lift's row is "Quad Faustin | Mont
Faustin", its name and its mountain; each mountain is a mountain area here, holding its lifts and its trails. A
mountain's rows are its trails, "12 - Cigale", and its lodges, which have no number and are left out, as the
touring routes are.

A row has two status symbols, one under the page's skiing column and one under its services column, and "Blank"
where a column does not apply. A trail's status is its symbol under skiing and a lift's is its symbol under
services, or the other where that one is blank. The symbol's title is the status, in the page's own key:
  Ouvert / Open -> Open                  Fermé / Closed -> Closed
  Attention ! -> Caution (open)          Piste glacée -> Icy (open)
  Faible visibilité -> Low visibility (open)
  Ouverture retardée -> Delayed          Maintenance -> Maintenance (closed)
and one the reader does not know fails. A trail's difficulty is the drawing before its name, known by its colour
and its outline (green circle, blue square, black diamond, two black diamonds; the two orange terrain park badges
have none), and one the reader does not know fails. The page gives no count of its lifts to
check against (its sector summaries count symbols, not rows), so the reader requires every row to read: a row
without a name, without its two symbols or without a mountain fails instead of showing wrong numbers.

The page gives no snow report: its only snow figure is a weather forecast's, in millimetres, and it is not read.
So nothing is converted here; if the page ever gives depths they will be centimetres, to be divided by 2.54 and
rounded to one decimal like the other Quebec mountains. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://app.gettrail.info/embed/3e435d5b-aa7a-4105-b3d2-8b20cfcc7531/tabletrails"
NAME = "Mont Blanc"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The status symbols' titles, French and English: the word the app shows and the English lower-case word it sorts by.
STATUSES = {"ouvert": ("Open", "open"), "open": ("Open", "open"),
            "fermé": ("Closed", "closed"), "closed": ("Closed", "closed"),
            "attention !": ("Caution", "open"), "caution": ("Caution", "open"),
            "piste glacée": ("Icy", "open"), "icy trail": ("Icy", "open"),
            "faible visibilité": ("Low visibility", "open"), "low visibility": ("Low visibility", "open"),
            "ouverture retardée": ("Delayed", "delayed"), "delayed opening": ("Delayed", "delayed"),
            "maintenance": ("Maintenance", "closed")}
BLANK = "blank"
# The sectors that are not mountains: the lifts, in both languages, and the touring routes, which are left out.
LIFT_SECTORS = ("remontées mécaniques", "lifts")
TOURING = ("randonnée alpine", "touring")
# The difficulty drawings by their colour and the start of their outline, in the words the app's difficulty symbols
# are keyed on; the two terrain park badges have none.
LEVELS = {("#36B649", "M22 12a10 10"): "Green", ("#1176BC", "M2 2h20v20H2z"): "Blue",
          ("#000", "m12 2 10 10-10 10L2 12z"): "Black", ("#000", "M15.75 2 22 12l-6.25 10L9.5 12Z"): "Double black",
          ("#F36522", "M7 7h10c2.77"): "", ("#36B649", "M54.1,35.7H17.9"): ""}
SECTOR = re.compile(r"<ui-disclosure\s[^>]*data-flux-accordion-item[^>]*>(.*?)(?=<ui-disclosure\s|\Z)", re.S)
HEADING = re.compile(r"<span class=\"[^\"]*widget-sector-text[^\"]*\">(.*?)</span>", re.S)
ROW = re.compile(r"<div data-flux-widget-trail>(.*?)(?=<div data-flux-widget-trail>|\Z)", re.S)
NAMED = re.compile(r"<span class=\"text-sm truncate[^\"]*\">(.*?)</span>", re.S)
SYMBOL = re.compile(r"<svg[^>]*\stitle=\"([^\"]*)\"\s+aria-label=\"")
DRAWING = re.compile(r"<svg[^>]*\sfill=\"(#[0-9A-Fa-f]+)\"[^>]*>(?:\s|<!--.*?-->)*<path[^>]*\sd=\"([^\"]*)\"", re.S)
NUMBERED = re.compile(r"\d+[A-Za-z]?\s*-\s*(\S.*)")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def status_row(name: str, row: str, lift: bool) -> dict:
    """One lift or trail: its status is its symbol under skiing, or for a lift under services, where it has one."""
    symbols = [html.unescape(title).strip().lower() for title in SYMBOL.findall(row)]
    said = [symbol for symbol in symbols if symbol != BLANK]
    if len(symbols) != 2 or not said or any(symbol not in STATUSES for symbol in said):
        raise ValueError(f"{name} has status symbols {symbols}, not two the reader knows")
    status, english = STATUSES[said[-1] if lift else said[0]]
    return {"Name": name, "Status": status, "StatusEnglish": english, "Difficulty": None}


def difficulty(name: str, row: str) -> str:
    """A trail's difficulty: the first drawing in its row, before its name."""
    drawing = DRAWING.search(row[:NAMED.search(row).start()])
    if drawing:
        for (colour, outline), level in LEVELS.items():
            if drawing.group(1).upper() == colour.upper() and drawing.group(2).startswith(outline):
                return level
    raise ValueError(f"{name} has a difficulty drawing the reader does not know")


def sectors(page: str) -> list:
    """Each sector's heading and its rows as (name, markup), in the page's order."""
    found = []
    for block in SECTOR.findall(page):
        heading = HEADING.search(block)
        if not heading or not words(heading.group(1)):
            raise ValueError("a sector has no heading")
        rows = []
        for row in ROW.findall(block):
            name = NAMED.search(row)
            if not name or not words(name.group(1)):
                raise ValueError(f"a row under {words(heading.group(1))} has no name")
            rows.append((words(name.group(1)), row))
        found.append((words(heading.group(1)), rows))
    return found


def parse(page: str, now: datetime) -> dict:
    areas, lifts = {}, []
    for heading, rows in sectors(page):
        if any(word in heading.lower() for word in TOURING):
            continue
        if heading.lower() in LIFT_SECTORS:
            for name, row in rows:
                lift, bar, mountain = name.partition("|")
                if not bar or not lift.strip() or not mountain.strip():
                    raise ValueError(f"the lift {name!r} is not a name, a bar and a mountain")
                lifts.append((mountain.strip(), status_row(lift.strip(), row, lift=True)))
            continue
        trails = []
        for name, row in rows:
            numbered = NUMBERED.fullmatch(name)
            if not numbered:
                # A lodge or a restaurant: no trail number.
                continue
            trail = status_row(numbered.group(1), row, lift=False)
            trail["Difficulty"] = difficulty(name, row)
            trails.append(trail)
        if not trails:
            raise ValueError(f"{heading} lists no trails")
        if heading.lower() in areas:
            raise ValueError(f"the page lists {heading} twice")
        areas[heading.lower()] = {"Name": heading.title(), "Lifts": [], "Trails": trails}
    if not lifts or not areas:
        raise ValueError("the page lists no lifts or no trails")
    for mountain, lift in lifts:
        if mountain.lower() not in areas:
            raise ValueError(f"{lift['Name']} is on {mountain}, which the page has no trails for")
        areas[mountain.lower()]["Lifts"].append(lift)
    return {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": list(areas.values())}
