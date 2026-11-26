from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import monarch

# The page as the site gave it on 2026-11-26, before the season: every lift and trail closed.
PAGE = (Path(__file__).parent / "fixtures" / "monarch.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED = '<span style="color: red; font-weight: normal;">Closed</span>'
GREEN = '<circle cx="15" cy="15" r="14" fill="#4CAF50"/>'
NOT_GROOMED = ('<td class="td_center_data" data-label="Groomed">\n'
               '                                                    </td>')


def page(old: str, new: str, count: int = 1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_preseason_mountain_reads_its_lifts_and_trails_by_part_of_the_mountain():
    feed = monarch.parse(PAGE, NOW)
    assert feed["Name"] == "Monarch Mountain" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Frontside Terrain", ["Garfield", "Pioneer", "Tumbelina"], 32),
        ("Learning Areas", ["Caterpillar", "Safari"], 3), ("Panorama Ridge", ["Panorama"], 15),
        ("Breezeway Terrain", ["Breezeway"], 10), ("No Name Basin", ["Tomichi"], 12), ("Mirkwood Basin", [], 8)]
    lifts, trails = rows(feed, "Lifts"), rows(feed, "Trails")
    # The page counts nine lifts; the ninth is the tubing park's, which is left out.
    assert len(lifts) == 8 and not [lift for lift in lifts if "Tubing" in lift["Name"]]
    assert lifts[0] == {"Name": "Garfield", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert len(trails) == 80 and {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "Drifter", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["Skywalker"]["Difficulty"] == "Green" and by_name["Gunbarrel"]["Difficulty"] == "Black"
    assert by_name["Freeway"]["Difficulty"] == "Blue" and by_name["Butterfly ( Lessons Only )"]["Difficulty"] == "Green"
    # The terrain parks' orange oval is no difficulty, and the hike-to basin's picture is "Expert Only".
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == ""] == ["Ricochet", "Tilt", "Steel City"]
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == "Double black"] == [
        "East Trees", "Elation", "Lodgeview", "Mirkwood Bowl", "Mirkwood Trees", "Orcs", "Staircase"]


def test_the_snow_report_gives_the_base_depth_the_snowfall_and_when_it_was_updated():
    snow = monarch.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated: November 25, 2026 - 07:24 AM", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-25T14:24:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "OvernightIn": 0, "Last24HoursIn": 0, "Last48HoursIn": 5,
                                "Last7DaysIn": 8, "BaseIn": 16}
    assert snow["SeasonTotalIn"] == 32 and snow["BaseConditions"] is None


def test_an_open_lift_and_an_open_groomed_trail_take_the_page_s_words():
    opened = PAGE.replace(CLOSED, '<span style="color: green; font-weight: normal;">Open</span>', 10)
    groomed = '<td class="td_center_data" data-label="Groomed">\n<span>&#10003;</span></td>'
    opened = opened.replace(NOT_GROOMED, groomed, 1)
    opened = opened.replace("Lifts Open:\n            0 of", "Lifts Open:\n            9 of")
    opened = opened.replace("Trails Open:\n            0 of", "Trails Open:\n            1 of")
    feed = monarch.parse(opened, NOW)
    assert {lift["Status"] for lift in rows(feed, "Lifts")} == {"Open"}
    assert rows(feed, "Trails")[0] == {"Name": "Drifter", "Status": "Open", "StatusEnglish": "open",
                                       "Difficulty": "Green", "Grooming": "Yes"}
    assert rows(feed, "Trails")[1]["StatusEnglish"] == "closed" and rows(feed, "Trails")[1]["Grooming"] == "No"
    held = monarch.parse(page(CLOSED, "<span>ON HOLD</span>"), NOW)
    lift = held["MountainAreas"][3]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Breezeway", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift table was not found"):
        monarch.parse(page('<table class="lifts-table">', '<table class="lifts">'), NOW)
    with pytest.raises(ValueError, match="Breezeway has no status"):
        monarch.parse(page(CLOSED, ""), NOW)
    with pytest.raises(ValueError, match="counts 0 of 10 lifts open but 0 of 9"):
        monarch.parse(page("0 of\n            9 ", "0 of\n            10 "), NOW)
    with pytest.raises(ValueError, match="counts 0 of 9 lifts open but 1 of 9"):
        monarch.parse(page(CLOSED, "<span>Open</span>"), NOW)
    with pytest.raises(ValueError, match="counts 0 of 81 trails open but 0 of 80"):
        monarch.parse(page("0 of\n            80 ", "0 of\n            81 "), NOW)
    with pytest.raises(ValueError, match="count of lifts was not found"):
        monarch.parse(page("Lifts Open:", "Lifts:"), NOW)
    with pytest.raises(ValueError, match="Drifter has a difficulty the reader does not know"):
        monarch.parse(page(GREEN, '<circle cx="15" cy="15" r="14" fill="#9C27B0"/>'), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        monarch.parse(page(NOT_GROOMED, ""), NOW)
    with pytest.raises(ValueError, match="no name or no table of trails"):
        monarch.parse(page('<table class="trails-table">', '<table class="trails">'), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        monarch.parse(PAGE.replace('data-label="Lift Name"', 'data-label="Lift"'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = monarch.parse(page("Last Updated: November 25, 2026 - 07:24 AM", "Last Updated: this morning"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 8
    assert "SnowReport" not in monarch.parse(page('<table class="accumulation__table">', "<table>"), NOW)
    assert "SnowReport" not in monarch.parse(page('16"\n                    </th>', "16 cm</th>"), NOW)
    assert "SnowReport" not in monarch.parse(page("Base                        </td>", "Depth</td>"), NOW)
