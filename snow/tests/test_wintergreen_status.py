from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import wintergreen

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "wintergreen.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
LIFT_CLOSED = "<td data-title=\"Status\" class=\"closed\">closed</td>"
BLANK = "<h6>Current Base</h6>\n <h3>”</h3>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_the_runs_under_each_lift():
    # Wintergreen's page on 2026-11-26, before it opened: six lifts and 27 runs, all closed, and blank snow figures.
    feed = wintergreen.parse(PAGE, NOW)
    assert feed["Name"] == "Wintergreen" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    # The tubing park's table is left out, which leaves the 27 runs the page itself counts.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Wintergreen", 6, 0), ("Potato Patch", 0, 1), ("Blue Ridge Express", 0, 6), ("Big Acorn", 0, 8),
        ("Highlands", 0, 10), ("Loggers Alley", 0, 2)]
    assert "0 of 27" in PAGE
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Big Acorn", "Potato Patch", "Blue Ridge Express", "Loggers Alley",
                                                "Highlands", "Teaching Conveyor"]
    assert lifts[0] == {"Name": "Big Acorn", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    levels = {trail["Name"]: trail["Difficulty"] for trail in trails}
    assert (levels["Potato Patch"], levels["Eagles Swoop"], levels["Cross Cut"], levels["Lower Cliffhanger"],
            levels["Terrain Park"]) == ("Green", "Blue", "Black", "Double black", "")
    assert "The Plunge Tubing Park" not in levels


def test_the_snow_report_and_an_open_lift_are_read_as_wisp_s_are():
    filled = page(BLANK, BLANK.replace("”", "30”")).replace(LIFT_CLOSED,
                                                             "<td data-title=\"Status\" class=\"open\">open</td>", 1)
    feed = wintergreen.parse(filled, NOW)
    assert feed["SnowReport"]["BaseArea"]["BaseIn"] == 30 and feed["SnowReport"]["LastUpdate"] is None
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]][:2] == ["open", "closed"]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="difficulty symbols \\['purple'\\]"):
        wintergreen.parse(page("/themes/pgri/images/doubleblack.svg", "/themes/pgri/images/purple.svg"), NOW)
    with pytest.raises(ValueError, match="The Plunge Tubing Park has difficulty symbols \\[\\]"):
        wintergreen.parse(page(">Tubing</h5>", ">The Plunge</h5>"), NOW)
    with pytest.raises(ValueError, match="the page's lifts were not found"):
        wintergreen.parse("<html><body>Page not found</body></html>", NOW)
