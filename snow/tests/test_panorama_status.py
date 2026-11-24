from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import panorama

FIXTURES = Path(__file__).parent / "fixtures"
# Of each page, only its snow, weather and lift blocks, with the groomer's drawing emptied; the reader gives the
# same on the whole pages. The first is the page on 2026-11-24, ten days before Panorama opens; the second is the
# Internet Archive's copy of it from 2026-02-10, in the middle of the season.
PAGE = (FIXTURES / "panorama.html").read_text()
MIDSEASON = (FIXTURES / "panorama_midseason.html").read_text()
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
ZONES = [("Champagne", 17), ("Discovery Zone", 7), ("Extreme Dream Zone", 19), ("Founder's Ridge", 8),
         ("Mile One", 10), ("Summit", 13), ("Sun Bowl", 18), ("Sunbird", 12), ("Taynton Bowl", 33),
         ("Terrain Park", 3), ("Toby", 5)]
OPEN = "<span class=\"label success\">\n                                                    Open"


def changed(page: str, old: str, new: str, count: int = -1) -> str:
    assert old in page
    return page.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_its_trails_by_zone():
    # 11 lifts and 145 trails, all closed, and no snow figures yet.
    feed = panorama.parse(PAGE, NOW)
    assert feed["Name"] == "Panorama" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Panorama", 11, 0), *((zone, 0, trails) for zone, trails in ZONES)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Village Gondola", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert [lift["Name"] for lift in lifts][-3:] == ["Champagne Express", "Summit Quad", "Monster X Snowcat"]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "World Cup Way", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Blue",
                         "Grooming": "No"}
    assert len(trails) == 145 and {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert [sum(trail["Difficulty"] == level for trail in trails)
            for level in ("Green", "Blue", "Black", "Double black")] == [16, 52, 32, 45]
    assert "SnowReport" not in feed


def test_the_open_mountain_reads_open_lifts_and_groomed_trails():
    # 10 of the 11 lifts turning (the page counts 10 of 10: it leaves the snowcat out), and all 145 trails open, 46
    # of them groomed.
    feed = panorama.parse(MIDSEASON, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Panorama", 11, 0), *((zone, 0, trails) for zone, trails in ZONES)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] != "open"] == ["Monster X Snowcat"]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "World Cup Way", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                         "Grooming": "Yes"}
    assert {trail["StatusEnglish"] for trail in trails} == {"open"}
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 46
    assert [trail["Difficulty"] for trail in feed["MountainAreas"][3]["Trails"]][:1] == ["Black"]


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = panorama.parse(MIDSEASON, NOW)["SnowReport"]
    # 54 cm at the village and 124 cm at the summit; 0 cm overnight and in 24 hours, 2 cm in 48 hours and 7 days,
    # and 406 cm this season. The page does not date the report.
    assert snow["BaseArea"] == {"Name": "Village", "BaseIn": 21.3, "OvernightIn": 0.0, "Last24HoursIn": 0.0,
                                "Last48HoursIn": 0.8, "Last7DaysIn": 0.8}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 48.8}
    assert snow["SeasonTotalIn"] == 159.8 and snow["LastUpdate"] is None and snow["Resortwide"] is False
    assert snow["BaseConditions"] is None and "MidMountainArea" not in snow
    assert snow["Report"].startswith("FEB 9 Firmer conditions") and "<" not in snow["Report"]


def test_the_statuses_of_the_page_s_legend_are_read():
    page = changed(MIDSEASON, OPEN, OPEN.replace("Open", "On-hold"), 1)
    page = page.replace(OPEN, OPEN.replace("Open", "Delayed"), 1).replace(OPEN, OPEN.replace("Open", "Race in Progress"), 1)
    page = page.replace("<td><span class=\"label success\">Open</span></td>",
                        "<td><span class=\"label warning\">On-hold</span></td>", 1)
    page = page.replace("145<sup class=\"light-text\">/145</sup>", "142<sup class=\"light-text\">/145</sup>")
    feed = panorama.parse(page, NOW)
    assert (feed["MountainAreas"][0]["Lifts"][0]["Status"], feed["MountainAreas"][0]["Lifts"][0]["StatusEnglish"]) == (
        "On hold", "on hold")
    assert [(trail["Name"], trail["Status"], trail["StatusEnglish"]) for trail in feed["MountainAreas"][1]["Trails"][:4]] == [
        ("World Cup Way", "On hold", "on hold"), ("Skyway", "Delayed", "delayed"),
        ("Grice Paddy", "Race in progress", "race in progress"), ("Rollercoaster", "Open", "open")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="World Cup Way has a status the reader does not know: 'patrol'"):
        panorama.parse(changed(MIDSEASON, OPEN, OPEN.replace("Open", "Patrol"), 1), NOW)
    with pytest.raises(ValueError, match="Village Gondola has a status the reader does not know: 'wind'"):
        panorama.parse(changed(MIDSEASON, "<span class=\"label success\">Open</span>",
                               "<span class=\"label success\">Wind</span>", 1), NOW)
    with pytest.raises(ValueError, match="World Cup Way has difficulty symbols \\['star'\\]"):
        panorama.parse(changed(MIDSEASON, "flaticon-square lvl-intermediate", "flaticon-star lvl-intermediate", 1), NOW)
    with pytest.raises(ValueError, match="World Cup Way has a grooming mark the reader does not know"):
        panorama.parse(changed(MIDSEASON, "<svg class=\"groomed-icon\">", "<svg class=\"winched-icon\">", 1), NOW)
    with pytest.raises(ValueError, match="counts 144 of 145 trails open but 145 of 145 were read"):
        panorama.parse(changed(MIDSEASON, "145<sup class=\"light-text\">/145</sup>",
                               "144<sup class=\"light-text\">/145</sup>"), NOW)
    with pytest.raises(ValueError, match="trail table has 156 rows but 155 were read"):
        panorama.parse(changed(MIDSEASON, "<td>World Cup Way</td>", "<th>World Cup Way</th>"), NOW)
    with pytest.raises(ValueError, match="lift table has 11 rows but 10 were read"):
        panorama.parse(changed(MIDSEASON, "<td>Village Gondola</td>", "<th>Village Gondola</th>"), NOW)
    with pytest.raises(ValueError, match="table of trails was not found"):
        panorama.parse(changed(MIDSEASON, "id=\"trails-info\"", "id=\"trails\""), NOW)
    with pytest.raises(ValueError, match="table of lifts was not found"):
        panorama.parse(changed(MIDSEASON, "id=\"lifts-info\"", "id=\"lifts\""), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("124<sup class=\"light-text\">cm</sup>", "124<sup class=\"light-text\">in</sup>"),
                     (">Summit</p>", ">Mid Mountain</p>"), (">24 Hours</p>", ">Day</p>"),
                     ("reports--block reports--snow", "reports--block reports--depth"),
                     ("406<sup", "lots<sup")):
        feed = panorama.parse(changed(MIDSEASON, old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 12
    # A figure that has lost its shape is not passed over.
    assert "SnowReport" not in panorama.parse(changed(MIDSEASON, "54<sup class=\"light-text\">cm</sup>",
                                                      "54<sup>cm</sup>"), NOW)
