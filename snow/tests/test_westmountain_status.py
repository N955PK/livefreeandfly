from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import westmountain

# The page with its scripts, styles, drawings, header and footer taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "westmountain.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def test_the_preseason_mountain_reads_its_lifts_and_trails():
    # West Mountain's page on 2026-11-26, before opening: six lifts, all closed, and 36 trails.
    feed = westmountain.parse(PAGE, NOW)
    assert feed["Name"] == "West Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("West Mountain", 6, 36)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # A lift's note of its hours is left on its name, and the row with an empty cell at its end is read.
    assert [lift["Name"] for lift in lifts] == [
        "Apex Triple Chairlift (open 10am-4pm during April operations)", "Face Quad Chairlift",
        "West Express Triple Chairlift", "Learning Area Surface Lift", "Tubing Park Surface Lift",
        "Learning Area Rope Tow for Kiddie TP access"]
    assert lifts[1] == {"Name": "Face Quad Chairlift", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][0]["Trails"]}
    assert trails["The Cure"] == {"Name": "The Cure", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Black", "Grooming": "No"}
    # "MG" among a trail's letters is machine groomed, however the letters are set apart.
    assert trails["Coy Dog"]["Grooming"] == "Yes" and trails["The Alley"]["Grooming"] == "Yes"
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black")] == [17, 12, 7]
    # The page had one glade marked open with every lift closed, and it is carried as the page says it.
    assert [name for name, trail in trails.items() if trail["StatusEnglish"] == "open"] == ["Northwest Glades"]
    # The parking lots and the tubing lanes are not lifts or trails.
    assert "Main Base Parking Lot" not in trails and "Upper Lane 1" not in trails


def test_an_open_lift_and_an_open_trail_are_read():
    page = changed("<td>Face Quad Chairlift</td><td>Closed</td>", "<td>Face Quad Chairlift</td><td>Open</td>")
    page = changed("<td>The Cure</td><td>Black</td><td>Closed</td><td>Closed</td>",
                   "<td>The Cure</td><td>Black</td><td>Open</td><td>MG/PP</td>", page=page)
    area = westmountain.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][1] == {"Name": "Face Quad Chairlift", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    trail = next(trail for trail in area["Trails"] if trail["Name"] == "The Cure")
    assert trail == {"Name": "The Cure", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Black",
                     "Grooming": "Yes"}


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = changed("<td>Face Quad Chairlift</td><td>Closed</td>", "<td>Face Quad Chairlift</td><td>Wind Hold</td>")
    lift = westmountain.parse(page, NOW)["MountainAreas"][0]["Lifts"][1]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no table headed"):
        westmountain.parse(changed('<span class="pp-table-header-text">LIFTS</span>',
                                   '<span class="pp-table-header-text">CHAIRS</span>'), NOW)
    with pytest.raises(ValueError, match="no table headed"):
        westmountain.parse(changed('<span class="pp-table-header-text">LIGHTS</span>', ""), NOW)
    with pytest.raises(ValueError, match="The Cure has a difficulty the reader does not know: Orange"):
        westmountain.parse(changed("<td>The Cure</td><td>Black</td>", "<td>The Cure</td><td>Orange</td>"), NOW)
    with pytest.raises(ValueError, match="a row of the trails does not have a name and 4 more cells"):
        westmountain.parse(changed("<td>The Cure</td><td>Black</td>", "<td>The Cure</td>"), NOW)
    with pytest.raises(ValueError, match="Face Quad Chairlift has no status"):
        westmountain.parse(changed("<td>Face Quad Chairlift</td><td>Closed</td>",
                                   "<td>Face Quad Chairlift</td><td></td>"), NOW)
    with pytest.raises(ValueError, match="lists a lift or a trail twice"):
        westmountain.parse(changed("<td>The Cure</td>", "<td>Gnarwall</td>"), NOW)
    with pytest.raises(ValueError):
        westmountain.parse("<html><body>Not the page</body></html>", NOW)
