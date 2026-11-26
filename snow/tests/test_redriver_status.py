from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import redriver

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "redriver.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
CLOSED = '<i class="pti pti-closed"></i><span class="SnowReport-sr-label">Closed</span>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_early_season_mountain_reads_its_two_open_lifts_and_its_trails():
    # Red River's page on 2026-11-26, early season: seven lifts with two open, 64 trails, a glade and two parks.
    feed = redriver.parse(PAGE, NOW)
    assert feed["Name"] == "Red River" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Red River", 7, 64), ("Glades", 0, 1), ("Terrain Parks", 0, 2)]
    assert [(lift["Name"], lift["Status"]) for lift in feed["MountainAreas"][0]["Lifts"]] == [
        ("Copper", "Closed"), ("Emerald", "Closed"), ("Gold", "Open"), ("Little Blue", "Open"),
        ("Platinum", "Closed"), ("Rug Rat", "Closed"), ("Silver", "Closed")]
    assert feed["MountainAreas"][0]["Lifts"][2] == {"Name": "Gold", "Status": "Open", "StatusEnglish": "open",
                                                    "Difficulty": None}
    trails = feed["MountainAreas"][0]["Trails"]
    assert [trail["Difficulty"] for trail in trails] == ["Green"] * 20 + ["Blue"] * 20 + ["Black"] * 24
    assert [trail for trail in trails if trail["StatusEnglish"] == "open"] == [
        {"Name": "Gold Rush", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"},
        {"Name": "Little Blue", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"}]
    assert trails[0] == {"Name": "Buffalo", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    assert feed["MountainAreas"][2]["Trails"][-1] == {"Name": "Pot O’ Gold", "Status": "Open",
                                                      "StatusEnglish": "open", "Difficulty": "", "Grooming": "Yes"}


def test_the_snow_report_gives_the_ends_of_the_base_depth_and_when_it_was_updated():
    snow = redriver.parse(PAGE, NOW)["SnowReport"]
    # "07:49 AM, November 25, 2026", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-25T14:49:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 13, "BaseMinIn": 10, "BaseMaxIn": 16,
                                "Last24HoursIn": 0, "Last72HoursIn": 1}
    assert snow["SeasonTotalIn"] == 14 and snow["BaseConditions"] == "Machine Groomed"


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = changed(CLOSED, '<i class="pti pti-hold"></i><span class="SnowReport-sr-label">Wind Hold</span>', 1)
    lift = redriver.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Copper", "Wind hold", "wind hold")


def test_an_all_closed_mountain_reads_as_closed():
    page = PAGE.replace("pti-open", "pti-closed").replace('SnowReport-sr-label">Open<', 'SnowReport-sr-label">Closed<')
    feed = redriver.parse(page, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 74 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no lifts or no trails"):
        redriver.parse(changed("SnowReport-section--lifts", "SnowReport-section--chairs"), NOW)
    with pytest.raises(ValueError, match="heading the reader does not know: 'hardest'"):
        redriver.parse(changed("Most Difficult\n", "Hardest\n"), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        redriver.parse(changed(CLOSED, "", 1), NOW)
    with pytest.raises(ValueError, match="lists 74 lifts and trails but 73 were read"):
        redriver.parse(changed('<article class="SnowReport-Lift SnowReport-feature">',
                               '<article class="SnowReport-Lift">', 1), NOW)
    with pytest.raises(ValueError, match="counts 8 lifts but 7 were read"):
        redriver.parse(changed('<span class="ffs">7</span>', '<span class="ffs">8</span>'), NOW)
    with pytest.raises(ValueError, match="counts 65 trails but 64 were read"):
        redriver.parse(changed('<span class="ffs">64</span>', '<span class="ffs">65</span>'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = redriver.parse(changed("10 - 16&quot;", "plenty"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 3
    assert "SnowReport" not in redriver.parse(changed("07:49 AM, November 25, 2026", "This morning"), NOW)
    assert "SnowReport" not in redriver.parse(changed("<dt>Base Depth</dt>", "<dt>Summit Depth</dt>"), NOW)
