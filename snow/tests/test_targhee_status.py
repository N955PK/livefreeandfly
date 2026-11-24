from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import targhee

FIXTURES = Path(__file__).parent / "fixtures"
PAGES = {"lifts": (FIXTURES / "targhee.html").read_text(), "report": (FIXTURES / "targhee_report.html").read_text()}
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def test_each_lift_is_an_area_holding_its_own_trails():
    # Grand Targhee on 2026-11-24, open on two lifts: six lifts, 113 runs listed beneath them.
    feed = targhee.parse(PAGES, NOW)
    assert feed["Name"] == "Grand Targhee" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    areas = feed["MountainAreas"]
    assert [(area["Name"], area["Lifts"][0]["StatusEnglish"], len(area["Trails"])) for area in areas] == [
        ("Blackfoot", "closed", 13), ("Colter", "closed", 27), ("Dreamcatcher", "closed", 33),
        ("Sacajawea", "closed", 17), ("Shoshone", "open", 15), ("Huckleberry", "open", 8)]
    assert all(len(area["Lifts"]) == 1 for area in feed["MountainAreas"])
    shoshone = {trail["Name"]: trail for trail in feed["MountainAreas"][4]["Trails"]}
    assert shoshone["Big Horn"] == {"Name": "Big Horn", "Status": "Open", "StatusEnglish": "open",
                                    "Difficulty": "Green", "Grooming": "Yes"}
    assert shoshone["Alley Oop Alley"]["Grooming"] == "No"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 15
    # The uphill route is left out, and the terrain parks have no level.
    assert "Uphill Access" not in {trail["Name"] for trail in trails}
    assert sorted(trail["Name"] for trail in trails if trail["Difficulty"] == "") == [
        "North Pole Terrain Park", "Sweetwater Terrain Park"]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_is_the_mountain_report_s_figures_and_its_snapshot_time():
    snow = targhee.parse(PAGES, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T17:27:01Z" and snow["Resortwide"] is True
    assert snow["SeasonTotalIn"] == 44 and snow["Weather"] == "Sunny"
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 22, "Last24HoursIn": 1, "OvernightIn": 1}
    assert "Stick of Truth" in snow["Report"]


def test_a_page_whose_lifts_do_not_match_its_count_or_whose_levels_are_new_is_refused():
    with pytest.raises(ValueError, match="counts 6 lifts but 5"):
        # The last lift on the page is not read as one: its trails fall to the lift before it.
        page = "node--type-chair ".join(PAGES["lifts"].rsplit("node--type-lift ", 1))
        targhee.parse({**PAGES, "lifts": page}, NOW)
    with pytest.raises(ValueError, match="a level the reader does not know"):
        page = PAGES["lifts"].replace('f-icon level expert"', 'f-icon level extreme"', 1)
        targhee.parse({**PAGES, "lifts": page}, NOW)
    with pytest.raises(ValueError, match="count of lifts was not found"):
        page = PAGES["lifts"].replace(">Overview<", ">Summary<").replace("Lifts", "Chairs")
        targhee.parse({**PAGES, "lifts": page}, NOW)


def test_a_mountain_report_with_no_snapshot_costs_the_snow_report_and_not_the_lifts():
    feed = targhee.parse({**PAGES, "report": "<html><body>Closed for the season</body></html>"}, NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
