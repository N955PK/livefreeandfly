from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import cooperspur

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "cooperspur.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED = '<p class="eael-feature-list-content">Closed</p>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_two_lifts_and_no_trails():
    # Cooper Spur's page on 2026-11-26, before it opens: the chair and the rope tow, both closed.
    feed = cooperspur.parse(PAGE, NOW)
    assert feed["Name"] == "Cooper Spur" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert feed["MountainAreas"] == [{"Name": "Cooper Spur", "Trails": [], "Lifts": [
        {"Name": "Homestead Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Rope Tow", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]}]


def test_the_snow_report_is_stamped_at_noon_on_the_day_the_page_was_updated():
    snow = cooperspur.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: October 31st, 2026", at noon Pacific daylight time.
    assert snow["LastUpdate"] == "2026-10-31T19:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "BaseIn": 0}
    assert snow["SeasonTotalIn"] is None and snow["BaseConditions"] is None
    page = changed('<p class="eael-feature-list-content">0" </p>', '<p class="eael-feature-list-content">27.5" </p>')
    assert cooperspur.parse(page, NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 27.5


def test_a_lift_s_status_is_carried_in_the_page_s_words():
    lifts = cooperspur.parse(changed(CLOSED, '<p class="eael-feature-list-content">Open</p>', 1),
                             NOW)["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [("Homestead Lift", "open"),
                                                                         ("Rope Tow", "closed")]
    page = changed(CLOSED, '<p class="eael-feature-list-content">Wind Hold </p>', 1)
    lift = cooperspur.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of conditions was not found"):
        cooperspur.parse(changed("eael-feature-list-title", "feature-title"), NOW)
    with pytest.raises(ValueError, match="no status for the Rope Tow"):
        cooperspur.parse(changed(">Rope Tow</p>", ">Rope Tow</div>"), NOW)
    with pytest.raises(ValueError, match="no status for the Homestead Lift"):
        cooperspur.parse(changed(CLOSED, '<p class="eael-feature-list-content"> </p>', 1), NOW)
    with pytest.raises(ValueError, match="a name the reader does not know: 'Tubing Hill'"):
        cooperspur.parse(changed(">Rope Tow</p>", ">Tubing Hill</p>"), NOW)
    with pytest.raises(ValueError, match="names Parking twice"):
        cooperspur.parse(changed(">Temperature</p>", ">Parking</p>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = cooperspur.parse(changed('<p class="eael-feature-list-content">0" </p>',
                                    '<p class="eael-feature-list-content">a dusting</p>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 2
    assert "SnowReport" not in cooperspur.parse(changed("October 31st, 2026", "today"), NOW)
    assert "SnowReport" not in cooperspur.parse(changed(">Snow Depth</p>", ">Snow Depth</div>"), NOW)
