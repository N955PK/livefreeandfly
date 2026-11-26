"""Massanutten's lifts and trails from its conditions page (massresort.com/snow-sports/conditions-webcams) and the
status that page asks its own site for (massresort.com/_actions/getLiftTrailStatus).

The page is built on the server with every lift and trail named but no status: each row carries an id, and the
page's script asks the site for the status of each id and fills the rows in. So this takes two requests. The page
gives the names, the lifts in one list and the trails under a heading for each difficulty (easiest, more
difficult, most difficult, extreme difficulty, freestyle terrain); a heading the reader does not know fails. The
status gives each lift's state (open, scheduled, hold, closed), in the words the page shows for them, and whether
each trail is open, with groomed among its features carried as its grooming. Every row of the page has to have a
status and every status a row, so a change in either fails instead of showing wrong numbers. The lifts are one
mountain area and each difficulty another.

The status answers only a POST with no body and no content type (``POST`` names the request; a GET gets the
site's page-not-found), and comes in the flattened form the site's framework writes: a list whose first item is
the answer, with every value inside it written as the position of that value in the list. The site gives no base
depth and no snowfall, so there is no snow report. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timezone

URLS = {"page": "https://www.massresort.com/snow-sports/conditions-webcams/",
        "status": "https://www.massresort.com/_actions/getLiftTrailStatus"}
# The requests that have to be sent as a POST, with no body.
POST = frozenset({"status"})
NAME = "Massanutten"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# A lift's states, in the words the page's own script shows for them.
STATES = {"open": "Open", "scheduled": "Scheduled", "hold": "On hold", "closed": "Closed"}
# The headings over the trails, with the words the app's difficulty symbols are keyed on; the parks have none.
LEVELS = {"Easiest": "Green", "More Difficult": "Blue", "Most Difficult": "Black",
          "Extreme Difficulty": "Double black", "Freestyle Terrain": ""}
BLOCK = r"<section[^>]*\sdata-lift-trail-block=\"{kind}\"[^>]*>(.*?)</section>"
LIFT = re.compile(r"<li data-status-lift=\"([0-9a-f]+)\"[^>]*>.*?<p class=\"lift-title[^\"]*\"[^>]*>(.*?)</p>", re.S)
HEADING_OR_TRAIL = re.compile(r"<span class=\"trail-group-title\"[^>]*>(.*?)</span>|"
                              r"<li data-status-trail=\"([0-9a-f]+)\"[^>]*>\s*(?:<svg.*?</svg>\s*)?"
                              r"<span[^>]*\sdata-status-label[^>]*>[^<]*</span>\s*<span[^>]*>(.*?)</span>", re.S)
TAG = re.compile(r"<[^>]+>")


def words(markup: str) -> str:
    """The text of a piece of the page: tags out, entities read, spaces run together."""
    return " ".join(html.unescape(TAG.sub(" ", markup)).split())


def unflattened(values: list, at: int = 0, depth: int = 0):
    """The value at one position of the flattened list, with the positions inside it followed. The framework
    writes a value that is not there as a position below zero, which is read as None."""
    if not isinstance(at, int) or isinstance(at, bool) or at >= len(values) or depth > 8:
        raise ValueError("the status is not in the flattened form expected")
    if at < 0:
        return None
    value = values[at]
    if isinstance(value, dict):
        return {key: unflattened(values, inner, depth + 1) for key, inner in value.items()}
    if isinstance(value, list):
        return [unflattened(values, inner, depth + 1) for inner in value]
    return value


def block(page: str, kind: str) -> str:
    found = re.search(BLOCK.format(kind=kind), page, re.S)
    if not found:
        raise ValueError(f"the page's list of {kind} was not found")
    return found.group(1)


def named(page: str) -> tuple:
    """The page's lifts as {id: name}, and its trails as (id, name, heading) in the page's order."""
    lifts = {found: words(name) for found, name in LIFT.findall(block(page, "lifts"))}
    trails, heading = [], None
    for said, found, name in HEADING_OR_TRAIL.findall(block(page, "trails")):
        if not found:
            heading = words(said)
            if heading not in LEVELS:
                raise ValueError(f"the trails have a heading the reader does not know: {heading!r}")
            continue
        if not heading:
            raise ValueError(f"{words(name)} is under no heading")
        trails.append((found, words(name), heading))
    if not lifts or not trails or not all(lifts.values()) or not all(name for _, name, _ in trails):
        raise ValueError("the page names no lifts or no trails")
    return lifts, trails


def parse(pages: dict, now: datetime) -> dict:
    lifts, trails = named(pages["page"])
    try:
        status = unflattened(json.loads(pages["status"]))
    except (ValueError, RecursionError) as error:
        raise ValueError(f"the status could not be read: {error}") from error
    if not isinstance(status, dict) or status.get("available") is not True:
        raise ValueError("the site says its status is not available")
    states, opened = status.get("lifts"), status.get("trails")
    if not isinstance(states, dict) or not isinstance(opened, dict):
        raise ValueError("the status has no lifts or no trails")
    if set(states) != set(lifts) or set(opened) != {found for found, _, _ in trails}:
        raise ValueError("the lifts and trails the page names are not the ones the status gives")
    area = {"Name": NAME, "Lifts": [], "Trails": []}
    for found, name in lifts.items():
        state = states[found].get("status") if isinstance(states[found], dict) else None
        if state not in STATES:
            raise ValueError(f"{name} has a state the reader does not know: {state!r}")
        area["Lifts"].append({"Name": name, "Status": STATES[state], "StatusEnglish": STATES[state].lower(),
                              "Difficulty": None})
    areas = {}
    for found, name, heading in trails:
        trail = opened[found]
        if not isinstance(trail, dict) or not isinstance(trail.get("open"), bool):
            raise ValueError(f"{name} is not said to be open or closed")
        said = "Open" if trail["open"] else "Closed"
        areas.setdefault(heading, []).append({
            "Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": LEVELS[heading],
            "Grooming": "Yes" if "groomed" in (trail.get("features") or []) else "No"})
    return {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [area, *({"Name": heading, "Lifts": [], "Trails": rows}
                                      for heading, rows in areas.items())]}
