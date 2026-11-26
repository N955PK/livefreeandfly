import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import boynemountain

# The report as the site gave it on 2026-11-26, before the mountain opens.
PAGE = (Path(__file__).parent / "fixtures" / "boynemountain.json").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(change) -> str:
    report = json.loads(PAGE)
    change(report)
    return json.dumps(report)


def areas_of(report: dict) -> list:
    return report["facilities"]["areas"]["area"]


def test_the_report_is_read_from_boyne_mountain_s_own_site_by_the_code_its_page_names():
    assert boynemountain.URL == "https://www.boynemountain.com/api/reportpal?resortName=bm&useReportPal=true"


def test_the_closed_mountain_reads_its_lifts_and_trails_as_one_area():
    # Ten lifts and 65 trails, all closed.
    feed = boynemountain.parse(PAGE, NOW)
    assert feed["Name"] == "Boyne Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Boyne Mountain", 10, 65)]
    area = feed["MountainAreas"][0]
    assert [lift["Name"] for lift in area["Lifts"]] == [
        "Alpine", "Boyneland", "Disciples 8", "Hemlock", "Estelle's Way", "Meadows", "Mountain Express", "Ramshead",
        "Superbowl", "Victor"]
    assert area["Lifts"][2] == {"Name": "Disciples 8", "Status": "Closed", "StatusEnglish": "closed",
                                "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Audie's Alley", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Green", "Grooming": "Yes"}
    assert {row["StatusEnglish"] for row in area["Lifts"] + area["Trails"]} == {"closed"}
    count = {}
    for trail in area["Trails"]:
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 31, "Blue": 18, "Black": 14, "Double black": 2}


def test_the_snow_report_gives_the_depth_the_snowfall_and_when_it_was_posted():
    snow = boynemountain.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-25T15:08:30Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 20, "BaseMinIn": 20, "BaseMaxIn": 20, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 0, "Last7DaysIn": 0}
    # The surface and the season's total are what the report says, though they read as last season's.
    assert snow["BaseConditions"] == "Machine Groomed, Spring Conditions" and snow["SeasonTotalIn"] == 105
    assert "snowmaking" in snow["Report"] and snow["Alert"] is None


def test_a_lift_on_hold_and_an_open_ungroomed_trail_take_the_report_s_words():
    def turn(report):
        areas_of(report)[0]["lifts"]["lift"][0]["status"] = "On Hold"
        areas_of(report)[0]["trails"]["trail"][0].update(status="Open", groomed=False)
    area = boynemountain.parse(changed(turn), NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Alpine", "Status": "On hold", "StatusEnglish": "on hold", "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Audie's Alley", "Status": "Open", "StatusEnglish": "open",
                                 "Difficulty": "Green", "Grooming": "No"}


def test_a_report_with_no_snow_location_has_no_snow_report_but_keeps_its_lifts():
    feed = boynemountain.parse(
        changed(lambda report: report["currentConditions"]["resortLocations"].update(location=[])), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 10


def test_a_report_that_is_missing_or_changed_is_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        boynemountain.parse("<html>", NOW)
    with pytest.raises(ValueError, match="not Boyne Mountain's"):
        boynemountain.parse("[]", NOW)
    with pytest.raises(ValueError, match="not Boyne Mountain's"):
        boynemountain.parse(changed(lambda report: report.update(name="Boyne Highlands")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        boynemountain.parse(changed(lambda report: report.pop("facilities")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        boynemountain.parse(changed(lambda report: areas_of(report)[0]["lifts"]["lift"][0].pop("status")), NOW)
    with pytest.raises(ValueError, match="rating the reader does not know: extreme"):
        boynemountain.parse(
            changed(lambda report: areas_of(report)[0]["trails"]["trail"][0].update(difficultyIcon="extreme")), NOW)
    with pytest.raises(ValueError, match="counts 11 lifts but 10"):
        boynemountain.parse(
            changed(lambda report: report["currentConditions"]["resortwide"].update(numLiftsTotal=11)), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        boynemountain.parse(changed(lambda report: [area.update(lifts=None) for area in areas_of(report)]), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        boynemountain.parse(changed(lambda report: [area.update(trails=None) for area in areas_of(report)]), NOW)
