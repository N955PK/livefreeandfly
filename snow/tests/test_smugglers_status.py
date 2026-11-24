from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import smugglers

# The page's main element as read on 2026-11-24, without its scripts, styles and drawings.
PAGE = (Path(__file__).parent / "fixtures" / "smugglers.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_eight_closed_lifts_and_the_trails_by_mountain():
    # Smugglers' Notch's report before it opened: every lift and trail closed; uphill access is not an area.
    feed = smugglers.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Morse", 4, 18), ("Sterling", 2, 32), ("Madonna", 2, 33)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert lifts["Madonna I Lift"] == {"Name": "Madonna I Lift", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": None}
    assert "Sterling T-Bar Lift" in lifts and "Village Lift" in lifts
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Curley's Cutback", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": "Green"}
    assert {trail["Difficulty"] for area in feed["MountainAreas"] for trail in area["Trails"]} == {
        "Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_carries_the_depths_the_surfaces_the_message_and_the_time_it_was_posted():
    snow = smugglers.parse(PAGE, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0, "NaturalIn": 0, "Last24HoursIn": 0}
    assert snow["LastUpdate"] == "2026-11-13T15:27:00Z" and snow["SeasonTotalIn"] == 0
    assert snow["BaseConditions"] == "Machine Groomed, Variable Conditions"
    assert snow["Report"].startswith("Madonna & Sterling Mountain are closed to uphill access")
    page = PAGE.replace("Man-Made Snow Depth: 0&#8243;", "Man-Made Snow Depth: 24&#8243;")
    assert smugglers.parse(page, NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 24


def test_an_open_status_and_a_groomed_condition_read():
    row = PAGE[PAGE.index('<tr class="facility-report_item"'):PAGE.index("</tr>", PAGE.index('<tr class="facility-report_item"'))]
    row = row.replace('--status --closed" title="Closed"', '--status --open" title="Open"')
    row = row.replace('<td class="facility-report_condition">', '<td class="facility-report_condition"><span title="Groomed">')
    assert smugglers.table_row(row, True) == {"Name": "Curley's Cutback", "Status": "Open", "StatusEnglish": "open",
                                              "Difficulty": "Green", "Grooming": "Yes"}


def test_a_page_whose_counts_do_not_add_up_or_whose_depth_does_not_read_is_refused():
    with pytest.raises(ValueError, match="counts 8 lifts and 78 trails but 7 and 78"):
        smugglers.parse(remove_row(PAGE, "Madonna II Lift"), NOW)
    with pytest.raises(ValueError, match="does not read as inches"):
        smugglers.parse(PAGE.replace("Natural Snow Depth: 0&#8243;", "Natural Snow Depth: a dusting"), NOW)
    with pytest.raises(ValueError, match="lift tables"):
        smugglers.parse(PAGE.replace('<table class="facility-table">', '<table class="report">'), NOW)


def remove_row(page: str, name: str) -> str:
    start = page.rindex('<tr class="facility-report_item"', 0, page.index(name))
    return page[:start] + page[page.index("</tr>", start) + 5:]
