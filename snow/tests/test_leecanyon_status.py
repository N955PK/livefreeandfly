from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import leecanyon

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "leecanyon.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_page_is_lee_canyon_s_lifts_and_trails_page():
    assert leecanyon.URL == "https://www.leecanyonlv.com/lifts-and-trails/"


def test_the_early_season_mountain_reads_its_lifts_and_its_trails_by_lift():
    # Lee Canyon's page on Thanksgiving 2026: seven lifts with three turning, 35 trails with six open.
    feed = leecanyon.parse(PAGE, NOW)
    assert feed["Name"] == "Lee Canyon" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lee Canyon", 7, 0), ("Rabbit Peak", 0, 1), ("Alpenglow Surface Lift", 0, 1), ("Ponderosa", 0, 4),
        ("Bluebird", 0, 11), ("Sherwood", 0, 12), ("West Bowl", 0, 6)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Rabbit Peak", "open"), ("Alpenglow Surface Lift", "open"), ("Ponderosa", "open"), ("Bluebird", "closed"),
        ("Sherwood", "closed"), ("West Bowl Coming in December", "closed"),
        ("Chipmunk Express Coming Soon", "closed")]
    assert lifts[0] == {"Name": "Rabbit Peak", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Rabbit Peak", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                         "Grooming": "No"}
    assert sorted(trail["Name"] for trail in trails if trail["StatusEnglish"] == "open") == [
        "Bonanza Ridge", "Bristlecone Alley", "Foxtail Alley", "Limber Pine Lane", "Rabbit Peak", "Rabbit Return"]
    assert len(trails) == 35 and {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}


def test_the_uphill_travel_routes_are_not_trails():
    # The page lists six uphill routes in two groups after the lifts' groups, with no difficulty.
    assert PAGE.count('<li class="m-filter-target') == 41
    feed = leecanyon.parse(PAGE, NOW)
    names = {trail["Name"] for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert "Mystic Gate" not in names and not any(name.startswith("Below Lift Served") for name in names)
    assert not any(area["Name"].startswith("Uphill") for area in feed["MountainAreas"])


def test_the_snow_figures_have_no_base_depth_and_are_undated():
    snow = leecanyon.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "BaseIn": None}
    assert snow["SeasonTotalIn"] == 25 and snow["BaseConditions"] is None and snow["Report"] is None


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 8 lifts but 7 were read"):
        leecanyon.parse(changed("3/7", "3/8"), NOW)
    with pytest.raises(ValueError, match="counts 36 trails but 35 were read"):
        leecanyon.parse(changed("6/35", "6/36"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        leecanyon.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="list of trails was not found"):
        leecanyon.parse(changed('m-lifts-and-trails">', 'm-trails">'), NOW)
    with pytest.raises(ValueError, match="is marked closed but reads 'Open'"):
        leecanyon.parse(changed('<li class="m-lift-status-open">', '<li class="m-lift-status-closed">', 1), NOW)
    # A group of routes with no difficulty under any other name is not passed over.
    with pytest.raises(ValueError, match="a trail in the list has no name or no status"):
        leecanyon.parse(changed("Uphill Travel &#8211; Above", "Backcountry &#8211; Above"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        leecanyon.parse("<html></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = leecanyon.parse(changed("25&#8243;", "some"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
