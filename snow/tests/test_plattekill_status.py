from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import plattekill

# The page with its scripts, styles, drawings and footer taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "plattekill.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
TRAIL = '<td class="column-1">{}</td><td class="column-2">{}</td><td class="column-3">{}</td>'
LIFT = '<td class="column-1">{}</td><td colspan="2" class="column-2">{}</td>'


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def with_snow(new: str = '4"', low: str = '18"', high: str = '40"') -> str:
    """The page with the snow part of its table filled in, as it is in season."""
    page = changed(LIFT.format("New Natural Snow last 24 HOURS", "N/A"),
                   LIFT.format("New Natural Snow last 24 HOURS", new))
    page = changed(LIFT.format("Base Depth, MINIMUM:", "N/A"), LIFT.format("Base Depth, MINIMUM:", low), page=page)
    return changed(LIFT.format("Base Depth, MAXIMUM:", "N/A"), LIFT.format("Base Depth, MAXIMUM:", high), page=page)


def test_the_preseason_mountain_reads_its_lifts_trails_and_park():
    # Plattekill's report of 2026-11-15, before opening: four lifts, 40 trails and the terrain park, all closed.
    feed = plattekill.parse(PAGE, NOW)
    assert feed["Name"] == "Plattekill" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Plattekill", 4, 40), ("Terrain Parks", 0, 1)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Sunshine Triple Chair", "Northface Double Chair",
                                                "Bunny Hop Carpet", "Tubing Carpet"]
    # "CLOSED" is carried with one capital.
    assert lifts[0] == {"Name": "Sunshine Triple Chair", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][0]["Trails"]}
    assert len(trails) == 40 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Overlook"] == {"Name": "Overlook", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Green", "Grooming": "No"}
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black")] == [6, 20, 7, 7]
    assert trails["Backdraft"]["Difficulty"] == "Blue" and trails["Blockbuster"]["Difficulty"] == "Double black"
    assert "Whiskey’s Way" in trails
    # The terrain park is a row among the hardest trails, and has no difficulty.
    assert feed["MountainAreas"][1]["Trails"] == [{"Name": "Terrain Park", "Status": "Closed",
                                                   "StatusEnglish": "closed", "Difficulty": "", "Grooming": "No"}]


def test_before_the_season_the_snow_report_has_no_depth():
    snow = plattekill.parse(PAGE, NOW)["SnowReport"]
    # "Report for: 11/15/2026", read as noon of that day in Eastern time.
    assert snow["LastUpdate"] == "2026-11-15T17:00:00Z" and snow["Resortwide"] is True
    # The table gives no snow of the last 24 hours, so the heading's is used; the heading gives the season's.
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": 0}
    assert snow["SeasonTotalIn"] == 9


def test_in_season_the_base_depth_is_its_least_and_its_most():
    area = plattekill.parse(with_snow(), NOW)["SnowReport"]["BaseArea"]
    assert area == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": 18, "BaseMaxIn": 40, "Last24HoursIn": 4}
    # One depth given twice is the depth, and so is one given alone.
    assert plattekill.parse(with_snow(low='30"', high='30"'), NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 30
    alone = plattekill.parse(with_snow(low="N/A", high="24 inches"), NOW)["SnowReport"]["BaseArea"]
    assert (alone["BaseIn"], alone["BaseMinIn"], alone["BaseMaxIn"]) == (24, None, None)


def test_an_open_lift_and_a_groomed_trail_are_read():
    page = changed(LIFT.format("Northface Double Chair", "CLOSED"), LIFT.format("Northface Double Chair", "OPEN"))
    page = changed(TRAIL.format("Overlook", "CLOSED", "-----"), TRAIL.format("Overlook", "OPEN", "MG/PP"), page=page)
    page = changed(TRAIL.format("Backdraft", "CLOSED", "-----"), TRAIL.format("Backdraft", "OPEN", "PP"), page=page)
    area = plattekill.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][1] == {"Name": "Northface Double Chair", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    trails = {trail["Name"]: trail for trail in area["Trails"]}
    assert trails["Overlook"] == {"Name": "Overlook", "Status": "Open", "StatusEnglish": "open",
                                  "Difficulty": "Green", "Grooming": "Yes"}
    assert (trails["Backdraft"]["StatusEnglish"], trails["Backdraft"]["Grooming"]) == ("open", "No")
    assert sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 2


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="trail report's table was not found"):
        plattekill.parse(changed("Surface Condition</th>", "Surface</th>"), NOW)
    with pytest.raises(ValueError, match="parts the reader does not know: \\['glades'\\]"):
        plattekill.parse(changed("<h3>Most Difficult</h3>", "<h3>Glades</h3>"), NOW)
    with pytest.raises(ValueError, match="two parts headed 'easiest'"):
        plattekill.parse(changed("<h3>More Difficult</h3>", "<h3>Easiest</h3>"), NOW)
    with pytest.raises(ValueError, match="not a name, a status and a surface"):
        plattekill.parse(changed(TRAIL.format("Overlook", "CLOSED", "-----"),
                                 '<td class="column-1">Overlook</td><td class="column-2">CLOSED</td>'), NOW)
    with pytest.raises(ValueError, match="not a name and a status"):
        plattekill.parse(changed(LIFT.format("Northface Double Chair", "CLOSED"),
                                 LIFT.format("Northface Double Chair", "")), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        plattekill.parse(changed("<h3>Lifts</h3>", "<h3>Snow</h3>").replace('<h3 class="snow-report">Snow</h3>', ""),
                         NOW)
    with pytest.raises(ValueError):
        plattekill.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = plattekill.parse(with_snow(low="deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
    assert "SnowReport" not in plattekill.parse(with_snow(low='40"', high='18"'), NOW)
    assert "SnowReport" not in plattekill.parse(changed("Report for: 11/15/2026", "Report for: today"), NOW)
    assert "SnowReport" not in plattekill.parse(changed("Base Depth, MINIMUM:", "Depth:"), NOW)
