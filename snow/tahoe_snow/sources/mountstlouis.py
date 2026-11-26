"""Mount St. Louis Moonstone's lifts and slopes, and its base depth, from its mountain status page
(mountstlouis.com/status).

The page is built on the server. Its slopes and its lifts are each given twice, for day skiing and for night
skiing, as a table for each of the resort's two hills (Mount St. Louis and Moonstone), each hill a mountain area
here holding its lifts and its slopes. A row is a name and its status in a word, and a slope's row ends with its
difficulty symbol (easy, more difficult, most difficult, or freestyle terrain, which has no difficulty). By the
page's own key a groomed slope carries a snowplough beside that symbol and a slope closed for a race a chequered
flag; the page was read before the season, with neither on any slope, so any other symbol in a row fails, and
grooming is said of the slopes only when at least one carries the snowplough. A status other than open or closed
is carried in the page's words. The page's own counts ("0/37 Open Slopes", "0/12 Open Lifts") say which tables are
read: the day's when the counts agree with them, the night's when they agree with those instead, and a page whose
counts agree with neither is refused, so a change in its shape fails instead of showing wrong numbers.
The terrain parks are a list of their own, counted apart from the slopes by the page, and are left out.

The page gives a base depth, whether natural snow fell in the last 24 hours, and the surface, each typed by hand
and none dated; before the season the base depth is empty. **The resort is in Ontario and a depth is read only
when it is given in centimetres ("60 cm", or a range "60-90 cm"), which are converted to inches here (divided by
2.54, to one decimal)**; a snowfall of "no" is none, and one in any other words is left out. A snow report that
cannot be read costs only the snow report, not the lifts. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.mountstlouis.com/status/"
NAME = "Mount St. Louis Moonstone"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# The difficulty symbols' classes, in the words the app's difficulty symbols are keyed on; freestyle has none.
LEVELS = {"easy": "Green", "more-difficult": "Blue", "most-difficult": "Black", "freestyleterrain": ""}
GROOMED_MARK, RACE_MARK = "fa-snowplow", "fa-flag-checkered"
PANE = r"<div id=\"{name}\" class=\"tab-pane[^\"]*\">(.*?)(?=<div id=\"[\w-]+\" class=\"(?:tab-pane|collapse)|$)"
HILL = re.compile(r"<h4>(.*?)</h4>\s*<table[^>]*class\s*=\s*\"availability_list table\"[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
SYMBOL = re.compile(r"<i class=\"([^\"]*)\"[^>]*>")
COUNT = r"</i>\s*(\d+)/(\d+) Open {kind}\s*</a>"
LINE = r"<p><strong>{label}:\s*</strong>(.*?)</p>"
DEPTH = re.compile(r"(\d+(?:\.\d+)?)(?:\s*(?:-|–|to)\s*(\d+(?:\.\d+)?))?\s*cm\.?", re.I)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def symbols(name: str, cell: str) -> tuple:
    """A slope's difficulty and whether it is groomed, from the symbols in the last cell of its row."""
    level, groomed = None, False
    for classes in SYMBOL.findall(cell):
        marks = classes.split()
        if GROOMED_MARK in marks:
            groomed = True
        elif RACE_MARK in marks:
            continue
        elif marks[:1] == ["difficulty"] and len(marks) > 1 and marks[1] in LEVELS and level is None:
            level = LEVELS[marks[1]]
        else:
            raise ValueError(f"{name} has a symbol the reader does not know: {classes!r}")
    if level is None:
        raise ValueError(f"{name} has no difficulty symbol")
    return level, groomed


