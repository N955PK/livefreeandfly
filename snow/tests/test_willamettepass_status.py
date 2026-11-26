from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import willamettepass

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "willamettepass.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_its_trails_by_part_of_the_mountain():
    # Willamette Pass's page on 2026-11-26, before it opens: six lifts and 30 trails, all closed.
    feed = willamettepass.parse(PAGE, NOW)
    assert feed["Name"] == "Willamette Pass" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Willamette Pass", 6, 0), ("Frontside", 0, 21), ("Backside", 0, 8), ("Sleepy Hollow Beginner Area", 0, 1)]
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "The Magic Carpet (Conveyor)", "Sleepy Hollow", "Midway", "Twilight", "Eagle Peak Accelerator", "Peak 2"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 36 and {row["StatusEnglish"] for row in rows} == {"closed"}
    assert feed["MountainAreas"][0]["Lifts"][4] == {"Name": "Eagle Peak Accelerator", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}
    # The one trail of the beginner area is marked groomed though it is closed.
    assert [trail["Grooming"] for trail in trails].count("Yes") == 1
    assert feed["MountainAreas"][3]["Trails"][0]["Grooming"] == "Yes"


def test_the_snow_figures_are_read_and_undated():
    snow = willamettepass.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    # The row of figures also counts the open lifts and trails ("0/6", "0/30"), which are not snow.
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 7.5,
                                "BaseIn": 0}
    assert snow["SeasonTotalIn"] == 11.5


def test_an_open_lift_and_trail_read_as_open():
    page = changed('<li class="m-lift-status-closed">', '<li class="m-lift-status-open">', 1)
    page = page.replace('m-status m-margin-bottom m-status-closed">Closed<',
                        'm-status m-margin-bottom m-status-open">Open<', 1)
    lift = willamettepass.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("The Magic Carpet (Conveyor)", "Open", "open")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 7 lifts but 6 were read"):
        willamettepass.parse(changed("0/6", "0/7"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        willamettepass.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="list of trails was not found"):
        willamettepass.parse(changed('m-lifts-and-trails">', 'm-trails">'), NOW)
    with pytest.raises(ValueError, match="a group of trails has no name"):
        willamettepass.parse(changed('m-lift-header" role="button">Backside<', 'm-header" role="button">Backside<'),
                             NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = willamettepass.parse(changed("11.5”", "a foot"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
