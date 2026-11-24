import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import marmot

FIXTURES = Path(__file__).parent / "fixtures"
# Of each page, only the block its figures are in, with its drawings taken out; the reader gives the same on the
# whole pages.
PAGES = {name: (FIXTURES / f"marmot_{name}.html").read_text() for name in marmot.URLS}
NOW = datetime(2026, 11, 24, 23, 40, tzinfo=timezone.utc)
# The status word of the row under a name, as a pattern whose first group is everything before the word.
STATUS = r"({name}\s*</h3>.*?<div class=\"lf-status-icon[^\"]*\">.*?</div>\s*){word}"


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def reworded(name: str, pattern: str, new: str) -> dict:
    """The pages with the first match of a pattern on one of them replaced."""
    changed, count = re.subn(pattern, new, PAGES[name], count=1, flags=re.S)
    assert count == 1
    return {**PAGES, name: changed}


def test_the_early_season_mountain_reads_its_lifts_and_its_trails_by_part():
    # Marmot Basin on 2026-11-24: 3 of 7 lifts and 2 of 94 trails open.
    feed = marmot.parse(PAGES, NOW)
    assert feed["Name"] == "Marmot Basin" and feed["LastUpdate"] == "2026-11-24T23:40:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Marmot Basin", 7, 0), ("Lower Mountain", 0, 22), ("Upper Mountain", 0, 32), ("Eagle Ridge Area", 0, 27),
        ("Knob Area", 0, 13)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Magic Carpet", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] == "open"] == [
        "Magic Carpet", "School House Triple", "Eagle Express Quad"]
    assert lifts[-1] == {"Name": "Knob Quad", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 94
    assert trails["Tranquilizer"] == {"Name": "Tranquilizer", "Status": "Open", "StatusEnglish": "open",
                                      "Difficulty": "Green", "Grooming": "Yes"}
    assert trails["School House"] == {"Name": "School House", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": "Green", "Grooming": "No"}
    assert [name for name, trail in trails.items() if trail["StatusEnglish"] == "open"] == ["Tranquilizer",
                                                                                           "Sleepy Hollow"]
    # The terrain parks are marked orange and have no difficulty.
    assert [name for name, trail in trails.items() if trail["Difficulty"] == ""] == ["Lower Park", "Mini Rail Park",
                                                                                    "Terrain Park"]
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = marmot.parse(PAGES, NOW)["SnowReport"]
    # "Nov. 24, 2026, 12:55 p.m.": Alberta keeps one time all year, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T18:55:00Z" and snow["Resortwide"] is True
    # A trace in 24 hours, 5 cm in 7 days, 20 cm of base and 35 cm this season.
    assert snow["BaseArea"] == {"Name": "Marmot Basin", "Last24HoursIn": 0.0, "Last7DaysIn": 2.0, "BaseIn": 7.9}
    assert snow["SeasonTotalIn"] == 13.8 and snow["BaseConditions"] is None
    fell = marmot.parse(page("snow", ">Trace<", ">12 cm<"), NOW)["SnowReport"]
    assert fell["BaseArea"]["Last24HoursIn"] == 4.7


def test_the_time_of_the_update_is_read_however_the_page_writes_it():
    for said, stamp in (("March 3, 2027, 7 a.m.", "2027-03-03T13:00:00Z"), ("Dec. 31, 2026, noon", "2026-12-31T18:00:00Z"),
                        ("Sept. 30, 2026, midnight", "2026-09-30T06:00:00Z"),
                        ("Jan. 9, 2027, 12:05 a.m.", "2027-01-09T06:05:00Z")):
        snow = marmot.parse(page("snow", "Nov. 24, 2026, 12:55 p.m.", said), NOW)["SnowReport"]
        assert snow["LastUpdate"] == stamp


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Magic Carpet has a status the reader does not know: \\['hold'\\]"):
        marmot.parse(reworded("lifts", STATUS.format(name="Magic Carpet", word="open"), r"\1hold"), NOW)
    with pytest.raises(ValueError, match="School House has difficulty symbols \\['purple'\\]"):
        marmot.parse(page("lifts", "#icon-green", "#icon-purple", 1), NOW)
    with pytest.raises(ValueError, match="Tranquilizer has a status the reader does not know: \\['open', 'Icy'\\]"):
        marmot.parse(page("lifts", "Groomed", "Icy", 1), NOW)
    with pytest.raises(ValueError, match="a group the reader does not know: Nordic Trails"):
        marmot.parse(page("lifts", "<h2>Knob Area Trail Status</h2>", "<h2>Nordic Trails</h2>"), NOW)
    with pytest.raises(ValueError, match="does not list its lifts once"):
        marmot.parse(page("lifts", "lf-status-group", "status-group"), NOW)
    # A row that has lost its status is refused.
    with pytest.raises(ValueError, match="Home Run has a status the reader does not know: \\[\\]"):
        marmot.parse(reworded("lifts", r"(Home Run\s*</h3>\s*<div class=\"lf-status-container\">\s*)"
                                       r"<div class=\"lf-status-status\">", r"\1<div class=\"status\">"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in ((">20 cm<", ">20 in<"), ("Nov. 24, 2026, 12:55 p.m.", "this afternoon"),
                     (">Snow Base<", ">Depth<"), (">Last 24 Hours<", ">Today<"),
                     ("Snow Report</h3>", "Snow</h3>")):
        feed = marmot.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
