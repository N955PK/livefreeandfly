from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import brettonwoods

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "brettonwoods.html").read_text()
MIDSEASON = (FIXTURES / "brettonwoods_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 17, 30, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_part_of_the_mountain():
    # Bretton Woods' report on 2026-11-24, before it opened: eight lifts, 63 trails and 40 glades, all closed.
    feed = brettonwoods.parse(PAGE, NOW)
    assert feed["Name"] == "Bretton Woods" and feed["LastUpdate"] == "2026-11-24T17:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Bretton Woods", 8, 0), ("Mount Rosebrook", 0, 40), ("West Mountain", 0, 11), ("Zephyr Area", 0, 12),
        ("Mount Rosebrook Glades", 0, 19), ("Stickney System", 0, 5), ("West Mountain Glades", 0, 9), ("Zephyr Glades", 0, 7)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Bretton Woods Skyway Gondola"] == {"Name": "Bretton Woods Skyway Gondola", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": None}
    assert lifts["Zephyr High Speed Quad"]["Status"] == "Closed"
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Almost Home", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green", "Grooming": "No"}


def test_the_nordic_report_is_not_read():
    # The Nordic report has one trail open (Links Blue) and its own Stickney System of eleven trails.
    feed = brettonwoods.parse(PAGE, NOW)
    names = {row["Name"] for area in feed["MountainAreas"] for row in area["Trails"]}
    assert "Links Blue" not in names and "Ammonoosuc System" not in {area["Name"] for area in feed["MountainAreas"]}


def test_before_the_season_the_snow_report_has_the_season_s_snowfall_and_no_depth():
    snow = brettonwoods.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T15:00:00Z" and snow["BaseConditions"] is None
    assert snow["BaseArea"]["BaseIn"] is None and snow["BaseArea"]["RecentIn"] is None
    assert snow["BaseArea"]["SeasonTotalIn"] == 1
    # The upper mountain's season to date reads 1-3".
    assert (snow["SummitArea"]["SeasonTotalMinIn"], snow["SummitArea"]["SeasonTotalIn"], snow["SummitArea"]["SeasonTotalMaxIn"]) == (1, 2, 3)
    assert snow["Report"].startswith("<div><p>") and "Snowmakers" in snow["Report"]


def test_the_open_mountain_reads_open_lifts_groomed_runs_and_the_base_depth_as_a_range():
    # The page on 2026-02-16 (from the Internet Archive): nine lifts and every trail open, base 25-50 inches.
    feed = brettonwoods.parse(MIDSEASON, NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert len(lifts) == 9 and {lift["StatusEnglish"] for lift in lifts} == {"open"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 103 and {trail["StatusEnglish"] for trail in trails} == {"open"}
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 50
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    snow = feed["SnowReport"]
    assert (snow["BaseArea"]["BaseMinIn"], snow["BaseArea"]["BaseIn"], snow["BaseArea"]["BaseMaxIn"]) == (25, 37.5, 50)
    assert snow["BaseConditions"] == "Machine Groomed / Packed Powder" and snow["Resortwide"] is False
    assert snow["BaseArea"]["Name"] == "Mountain Base" and snow["SummitArea"]["Name"] == "Upper Mountain"
    assert (snow["BaseArea"]["RecentIn"], snow["BaseArea"]["SeasonTotalIn"]) == (0, 106)
    assert (snow["SummitArea"]["RecentIn"], snow["SummitArea"]["SeasonTotalIn"]) == (0, 144)
    # "Recent" is not said to be a day's snow, so it is not given as one.
    assert snow["BaseArea"]["Last24HoursIn"] is None
    # "Updated: 2/16 at 2pm", read in November: the February before, in the mountain's own time.
    assert snow["LastUpdate"] == "2026-02-16T19:00:00Z"


def test_a_report_posted_in_december_and_read_in_january_is_last_year_s():
    page = PAGE.replace("Updated: 11/24 at 10am", "Updated: 12/31 at 4:30pm")
    snow = brettonwoods.parse(page, datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-12-31T21:30:00Z"


def test_depths_read_as_one_figure_or_a_range_and_other_words_are_refused():
    assert brettonwoods.span('0"', "Recent") == {"RecentIn": 0, "RecentMinIn": 0, "RecentMaxIn": 0}
    assert brettonwoods.span("25-50 inches", "Base") == {"BaseIn": 37.5, "BaseMinIn": 25, "BaseMaxIn": 50}
    assert brettonwoods.span("", "Base") == {"BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None}
    with pytest.raises(ValueError, match="not a depth"):
        brettonwoods.span("a dusting", "Recent")


def test_a_page_whose_lists_do_not_add_up_is_refused():
    with pytest.raises(ValueError, match="Mount Rosebrook counts 40 but 39"):
        brettonwoods.parse(PAGE.replace('<div class="trail-reports__table-item--name">Almost Home</div>', "", 1)
                           .replace('data-status="closed"><div class="trail-reports__table-item-content"><div class="trail-reports__table-item--ability">',
                                    'data-state="closed"><div class="trail-reports__table-item-content"><div class="trail-reports__table-item--ability">', 1), NOW)
    with pytest.raises(ValueError, match="counts 9 lifts"):
        brettonwoods.parse(PAGE.replace('<div class="trail-reports__summary-item-count">0/8</div>',
                                        '<div class="trail-reports__summary-item-count">0/9</div>'), NOW)
    with pytest.raises(ValueError, match="alpine report"):
        brettonwoods.parse(PAGE.replace('id="alpine-report', 'id="downhill-report'), NOW)
    with pytest.raises(ValueError, match="posted"):
        brettonwoods.parse(PAGE.replace("Updated: 11/24 at 10am", "Updated: this morning"), NOW)
