import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bigsky

# The report as the site gave it on the evening of 2026-11-25, its opening day.
PAGE = (Path(__file__).parent / "fixtures" / "bigsky.json").read_text()
NOW = datetime(2026, 11, 26, 1, 0, tzinfo=timezone.utc)


def changed(change) -> str:
    report = json.loads(PAGE)
    change(report)
    return json.dumps(report)


def areas_of(report: dict) -> list:
    return report["facilities"]["areas"]["area"]


def test_the_report_is_read_from_big_sky_s_own_site_by_the_code_its_page_names():
    assert bigsky.URL == "https://www.bigskyresort.com/api/reportpal?resortName=bs&useReportPal=true"


def test_the_opening_week_mountain_reads_its_lifts_and_trails_by_area():
    # 40 lifts with eight scheduled for the morning, 318 trails with eight open.
    feed = bigsky.parse(PAGE, NOW)
    assert feed["Name"] == "Big Sky" and feed["LastUpdate"] == "2026-11-26T01:00:00Z"
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert len(areas) == 22 == len(feed["MountainAreas"])
    assert [(name, len(area["Lifts"]), len(area["Trails"])) for name, area in areas.items()][:5] == [
        ("Cascade Area", 2, 2), ("Challenger Area", 1, 21), ("Dakota Area", 1, 12), ("Derringer Area", 5, 10),
        ("Explorer Area", 3, 17)]
    # The North Summit's trails are reached from the tram, which is listed under the Lone Peak area.
    assert areas["North Summit Area"]["Lifts"] == [] and len(areas["North Summit Area"]["Trails"]) == 12
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert len(lifts) == 40
    assert sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "scheduled") == [
        "Explorer Gondola", "First Light Carpet", "Lone Peak Tram", "Middle Basin Carpet", "Ramcharger 8",
        "Small Fry Carpet", "Sun Dog Carpet", "Swift Current 6"]
    assert lifts["Lone Peak Tram"] == {"Name": "Lone Peak Tram", "Status": "Scheduled", "StatusEnglish": "scheduled",
                                       "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts.values()} == {"scheduled", "closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 318
    assert sorted(trail["Name"] for trail in trails if trail["StatusEnglish"] == "open") == [
        "Ambush", "Hangman's", "Jay Walk", "Mountain Village Learning Area", "Mr. Ed", "Mr. K", "Old Tippy's",
        "Tippy's Tumble"]
    assert areas["Cascade Area"]["Trails"][0] == {"Name": "Middle River", "Status": "Closed", "StatusEnglish": "closed",
                                                  "Difficulty": "Green", "Grooming": "No"}
    # Six trails are given no status at all, which reads as closed.
    assert {trail["StatusEnglish"] for trail in trails} == {"open", "closed"}


def test_big_sky_s_six_ratings_are_carried_as_the_page_s_four():
    feed = bigsky.parse(PAGE, NOW)
    trails = {(area["Name"], trail["Name"]): trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    count = {}
    for trail in trails.values():
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 65, "Blue": 93, "Black": 100, "Double black": 60}
    # AZ Chutes is high exposure (a triple black) and Forbidden Forest advanced intermediate (a blue-black).
    assert trails[("Challenger Area", "AZ Chutes")]["Difficulty"] == "Double black"
    assert trails[("Explorer Area", "Forbidden Forest")]["Difficulty"] == "Blue"


def test_the_snow_report_gives_the_depth_the_snowfall_and_when_it_was_posted():
    snow = bigsky.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-26T00:00:03Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 17, "BaseMinIn": 17, "BaseMaxIn": 17, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 2, "Last7DaysIn": 13}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None and snow["Alert"] is None
    assert "Happy opening day" in snow["Report"]


def test_a_lift_on_hold_and_an_open_groomed_trail_take_the_report_s_words():
    def turn(report):
        areas_of(report)[0]["lifts"]["lift"][0]["status"] = "On Hold"
        areas_of(report)[0]["trails"]["trail"][0].update(status="Open", groomed=True)
    area = bigsky.parse(changed(turn), NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Cascade 3", "Status": "On hold", "StatusEnglish": "on hold", "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Middle River", "Status": "Open", "StatusEnglish": "open",
                                 "Difficulty": "Green", "Grooming": "Yes"}


def test_a_report_with_no_snow_location_has_no_snow_report_but_keeps_its_lifts():
    feed = bigsky.parse(changed(lambda report: report["currentConditions"]["resortLocations"].update(location=[])), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 22


def test_a_report_that_is_missing_or_changed_is_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        bigsky.parse("<html>", NOW)
    with pytest.raises(ValueError, match="not Big Sky's"):
        bigsky.parse("[]", NOW)
    with pytest.raises(ValueError, match="not Big Sky's"):
        bigsky.parse(changed(lambda report: report.update(name="Loon")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        bigsky.parse(changed(lambda report: report.pop("facilities")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        bigsky.parse(changed(lambda report: areas_of(report)[0]["lifts"]["lift"][0].pop("status")), NOW)
    with pytest.raises(ValueError, match="rating the reader does not know: extreme"):
        bigsky.parse(changed(lambda report: areas_of(report)[0]["trails"]["trail"][0].update(difficultyIcon="extreme")),
                     NOW)
    with pytest.raises(ValueError, match="counts 41 lifts but 40"):
        bigsky.parse(changed(lambda report: report["currentConditions"]["resortwide"].update(numLiftsTotal=41)), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        bigsky.parse(changed(lambda report: [area.update(lifts=None) for area in areas_of(report)]), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        bigsky.parse(changed(lambda report: [area.update(trails=None) for area in areas_of(report)]), NOW)
