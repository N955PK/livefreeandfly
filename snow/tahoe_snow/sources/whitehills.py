"""White Hills' lifts and trails, and its snow report, from its snow report page (whitehillsresort.com/snow-report).

The page is built on the server by a site builder that writes, for each lift and each trail, a block for every
status it could have (open, on hold, closed) and hides all but the one that holds, with the same word under each.
So a lift's or trail's status is the mark of its one block that is not hidden, in the words of the page's own key
(Open, On Hold, Closed); a box with no block showing, or two, or a mark the reader does not know, fails, and so
does a word under the mark that is one of the key's but not the mark's. A trail's heading carries its difficulty
as symbols: a circle, a square, a diamond, or two diamonds for a double black. Names are written in small letters
and shown in capitals by the page's styling; here each word is given a capital. Every lift and trail box in the
page is read, so a change in the page's shape fails instead of showing wrong numbers. The lifts are one mountain
area and the trails another, since the page does not say which lift serves which trail. The page says nothing of
grooming.

The snow report gives the snow of the last 24 hours, the season's snowfall and the snow depth, none dated;
outside the season all three are empty. **The resort is in Newfoundland and the page reports centimetres; they are
converted to inches here (divided by 2.54, to one decimal).** A snow report that cannot be read costs only the
snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.whitehillsresort.com/snow-report"
NAME = "White Hills"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
HIDDEN = "w-condition-invisible"
# The marks of a status block, in the words of the page's key.
STATUSES = {"status-open": "Open", "status-onhold": "On hold", "status-closed": "Closed"}
# A trail's symbols, in the words the app's difficulty symbols are keyed on.
LEVELS = {("circle",): "Green", ("square",): "Blue", ("diamond",): "Black", ("diamond", "diamond"): "Double black"}
# The snow report's figures, by the names the Ikon feed gives them (the app reads those).
SNOWFALL = {"24 Hour Snow": "Last24HoursIn", "Snowfall Season to date": "SeasonTotalIn", "Snow depth": "BaseIn"}
BOX = re.compile(r"<div class=\"(lift|trail)-box\">(.*?)(?=<div class=\"(?:lift|trail)-box\">|<section|</section>|$)",
                 re.S)
NAMED = re.compile(r"<h4 [^>]*class=\"h4-heading[^\"]*\"[^>]*>(.*?)</h4>", re.S)
BLOCK = re.compile(r"<div class=\"w-layout-vflex status-block( w-condition-invisible)?\">\s*<div class=\"status-icon\">"
                   r"\s*<img [^>]*class=\"([\w-]+)[^\"]*\"\s*/?>\s*</div>\s*<div class=\"status-text\">\s*"
                   r"<h4[^>]*>(.*?)</h4>", re.S)
SYMBOL = re.compile(r"<div class=\"stats-icon (\w+)[^\"]*\">")
FIGURE = re.compile(r"<div class=\"snow-status w-richtext\">(.*?)</div>.*?<h4 class=\"h4-heading center\">(.*?)</h4>",
                    re.S)
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*cm", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, joiners out, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).replace("‍", " ").split())


def titled(name: str) -> str:
    """A name the page writes in small letters, with a capital on each word as the page's styling shows it."""
    return " ".join(word[:1].upper() + word[1:] for word in name.split())


def status_row(kind: str, body: str) -> dict:
    """A lift or a trail with the status of its one block that is not hidden."""
    heading = NAMED.search(body)
    name = titled(words(heading.group(1))) if heading else ""
    blocks = BLOCK.findall(body)
    showing = [(mark, words(said)) for hidden, mark, said in blocks if not hidden]
    if not name or len(blocks) != body.count("\"w-layout-vflex status-block") or len(showing) != 1:
        raise ValueError(f"{name or 'a ' + kind} does not have one status showing, or a block could not be read")
    mark, said = showing[0]
    if mark not in STATUSES:
        raise ValueError(f"{name} has a status mark the reader does not know: {mark}")
    status = STATUSES[mark]
    if said.lower() != status.lower() and said.lower() in {known.lower() for known in STATUSES.values()}:
        raise ValueError(f"{name} is marked {status.lower()} but reads {said!r}")
    difficulty = None
    if kind == "trail":
        symbols = tuple(SYMBOL.findall(body[:heading.start()]))
        if symbols not in LEVELS:
            raise ValueError(f"{name} has difficulty symbols the reader does not know: {list(symbols)}")
        difficulty = LEVELS[symbols]
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def inches(centimetres: float) -> float:
    return round(centimetres / CM_PER_INCH, 1)


def snow_report(page: str) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    figures = {}
    for said, label in FIGURE.findall(page):
        label, said = words(label), words(said)
        if label not in SNOWFALL:
            continue
        found = CENTIMETRES.fullmatch(said)
        if not found or SNOWFALL[label] in figures:
            raise ValueError(f"the snow report's {label!r} reads {said!r}, not centimetres, or is given twice")
        figures[SNOWFALL[label]] = inches(float(found.group(1)))
    if "BaseIn" not in figures or "Last24HoursIn" not in figures:
        raise ValueError("the snow report has no snow depth or no 24 hour snowfall")
    season = figures.pop("SeasonTotalIn", None)
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": season,
            "BaseArea": {"Name": "Mountain", **figures}, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    rows = {"lift": [], "trail": []}
    for kind, body in BOX.findall(page):
        rows[kind].append(status_row(kind, body))
    for kind, found in rows.items():
        boxes = page.count(f"class=\"{kind}-box\"")
        if not found or len(found) != boxes or len({row["Name"] for row in found}) != len(found):
            raise ValueError(f"the page has {boxes} {kind} boxes but {len(found)} were read, or one twice")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": rows["lift"], "Trails": []},
                              {"Name": "Trails", "Lifts": [], "Trails": rows["trail"]}]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
