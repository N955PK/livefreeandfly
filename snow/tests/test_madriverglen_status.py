from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import madriverglen

PAGE = (Path(__file__).parent / "fixtures" / "madriverglen.html").read_text()
NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)
CROSS = '<img src="https://www.madriverglen.com/wp-content/themes/mrg-theme/img/cross.png" alt="" />'
CHECK = '<img src="https://www.madriverglen.com/wp-content/themes/mrg-theme/img/check.png" alt="" />'


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_chair():
    # Mad River Glen's page on 2026-11-24, before it opened: four chairs and a handle tow, all closed.
    feed = madriverglen.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mad River Glen", 5, 0), ("Upper Single Chair", 0, 12), ("Lower Single Chair", 0, 4), ("Lower Mountain", 0, 22),
        ("Upper Double Chair", 0, 10), ("Birdland Chair", 0, 5), ("Practice Slope Chair", 0, 6), ("Callie's Corner", 0, 1)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Single Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert [lift["Name"] for lift in lifts][1:] == ["Sunnyside Double Chair", "Birdland Double Chair",
                                                    "Practice Slope Chair", "Callie's Corner Handle Tow"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Antelope", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Blue", "Grooming": "No"}
    assert {trail["Difficulty"] for area in feed["MountainAreas"] for trail in area["Trails"]} == {"Green", "Blue", "Black"}


def test_the_snow_report_has_snowfall_and_surface_and_no_base_depth():
    snow = madriverglen.parse(PAGE, NOW)["SnowReport"]
    # Posted Tuesday November 24, 2026 5:00 AM, Eastern.
    assert snow == {"LastUpdate": "2026-11-24T10:00:00Z", "Resortwide": True, "BaseConditions": "Fall",
                    "SeasonTotalIn": 0, "SeasonTotalMinIn": 0, "SeasonTotalMaxIn": 0,
                    "BaseArea": {"Name": "Mountain", "Last24HoursIn": 0, "Last24HoursMinIn": 0, "Last24HoursMaxIn": 0}}
    assert "BaseIn" not in snow["BaseArea"]
    assert madriverglen.figures("Last24Hours", '3" - 5"') == {"Last24HoursIn": None, "Last24HoursMinIn": 3,
                                                              "Last24HoursMaxIn": 5}
    assert madriverglen.figures("Last24Hours", '0 - 0"')["Last24HoursIn"] == 0


def test_a_picture_that_is_not_a_cross_reads_as_open_and_a_second_one_as_groomed():
    page = PAGE.replace(f"<td>Single Chair</td>									  \n																  <td>\n																			{CROSS}",
                        f"<td>Single Chair</td>									  \n																  <td>\n																			{CHECK}")
    assert page != PAGE
    lifts = {lift["Name"]: lift for lift in madriverglen.parse(page, NOW)["MountainAreas"][0]["Lifts"]}
    assert lifts["Single Chair"]["StatusEnglish"] == "open" and lifts["Sunnyside Double Chair"]["StatusEnglish"] == "closed"
    trail = madriverglen.trail_row('<img src="http://www.madriverglen.com/images/greencircle.gif" /> Fox', CHECK, CHECK)
    assert trail == {"Name": "Fox", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"}


def test_a_page_whose_tables_or_rows_do_not_read_is_refused():
    with pytest.raises(ValueError, match="tables were not found"):
        madriverglen.parse(PAGE.replace("<h4>LIFTS</h4>", ""), NOW)
    with pytest.raises(ValueError, match="status pictures"):
        madriverglen.parse(PAGE.replace(CROSS, "", 1), NOW)
    with pytest.raises(ValueError, match="lists 60 trails but 59"):
        madriverglen.parse(PAGE.replace('<p class="open make_trans_cls" style="">' + CROSS + "</p>", CROSS, 1), NOW)


def test_a_snow_report_that_does_not_read_costs_only_the_snow_report():
    feed = madriverglen.parse(PAGE.replace("<p>Updated:", "<p>Posted:"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 5
