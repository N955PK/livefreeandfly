from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sunvalley

# The page with its scripts, styles and drawings taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "sunvalley.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
BALD_SNOW = PAGE.index('<div class="mc__tab js-mc__tab -active" data-tab="weather-bald">')


def changed(old: str, new: str, count: int = 1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_opening_morning_reads_bald_mountain_s_lifts_and_trails_by_part_of_the_mountain():
    # Sun Valley's page on the morning of 2026-11-26, its opening day: 12 lifts with two scheduled, 113 trails.
    feed = sunvalley.parse(PAGE, NOW)
    assert feed["Name"] == "Sun Valley" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Bowls", 3, 17), ("Frenchman's", 1, 11), ("River Run", 5, 36), ("Seattle Ridge", 1, 9),
        ("Warm Springs", 2, 31), ("Sunrise", 0, 5), ("Terrain Park", 0, 4)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert [lift["Name"] for lift in lifts] == [
        "Broadway", "Lookout", "Mayday", "Frenchman's", "Roundhouse Express", "Christmas", "Lookout Express",
        "River Run", "Kinderspielplatz", "Seattle Ridge", "Challenger", "Flying Squirrel"]
    # The notes under two lifts' names ("Early season: Last up 3:30") are not part of their names.
    assert [lift for lift in lifts if lift["StatusEnglish"] != "closed"] == [
        {"Name": "Roundhouse Express", "Status": "Scheduled", "StatusEnglish": "scheduled", "Difficulty": None},
        {"Name": "Christmas", "Status": "Scheduled", "StatusEnglish": "scheduled", "Difficulty": None}]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # The page counts 109 trails: the four terrain parks are not among them.
    assert len(trails) == 113 == len({trail["Name"] for trail in trails})
    assert [trail for trail in trails if trail["StatusEnglish"] != "closed"] == [
        {"Name": "Roundhouse Lane", "Status": "Expected", "StatusEnglish": "expected", "Difficulty": "Green",
         "Grooming": "Yes"},
        {"Name": "Upper College", "Status": "Expected", "StatusEnglish": "expected", "Difficulty": "Green",
         "Grooming": "Yes"}]
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Bowl Lane", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green", "Grooming": "No"}
    count = {}
    for trail in trails:
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 30, "Blue": 37, "Black": 39, "Double black": 3, "": 4}
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == ""] == [
        "Broadway Family Cross Course", "College Hike Park", "Saddle Up Park", "Showtime Park"]
    # Dollar Mountain's lifts and trails are not Bald Mountain's.
    assert "Quarter Dollar" not in {lift["Name"] for lift in lifts}
    assert "Dollar Face" not in {trail["Name"] for trail in trails}


def test_the_snow_report_gives_bald_mountain_s_depth_and_snowfall_and_when_it_was_updated():
    snow = sunvalley.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: Nov 26, 5:32 AM MT", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T12:32:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 24, "OvernightIn": 0, "Last24HoursIn": 0,
                                "Last7DaysIn": 6}
    assert snow["SeasonTotalIn"] == 26 and snow["BaseConditions"] is None and snow["Report"] is None


