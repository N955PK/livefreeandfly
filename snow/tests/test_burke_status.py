from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import burke

# The page's main element as read on 2026-11-24, without its scripts, styles and drawings.
PAGE = (Path(__file__).parent / "fixtures" / "burke.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
# A lift's closed icon; the trails' is written without the space.
CLOSED = '<span class="uk-text-danger uk-icon" uk-icon="icon: bootstrap-filled--x-square"></span>'


def test_the_closed_mountain_reads_as_five_closed_lifts_and_the_trails_glades_and_parks():
    # Burke's page before it opened: five lifts, all closed; the uphill routes are not the mountain's trails.
    feed = burke.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Burke Mountain", 5, 0), ("Trails", 0, 38), ("Glades", 0, 14), ("Terrain Parks", 0, 3)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Mid-Burke Express", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert [lift["Name"] for lift in lifts] == ["Mid-Burke Express", "Sherburne Express", "T-Bar", "J-Bar", "Magic Carpet"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    trails = {trail["Name"]: trail["Difficulty"] for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert (trails["High Meadows Pass"], trails["Powderhorn"], trails["Upper Warren's Way"], trails["Jester"]) == (
        "Green", "Blue", "Black", "")
    assert "Double black" in trails.values() and "Willoughby (Non-operational hours only)" not in trails


def test_the_snow_report_carries_the_snowmaking_depth_as_the_base_and_the_natural_range_beside_it():
    snow = burke.parse(PAGE, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 25, "BaseMinIn": 25, "BaseMaxIn": 25, "NaturalMinIn": 2,
                                "NaturalMaxIn": 8, "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 4,
                                "OvernightIn": 0}
    assert snow["BaseConditions"] == "Frozen granular, Loose granular" and snow["SeasonTotalIn"] == 173
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True


def test_a_range_whose_ends_differ_has_no_single_base_depth():
    area = burke.parse(PAGE.replace(" 25-25 ", " 18-30 "), NOW)["SnowReport"]["BaseArea"]
    assert (area["BaseIn"], area["BaseMinIn"], area["BaseMaxIn"]) == (None, 18, 30)
    with pytest.raises(ValueError, match="does not read as inches"):
        burke.parse(PAGE.replace(" 25-25 ", " deep "), NOW)


def test_green_and_amber_icons_read_as_open_and_on_hold_and_the_snowplough_is_not_a_status():
    assert CLOSED in PAGE
    page = PAGE.replace(CLOSED, CLOSED.replace("danger", "success").replace("x-square", "check-square"), 1)
    page = page.replace(CLOSED, CLOSED.replace("danger", "warning").replace("x-square", "exclamation-square"), 1)
    lifts = burke.parse(page, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts] == ["open", "on hold", "closed", "closed", "closed"]


def test_a_page_whose_lifts_do_not_add_up_or_whose_row_has_no_status_is_refused():
    with pytest.raises(ValueError, match="counts 6 lifts but 5"):
        burke.parse(PAGE.replace("0/5", "0/6"), NOW)
    with pytest.raises(ValueError, match="Mid-Burke Express on the page does not give one status"):
        burke.parse(PAGE.replace(CLOSED, "", 1), NOW)
    with pytest.raises(ValueError, match="lift table"):
        burke.parse(PAGE.replace(">Lift Name<", ">Name<"), NOW)
