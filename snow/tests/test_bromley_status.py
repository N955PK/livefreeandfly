from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bromley

PAGE = (Path(__file__).parent / "fixtures" / "bromley.html").read_text()
NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed():
    # Bromley's report on 2026-11-24, the week before it opened: eight lifts, 48 trails and two parks, all closed.
    feed = bromley.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Bromley", 8, 48), ("Terrain Parks", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Sun Mountain Express", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert "Lord's Prayer T-Bar" in {lift["Name"] for lift in lifts}
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Chase It", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green", "Grooming": "No"}
    assert feed["MountainAreas"][1]["Trails"][0]["Difficulty"] == ""


def test_the_snow_report_has_no_base_depth_before_the_season_not_a_zero():
    snow = bromley.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-23T15:47:21Z" and snow["SeasonTotalIn"] == 4
    assert snow["BaseConditions"] is None and snow["Report"].startswith("Winter is Coming!")
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None,
                                "Last24HoursIn": 0, "Last24HoursMinIn": 0, "Last24HoursMaxIn": 0}


def test_a_depth_is_one_figure_or_a_least_and_a_most():
    assert bromley.figures("Base", {"min": 18, "max": None}) == {"BaseIn": 18, "BaseMinIn": 18, "BaseMaxIn": 18}
    assert bromley.figures("Base", {"min": 12, "max": 30}) == {"BaseIn": None, "BaseMinIn": 12, "BaseMaxIn": 30}


def test_statuses_and_ratings_take_the_page_s_words_and_unknown_ones_are_refused():
    assert bromley.status_row("Lift", "onHold", None)["StatusEnglish"] == "on hold"
    assert bromley.status_row("Lift", "scheduled", None)["Status"] == "Scheduled"
    trail = bromley.trail_row({"name": "Run", "rating": "extremeDoubleBlack", "status": "open", "groomed": True})
    assert trail == {"Name": "Run", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Double black", "Grooming": "Yes"}
    with pytest.raises(ValueError, match="status the reader does not know"):
        bromley.status_row("Lift", "maybe", None)
    with pytest.raises(ValueError, match="rating the reader does not know"):
        bromley.trail_row({"name": "Run", "rating": "purple", "status": "open"})


def test_a_page_without_the_report_or_without_lifts_is_refused():
    with pytest.raises(ValueError, match="report was not found"):
        bromley.parse(PAGE.replace('id="__NEXT_DATA__"', 'id="other"'), NOW)
    with pytest.raises(ValueError, match="no lifts"):
        bromley.parse('<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"report":{"lifts":[]}}}}</script>', NOW)
