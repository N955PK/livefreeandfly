import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import saddleback

FIXTURES = Path(__file__).parent / "fixtures"
# Saddleback's report on 2026-11-24, before it opened, and its mountain-report page of the same hour with its
# scripts, style sheets and drawings taken out (the day's words are all that is read from it).
REPORT = (FIXTURES / "saddleback.json").read_text()
PAGE = (FIXTURES / "saddleback.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(edit) -> str:
    report = json.loads(REPORT)
    edit(report["data"])
    return json.dumps(report)


def test_the_report_and_the_page_are_read_from_the_resort_s_own_addresses():
    assert saddleback.URLS == {"status": "https://saddlebackapi.netlify.app/.netlify/functions/getAll",
                               "snow": "https://www.saddlebackmaine.com/mountain-report/"}


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_difficulty():
    feed = saddleback.parse({"status": REPORT, "snow": PAGE}, NOW)
    assert feed["Name"] == "Saddleback" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Saddleback", 6, 0), ("Easier", 0, 24), ("More Difficult", 0, 29), ("Most Difficult", 0, 26),
        ("Experts Only", 0, 24), ("Terrain Parks", 0, 2)]
    # The report writes "Kennebago " and "Rangeley " with a space after them.
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Cupsuptic", "Kennebago", "Rangeley", "Sandy", "South Branch", "Molly Chunkamunk"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][0]["Lifts"][2] == {"Name": "Rangeley", "Status": "Closed", "StatusEnglish": "closed",
                                                    "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Lower Green Hornet", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": "Green", "Grooming": "No"}
    assert feed["MountainAreas"][4]["Trails"][0]["Difficulty"] == "Double black"


def test_uphill_routes_and_the_surface_entries_are_not_trails():
    names = {trail["Name"] for area in saddleback.parse({"status": REPORT}, NOW)["MountainAreas"] for trail in area["Trails"]}
    assert "The Judge-Lower" not in names and not names & set(saddleback.SURFACE_ROWS)


def test_statuses_and_grooming_are_read_as_the_resort_s_page_reads_them():
    def edit(data):
        data["lifts"]["rangeley "]["openingStatus"] = "OPEN"
        data["lifts"]["kennebago "]["openingStatus"] = "FORECAST"
        data["lifts"]["sandy "]["openingStatus"] = "STOPPED"
        data["lifts"]["cupsuptic"]["openingStatus"] = "CLOSED"
        data["trailsSorted"]["blueSquare"][0].update(openingStatus="OPEN", groomingStatus="GROOMED")

    feed = saddleback.parse({"status": changed(edit)}, NOW)
    lifts = {lift["Name"]: lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts == {"Cupsuptic": "closed", "Kennebago": "expected", "Rangeley": "open", "Sandy": "on hold",
                     "South Branch": "closed", "Molly Chunkamunk": "closed"}
    assert feed["MountainAreas"][2]["Trails"][0] == {"Name": "Blue Devil", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Blue", "Grooming": "Yes"}


def test_last_season_s_snow_figures_are_left_empty_and_the_day_s_words_are_the_page_s():
    # The report still held 30 in of base, last changed on 8 April; the page's words were posted at 11:45 am Eastern.
    snow = saddleback.parse({"status": REPORT, "snow": PAGE}, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T16:45:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": None, "Last48HoursIn": None,
                                "Last72HoursIn": None, "Last7DaysIn": None}
    assert snow["SeasonTotalIn"] is None and snow["BaseConditions"] is None
    assert snow["Report"].startswith("<p>Anyone see that white stuff") and "Opening day is December 4" in snow["Report"]
    assert "SnowReport" not in saddleback.parse({"status": REPORT}, NOW)


def test_fresh_snow_figures_are_carried_in_inches_with_the_surface():
    def edit(data):
        data["snow"].update(lastModified="2026-11-24T06:10:00.000-05:00", snowTotalDepth={"value": 18, "unit": "INCH"},
                            freshSnowFallDepth24H={"value": 3.5, "unit": "INCH"})
        data["snow"]["snowFallDepthCompleteSeason"].update(countryValue=12)
        data["trailsSorted"]["greenCircle"].append({"name": "PRIMARY SURFACE", "openingStatus": "OPEN", "snowQuality": "PACKED_POWDER"})
        data["trailsSorted"]["greenCircle"].append({"name": "SECONDARY SURFACE", "openingStatus": "OPEN", "snowQuality": "SNOW_GROOMED"})

    feed = saddleback.parse({"status": changed(edit)}, NOW)
    snow = feed["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T11:10:00Z" and snow["Report"] is None
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 18, "Last24HoursIn": 3.5, "Last48HoursIn": None,
                                "Last72HoursIn": None, "Last7DaysIn": None}
    assert snow["SeasonTotalIn"] == 12 and snow["BaseConditions"] == "Packed Powder, Machine Groomed"
    assert len(feed["MountainAreas"][1]["Trails"]) == 24


def test_a_report_whose_shape_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 7 lifts but 6"):
        saddleback.parse({"status": changed(lambda data: data["liftStatus"].update(totalLifts=7))}, NOW)
    with pytest.raises(ValueError, match="does not list: glades"):
        saddleback.parse({"status": changed(lambda data: data["trailsSorted"].update(glades=[]))}, NOW)
    with pytest.raises(ValueError, match="lifts were not found"):
        saddleback.parse({"status": json.dumps({"data": {}})}, NOW)

    def metric(data):
        data["snow"].update(lastModified="2026-11-24T06:10:00.000-05:00", snowTotalDepth={"value": 45, "unit": "CENTIMETER"})

    with pytest.raises(ValueError, match="not inches"):
        saddleback.parse({"status": changed(metric)}, NOW)
