from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import discovery

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"discovery_{name}.html").read_text() for name in discovery.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new, count)}


def test_the_early_season_mountain_reads_each_heading_s_lifts_with_the_trails_under_it():
    # Discovery's pages on 2026-11-26, early season: eight lifts with two open, 67 trails with three open.
    feed = discovery.parse(PAGES, NOW)
    assert feed["Name"] == "Discovery" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], [(lift["Name"], lift["Status"]) for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        # One heading names two lifts over one table, and Rumsey has a heading and no table.
        ("Easy Triple Chair & Totemoff Magic Carpet",
         [("Easy Triple Chair", "Open"), ("Totemoff Magic Carpet", "Open")], 3),
        ("Jubliee Triple Chair", [("Jubliee Triple Chair", "Closed")], 6),
        ("Rumsey Double Chair", [("Rumsey Double Chair", "Closed")], 0),
        ("Anaconda Triple Chair", [("Anaconda Triple Chair", "Closed")], 15),
        ("Granite Triple Chair", [("Granite Triple Chair", "Closed")], 11),
        ("Limelight Double Chair", [("Limelight Double Chair", "Closed")], 22),
        ("Silver Chief Triple Chair", [("Silver Chief Triple Chair", "Closed")], 10)]
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Easy Triple Chair", "Status": "Open",
                                                    "StatusEnglish": "open", "Difficulty": None}
    assert feed["MountainAreas"][0]["Trails"] == [
        {"Name": "Lums Run", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"},
        {"Name": "Easy Street", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"},
        {"Name": "Lower Sapphire", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
         "Grooming": "Yes"}]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 67 == len({trail["Name"] for trail in trails})
    assert sum(trail["StatusEnglish"] == "open" for trail in trails) == 3
    assert trails[3] == {"Name": "Gold Bug", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    # The double black diamond's picture says "Black" in its words: its name is what is read.
    levels = [trail["Difficulty"] for trail in trails]
    assert [levels.count(level) for level in ("Green", "Blue", "Black", "Double black")] == [10, 24, 15, 18]


def test_the_snow_report_gives_the_bottom_and_the_top_and_when_it_was_updated():
    snow = discovery.parse(PAGES, NOW)["SnowReport"]
    # "Updated: November 26, 2026 at 8:38 am", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T15:38:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Bottom", "SinceLiftsClosedIn": 0, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 0, "BaseIn": 6}
    assert snow["SummitArea"] == {"Name": "Top", "BaseIn": 8}
    assert snow["SeasonTotalIn"] == 10 and snow["BaseConditions"] == "Groomed"


def test_an_all_closed_mountain_reads_as_closed():
    pages = lifts_page("- OPEN", "- CLOSED")
    assert pages["lifts"].count("\tOpen  ") == 3
    pages = {**pages, "lifts": pages["lifts"].replace("\tOpen  ", "\tClosed  ")}
    feed = discovery.parse(pages, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 75 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = discovery.parse(lifts_page("GRANITE TRIPLE CHAIR - CLOSED", "GRANITE TRIPLE CHAIR - WIND HOLD"), NOW)
    lift = feed["MountainAreas"][4]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Granite Triple Chair", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="trail report was not found"):
        discovery.parse(lifts_page('class="include-table"', 'class="table"'), NOW)
    with pytest.raises(ValueError, match="not a name, a dash and a status"):
        discovery.parse(lifts_page("GRANITE TRIPLE CHAIR - CLOSED", "GRANITE TRIPLE CHAIR"), NOW)
    with pytest.raises(ValueError, match="difficulty pictures"):
        discovery.parse(lifts_page("double-black-diamond.png", "triple-black-diamond.png"), NOW)
    with pytest.raises(ValueError, match="no lift's heading of its own"):
        discovery.parse(lifts_page("<h4", "<h3"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        discovery.parse(lifts_page("GRANITE TRIPLE CHAIR", "LIMELIGHT DOUBLE CHAIR"), NOW)
    with pytest.raises(ValueError, match="counts 9 lifts but 8"):
        discovery.parse(snow_page('<span class="lift-total">/8</span>', '<span class="lift-total">/9</span>'), NOW)
    with pytest.raises(ValueError):
        discovery.parse({**PAGES, "lifts": "<html><body>Not the page</body></html>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = discovery.parse(snow_page('<p class="little-text inch">6</p>', '<p class="little-text inch">thin</p>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
    assert "SnowReport" not in discovery.parse(snow_page("Updated: November 26, 2026", "Updated this morning"), NOW)
    assert "SnowReport" not in discovery.parse(snow_page("Snow Depth - Top", "Snow Depth - Summit"), NOW)
