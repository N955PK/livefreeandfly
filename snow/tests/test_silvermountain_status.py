from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import silvermountain

# The pages with their scripts, styles, drawings, headers and footers taken out; the reader gives the same on the
# whole pages.
FIXTURES = Path(__file__).parent / "fixtures"
LIFTS = (FIXTURES / "silvermountain_lifts.html").read_text()
SNOW = (FIXTURES / "silvermountain_snow.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
LIFT_CLOSED = '<span class="brxe-ah8ye6 brxe-text-basic status-badge" data-status="closed">Closed</span>'
TRAIL_CLOSED = '<span class="brxe-chzcdf brxe-text-basic status-badge" data-status="closed">Closed</span>'


def read(lifts: str = LIFTS, snow: str = SNOW) -> dict:
    return silvermountain.parse({"lifts": lifts, "snow": snow}, NOW)


def changed(page: str, old: str, new: str, count: int = -1) -> str:
    assert old in page
    return page.replace(old, new, count)


def test_the_preseason_mountain_reads_each_lift_with_the_trails_under_it():
    # Silver Mountain's trail status on 2026-11-26, before opening: six lifts and 82 trails, all closed.
    feed = read()
    assert feed["Name"] == "Silver Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Chair 1", "Closed", 7), ("Chair 2", "Closed", 29), ("Chair 3", "Closed", 6), ("Chair 4", "Closed", 31),
        ("Chair 5", "Closed", 7), ("Prospector Adventure", "Closed", 2)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Chair 1", "Status": "Closed", "StatusEnglish": "closed",
                                                  "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 82 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Alpenway"] == {"Name": "Alpenway", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Green"}
    assert (trails["Fast Eddy"]["Difficulty"], trails["Gem"]["Difficulty"]) == ("Blue", "Black")
    # An entity in a name is read, and a terrain park has no difficulty.
    assert trails["Hammy’s Delight"]["Difficulty"] == "Blue" and trails["Main Terrain Park"]["Difficulty"] == ""
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black", "")] == [10, 34, 27, 9, 2]


def test_the_snow_report_gives_the_summit_and_is_undated():
    snow = read()["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True and "BaseArea" not in snow
    assert snow["SummitArea"] == {"Name": "Summit", "Last24HoursIn": 0, "Last48HoursIn": 0, "BaseIn": 6}
    assert snow["SeasonTotalIn"] == 9 and snow["BaseConditions"] == "Spring Conditions"


def test_an_open_lift_and_an_open_trail_are_read():
    lifts = changed(LIFTS, LIFT_CLOSED, LIFT_CLOSED.replace("closed", "open").replace("Closed", "Open"), 1)
    lifts = changed(lifts, TRAIL_CLOSED, TRAIL_CLOSED.replace("closed", "open").replace("Closed", "Open"), 2)
    areas = read(lifts)["MountainAreas"]
    assert areas[0]["Lifts"][0] == {"Name": "Chair 1", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert [trail["StatusEnglish"] for trail in areas[0]["Trails"][:3]] == ["open", "open", "closed"]
    assert areas[1]["Lifts"][0]["StatusEnglish"] == "closed"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    held = LIFT_CLOSED.replace('"closed"', '"wind-hold"').replace("Closed", "Wind Hold")
    lifts = changed(LIFTS, LIFT_CLOSED, held, 1)
    lift = read(lifts)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Chair 1", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Chair 1 is marked shut but reads 'Closed'"):
        read(changed(LIFTS, LIFT_CLOSED, LIFT_CLOSED.replace('"closed"', '"shut"'), 1))
    with pytest.raises(ValueError, match="Alpenway has a difficulty sign the reader does not know: orange"):
        read(changed(LIFTS, 'data-sign="easy"', 'data-sign="orange"', 1))
    with pytest.raises(ValueError, match="not a name, a difficulty sign and a status"):
        read(changed(LIFTS, "status-list__row-name", "status-list__title", 1))
    with pytest.raises(ValueError, match="does not begin with its name and its status"):
        read(changed(LIFTS, "status-list__name", "status-list__title", 1))
    with pytest.raises(ValueError, match="6 lifts and 82 trail rows but 5 and 75"):
        read(changed(LIFTS, "<details ", "<section ", 1))
    with pytest.raises(ValueError, match="0 lifts and 0 trail rows"):
        read("<html><body>Not the page</body></html>")


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = read(snow=changed(SNOW, '<p class="brxe-text-basic stat-tile__value">6 in.</p>',
                             '<p class="brxe-text-basic stat-tile__value">deep</p>'))
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
    assert "SnowReport" not in read(snow=changed(SNOW, "Summit Snow Depth", "Snow Stake"))
    assert "SnowReport" not in read(snow="<html><body>Not the page</body></html>")
