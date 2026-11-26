import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import terrypeak

# The pages with their scripts, styles, drawings, headers and footers taken out; the reader gives the same on the
# whole pages.
FIXTURES = Path(__file__).parent / "fixtures"
LIFTS = (FIXTURES / "terrypeak_lifts.html").read_text()
SNOW = (FIXTURES / "terrypeak_snow.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
BADGE = re.compile(r'dor-status-display__badge--closed">\s*Closed\s*</span>')


def read(lifts: str = LIFTS, snow: str = SNOW, now: datetime = NOW) -> dict:
    return terrypeak.parse({"lifts": lifts, "snow": snow}, now)


def changed(page: str, old: str, new: str, count: int = -1) -> str:
    assert old in page
    return page.replace(old, new, count)


def badged(page: str, marked: str, said: str, count: int = 1) -> str:
    """The page with its first closed badges given another class and other words."""
    assert BADGE.search(page)
    return BADGE.sub(f'dor-status-display__badge--{marked}"> {said} </span>', page, count=count)


def test_the_preseason_mountain_reads_its_lifts_and_the_trails_of_each_column():
    # Terry Peak's page on 2026-11-26, before opening: five lifts and 29 trails, all closed.
    feed = read()
    assert feed["Name"] == "Terry Peak" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Terry Peak", 5, 0), ("Beginner", 0, 6), ("Intermediate", 0, 11), ("Advanced", 0, 12)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Stewart Lift", "Snow Carpet", "Surprise Express", "Kussy Express",
                                                "Coeur Wharf Express"]
    assert lifts[0] == {"Name": "Stewart Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 29 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    # No trail carries a mark for grooming, so the page says nothing of it; the mark for snowmaking is not one.
    assert trails["Stewart Slope"] == {"Name": "Stewart Slope", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Green"}
    assert (trails["Welcome"]["Difficulty"], trails["The Falls"]["Difficulty"]) == ("Blue", "Black")
    assert "Homestake (upper closed)" in trails


def test_the_snow_report_takes_the_time_the_trails_and_lifts_were_updated():
    snow = read()["SnowReport"]
    # "Updated: 10:04 AM Wednesday, Nov 25", in Mountain time; the year is the one whose November 25 is a Wednesday.
    assert snow["LastUpdate"] == "2026-11-25T17:04:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 0,
                                "BaseIn": 0}
    assert snow["SeasonTotalIn"] is None and snow["BaseConditions"] is None
    deep = changed(SNOW, '<div class="value">0"</div>', '<div class="value">3.5"</div>', 1)
    assert read(snow=deep)["SnowReport"]["BaseArea"]["Last24HoursIn"] == 3.5


def test_the_year_is_last_year_s_when_the_day_has_not_come_yet():
    late = changed(LIFTS, "Updated: 10:04 AM Wednesday, Nov 25", "Updated: 8:15 AM Thursday, Dec 31")
    january = datetime(2027, 1, 2, 18, 0, tzinfo=timezone.utc)
    assert read(late, now=january)["SnowReport"]["LastUpdate"] == "2026-12-31T15:15:00Z"
    # A weekday that agrees with neither year is refused, and costs only the snow report.
    wrong = changed(LIFTS, "Updated: 10:04 AM Wednesday, Nov 25", "Updated: 10:04 AM Sunday, Nov 25")
    assert "SnowReport" not in read(wrong)


def test_an_open_lift_an_open_trail_and_a_groomed_trail_are_read():
    lifts = badged(LIFTS, "open", "Open")
    at = lifts.index('<h3 class="dor-status-display__heading">Trail Status</h3>')
    lifts = lifts[:at] + badged(lifts[at:], "open", "Open", 2)
    lifts = changed(lifts, '<i class="fa-light fa-snowflake" title="Snow Making"></i>',
                    '<i class="fa-light fa-snowplow" title="Groomed"></i>', 1)
    areas = read(lifts)["MountainAreas"]
    assert areas[0]["Lifts"][0] == {"Name": "Stewart Lift", "Status": "Open", "StatusEnglish": "open",
                                    "Difficulty": None}
    assert areas[0]["Lifts"][1]["StatusEnglish"] == "closed"
    assert areas[1]["Trails"][0] == {"Name": "Stewart Slope", "Status": "Open", "StatusEnglish": "open",
                                     "Difficulty": "Green", "Grooming": "Yes"}
    assert areas[1]["Trails"][1] == {"Name": "Upper Stewart", "Status": "Open", "StatusEnglish": "open",
                                     "Difficulty": "Green", "Grooming": "No"}
    assert all(trail["Grooming"] == "No" for area in areas[2:] for trail in area["Trails"])


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    lift = read(badged(LIFTS, "wind-hold", "Wind Hold"))["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Stewart Lift", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Stewart Lift is marked shut but reads 'Closed'"):
        read(badged(LIFTS, "shut", "Closed"))
    with pytest.raises(ValueError, match="not a lift status and then a trail status"):
        read(changed(LIFTS, ">Trail Status</h3>", ">Runs</h3>"))
    with pytest.raises(ValueError, match="a difficulty the reader does not know: expert"):
        read(changed(LIFTS, "column-heading--advanced", "column-heading--expert"))
    with pytest.raises(ValueError, match="lists 34 lifts and trails but 33 were read"):
        read(changed(LIFTS, '<span class="dor-status-display__name">Welcome</span>', "<b>Welcome</b>"))
    with pytest.raises(ValueError, match="counts 6 under 'Lifts Open' but 5 were read"):
        read(snow=changed(SNOW, '<div class="value">0/5</div>', '<div class="value">0/6</div>'))
    with pytest.raises(ValueError, match="count under 'Trails Open' was not found"):
        read(snow=changed(SNOW, '<div class="value">0/29</div>', '<div class="value">none</div>'))
    with pytest.raises(ValueError):
        read("<html><body>Not the page</body></html>")


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = read(snow=changed(SNOW, '<div class="value">0"</div>', '<div class="value">deep</div>', 1))
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 5
    assert "SnowReport" not in read(snow=changed(SNOW, "Base Depth", "Snow Stake"))
    assert "SnowReport" not in read(changed(LIFTS, "Updated: 10:04 AM Wednesday, Nov 25", "Updated this morning"))
