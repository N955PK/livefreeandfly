from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import ashland

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGE = (FIXTURES / "ashland.html").read_text()
MIDSEASON = (FIXTURES / "ashland_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def rows_of(feed: dict) -> list:
    return [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]


def changed(old: str, new: str, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed():
    # Mt. Ashland's report on 2026-11-24, before its season: six lifts and 43 trails, all closed.
    feed = ashland.parse(PAGE, NOW)
    assert feed["Name"] == "Mt. Ashland" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mt. Ashland", 6, 0), ("Sonnet & Lithia Terrain Pods", 0, 5), ("Comer & Windsor Terrain Pods", 0, 17),
        ("Ariel Terrain Pod", 0, 21)]
    assert {row["StatusEnglish"] for row in rows_of(feed)} == {"closed"} and all(row["Name"] for row in rows_of(feed))
    lifts = feed["MountainAreas"][0]["Lifts"]
    # "Sonnet Triple Chair (easiest)" loses its note, and the table's "Uphill Access" row, which says Open, is no lift.
    assert [lift["Name"] for lift in lifts] == ["First Act Learning Carpet", "Sonnet Triple Chair",
                                                "Lithia Triple Chair", "Comer Triple Chair", "Windsor Double Chair",
                                                "Ariel Double Chair"]
    assert lifts[5] == {"Name": "Ariel Double Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    areas = {area["Name"]: area["Trails"] for area in feed["MountainAreas"]}
    assert areas["Sonnet & Lithia Terrain Pods"][0] == {"Name": "Sonnet", "Status": "Closed", "StatusEnglish": "closed",
                                                        "Difficulty": "Green", "Grooming": "No"}
    # Bumblebee's picture is the blue square though its caption says green circle; the chutes are double diamonds.
    assert areas["Sonnet & Lithia Terrain Pods"][2]["Difficulty"] == "Blue"
    assert [trail["Name"] for trail in rows_of(feed) if trail["Difficulty"] == "Double black"] == [
        "Chute 1", "Chute 2", "Chute 3", "Chute 4", "Chute 5"]
    assert {trail["Difficulty"] for area in areas.values() for trail in area} == {"Green", "Blue", "Black",
                                                                                  "Double black"}


def test_the_snow_report_gives_the_three_depths_and_when_it_was_updated():
    snow = ashland.parse(PAGE, NOW)["SnowReport"]
    # "Updated November 10, 2026 at 6:20 PM", eight hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-11T02:20:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Lower Mountain", "Last24HoursIn": 0, "Last7DaysIn": 0, "BaseIn": 0}
    assert snow["MidMountainArea"] == {"Name": "Mid-Mountain", "BaseIn": 0}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 0}
    # The surface reads "Ski Area Closed", which is no surface; the season's total is still last season's.
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 82


def test_the_open_mountain_reads_its_open_lifts_and_its_groomed_trails():
    # The report on 2026-03-02 as the Internet Archive kept it: five lifts turning, 33 trails open, 14 of them groomed.
    feed = ashland.parse(MIDSEASON, NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    # "Open 9am - 9pm" is open.
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in lifts] == [
        ("First Act Learning Carpet", "open"), ("Sonnet Triple Chair", "closed"), ("Lithia Triple Chair", "open"),
        ("Comer Triple Chair", "open"), ("Windsor Double Chair", "open"), ("Ariel Double Chair", "open")]
    assert lifts[2]["Status"] == "Open"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 43 and {trail["Status"] for trail in trails} == {"Open", "Closed"}
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 33
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 14
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["Sonnet"] == {"Name": "Sonnet", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                                 "Grooming": "Yes"}
    assert by_name["Mercutio"]["StatusEnglish"] == "open" and by_name["Mercutio"]["Grooming"] == "No"
    assert by_name["Chute 1"]["StatusEnglish"] == "closed"
    snow = feed["SnowReport"]
    assert snow["LastUpdate"] == "2026-03-02T20:40:00Z"
    assert (snow["BaseArea"]["BaseIn"], snow["MidMountainArea"]["BaseIn"], snow["SummitArea"]["BaseIn"]) == (14, 29, 24)


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = ashland.parse(changed("<td>Comer Triple Chair</td>\n<td style=\"text-align: center;\">Closed</td>",
                                 "<td>Comer Triple Chair</td>\n<td style=\"text-align: center;\">Wind Hold</td>"), NOW)
    lift = feed["MountainAreas"][0]["Lifts"][3]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Comer Triple Chair", "Wind Hold", "wind hold")


def test_a_depth_given_as_a_range_is_carried_as_its_two_ends():
    page = changed("29\"</span>", "24-30&#8243;</span>", MIDSEASON)
    assert ashland.parse(page, NOW)["SnowReport"]["MidMountainArea"] == {
        "Name": "Mid-Mountain", "BaseIn": None, "BaseMinIn": 24, "BaseMaxIn": 30}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="table of lifts was not found"):
        ashland.parse(changed("Chairlift Status</h1>", "Lift Status</h1>"), NOW)
    with pytest.raises(ValueError, match="Chair Lift and Status headings"):
        ashland.parse(changed("Chair Lift</span>", "Lift</span>"), NOW)
    with pytest.raises(ValueError, match="trail report was not found"):
        ashland.parse(changed("Ski Trail Status Report</h1>", "Trails</h1>"), NOW)
    with pytest.raises(ValueError, match="Lupine has difficulty pictures"):
        ashland.parse(changed("Lupine</span></td>\n<td style=\"text-align: center;\"><img decoding=\"async\" data-src="
                              "\"https://www.mtashland.com/wp-content/uploads/2015/12/Blue_Square.gif\"",
                              "Lupine</span></td>\n<td style=\"text-align: center;\"><img decoding=\"async\" data-src="
                              "\"https://www.mtashland.com/wp-content/uploads/2015/12/Orange_Oval.gif\""), NOW)
    with pytest.raises(ValueError, match="no name over it"):
        ashland.parse(changed("<strong>Ariel Terrain Pod</strong>", "Ariel Terrain Pod"), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        ashland.parse(changed("<td>Lithia Triple Chair</td>\n<td style=\"text-align: center;\">Closed</td>",
                              "<td>Lithia Triple Chair</td>\n<td style=\"text-align: center;\"></td>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = ashland.parse(changed("29\"</span>", "deep</span>", MIDSEASON), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 6
    assert "SnowReport" not in ashland.parse(changed("Mid-Mountain</span>", "Halfway</span>"), NOW)
    undated = ashland.parse(PAGE.replace("November 10, 2026 at 6:20 PM", "this morning"), NOW)["SnowReport"]
    assert undated["LastUpdate"] is None
