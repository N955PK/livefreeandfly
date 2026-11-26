"""Windham's lifts and trails from the live trail map its mountain page shows
(usa.lumiplan.pro/moduleweb/3.0/windham.php?module=ouvertures, framed by windhammountainclub.com/mountain).

The map is Lumiplan's. Its page loads the statuses as a piece of markup from ``php/getOuvertures.php`` on the same
host, which is what is read here: one marker for each lift and each trail, laid over the drawing of the mountain.
A marker carries a picture of what it is (a chairlift, a carpet, or a trail's green circle, blue square, black
diamond or double black diamond, or a terrain park), its name, and its status as a coloured mark and in words:
"Open", "Closed", "Out of operations", or something else while it is expected or on hold. The words are carried as
the map says them, and they have to agree with the mark. The map does not divide the mountain into parts, so the
lifts and trails are one area and the parks another. A kind of marker or a mark the reader does not know fails, and
every marker in the piece is one read, so a change in its shape fails instead of showing wrong numbers.

The map gives no snow report: no base depth and no new snow. Standard library only.
"""
import html
import re
from datetime import datetime

URL = "https://usa.lumiplan.pro/moduleweb/3.0/php/getOuvertures.php?resort=windham"
NAME = "Windham"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# The pictures of a trail's kind, in the words the app's difficulty symbols are keyed on; a terrain park has none.
LEVELS = {"piste-gc": "Green", "piste-bs": "Blue", "piste-bd": "Black", "piste-dbd": "Double black",
          "terrain-park": ""}
PARK = "terrain-park"
# A lift's picture is named for its kind (a chairlift, a detachable chairlift, a carpet), after this.
LIFT = "prl_"
# The coloured marks, by what the map's legend says of them: a square for a lift and a numbered disc for a trail.
MARKS = {"carre-vert": "open", "carre-orange": "waiting", "carre-rouge": "closed", "carre-bleu": "out",
         "1": "open", "3": "waiting", "2": "closed", "4": "out"}
# The words that go with a mark; a lift or trail that is expected or on hold can be said several ways.
SAID = {"open": "open", "closed": "closed", "out of operations": "out"}
OVERLAY = re.compile(r"<div class=\"overlay ski-plus\" id=\"calque_ouverture\"")
SCRIPT = re.compile(r"<script\b.*?</script>", re.S)
MARKER = re.compile(r"<div class=\"marker-icon\"[^>]*>\s*<img[^>]*\ssrc=\"svg/([\w-]+)\.svg\"\s*/>\s*</div>\s*"
                    r"<div class=\"ouvertures-marker-popover\"[^>]*>\s*<div class=\"marker-title\">\s*"
                    r"<img src=\"images/markers/([\w-]+)\.svg\"\s*/>([^<]*)<div class=\"toggle-marker\"></div>\s*</div>"
                    r"\s*<div class=\"marker-content\">\s*<div class=\"marker-title [a-z-]+\">\s*<img[^>]*/>([^<]*)</div>",
                    re.S)


def words(markup: str) -> str:
    """The text of a piece of the map: entities read, spaces run together."""
    return " ".join(html.unescape(markup).split())


def status_row(mark: str, name: str, said: str, difficulty: str | None) -> dict:
    """A lift or a trail with its status in the map's words, which have to agree with its coloured mark."""
    if not name or not said:
        raise ValueError("a marker has no name or no status")
    if mark not in MARKS:
        raise ValueError(f"{name} has a mark the reader does not know: {mark}")
    if SAID.get(said.lower(), "waiting") != MARKS[mark]:
        raise ValueError(f"{name} is marked {MARKS[mark]} but reads {said!r}")
    said = said.capitalize()
    return {"Name": name, "Status": said, "StatusEnglish": said.lower(), "Difficulty": difficulty}


def parse(page: str, now: datetime) -> dict:
    if not OVERLAY.search(page):
        raise ValueError("the map's statuses were not found")
    page = SCRIPT.sub("", page)
    lifts, trails, parks = [], [], []
    for mark, kind, name, said in MARKER.findall(page):
        name, said = words(name), words(said)
        if kind.startswith(LIFT):
            lifts.append(status_row(mark, name, said, None))
        elif kind in LEVELS:
            (parks if kind == PARK else trails).append(status_row(mark, name, said, LEVELS[kind]))
        else:
            raise ValueError(f"{name} is a kind of marker the reader does not know: {kind}")
    if not lifts or not trails:
        raise ValueError("the map lists no lifts or no trails")
    # Every marker on the map is one read, so a change in its shape fails instead of dropping lifts or runs.
    listed, found = page.count("class=\"ouvertures-marker\""), len(lifts) + len(trails) + len(parks)
    if found != listed:
        raise ValueError(f"the map has {listed} markers but {found} were read")
    areas = [{"Name": NAME, "Lifts": lifts, "Trails": trails}]
    if parks:
        areas.append({"Name": "Terrain Parks", "Lifts": [], "Trails": parks})
    return {"Name": NAME, "LastUpdate": now.strftime(STAMP), "MountainAreas": areas}
