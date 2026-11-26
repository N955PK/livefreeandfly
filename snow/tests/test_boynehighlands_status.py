import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import boynehighlands

# The report as the site gave it on 2026-11-26, before the mountain opens.
PAGE = (Path(__file__).parent / "fixtures" / "boynehighlands.json").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(change) -> str:
    report = json.loads(PAGE)
    change(report)
    return json.dumps(report)


def areas_of(report: dict) -> list:
    return report["facilities"]["areas"]["area"]


def test_the_report_is_read_from_the_highlands_own_site_by_the_code_its_page_names():
    assert boynehighlands.URL == ("https://www.highlandsharborsprings.com/api/reportpal?resortName=th"
                                  "&useReportPal=true")


def test_the_closed_mountain_reads_its_lifts_and_trails_as_one_area_under_its_new_name():
    # Eight lifts and 55 trails, all closed; the report still calls itself and its area Boyne Highlands.
    feed = boynehighlands.parse(PAGE, NOW)
    assert feed["Name"] == "The Highlands" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("The Highlands", 8, 55)]
    area = feed["MountainAreas"][0]
    assert [lift["Name"] for lift in area["Lifts"]] == [
        "Amy's", "Camelot 6", "Challenger", "Heather Express", "Interconnect", "Magic Carpet", "North Face",
        "Renate's Express"]
    assert area["Lifts"][1] == {"Name": "Camelot 6", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Ablaze", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Green", "Grooming": "No"}
    assert {row["StatusEnglish"] for row in area["Lifts"] + area["Trails"]} == {"closed"}
    count = {}
    for trail in area["Trails"]:
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 22, "Blue": 16, "Black": 16, "Double black": 1}


def test_the_snow_report_gives_the_depth_the_snowfall_and_when_it_was_posted():
    snow = boynehighlands.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-25T20:23:25Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0, "BaseMinIn": 0, "BaseMaxIn": 0, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 0, "Last7DaysIn": 0}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 0 and snow["Alert"] is None
    assert "Closed for the Season" in snow["Report"]


def test_an_open_lift_and_an_open_groomed_trail_take_the_report_s_words():
    def turn(report):
        areas_of(report)[0]["lifts"]["lift"][0]["status"] = "Open"
        areas_of(report)[0]["trails"]["trail"][0].update(status="Open", groomed=True)
    area = boynehighlands.parse(changed(turn), NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Amy's", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Ablaze", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                                 "Grooming": "Yes"}


def test_a_report_with_no_snow_location_has_no_snow_report_but_keeps_its_lifts():
    feed = boynehighlands.parse(
        changed(lambda report: report["currentConditions"]["resortLocations"].update(location=[])), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 8


def test_a_report_that_is_missing_or_changed_is_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        boynehighlands.parse("<html>", NOW)
    with pytest.raises(ValueError, match="not The Highlands's"):
        boynehighlands.parse("[]", NOW)
    with pytest.raises(ValueError, match="not The Highlands's"):
        boynehighlands.parse(changed(lambda report: report.update(name="Boyne Mountain")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        boynehighlands.parse(changed(lambda report: report.pop("facilities")), NOW)
    with pytest.raises(ValueError, match="rating the reader does not know: extreme"):
        boynehighlands.parse(
            changed(lambda report: areas_of(report)[0]["trails"]["trail"][0].update(difficultyIcon="extreme")), NOW)
    with pytest.raises(ValueError, match="counts 9 lifts but 8"):
        boynehighlands.parse(
            changed(lambda report: report["currentConditions"]["resortwide"].update(numLiftsTotal=9)), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        boynehighlands.parse(changed(lambda report: [area.update(lifts=None) for area in areas_of(report)]), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        boynehighlands.parse(changed(lambda report: [area.update(trails=None) for area in areas_of(report)]), NOW)
