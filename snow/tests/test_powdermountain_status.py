import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import powdermountain

PAGE = (Path(__file__).parent / "fixtures" / "powdermountain.json").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(change) -> str:
    """The report with one change made to it."""
    report = json.loads(PAGE)
    change(report)
    return json.dumps(report)


def first_lift(report: dict) -> dict:
    return next(sector["lifts"][0] for sector in report["status"]["sectorsData"] if sector.get("lifts"))


def rows_of(feed: dict) -> list:
    return [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_part_of_the_mountain():
    # Powder Mountain's report on 2026-11-24, before it opened: eight lifts and 156 trails, all out of their season.
    feed = powdermountain.parse(PAGE, NOW)
    assert feed["Name"] == "Powder Mountain" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Adventure Terrain", 0, 6), ("Cobabe Canyon", 0, 22), ("DMI", 1, 21), ("Hidden Lake", 1, 15),
        ("James Peak", 0, 5), ("Lefty's Left", 0, 4), ("Lightning Ridge", 1, 18), ("Paradise", 1, 23),
        ("Powder Country", 0, 6), ("Sundown", 2, 8), ("Sunrise", 1, 9), ("Timberline", 1, 12), ("Woody's World", 0, 7)]
    assert {row["StatusEnglish"] for row in rows_of(feed)} == {"closed"} and all(row["Name"] for row in rows_of(feed))
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert len(lifts) == 8
    assert lifts["Hidden Lake Express"] == {"Name": "Hidden Lake Express", "Status": "Closed", "StatusEnglish": "closed",
                                            "Difficulty": None}
    assert lifts["Paradise Express"]["Status"] == "Closed" and lifts["Sun Tunnel"]["Status"] == "Closed"
    trails = {(area["Name"], trail["Name"]): trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert trails[("DMI", "Bill's Bowl")] == {"Name": "Bill's Bowl", "Status": "Closed", "StatusEnglish": "closed",
                                              "Difficulty": "Black"}
    # Grooming is carried only where the report says one way or the other.
    said = [trail.get("Grooming") for trail in trails.values()]
    assert (said.count("Yes"), said.count("No"), said.count(None)) == (27, 28, 101)


def test_the_snow_report_gives_the_plot_s_depth_and_snowfall_in_inches():
    snow = powdermountain.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-21T12:55:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 16, "OvernightIn": 0, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 0, "Last7DaysIn": 25}
    assert snow["SeasonTotalIn"] == 34 and snow["BaseConditions"] is None
    assert "opening day scheduled for Friday, December 11" in snow["Report"]


def test_statuses_take_the_words_of_the_resort_s_page():
    def turning(report):
        first_lift(report)["openingStatus"] = "OPEN"
        report["status"]["sectorsData"][1]["trails"][0].update(openingStatus="OPEN", groomingStatus="MORNING_GROOMED")
        report["status"]["sectorsData"][1]["trails"][1]["openingStatus"] = "FORECAST"
    feed = powdermountain.parse(changed(turning), NOW)
    assert next(lift for area in feed["MountainAreas"] for lift in area["Lifts"])["StatusEnglish"] == "open"
    first, second = feed["MountainAreas"][1]["Trails"][:2]
    assert (first["Status"], first["Grooming"], second["Status"]) == ("Open", "Yes", "Expected")
    row = powdermountain.status_row({"name": "A", "openingStatus": "STOPPED_WIND"}, None)
    assert (row["Status"], row["StatusEnglish"]) == ("On-hold Wind", "on-hold wind")
    assert powdermountain.status_row({"name": "A", "openingStatus": "OUT_OF_PERIOD_SEASON_ENDING"}, None)["Status"] == "Closed"
    assert powdermountain.status_row({"name": "A", "openingStatus": "NEW_CODE"}, None)["Status"] == "NEW_CODE"


def test_a_report_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no status by part"):
        powdermountain.parse(changed(lambda report: report.pop("status")), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        powdermountain.parse(changed(lambda report: first_lift(report).pop("openingStatus")), NOW)
    with pytest.raises(ValueError, match="does not know"):
        powdermountain.parse(changed(lambda report: report["status"]["sectorsData"][0]["trails"][0].update(
            trailLevel="ORANGE_OVAL")), NOW)
    with pytest.raises(ValueError, match="counts 6 lifts but 0"):
        powdermountain.parse(changed(lambda report: [sector.pop("lifts", None)
                                                     for sector in report["status"]["sectorsData"]]), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        powdermountain.parse(changed(lambda report: report["status"].pop("liftsOverall")), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(report):
        report["conditions"]["currentSnow"]["snowTotalDepth"]["countryUnit"] = "CENTIMETER"
    feed = powdermountain.parse(changed(metric), NOW)
    assert "SnowReport" not in feed and len(rows_of(feed)) == 164
    assert "SnowReport" not in powdermountain.parse(changed(lambda report: report["conditions"].pop("currentSnow")), NOW)
