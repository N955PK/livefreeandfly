from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import nubsnob

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "nubsnob.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<i class=\"fas fa-times closed-icon\"></i>"
OPEN = "<i class=\"fas fa-check open-icon\"></i>"
NO_DEPTH = "<div class='conditions-cell cell-0'>Base Depth:</div><div class='conditions-cell cell-1'>N/A</div>"
UNDATED = "<div class='conditions-cell cell-1'>Thanksgiving Day</div>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def depth(said: str) -> str:
    return NO_DEPTH.replace("N/A", said)


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_part_of_the_mountain():
    # Nub's Nob's page on 2026-11-26, before it opened: ten lifts and 48 trails, all closed, and no base depth yet.
    feed = nubsnob.parse(PAGE, NOW)
    assert feed["Name"] == "Nub's Nob" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Nub's Nob", 10, 0), ("Nub’s North (The Front)", 0, 19), ("Nub’s Nob South", 0, 17),
        ("Pintail Peak", 0, 12)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Green Lift", "Red Lift", "Brown Lift", "JB Arena Rope Tow", "Orange Lift", "Black Lift", "Purple Lift",
        "Yellow Lift", "Gray Lift", "Space Worm"]
    assert lifts[0] == {"Name": "Green Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    assert trails[0] == {"Name": "Fun Bowl", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    levels = {trail["Name"]: trail["Difficulty"] for trail in trails}
    # A glade's two diamonds, a park's one, a square and a circle.
    assert (levels["Powerline Glades 1&2"], levels["Terrain Parks"], levels["Outback Jack"], levels["Easy Mile"]) == (
        "Double black", "Black", "Blue", "Green")
    assert set(levels.values()) == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_read_once_the_page_gives_a_depth():
    feed = nubsnob.parse(page(NO_DEPTH, depth("24-40\"")).replace(UNDATED, UNDATED.replace(
        "Thanksgiving Day", "Friday, November 27")), datetime(2026, 11, 27, 14, 0, tzinfo=timezone.utc))
    snow = feed["SnowReport"]
    # Noon of the day the page names, five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-27T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 24, "BaseMaxIn": 40, "Last24HoursIn": 0,
                                "Last72HoursIn": 0, "Last7DaysIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Happy Thanksgiving from all of us at Nub's Nob!")
    # One depth, and a day the page names only in words.
    snow = nubsnob.parse(page(NO_DEPTH, depth("30\"")), NOW)["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] == 30 and snow["LastUpdate"] is None
    # A date with no year that would be ahead of today is last year's.
    late = page(NO_DEPTH, depth("30\"")).replace("Thanksgiving Day", "December 30")
    assert nubsnob.parse(late, datetime(2027, 1, 2, 14, 0, tzinfo=timezone.utc))["SnowReport"]["LastUpdate"] == \
        "2026-12-30T17:00:00Z"


def test_an_open_lift_and_trail_are_read_from_their_symbols():
    opened = page(CLOSED, OPEN, 2).replace(
        "<div class='conditions-cell cell-0'>Lifts Open:</div><div class='conditions-cell cell-1'>0</div>",
        "<div class='conditions-cell cell-0'>Lifts Open:</div><div class='conditions-cell cell-1'>2</div>")
    lifts = nubsnob.parse(opened, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts[:3]] == ["open", "open", "closed"]
    trail = "<div class='conditions-cell cell-0'>Fun Bowl</div><div class='conditions-cell cell-1'>"
    feed = nubsnob.parse(page(trail + CLOSED, trail + OPEN), NOW)
    assert feed["MountainAreas"][1]["Trails"][0]["Status"] == "Open"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 0 lifts open but 1 were read"):
        nubsnob.parse(page(CLOSED, OPEN, 1), NOW)
    with pytest.raises(ValueError, match="Green Lift has the status symbols \\['shut-icon'\\]"):
        nubsnob.parse(page("closed-icon", "shut-icon", 1), NOW)
    with pytest.raises(ValueError, match="Fun Bowl has the difficulty symbols \\['novice-icon'\\]"):
        nubsnob.parse(page("beginner-icon", "novice-icon", 1), NOW)
    # The block of lifts under another name is read as a block of trails, and its rows have no difficulty.
    with pytest.raises(ValueError, match="Green Lift has the difficulty symbols \\[\\]"):
        nubsnob.parse(page("data-region='ski-lift-information'", "data-region='lifts'"), NOW)
    with pytest.raises(ValueError, match="the day's figures were not found"):
        nubsnob.parse(page("data-region=\"current\"", "data-region=\"today\""), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        nubsnob.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = nubsnob.parse(page(NO_DEPTH, depth("deep")), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
