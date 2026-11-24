from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import cannon

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "cannon.html").read_text()
MIDSEASON = (FIXTURES / "cannon_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 17, 30, tzinfo=timezone.utc)


def rows_of(feed: dict) -> list:
    return [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_part_of_the_mountain():
    # Cannon's report on 2026-11-24, before it opened: nine lifts and 102 listed trails, all closed, guns running.
    feed = cannon.parse(PAGE, NOW)
    assert feed["Name"] == "Cannon Mountain" and feed["LastUpdate"] == "2026-11-24T17:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Cannon Mountain", 9, 0), ("Upper Mountain", 0, 9), ("Tuckerbrook Family Area", 0, 12), ("Mid-Mountain", 0, 28),
        ("Front5", 0, 16), ("Mittersill", 0, 14), ("Glades", 0, 23)]
    assert {row["StatusEnglish"] for row in rows_of(feed)} == {"closed"} and all(row["Name"] for row in rows_of(feed))
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Cannonball Quad Chair"] == {"Name": "Cannonball Quad Chair", "Status": "Closed", "StatusEnglish": "closed",
                                              "Difficulty": None}
    assert lifts["Mittersill Double"]["Status"] == "Closed"
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "David's Detour", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Blue", "Grooming": "No"}


def test_before_the_season_the_snow_report_has_a_surface_and_a_season_total_and_no_depth():
    snow = cannon.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T14:48:12Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] == "Variable Conditions" and snow["SeasonTotalIn"] == 5
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": None, "Last24HoursMinIn": None, "Last24HoursMaxIn": None,
                                "Last48HoursIn": None}
    assert snow["Report"].startswith("<h3>The Window is Open")


def test_the_open_mountain_reads_open_lifts_groomed_runs_and_the_base_depth_as_a_range():
    # The page on 2026-02-22 (from the Internet Archive): everything open, base 34 to 68 in, 6 in in 48 hours.
    feed = cannon.parse(MIDSEASON, NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert len(lifts) == 9 and {lift["StatusEnglish"] for lift in lifts} == {"open"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 102 and {trail["StatusEnglish"] for trail in trails} == {"open"}
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 48
    snow = feed["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 51, "BaseMinIn": 34, "BaseMaxIn": 68, "Last24HoursIn": 0,
                                "Last24HoursMinIn": 0, "Last24HoursMaxIn": 0, "Last48HoursIn": 6}
    assert snow["BaseConditions"] == "Machine Groomed, Packed Powder" and snow["SeasonTotalIn"] == 167
    assert snow["LastUpdate"] == "2026-02-22T12:07:27Z"


def test_a_part_of_the_mountain_the_resort_has_shut_is_closed_whatever_its_trails_are_marked():
    page = MIDSEASON.replace('"toggleAllOverrideMittersill":false', '"toggleAllOverrideMittersill":true')
    areas = {area["Name"]: area for area in cannon.parse(page, NOW)["MountainAreas"]}
    assert {trail["StatusEnglish"] for trail in areas["Mittersill"]["Trails"]} == {"closed"}
    assert {trail["StatusEnglish"] for trail in areas["Front5"]["Trails"]} == {"open"}
    assert {lift["StatusEnglish"] for lift in areas["Cannon Mountain"]["Lifts"]} == {"open"}
    shut = cannon.parse(MIDSEASON.replace('"toggleAllOverride":false', '"toggleAllOverride":true'), NOW)
    assert {row["StatusEnglish"] for row in rows_of(shut)} == {"closed"}


def test_statuses_take_the_page_s_own_rule():
    assert cannon.status_of(["open"], False) == "Open" and cannon.status_of([], False) == "Closed"
    assert cannon.status_of(["snowmaking"], False) == "Closed" and cannon.status_of(["open"], True) == "Closed"
    assert cannon.status_of(["onHold"], False) == "On hold"
    assert cannon.status_of(["open", "pendingInspection"], False) == "Pending inspection"
    assert cannon.span([{"min": None, "max": 12}], "Base") == {"BaseIn": 12, "BaseMinIn": 12, "BaseMaxIn": 12}
    assert cannon.span([{"min": 3, "max": 4}], "Last24Hours")["Last24HoursIn"] == 3.5


def test_a_page_whose_data_is_missing_or_changed_is_refused():
    with pytest.raises(ValueError, match="data was not found"):
        cannon.parse(PAGE.replace('id="__NEXT_DATA__"', 'id="other"'), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        cannon.parse(PAGE.replace('"trailsLiftsEntries"', '"liftsEntries"'), NOW)
    with pytest.raises(ValueError, match="does not know"):
        cannon.parse(PAGE.replace('"gladesTrailsFieldEntries"', '"bowlsTrailsFieldEntries"'), NOW)
    with pytest.raises(ValueError, match="not a number"):
        cannon.parse(MIDSEASON.replace('"baseDepth":[{"min":34', '"baseDepth":[{"min":"deep"'), NOW)
