from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import tamarack

# The page with its scripts, styles, drawings and menus taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "tamarack.html").read_text()
NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
ICONS = "https://tamarackidaho.com/wp-content/themes/Tamarack/img/snow-report"
CLOSED = f"<span class=\"sr-icon-label\"><img src=\"{ICONS}/cancel.svg\" alt=\"\" width=\"16\" height=\"16\">" \
         "<span>Closed</span></span>"


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_its_two_tables_of_trails():
    # Tamarack's page on 2026-11-26, before it opened: seven lifts, 64 downhill trails and two parks, all closed.
    feed = tamarack.parse(PAGE, NOW)
    assert feed["Name"] == "Tamarack" and feed["LastUpdate"] == "2026-11-26T16:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Tamarack", 7, 0), ("Downhill Trails", 0, 64), ("Terrain Parks", 0, 2)]
    # The table of uphill routes is not lifts.
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Buttercup Chair", "Discovery Chair", "Mutton Buster Carpet", "Rock Creek Poma", "Summit Express",
        "Tamarack Express", "Wildwood Express"]
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Buttercup Chair", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 73 and {row["StatusEnglish"] for row in rows} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len({trail["Name"] for trail in trails}) == 66
    assert trails[0] == {"Name": "Adrenaline", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black"}
    assert trails[-1] == {"Name": "Homestead Terrain Park", "Status": "Closed", "StatusEnglish": "closed",
                          "Difficulty": ""}
    assert {trail["Difficulty"] for trail in feed["MountainAreas"][1]["Trails"]} == {"Green", "Blue", "Black"}


def test_the_snow_report_gives_the_summit_and_mid_mountain_and_when_it_was_updated():
    snow = tamarack.parse(PAGE, NOW)["SnowReport"]
    # "25 Nov 2026 at 9:51 AM", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-25T16:51:00Z" and snow["Resortwide"] is True
    assert snow["SummitArea"] == {"Name": "Summit", "Last24HoursIn": 0, "Last48HoursIn": 0, "StormTotalIn": 5,
                                  "BaseIn": 17}
    assert snow["MidMountainArea"] == {"Name": "Mid-Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0,
                                       "StormTotalIn": 5, "BaseIn": 13}
    assert snow["SeasonTotalIn"] == 40 and snow["BaseConditions"] is None and "BaseArea" not in snow


def test_a_status_is_carried_in_the_page_s_words():
    feed = tamarack.parse(changed(CLOSED, CLOSED.replace("Closed", "Open"), 1), NOW)
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]][:2] == ["open", "closed"]
    feed = tamarack.parse(changed(CLOSED, CLOSED.replace("Closed", "On Hold"), 1), NOW)
    lift = feed["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="table of lifts was not found"):
        tamarack.parse(changed("<th scope=\"col\">Lifts</th>", "<th scope=\"col\">Chairs</th>"), NOW)
    with pytest.raises(ValueError, match="table of lifts has no name or no status"):
        tamarack.parse(changed("<td data-label=\"Status\">", "<td data-label=\"State\">", 1), NOW)
    with pytest.raises(ValueError, match="66 trail rows but 2 were read"):
        tamarack.parse(changed("id=\"sr-panel-downhill\"", "id=\"panel-downhill\""), NOW)
    with pytest.raises(ValueError, match="table of trails the reader does not know: nordic"):
        tamarack.parse(changed("id=\"sr-panel-parks\"", "id=\"sr-panel-nordic\""), NOW)
    with pytest.raises(ValueError, match="Adrenaline has a difficulty the reader does not know: Extreme"):
        tamarack.parse(changed("<span>Advanced</span>", "<span>Extreme</span>", 1), NOW)
    with pytest.raises(ValueError, match="not a name, a difficulty and a status"):
        tamarack.parse(changed("<td data-label=\"Difficulty\">", "<td data-label=\"Level\">", 1), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = tamarack.parse(changed("Last update: 25 Nov 2026 at 9:51 AM", "Last update: this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 3
    assert "SnowReport" not in tamarack.parse(changed("Summit Base Depth", "Summit Depth"), NOW)
    assert "SnowReport" not in tamarack.parse(changed("<span class=\"sr-stat__value\">17\"</span>",
                                                      "<span class=\"sr-stat__value\">deep</span>"), NOW)
    assert "SnowReport" not in tamarack.parse(changed("sr-stats sr-stats--snow", "sr-stats"), NOW)
