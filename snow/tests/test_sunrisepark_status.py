import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sunrisepark

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "sunrisepark.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "uploads/2021/12/closed_x.png' alt='Groomed Status' style='max-width: 14px;'>"
UNGROOMED = "uploads/2021/12/no_snow_groomer.png'"


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def counting(page: str, kind: str, some: int) -> str:
    """The page with its own counts of ``kind`` (it gives each twice, or once for the groomed) set to ``some``."""
    out, made = re.subn(r">0(</span>(?:<span[^>]*>)?/\d+<br\s*/?>\s*" + kind + r")", rf">{some}\1", page)
    assert made
    return out


def test_the_preseason_mountain_reads_each_lift_and_each_peak_s_trails():
    # Sunrise Park's page on 2026-11-26, before opening: eight lifts and 67 trails on three peaks, all closed.
    feed = sunrisepark.parse(PAGE, NOW)
    assert feed["Name"] == "Sunrise Park" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 8, 0), ("Sunrise", 0, 34), ("Apache", 0, 17), ("Cyclone", 0, 16)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Sunrise High-Speed", "Pony Chair", "Rustler", "Fort Apache",
                                                "Geronimo", "Spirit Ridge", "Magic Carpet", "Cyclone Cord"]
    assert lifts[0] == {"Name": "Sunrise High-Speed", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 67 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Apache Pass", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    levels = [trail["Difficulty"] for trail in trails]
    assert [levels.count(level) for level in ("Green", "Blue", "Black", "Double black")] == [31, 19, 14, 3]


def test_the_snow_report_is_last_season_s_with_its_time_in_arizona_s_zone():
    snow = sunrisepark.parse(PAGE, NOW)["SnowReport"]
    # "Updated: March 6th, 2026 8:44am", which Arizona keeps seven hours behind UTC the year round.
    assert snow["LastUpdate"] == "2026-03-06T15:44:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last72HoursIn": 0, "Last7DaysIn": 0,
                                "BaseIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None


def test_snow_levels_in_inches_are_read():
    page = changed("<p style=\"text-align: center;\">0&#8220;</p>", "<p>6.5&#8220;</p>", 1)
    page = changed("Updated: March 6th, 2026 8:44am", "Updated: December 22nd, 2026 12:05pm", page=page)
    snow = sunrisepark.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursIn"] == 6.5 and snow["LastUpdate"] == "2026-12-22T19:05:00Z"


def test_an_open_lift_and_an_open_groomed_trail_are_read_when_the_page_s_counts_agree():
    page = changed("<p>Closed</p>", "<p>Open</p>", 1)
    page = changed(CLOSED, CLOSED.replace("closed_x", "open_check"), 2, page)
    page = changed(UNGROOMED, UNGROOMED.replace("no_snow_groomer", "snow_groomer"), 1, page)
    page = counting(counting(counting(page, "lifts open", 1), "trails open", 2), "groomed", 1)
    feed = sunrisepark.parse(page, NOW)
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Sunrise High-Speed", "Status": "Open",
                                                    "StatusEnglish": "open", "Difficulty": None}
    assert feed["MountainAreas"][0]["Lifts"][1]["StatusEnglish"] == "closed"
    trails = feed["MountainAreas"][1]["Trails"]
    assert trails[0] == {"Name": "Apache Pass", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                         "Grooming": "Yes"}
    assert (trails[1]["StatusEnglish"], trails[1]["Grooming"]) == ("open", "No")
    assert trails[2]["StatusEnglish"] == "closed"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    lift = sunrisepark.parse(changed("<p>Closed</p>", "<p>Wind Hold</p>", 1), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_trail_mark_the_page_s_counts_do_not_bear_out_is_refused():
    # A third picture (a hold, say) would be read as open: the page's own count of open trails catches it.
    with pytest.raises(ValueError, match="counts 0 of 67 trails open but 1 of 67 were read"):
        sunrisepark.parse(changed(CLOSED, CLOSED.replace("closed_x", "hold"), 1), NOW)
    with pytest.raises(ValueError, match="counts 0 of 67 groomed but 1 of 67 were read"):
        sunrisepark.parse(changed(UNGROOMED, UNGROOMED.replace("no_snow_groomer", "maybe"), 1), NOW)
    with pytest.raises(ValueError, match="counts 0 of 8 lifts open but 1 of 8 were read"):
        sunrisepark.parse(changed("<p>Closed</p>", "<p>Open</p>", 1), NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift table was not found"):
        sunrisepark.parse(changed('class="liftstable"', 'class="lifts"'), NOW)
    with pytest.raises(ValueError, match="not a status in a word and a name"):
        sunrisepark.parse(changed("<p>Closed</p>", "", 1), NOW)
    with pytest.raises(ValueError, match="difficulty symbol the reader does not know"):
        sunrisepark.parse(changed("green_trail.png", "orange_oval.png", 1), NOW)
    with pytest.raises(ValueError, match="3 trail tables and 70 rows but 2 tables"):
        sunrisepark.parse(changed('id="mobile-fusion-tab-', 'id="mobile-tab-', 1), NOW)
    with pytest.raises(ValueError, match="count of lifts open was not found"):
        sunrisepark.parse(changed("lifts open", "lifts turning"), NOW)
    with pytest.raises(ValueError, match="does not begin with the headings"):
        sunrisepark.parse(changed(">Groomed</td>", ">Surface</td>", 1), NOW)
    with pytest.raises(ValueError):
        sunrisepark.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sunrisepark.parse(changed("<p style=\"text-align: center;\">0&#8220;</p>", "<p>deep</p>", 1), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in sunrisepark.parse(changed("Updated: March 6th", "Posted: March 6th"), NOW)
    assert "SnowReport" not in sunrisepark.parse(changed(">Base Depth<", ">Depth<"), NOW)
