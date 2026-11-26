from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import pajarito

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "pajarito.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_each_trail_once_under_the_first_lift_that_serves_it():
    # Pajarito's page on 2026-11-26, the day before it opens: six lifts and 57 trails, all closed.
    feed = pajarito.parse(PAGE, NOW)
    assert feed["Name"] == "Pajarito" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    # The page lists 73 trail rows; 16 are trails listed again under a second lift.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Pajarito", 6, 0), ("Spruce", 0, 9), ("Mother", 0, 24), ("Beginner", 0, 5), ("Aspen", 0, 9),
        ("Townsight", 0, 9), ("Magic Carpet", 0, 1)]
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Spruce", "Mother", "Beginner", "Aspen", "Townsight", "Magic Carpet"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 63 and {row["StatusEnglish"] for row in rows} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 57 == len({trail["Name"] for trail in trails})
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    assert {trail["Grooming"] for trail in trails} == {"No"}


def test_the_snow_figures_the_resort_leaves_empty_stay_empty():
    snow = pajarito.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    # The page also has a 5 day figure, which the feed has no name for.
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": None, "Last48HoursIn": None,
                                "Last72HoursIn": None, "BaseIn": 12}
    assert snow["SeasonTotalIn"] == 7


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = changed('<li class="m-lift-status-closed">', '<li class="m-lift-status-open-as-needed">', 1)
    page = page.replace('m-status m-margin-bottom m-status-closed">Closed<',
                        'm-status m-margin-bottom m-status-open-as-needed">Open as needed<', 1)
    lift = pajarito.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Spruce", "Open as needed", "open as needed")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts was not found"):
        pajarito.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="the page lists a lift twice"):
        pajarito.parse(changed('m-lift-header">Mother</h3>', 'm-lift-header">Spruce</h3>', 1), NOW)
    with pytest.raises(ValueError, match="74 trail rows but 73 were read"):
        pajarito.parse(changed("<main ", "<li class=\"m-filter-target\"></li><main "), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        pajarito.parse(changed('<li class="m-accordion">', '<li class="m-group">'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = pajarito.parse(changed("12&#8243;", "a foot"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
    assert "SnowReport" not in pajarito.parse(changed("5 Day", "Storm"), NOW)
