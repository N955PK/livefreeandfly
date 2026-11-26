import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import independents, taos

# The page as the site gave it on 2026-11-26, the morning of opening day, before any lift had turned.
PAGE = (Path(__file__).parent / "fixtures" / "taos.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def escaped(text: str) -> str:
    """A piece of the page's data as it is written inside the page's scripts."""
    return json.dumps(text)[1:-1]


def changed(old: str, new: str, count: int | None = None) -> str:
    old, new = escaped(old), escaped(new)
    assert old in PAGE and (count is None or PAGE.count(old) == count)
    return PAGE.replace(old, new)


def test_the_closed_mountain_reads_its_winter_lifts_and_trails():
    feed = taos.parse(PAGE, NOW)
    assert feed["Name"] == "Taos Ski Valley" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [area["Name"] for area in feed["MountainAreas"]] == ["Taos Ski Valley"]
    lifts, trails = feed["MountainAreas"][0]["Lifts"], feed["MountainAreas"][0]["Trails"]
    assert [lift["Name"] for lift in lifts] == [
        "Gondolita", "Kachina Peak", "Lift 1", "Lift 2", "Lift 4", "Lift 7", "Lift 7A", "Lift 8", "Pika Peak",
        "Pioneers", "Rueggli", "Zipper 1", "Zipper 2"]
    assert lifts[0] == {"Name": "Gondolita", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    # The page lists 120 winter slopes; the skating rink among them is not counted as a trail and is left out, and
    # so are the summer's bike trails, restaurants and shops.
    assert len(trails) == 119 and not any("Rink" in trail["Name"] or "Scenic" in trail["Name"] for trail in trails)
    assert trails[0] == {"Name": "Al's Run", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black",
                         "Grooming": "No"}
    levels = [trail["Difficulty"] for trail in trails]
    assert {level: levels.count(level) for level in set(levels)} == {"Green": 15, "Blue": 19, "Black": 39,
                                                                     "Double black": 46}


def test_the_snow_report_gives_the_base_depth_and_is_undated():
    snow = taos.parse(PAGE, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 19, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 0, "Last7DaysIn": 8}
    assert snow["SeasonTotalIn"] == 23.75 and snow["Resortwide"] is True and snow["BaseConditions"] is None
    # The page does not say when the figures were measured, so the runner leaves them out while no lift is turning.
    assert snow["LastUpdate"] is None
    assert "SnowReport" not in independents.settled(taos.parse(PAGE, NOW), NOW)


def test_an_open_lift_and_an_open_groomed_trail_are_read():
    page = changed('"name":"Lift 1","status":"closed"', '"name":"Lift 1","status":"wind-hold"')
    page = page.replace(escaped('"name":"Al\'s Run","open":false'), escaped('"name":"Al\'s Run","open":true'))
    page = page.replace(escaped('"name":"Kachina Peak","status":"closed"'),
                        escaped('"name":"Kachina Peak","status":"open"'))
    page = page.replace(escaped('"conditions":"none","conditionsText":"","displayName":"","coordinates":null'),
                        escaped('"conditions":"groomed","conditionsText":"","displayName":"","coordinates":null'))
    feed = taos.parse(page, NOW)
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert (lifts["Lift 1"]["Status"], lifts["Lift 1"]["StatusEnglish"]) == ("Wind hold", "wind hold")
    assert lifts["Kachina Peak"]["StatusEnglish"] == "open" and lifts["Lift 2"]["StatusEnglish"] == "closed"
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Al's Run", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Black", "Grooming": "Yes"}
    # With a lift turning, the undated snow report is kept.
    assert independents.settled(feed, NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 19


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="carries no data"):
        taos.parse("<html><body>Lifts 0 / 13</body></html>", NOW)
    with pytest.raises(ValueError, match="lifts were not found"):
        taos.parse(changed('"liftData":', '"lifts":'), NOW)
    with pytest.raises(ValueError, match="trails were not found after its lifts"):
        taos.parse(changed('"slopeData":', '"slopes":'), NOW)
    with pytest.raises(ValueError, match="counts 14 lifts and 120 slopes but 13 and 120"):
        taos.parse(changed('"liftsTotal":13', '"liftsTotal":14', 1), NOW)
    with pytest.raises(ValueError, match="counts None lifts"):
        taos.parse(changed('{"liftsOpen":', '{"openLifts":', 1), NOW)
    with pytest.raises(ValueError, match="says it has 14 lifts but does not list that many"):
        taos.parse(changed('"winter":{"total":13,', '"winter":{"total":14,'), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: hardest"):
        taos.parse(changed('"difficulty":"expert","name":"Al\'s Run"', '"difficulty":"hardest","name":"Al\'s Run"'),
                   NOW)
    with pytest.raises(ValueError, match="Al's Run is not said to be open or closed"):
        taos.parse(changed('"name":"Al\'s Run","open":false', '"name":"Al\'s Run","open":null'), NOW)
    with pytest.raises(ValueError, match="Lift 1 has no status"):
        taos.parse(changed('"name":"Lift 1","status":"closed"', '"name":"Lift 1","status":null'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = taos.parse(changed('"base":19,', '"base":"deep",', 1), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 13
    assert "SnowReport" not in taos.parse(changed('"base":19,', '"base":null,', 1), NOW)
    assert "SnowReport" not in taos.parse(changed('"snowData":', '"snow":', 1), NOW)
