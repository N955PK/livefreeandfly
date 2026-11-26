from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import snowyrange

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "snowyrange.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<td align="left">CLOSED</td>'
LIFT = '<td align="left">9:00 AM – 4:00 PM</td>\n' + CLOSED


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_each_lift_and_each_trail():
    # Snowy Range's page on 2026-11-26, before opening: five lifts and 33 trails, all closed.
    feed = snowyrange.parse(PAGE, NOW)
    assert feed["Name"] == "Snowy Range" and feed["LastUpdate"] == "2026-11-26T18:00:00Z" and "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 5, 0), ("Trails", 0, 33)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Pioneer", "The Colt", "Chute", "Sundance", "Virginian"]
    assert lifts[0] == {"Name": "Pioneer", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][1]["Trails"]}
    assert len(trails) == 33 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Blackfoot"] == {"Name": "Blackfoot", "Status": "Closed", "StatusEnglish": "closed",
                                   "Difficulty": "Green"}
    assert trails["Crow’s Nest"]["Difficulty"] == "Blue" and trails["Rattler"]["Difficulty"] == "Black"
    levels = [trail["Difficulty"] for trail in trails.values()]
    assert [levels.count(level) for level in ("Green", "Blue", "Black")] == [10, 15, 8]


def test_an_open_trail_and_an_open_lift_are_read():
    # The first status in the page is the first trail's; the lift's is found by the hours beside it.
    feed = snowyrange.parse(changed(CLOSED, '<td align="left">OPEN</td>', 1), NOW)
    trails = feed["MountainAreas"][1]["Trails"]
    assert trails[0] == {"Name": "Blackfoot", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green"}
    assert trails[1]["StatusEnglish"] == "closed"
    assert {lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]} == {"closed"}
    feed = snowyrange.parse(changed(LIFT, LIFT.replace("CLOSED", "Open"), 1), NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Pioneer", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert lifts[1]["StatusEnglish"] == "closed"
    assert {trail["StatusEnglish"] for trail in feed["MountainAreas"][1]["Trails"]} == {"closed"}


def test_another_status_is_carried_in_the_page_s_words():
    lift = snowyrange.parse(changed(LIFT, LIFT.replace("CLOSED", "WIND HOLD"), 1), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Pioneer", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift status table was not found"):
        snowyrange.parse(changed(">HOURS OF OPERATION<", ">HOURS<"), NOW)
    with pytest.raises(ValueError, match="trail report table was not found"):
        snowyrange.parse(changed(">Symbol</th>", ">Sign</th>"), NOW)
    with pytest.raises(ValueError, match="Blackfoot has a difficulty the reader does not know: 'Hardest'"):
        snowyrange.parse(changed('<td align="left">Easiest</td>', '<td align="left">Hardest</td>', 1), NOW)
    with pytest.raises(ValueError, match="Blackfoot has no name or no status"):
        snowyrange.parse(changed(CLOSED, '<td align="left"></td>', 1), NOW)
    with pytest.raises(ValueError, match="lift status table is not rows of 3 cells"):
        snowyrange.parse(changed(LIFT, CLOSED, 1), NOW)
    with pytest.raises(ValueError, match="lists a trail twice"):
        snowyrange.parse(changed('<td align="left">Centennial</td>', '<td align="left">Blackfoot</td>'), NOW)
    with pytest.raises(ValueError):
        snowyrange.parse("<html><body>Not the page</body></html>", NOW)
