from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import chinapeak

# The page's conditions and lift status with its scripts, styles and menus taken out; the reader gives the same on
# the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "chinapeak.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_each_lift_with_the_runs_under_it():
    # China Peak's page on 2026-11-26, before opening: nine lifts, all closed, and 54 runs, twelve marked open.
    feed = chinapeak.parse(PAGE, NOW)
    assert feed["Name"] == "China Peak" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    # The tubing hill's bar is left out, and the runs under "*" are an area with no lift.
    assert [(area["Name"], [lift["Status"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Chair 1", ["Closed"], 19), ("Chair 2", ["Closed"], 5), ("Chair 4", ["Closed"], 7),
        ("Chair 5", ["Closed"], 4), ("Chair 6", ["Closed"], 11), ("Chair 7", ["Closed"], 6),
        ("Kids Carpet", ["Closed"], 0), ("Boulder Carpet", ["Closed"], 0), ("Juniper Carpet", ["Closed"], 0),
        ("Other terrain", [], 2)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Chair 1", "Status": "Closed", "StatusEnglish": "closed",
                                                  "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 54 and sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 12
    assert trails["Academy - Upper"] == {"Name": "Academy - Upper", "Status": "Open", "StatusEnglish": "open",
                                         "Difficulty": "Blue"}
    assert trails["Jack's Run - Upper"]["Status"] == "Closed"
    assert trails["Buckhorn - Lower"]["Difficulty"] == "Double black"
    assert trails["Buckhorn - Upper"]["Difficulty"] == "Black"
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black")] == [0, 39, 11, 4]


def test_the_snow_totals_are_read_with_their_ranges_and_no_date():
    snow = chinapeak.parse(PAGE, NOW)["SnowReport"]
    # "Last 24 Hours: 0", Last 7 Days: 12-18", Season Total: 34-48"": no base depth, and no date.
    assert snow == {"LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": None,
                    "SeasonTotalMinIn": 34, "SeasonTotalMaxIn": 48,
                    "BaseArea": {"Name": "Mountain", "Last24HoursIn": 0, "Last7DaysMinIn": 12, "Last7DaysMaxIn": 18},
                    "Report": None, "Alert": None}
    page = changed('font-weight:bold;">0&quot;</span>', 'font-weight:bold;">2-4&quot;</span>')
    page = page.replace("34-48&quot;", "61.5&quot;")
    snow = chinapeak.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursMinIn"] == 2 and snow["BaseArea"]["Last24HoursMaxIn"] == 4
    assert "Last24HoursIn" not in snow["BaseArea"] and snow["SeasonTotalIn"] == 61.5


def test_an_open_lift_a_scheduled_lift_and_a_scheduled_run_are_read():
    page = changed('Chair 1: <span class="CLOSED">CLOSED</span>', 'Chair 1: <span class="OPEN">OPEN</span>')
    page = page.replace('Chair 2: <span class="CLOSED">CLOSED</span>',
                        'Chair 2: <span class="SCHEDULED">SCHEDULED</span>')
    page = page.replace('<span class="C">C</span>', '<span class="S">S</span>', 1)
    one, two = chinapeak.parse(page, NOW)["MountainAreas"][:2]
    assert one["Lifts"][0] == {"Name": "Chair 1", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert two["Lifts"][0]["Status"] == "Scheduled" and two["Lifts"][0]["StatusEnglish"] == "scheduled"
    assert [(trail["Name"], trail["Status"]) for trail in one["Trails"][3:5]] == [
        ("Jack's Run - Upper", "Scheduled"), ("Jack's Run - Lower", "Closed")]
    green = chinapeak.parse(changed("level_mod.jpg", "level_easy.jpg", 1), NOW)["MountainAreas"][0]["Trails"][0]
    assert green["Difficulty"] == "Green"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="a difficulty the reader does not know: orange"):
        chinapeak.parse(changed("level_dd.jpg", "level_orange.jpg", 1), NOW)
    with pytest.raises(ValueError, match="has the status 'X'"):
        chinapeak.parse(changed('<span class="C">C</span>', '<span class="X">X</span>', 1), NOW)
    with pytest.raises(ValueError, match=r"Chair 1 has the status 'CLOSED' \(marked OPEN\)"):
        chinapeak.parse(changed('Chair 1: <span class="CLOSED">', 'Chair 1: <span class="OPEN">'), NOW)
    with pytest.raises(ValueError, match="11 lift bars and 54 runs but 11 and 53"):
        chinapeak.parse(changed('<td style="width:27px;">', "<td>", 1).replace("<td><img", "<th><img", 1), NOW)
    with pytest.raises(ValueError, match="11 lift bars and 54 runs but 10 and"):
        chinapeak.parse(changed('Chair 4: <span class="CLOSED">CLOSED</span>', "Chair 4: <b>CLOSED</b>"), NOW)
    with pytest.raises(ValueError):
        chinapeak.parse("<html><body>Not the page</body></html>", NOW)


def test_snow_totals_that_cannot_be_read_cost_only_the_snow_report():
    feed = chinapeak.parse(changed("12-18&quot;", "a foot"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 10
    assert "SnowReport" not in chinapeak.parse(changed("Snow Totals:", "Snowfall:"), NOW)
    assert "SnowReport" not in chinapeak.parse(changed("Last 24 Hours:", "Overnight:"), NOW)
