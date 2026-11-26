from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import brundage

# The page with its scripts, styles, drawings and menus taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "brundage.html").read_text()
NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
CLOSED_ROW = "<td>North</td><td><img decoding=\"async\" fetchpriority=\"low\" " \
             "src=\"https://brundage.com/wp-content/themes/brundage/assets/images/trail-icons/blue.gif\" " \
             "alt=\"\">Blue</td><td>Closed</td>"
# The page's count of trails, open and in all.
COUNTED = "<div>0</div>\n                        <div>70</div>"


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_each_zone_with_its_lifts_and_trails():
    # Brundage's page on 2026-11-26, before it opened: seven lifts and 70 trails in four zones, all closed.
    feed = brundage.parse(PAGE, NOW)
    assert feed["Name"] == "Brundage" and feed["LastUpdate"] == "2026-11-26T16:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Front Side Zone", ["Blue Bird Express", "Centennial Express"], 38),
        ("Beartopia Zone", ["Easy Street Triple Chair Lift", "Bear Chair", "Easy Rider Conveyor"], 16),
        ("Lakeview Zone", ["Lakeview Triple"], 5), ("Hidden Valley Zone", ["Hidden Valley"], 11)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 77 and {row["StatusEnglish"] for row in rows} == {"closed"}
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Blue Bird Express", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # No trail is called groomed, so none carries grooming.
    assert trails[0] == {"Name": "North", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Blue"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", ""}
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == ""] == [
        "Bear Terrain Park", "Jammer Terrain Park", "Roller Coaster Terrain Park"]


def test_the_snow_report_gives_three_depths_and_when_it_was_updated():
    snow = brundage.parse(PAGE, NOW)["SnowReport"]
    # "Last Updated 11/25/26 8:23PM MST", seven hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-26T03:23:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 0, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 0, "Last7DaysIn": 5}
    assert snow["MidMountainArea"] == {"Name": "Lakeview", "BaseIn": 0, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                       "Last72HoursIn": 0, "Last7DaysIn": 5}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 0}
    assert snow["SeasonTotalIn"] == 19 and snow["BaseConditions"] is None


def test_an_open_lift_and_open_and_groomed_trails_are_read():
    page = changed("<p class=\"lift-status closed\">Closed</p>", "<p class=\"lift-status open\">Open</p>", 1)
    page = page.replace(CLOSED_ROW, CLOSED_ROW.replace("Closed", "Groomed"))
    rodeo = "<td>Rodeo</td>" + CLOSED_ROW[14:]
    page = page.replace(rodeo, rodeo.replace("Closed", "Open")).replace(COUNTED, COUNTED.replace("0", "2", 1))
    feed = brundage.parse(page, NOW)
    front = feed["MountainAreas"][0]
    assert [lift["StatusEnglish"] for lift in front["Lifts"]] == ["open", "closed"]
    assert front["Trails"][0] == {"Name": "North", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                                  "Grooming": "Yes"}
    assert front["Trails"][1] == {"Name": "Rodeo", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                                  "Grooming": "No"}
    assert front["Trails"][2]["StatusEnglish"] == "closed" and front["Trails"][2]["Grooming"] == "No"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = changed("<p class=\"lift-status closed\">Closed</p>", "<p class=\"lift-status on-hold\">On Hold</p>", 1)
    lift = brundage.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift and zone status was not found"):
        brundage.parse(changed("weather-conditions lift-zone-report", "weather-conditions lifts"), NOW)
    with pytest.raises(ValueError, match="trail status was not found"):
        brundage.parse(changed("weather-conditions trail-report", "weather-conditions trails"), NOW)
    with pytest.raises(ValueError, match="Blue Bird Express is marked closed but reads 'Open'"):
        brundage.parse(changed("<p class=\"lift-status closed\">Closed</p>", "<p class=\"lift-status closed\">Open</p>",
                               1), NOW)
    with pytest.raises(ValueError, match="7 lift rows but 6 were read"):
        brundage.parse(changed("<h4>Bear Chair</h4>", "<h5>Bear Chair</h5>"), NOW)
    with pytest.raises(ValueError, match="North has a difficulty the reader does not know: Orange"):
        brundage.parse(changed(CLOSED_ROW, CLOSED_ROW.replace("Blue<", "Orange<")), NOW)
    with pytest.raises(ValueError, match="not a name, a difficulty and a status"):
        brundage.parse(changed(CLOSED_ROW, CLOSED_ROW + "<td>Yes</td>"), NOW)
    with pytest.raises(ValueError, match="counts 0 of 71 trails open but 0 of 70"):
        brundage.parse(changed(COUNTED, COUNTED.replace("70", "71")), NOW)
    with pytest.raises(ValueError, match="count of trails was not found"):
        brundage.parse(changed("Trails Open</div>", "Runs Open</div>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = brundage.parse(changed("Last Updated 11/25/26 8:23PM MST", "Last Updated yesterday"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in brundage.parse(changed("Base: 0&#8243;", "Base: deep"), NOW)
    assert "SnowReport" not in brundage.parse(changed("Summit: 0&#8243;", "Peak: 0&#8243;"), NOW)
    assert "SnowReport" not in brundage.parse(changed("<li>24 Hours: 0&#8243;</li>", "<li>Day: 0&#8243;</li>"), NOW)
    # A figure the resort leaves as a dash stays empty.
    snow = brundage.parse(changed("Lakeview: 0&#8243;", "Lakeview: &#8212;"), NOW)["SnowReport"]
    assert snow["MidMountainArea"]["BaseIn"] is None and snow["BaseArea"]["BaseIn"] == 0
