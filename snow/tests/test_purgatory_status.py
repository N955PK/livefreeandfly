import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import purgatory

FIXTURES = Path(__file__).parent / "fixtures"
# The page and the file its script reads, as the site gave them on 2026-11-26, early season: three lifts open.
PAGES = {"report": (FIXTURES / "purgatory_report.html").read_text(),
         "updated": (FIXTURES / "purgatory_updated.json").read_text()}
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED_GREEN = "m-filter-target m-filter-value-closed m-filter-value-not-groomed m-filter-status m-filter-value-green"
OPEN_LIFT = '<div class="has-m-h-small-font-size m-status m-margin-bottom m-status-open">Open</div>'


def page(old: str, new: str, count: int = 1) -> dict:
    assert old in PAGES["report"]
    return {**PAGES, "report": PAGES["report"].replace(old, new, count)}


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_early_season_mountain_reads_its_lifts_and_trails_by_part_of_the_mountain():
    feed = purgatory.parse(PAGES, NOW)
    assert feed["Name"] == "Purgatory" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Frontside", ["Purgatory Express #1", "Engineer Double #2"], 57),
        ("Columbine Beginner Area", ["Graduate Triple #7", "Columbine Triple #9", "Columbine Magic Carpet #11"], 6),
        ("Backside", ["Hermosa Park Express #3", "Grizzly Double #5", "Legends Express #8"], 52),
        # The lifts no part of the mountain names.
        ("Purgatory", ["Twilight Double #4", "Needles Triple #6", "Ski School Magic Carpet #10", "Colorado Couloir"], 0)]
    lifts, trails = rows(feed, "Lifts"), rows(feed, "Trails")
    assert len(lifts) == 12
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] == "open"] == [
        "Purgatory Express #1", "Engineer Double #2", "Graduate Triple #7"]
    assert lifts[0] == {"Name": "Purgatory Express #1", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert len(trails) == 115 == len({trail["Name"] for trail in trails})
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 22
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["Westfork"] == {"Name": "Westfork", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                                   "Grooming": "Yes"}
    assert by_name["Cherub"]["Grooming"] == "No" and by_name["Cherub"]["StatusEnglish"] == "open"
    assert by_name["Lower Pandemonium"] == {"Name": "Lower Pandemonium", "Status": "Closed", "StatusEnglish": "closed",
                                            "Difficulty": "Green", "Grooming": "No"}
    assert sorted(name for name, trail in by_name.items() if trail["Grooming"] == "Yes") == [
        "Lower Demon", "Nirvana", "Silvertip", "Upper Demon", "Westfork"]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_gives_the_base_depth_the_snowfall_and_when_the_totals_were_updated():
    snow = purgatory.parse(PAGES, NOW)["SnowReport"]
    # "November 26, 2026 5:48 am" in the file the page's script reads, seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T12:48:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 11,
                                "BaseIn": 20}
    assert snow["SeasonTotalIn"] == 34 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Enjoy top to bottom skiing") and "<" not in snow["Report"]


def test_a_report_whose_time_cannot_be_read_is_given_undated():
    for said in ("<html>", "{}", json.dumps({"conditions_table_updated": "this morning"})):
        snow = purgatory.parse({**PAGES, "updated": said}, NOW)["SnowReport"]
        assert snow["LastUpdate"] is None and snow["BaseArea"]["BaseIn"] == 20
    assert purgatory.parse({"report": PAGES["report"]}, NOW)["SnowReport"]["LastUpdate"] is None


def test_a_lift_on_hold_takes_the_page_s_words():
    held = page(OPEN_LIFT, OPEN_LIFT.replace(">Open<", ">On Hold<"))
    lift = purgatory.parse(held, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Purgatory Express #1", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="the lifts tab was not found"):
        purgatory.parse(page('id="m-tab-lifts"', 'id="tab-lifts"'), NOW)
    with pytest.raises(ValueError, match="the trails tab was not found"):
        purgatory.parse(page('id="m-tab-terrain"', 'id="tab-terrain"'), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        purgatory.parse({**PAGES, "report": PAGES["report"].replace('<li class="m-lift-status-', '<li class="lift-')}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected, or is listed twice"):
        purgatory.parse(page(OPEN_LIFT, "<p>Open</p>"), NOW)
    with pytest.raises(ValueError, match="Purgatory Express #1 has no status"):
        purgatory.parse(page(OPEN_LIFT, OPEN_LIFT.replace(">Open<", "><")), NOW)
    with pytest.raises(ValueError, match="counts 21 trails open on Frontside but 20"):
        purgatory.parse(page("<div>20/57 Trails Open", "<div>21/57 Trails Open"), NOW)
    with pytest.raises(ValueError, match="no name or no count"):
        purgatory.parse(page("<div>20/57 Trails Open", "<div>Trails Open"), NOW)
    with pytest.raises(ValueError, match="Lower Pandemonium has a difficulty the reader does not know: purple"):
        purgatory.parse(page(CLOSED_GREEN, CLOSED_GREEN.replace("value-green", "value-purple")), NOW)
    with pytest.raises(ValueError, match="a trail of Frontside is not in the shape expected"):
        purgatory.parse(page(CLOSED_GREEN, CLOSED_GREEN.replace("m-filter-value-not-groomed ", "")), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = purgatory.parse(page("m-snow-totals-table-header", "m-totals-header"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 12
    assert "SnowReport" not in purgatory.parse(page("20&#8243;        </div>", "20 cm</div>"), NOW)
    assert "SnowReport" not in purgatory.parse(page("Base Depth        </div>", "Depth</div>"), NOW)
