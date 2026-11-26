"""Mt. Hood Skibowl's lifts, from its conditions and lift status page (skibowl.com/winter-condition-and-lift-status).

The page is built on the server and kept by hand. Under its "LIFT STATUS" heading is a table with a row for each
lift: its name, its status in a word or two ("Closed"), and sometimes a note ("Waiting for snow to fall"). A status
is carried as the page says it, so a lift reads as open only when the page's word is "Open"; a lift with no status
fails. The table also has the conveyor of the snow tube park, which carries no skiers: a mountain with only its
tubing hill running has no lift turning, so that row is left out. The page's grooming report names lifts, not
trails, so no trails are given.

No snow report is given. The page has a table for the date, the snow depth and the new snow, but the resort had
filled in none of it when this reader was written, so how it writes those figures is not known, and a guess at them
could give wrong numbers. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://skibowl.com/winter-condition-and-lift-status/"
NAME = "Mt. Hood Skibowl"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The rows of the lift table that are not ski lifts, by a word of their names.
NOT_SKIED = ("tube", "tubing")
LIFTS = re.compile(r"<h2[^>]*>\s*LIFT STATUS\s*</h2>(?:(?!<h2|<table).)*<table[^>]*>(.*?)</table>", re.S)
BODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TAG = re.compile(r"<[^>]+>")
STATUS = re.compile(r"[A-Za-z][A-Za-z '/&-]*")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def lift_row(cells: list) -> dict | None:
    """One lift, or None for the snow tube park's conveyor."""
    if len(cells) != 3:
        raise ValueError("a row of the lift table is not a name, a status and a note")
    name, said = words(cells[0]), words(cells[1])
    if not name:
        raise ValueError("a row of the lift table has no name")
    if any(word in name.lower() for word in NOT_SKIED):
        return None
    if not said:
        raise ValueError(f"{name} has no status")
    if not STATUS.fullmatch(said) or len(said) > 40:
        raise ValueError(f"{name} has a status that does not read as one: {said!r}")
    status = said.capitalize()
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": None}


def lifts_of(page: str) -> list:
    """The ski lifts of the page's lift table, in the page's order."""
    tables = LIFTS.findall(page)
    if len(tables) != 1:
        raise ValueError(f"the page has {len(tables)} tables under a LIFT STATUS heading, not one")
    body = BODY.search(tables[0])
    if not body:
        raise ValueError("the lift table has no body")
    lifts = [lift for lift in (lift_row(CELL.findall(row)) for row in ROW.findall(body.group(1))) if lift]
    if not lifts:
        raise ValueError("the lift table lists no lifts")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the lift table lists a lift twice")
    return lifts


def parse(page: str, now: datetime) -> dict:
    return {"Name": NAME, "LastUpdate": now.strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts_of(page), "Trails": []}]}
