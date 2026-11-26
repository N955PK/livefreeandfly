from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import eaglecrest

# The page with its scripts, styles, drawings, header and footer taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "eaglecrest.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
ROW = '<td class="column-1">{}</td><td class="column-2">{}</td>'
SNOW_ROW = '<td class="column-1">{}</td><td class="column-2">{}</td><td class="column-3">{}</td>'


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def with_snow(new: str = '4"', base: str = '38"', summit: str = "92 in", season: str = '120"') -> str:
    """The page with its table of conditions filled in, as it is in season."""
    page = changed(SNOW_ROW.format("New Snow: 12hrs", "", ""), SNOW_ROW.format("New Snow: 12hrs", new, new))
    page = changed(SNOW_ROW.format("Snowpack ", "", ""), SNOW_ROW.format("Snowpack ", base, summit), page=page)
    return changed(SNOW_ROW.format("Season Snowfall ", "", ""), SNOW_ROW.format("Season Snowfall ", "", season),
                   page=page)


def test_the_preseason_mountain_reads_its_chairlifts_trails_and_gates():
    # Eaglecrest's page on 2026-11-26, before opening: three chairlifts, 39 trails and six gates, all closed.
    feed = eaglecrest.parse(PAGE, NOW)
    assert feed["Name"] == "Eaglecrest" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Eaglecrest", 3, 39), ("Gate Access", 0, 6)]
    # The line for the hours of operation and the link under it are not lifts.
    assert feed["MountainAreas"][0]["Lifts"] == [
        {"Name": name, "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
        for name in ("Porcupine", "Hooter", "Ptarmigan")]
    trails = feed["MountainAreas"][0]["Trails"]
    assert trails[0] == {"Name": "Muskeg", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": ""}
    assert trails[-1]["Name"] == "Hang Ten" and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    # The Nordic trails' table is not read, and the note under the gates is not a gate.
    assert not [trail for trail in trails if "Skate" in trail["Name"]]
    gates = feed["MountainAreas"][1]["Trails"]
    assert [gate["Name"] for gate in gates] == ["East Bowl Chutes", "West Bowl", "Pittman's Ridge", "Steep Chutes",
                                                "Beacon Park", "Raven Rock"]


def test_out_of_season_the_empty_table_of_conditions_gives_no_snow_report():
    assert "SnowReport" not in eaglecrest.parse(PAGE, NOW)


def test_in_season_the_snow_report_gives_the_base_and_the_summit_undated():
    snow = eaglecrest.parse(with_snow(), NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "Last12HoursIn": 4, "BaseIn": 38}
    assert snow["SummitArea"] == {"Name": "Summit", "Last12HoursIn": 4, "BaseIn": 92}
    assert snow["SeasonTotalIn"] == 120


def test_an_open_chairlift_and_an_open_trail_are_carried_in_the_page_s_words():
    page = changed(ROW.format("Porcupine", "Closed"), ROW.format("Porcupine", "Open"))
    page = changed(ROW.format("Ptarmigan", "Closed"), ROW.format("Ptarmigan", "Wind Hold"), page=page)
    page = changed(ROW.format("Muskeg", "Closed"), ROW.format("Muskeg", "Open - Groomed"), page=page)
    area = eaglecrest.parse(page, NOW)["MountainAreas"][0]
    assert [lift["StatusEnglish"] for lift in area["Lifts"]] == ["open", "closed", "wind hold"]
    assert area["Lifts"][2]["Status"] == "Wind hold"
    assert area["Trails"][0] == {"Name": "Muskeg", "Status": "Open - groomed", "StatusEnglish": "open - groomed",
                                 "Difficulty": ""}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no table headed"):
        eaglecrest.parse(changed('<th class="column-1">CHAIRLIFT</th>', '<th class="column-1">LIFT</th>'), NOW)
    with pytest.raises(ValueError, match="no table headed"):
        eaglecrest.parse(changed('<th class="column-1">TERRAIN</th>', '<th class="column-1">GATE</th>'), NOW)
    with pytest.raises(ValueError, match="a row of the chairlifts is not a name and a status"):
        eaglecrest.parse(changed(ROW.format("Hooter", "Closed"), ROW.format("Hooter", "")), NOW)
    with pytest.raises(ValueError, match="a row of the trails is not a name and a status"):
        eaglecrest.parse(changed(ROW.format("Muskeg", "Closed"), ROW.format("Muskeg", "Closed") + "<td>9am</td>"), NOW)
    with pytest.raises(ValueError, match="the trails list a name twice"):
        eaglecrest.parse(changed(ROW.format("Muskeg", "Closed"), ROW.format("Sneaky", "Closed")), NOW)
    with pytest.raises(ValueError, match="two tables headed"):
        eaglecrest.parse(changed('<th class="column-1">TERRAIN</th>', '<th class="column-1">Trail</th>').replace(
            '<th class="column-2">STATUS</th>', '<th class="column-2">Status</th>'), NOW)
    with pytest.raises(ValueError):
        eaglecrest.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = eaglecrest.parse(with_snow(base="deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 3
    assert "SnowReport" not in eaglecrest.parse(changed("Snowpack ", "Snow Stake ", page=with_snow()), NOW)
    assert "SnowReport" not in eaglecrest.parse(changed('<th class="column-2">BASE</th>',
                                                        '<th class="column-2">LODGE</th>', page=with_snow()), NOW)
