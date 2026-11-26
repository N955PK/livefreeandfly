from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import snowriver

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings, menus and written report taken out; the reader gives the same
# on the whole pages.
PAGES = {name: (FIXTURES / f"snowriver_{name}.html").read_text() for name in snowriver.URLS}
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
CLOSED = "<div class=\"f-icon icon-closed\"\n             title=\"Closed\"></div>"


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def test_the_preseason_resort_reads_each_part_of_its_two_peaks_with_its_lifts_and_runs():
    # Snowriver's pages on 2026-11-26, nine days before it opened: ten lifts, one of them posted open, and 72 runs.
    feed = snowriver.parse(PAGES, NOW)
    assert feed["Name"] == "Snowriver" and feed["LastUpdate"] == "2026-11-26T17:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Frontside", ["Ascender", "Birgantine"], 13), ("Westside", ["Capstan", "Draw Stroke"], 14),
        ("Main Face", ["Cloudfront Double", "Maple Tow", "Sugar Hills Conveyor", "Voyageur Express"], 25),
        ("Bear Creek", ["Bear Creek"], 11), ("The East", ["East T"], 9)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    # "Birgantine (1:00pm-4:00pm)" is read without its hours.
    assert lifts[1] == {"Name": "Birgantine", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert [lift["StatusEnglish"] for lift in lifts] == ["closed", "open"] + ["closed"] * 8
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 72 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Lost Tarn", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_gives_the_depth_and_when_it_was_updated():
    snow = snowriver.parse(PAGES, NOW)["SnowReport"]
    # "Nov 26th - 10:52am" in Central time, six hours behind UTC in November, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-26T16:52:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 0,
                                "BaseIn": 24}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None


def test_a_held_lift_is_read():
    pages = lifts_page(CLOSED, "<div class=\"f-icon icon-on-hold\"\n             title=\"On Hold\"></div>", 1)
    lift = snowriver.parse(pages, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Ascender", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts of lifts and trails were not found"):
        snowriver.parse(lifts_page("snow-weather page mountain-stats", "snow-weather page"), NOW)
    with pytest.raises(ValueError, match="counts 54 primary trails but 53 were read"):
        snowriver.parse(lifts_page("<span class=\"unit\">/53</span>", "<span class=\"unit\">/54</span>"), NOW)
    with pytest.raises(ValueError, match="Ascender's status icon is shut and reads 'Closed'"):
        snowriver.parse(lifts_page(CLOSED, CLOSED.replace("icon-closed", "icon-shut"), 1), NOW)
    with pytest.raises(ValueError, match="Lost Tarn has a difficulty the reader does not know: novice"):
        snowriver.parse(lifts_page("cell f-icon level icon-beginner", "cell f-icon level icon-novice", 1), NOW)
    with pytest.raises(ValueError, match="82 lift and run rows but 0 were read"):
        snowriver.parse(lifts_page("<details>", "<section>"), NOW)
    with pytest.raises(ValueError):
        snowriver.parse({**PAGES, "lifts": "<html><body>Page not found</body></html>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = snowriver.parse(snow_page("Nov 26th - 10:52am", "this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
    assert "SnowReport" not in snowriver.parse(snow_page("condition-block snow winter", "condition-block winter"),
                                               NOW)
