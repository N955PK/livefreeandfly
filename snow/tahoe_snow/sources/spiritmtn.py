"""Spirit Mountain's lifts and trails, from its current conditions page (spiritmt.com/current-conditions).

The page is built on the server. Under "Trails" it has a grid of the trails for each difficulty (Easiest, More
Difficult, Most Difficult, Terrain Parks) and under "Lifts" a grid of the lifts. Every trail and lift is one item
of a grid: the item's own classes say whether it is a trail or a lift and, for a trail, its difficulty, and inside
it are its name and its status in words. The status is also in the class of the words, and the two have to agree;
it is carried as the page says it ("Closed", "Closed for season"). The item's classes also carry status words of
their own, which run behind the written status and are not read. A terrain park has no difficulty, and a
difficulty the reader does not know fails. Every status on the page is one read, so a change in the page's shape
fails instead of showing wrong numbers. The mountain is one mountain area holding all of them.

The page gives no snow report: no base depth and no new snow. Standard library only.
"""
import html
import re
from datetime import datetime, timezone

URL = "https://spiritmt.com/current-conditions/"
NAME = "Spirit Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The difficulty in a trail's classes, in the words the app's difficulty symbols are keyed on; parks have none.
LEVELS = {"easiest": "Green", "more-difficult": "Blue", "most-difficult": "Black", "terrain-parks": ""}
ITEM = re.compile(r"class=\"elementor elementor-\d+ e-loop-item ([^\"]*)\"")
KIND = re.compile(r"(?:^|\s)type-(trail|lift)(?:\s|$)")
LEVEL = re.compile(r"(?:^|\s)trail-difficulty-([a-z-]+)(?:\s|$)")
TITLE = re.compile(r"<h3 class=\"elementor-heading-title[^\"]*\">(.*?)</h3>", re.S)
STATUS = re.compile(r"<span class=\"trail-status trail-status-([a-z-]+)\">(.*?)</span>", re.S)
STATUSES = "<span class=\"trail-status "
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def row_of(kind: str, classes: str, body: str) -> dict:
    """One lift or trail, from its item of a grid."""
    title, status = TITLE.search(body), STATUS.search(body)
    if not title or not words(title.group(1)) or not status or not words(status.group(2)):
        raise ValueError(f"a {kind} on the page is not a name and a status")
    name, marked, said = words(title.group(1)), status.group(1), words(status.group(2))
    if marked != "-".join(said.lower().split()):
        raise ValueError(f"{name} is marked {marked} but reads {said!r}")
    said = said.capitalize()
    difficulty = None
    if kind == "trail":
        level = LEVEL.search(classes)
        if not level or level.group(1) not in LEVELS:
            raise ValueError(f"{name} has a difficulty the reader does not know: {level.group(1) if level else None}")
        difficulty = LEVELS[level.group(1)]
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def parse(page: str, now: datetime) -> dict:
    items = list(ITEM.finditer(page))
    lifts, trails = [], []
    for at, item in enumerate(items):
        kind = KIND.search(item.group(1))
        if not kind:
            continue
        end = items[at + 1].start() if at + 1 < len(items) else len(page)
        row = row_of(kind.group(1), item.group(1), page[item.end():end])
        (lifts if kind.group(1) == "lift" else trails).append(row)
    listed = page.count(STATUSES)
    if not lifts or not trails or len(lifts) + len(trails) != listed:
        raise ValueError(f"the page has {listed} statuses but {len(lifts)} lifts and {len(trails)} trails were read")
    if len({lift["Name"] for lift in lifts}) != len(lifts):
        raise ValueError("the page lists a lift twice")
    return {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": lifts, "Trails": trails}]}
