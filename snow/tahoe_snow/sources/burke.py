"""Burke Mountain's lifts and trails, and its snow report, from its weather and conditions page
(skiburke.com/the-mountain/weather-conditions).

The page is built on the server, so the browser cannot read it from another site; a scheduled job reads it and
writes one small file the page reads, in the shape of the Ikon feed the rest of the page uses. The page is a run of
tables: the lifts under "Lift Status", then the trails, the glades and the terrain parks, each row a name beside
icons. A status is a coloured icon (red closed, green open, amber on hold), and a trail's difficulty a green
circle, a blue square or one or two diamonds. The snowplough beside some trails is not read: the page does not say
what it marks. The uphill routes are left out: the status is of the lift-served mountain. The page's own count of
lifts is checked against what is read and every row must give a name and one status, so a change in its shape
fails instead of showing wrong numbers. The snow report (snowfall, the season's total, the depth on snowmaking
terrain and on natural terrain, each a range, and the surface) is carried in the shape of the Ikon feed's snow
report. The base depth is the snowmaking terrain's, with the natural terrain's beside it, and has a single figure
only where the two ends of its range are the same. The page does not say when the report was posted, so that is
empty. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://www.skiburke.com/the-mountain/weather-conditions"
NAME = "Burke Mountain"
# The colours of the page's status icons.
STATUSES = {"danger": "Closed", "success": "Open", "warning": "On hold"}
PIECE = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>|<table\b(.*?)</table>", re.S)
HEAD = re.compile(r"<th[^>]*>(.*?)</th>", re.S)
ROW = re.compile(r'<tr class="el-item[^>]*>(.*?)</tr>', re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
MARK = re.compile(r'<span class="uk-text-([a-z]+) uk-icon" uk-icon="icon:\s*([^"]+)"')
COUNT = re.compile(r"Lifts Open\s*</h1>\s*<h1[^>]*>\s*\d+\s*/\s*(\d+)\s*</h1>")
# The report's snowfall labels, by the names the Ikon feed gives them (the page reads those).
SNOWFALL = {"Snowfall: 24 Hours": "Last24HoursIn", "Snowfall: 48 Hours": "Last48HoursIn",
            "Snowfall: 7 Day": "Last7DaysIn"}
NOT_SKIED = {"Uphill Routes"}


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def status_of(name: str, cells: list) -> str:
    """The one status icon in a row's cells after its name; the snowplough is not a status."""
    marks = [colour for colour, icon in MARK.findall(" ".join(cells)) if "snowplow" not in icon]
    if not name or len(marks) != 1 or marks[0] not in STATUSES:
        raise ValueError(f"the row {name or '(no name)'} on the page does not give one status")
    return STATUSES[marks[0]]


def level_of(cell: str) -> str:
    """A trail's difficulty from its symbol; a terrain park's picture is none."""
    if "bootstrap-filled--circle" in cell:
        return "Green"
    if "bootstrap-filled--square" in cell:
        return "Blue"
    return {1: "Black", 2: "Double black"}.get(cell.count("poker-diamonds-fill"), "")


def number(said: str) -> float | int:
    figure = re.fullmatch(r"\d+(?:\.\d+)?", said.strip())
    if not figure:
        raise ValueError(f"a figure on the page does not read as inches: {said}")
    value = float(figure.group(0))
    return int(value) if value.is_integer() else value


def spread(said: str) -> tuple:
    """A depth the page gives as a range ('2-8'), or as one figure, as its least and most."""
    low, _, high = said.partition("-")
    return number(low), number(high if high.strip() else low)


def snow_report(said: dict) -> dict:
    """The page's snow figures in the shape of the Ikon feed's SnowReport, for the whole mountain."""
    if "Snowfall: 24 Hours" not in said or "Snowmaking" not in said or "Natural Terrain" not in said:
        raise ValueError("the snow report's 24-hour snowfall or its base depths were not found")
    least, most = spread(said["Snowmaking"])
    natural_least, natural_most = spread(said["Natural Terrain"])
    area = {"Name": "Mountain", "BaseIn": least if least == most else None, "BaseMinIn": least, "BaseMaxIn": most,
            "NaturalMinIn": natural_least, "NaturalMaxIn": natural_most}
    area.update({ikon: number(said[label]) if label in said else None for label, ikon in SNOWFALL.items()})
    if "Snowfall: Overnight" in said:
        area["OvernightIn"] = number(said["Snowfall: Overnight"])
    surface = ", ".join(dict.fromkeys(word.strip().capitalize() for word in said.get("Snow Surface", "").split("/")
                                      if word.strip()))
    return {"LastUpdate": None, "Resortwide": True, "BaseConditions": surface or None,
            "SeasonTotalIn": number(said["Snowfall: Season"]) if "Snowfall: Season" in said else None,
            "BaseArea": area}


def parse(page: str, now: datetime) -> dict:
    lifts, areas, said, heading = [], [], {}, ""
    for title, table in PIECE.findall(page):
        if not table:
            heading = text_of(title)
            continue
        columns = [text_of(column) for column in HEAD.findall(table)]
        rows = [CELL.findall(row) for row in ROW.findall(table)]
        if "Lift Name" in columns:
            lifts += [status_row(text_of(cells[0]), status_of(text_of(cells[0]), cells[1:]), None) for cells in rows]
        elif "Trail Name" in columns:
            if heading in NOT_SKIED:
                continue
            if any(len(cells) < 3 for cells in rows):
                raise ValueError("a trail row on the page has no status column")
            # The table of trails follows the lifts' under their heading; the glades and parks have their own.
            areas.append({"Name": "Trails" if heading == "Lift Status" else heading, "Lifts": [],
                          "Trails": [status_row(text_of(cells[1]), status_of(text_of(cells[1]), cells[2:]),
                                                level_of(cells[0])) for cells in rows]})
        else:
            said.update({text_of(cells[0]): text_of(cells[1]) for cells in rows if len(cells) == 2})
    areas = [area for area in areas if area["Trails"]]
    if not lifts:
        raise ValueError("the page's lift table was not found")
    counted = COUNT.search(page)
    if not counted:
        raise ValueError("the page's count of lifts was not found")
    if int(counted.group(1)) != len(lifts):
        raise ValueError(f"the page counts {counted.group(1)} lifts but {len(lifts)} were read")
    return {"Name": NAME, "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": []}, *areas], "SnowReport": snow_report(said)}
