from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import skibowl

# The page from its weather table to the end of its grooming report, with its scripts, styles and drawings taken out;
# the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "skibowl.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
MULTORPOR = '<div class="jet-table__cell-text">Multorpor Chair</div></div></div></td>'
CLOSED = '<div class="jet-table__cell-text">Closed</div>'


def page(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new)


def multorpor(status: str) -> str:
    """The page with the Multorpor Chair's status cell holding other words."""
    start = PAGE.index(MULTORPOR) + len(MULTORPOR)
    at = PAGE.index(CLOSED, start)
    assert at - start < 200
    return PAGE[:at] + f'<div class="jet-table__cell-text">{status}</div>' + PAGE[at + len(CLOSED):]


def test_the_page_is_the_resort_s_lift_status_page():
    assert skibowl.URL == "https://skibowl.com/winter-condition-and-lift-status/"


def test_the_mountain_waiting_for_snow_reads_its_seven_ski_lifts_as_closed():
    # Skibowl's page on 2026-11-26, before it opens: eight rows, every one closed, one of them the tube park's.
    feed = skibowl.parse(PAGE, NOW)
    assert feed["Name"] == "Mt. Hood Skibowl" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [
        ("Mt. Hood Skibowl", 7, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # The "Snow Tube Conveyor Lift" carries no skiers and is left out; the weather and grooming tables are not lifts.
    assert [lift["Name"] for lift in lifts] == [
        "Lower Bowl Chair", "Upper Bowl Chair", "West Rope Tow Terrain Park", "West Learning Conveyor Lift",
        "Multorpor Chair", "Handle Tow", "Cascade Chair"]
    # "Closed " is written with a space after it for the Upper Bowl Chair.
    assert lifts[1] == {"Name": "Upper Bowl Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}


def test_an_open_lift_and_a_lift_on_hold_take_the_page_s_words():
    lift = skibowl.parse(multorpor("OPEN"), NOW)["MountainAreas"][0]["Lifts"][4]
    assert lift == {"Name": "Multorpor Chair", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    lift = skibowl.parse(multorpor("Wind Hold"), NOW)["MountainAreas"][0]["Lifts"][4]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Multorpor Chair", "Wind hold", "wind hold")


def test_the_tube_park_s_conveyor_running_alone_turns_no_ski_lift():
    tubing = '<div class="jet-table__cell-text">Snow Tube Conveyor Lift</div></div></div></td>'
    start = PAGE.index(tubing)
    at = PAGE.index(CLOSED, start)
    feed = skibowl.parse(PAGE[:at] + CLOSED.replace("Closed", "Open") + PAGE[at + len(CLOSED):], NOW)
    assert {lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]} == {"closed"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 tables under a LIFT STATUS heading"):
        skibowl.parse(page(">LIFT STATUS</h2>", ">LIFTS</h2>"), NOW)
    with pytest.raises(ValueError, match="0 tables under a LIFT STATUS heading"):
        skibowl.parse("<html><body>Just a moment...</body></html>", NOW)
    with pytest.raises(ValueError, match="Multorpor Chair has no status"):
        skibowl.parse(multorpor(" "), NOW)
    with pytest.raises(ValueError, match="does not read as one"):
        skibowl.parse(multorpor("9am - 4pm"), NOW)
    with pytest.raises(ValueError, match="has no name"):
        skibowl.parse(page(">Multorpor Chair</div>", "></div>"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        skibowl.parse(page(">Multorpor Chair</div>", ">Cascade Chair</div>"), NOW)
    with pytest.raises(ValueError, match="not a name, a status and a note"):
        skibowl.parse(page(MULTORPOR, MULTORPOR + '<td class="jet-table__cell"></td>'), NOW)
