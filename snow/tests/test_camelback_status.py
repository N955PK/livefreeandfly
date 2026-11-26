from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import camelback

# The report with its scripts, styles and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "camelback.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
OPEN = '<i class="pti pti-open"></i><span class="SnowReport-sr-label">Open</span>'
CLOSED = '<i class="pti pti-closed"></i><span class="SnowReport-sr-label">Closed</span>'
# The page as it would be with the four lifts left marked open from the spring closed like the rest.
SHUT = PAGE.replace(OPEN, CLOSED)


def changed(page: str, old: str, new: str, count: int = -1) -> str:
    assert old in page
    return page.replace(old, new, count)


def test_the_page_before_the_season_counts_no_lifts_open_but_marks_four_open_and_is_refused():
    # Camelback's report on 2026-11-26, last written on November 5: "0 Lifts" open and every trail closed, with
    # Bailey, Meadows, Raceway and The Glen still marked open.
    assert PAGE.count(OPEN) == 4
    with pytest.raises(ValueError, match="counts no lifts open but marks 4 open"):
        camelback.parse(PAGE, NOW)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed():
    feed = camelback.parse(SHUT, NOW)
    assert feed["Name"] == "Camelback" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Camelback", 13, 46)]
    rows = feed["MountainAreas"][0]["Lifts"] + feed["MountainAreas"][0]["Trails"]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Stevenson Express"] == {"Name": "Stevenson Express", "Status": "Closed", "StatusEnglish": "closed",
                                          "Difficulty": None}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][0]["Trails"]}
    assert trails["Birches"] == {"Name": "Birches", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Green", "Grooming": "No"}
    assert (trails["King Tut"]["Difficulty"], trails["Asp"]["Difficulty"], trails["Cliffhanger"]["Difficulty"]) == (
        "Blue", "Black", "Double black")
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black")] == [18, 17, 7, 4]


def test_before_the_season_the_snow_report_has_no_depth():
    snow = camelback.parse(SHUT, NOW)["SnowReport"]
    # "10:15am, November 05, 2026", in Eastern time.
    assert snow["LastUpdate"] == "2026-11-05T15:15:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": None, "Last24HoursMinIn": None, "Last24HoursMaxIn": None,
                                "Last48HoursIn": None}
    assert snow["BaseConditions"] == "Variable Conditions" and snow["SeasonTotalIn"] == 0
    assert "We will be closed today" in snow["Report"]


def test_the_open_mountain_reads_its_open_lifts_and_its_depth():
    page = changed(PAGE, "<dt>Open Lifts</dt><dd>0 Lifts</dd>", "<dt>Open Lifts</dt><dd>4 Lifts</dd>")
    page = changed(page, "<dt>Base Depth</dt><dd> in.</dd>", "<dt>Base Depth</dt><dd>24 - 36 in.</dd>")
    page = changed(page, "<dt>Past 24 Hours</dt><dd> in.</dd>", "<dt>Past 24 Hours</dt><dd>3 in.</dd>")
    feed = camelback.parse(page, NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] == "open"] == [
        "Bailey", "Meadows", "Raceway", "The Glen"]
    area = feed["SnowReport"]["BaseArea"]
    assert (area["BaseIn"], area["BaseMinIn"], area["BaseMaxIn"], area["Last24HoursIn"]) == (30, 24, 36, 3)


def test_a_held_lift_and_a_groomed_trail_take_the_report_s_words():
    start = SHUT.index("Black Bear 6")
    page = SHUT[:start] + SHUT[start:].replace("pti-closed", "pti-hold", 1).replace(">Closed<", ">On Hold<", 1)
    lifts = {lift["Name"]: lift for lift in camelback.parse(page, NOW)["MountainAreas"][0]["Lifts"]}
    assert lifts["Black Bear 6"] == {"Name": "Black Bear 6", "Status": "On hold", "StatusEnglish": "on hold",
                                     "Difficulty": None}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="count of open lifts was not found"):
        camelback.parse(changed(SHUT, "<dt>Open Lifts</dt>", "<dt>Lifts Spinning</dt>"), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        camelback.parse(changed(SHUT, '<h3 class="SnowReport-feature-title">Birches</h3>', "<h4>Birches</h4>", 1), NOW)
    with pytest.raises(ValueError, match="lists 59 lifts and trails but 41"):
        camelback.parse(changed(SHUT, '<section class="SnowReport-section SnowReport-section--trails">',
                                '<section class="SnowReport-section SnowReport-section--runs">', 1), NOW)
    with pytest.raises(ValueError, match="posted"):
        camelback.parse(changed(SHUT, "10:15am, November 05, 2026", "this morning"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        camelback.parse("<html><body>Not the page</body></html>", NOW)
