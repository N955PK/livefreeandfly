import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import snowbird

FIXTURES = Path(__file__).parent / "fixtures"
PAGES = {name: (FIXTURES / f"snowbird_{name}.json").read_text() for name in snowbird.URLS}
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    rows = json.loads(PAGES[name])
    change(rows)
    return {**PAGES, name: json.dumps(rows)}


def test_the_closed_mountain_reads_as_every_lift_and_winter_trail_closed_by_part_of_the_mountain():
    # Snowbird's reports on 2026-11-24, the day before it opened: 14 lifts and 150 ski trails, all closed.
    feed = snowbird.parse(PAGES, NOW)
    assert feed["Name"] == "Snowbird" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Peruvian Gulch", 4, 48), ("Mineral Basin", 3, 31), ("Gad Valley", 7, 71)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"}
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert lifts["Aerial Tram"] == {"Name": "Aerial Tram", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert lifts["Gadzoom"]["Status"] == "Closed" and "Mineral Basin" in lifts and "Little Cloud" in lifts
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Adager", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Black", "Grooming": "No"}
    # The summer hiking and biking trails and the trails the resort hides are not there.
    assert sum(len(area["Trails"]) for area in feed["MountainAreas"]) == 150 < len(json.loads(PAGES["trails"]))


def test_the_snow_report_is_the_newest_with_its_depth_snowfall_and_when_it_was_posted():
    snow = snowbird.parse(PAGES, NOW)["SnowReport"]
    # Posted 05:25 Mountain standard time.
    assert snow["LastUpdate"] == "2026-11-24T12:25:00Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 80
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 45, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 0, "Last7DaysIn": 30, "OvernightIn": 0}
    assert "Snowbird opens tomorrow" in snow["Report"]
    # The newest is taken whatever the order the reports come in.
    backwards = changed("snow", lambda rows: rows.reverse())
    assert snowbird.parse(backwards, NOW)["SnowReport"] == snow


def test_an_open_lift_a_lift_on_hold_and_a_groomed_trail_take_the_report_s_words():
    def turn(rows):
        rows[0]["status"], rows[1]["status"] = "open", "wind_hold"
    lifts = snowbird.parse(changed("lifts", turn), NOW)["MountainAreas"][0]["Lifts"]
    assert (lifts[0]["Name"], lifts[0]["StatusEnglish"]) == ("Aerial Tram", "open")
    assert (lifts[1]["Status"], lifts[1]["StatusEnglish"]) == ("Wind hold", "wind hold")

    def groom(rows):
        trail = next(row for row in rows if row["name"] == "Adager")
        trail["status"], trail["groom_status"] = "open", "groomed"
    trail = snowbird.parse(changed("trails", groom), NOW)["MountainAreas"][0]["Trails"][0]
    assert trail["StatusEnglish"] == "open" and trail["Grooming"] == "Yes"


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(rows):
        rows[0]["unit_of_measurement"] = "cm"
    feed = snowbird.parse(changed("snow", metric), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 3
    assert "SnowReport" not in snowbird.parse({**PAGES, "snow": "[]"}, NOW)
    with pytest.raises(ValueError, match="not a number"):
        snowbird.figure("45")


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        snowbird.parse({**PAGES, "lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not a list"):
        snowbird.parse({**PAGES, "trails": "{}"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        snowbird.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        snowbird.parse({**PAGES, "trails": "[]"}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        snowbird.parse(changed("lifts", lambda rows: rows[0].pop("sector")), NOW)
    with pytest.raises(ValueError, match="does not know"):
        snowbird.parse(changed("trails", lambda rows: rows[0].update(difficulty="hardest")), NOW)
    with pytest.raises(ValueError, match="has no status"):
        snowbird.parse(changed("lifts", lambda rows: rows[0].update(status=None)), NOW)
