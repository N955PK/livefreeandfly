"""Bristol Mountain's lifts and trails from its conditions page (bristolmountain.com/conditions).

The page is built on the server: a table of the lifts, then a table of trails under a heading for each difficulty
(easier, more difficult, most difficult, extremely difficult), one of the terrain parks under "On-Snow Experiences"
and one of the cross-country loops. A lift's or trail's status is the word in its row, carried as the page says it.
A trail takes its difficulty from the heading its table is under, and a table under a heading the reader does not
know fails; the terrain parks have none. A trail whose surface codes include MG, the page's code for machine
groomed, is carried as groomed. The cross-country loops are left out: the status is of the lift-served mountain.
The lifts are one mountain area and each table of trails another.

The page gives no base depth and no snowfall, so there is no snow report: its "Last Updated" is when the page was
last edited. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://www.bristolmountain.com/conditions/"
NAME = "Bristol Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The headings over the tables of trails, with the words the app's difficulty symbols are keyed on.
LEVELS = {"Easier": "Green", "More Difficult": "Blue", "Most Difficult": "Black",
          "Extremely Difficult": "Double black", "On-Snow Experiences": ""}
# The heading over the table that is not of the lift-served mountain.
NORDIC = "Nordic/Cross-Country"
# The columns of the two kinds of table; the terrain parks' third column is their size.
LIFT_COLUMNS = ("Lift", "Status", "Notes")
TRAIL_COLUMNS = ("Trail", "Status", ("Surface Conditions", "Feature Size/Difficulty"), "Comments")
HEADING_OR_TABLE = re.compile(r"<h[23][^>]*>(.*?)</h[23]>|<table\s+class='avia-table\s[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def fits(found: list, columns: tuple) -> bool:
    return len(found) == len(columns) and all(said in wanted if isinstance(wanted, tuple) else said == wanted
                                              for said, wanted in zip(found, columns))


def row_of(cells: list, difficulty) -> dict:
    """One lift or trail: its name and the status word of its row."""
    name, status = cells[0], cells[1].capitalize()
    if not name or not status or not status.replace(" ", "").isalpha():
        raise ValueError(f"{name or 'a row'} has the status {cells[1]!r}, not a word")
    row = {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}
    if difficulty is not None:
        row["Grooming"] = "Yes" if "MG" in re.split(r"[/,\s]+", cells[2]) else "No"
    return row


def areas_of(page: str) -> list:
    """The lifts' area and one for each table of trails, in the page's order."""
    areas, heading = [], None
    for said, table in HEADING_OR_TABLE.findall(page):
        if not table:
            heading = words(said)
            continue
        rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(table)]
        if not rows:
            raise ValueError("a table has no rows")
        if fits(rows[0], LIFT_COLUMNS):
            areas.append({"Name": NAME, "Lifts": [row_of(cells, None) for cells in rows[1:]], "Trails": []})
        elif fits(rows[0], TRAIL_COLUMNS) and heading in LEVELS:
            if any(len(cells) != len(TRAIL_COLUMNS) for cells in rows[1:]):
                raise ValueError(f"a row under {heading} is not a trail, a status, a surface and a comment")
            areas.append({"Name": heading, "Lifts": [], "Trails": [row_of(cells, LEVELS[heading]) for cells in rows[1:]]})
        elif not (fits(rows[0], TRAIL_COLUMNS) and heading == NORDIC):
            raise ValueError(f"the table under {heading!r} with the columns {rows[0]} is not one the reader knows")
    if len({area["Name"] for area in areas}) != len(areas):
        raise ValueError("the page has two tables of lifts, or two under one heading")
    if not any(area["Lifts"] for area in areas) or not any(area["Trails"] for area in areas):
        raise ValueError("the page lists no lifts or no trails")
    return areas


def parse(page: str, now: datetime) -> dict:
    return {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP), "MountainAreas": areas_of(page)}
