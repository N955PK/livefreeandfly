from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bolton

PAGE = (Path(__file__).parent / "fixtures" / "bolton.json").read_text()
NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed():
    # Bolton Valley's report on 2026-11-24, before it opened: six lifts and 71 trails, all closed.
    feed = bolton.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Bolton Valley", 6, 71)]
    area = feed["MountainAreas"][0]
    assert [lift["Name"] for lift in area["Lifts"]] == ["Mid Mountain", "Mighty Mite", "Snowflake", "Timberline", "Vista",
                                                        "Wilderness"]
    assert area["Lifts"][4] == {"Name": "Vista", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in area["Lifts"] + area["Trails"]} == {"closed"}
    trails = {trail["Name"]: trail for trail in area["Trails"]}
    assert trails["Abenaki Trail"] == {"Name": "Abenaki Trail", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Green", "Grooming": "No"}
    # A trail the report marks Groomed and Closed is closed, and groomed.
    assert trails["Bear Run"]["StatusEnglish"] == "closed" and trails["Bear Run"]["Grooming"] == "Yes"
    assert trails["Hide Away"]["Difficulty"] == ""


def test_the_snow_report_carries_the_depth_the_snowfall_and_when_it_was_posted():
    snow = bolton.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-23T22:14:00Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] == "Machine Groomed, Spring Conditions" and snow["SeasonTotalIn"] == 6
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0, "BaseMinIn": 0, "BaseMaxIn": 0, "Last24HoursIn": 0,
                                "Last24HoursMinIn": 0, "Last24HoursMaxIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 5,
                                "Last7DaysIn": 5}


def test_a_range_is_carried_as_its_two_ends_and_a_single_figure_only_where_they_agree():
    assert bolton.figures("Base", "12-24") == {"BaseIn": None, "BaseMinIn": 12, "BaseMaxIn": 24}
    assert bolton.figures("Base", "18-18") == {"BaseIn": 18, "BaseMinIn": 18, "BaseMaxIn": 18}
    assert bolton.figures("Last48Hours", "2.5") == {"Last48HoursIn": 2.5}
    assert bolton.figures("Last48Hours", "") == {"Last48HoursIn": None}
    with pytest.raises(ValueError, match="does not read"):
        bolton.figures("Base", "a few")


def test_an_open_lift_and_a_lift_on_hold_take_the_report_s_words():
    page = PAGE.replace('"name": "Vista",\n\t\t\t\t\t\t"type": "Quad",\n\t\t\t\t\t\t"statuses": [                                                    "Closed"',
                        '"name": "Vista",\n\t\t\t\t\t\t"type": "Quad",\n\t\t\t\t\t\t"statuses": [                                                    "Open"')
    assert page != PAGE
    lifts = {lift["Name"]: lift for lift in bolton.parse(page, NOW)["MountainAreas"][0]["Lifts"]}
    assert lifts["Vista"]["StatusEnglish"] == "open" and lifts["Timberline"]["StatusEnglish"] == "closed"
    assert bolton.status_row("Lift", ["Wind Hold"], None)["StatusEnglish"] == "wind hold"


def test_a_report_that_does_not_add_up_or_has_no_clear_status_is_refused():
    with pytest.raises(ValueError, match="counts 7 lifts but 6"):
        bolton.parse(PAGE.replace('"maxOpenDownHillLifts": "6"', '"maxOpenDownHillLifts": "7"'), NOW)
    with pytest.raises(ValueError, match="not one that says open or closed"):
        bolton.status_row("Lift", ["Groomed"], None)
    with pytest.raises(ValueError, match="no facilities"):
        bolton.parse('{"report": {}}', NOW)
