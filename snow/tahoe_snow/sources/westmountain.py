"""West Mountain's lifts and trails from its trail conditions page (westmountain.com/trail-conditions).

The page is built on the server, as tables the mountain fills in by hand, and each is known here by the words
that head its columns. "LIFTS, OPEN/CLOSED" is the lifts, each with its status in words, carried as the page says
it; a lift's name may carry a note of its hours, which is left on it. "Trails, Difficulty, Open/Closed,
Conditions, LIGHTS" is the trails: a difficulty in words (Green, Blue, Black; one the reader does not know
fails), a status, and the surface in the page's own letters ("MG" for machine groomed, "PP" for packed powder) or
in words. A trail whose letters include "MG" is carried as groomed. The tables of parking lots and tubing lanes
are not read. The page does not divide the mountain into parts, so the lifts and trails are one area. Every row
of the two tables is one read, so a change in the page's shape fails instead of showing wrong numbers.

The page gives no snow report: no base depth and no new snow, and no time it was updated. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://westmountain.com/trail-conditions/"
NAME = "West Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The tables, by the words that head their columns.
LIFTS, TRAILS = ("lifts", "open/closed"), ("trails", "difficulty", "open/closed", "conditions", "lights")
# The page's words for a difficulty are the ones the app's difficulty symbols are keyed on.
LEVELS = {"green": "Green", "blue": "Blue", "black": "Black", "double black": "Double black"}
GROOMED = "MG"
TABLE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S)
HEAD = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S)
CELL = re.compile(r"<td\b[^>]*>(.*?)</td>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def tables(page: str) -> dict:
    """The tables that are read, each under the words that head its columns, as rows of cells."""
    found = {}
    for body in TABLE.findall(page):
        heads = tuple(words(head).lower() for head in HEAD.findall(body))
        if heads not in (LIFTS, TRAILS):
            continue
        rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(body)]
        if heads in found:
            raise ValueError(f"the page has two tables headed {heads}")
        found[heads] = [row for row in rows if row]
    return found


def cells_of(row: list, width: int, what: str) -> list:
    """A row's cells without the empty ones the page sometimes leaves at its end."""
    while len(row) > width and not row[-1]:
        row = row[:-1]
    if len(row) != width or not row[0]:
        raise ValueError(f"a row of the {what} does not have a name and {width - 1} more cells: {row}")
    return row


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    if not said:
        raise ValueError(f"{name} has no status")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(row: list) -> dict:
    name, level, said, surface, _ = cells_of(row, 5, "trails")
    if level.lower() not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {level}")
    letters = re.findall(r"[A-Za-z]+", surface)
    return {**status_row(name, said, LEVELS[level.lower()]), "Grooming": "Yes" if GROOMED in letters else "No"}


def parse(page: str, now: datetime) -> dict:
    found = tables(page)
    missing = [heads for heads in (LIFTS, TRAILS) if heads not in found]
    if missing:
        raise ValueError(f"the page has no table headed {missing}")
    lifts = [status_row(*cells_of(row, 2, "lifts"), None) for row in found[LIFTS]]
    trails = [trail_row(row) for row in found[TRAILS]]
    if not lifts or not trails:
        raise ValueError("the page lists no lifts or no trails")
    for rows in (lifts, trails):
        if len({row["Name"] for row in rows}) != len(rows):
            raise ValueError("the page lists a lift or a trail twice")
    return {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
