from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import eaglepoint

# The page's snowfall, cameras and lifts and runs with its scripts, styles, menus and layout settings taken out;
# the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "eaglepoint.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
LABEL = '<p class="elementor-heading-title elementor-size-default">{}</p>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def figure(page: str, label: str, said: str) -> str:
    """The page with a figure written under one of the snow report's labels, the way its season total is."""
    old = LABEL.format(label)
    assert old in page
    return page.replace(old, f'{old}</div></div><div><div class="elementor-widget-container">{said}</div>')


def test_the_preseason_mountain_reads_each_lift_with_the_runs_in_its_table():
    # Eagle Point's page on 2026-11-26, before opening: five lifts and 46 runs, all closed.
    feed = eaglepoint.parse(PAGE, NOW)
    assert feed["Name"] == "Eagle Point" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    # The table headed "Terrain Parks" is not a lift.
    assert [(area["Name"], [lift["Status"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Lookout Quad", ["Closed"], 18), ("Monarch Triple Chair", ["Closed"], 16),
        ("Skyline Double Chair", ["Closed"], 7), ("Tushar Peaks Surface Lift", ["Closed"], 1),
        ("Canyonside Double Chair", ["Closed"], 2), ("Terrain Parks", [], 2)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Lookout Quad", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 46 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    # "Condition not available" (and "Closed") say nothing of the grooming.
    assert trails["Puffer's Pass"] == {"Name": "Puffer's Pass", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Blue"}
    assert trails["Big Horn"] == {"Name": "Big Horn", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Green", "Grooming": "Yes"}
    assert trails["Crescent Moon"]["Grooming"] == "No" and "Grooming" not in trails["Falling Water"]
    assert trails["Tushar"]["Difficulty"] == "Black"
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black")] == [13, 20, 13]
    assert sum(trail.get("Grooming") == "Yes" for trail in trails.values()) == 6


def test_the_blank_preseason_snow_report_is_no_snow_report_and_a_filled_one_is_read():
    # Before opening only the season's total (last season's 127 inches) is written.
    assert "SnowReport" not in eaglepoint.parse(PAGE, NOW)
    page = figure(figure(figure(PAGE, "24hr Snowfall", "3&#8243;"), "48hr Snowfall", "5.5&#8243;"), "Base", "41&#8243;")
    assert eaglepoint.parse(page, NOW)["SnowReport"] == {
        "LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": 127,
        "BaseArea": {"Name": "Mountain", "Last24HoursIn": 3, "Last48HoursIn": 5.5, "BaseIn": 41}, "Report": None,
        "Alert": None}
    feed = eaglepoint.parse(figure(figure(PAGE, "24hr Snowfall", "3&#8243;"), "Base", "deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6


def test_an_open_lift_and_an_open_run_are_read():
    page = changed('<td class="main-status status-closed">closed</td>',
                   '<td class="main-status status-open">open</td>', 1)
    page = page.replace("Wolverine</td><td>Closed</td><td>Condition not available</td>",
                        "Wolverine</td><td>Open</td><td>Groomed</td>")
    area = eaglepoint.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Lookout Quad", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Wolverine", "Status": "Open", "StatusEnglish": "open",
                                 "Difficulty": "Blue", "Grooming": "Yes"}
    assert area["Trails"][1]["StatusEnglish"] == "closed"
    hold = changed('<td class="main-status status-closed">closed</td>',
                   '<td class="main-status status-wind-hold">Wind Hold</td>', 1)
    lift = eaglepoint.parse(hold, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="is marked shut but reads 'closed'"):
        eaglepoint.parse(changed('class="main-status status-closed"', 'class="main-status status-shut"', 1), NOW)
    with pytest.raises(ValueError, match="a difficulty symbol the reader does not know: orange"):
        eaglepoint.parse(changed("difficulty-diamond difficulty-black", "difficulty-oval difficulty-orange", 1), NOW)
    with pytest.raises(ValueError, match="not headed by a lift and its status"):
        eaglepoint.parse(changed('<tr class="label-status-row">', '<tr class="head">', 1), NOW)
    with pytest.raises(ValueError, match="6 tables and 46 runs but 6 and 45"):
        eaglepoint.parse(changed("Wolverine</td><td>Closed</td><td>Condition not available</td>",
                                 "Wolverine</td><td>Closed</td>"), NOW)
    with pytest.raises(ValueError, match="list of lifts does not name the lifts of its tables"):
        eaglepoint.parse(changed('<div class="lift-item">Lookout Quad</div>',
                                 '<div class="lift-item">Lookout Express</div>'), NOW)
    with pytest.raises(ValueError):
        eaglepoint.parse("<html><body>Not the page</body></html>", NOW)
