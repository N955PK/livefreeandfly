"""Montage Mountain's lifts and trails, from the trail status table of its trails page
(montagemountainresorts.com/trails/#trailconditions).

The page is built on the server. Its trail status is one table: a heading row "TRAIL, STATUS, GROOMED" over a row
for each trail, then a heading row "LIFT, STATUS" over a row for each lift. A row is a picture, a name, a status and
whether it is groomed. A status is carried in the page's own words (Open, Closed). A trail's difficulty is the
picture in its first cell, read from the picture's name; a trail with no picture (a glade) has none, and a picture
the reader does not know fails. The page names no areas of the mountain, so the lifts and the trails are one area.
A row that is not four cells, a name given twice, a row with no status, or a table without both of its headings
fails, so a change in the page's shape fails instead of showing wrong numbers.

The page was only ever seen closed, with the groomed column empty. An empty cell is read as not groomed, and a cell
saying yes (or holding a picture) as groomed; if the column holds any other words, grooming is left off every trail
instead of being guessed. The page's snow report is a dated piece of writing with no base depth or snowfall figures,
so no snow report is given. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.montagemountainresorts.com/trails/"
NAME = "Montage Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The difficulty pictures, by the start of their names, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easy": "Green", "intermediate": "Blue", "diamond": "Black", "doublediamond": "Double black"}
GROOMED = {"": "No", "no": "No", "n": "No", "yes": "Yes", "y": "Yes", "groomed": "Yes", "x": "Yes", "✓": "Yes",
           "✔": "Yes"}
TABLE = re.compile(r"<table id=\"tgtable\"[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<(t[dh])\b([^>]*)>(.*?)</t[dh]>", re.S)
PICTURE = re.compile(r"url\(\s*['\"]?([^'\")]*)['\"]?\s*\)")
LETTERS = re.compile(r"[A-Za-z]+")
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def difficulty(attributes: str, name: str) -> str:
    """A trail's difficulty from the picture behind its first cell; none where the cell has no picture."""
    picture = PICTURE.search(html.unescape(attributes))
    if not picture or not picture.group(1).strip():
        return ""
    # A picture is named "Easy-e1477746564526.png" or "DoubleDiamond.png": the letters it starts with say which.
    start = LETTERS.match(picture.group(1).rsplit("/", 1)[-1])
    if not start or start.group(0).lower() not in LEVELS:
        raise ValueError(f"{name} has a difficulty picture the reader does not know: {picture.group(1)}")
    return LEVELS[start.group(0).lower()]


def rows_of(page: str) -> tuple:
    """The lifts and the trails of the trail status table, in the page's order, and what each trail's groomed cell
    says."""
    tables = TABLE.findall(page)
    if len(tables) != 1:
        raise ValueError(f"the page has {len(tables)} trail status tables, not one")
    lifts, trails, grooming, kind = [], [], [], None
    for row in ROW.findall(tables[0]):
        cells = CELL.findall(row)
        if len(cells) != 4:
            raise ValueError("a row of the trail status is not a picture, a name, a status and a grooming")
        name, said = words(cells[1][2]), words(cells[2][2])
        if cells[1][0] == "th":
            if (name, said) not in (("TRAIL", "STATUS"), ("LIFT", "STATUS")):
                raise ValueError(f"the trail status has a heading the reader does not know: {name!r}, {said!r}")
            kind = name
            continue
        if kind is None:
            raise ValueError("the trail status has a row before its first heading")
        if not name or not LETTERS.match(said):
            raise ValueError(f"a row of the trail status reads {name!r}, {said!r}, not a name and a status")
        found = {"Name": name, "Status": said.capitalize(), "StatusEnglish": said.lower(),
                 "Difficulty": difficulty(cells[0][1], name) if kind == "TRAIL" else None}
        if kind == "TRAIL":
            trails.append(found)
            grooming.append("yes" if "<img" in cells[3][2] else words(cells[3][2]).lower())
        else:
            lifts.append(found)
    return lifts, trails, grooming


def parse(page: str, now: datetime) -> dict:
    lifts, trails, grooming = rows_of(page)
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    for rows in (lifts, trails):
        names = [row["Name"].lower() for row in rows]
        if len(set(names)) != len(names):
            raise ValueError("the trail status names a lift or a trail twice")
    if all(said in GROOMED for said in grooming):
        trails = [{**trail, "Grooming": GROOMED[said]} for trail, said in zip(trails, grooming)]
    else:
        # Words the reader has not seen in the groomed column: grooming is left off, not guessed.
        print(f"{NAME}: the groomed column reads {sorted(set(grooming) - set(GROOMED))}, which is not known")
    return {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
