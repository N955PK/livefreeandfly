from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import alta

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "alta.html").read_text()
MIDSEASON = (FIXTURES / "alta_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_run_closed_by_lift():
    # Alta's page on 2026-11-24, before it opened: five lifts and 118 runs, all closed.
    feed = alta.parse(PAGE, NOW)
    assert feed["Name"] == "Alta" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    # A run two lifts serve is under the first of them, so the 118 are each counted once.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Sunnyside", 1, 11), ("Supreme", 1, 24), ("Sugarloaf", 1, 20), ("Collins", 1, 51), ("Wildcat", 1, 12)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"}
    assert feed["MountainAreas"][3]["Lifts"] == [{"Name": "Collins", "Status": "Closed", "StatusEnglish": "closed",
                                                  "Difficulty": None}]
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Patsey Marley", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green", "Grooming": "No"}


def test_the_snow_report_carries_the_depth_the_snowfall_and_when_it_was_measured():
    snow = alta.parse(PAGE, NOW)["SnowReport"]
    # 10:00 Mountain standard time.
    assert snow["LastUpdate"] == "2026-11-24T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 71
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 39, "Last12HoursIn": 0, "Last24HoursIn": 0, "StormTotalIn": 0}


def test_the_open_mountain_reads_open_lifts_groomed_runs_and_the_depth():
    # The page on 2026-02-12 (from the Internet Archive): every lift turning, 104 of 118 runs open.
    feed = alta.parse(MIDSEASON, NOW)
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert [lift["Name"] for lift in lifts] == ["Sunnyside", "Supreme", "Sugarloaf", "Collins", "Wildcat"]
    assert {lift["StatusEnglish"] for lift in lifts} == {"open"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 118 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 104
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 23
    snow = feed["SnowReport"]
    assert snow["LastUpdate"] == "2026-02-12T18:00:00Z" and snow["SeasonTotalIn"] == 154
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 67, "Last12HoursIn": 1, "Last24HoursIn": 4, "StormTotalIn": 11}


def test_figures_are_numbers_or_nothing():
    assert alta.figure("39.0") == 39 and alta.figure("2.5") == 2.5 and alta.figure(None) is None and alta.figure("") is None
    with pytest.raises(ValueError, match="not a number"):
        alta.figure("deep")
    with pytest.raises(ValueError, match="below nothing"):
        alta.figure("-1")


def test_a_page_whose_data_is_missing_or_changed_is_refused():
    with pytest.raises(ValueError, match="data was not found"):
        alta.parse(PAGE.replace("window.Alta =", "window.Other ="), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        alta.parse(PAGE.replace('"liftStatus"', '"lifts"'), NOW)
    with pytest.raises(ValueError, match="counts 6 lifts and 118 runs but 5 and 118"):
        alta.parse(PAGE.replace('"lifts":{"open":0,"total":5}', '"lifts":{"open":0,"total":6}'), NOW)
    with pytest.raises(ValueError, match="neither open nor closed"):
        alta.parse(PAGE.replace('"closing_at_formatted":"04:30 pm","open":false', '"closing_at_formatted":"04:30 pm","open":"hold"', 1),
                   NOW)
    with pytest.raises(ValueError, match="not a number"):
        alta.parse(PAGE.replace('"base_depth":"39.0"', '"base_depth":"deep"'), NOW)
