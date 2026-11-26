from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import mtspokane

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"mtspokane_{name}.html").read_text() for name in mtspokane.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CELL = '<td class="cell" data-auto="table-cell">'


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def in_season() -> str:
    """The conditions page with figures where it reads "N/A" before the mountain opens."""
    page = PAGES["snow"]
    assert page.count(">N/A<") == 9
    for figure in ('38"', '61.5"', '4"', '7"', "Packed Powder", "Machine Groomed", "Good", "5 mph", "44"):
        page = page.replace(">N/A<", f">{figure}<", 1)
    return page


def test_the_preseason_mountain_reads_each_heading_s_chairs_with_the_trails_under_it():
    # Mt. Spokane's pages on 2026-11-26, before opening: eight lifts and 62 trails, all closed.
    feed = mtspokane.parse(PAGES, NOW)
    assert feed["Name"] == "Mt. Spokane" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Vista Cruiser, Chair 1", ["Vista Cruiser, Chair 1"], 18),
        ("Illuminator, Chair 2/Parkway Express, Chair 3", ["Illuminator, Chair 2", "Parkway Express, Chair 3"], 20),
        ("Hidden Treasure, Chair 4", ["Hidden Treasure, Chair 4"], 12),
        # Short Shot and Johnson's Run are listed under chairs 2 and 3 as well: each is read once.
        ("Beginner's Luck, Chair 5", ["Beginner's Luck, Chair 5"], 1),
        ("Northwood, Chair 6", ["Northwood, Chair 6"], 11),
        # The terrain parks and the uphill route are rows of the table of lifts, and are not lifts.
        ("Other lifts", ["Sunkid Conveyor", "Half Hitch Handle Tow"], 0)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Vista Cruiser, Chair 1", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Al's Alley", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": None, "Grooming": "No"}
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 70 and {row["StatusEnglish"] for row in rows} == {"closed"}
    trails = [trail["Name"] for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 62 == len(set(trails))


def test_before_the_mountain_opens_there_is_no_snow_report():
    # The conditions table reads "N/A" throughout.
    assert "SnowReport" not in mtspokane.parse(PAGES, NOW)


def test_the_snow_report_gives_the_base_and_the_summit_and_the_day_it_was_updated():
    snow = mtspokane.parse({**PAGES, "snow": in_season()}, NOW)["SnowReport"]
    # "Updated Tuesday, Nov 24": the year is the one the page is read in, and the report is posted at five.
    assert snow["LastUpdate"] == "2026-11-24T13:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 38, "Last24HoursIn": 4, "Last48HoursIn": 7}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 61.5}
    assert snow["BaseConditions"] == "Packed Powder" and snow["SeasonTotalIn"] is None


def test_a_report_from_the_end_of_december_read_in_january_is_dated_to_the_year_before():
    page = in_season().replace("Updated Tuesday, Nov 24", "Updated Thursday, Dec 31")
    snow = mtspokane.parse({**PAGES, "snow": page}, datetime(2027, 1, 1, 18, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-12-31T13:00:00Z"


def test_open_lifts_and_groomed_trails_are_read():
    pages = lifts_page(f"{CELL}Closed</td>", f"{CELL}Open</td>", 12)
    pages = {**pages, "lifts": pages["lifts"].replace(f"{CELL}No</td>", f"{CELL}PM</td>", 1)}
    feed = mtspokane.parse(pages, NOW)
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert len(lifts) == 8 and {lift["StatusEnglish"] for lift in lifts} == {"open"}
    trails = feed["MountainAreas"][0]["Trails"]
    assert [(trail["StatusEnglish"], trail["Grooming"]) for trail in trails[:3]] == [
        ("open", "Yes"), ("open", "No"), ("closed", "No")]


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = mtspokane.parse(lifts_page(f"{CELL}Closed</td>", f"{CELL}On Hold</td>", 1), NOW)
    lift = feed["MountainAreas"][3]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Beginner's Luck, Chair 5", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="table of lifts and their statuses was not found once"):
        mtspokane.parse(lifts_page(">Lift/Area Name</th>", ">Lift</th>"), NOW)
    with pytest.raises(ValueError, match="not chairs of the table of lifts"):
        mtspokane.parse(lifts_page(">Northwood, Chair 6</span></h4>", ">Northwood</span></h4>"), NOW)
    with pytest.raises(ValueError, match="not chairs of the table of lifts"):
        mtspokane.parse(lifts_page("<h4", "<h3"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        mtspokane.parse(lifts_page(f"{CELL}Sunkid Conveyor</td>", f"{CELL}Half Hitch Handle Tow</td>"), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        page = PAGES["lifts"].replace(">GROOMED</th>", ">Notes</th>").replace(">Groomed</th>", ">Notes</th>")
        mtspokane.parse({**PAGES, "lifts": page}, NOW)
    with pytest.raises(ValueError):
        mtspokane.parse({**PAGES, "lifts": "<html><body>Not the page</body></html>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (('>38"<', ">deep<"), ("Updated Tuesday, Nov 24", "Updated this morning"),
                     ("Updated Tuesday, Nov 24", "Updated Monday, Nov 24"), (">Summit Depth<", ">Top Depth<")):
        page = in_season()
        assert old in page
        feed = mtspokane.parse({**PAGES, "snow": page.replace(old, new)}, NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
