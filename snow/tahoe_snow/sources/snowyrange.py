"""Snowy Range's lifts and trails from its lifts and trails report (snowyrangeski.com/lifts-and-trails-report).

The page is built on the server and is written by hand: two plain tables, found here by their headings. The trail
report is a row for each trail: its name, its difficulty in words (Easiest, More Difficult, Most Difficult; one
the reader does not know fails), a symbol, and its status in a word. The lift status is a row for each lift: its
name, its hours and its status. The page's own key gives two statuses, open and closed; anything else typed there
is carried in the page's words, and a row with no status fails. Every row of both tables has to be read, so a
change in the page's shape fails instead of showing wrong numbers. The lifts are one mountain area and the trails
another, since the page does not say which lift serves which trail.

The page gives no date, no grooming and no snow figures (its snow report page frames another site's widget), so
there is no snow report. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://snowyrangeski.com/lifts-and-trails-report/"
NAME = "Snowy Range"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The trail report's difficulties, in the words the app's difficulty symbols are keyed on.
LEVELS = {"easiest": "Green", "more difficult": "Blue", "most difficult": "Black", "expert": "Double black",
          "terrain park": ""}
# The headings each table begins with (the trail report has a last column with no heading and nothing in it).
TRAIL_HEADINGS = ["trail name", "difficulty", "symbol", "status", ""]
LIFT_HEADINGS = ["lift name", "hours of operation", "status"]
TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def table_rows(page: str, headings: list, kind: str) -> list:
    """The rows under the one table that begins with ``headings``, each as wide as the headings."""
    found = []
    for table in TABLE.findall(page):
        rows = [[words(cell) for cell in CELL.findall(row)] for row in ROW.findall(table)]
        if rows and [cell.lower() for cell in rows[0]] == headings:
            found.append(rows[1:])
    if len(found) != 1:
        raise ValueError(f"the {kind} table was not found, or there are two")
    rows = found[0]
    if not rows or any(len(cells) != len(headings) for cells in rows):
        raise ValueError(f"the {kind} table is not rows of {len(headings)} cells")
    return rows


def status_row(name: str, said: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in the page's words."""
    if not name or not said:
        raise ValueError(f"{name or 'a row'} has no name or no status")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def trail_row(cells: list) -> dict:
    name, level, _, said, _ = cells
    if level.lower() not in LEVELS:
        raise ValueError(f"{name} has a difficulty the reader does not know: {level!r}")
    return status_row(name, said, LEVELS[level.lower()])


def parse(page: str, now: datetime) -> dict:
    lifts = [status_row(name, said, None) for name, _, said in table_rows(page, LIFT_HEADINGS, "lift status")]
    trails = [trail_row(cells) for cells in table_rows(page, TRAIL_HEADINGS, "trail report")]
    for kind, rows in (("lift", lifts), ("trail", trails)):
        if len({row["Name"] for row in rows}) != len(rows):
            raise ValueError(f"the page lists a {kind} twice")
    return {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": "Lifts", "Lifts": lifts, "Trails": []},
                              {"Name": "Trails", "Lifts": [], "Trails": trails}]}
