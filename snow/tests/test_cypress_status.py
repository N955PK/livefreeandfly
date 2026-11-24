import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import cypress

# Cypress's report on 2026-11-24, before it opened: six lifts and 61 runs, all closed, and stakes nobody has read.
REPORT = json.loads((Path(__file__).parent / "fixtures" / "cypress.json").read_text())
NOW = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)


def parse(report: dict = REPORT) -> dict:
    return cypress.parse(json.dumps(report), NOW)


def changed() -> dict:
    return json.loads(json.dumps(REPORT))


def test_the_closed_mountain_reads_each_lift_with_the_runs_under_it():
    feed = parse()
    assert feed["Name"] == "Cypress Mountain" and feed["LastUpdate"] == "2026-11-25T00:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Eagle Express", 1, 13), ("Lions Express", 1, 24), ("Raven Ridge", 1, 13), ("Easy Rider", 1, 1),
        ("Sky Quad", 1, 6), ("Midway Chair", 1, 4)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert len(lifts) == 6 and {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    assert lifts[0] == {"Name": "Eagle Express", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert lifts[1]["Name"] == "Lions Express" and lifts[4]["Name"] == "Sky Quad"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # The Nordic area's 35 trails are left out.
    assert len(trails) == 61 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Panorama", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_dated_and_its_unread_stakes_read_zero():
    snow = parse()["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-19T23:04:32Z" and snow["Resortwide"] is False
    assert snow["BaseArea"]["Name"] == "Cypress Base" and snow["MidMountainArea"]["Name"] == "Mid Mountain"
    assert snow["BaseArea"]["BaseIn"] == 0 and snow["BaseArea"]["Last24HoursIn"] == 0
    assert snow["BaseConditions"] is None and snow["Report"].startswith("Mountain update: Cypress Mountain")


def test_centimetres_are_given_as_inches():
    report = changed()
    base, mid = report["currentConditions"]["resortLocations"]["location"][:2]
    base.update({"base": {"inches": "39", "centimeters": "100"}, "baseMin": {"inches": "31", "centimeters": "80"},
                 "baseMax": {"inches": "47", "centimeters": "120"}, "snow24Hours": {"inches": "5", "centimeters": "12"},
                 "snowSeasonTotal": {"inches": "118", "centimeters": "300"}, "primarySurface": "Powder",
                 "secondarySurface": "Packed Powder"})
    mid.update({"base": {"inches": "59", "centimeters": "150"}, "snow24Hours": None})
    snow = parse(report)["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] == 39.4 and snow["BaseArea"]["BaseMinIn"] == 31.5
    assert snow["BaseArea"]["BaseMaxIn"] == 47.2 and snow["BaseArea"]["Last24HoursIn"] == 4.7
    assert snow["MidMountainArea"]["BaseIn"] == 59.1 and snow["MidMountainArea"]["Last24HoursIn"] is None
    assert snow["SeasonTotalIn"] == 118.1 and snow["BaseConditions"] == "Powder, Packed Powder"


def test_an_open_lift_and_a_groomed_run_are_carried_in_the_report_s_words():
    report = changed()
    area = report["facilities"]["areas"]["area"][0]
    area["lifts"]["lift"][0]["status"] = "On Hold"
    area["trails"]["trail"][0].update({"status": "Open", "groomed": True})
    first = parse(report)["MountainAreas"][0]
    assert (first["Lifts"][0]["Status"], first["Lifts"][0]["StatusEnglish"]) == ("On hold", "on hold")
    assert first["Trails"][0]["StatusEnglish"] == "open" and first["Trails"][0]["Grooming"] == "Yes"


def test_a_report_that_has_changed_is_refused():
    report = changed()
    report["currentConditions"]["resortwide"]["numLiftsTotal"] = 7
    with pytest.raises(ValueError, match="counts 7 lifts but 6"):
        parse(report)
    report = changed()
    del report["facilities"]["areas"]
    with pytest.raises(ValueError, match="not in the shape"):
        parse(report)
    report = changed()
    report["facilities"]["areas"]["area"][0]["trails"]["trail"][0]["difficultyIcon"] = "hardest"
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        parse(report)
    with pytest.raises(ValueError):
        cypress.parse("<html>Just a moment...</html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    report = changed()
    report["units"] = "Imperial"
    feed = parse(report)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
    report = changed()
    report["currentConditions"]["resortLocations"]["location"][0]["base"]["centimeters"] = "deep"
    assert "SnowReport" not in parse(report)
    report = changed()
    report["updated"] = ""
    assert "SnowReport" not in parse(report)