def test_a_report_read_in_january_and_written_in_december_is_last_year_s():
    page = changed("Last Updated: Nov 26, 5:32 AM MT", "Last Updated: Dec 31, 4:10 PM MT", 99)
    snow = sunvalley.parse(page, datetime(2027, 1, 1, 3, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-12-31T23:10:00Z"
    assert sunvalley.parse(page, datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc))["SnowReport"] == snow


def test_an_open_lift_and_a_lift_on_hold_take_the_words_of_the_page_s_key():
    scheduled = '<span class="mc__icon mc__icon-scheduled"></span>\n <span class="sr-only">Lift Scheduled</span>'
    feed = sunvalley.parse(changed(scheduled, '<span class="mc__icon mc__icon-open"></span>'), NOW)
    assert feed["MountainAreas"][2]["Lifts"][0] == {"Name": "Roundhouse Express", "Status": "Open",
                                                    "StatusEnglish": "open", "Difficulty": None}
    feed = sunvalley.parse(changed(scheduled, '<span class="mc__icon mc__icon-hold"></span>'), NOW)
    assert feed["MountainAreas"][2]["Lifts"][0]["Status"] == "On hold"
    assert feed["MountainAreas"][2]["Lifts"][0]["StatusEnglish"] == "on hold"
    expected = '<span class="mc__icon mc__icon-expected"></span>\n <span class="sr-only">Trail Expected</span>'
    area = sunvalley.parse(changed(expected, '<span class="mc__icon mc__icon-open"></span>'), NOW)["MountainAreas"][2]
    assert area["Trails"][0] == {"Name": "Roundhouse Lane", "Status": "Open", "StatusEnglish": "open",
                                  "Difficulty": "Green", "Grooming": "Yes"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 lifts tabs for bald"):
        sunvalley.parse(changed('data-tab="lifts-bald">', 'data-tab="lifts-baldy">', 99), NOW)
    with pytest.raises(ValueError, match="0 trails tabs for bald"):
        sunvalley.parse(changed('js-mc__tab -active" data-tab="trails-bald">', 'js-mc__pane" data-tab="trails-bald">'),
                        NOW)
    with pytest.raises(ValueError, match="does not count the mountain's lifts"):
        sunvalley.parse(changed('<span class="mc-lifts__graph-value">2 / 12</span>', "<span>2 / 12</span>"), NOW)
    with pytest.raises(ValueError, match="counts 13 lifts but 12"):
        sunvalley.parse(changed('<span class="mc-lifts__graph-value">2 / 12</span>',
                                '<span class="mc-lifts__graph-value">2 / 13</span>'), NOW)
    with pytest.raises(ValueError, match="counts 110 trails but 113"):
        sunvalley.parse(changed('<span class="mc-lifts__graph-value">2 / 109</span>',
                                '<span class="mc-lifts__graph-value">2 / 110</span>'), NOW)
    with pytest.raises(ValueError, match="Roundhouse Express has status symbols \\['running'\\]"):
        sunvalley.parse(changed("mc__icon-scheduled\"></span>\n <span class=\"sr-only\">Lift Scheduled",
                                "mc__icon-running\"></span>\n <span class=\"sr-only\">Lift Scheduled"), NOW)
    with pytest.raises(ValueError, match="Roundhouse Lane has status symbols"):
        sunvalley.parse(changed("mc__icon-expected\"></span>\n <span class=\"sr-only\">Trail Expected",
                                "mc__icon-soon\"></span>\n <span class=\"sr-only\">Trail Expected"), NOW)
    with pytest.raises(ValueError, match="Inhibition has difficulty symbols"):
        sunvalley.parse(changed('<span class="mc__icon mc__icon-most-difficult"></span>\n <span>\n Inhibition',
                                '<span class="mc__icon mc__icon-extreme"></span>\n <span>\n Inhibition'), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        sunvalley.parse(changed('<h3 class="accordion__heading"><a href="#" class="accordion__toggle',
                                '<h3 class="accordion__heading"><a href="#" class="toggle', 99), NOW)
    with pytest.raises(ValueError, match="no name or no table"):
        sunvalley.parse(changed('<table class="mc__table mc-lifts__table">', '<table class="mc__table">'), NOW)
    with pytest.raises(ValueError, match="0 lifts tabs for bald"):
        sunvalley.parse("<html><body>Just a moment...</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def snow_changed(old: str, new: str) -> str:
        assert old in PAGE[BALD_SNOW:]
        return PAGE[:BALD_SNOW] + PAGE[BALD_SNOW:].replace(old, new, 1)

    feed = sunvalley.parse(snow_changed('<p class="mc__num mc__num-lg">24&#8221;</p>',
                                        '<p class="mc__num mc__num-lg">deep</p>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
    assert "SnowReport" not in sunvalley.parse(snow_changed("24 hours</h3>", "Today</h3>"), NOW)
    assert "SnowReport" not in sunvalley.parse(changed("Last Updated: Nov 26, 5:32 AM MT", "Updated this morning", 99),
                                               NOW)
    assert "SnowReport" not in sunvalley.parse(changed('data-tab="weather-bald">', 'data-tab="snow-bald">', 99), NOW)
    # A base depth the page leaves out stays empty.
    snow = sunvalley.parse(snow_changed('<h3 class="mc__heading mc__h3">Base</h3>',
                                        '<h3 class="mc__heading mc__h3">Summit</h3>'), NOW)["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] is None and snow["BaseArea"]["Last24HoursIn"] == 0
