import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import independents, sundance

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "sundance.json").read_text()
MIDSEASON = (FIXTURES / "sundance_midseason.json").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(change) -> str:
    """The report with one change made to it."""
    report = json.loads(PAGE)
    change(report)
    return json.dumps(report)


def rows_of(feed: dict) -> list:
    return [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_part_of_the_mountain():
    # Sundance's report on 2026-11-24, before it opened: ten lifts, 86 ski trails and four parks, all closed. The
    # summer's hiking and biking trails in the same list are marked not to be shown and are left out.
    feed = sundance.parse(PAGE, NOW)
    assert feed["Name"] == "Sundance" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Sundance", 10, 0), ("Front Mountain", 0, 19), ("Mid Mountain", 0, 11), ("Back Mountain", 0, 30),
        ("Bishop's Bowl", 0, 7), ("Upper Storyteller", 0, 3), ("Lower Storyteller", 0, 16), ("Terrain Parks", 0, 4)]
    assert {row["StatusEnglish"] for row in rows_of(feed)} == {"closed"} and all(row["Name"] for row in rows_of(feed))
    names = {row["Name"] for row in rows_of(feed)}
    assert "Stewart Falls Trail" not in names and "Upper Flow Trail" not in names
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Outlaw Express"] == {"Name": "Outlaw Express", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": None}
    assert lifts["Red's"]["Status"] == "Closed" and lifts["Magic Carpet 3"]["Status"] == "Closed"
    assert feed["MountainAreas"][1]["Trails"][1] == {"Name": "Bandit", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green", "Grooming": "No"}
    assert feed["MountainAreas"][-1]["Trails"][0] == {"Name": "Stampede", "Status": "Closed", "StatusEnglish": "closed",
                                                      "Difficulty": "", "Grooming": "No"}


def test_the_snow_report_gives_the_base_depth_and_no_time_so_the_closed_mountain_s_is_left_out():
    feed = sundance.parse(PAGE, NOW)
    snow = feed["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 11, "Last24HoursIn": 0, "Last48HoursIn": 0}
    assert snow["SeasonTotalIn"] == 14 and snow["LastUpdate"] is None and snow["Report"] is None
    # The file does not say when the figures were posted, and the runner drops an undated report while no lift turns.
    assert "SnowReport" not in independents.settled(feed, NOW)


def test_the_open_mountain_reads_open_lifts_and_groomed_runs():
    # The file on 2026-02-09 (from the Internet Archive), in the shape it then had: seven of nine lifts open.
    feed = sundance.parse(MIDSEASON, NOW)
    lifts = {lift["Name"]: lift["Status"] for lift in feed["MountainAreas"][0]["Lifts"]}
    assert len(lifts) == 9 and sum(status == "Open" for status in lifts.values()) == 7
    assert lifts["Outlaw Express"] == "Open" and lifts["Flathead"] == "Closed"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 71 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 35
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 25
    groomed = next(trail for trail in trails if trail["Name"] == "Lone Pine")
    assert groomed == {"Name": "Lone Pine", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                       "Grooming": "Yes"}
    snow = feed["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] == 13 and snow["SeasonTotalIn"] == 35
    assert snow["Report"].startswith("Groomed runs recommended.")
    # With lifts turning the undated report is kept.
    assert "SnowReport" in independents.settled(feed, NOW)


def test_a_report_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no lifts or no trails"):
        sundance.parse(changed(lambda report: report.pop("lift-status")), NOW)
    with pytest.raises(ValueError, match="not one the reader knows"):
        sundance.parse(changed(lambda report: report["lift-status"][1].update(status_value="spinning")), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        sundance.parse(changed(lambda report: report["grooming"][1].update(difficulty="orange")), NOW)
    with pytest.raises(ValueError, match="counts 10 lifts but 9"):
        sundance.parse(changed(lambda report: report["lift-status"][1].update(display="no")), NOW)
    with pytest.raises(ValueError, match="names no part"):
        sundance.parse(changed(lambda report: report["grooming"][1].pop("type")), NOW)
    with pytest.raises(ValueError, match="an entry has the status"):
        sundance.parse(changed(lambda report: report["lift-status"][1].pop("Lifts")), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sundance.parse(changed(lambda report: report["snow-weather"][2].update(status_value="deep")), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 10
    assert "SnowReport" not in sundance.parse(changed(lambda report: report["snow-weather"][2].update(status_value="")), NOW)
