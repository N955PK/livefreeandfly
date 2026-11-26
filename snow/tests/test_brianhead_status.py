from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import brianhead

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "brianhead.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_page_is_brian_head_s_conditions_page():
    assert brianhead.URL == "https://www.brianhead.com/weather-conditions-webcams/"


def test_the_early_season_mountain_reads_its_lifts_and_its_trails_by_chair():
    # Brian Head's page on Thanksgiving 2026: eight lifts with three turning, 73 trails with 24 open.
    feed = brianhead.parse(PAGE, NOW)
    assert feed["Name"] == "Brian Head" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Brian Head", 8, 0), ("Wildflower, Chair 1", 0, 11), ("Giant Steps Express, Chair 2", 0, 17),
        ("Blackfoot, Chair 3", 0, 6), ("Navajo Express, Chair 4", 0, 10), ("Roulette, Chair 5", 0, 10),
        ("Pioneer, Chair 6", 0, 3), ("The Dunes, Chair 7", 0, 13), ("Alpen Glow, Chair 8", 0, 3)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Wildflower, Chair 1", "open"), ("Giant Steps Express, Chair 2", "closed"), ("Blackfoot, Chair 3", "closed"),
        ("Navajo Express, Chair 4", "open"), ("Roulette, Chair 5", "closed"), ("Pioneer, Chair 6", "open"),
        ("The Dunes, Chair 7", "closed"), ("Alpen Glow, Chair 8", "closed")]
    assert lifts[0] == {"Name": "Wildflower, Chair 1", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Ute", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                         "Grooming": "Yes"}
    assert len(trails) == 73 and [trail["StatusEnglish"] for trail in trails].count("open") == 24
    assert {trail["StatusEnglish"] for trail in trails} == {"open", "closed"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    assert [trail["Grooming"] for trail in trails].count("Yes") == 15


def test_the_snow_figures_are_read_and_undated():
    snow = brianhead.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 23,
                                "BaseIn": 16}
    assert snow["SeasonTotalIn"] == 55 and snow["BaseConditions"] is None and snow["Report"] is None


def test_a_lift_whose_mark_and_words_disagree_is_refused():
    page = changed('<li class="m-lift-status-open">', '<li class="m-lift-status-closed">', 1)
    page = page.replace('m-status m-margin-bottom m-status-open">', 'm-status m-margin-bottom m-status-closed">', 1)
    with pytest.raises(ValueError, match="is marked closed but reads 'Open'"):
        brianhead.parse(page, NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts was not found"):
        brianhead.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="list of trails was not found"):
        brianhead.parse(changed('m-lifts-and-trails">', 'm-trails">'), NOW)
    with pytest.raises(ValueError, match="Ute has a difficulty the reader does not know: purple"):
        brianhead.parse(changed('m-status-blue">Ute<', 'm-status-purple">Ute<'), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        brianhead.parse("<html></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = brianhead.parse(changed("55”", "a lot"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 9
