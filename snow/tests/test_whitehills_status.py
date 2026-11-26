from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import whitehills

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "whitehills.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
SHOWN = '<div class="w-layout-vflex status-block">'
HIDDEN = '<div class="w-layout-vflex status-block w-condition-invisible">'
LIFT = 'class="h4-heading mb-0 white">Powder Line Express</h4>'
TRAIL = '<h4 class="h4-heading mb-0">meadow</h4>'


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def showing(page: str, heading: str, mark: str, said: str | None = None) -> str:
    """The page with the box under ``heading`` showing its block marked ``mark`` and no other."""
    start = page.index(heading)
    end = min(at for at in (page.find('-box">', start), len(page)) if at > 0)
    box = page[start:end].replace(SHOWN, HIDDEN)
    at = box.index(f'class="{mark}')
    block = box.rindex(HIDDEN, 0, at)
    box = box[:block] + SHOWN + box[block + len(HIDDEN):]
    if said:
        box = box.replace(">Closed</h4>", f">{said}</h4>")
    return page[:start] + box + page[end:]


def test_the_closed_resort_reads_each_lift_and_each_trail():
    # White Hills' page on 2026-11-26, closed for the season: two lifts and 24 trails, all closed.
    feed = whitehills.parse(PAGE, NOW)
    assert feed["Name"] == "White Hills" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 2, 0), ("Trails", 0, 24)]
    assert feed["MountainAreas"][0]["Lifts"] == [
        {"Name": "Powder Line Express", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Magic Carpet", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][1]["Trails"]}
    assert len(trails) == 24 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    # The page writes "meadow" and "leonard's saw"; each word is given a capital.
    assert trails["Meadow"] == {"Name": "Meadow", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    assert trails["Leonard's Saw"]["Difficulty"] == "Double black" and trails["Uh Oh"]["Difficulty"] == "Black"
    levels = [trail["Difficulty"] for trail in trails.values()]
    assert [levels.count(level) for level in ("Green", "Blue", "Black", "Double black")] == [2, 11, 7, 4]
    # The snow figures are empty outside the season, so there is no snow report.
    assert "SnowReport" not in feed


def test_the_block_that_is_showing_gives_the_status():
    page = showing(showing(PAGE, LIFT, "status-open", "Open"), TRAIL, "status-onhold", "On Hold")
    feed = whitehills.parse(page, NOW)
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in feed["MountainAreas"][0]["Lifts"]] == [
        ("Powder Line Express", "Open", "open"), ("Magic Carpet", "Closed", "closed")]
    trails = feed["MountainAreas"][1]["Trails"]
    assert [(trail["Name"], trail["Status"], trail["StatusEnglish"]) for trail in trails[:2]] == [
        ("Meadow", "On hold", "on hold"), ("Easy Street", "Closed", "closed")]
    # A word under the mark that is not one of the key's (the trail has two open blocks) does not change it.
    trail = whitehills.parse(showing(PAGE, TRAIL, "status-open", "Groomed"), NOW)["MountainAreas"][1]["Trails"][0]
    assert (trail["Status"], trail["StatusEnglish"]) == ("Open", "open")


def test_snow_in_centimetres_is_given_in_inches():
    page = changed("<h2> cm</h2>", "<h2>12 cm</h2>")
    page = changed("<h1> cm</h1>", "<h1>180 cm</h1>", page=page)
    page = changed("<h2>cm </h2>", "<h2>75cm </h2>", page=page)
    snow = whitehills.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 4.7, "BaseIn": 29.5}
    assert snow["SeasonTotalIn"] == 70.9 and snow["LastUpdate"] is None and snow["Resortwide"] is True
    # A figure with no number, or in other words, costs only the snow report.
    feed = whitehills.parse(changed("<h2>12 cm</h2>", "<h2>a dusting</h2>", page=page), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][1]["Trails"]) == 24
    assert "SnowReport" not in whitehills.parse(changed(">Snow depth</h4>", ">Depth</h4>", page=page), NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Powder Line Express does not have one status showing"):
        whitehills.parse(changed(SHOWN, HIDDEN, 2), NOW)
    with pytest.raises(ValueError, match="Powder Line Express does not have one status showing"):
        at = PAGE.index(LIFT)
        whitehills.parse(PAGE[:at] + PAGE[at:].replace(HIDDEN, SHOWN, 1), NOW)
    with pytest.raises(ValueError, match="Powder Line Express is marked open but reads 'Closed'"):
        whitehills.parse(showing(PAGE, LIFT, "status-open"), NOW)
    with pytest.raises(ValueError, match="status mark the reader does not know: status-delayed"):
        whitehills.parse(changed('class="status-closed"', 'class="status-delayed"'), NOW)
    with pytest.raises(ValueError, match="Meadow has difficulty symbols the reader does not know"):
        whitehills.parse(changed('class="stats-icon circle sm w-embed"', 'class="stats-icon oval sm w-embed"', 1), NOW)
    with pytest.raises(ValueError, match="2 lift boxes but 2 were read, or one twice"):
        whitehills.parse(changed(">magic carpet</h4>", ">powder Line Express</h4>"), NOW)
    with pytest.raises(ValueError, match="a block could not be read"):
        at = PAGE.index(LIFT)
        whitehills.parse(PAGE[:at] + PAGE[at:].replace('<div class="status-text">', '<div class="words">', 1), NOW)
    with pytest.raises(ValueError, match="0 lift boxes"):
        whitehills.parse(changed('class="lift-box"', 'class="lift"'), NOW)
    with pytest.raises(ValueError):
        whitehills.parse("<html><body>Not the page</body></html>", NOW)
