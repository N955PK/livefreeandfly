import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sunshine

FIXTURES = Path(__file__).parent / "fixtures"
# Of each page, only the block its figures are in, with its drawings taken out; the reader gives the same on the
# whole pages.
PAGES = {name: (FIXTURES / f"sunshine_{name}.html").read_text() for name in sunshine.URLS}
NOW = datetime(2026, 11, 24, 23, 40, tzinfo=timezone.utc)
# The first closed status on the page, which is the first lift's.
CLOSED = r"icon-status icon-19(\">\s*<span class=\"visually-hidden\">\s*)Closed"


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def reworded(name: str, pattern: str, new: str) -> dict:
    """The pages with the first match of a pattern on one of them replaced."""
    changed, count = re.subn(pattern, new, PAGES[name], count=1)
    assert count == 1
    return {**PAGES, name: changed}


def test_the_early_season_mountain_reads_its_lifts_and_its_trails_by_mountain():
    # Banff Sunshine on 2026-11-24: 3 of 12 lifts and 8 of 139 trails open.
    feed = sunshine.parse(PAGES, NOW)
    assert feed["Name"] == "Banff Sunshine" and feed["LastUpdate"] == "2026-11-24T23:40:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Banff Sunshine", 12, 0), ("Goat's Eye Mountain", 0, 58), ("Lookout Mountain", 0, 41),
        ("Mount Standish", 0, 40)]
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Gondola"] == {"Name": "Gondola", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert lifts["Goat's Eye Express Quad"]["Status"] == "Closed"
    assert sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "open") == [
        "Gondola", "Mitey Mite Conveyor", "Strawberry Express Quad"]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 139
    assert trails["Banff Ave"] == {"Name": "Banff Ave", "Status": "Closed", "StatusEnglish": "closed",
                                   "Difficulty": "Green", "Grooming": "No"}
    assert trails["Boutry's Bowl"] == {"Name": "Boutry's Bowl", "Status": "Open", "StatusEnglish": "open",
                                       "Difficulty": "Blue", "Grooming": "Yes"}
    assert sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 8
    assert sum(trail["Grooming"] == "Yes" for trail in trails.values()) == 5
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = sunshine.parse(PAGES, NOW)["SnowReport"]
    # "Tuesday, November 24th, 2026 8:57 AM": Alberta keeps one time all year, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T14:57:00Z" and snow["Resortwide"] is False
    # Up high 38 cm of base, nothing new and 3 cm in 7 days; at mid mountain 31 cm, 2 cm overnight, 3 cm and 9 cm.
    assert snow["SummitArea"] == {"Name": "Upper Mountain", "OvernightIn": 0.0, "Last24HoursIn": 0.0,
                                  "Last7DaysIn": 1.2, "BaseIn": 15.0}
    assert snow["MidMountainArea"] == {"Name": "Mid Mountain", "OvernightIn": 0.8, "Last24HoursIn": 1.2,
                                       "Last7DaysIn": 3.5, "BaseIn": 12.2}
    # 66 cm this season at the upper mountain.
    assert snow["SeasonTotalIn"] == 26.0 and snow["BaseConditions"] is None and "BaseArea" not in snow


def test_a_lift_on_standby_is_on_hold():
    lifts = sunshine.parse(reworded("lifts", CLOSED, r"icon-status icon-20\1Standby"), NOW)["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Goat's Eye Express Quad", "Status": "Standby", "StatusEnglish": "on hold",
                        "Difficulty": None}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lifts and trails were not found"):
        sunshine.parse(page("lifts", "block-lifts-trails", "block-lifts"), NOW)
    with pytest.raises(ValueError, match="Goat's Eye Express Quad has a status the reader does not know: 'Shut'"):
        sunshine.parse(reworded("lifts", CLOSED, r"icon-status icon-19\1Shut"), NOW)
    with pytest.raises(ValueError, match="Banff Ave has a difficulty the reader does not know: 'Easy'"):
        sunshine.parse(reworded("lifts", r"Easiest(\s*</span>\s*</div>\s*Banff Ave)", r"Easy\1"), NOW)
    with pytest.raises(ValueError, match="counts 4 of 12 lifts open but 3 of 12"):
        sunshine.parse(page("lifts", "value\">3</div>", "value\">4</div>"), NOW)
    with pytest.raises(ValueError, match="counts 8 of 140 trails open but 8 of 139"):
        sunshine.parse(page("lifts", "of 139", "of 140"), NOW)
    with pytest.raises(ValueError, match="count of trails was not found"):
        sunshine.parse(page("lifts", "trails Open</figcaption>", "runs Open</figcaption>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("Updated: Tuesday, November 24th, 2026 8:57 AM", "Updated this morning"),
                     ("Mid Mountain Snow Report", "Village Snow Report"), ("<h4>Settled Base</h4>", "<h4>Depth</h4>"),
                     ("<h4>24hr</h4>", "<h4>Today</h4>"), ("block-weather-feed", "block-weather")):
        feed = sunshine.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
