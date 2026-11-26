from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import azsnowbowl

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "azsnowbowl.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_page_is_arizona_snowbowl_s_conditions_page():
    assert azsnowbowl.URL == "https://www.snowbowl.ski/the-mountain/weather-conditions-webcams/"


def test_the_early_season_mountain_reads_its_lifts_and_its_trails_by_lift():
    # Arizona Snowbowl's page on Thanksgiving 2026: nine lifts with four turning, 61 trails with 11 open.
    feed = azsnowbowl.parse(PAGE, NOW)
    assert feed["Name"] == "Arizona Snowbowl" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Arizona Snowbowl", 9, 0), ("Arizona Gondola", 0, 17), ("Grand Canyon Express", 0, 19),
        ("Little Spruce", 0, 1), ("Big Spruce", 0, 1), ("Sunset", 0, 4), ("Hart Prairie", 0, 4),
        ("Humphrey’s Peak", 0, 10), ("Aspen", 0, 5)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Arizona Gondola", "open"), ("Grand Canyon Express", "open"), ("Little Spruce", "open"),
        ("Big Spruce", "open"), ("Sunset", "closed"), ("Hart Prairie", "closed"), ("Humphrey’s Peak", "closed"),
        ("Aspen", "closed"), ("Sunshine", "closed")]
    assert lifts[0] == {"Name": "Arizona Gondola", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Spur Catwalk", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Black",
                         "Grooming": "Yes"}
    assert sorted(trail["Name"] for trail in trails if trail["StatusEnglish"] == "open") == [
        "Big Spruce", "Frontier", "Little Spruce", "Logjam", "Lower Bowl", "Lower Northstar", "Midway Catwalk",
        "Round Up", "Spur Catwalk", "Upper Ridge", "Wild Turkey"]
    # The page's own count is 11 of 61.
    assert len(trails) == 61
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_figures_are_read_and_undated():
    snow = azsnowbowl.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    # The row of figures also counts the open lifts and trails ("4/9", "11/61"), which are not snow.
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 0,
                                "BaseIn": 18}
    assert snow["SeasonTotalIn"] == 21 and snow["BaseConditions"] is None and snow["Report"] is None


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 10 lifts but 9 were read"):
        azsnowbowl.parse(changed("4/9", "4/10"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        azsnowbowl.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="list of trails was not found"):
        azsnowbowl.parse(changed('m-lifts-and-trails">', 'm-trails">'), NOW)
    with pytest.raises(ValueError, match="is marked closed but reads 'Open'"):
        azsnowbowl.parse(changed('<li class="m-lift-status-open">', '<li class="m-lift-status-closed">', 1), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        azsnowbowl.parse("<html></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = azsnowbowl.parse(changed("21&#8243;", "a little"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 9
