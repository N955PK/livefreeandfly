from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import arcticvalley

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "arcticvalley.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
SLIP = "Friday November 30th"


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_mountain_before_its_season_reads_its_four_lifts_in_the_page_s_words():
    # Arctic Valley's page on 2026-11-26, two weeks before it opens: each lift reads "N/A".
    feed = arcticvalley.parse(PAGE, NOW)
    assert feed["Name"] == "Arctic Valley" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert feed["MountainAreas"] == [{"Name": "Arctic Valley", "Trails": [], "Lifts": [
        {"Name": name, "Status": "N/A", "StatusEnglish": "n/a", "Difficulty": None}
        for name in ("Handle Tow", "T-bar", "Chair 1", "Chair 2")]}]


def test_a_day_whose_weekday_does_not_agree_costs_the_snow_report():
    # The page says "Updated Friday November 30th": no November 30th of the last year is a Friday.
    assert "SnowReport" not in arcticvalley.parse(PAGE, NOW)


def test_the_snow_report_is_stamped_at_noon_on_the_day_it_was_updated():
    snow = arcticvalley.parse(changed(SLIP, "Friday November 20th"), NOW)["SnowReport"]
    # Noon in Alaska, nine hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-20T21:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 12, "Last7DaysIn": 12, "BaseIn": 20}
    assert snow["SeasonTotalIn"] is None and snow["BaseConditions"] is None
    # A day later in the year than today is last year's: December 26th, 2025 was a Friday.
    snow = arcticvalley.parse(changed(SLIP, "Friday December 26th"), NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2025-12-26T21:00:00Z"


def test_a_lift_reads_as_open_or_closed_where_its_words_begin_so():
    page = changed("<strong>Chair 1: </strong>N/A", "<strong>Chair 1: </strong>Open until 4pm")
    page = page.replace("<strong>T-bar:</strong> N/A", "<strong>T-bar:</strong> CLOSED")
    page = page.replace("<strong>Chair 2: </strong>N/A", "<strong>Chair 2: </strong>Wind hold")
    lifts = arcticvalley.parse(page, NOW)["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Handle Tow", "N/A", "n/a"), ("T-bar", "CLOSED", "closed"), ("Chair 1", "Open until 4pm", "open"),
        ("Chair 2", "Wind hold", "wind hold")]
    opening = changed("<strong>Chair 1: </strong>N/A", "<strong>Chair 1: </strong>Opening Saturday")
    assert arcticvalley.parse(opening, NOW)["MountainAreas"][0]["Lifts"][2]["StatusEnglish"] == "opening saturday"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no lift status section"):
        arcticvalley.parse(changed("<summary>• Lift Status</summary>", "<summary>• Lifts</summary>"), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        arcticvalley.parse(changed("<strong>Chair 1: </strong>N/A", "<strong>Chair 1: </strong>"), NOW)
    with pytest.raises(ValueError, match="has 4 names but 3 lifts were read"):
        arcticvalley.parse(changed("<strong>Chair 1: </strong>N/A", "<strong>Chair 1</strong> N/A"), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        arcticvalley.parse(changed("<strong>Handle Tow: </strong>N/A<br><strong>T-bar:</strong> N/A<br>"
                                   "<strong>Chair 1: </strong>N/A<br><strong>Chair 2: </strong>N/A", "Closed"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    dated = changed(SLIP, "Friday November 20th")
    feed = arcticvalley.parse(dated.replace("Total snow depth: 20&#8243;", "Total snow depth: deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
    assert "SnowReport" not in arcticvalley.parse(changed(SLIP, "this morning"), NOW)
    assert "SnowReport" not in arcticvalley.parse(dated.replace("<summary>• Snow Report</summary>",
                                                                "<summary>• Snow</summary>"), NOW)
