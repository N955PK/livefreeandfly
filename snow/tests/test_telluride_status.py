from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import telluride

# The page as the site gave it on 2026-11-26, before the season: only the free gondola from town was running.
PAGE = (Path(__file__).parent / "fixtures" / "telluride.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED_TRAIL = 'data-level="novice"\n\t\t\t\t\t\t\tdata-groomed="0"\n\t\t\t\t\t\t\tdata-hold="0"\n' \
               '                            data-closed="1"'


def page(old: str, new: str, count: int = 1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_preseason_mountain_reads_each_lift_with_the_trails_under_it():
    feed = telluride.parse(PAGE, NOW)
    assert feed["Name"] == "Telluride" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Chondola", 1, 3), ("Childrens Magic Carpet", 1, 1), ("Adult Magic Carpet", 1, 1), ("Village Express", 1, 19),
        ("Polar Queen Express", 1, 14), ("Apex Lift", 1, 10), ("Lift 7", 1, 10), ("Oak Street Lift", 1, 6),
        ("Plunge Lift", 1, 18), ("Sunshine Express", 1, 14), ("UTE Park", 1, 4), ("Prospect Express", 1, 12),
        ("Prospect Express (Hike-To Terrain)", 0, 23), ("Gold Hill Express", 1, 8),
        ("Gold Hill Express (Hike-To Terrain)", 0, 1), ("Revelation Lift", 1, 6),
        ("Revelation Lift (Hike-To Terrain)", 0, 6), ("North Meadows Carpet", 1, 1),
        ("Free Gondola – Town to MV", 1, 0), ("Lynx", 1, 0)]
    lifts = {lift["Name"]: lift for lift in rows(feed, "Lifts")}
    assert len(lifts) == 17
    assert [name for name, lift in lifts.items() if lift["StatusEnglish"] == "open"] == ["Free Gondola – Town to MV"]
    assert lifts["Plunge Lift"] == {"Name": "Plunge Lift", "Status": "Closed", "StatusEnglish": "closed",
                                    "Difficulty": None}
    trails = rows(feed, "Trails")
    assert len(trails) == 157 == len({trail["Name"] for trail in trails})
    assert {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Meadows – South", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Green", "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["Jello’s Bowl"]["Difficulty"] == "Double black" and by_name["Misty Maiden – Upper"]["Difficulty"] == "Blue"


def test_the_snow_report_gives_the_depth_the_snowfall_the_surface_and_when_it_was_updated():
    snow = telluride.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: November 26, 2026 at 6:48am", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T13:48:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 20, "OvernightIn": 3, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last7DaysIn": 8}
    assert snow["SeasonTotalIn"] == 24 and snow["BaseConditions"] == "Variable"


def test_an_open_and_groomed_trail_and_one_on_hold_are_read_from_the_trail_s_own_attributes():
    opened = CLOSED_TRAIL.replace('groomed="0"', 'groomed="1"').replace('closed="1"', 'closed="0"')
    feed = telluride.parse(page(CLOSED_TRAIL, opened), NOW)
    assert rows(feed, "Trails")[0] == {"Name": "Meadows – South", "Status": "Open", "StatusEnglish": "open",
                                       "Difficulty": "Green", "Grooming": "Yes"}
    held = CLOSED_TRAIL.replace('hold="0"', 'hold="1"').replace('closed="1"', 'closed="0"')
    trail = rows(telluride.parse(page(CLOSED_TRAIL, held), NOW), "Trails")[0]
    assert (trail["Status"], trail["StatusEnglish"], trail["Grooming"]) == ("On hold", "on hold", "No")


def test_a_lift_on_hold_takes_the_words_of_the_page_s_key():
    held = page('<td><span class="tsr-report-app-icon-closed"></span></td>\n\t\t\t\t\t\t\t\t<td>Chondola</td>',
                '<td><span class="tsr-report-app-icon-hold"></span></td>\n\t\t\t\t\t\t\t\t<td>Chondola</td>')
    lift = telluride.parse(held, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Chondola", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift table was not found"):
        telluride.parse(page('id="tsr-report-app-lift-table"', 'id="lift-table"'), NOW)
    with pytest.raises(ValueError, match="status pictures"):
        telluride.parse(page('<td><span class="tsr-report-app-icon-open"></span></td>',
                             '<td><span class="tsr-report-app-icon-delayed"></span></td>'), NOW)
    with pytest.raises(ValueError, match="counts 1 of 18 lifts open but 1 of 17"):
        telluride.parse(page("<span>1<span>/17</span>", "<span>1<span>/18</span>"), NOW)
    with pytest.raises(ValueError, match="counts 1 of 17 lifts open but 0 of 17"):
        telluride.parse(page('<td><span class="tsr-report-app-icon-open"></span></td>',
                             '<td><span class="tsr-report-app-icon-closed"></span></td>'), NOW)
    with pytest.raises(ValueError, match="count of lifts was not found"):
        telluride.parse(page("<p>lifts open</p>", "<p>lifts</p>"), NOW)
    with pytest.raises(ValueError, match="trail list was not found"):
        telluride.parse(page('<div class="tsr-report-app-trail-list">', '<div class="trail-list">'), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: hardest"):
        telluride.parse(page(CLOSED_TRAIL, CLOSED_TRAIL.replace("novice", "hardest")), NOW)
    with pytest.raises(ValueError, match="closed, on hold and groomed"):
        telluride.parse(page(CLOSED_TRAIL, CLOSED_TRAIL.replace('data-closed="1"', 'data-closed="maybe"')), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        telluride.parse(page('<span class="tsr-report-app-level" data-level="novice"></span>\n\t\t\t\t\t\t\t<span>',
                             '<span class="tsr-report-app-level" data-level="novice"></span>\n\t\t\t\t\t\t\t<b>'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = telluride.parse(page("Last Updated: November 26, 2026 at 6:48am", "Last Updated: this morning"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 17
    assert "SnowReport" not in telluride.parse(page("<span>Snow depth</span>", "<span>Depth</span>"), NOW)
    assert "SnowReport" not in telluride.parse(page('<span><strong>20"</strong></span>',
                                                    "<span><strong>deep</strong></span>"), NOW)
