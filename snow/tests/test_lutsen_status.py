from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import lutsen

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and menus taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"lutsen_{name}.html").read_text() for name in lutsen.URLS}
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
CLOSED = "<div class=\"f-icon icon-closed\"\n             title=\"Closed\"></div>"


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def test_the_early_season_resort_reads_each_mountain_with_its_lifts_and_runs():
    # Lutsen's pages on 2026-11-26, two days before it opened: nine lifts with the conveyor open, 87 runs.
    feed = lutsen.parse(PAGES, NOW)
    assert feed["Name"] == "Lutsen Mountains" and feed["LastUpdate"] == "2026-11-26T17:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Ullr Mountain", ["Conveyor", "Ullr Chair"], 8), ("Eagle Mountain", ["Bridge Chair", "Raptor Express"], 25),
        ("Moose Mountain", ["Caribou Express", "Summit Express Gondola", "Timberwolf Chair"], 45),
        ("Mystery Mountain", ["Mystery Mountain Chair"], 9), ("Lutsen Nordic Center", ["Ullr (Nordic)"], 0)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    # "Conveyor (9:00am-4:00pm)" is read without its hours.
    assert lifts[0] == {"Name": "Conveyor", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert [lift["StatusEnglish"] for lift in lifts] == ["open"] + ["closed"] * 8
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 87 == len({trail["Name"] for trail in trails})
    assert trails[0] == {"Name": "Big Bunny", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    # Flapjack is "Projected", the page's word for a run it expects to open; "Karen&#039;s Corner" is read as said.
    assert trails[1] == {"Name": "Flapjack", "Status": "Expected", "StatusEnglish": "expected", "Difficulty": "Green",
                         "Grooming": "No"}
    assert trails[2]["Name"] == "Karen's Corner"
    assert [trail["Name"] for trail in trails if trail["StatusEnglish"] != "closed"] == ["Flapjack"]
    assert [sum(trail["Difficulty"] == level for trail in trails)
            for level in ("Green", "Blue", "Black", "Double black")] == [5, 49, 23, 10]


def test_the_snow_report_gives_the_depth_and_when_it_was_updated():
    snow = lutsen.parse(PAGES, NOW)["SnowReport"]
    # "Nov 26th - 9:56am", six hours behind UTC in November, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-26T15:56:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 0,
                                "BaseIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None


def test_a_date_that_would_be_ahead_of_the_reading_is_last_year_s():
    snow = lutsen.parse(PAGES, datetime(2027, 1, 2, 17, 0, tzinfo=timezone.utc))["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-26T15:56:00Z"


def test_a_held_lift_and_a_groomed_run_are_read():
    pages = lifts_page(CLOSED, "<div class=\"f-icon icon-on-hold\"\n             title=\"On Hold\"></div>", 1)
    lift = lutsen.parse(pages, NOW)["MountainAreas"][0]["Lifts"][1]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Ullr Chair", "On hold", "on hold")
    groomed = "<div class=\"cell icon-cell condition\"><div class=\"f-icon icon-groomed\" title=\"Groomed\"></div>" \
              "</div>"
    pages = lifts_page("Big Bunny\n    </div>", "Big Bunny\n    </div>" + groomed)
    trails = lutsen.parse(pages, NOW)["MountainAreas"][0]["Trails"]
    assert (trails[0]["Name"], trails[0]["Grooming"], trails[1]["Grooming"]) == ("Big Bunny", "Yes", "No")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts of lifts and trails were not found"):
        lutsen.parse(lifts_page("snow-weather page mountain-stats", "snow-weather page"), NOW)
    with pytest.raises(ValueError, match="counts 9 lifts but 8 were read"):
        lutsen.parse(lifts_page("node node--type-lift node--view-mode-row\" id=\"node-961\"",
                                "node node--type-lift\" id=\"node-961\""), NOW)
    with pytest.raises(ValueError, match="counts 59 primary trails but 58 were read"):
        lutsen.parse(lifts_page("<span class=\"unit\">/58</span>", "<span class=\"unit\">/59</span>"), NOW)
    with pytest.raises(ValueError, match="Ullr Chair's status icon is shut and reads 'Closed'"):
        lutsen.parse(lifts_page(CLOSED, CLOSED.replace("icon-closed", "icon-shut"), 1), NOW)
    with pytest.raises(ValueError, match="Big Bunny has a difficulty the reader does not know: novice"):
        lutsen.parse(lifts_page("cell f-icon level icon-beginner", "cell f-icon level icon-novice", 1), NOW)
    with pytest.raises(ValueError, match="Ullr Mountain has a list the reader does not know: Glades"):
        lutsen.parse(lifts_page("<h2 class=\"h4 \">Sidecountry Runs</h2>", "<h2 class=\"h4 \">Glades</h2>", 1), NOW)
    with pytest.raises(ValueError, match="96 lift and run rows but 0 were read"):
        lutsen.parse(lifts_page("<details>", "<section>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = lutsen.parse(snow_page("Nov 26th - 9:56am", "this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
    assert "SnowReport" not in lutsen.parse(snow_page("condition-block snow winter", "condition-block winter"), NOW)
    base = PAGES["snow"].rindex("Base\n")
    pages = {**PAGES, "snow": PAGES["snow"][:base] + "Summit\n" + PAGES["snow"][base + 5:]}
    assert "SnowReport" not in lutsen.parse(pages, NOW)
