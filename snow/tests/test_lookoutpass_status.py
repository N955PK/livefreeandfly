from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import lookoutpass

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "lookoutpass.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_each_lift_with_the_trails_under_it():
    # Lookout Pass's page on 2026-11-26, before opening: five chairs and 59 trails, all closed.
    feed = lookoutpass.parse(PAGE, NOW)
    assert feed["Name"] == "Lookout Pass" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Chair 1: Peak 1 Quad", "Closed", 24), ("Chair 2: Timberwolf Triple", "Closed", 13),
        ("Chair 3: Northstar Double", "Closed", 5), ("Chair 4: Success Triple", "Closed", 1),
        ("Chair 5: Eagle Peak Quad", "Closed", 16)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Chair 1: Peak 1 Quad", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 59 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Black Bear"] == {"Name": "Black Bear", "Status": "Closed", "StatusEnglish": "closed",
                                    "Difficulty": "Blue", "Grooming": "No"}
    # Two black diamonds are a double black, the park symbol has no difficulty, and two symbols give the harder.
    assert trails["Lucky Friday Glades"]["Difficulty"] == "Double black"
    assert trails["Progression Park"]["Difficulty"] == ""
    assert trails["Rainbow Ridge"]["Difficulty"] == "Blue" and trails["Copper"]["Difficulty"] == "Black"
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_gives_the_base_and_the_summit_and_when_it_was_updated():
    snow = lookoutpass.parse(PAGE, NOW)["SnowReport"]
    # "Last updated: November 25, 2026 at 5:02 PM, PST", read from the block's count of seconds.
    assert snow["LastUpdate"] == "2026-11-26T01:02:23Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 0.7,
                                "BaseIn": 3}
    assert snow["SummitArea"] == {"Name": "Summit", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 2,
                                  "BaseIn": 12}
    assert snow["SeasonTotalIn"] == 16.5 and snow["BaseConditions"] == "Heavy Powder"


def swapped(page: str, opening: str, new: str, closing: str) -> str:
    """The page with the first piece that begins with ``opening`` replaced, up to its closing tag, by ``new``."""
    at = page.index(opening)
    return page[:at] + new + page[page.index(closing, at):]


def test_an_open_lift_and_a_groomed_trail_are_read():
    page = swapped(PAGE, '<div class="lift-status closed">', '<div class="lift-status open"> Open ', "</div>")
    page = swapped(page, '<span class="status-badge closed">', '<span class="status-badge open"> Open ', "</span>")
    page = page.replace('<span class="groomed-badge no">No</span>', '<span class="groomed-badge yes">Yes</span>', 1)
    area = lookoutpass.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Chair 1: Peak 1 Quad", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    assert area["Trails"][0] == {"Name": "Black Bear", "Status": "Open", "StatusEnglish": "open",
                                 "Difficulty": "Blue", "Grooming": "Yes"}
    assert area["Trails"][1]["StatusEnglish"] == "closed"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = swapped(PAGE, '<div class="lift-status closed">', '<div class="lift-status wind-hold"> Wind Hold ',
                   "</div>")
    lift = lookoutpass.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Chair 1: Peak 1 Quad", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift and slope status was not found"):
        lookoutpass.parse(changed('class="powderwatch-lifts"', 'class="lifts"'), NOW)
    with pytest.raises(ValueError, match="is marked shut but reads 'Closed'"):
        lookoutpass.parse(changed('<div class="lift-status closed">', '<div class="lift-status shut">', 1), NOW)
    with pytest.raises(ValueError, match="difficulty symbols the reader does not know"):
        lookoutpass.parse(changed("difficulty-symbol park", "difficulty-symbol orange-oval"), NOW)
    with pytest.raises(ValueError, match="grooming reads 'Maybe'"):
        lookoutpass.parse(changed('<span class="groomed-badge no">No</span>',
                                  '<span class="groomed-badge no">Maybe</span>', 1), NOW)
    with pytest.raises(ValueError, match="not a name, a status, a grooming and a difficulty"):
        lookoutpass.parse(changed('<td class="groomed-cell">', '<td class="grooming">', 1), NOW)
    with pytest.raises(ValueError, match="5 lifts and 59 trail rows but 4 and"):
        lookoutpass.parse(changed('<div class="lift-status-container">', '<div class="lift-state">', 1), NOW)
    with pytest.raises(ValueError):
        lookoutpass.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = lookoutpass.parse(changed('<span class="value">3&#8243;</span>', '<span class="value">deep</span>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
    assert "SnowReport" not in lookoutpass.parse(changed("data-timestamp=", "data-time="), NOW)
    assert "SnowReport" not in lookoutpass.parse(changed("<h4>Base</h4>", "<h4>Lodge</h4>"), NOW)
