from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import cranmore

FIXTURES = Path(__file__).parent / "fixtures"
# Cranmore's page on 2026-11-24, before it opened, and on 2026-02-11 (from the Internet Archive), in mid-season.
PAGE = (FIXTURES / "cranmore.html").read_text()
WINTER = (FIXTURES / "cranmore_winter.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def lifts_of(feed: dict) -> dict:
    return {lift["Name"]: lift["StatusEnglish"] for area in feed["MountainAreas"] for lift in area["Lifts"]}


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_kind():
    feed = cranmore.parse(PAGE, NOW)
    assert feed["Name"] == "Cranmore" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Cranmore", 7, 0), ("Beginner", 0, 18), ("Intermediate", 0, 27), ("Expert", 0, 8), ("Glades", 0, 10),
        ("Terrain Parks", 0, 4)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "C-More Double", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][1] == {"Name": "C-More's Return", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": "Green", "Grooming": "No"}


def test_the_tubing_park_and_the_rides_are_not_lifts():
    assert not {"Tubing Park", "Mountain Coaster", "Giant Swing", "Soaring Eagle"} & set(lifts_of(cranmore.parse(WINTER, NOW)))


def test_before_the_season_the_snow_report_has_the_resort_s_words_and_no_figures():
    snow = cranmore.parse(PAGE, NOW)["SnowReport"]
    # The page dates its report by the day only: noon Eastern.
    assert snow["LastUpdate"] == "2026-11-20T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": None, "OvernightIn": None, "Last7DaysIn": None}
    assert snow["SeasonTotalIn"] is None and "closer to winter" in snow["Report"]


def test_the_open_mountain_reads_its_lifts_its_trails_and_its_grooming():
    feed = cranmore.parse(WINTER, NOW)
    assert lifts_of(feed) == {"C-More Double": "open", "Flying Carpet": "closed", "Lookout Triple": "closed",
                              "Magic Carpet": "open", "Schneider Triple": "closed", "Skimobile Express": "open",
                              "South Quad": "open"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 67 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 60
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 50
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", ""}


def test_a_base_depth_given_as_a_range_is_carried_as_its_least_and_most():
    snow = cranmore.parse(WINTER, NOW)["SnowReport"]
    # The page said: Base Depth 26-40", Overnight 4", 7 Day Total 5", Season Total 63".
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 33, "BaseMinIn": 26, "BaseMaxIn": 40,
                                "Last24HoursIn": 4, "OvernightIn": 4, "Last7DaysIn": 5}
    assert snow["SeasonTotalIn"] == 63 and snow["LastUpdate"] == "2026-02-11T17:00:00Z"
    assert cranmore.depth('30"') == (30, None, None) and cranmore.depth("1.5\"") == (1.5, None, None)
    assert cranmore.depth("Trace") == (None, None, None) and cranmore.depth("") == (None, None, None)


def test_a_page_whose_rows_do_not_all_read_is_refused():
    with pytest.raises(ValueError, match="counts 8 lifts but 7"):
        cranmore.parse(PAGE.replace('<span class="value">0/7</span>', '<span class="value">0/8</span>'), NOW)
    with pytest.raises(ValueError, match="7 lift rows but 6"):
        cranmore.parse(PAGE.replace('<div class="col">South Quad</div>', '<div class="name">South Quad</div>'), NOW)
    with pytest.raises(ValueError, match="67 trail rows but 66"):
        cranmore.parse(PAGE.replace('<div class="col">Chinstrap</div>', '<div class="name">Chinstrap</div>'), NOW)
    with pytest.raises(ValueError, match="tables were not found"):
        cranmore.parse(PAGE.replace("<h2>Lifts</h2>", ""), NOW)
