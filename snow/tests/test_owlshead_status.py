from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import owlshead

FIXTURES = Path(__file__).parent / "fixtures"
# The pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGE = (FIXTURES / "owlshead.html").read_text()
MIDSEASON = (FIXTURES / "owlshead_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new)


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_closed_mountain_reads_each_lift_with_the_trails_under_it():
    # Owl's Head's page on 2026-11-24, before the season: six lifts and 51 trails, all closed.
    feed = owlshead.parse(PAGE, NOW)
    assert feed["Name"] == "Owl's Head" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Summit", 1, 24), ("Family", 1, 4), ("Blue", 1, 3), ("Panorama", 1, 8), ("Lake", 1, 10),
        ("Magic carpet", 1, 1), ("Snowparks", 0, 1)]
    assert rows(feed, "Lifts")[0] == {"Name": "Summit", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": None}
    assert {row["StatusEnglish"] for row in rows(feed, "Lifts") + rows(feed, "Trails")} == {"closed"}
    assert rows(feed, "Trails")[0] == {"Name": "Fleur de lys", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Blue", "Grooming": "No"}
    # Kandahar's row draws a glade's tree beside its level; the snowpark has no level.
    trails = {trail["Name"]: trail for trail in rows(feed, "Trails")}
    assert trails["Kandahar"]["Difficulty"] == "Double black" and trails["JCT 16-18"]["Difficulty"] == ""


def test_the_midseason_mountain_reads_what_is_open_and_groomed():
    # The page as the Internet Archive kept it on 2026-01-21: five of six lifts turning, 49 of 51 trails open.
    feed = owlshead.parse(MIDSEASON, NOW)
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in rows(feed, "Lifts")] == [
        ("Summit", "open"), ("Family", "open"), ("Blue", "closed"), ("Panorama", "open"), ("Lake", "open"),
        ("Magic carpet", "open")]
    trails = rows(feed, "Trails")
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 49
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 26


def test_the_snowfall_is_turned_from_centimetres_into_inches_and_there_is_no_depth():
    snow = owlshead.parse(MIDSEASON, NOW)["SnowReport"]
    # "Last modification: 2026-01-20 16:00", five hours behind UTC in January; 2, 2, 19 and 276 cm.
    assert snow["LastUpdate"] == "2026-01-20T21:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.8, "Last48HoursIn": 0.8, "Last7DaysIn": 7.5}
    assert snow["SeasonTotalIn"] == 108.7 and snow["BaseConditions"] is None
    # Before the season the page still carries last April's report, which the runner leaves out as old.
    assert owlshead.parse(PAGE, NOW)["SnowReport"]["LastUpdate"] == "2026-04-13T12:01:00Z"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = owlshead.parse(changed('<span class="section-close">Closed</span>',
                                  '<span class="section-hold">On hold</span>'), NOW)
    assert {(lift["Status"], lift["StatusEnglish"]) for lift in rows(feed, "Lifts")} == {("On hold", "on hold")}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="level symbols"):
        owlshead.parse(changed('<span class="icon-vdiff">', '<span class="icon-hard">'), NOW)
    with pytest.raises(ValueError, match="Summit counts 25 trails but 24"):
        owlshead.parse(changed('<p class="sum-total p-large">0/24</p>', '<p class="sum-total p-large">0/25</p>'), NOW)
    with pytest.raises(ValueError, match="counts 7 chairlifts but 6"):
        owlshead.parse(changed('<div class="text p-large">0/6</div>', '<div class="text p-large">0/7</div>'), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        owlshead.parse(changed('class="section-piste"', 'class="section-trails"'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = owlshead.parse(changed("Last modification:", "Modified:"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 6
    assert "SnowReport" not in owlshead.parse(changed("<h4>Last 48 h</h4>", "<h4>Two days</h4>"), NOW)
