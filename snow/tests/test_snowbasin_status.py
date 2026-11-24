from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import snowbasin

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles and drawings taken out; the reader gives the same on the whole page.
PAGE = (FIXTURES / "snowbasin.html").read_text()
MIDSEASON = (FIXTURES / "snowbasin_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def rows_of(feed: dict) -> list:
    return [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_part_of_the_mountain():
    # Snowbasin's report on 2026-11-24, three days before it opened: thirteen lifts and 139 listed trails, all closed.
    feed = snowbasin.parse(PAGE, NOW)
    assert feed["Name"] == "Snowbasin" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Snowbasin", 13, 0), ("Access Gates", 0, 18), ("John Paul", 0, 23), ("Needles", 0, 57), ("Porcupine", 0, 6),
        ("Strawberry", 0, 32), ("Terrain Parks", 0, 3)]
    assert {row["StatusEnglish"] for row in rows_of(feed)} == {"closed"} and all(row["Name"] for row in rows_of(feed))
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Needles Gondola"] == {"Name": "Needles Gondola", "Status": "Closed", "StatusEnglish": "closed",
                                        "Difficulty": None}
    assert lifts["John Paul Express"]["Status"] == "Closed" and lifts["Wildcat Handle Tow"]["Status"] == "Closed"
    areas = {area["Name"]: area["Trails"] for area in feed["MountainAreas"]}
    assert areas["Access Gates"][5] == {"Name": "Lower Sister's Gate", "Status": "Closed", "StatusEnglish": "closed",
                                        "Difficulty": "Black", "Grooming": "No"}
    assert areas["Needles"][0] == {"Name": "119", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Blue",
                                   "Grooming": "Yes"}
    assert areas["Terrain Parks"][0]["Name"] == "Blue Grouse" and areas["Terrain Parks"][0]["Difficulty"] == ""


def test_the_snow_report_gives_the_base_depth_and_when_it_was_posted():
    snow = snowbasin.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: Nov 24, 4:23 AM MT", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T11:23:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "OvernightIn": 0, "BaseIn": 21, "Last24HoursIn": 0,
                                "Last7DaysIn": 29}
    assert snow["SeasonTotalIn"] == 33 and snow["BaseConditions"] is None


def test_the_open_mountain_reads_open_lifts_and_groomed_runs():
    # The page on 2026-02-09 (from the Internet Archive): nine of thirteen lifts open, base 39 in.
    feed = snowbasin.parse(MIDSEASON, NOW)
    lifts = {lift["Name"]: lift["Status"] for lift in feed["MountainAreas"][0]["Lifts"]}
    assert len(lifts) == 13 and sum(status == "Open" for status in lifts.values()) == 9
    assert lifts["Needles Gondola"] == "Open" and lifts["John Paul Express"] == "Closed"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 139 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 79
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 28
    snow = feed["SnowReport"]
    # The page gives no year: February read in November is this year's February.
    assert snow["LastUpdate"] == "2026-02-09T11:19:00Z"
    assert snow["BaseArea"]["BaseIn"] == 39 and snow["SeasonTotalIn"] == 74


def test_a_report_dated_later_in_the_year_than_the_reading_is_last_year_s():
    snow = snowbasin.parse(PAGE, datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T11:23:00Z"


def test_the_other_status_symbols_take_the_words_of_the_page_s_key():
    row = "<td> Needles Gondola </td>"
    held = PAGE.replace(row + ' <td class="mc__table-cell mc__table-cell-svg"> <span class="mc__icon mc__icon-gondola">'
                        '&nbsp;</span> <span class="sr-only">Gondola</span> </td> <td class="mc__table-cell '
                        'mc__table-cell-svg"> <span class="mc__icon mc__icon-closed">',
                        row + ' <td class="mc__table-cell mc__table-cell-svg"> <span class="mc__icon mc__icon-gondola">'
                        '&nbsp;</span> <span class="sr-only">Gondola</span> </td> <td class="mc__table-cell '
                        'mc__table-cell-svg"> <span class="mc__icon mc__icon-hold">')
    assert held != PAGE
    lifts = {lift["Name"]: lift for lift in snowbasin.parse(held, NOW)["MountainAreas"][0]["Lifts"]}
    assert lifts["Needles Gondola"]["Status"] == "On hold" and lifts["Needles Gondola"]["StatusEnglish"] == "on hold"
    assert snowbasin.status_row("A", '<span class="mc__icon mc__icon-delayed"></span>', None)["Status"] == "Delayed"
    assert snowbasin.status_row("A", '<span class="mc__icon mc__icon-expected"></span>', "Blue")["Status"] == "Expected"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="table of lifts"):
        snowbasin.parse(PAGE.replace("mc-lifts__table", "lifts__table"), NOW)
    with pytest.raises(ValueError, match="not one the reader knows"):
        snowbasin.parse(PAGE.replace("mc__icon mc__icon-closed", "mc__icon mc__icon-shut"), NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        snowbasin.parse(PAGE.replace("mc__icon mc__icon-moderate", "mc__icon mc__icon-middling"), NOW)
    with pytest.raises(ValueError, match="counts 14 lifts but 13"):
        snowbasin.parse(PAGE.replace("0 / 13</span> Lifts Open", "0 / 14</span> Lifts Open"), NOW)
    with pytest.raises(ValueError, match="trails part"):
        snowbasin.parse(PAGE.replace('<div class="mc-trails">', '<div class="trails">'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = snowbasin.parse(PAGE.replace('<p class="mc__num mc__num-lg">21&#8221;</p>',
                                        '<p class="mc__num mc__num-lg">deep</p>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 13
    assert "SnowReport" not in snowbasin.parse(PAGE.replace("Last Updated:", "Posted:"), NOW)