def hills(page: str, pane: str, kind: str) -> dict:
    """Each hill's rows in the pane named ``pane`` (its slopes or its lifts), by the hill's name."""
    found = re.search(PANE.format(name=pane), page, re.S)
    if not found:
        raise ValueError(f"the {kind.lower()} of the day or of the night were not found")
    out = {}
    for heading, table in HILL.findall(found.group(1)):
        hill = words(heading).removesuffix(kind).strip()
        rows = [CELL.findall(row) for row in ROW.findall(table)]
        width = 3 if kind == "Slopes" else 2
        if not hill or hill in out or len(rows) < 2 or any(len(cells) != width for cells in rows):
            raise ValueError(f"a table of {kind.lower()} has no hill, a hill twice, or is not rows of {width} cells")
        if [words(cell) for cell in rows[0]][1:] != ["Status", "Difficulty"][:width - 1]:
            raise ValueError(f"a table of {kind.lower()} does not begin with its headings")
        out[hill] = [row(kind, cells) for cells in rows[1:]]
    if not out or len(out) != found.group(1).count("availability_list"):
        raise ValueError(f"a table of {kind.lower()} could not be read")
    return out


def row(kind: str, cells: list) -> dict:
    """A lift or a slope with its status in the page's words."""
    name, said = words(cells[0]), words(cells[1]).capitalize()
    if not name or not said:
        raise ValueError(f"{name or 'a row'} has no name or no status")
    out = {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": None}
    if kind == "Slopes":
        out["Difficulty"], out["Grooming"] = symbols(name, cells[2])
    return out


def grooming(areas: list) -> list:
    """The areas with each slope's grooming said as the app reads it, or not at all when no slope is marked."""
    slopes = [slope for area in areas for slope in area["Trails"]]
    marked = any(slope["Grooming"] for slope in slopes)
    for slope in slopes:
        # With no snowplough on any slope the page may not be marking grooming at all, so none is claimed.
        if marked:
            slope["Grooming"] = "Yes" if slope["Grooming"] else "No"
        else:
            del slope["Grooming"]
    return areas


def counted(page: str, kind: str) -> dict:
    """The day's tables of ``kind``, or the night's when it is those the page's own count of the open agrees with."""
    count = re.search(COUNT.format(kind=kind), page)
    if not count:
        raise ValueError(f"the page's count of open {kind.lower()} was not found")
    is_open, total = (int(figure) for figure in count.groups())
    read = []
    for pane in ("day", "night"):
        tables = hills(page, f"{pane}-{'runs' if kind == 'Slopes' else 'lifts'}", kind)
        rows = [row for rows in tables.values() for row in rows]
        read.append((sum(row["StatusEnglish"] == "open" for row in rows), len(rows)))
        if read[-1] == (is_open, total):
            return tables
    raise ValueError(f"the page counts {is_open} of {total} {kind.lower()} open but {read[0][0]} of {read[0][1]} "
                     f"were read by day and {read[1][0]} of {read[1][1]} by night")


def inches(centimetres: str) -> float:
    return round(float(centimetres) / CM_PER_INCH, 1)


def said(page: str, label: str) -> str:
    found = re.search(LINE.format(label=re.escape(label)), page, re.S)
    if not found:
        raise ValueError(f"the page's line for {label!r} was not found")
    return words(found.group(1))


def snow_report(page: str) -> dict:
    """The page's base depth in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    depth, fresh = DEPTH.fullmatch(said(page, "Base Depth")), said(page, "Natural Snow in Last 24 Hrs")
    if not depth:
        raise ValueError("the base depth is not given, or not in centimetres")
    low, high = depth.group(1), depth.group(2)
    area = {"Name": "Mountain", "BaseIn": None if high else inches(low)}
    if high:
        area.update({"BaseMinIn": inches(low), "BaseMaxIn": inches(high)})
    snowfall = DEPTH.fullmatch(fresh)
    if fresh.lower() in ("no", "none", "0"):
        area["Last24HoursIn"] = 0
    elif snowfall and not snowfall.group(2):
        area["Last24HoursIn"] = inches(snowfall.group(1))
    else:
        area["Last24HoursIn"] = None
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": said(page, "Conditions") or None,
            "SeasonTotalIn": None, "BaseArea": area, "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    slopes, lifts = counted(page, "Slopes"), counted(page, "Lifts")
    if list(slopes) != list(lifts):
        raise ValueError(f"the hills with slopes are not the hills with lifts: {list(slopes)} and {list(lifts)}")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": grooming([{"Name": hill, "Lifts": lifts[hill], "Trails": slopes[hill]}
                                       for hill in slopes])}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
