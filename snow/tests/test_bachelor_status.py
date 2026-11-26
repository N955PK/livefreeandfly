import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bachelor

FIXTURES = Path(__file__).parent / "fixtures"
# The three reports as the API gave them; the snow reports' author fields were already empty.
PAGES = {name: (FIXTURES / f"bachelor_{name}.json").read_text() for name in bachelor.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    rows = json.loads(PAGES[name])
    change(rows)
    return {**PAGES, name: json.dumps(rows)}


def test_the_reports_are_the_resort_s_own_api_s():
    assert bachelor.URLS == {"lifts": "https://api.mtbachelor.com/api/v1/dor/drupal/lifts",
                             "trails": "https://api.mtbachelor.com/api/v1/dor/drupal/trails",
                             "snow": "https://api.mtbachelor.com/api/v1/dor/drupal/snow-reports"}


def test_the_mountain_before_it_opens_reads_its_winter_lifts_by_part_of_the_mountain():
    # Mt. Bachelor's reports on 2026-11-26, a week before it opens: 14 winter lifts and 123 ski trails, all closed.
    feed = bachelor.parse(PAGES, NOW)
    assert feed["Name"] == "Mt. Bachelor" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Frontside", 5, 37), ("Eastside", 6, 38), ("Summit", 1, 14), ("Westside", 2, 34)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert sorted(lifts) == ["Alpenglow", "Chipmunk Carpet", "Cloudchaser", "Early Riser", "Lava Tube", "Little Pine",
                             "Northwest", "Outback", "Pine Marten", "Rainbow", "Red Chair", "Skyliner Express",
                             "Summit", "Sunrise"]
    assert lifts["Pine Marten"] == {"Name": "Pine Marten", "Status": "Closed", "StatusEnglish": "closed",
                                    "Difficulty": None}
    # The two summer lifts of the bike park are not there.
    assert len(lifts) == 14 < len(json.loads(PAGES["lifts"]))
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Avalanche (Lower)", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Green", "Grooming": "No"}
    # The biking, hiking, cross-country, snowshoe and uphill routes and the hidden terrain parks are not there.
    assert len(trails) == 123 < len(json.loads(PAGES["trails"]))
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    assert {row["StatusEnglish"] for row in list(lifts.values()) + trails} == {"closed"}


def test_the_snow_report_is_the_newest_and_its_time_is_pacific():
    snow = bachelor.parse(PAGES, NOW)["SnowReport"]
    # Dated 07:00 Pacific standard time, eight hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-25T15:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 25
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 9, "Last24HoursIn": 0, "Last48HoursIn": 1,
                                "Last72HoursIn": 1, "Last7DaysIn": 5, "OvernightIn": 0}
    assert "scheduled to open" in snow["Report"]
    backwards = changed("snow", lambda rows: rows.reverse())
    assert bachelor.parse(backwards, NOW)["SnowReport"] == snow


def test_an_open_lift_and_a_lift_on_hold_take_the_report_s_words():
    def turn(rows):
        rows[1]["status"], rows[2]["status"] = "open", "wind_hold"
    lifts = bachelor.parse(changed("lifts", turn), NOW)["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts[:3]] == [
        ("Chipmunk Carpet", "Closed", "closed"), ("Little Pine", "Open", "open"),
        ("Pine Marten", "Wind hold", "wind hold")]


def test_an_open_groomed_trail_reads_as_open_and_groomed():
    def groom(rows):
        rows[0].update(status="open", groom_status="groomed")
    trail = bachelor.parse(changed("trails", groom), NOW)["MountainAreas"][0]["Trails"][0]
    assert trail == {"Name": "Avalanche (Lower)", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                     "Grooming": "Yes"}


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(rows):
        rows[0]["unit_of_measurement"] = "cm"
    feed = bachelor.parse(changed("snow", metric), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in bachelor.parse({**PAGES, "snow": "[]"}, NOW)
    assert "SnowReport" not in bachelor.parse(changed("snow", lambda rows: rows[0].update(base_depth="9")), NOW)


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        bachelor.parse({**PAGES, "lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not a list"):
        bachelor.parse({**PAGES, "trails": "{}"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        bachelor.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        bachelor.parse({**PAGES, "trails": "[]"}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        bachelor.parse(changed("lifts", lambda rows: rows[0].pop("sector")), NOW)
    with pytest.raises(ValueError, match="part of the mountain with no name"):
        bachelor.parse(changed("lifts", lambda rows: rows[0]["sector"].update(name=" ")), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        bachelor.parse(changed("trails", lambda rows: rows[0].update(difficulty="hardest")), NOW)
    with pytest.raises(ValueError, match="grooming the reader does not know"):
        bachelor.parse(changed("trails", lambda rows: rows[0].update(groom_status="maybe")), NOW)
    with pytest.raises(ValueError, match="has no status"):
        bachelor.parse(changed("lifts", lambda rows: rows[0].update(status=None)), NOW)
