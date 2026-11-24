from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import jaypeak

PAGE = (Path(__file__).parent / "fixtures" / "jaypeak.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_nine_closed_lifts_and_the_trails_by_kind():
    # Jay Peak's report on 2026-11-24, before it opened: every lift closed, two trails marked open.
    feed = jaypeak.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Jay Peak", 9, 0), ("Beginner", 0, 14), ("Intermediate", 0, 31), ("Advanced", 0, 20), ("Terrain Park", 0, 5),
        ("Intermediate Glade", 0, 5), ("Advanced Glade", 0, 20)]
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Aerial Tram"] == {"Name": "Aerial Tram", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert lifts["Jet Triple"]["StatusEnglish"] == "closed" and {lift["Status"] for lift in lifts.values()} == {"Closed"}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert trails["Queen's Highway"] == {"Name": "Queen's Highway", "Status": "Closed", "StatusEnglish": "closed",
                                         "Difficulty": "Green"}
    assert trails["The Jet"]["StatusEnglish"] == "open" and trails["The Jet"]["Difficulty"] == "Black"
    assert sorted(name for name, trail in trails.items() if trail["StatusEnglish"] == "open") == ["The Jet", "The Jet Lower"]


def test_the_snow_report_keeps_an_empty_base_depth_empty_and_dates_the_report_in_utc():
    snow = jaypeak.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-16T13:36:00Z" and snow["SeasonTotalIn"] == 8 and snow["BaseConditions"] is None
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": 0, "Last48HoursIn": 8, "Last7DaysIn": 8}


def test_a_depth_reads_as_a_figure_or_a_range_and_nothing_else():
    assert jaypeak.depth('18 "') == (18, None, None) and jaypeak.depth('12 - 24 "') == (None, 12, 24)
    assert jaypeak.depth('"') == (None, None, None)
    with pytest.raises(ValueError, match="does not read as inches"):
        jaypeak.depth("deep")
    page = PAGE.replace("<dt>Base Depth</dt><dd> &quot;</dd>", "<dt>Base Depth</dt><dd>20 &quot;</dd>")
    assert jaypeak.parse(page, NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 20


def test_hold_and_groomed_marks_read_and_the_year_is_the_one_whose_weekday_agrees():
    card = PAGE[PAGE.index('<article class="SnowReport-Lift'):PAGE.index("</article>", PAGE.index('<article class="SnowReport-Lift'))]
    assert jaypeak.card_row(card.replace("pti-closed", "pti-hold"), None)["StatusEnglish"] == "on hold"
    assert jaypeak.card_row(card + '<i class="pti pti-groomed"></i>', "Blue")["Grooming"] == "Yes"
    assert jaypeak.posted_at("Wednesday December 30 at 4:05 PM", datetime(2027, 1, 2, tzinfo=timezone.utc)) == "2026-12-30T21:05:00Z"
    with pytest.raises(ValueError, match="not a day of this year or last"):
        jaypeak.posted_at("Friday November 16 at 8:36 AM", NOW)


def test_a_page_whose_lifts_or_statuses_do_not_all_read_is_refused():
    with pytest.raises(ValueError, match="counts 10 lifts but 9"):
        jaypeak.parse(PAGE.replace("<dd>0 / 9</dd>", "<dd>0 / 10</dd>"), NOW)
    with pytest.raises(ValueError, match="legend does not name"):
        jaypeak.parse(PAGE.replace('<i class="pti pti-closed"', '<i class="pti pti-maybe"', 1), NOW)
    with pytest.raises(ValueError, match="lifts were not found"):
        jaypeak.parse(PAGE.replace("SnowReport-section--lifts", "SnowReport-section--chairs"), NOW)
