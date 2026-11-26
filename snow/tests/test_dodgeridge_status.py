from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import dodgeridge

FIXTURES = Path(__file__).parent / "fixtures"
# The site's two answers as they came, and the snow report page with its scripts, styles, drawings and comments
# taken out; the reader gives the same on the whole page.
PAGES = {name: (FIXTURES / f"dodgeridge_{name}.html").read_text() for name in dodgeridge.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_first_week_s_mountain_reads_each_lift_and_each_part_s_trails():
    # Dodge Ridge on 2026-11-26, five days after opening: six of eleven lifts open, and all 69 trails marked open.
    feed = dodgeridge.parse(PAGES, NOW)
    assert feed["Name"] == "Dodge Ridge" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 11, 0), ("Lower Mountain", 0, 24), ("Backside", 0, 19), ("Upper Mountain", 0, 26)]
    assert [(lift["Name"], lift["Status"]) for lift in feed["MountainAreas"][0]["Lifts"]] == [
        ("Chair 1 - Triple Nugget", "Open"), ("Chair 3 - Motherlode", "Open"), ("Chair 4 - Comstock", "Closed"),
        ("Chair 5 - Gold Rush", "Closed"), ("Chair 6 - Clementine", "Open"), ("Chair 7 - Prospector", "Open"),
        ("Chair 8 - Boulder Creek", "Open"), ("Conveyer 1 River's Otter Run", "Closed"), ("Conveyor 2", "Closed"),
        ("Conveyor 3 The Highway", "Open"), ("TBar - 643", "Closed")]
    assert feed["MountainAreas"][0]["Lifts"][2] == {"Name": "Chair 4 - Comstock", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 69 and {trail["StatusEnglish"] for trail in trails.values()} == {"open"}
    # The site says nothing of grooming, so a trail carries none.
    assert trails["Alley Way"] == {"Name": "Alley Way", "Status": "Open", "StatusEnglish": "open",
                                   "Difficulty": "Blue"}
    assert trails["Bobby's Freedom Run"]["Difficulty"] == "Black"
    levels = [trail["Difficulty"] for trail in trails.values()]
    assert [levels.count(level) for level in ("Green", "Blue", "Black", "Double black")] == [5, 30, 27, 7]


def test_the_snow_report_gives_the_snowfall_and_no_base_depth():
    snow = dodgeridge.parse(PAGES, NOW)["SnowReport"]
    # "November 25 update:" is the start of that day in Pacific time, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-25T08:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": 0, "Last72HoursIn": 0}
    assert snow["SeasonTotalIn"] == 44 and snow["BaseConditions"] is None


def test_a_report_dated_late_in_the_year_and_read_early_in_the_next_is_last_year_s():
    pages = changed("snow", "November 25 update:", "December 30 update:")
    assert dodgeridge.parse(pages, datetime(2027, 1, 2, 18, tzinfo=timezone.utc))["SnowReport"]["LastUpdate"] == (
        "2026-12-30T08:00:00Z")
    # A report dated for the morning ahead is this year's.
    pages = changed("snow", "November 25 update:", "November 27 update:")
    assert dodgeridge.parse(pages, NOW)["SnowReport"]["LastUpdate"] == "2026-11-27T08:00:00Z"
    pages = changed("snow", ">0&#8243;</div>", ">7.5&#8243;</div>", 1)
    assert dodgeridge.parse(pages, NOW)["SnowReport"]["BaseArea"]["Last24HoursIn"] == 7.5


def test_another_status_is_carried_in_the_site_s_words():
    pages = changed("lifts", '<p class="lift-status">open</p>', '<p class="lift-status">wind hold</p>', 1)
    lift = dodgeridge.parse(pages, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Chair 1 - Triple Nugget", "Wind hold",
                                                                     "wind hold")
    pages = changed("trails", '<p class="trail-status">open</p>', '<p class="trail-status">closed</p>', 1)
    trails = dodgeridge.parse(pages, NOW)["MountainAreas"][1]["Trails"]
    assert (trails[0]["Name"], trails[0]["StatusEnglish"], trails[1]["StatusEnglish"]) == ("Alley Way", "closed",
                                                                                         "open")


def test_an_answer_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not its list of lifts"):
        dodgeridge.parse({**PAGES, "lifts": "0"}, NOW)
    with pytest.raises(ValueError, match="not its list of trails"):
        dodgeridge.parse({**PAGES, "trails": "<p>Unable to fetch trail status at this time.</p>"}, NOW)
    with pytest.raises(ValueError, match="lists 11 lifts but 10 were read"):
        dodgeridge.parse(changed("lifts", '<p class="lift-status">', '<p class="state">', 1), NOW)
    with pytest.raises(ValueError, match="lists 69 trails but 68 were read"):
        dodgeridge.parse(changed("trails", '<p class="trail-area">', '<p class="zone">', 1), NOW)
    with pytest.raises(ValueError, match="difficulty symbol the reader does not know: orange_oval"):
        dodgeridge.parse(changed("trails", "difficulty_icons/green_circle.png", "difficulty_icons/orange_oval.png", 1),
                         NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        dodgeridge.parse(changed("lifts", '<p class="lift-status">open</p>', '<p class="lift-status"></p>', 1), NOW)
    with pytest.raises(ValueError, match="one twice"):
        dodgeridge.parse(changed("lifts", "Chair 3 - Motherlode</p>", "Chair 1 - Triple Nugget</p>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = dodgeridge.parse(changed("snow", ">0&#8243;</div>", ">deep</div>", 1), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in dodgeridge.parse(changed("snow", "November 25 update:", "Today's update:"), NOW)
    assert "SnowReport" not in dodgeridge.parse(changed("snow", ">24 hrs</div>", ">Overnight</div>"), NOW)
    assert "SnowReport" not in dodgeridge.parse({**PAGES, "snow": "<html></html>"}, NOW)
