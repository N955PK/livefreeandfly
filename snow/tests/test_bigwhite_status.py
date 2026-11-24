from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bigwhite

FIXTURES = Path(__file__).parent / "fixtures"
# Of each page, only the block its figures are in; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"bigwhite_{name}.html").read_text() for name in bigwhite.URLS}
NOW = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_closed_mountain_reads_each_lift_with_the_runs_under_it():
    # Big White's pages on 2026-11-24, nine days before it opens: 17 lifts and 119 runs, all closed.
    feed = bigwhite.parse(PAGES, NOW)
    assert feed["Name"] == "Big White" and feed["LastUpdate"] == "2026-11-24T23:30:00Z"
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert len(areas) == 17 and all(len(area["Lifts"]) == 1 for area in areas.values())
    assert areas["Bullet Express Quad"]["Lifts"] == [{"Name": "Bullet Express Quad", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": None}]
    assert areas["Gem Lake Express Quad"]["Lifts"][0]["StatusEnglish"] == "closed"
    assert (len(areas["Gem Lake Express Quad"]["Trails"]), len(areas["Ridge Rocket Express Quad"]["Trails"])) == (31, 24)
    assert areas["Snow Ghost Express 6 Pack"]["Trails"] == []
    assert areas["Bullet Express Quad"]["Trails"][0] == {"Name": "Easy Street", "Status": "Closed",
                                                         "StatusEnglish": "closed", "Difficulty": "Green",
                                                         "Grooming": "No"}
    rows = [row for area in areas.values() for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 17 + 119 and {row["StatusEnglish"] for row in rows} == {"closed"}
    trails = [trail for area in areas.values() for trail in area["Trails"]]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = bigwhite.parse(PAGES, NOW)["SnowReport"]
    # "November 24th, 2026 8:25 AM MST", seven hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T15:25:00Z" and snow["Resortwide"] is True
    # 7 cm of base, 3 cm in 24 hours, 5 cm in 7 days and 39 cm this season.
    assert snow["BaseArea"] == {"Name": "Alpine", "Last24HoursIn": 1.2, "Last7DaysIn": 2.0, "BaseIn": 2.8}
    assert snow["SeasonTotalIn"] == 15.4 and snow["BaseConditions"] is None
    said = bigwhite.parse(page("snow", "Conditions<br />\n              <span class=\"bigger-font\"></span>",
                               "Conditions<br />\n              <span class=\"bigger-font\">Packed Powder</span>", 1),
                          NOW)["SnowReport"]
    assert said["BaseConditions"] == "Packed Powder"
    evening = page("snow", "November 24th, 2026 8:25 AM MST", "November 24th, 2026 18:58 PM MST")
    assert bigwhite.parse(evening, NOW)["SnowReport"]["LastUpdate"] == "2026-11-25T01:58:00Z"


def test_an_open_lift_and_open_and_groomed_runs_are_read():
    pages = page("lifts", "<i>Closed</i>", "<i>Open</i>", 2)
    pages = {**pages, "lifts": pages["lifts"].replace("Closed (17)", "Closed (15)")}
    pages["trails"] = (PAGES["trails"].replace("closed_icon.png\" srcset=\"/themes/custom/ht_bigwhite/images/icons/"
                                               "grooming/closed_icon@2x.png 2x\" alt=\"Closed\" title=\"Closed\"",
                                               "groomed_icon.png\" alt=\"Groomed\" title=\"Groomed\"", 1)
                       .replace("alt=\"Closed\" title=\"Closed\"", "alt=\"Open\" title=\"Open\"", 1)
                       .replace("Closed (119)", "Closed (117)"))
    feed = bigwhite.parse(pages, NOW)
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] == "open"] == ["Lara’s Gondola (free access)",
                                                                                   "Bullet Express Quad"]
    trails = feed["MountainAreas"][0]["Trails"]
    assert [(trail["Name"], trail["Status"], trail["Grooming"]) for trail in trails] == [
        ("Happy Valley Way", "Open", "Yes"), ("Nordic Trails", "Open", "No"), ("Ice Skating Rink", "Closed", "No")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="liftstatusblock was not found"):
        bigwhite.parse(page("lifts", "block-liftstatusblock", "block-lifts"), NOW)
    with pytest.raises(ValueError, match="counts 16 closed lifts but 17"):
        bigwhite.parse(page("lifts", "Closed (17)", "Closed (16)"), NOW)
    with pytest.raises(ValueError, match="lists 17 lifts but 16"):
        bigwhite.parse(page("lifts", "<i>Closed</i>", "<b>Closed</b>", 1), NOW)
    with pytest.raises(ValueError, match="status pictures"):
        bigwhite.parse(page("trails", "alt=\"Closed\" title=\"Closed\"", "alt=\"Shut\" title=\"Shut\"", 1), NOW)
    with pytest.raises(ValueError, match="difficulty pictures"):
        bigwhite.parse(page("trails", "alt=\"double_black\"", "alt=\"triple_black\"", 1), NOW)
    with pytest.raises(ValueError, match="counts 118 closed runs but 119"):
        bigwhite.parse(page("trails", "Closed (119)", "Closed (118)"), NOW)
    # A run's row that has lost its shape runs into the next one, and is refused there.
    with pytest.raises(ValueError, match="Nordic Trails has difficulty pictures"):
        bigwhite.parse(page("trails", "small-10 columns run-name", "small-10 columns name", 1), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("7&nbsp;cm", "7&nbsp;in"), ("8:25 AM MST", "8:25 AM XST"), ("Alpine snow Base", "Snow Base"),
                     ("id=\"metric\"", "id=\"metres\"")):
        feed = bigwhite.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 17
