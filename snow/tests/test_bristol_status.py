from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bristol

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "bristol.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<td class='avia-center-col'>CLOSED</td>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_difficulty():
    # Bristol's page on 2026-11-26, still as it closed in April: seven lifts and 42 trails, all closed.
    feed = bristol.parse(PAGE, NOW)
    assert feed["Name"] == "Bristol Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    # The two cross-country loops are left out, and the page gives no snow figures.
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Bristol Mountain", 7, 0), ("Easier", 0, 13), ("More Difficult", 0, 22), ("Most Difficult", 0, 4),
        ("Extremely Difficult", 0, 1), ("On-Snow Experiences", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Comet Express Quad", "Galaxy Express Quad", "Lunar Launch Surface Lift #1", "Lunar Launch Surface Lift #2",
        "Morning Star Quad", "Rocket Triple", "Sunset Double"]
    assert lifts[0] == {"Name": "Comet Express Quad", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    assert trails[0] == {"Name": "Eclipse", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    # "Halley’s Run" carries the surface codes MG/FG/LG/TC, and MG is machine groomed.
    assert trails[2]["Name"] == "Halley’s Run" and trails[2]["Grooming"] == "Yes"
    assert trails[-1] == {"Name": "Shooting Star Terrain Park", "Status": "Closed", "StatusEnglish": "closed",
                          "Difficulty": "", "Grooming": "No"}
    assert not {"Aries", "Gemini"} & {trail["Name"] for trail in trails}
    assert [area["Trails"][0]["Difficulty"] for area in feed["MountainAreas"][1:]] == [
        "Green", "Blue", "Black", "Double black", ""]


def test_a_status_is_carried_in_the_page_s_words():
    feed = bristol.parse(page(CLOSED, "<td class='avia-center-col'>OPEN</td>", 2), NOW)
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]][:3] == ["open", "open", "closed"]
    held = bristol.parse(page(CLOSED, "<td class='avia-center-col'>WIND HOLD</td>", 1), NOW)
    lift = held["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Comet Express Quad", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not a word"):
        bristol.parse(page(CLOSED, "<td class='avia-center-col'></td>", 1), NOW)
    with pytest.raises(ValueError, match="is not one the reader knows"):
        bristol.parse(page("/> More Difficult</h3>", "/> Harder</h3>"), NOW)
    with pytest.raises(ValueError, match="is not one the reader knows"):
        bristol.parse(page(">Surface Conditions</span>", ">Snow</span>", 1), NOW)
    with pytest.raises(ValueError, match="two tables of lifts, or two under one heading"):
        bristol.parse(page("/> More Difficult</h3>", "/> Easier</h3>"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        bristol.parse("<html><body>Page not found</body></html>", NOW)
