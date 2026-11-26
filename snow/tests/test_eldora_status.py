import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import eldora

FIXTURES = Path(__file__).parent / "fixtures"
# The three reports as the API gave them on 2026-11-26; the snow reports' author fields were already empty.
PAGES = {name: (FIXTURES / f"eldora_{name}.json").read_text() for name in eldora.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    rows = json.loads(PAGES[name])
    change(rows)
    return {**PAGES, name: json.dumps(rows)}


def test_the_reports_are_the_resort_s_own_api_s():
    assert eldora.URLS == {"lifts": "https://api.eldora.com/api/v1/dor/drupal/lifts",
                           "trails": "https://api.eldora.com/api/v1/dor/drupal/trails",
                           "snow": "https://api.eldora.com/api/v1/dor/drupal/snow-reports"}


def test_the_early_season_mountain_reads_its_lifts_and_trails_by_part_of_the_mountain():
    # Eldora's reports on Thanksgiving 2026: ten lifts with one turning, 63 ski trails with four open.
    feed = eldora.parse(PAGES, NOW)
    assert feed["Name"] == "Eldora" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Little Hawk", 7, 17), ("Corona", 1, 15), ("Challenge Mountain", 1, 21), ("Indian Peaks", 1, 10)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert sorted(lifts) == ["Alpenglow", "Caribou", "Corona", "EZ", "Indian Peaks", "Little Hawk", "Race",
                             "Sundance", "Sunkid", "Tenderfoot"]
    assert lifts["Alpenglow"] == {"Name": "Alpenglow", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert [name for name, lift in lifts.items() if lift["StatusEnglish"] == "open"] == ["Alpenglow"]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Caribou Crossing", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Green", "Grooming": "No"}
    assert sorted(trail["Name"] for trail in trails if trail["StatusEnglish"] == "open") == [
        "Hornblower", "International", "Klondike", "Windmill"]
    # The Nordic centre's 25 cross-country trails and the three uphill routes are not there.
    assert len(trails) == 63 == len(json.loads(PAGES["trails"])) - 28
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    assert [trail["Grooming"] for trail in trails].count("Yes") == 14


def test_the_snow_report_is_the_newest_and_its_time_is_mountain_time():
    snow = eldora.parse(PAGES, NOW)["SnowReport"]
    # Dated 05:39:20 Mountain standard time, seven hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-26T12:39:20Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 2
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 20, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 1, "Last7DaysIn": 2, "OvernightIn": 0}
    assert "Eldora snow report" in snow["Report"]
    backwards = changed("snow", lambda rows: rows.reverse())
    assert eldora.parse(backwards, NOW)["SnowReport"] == snow


def test_a_lift_on_hold_takes_the_report_s_words():
    def turn(rows):
        rows[0]["status"] = "wind_hold"
    lift = eldora.parse(changed("lifts", turn), NOW)["MountainAreas"][0]["Lifts"][0]
    assert lift == {"Name": "Caribou", "Status": "Wind hold", "StatusEnglish": "wind hold", "Difficulty": None}


def test_an_open_groomed_trail_reads_as_open_and_groomed():
    def groom(rows):
        rows[0].update(status="open", groom_status="groomed")
    feed = eldora.parse(changed("trails", groom), NOW)
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert trails["Powderhorn Glades"] == {"Name": "Powderhorn Glades", "Status": "Open", "StatusEnglish": "open",
                                           "Difficulty": "Double black", "Grooming": "Yes"}


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(rows):
        for row in rows:
            row["unit_of_measurement"] = "cm"
    feed = eldora.parse(changed("snow", metric), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in eldora.parse({**PAGES, "snow": "[]"}, NOW)


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        eldora.parse({**PAGES, "lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not a list"):
        eldora.parse({**PAGES, "trails": "{}"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        eldora.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        eldora.parse({**PAGES, "trails": "[]"}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        eldora.parse(changed("lifts", lambda rows: rows[0].pop("sector")), NOW)
    with pytest.raises(ValueError, match="part of the mountain with no name"):
        eldora.parse(changed("lifts", lambda rows: rows[0]["sector"].update(name=" ")), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        eldora.parse(changed("trails", lambda rows: rows[0].update(difficulty="hardest")), NOW)
    with pytest.raises(ValueError, match="grooming the reader does not know"):
        eldora.parse(changed("trails", lambda rows: rows[0].update(groom_status="maybe")), NOW)
    with pytest.raises(ValueError, match="has no status"):
        eldora.parse(changed("lifts", lambda rows: rows[0].update(status=None)), NOW)
