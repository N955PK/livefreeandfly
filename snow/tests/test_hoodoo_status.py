from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import hoodoo

# The main part of the page with its scripts, styles and comments taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "hoodoo.html").read_text()
# The page as it was read, months after its last report, and the Saturday that report was written for: 11 AM and
# 6 PM Pacific daylight time.
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
MIDDAY = datetime(2026, 3, 14, 18, 0, tzinfo=timezone.utc)
EVENING = datetime(2026, 3, 15, 1, 0, tzinfo=timezone.utc)
ED = '<td class="column-1">ED</td><td class="column-2">9 AM to 9 PM</td>'
HESITATION = '<td class="column-1">HESITATION</td>'


def page(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new)


def lifts_of(feed: dict) -> dict:
    return {lift["Name"]: lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]}


def test_the_page_is_the_resort_s_lift_status_page():
    assert hoodoo.URL == "https://hoodoo.com/the-mountain/mountain-lift-status/"


def test_on_the_day_of_its_report_the_lifts_scheduled_are_open_and_the_trails_read_as_written():
    # Hoodoo's report for Saturday, March 14, 2026, still up on 2026-11-26: six lifts with five scheduled, 42 trails.
    feed = hoodoo.parse(PAGE, MIDDAY)
    assert feed["Name"] == "Hoodoo" and feed["LastUpdate"] == "2026-03-14T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Hoodoo", 6, 42)]
    assert lifts_of(feed) == {"Harold's Magic Carpet": "open", "Easy Rider": "open", "Manzanita": "open", "Ed": "open",
                              "Big Green Machine": "open", "Hodag": "closed"}
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Harold's Magic Carpet", "Status": "Open",
                                                    "StatusEnglish": "open", "Difficulty": None}
    trails = feed["MountainAreas"][0]["Trails"]
    assert trails[0] == {"Name": "OVER EASY, LOWER (Below top of Manzanita)", "Status": "Open",
                         "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"}
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 30
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 12
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["THREE CREEKS"]["Difficulty"] == "Blue" and by_name["THREE CREEKS"]["Grooming"] == "No"
    assert by_name["FACE"] == {"Name": "FACE", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black",
                               "Grooming": "No"}
    # "DIFFICULT" is written beside the black diamond of "MOST DIFFICULT".
    assert by_name["DIVE"]["Difficulty"] == "Black"
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}


def test_a_lift_is_open_only_during_the_hours_it_is_scheduled():
    # In the evening the lifts scheduled until 4 PM have stopped and the ones lit until 9 PM are still turning.
    assert lifts_of(hoodoo.parse(PAGE, EVENING)) == {
        "Harold's Magic Carpet": "closed", "Easy Rider": "open", "Manzanita": "open", "Ed": "open",
        "Big Green Machine": "closed", "Hodag": "closed"}
    early = datetime(2026, 3, 14, 15, 30, tzinfo=timezone.utc)
    assert set(lifts_of(hoodoo.parse(PAGE, early)).values()) == {"closed"}
    half_past = page(ED, ED.replace("9 AM to 9 PM", "8:30 AM to 9 PM"))
    assert lifts_of(hoodoo.parse(half_past, early))["Ed"] == "open"


def test_an_old_report_reads_as_a_closed_mountain():
    feed = hoodoo.parse(PAGE, NOW)
    rows = feed["MountainAreas"][0]["Lifts"] + feed["MountainAreas"][0]["Trails"]
    assert len(rows) == 48 and {row["StatusEnglish"] for row in rows} == {"closed"}
    assert all(trail["Grooming"] == "No" for trail in feed["MountainAreas"][0]["Trails"])
    # The day after the report, at an hour its lifts were scheduled.
    next_day = datetime(2026, 3, 15, 18, 0, tzinfo=timezone.utc)
    assert set(lifts_of(hoodoo.parse(PAGE, next_day)).values()) == {"closed"}


def test_the_snow_report_gives_the_base_depth_dated_the_hour_it_was_read():
    snow = hoodoo.parse(PAGE, MIDDAY)["SnowReport"]
    # "Base (as of 2 AM): 16 inches" on March 14, seven hours behind UTC in daylight time.
    assert snow["LastUpdate"] == "2026-03-14T09:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 16, "Last24HoursIn": 0}
    assert snow["SeasonTotalIn"] is None and snow["BaseConditions"] is None
    assert hoodoo.parse(PAGE, NOW)["SnowReport"] == snow
    fresh = page("We have received no new snow since yesterday.", "4 inches in the last 24 hours.")
    assert hoodoo.parse(fresh, MIDDAY)["SnowReport"]["BaseArea"] == {"Name": "Base", "BaseIn": 16, "Last24HoursIn": 4}
    vague = page("We have received no new snow since yesterday.", "A dusting up top.")
    assert hoodoo.parse(vague, MIDDAY)["SnowReport"]["BaseArea"] == {"Name": "Base", "BaseIn": 16}


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = hoodoo.parse(page("</b> 16 inches<br />", "</b> thin<br />"), MIDDAY)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 6


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="does not say what day"):
        hoodoo.parse(page("Grooming Information for Saturday, March 14, 2026", "Grooming Information"), MIDDAY)
    with pytest.raises(ValueError, match="does not say what day"):
        hoodoo.parse("<html><body>Just a moment...</body></html>", MIDDAY)
    with pytest.raises(ValueError, match="0 lift tables"):
        hoodoo.parse(page('<th class="column-2">HOURS</th>', '<th class="column-2">STATUS</th>'), MIDDAY)
    with pytest.raises(ValueError, match="0 trail tables"):
        hoodoo.parse(page('<th class="column-3">Status</th>', '<th class="column-3">Open</th>'), MIDDAY)
    with pytest.raises(ValueError, match="Ed has hours the reader does not know"):
        hoodoo.parse(page(ED, ED.replace("9 AM to 9 PM", "WIND HOLD")), MIDDAY)
    with pytest.raises(ValueError, match="do not run forwards"):
        hoodoo.parse(page(ED, ED.replace("9 AM to 9 PM", "9 PM to 9 AM")), MIDDAY)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        hoodoo.parse(page("/>EASIER</td>", "/>EASY</td>"), MIDDAY)
    with pytest.raises(ValueError, match="status the reader does not know"):
        hoodoo.parse(page('<td class="column-3">CLOSED</td>', '<td class="column-3">ON HOLD</td>'), MIDDAY)
    with pytest.raises(ValueError, match="grooming the reader does not know"):
        hoodoo.parse(page("red-x-e1537406111797.png", "question-mark.png"), MIDDAY)
    with pytest.raises(ValueError, match="lists a lift or a trail twice"):
        hoodoo.parse(page(HESITATION, '<td class="column-1">THREE CREEKS</td>'), MIDDAY)
