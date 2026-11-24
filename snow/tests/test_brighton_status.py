import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import brighton

PAGE = (Path(__file__).parent / "fixtures" / "brighton.json").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def test_the_opening_mountain_reads_two_lifts_turning_and_the_trails_each_lift_serves():
    # Brighton's report on 2026-11-24, early season: two of eight lifts turning, 13 of 76 trails open.
    feed = brighton.parse(PAGE, NOW)
    assert feed["Name"] == "Brighton" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Caterpillar", 1, 0), ("Crest 6", 1, 8), ("Explorer", 1, 2), ("Great Western Express", 1, 14),
        ("Majestic", 1, 17), ("Milly Express", 1, 19), ("Porcupine", 1, 0), ("Snake Creek Express", 1, 16)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert len(lifts) == 8 and sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "open") == [
        "Explorer", "Majestic"]
    assert lifts["Majestic"] == {"Name": "Majestic", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert lifts["Milly Express"]["Status"] == "Closed"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 76 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 13
    assert feed["MountainAreas"][2]["Trails"][0] == {"Name": "Explorer Main", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Green", "Grooming": "Yes"}


def test_the_snow_report_carries_the_depth_the_snowfall_the_surface_and_when_it_was_posted():
    snow = brighton.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T16:00:02Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] == "Packed Powder, Powder" and snow["SeasonTotalIn"] == 77
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 28, "BaseMinIn": 28, "BaseMaxIn": 28, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 0, "Last7DaysIn": 55}


def test_a_report_that_is_not_brighton_s_or_has_changed_is_refused():
    report = json.loads(PAGE)
    with pytest.raises(ValueError, match="does not read as JSON"):
        brighton.parse("<html>", NOW)
    with pytest.raises(ValueError, match="not Brighton's"):
        brighton.parse(json.dumps({**report, "name": "Loon"}), NOW)
    with pytest.raises(ValueError, match="not inches"):
        brighton.parse(json.dumps({**report, "units": "metric"}), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        brighton.parse(json.dumps({**report, "facilities": {}}), NOW)
    report["currentConditions"]["resortwide"]["numLiftsTotal"] = 9
    with pytest.raises(ValueError, match="counts 9 lifts but 8"):
        brighton.parse(json.dumps(report), NOW)
